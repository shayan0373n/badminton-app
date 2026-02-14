# session_logic.py
"""
Session logic for managing badminton club night sessions.

This module handles player management, match generation, and session persistence.
"""

import logging
import os
import pickle
import random
import threading
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from constants import (
    DEFAULT_IS_DOUBLES,
    PLAYERS_PER_COURT_DOUBLES,
    PLAYERS_PER_COURT_SINGLES,
    SOLVER_BACKEND,
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
    OPTIMIZER_TIME_LIMIT_FAST,
    OPTIMIZER_TIME_LIMIT_SLOW,
)
from exceptions import SessionError

if SOLVER_BACKEND == "ortools":
    from optimizer_ortools import generate_one_round
else:
    from optimizer import generate_one_round
from rating_service import prepare_optimizer_ratings
from app_types import (
    Gender,
    GenderStats,
    MatchList,
    CourtHistory,
    PlayerName,
    PlayerPair,
    RequiredPartners,
    Round,
    SessionConfig,
)

logger = logging.getLogger("app.session_logic")

SESSIONS_DIR = "sessions"


def _default_court_history_value() -> tuple[int, int]:
    """Default value factory for CourtHistory (must be module-level for pickling)."""
    return (0, 0)


# =============================================================================
# Functional Queue and Matching Helpers
# =============================================================================


def get_resting_players(
    queue: list[PlayerName], num_courts: int, players_per_court: int
) -> set[PlayerName]:
    """Pure function to determine who should rest based on current queue."""
    total_players = len(queue)
    max_courts = total_players // players_per_court
    active_courts = min(num_courts, max_courts)
    num_to_play = active_courts * players_per_court
    num_to_rest = total_players - num_to_play
    return set(queue[:num_to_rest])


def rotate_queue(queue: list[PlayerName], who_rested: set[PlayerName]) -> list[PlayerName]:
    """Pure function to rotate the queue after a round."""
    rested_in_order = [p for p in queue if p in who_rested]
    random.shuffle(rested_in_order)
    return [p for p in queue if p not in who_rested] + rested_in_order


def get_required_partners_graph(
    player_pool: dict[str, "Player"], is_doubles: bool
) -> RequiredPartners:
    """Standalone helper to build the partnership graph."""
    if not is_doubles:
        return {}

    team_groups: dict[str, list[PlayerName]] = defaultdict(list)
    for player_name, player in player_pool.items():
        if player.team_name:
            for team in player.team_name.split(","):
                team = team.strip()
                if team:
                    team_groups[team].append(player_name)

    required: RequiredPartners = defaultdict(set)
    for members in team_groups.values():
        if len(members) >= 2:
            for p1, p2 in combinations(members, 2):
                required[p1].add(p2)
                required[p2].add(p1)
    return dict(required)


def generate_next_round(
    current_state: Round,
    config: SessionConfig,
    player_pool: dict[str, "Player"],
    time_limit: float,
) -> Round | None:
    """Pure function to calculate the next round based on current state and config.

    This function is thread-safe as it does not modify any input objects.
    """
    # 1. Determine who is resting
    resting_players = get_resting_players(
        current_state.rest_queue, config.num_courts, config.players_per_court
    )

    # 2. Calculate active courts
    max_courts = len(current_state.rest_queue) // config.players_per_court
    active_courts = min(config.num_courts, max_courts)

    if active_courts == 0:
        return None

    # 3. Prepare ratings
    player_genders = {p.name: p.gender for p in player_pool.values()}
    tier_ratings, real_skills = prepare_optimizer_ratings(
        player_pool, config.gender_stats
    )

    # 4. Get required partners
    required_partners = get_required_partners_graph(player_pool, config.is_doubles)

    # 5. Call the optimizer
    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=resting_players,
        num_courts=active_courts,
        court_history=current_state.court_history,
        players_per_court=config.players_per_court,
        is_doubles=config.is_doubles,
        required_partners=required_partners,
        weights=config.weights,
        time_limit=time_limit,
    )

    if not result.success:
        return None

    # 6. Return new state (Round N+1)
    return Round(
        matches=sorted(result.matches, key=lambda m: m.court),
        court_history=result.court_history,
        resting_players=resting_players,
        rest_queue=rotate_queue(current_state.rest_queue, resting_players),
        round_num=current_state.round_num + 1,
    )


@dataclass
class Player:
    """Represents a player with their TrueSkill Through Time rating and session-specific score."""

    name: str
    gender: Gender
    # TTT priors (input to TTT - set manually based on perceived skill level)
    prior_mu: float = TTT_DEFAULT_MU
    prior_sigma: float = TTT_DEFAULT_SIGMA
    # TTT posteriors (output from TTT - computed from match history)
    # Default to None so __post_init__ can set them to prior values
    mu: float | None = None  # TTT mean skill estimate
    sigma: float | None = None  # TTT uncertainty (standard deviation)
    team_name: str = ""  # Optional team name for permanent pairing
    earned_rating: float = 0.0  # Keeping this for session-specific standings
    database_id: int | None = None  # Supabase row ID for updates

    def __post_init__(self) -> None:
        """Initialize mu/sigma to prior values when not explicitly provided."""
        if self.mu is None:
            self.mu = self.prior_mu
        if self.sigma is None:
            self.sigma = self.prior_sigma

    @property
    def rating(self) -> float:
        """Compatibility property for existing code that expects .rating"""
        return self.mu

    @property
    def conservative_rating(self) -> float:
        """Conservative skill estimate (mu - 3*sigma).

        This is a lower-bound estimate of a player's skill, commonly used
        for ranking since it accounts for uncertainty in the rating.
        """
        return self.mu - 3 * self.sigma

    def add_rating(self, amount: float) -> None:
        """Adds rating to the player (session-specific score)."""
        self.earned_rating += amount


class SessionManager:
    """Handles loading, saving, and clearing named session states."""

    @staticmethod
    def _get_session_path(session_name: str) -> str:
        """Returns the file path for a given session name."""
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        return os.path.join(SESSIONS_DIR, f"{session_name}.pkl")

    @staticmethod
    def save(session_instance: "ClubNightSession", session_name: str) -> None:
        """Saves the given session instance to a named file."""
        path = SessionManager._get_session_path(session_name)
        with open(path, "wb") as f:
            pickle.dump(session_instance, f)
        logger.info("Session '%s' saved", session_name)

    @staticmethod
    def load(session_name: str) -> "ClubNightSession | None":
        """
        Loads a session from a named file if it exists.

        Args:
            session_name: Name of the session to load

        Returns:
            The session object or None if not found/corrupted
        """
        path = SessionManager._get_session_path(session_name)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    session = pickle.load(f)
                    logger.info("Session '%s' loaded", session_name)
                    return session
            except (pickle.UnpicklingError, EOFError):
                logger.error(
                    "Failed to load session '%s' - file may be corrupted", session_name
                )
                os.remove(path)
                return None
        return None

    @staticmethod
    def clear(session_name: str) -> None:
        """Clears a named session by deleting its file."""
        path = SessionManager._get_session_path(session_name)
        if os.path.exists(path):
            os.remove(path)
            logger.info("Session '%s' cleared", session_name)

    @staticmethod
    def list_sessions() -> list[str]:
        """Returns a list of all available session names."""
        if not os.path.exists(SESSIONS_DIR):
            return []
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".pkl")]
        return [f[:-4] for f in files]  # Remove .pkl extension


class ClubNightSession:
    """
    Orchestrates a club night session using the optimizer for match generation.
    """

    def __init__(
        self,
        players: dict[str, Player],
        num_courts: int,
        gender_stats: GenderStats,
        weights: dict[str, float] | None = None,
        is_doubles: bool = True,
        database_id: int | None = None,
        is_recorded: bool = True,
    ) -> None:
        self.player_pool = players
        self.config = SessionConfig(
            num_courts=num_courts,
            is_doubles=is_doubles,
            players_per_court=(
                PLAYERS_PER_COURT_DOUBLES if is_doubles else PLAYERS_PER_COURT_SINGLES
            ),
            weights=weights or {"skill": 1.0, "power": 1.0, "pairing": 1.0},
            gender_stats=gender_stats,
        )
        self.database_id = database_id
        self.is_recorded = is_recorded

        # Initialize with "Round 0" node
        initial_queue = list(self.player_pool.keys())
        random.shuffle(initial_queue)
        self.current_state = Round(
            matches=[],
            court_history=defaultdict(_default_court_history_value),
            resting_players=set(),
            rest_queue=initial_queue,
            round_num=0,
        )
        self.backup_state: Round | None = None
        
        # Threading state (not pickled)
        self._backup_lock = threading.Lock()
        self._backup_thread: threading.Thread | None = None
        self.queued_removals: set[PlayerName] = set()

    def __getstate__(self) -> dict:
        state = self.__dict__.copy()
        state.pop("_backup_lock", None)
        state.pop("_backup_thread", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._backup_lock = threading.Lock()
        self._backup_thread = None

    def start_backup_calculation(self) -> None:
        """Triggers background calculation for the next round."""
        with self._backup_lock:
            if self._backup_thread and self._backup_thread.is_alive():
                return
            
            # Prepare data for the thread
            state_to_optimize = self.current_state
            config = self.config
            pool = self.player_pool

            def task():
                logger.info("Starting background backup calculation (30s)")
                new_backup = generate_next_round(
                    state_to_optimize, config, pool, OPTIMIZER_TIME_LIMIT_SLOW
                )
                with self._backup_lock:
                    self.backup_state = new_backup
                    if new_backup:
                        logger.info("Backup Round %d ready.", new_backup.round_num)

            self._backup_thread = threading.Thread(target=task, daemon=True)
            self._backup_thread.start()

    def prepare_round(self) -> None:
        """Determines next round. Uses backup or calculates fast."""
        # 1. Try promotion
        if self.backup_state and self.backup_state.round_num == self.current_state.round_num + 1:
            self.current_state = self.backup_state
            self.backup_state = None
            logger.info("Promoted backup to Round %d.", self.current_state.round_num)
        else:
            # 2. Fast calculation
            logger.info("Calculating fast Round %d...", self.current_state.round_num + 1)
            new_state = generate_next_round(
                self.current_state, self.config, self.player_pool, OPTIMIZER_TIME_LIMIT_FAST
            )
            if new_state:
                self.current_state = new_state
        
        # 3. Always trigger next backup
        self.start_backup_calculation()

    def finalize_round(self, winners_by_court: dict[int, tuple[str, ...]]) -> None:
        """Updates earned ratings and processes removals."""
        for court_num, winning_team in winners_by_court.items():
            for player_name in winning_team:
                if player_name in self.player_pool:
                    self.player_pool[player_name].add_rating(1)

        for player_name in self.current_state.resting_players:
            if player_name in self.player_pool:
                self.player_pool[player_name].add_rating(0.5)

        self.current_state.matches = []
        for player_name in list(self.queued_removals):
            self._remove_player_now(player_name)

    def update_courts(self, new_num_courts: int) -> None:
        """Updates court count and invalidates backup."""
        new_num_courts = int(new_num_courts)
        if new_num_courts < 1: raise SessionError("Min 1 court.")
        self.config.num_courts = new_num_courts
        self.backup_state = None

    def update_weights(self, weights: dict[str, float]) -> None:
        """Updates weights and invalidates backup."""
        self.config.weights = weights
        self.backup_state = None

    def get_standings(self) -> list[tuple[str, float]]:
        standings = [(p.name, p.earned_rating) for p in self.player_pool.values()]
        return sorted(standings, key=lambda item: item[1], reverse=True)

    def get_persistent_state(self) -> dict:
        return {
            "player_pool": self.player_pool,
            "num_courts": self.config.num_courts,
            "is_doubles": self.config.is_doubles,
            "is_recorded": self.is_recorded,
            "weights": self.config.weights.copy(),
            "gender_stats": self.config.gender_stats,
        }

    def add_player(self, name: str, gender: Gender, mu: float = TTT_DEFAULT_MU, 
                   sigma: float = TTT_DEFAULT_SIGMA, team_name: str = "") -> bool:
        if name in self.player_pool: return False

        earned = 0.0
        if self.player_pool:
            earned = sum(p.earned_rating for p in self.player_pool.values()) / len(self.player_pool)
            earned = round(earned * 2) / 2

        new_player = Player(name=name, gender=gender, mu=mu, sigma=sigma, team_name=team_name)
        new_player.add_rating(earned)
        
        self.player_pool[name] = new_player
        self.current_state.rest_queue.append(name)
        self.backup_state = None
        return True

    def remove_player(self, name: str) -> tuple[bool, str]:
        if name not in self.player_pool: return False, "not_found"
        
        is_playing = any(name in (m.player_1, m.player_2) if not self.config.is_doubles 
                        else name in m.team_1 + m.team_2 
                        for m in self.current_state.matches)
        
        if is_playing:
            self.queued_removals.add(name)
            return True, "queued"
        
        self._remove_player_now(name)
        return True, "immediate"

    def _remove_player_now(self, name: str) -> None:
        if name in self.player_pool: del self.player_pool[name]
        if name in self.current_state.rest_queue: self.current_state.rest_queue.remove(name)
        if name in self.current_state.resting_players: self.current_state.resting_players.remove(name)
        self.queued_removals.discard(name)
        self.backup_state = None
