# session_logic.py
"""
Session logic for managing badminton club night sessions.

This module handles player management, match generation, and session persistence.
"""

import logging
import os
import pickle
import random
from collections import defaultdict
from dataclasses import dataclass

from constants import (
    DEFAULT_IS_DOUBLES,
    OPTIMIZER_SKILL_RANGE,
    PLAYERS_PER_COURT_DOUBLES,
    PLAYERS_PER_COURT_SINGLES,
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
    TTT_MU_BAD,
    TTT_MU_GOOD,
)
from exceptions import SessionError
from optimizer import generate_one_round
from app_types import Gender, MatchList, PartnerHistory, PlayerName, PlayerPair

logger = logging.getLogger("app.session_logic")

SESSIONS_DIR = "sessions"


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
    This class only contains game logic and no persistence code.
    """

    def __init__(
        self,
        players: dict[str, Player],
        num_courts: int,
        weights: dict[str, float] | None = None,
        female_female_team_penalty: float = 0,
        mixed_gender_team_penalty: float = 0,
        female_singles_penalty: float = 0,
        is_doubles: bool = True,
        database_id: int | None = None,
        is_recorded: bool = True,
    ) -> None:
        self.player_pool = players
        self.num_courts = num_courts
        self.database_id = database_id
        self.is_doubles = is_doubles
        self.is_recorded = is_recorded
        self.players_per_court = (
            PLAYERS_PER_COURT_DOUBLES if is_doubles else PLAYERS_PER_COURT_SINGLES
        )
        self.round_num = 0
        self.female_female_team_penalty = female_female_team_penalty
        self.mixed_gender_team_penalty = mixed_gender_team_penalty
        self.female_singles_penalty = female_singles_penalty

        # State required for the optimizer
        self.historical_partners: PartnerHistory = defaultdict(int)
        self.weights = (
            weights
            if weights is not None
            else {"skill": 1.0, "power": 1.0, "pairing": 1.0}
        )

        # Session flow state
        self.current_round_matches: MatchList | None = None
        self.resting_players: set[PlayerName] = set()
        self._rest_rotation_queue: list[PlayerName] = list(self.player_pool.keys())
        random.shuffle(self._rest_rotation_queue)
        self.queued_removals: set[PlayerName] = set()  # Players marked for removal

    def get_teammate_pairs(self) -> list[PlayerPair]:
        """Extract teammate pairs from player team names.

        Returns:
            List of (player1, player2) tuples for players sharing same team name.
        """
        team_groups: dict[str, list[PlayerName]] = defaultdict(list)
        for player_name, player in self.player_pool.items():
            if player.team_name and player.team_name.strip():
                team_groups[player.team_name.strip()].append(player_name)

        pairs: list[PlayerPair] = []
        for team_name, members in team_groups.items():
            if len(members) == 2:
                pairs.append(tuple(sorted(members)))
        return pairs

    def prepare_round(self) -> None:
        """
        Determines resting players and generates optimized matches for the next round.
        """
        self.round_num += 1

        # Get teammate pairs for this round
        teammate_pairs = self.get_teammate_pairs() if self.is_doubles else []

        # Create a set of all players who are in a locked pair
        paired_players = set()
        for p1, p2 in teammate_pairs:
            paired_players.add(p1)
            paired_players.add(p2)

        # 1. Determine who is resting and adjust courts if needed
        total_players = len(self.player_pool)
        max_courts = total_players // self.players_per_court
        active_courts = min(self.num_courts, max_courts)

        num_players_to_play = active_courts * self.players_per_court
        num_to_rest = total_players - num_players_to_play

        # Rest rotation with pair coordination
        # Build a map of player -> their partner (if any)
        partner_map = {}
        for p1, p2 in teammate_pairs:
            partner_map[p1] = p2
            partner_map[p2] = p1

        resting = []
        already_processed = set()

        # Go through the rotation queue in order
        for player in self._rest_rotation_queue:
            if player in already_processed:
                continue

            if len(resting) >= num_to_rest:
                break

            # Add this player to resting list
            resting.append(player)
            already_processed.add(player)

            # If they have a teammate AND we still need more resting players, add teammate too
            if player in partner_map and len(resting) < num_to_rest:
                partner = partner_map[player]
                if partner not in already_processed:
                    resting.append(partner)
                    already_processed.add(partner)

        self.resting_players = set(resting)

        # 1. Prepare raw data and Normalize ratings (0-5 scale) for optimizer stability
        original_ratings = {p.name: p.rating for p in self.player_pool.values()}
        player_genders = {p.name: p.gender for p in self.player_pool.values()}

        # Normalize using fixed anchors for consistency across sessions
        # A player with TTT_MU_BAD (18) maps to 0, TTT_MU_GOOD (32) maps to 5
        # Values outside this range extrapolate (e.g., mu=39 -> 7.5)
        rating_range = TTT_MU_GOOD - TTT_MU_BAD
        normalized_ratings = {
            n: (r - TTT_MU_BAD) / rating_range * OPTIMIZER_SKILL_RANGE
            for n, r in original_ratings.items()
        }

        # 2. Call the purified optimizer
        result = generate_one_round(
            player_ratings=normalized_ratings,
            player_genders=player_genders,
            players_to_rest=self.resting_players,
            num_courts=active_courts,
            historical_partners=self.historical_partners,
            female_female_team_penalty=self.female_female_team_penalty,
            mixed_gender_team_penalty=self.mixed_gender_team_penalty,
            female_singles_penalty=self.female_singles_penalty,
            players_per_court=self.players_per_court,
            is_doubles=self.is_doubles,
            teammate_pairs=teammate_pairs,
        )

        if not result.success:
            self.current_round_matches = None
            return

        matches = result.matches

        # 4. Update state
        self.historical_partners = result.partner_history
        self.current_round_matches = sorted(matches, key=lambda m: m["court"])

        # 4. Rotate the rest queue for the next round
        players_who_rested = [
            p for p in self._rest_rotation_queue if p in self.resting_players
        ]
        random.shuffle(players_who_rested)
        self._rest_rotation_queue = [
            p for p in self._rest_rotation_queue if p not in self.resting_players
        ] + players_who_rested

    def finalize_round(self, winners_by_court: dict[int, tuple[str, ...]]) -> None:
        """
        Updates player ratings based on results.

        Args:
            winners_by_court: A dictionary mapping court numbers to the winning team tuple.

        Raises:
            SessionError: If no round has been prepared yet.
        """
        if self.current_round_matches is None:
            raise SessionError("Cannot finalize a round that was not prepared.")

        for court_num, winning_team in winners_by_court.items():
            for player_name in winning_team:
                if player_name in self.player_pool:
                    self.player_pool[player_name].add_rating(1)

        # Add a small rating boost to resting players
        for player_name in self.resting_players:
            if player_name in self.player_pool:
                self.player_pool[player_name].add_rating(0.5)

        # Clear the matches for the completed round
        self.current_round_matches = None

        # Process any queued player removals
        for player_name in list(self.queued_removals):
            self._remove_player_now(player_name)

    def update_courts(self, new_num_courts: int) -> None:
        """Updates available courts mid session; applies on the next prepared round."""
        new_num_courts = int(new_num_courts)
        if new_num_courts < 1:
            raise SessionError("Number of courts must be at least 1.")
        self.num_courts = new_num_courts

    def get_standings(self) -> list[tuple[str, float]]:
        """Returns the current player ratings, sorted from highest to lowest."""
        standings = [(p.name, p.earned_rating) for p in self.player_pool.values()]
        return sorted(standings, key=lambda item: item[1], reverse=True)

    def get_persistent_state(self) -> dict:
        """Returns session parameters to preserve across session termination.

        This allows the next session to start with the same configuration.
        """
        return {
            "player_pool": self.player_pool,
            "num_courts": self.num_courts,
            "is_doubles": self.is_doubles,
            "is_recorded": self.is_recorded,
            "weights": self.weights.copy(),
            "female_female_team_penalty": self.female_female_team_penalty,
            "mixed_gender_team_penalty": self.mixed_gender_team_penalty,
            "female_singles_penalty": self.female_singles_penalty,
        }

    def add_player(
        self,
        name: str,
        gender: Gender,
        mu: float = TTT_DEFAULT_MU,
        sigma: float = TTT_DEFAULT_SIGMA,
        team_name: str = "",
    ) -> bool:
        """
        Adds a new player mid-session.

        - Appends the player to the end of the rest rotation queue.
        - Initializes the player's earned score to the average earned score of existing players
          so they are not disadvantaged in standings or court balance.

        Args:
            name: Player's name (must be unique)
            gender: Gender.MALE ('M') or Gender.FEMALE ('F')
            mu: TTT mean skill estimate
            sigma: TTT uncertainty (standard deviation)
            team_name: Optional team name for permanent pairing

        Returns:
            True if added successfully, False if name already exists.
        """
        # Prevent duplicates by exact name match
        if name in self.player_pool:
            return False

        # Create the player with base rating
        new_player = Player(
            name=name,
            gender=gender,
            mu=mu,
            sigma=sigma,
            team_name=team_name,
        )

        # Compute average earned among existing players (exclude the new one)
        existing_players = self.player_pool.values()
        avg_earned = 0.0
        if existing_players:
            avg_earned = sum(p.earned_rating for p in existing_players) / len(
                existing_players
            )
            # Round to nearest half point
            avg_earned = round(avg_earned * 2) / 2

        # Use add_rating to keep rating and earned_rating in sync
        new_player.add_rating(avg_earned)

        # Add to rest queue and player pool
        self.player_pool[name] = new_player
        self._rest_rotation_queue.append(name)
        self.resting_players.add(name)

        return True

    def remove_player(self, name: str) -> tuple[bool, str]:
        """
        Marks a player for removal from the session.

        - If player is currently playing, queues them for removal after round confirmation
        - If player is resting or no round active, removes immediately

        Args:
            name: The player's name to remove

        Returns:
            Tuple of (success, status) where status is 'immediate', 'queued', or 'not_found'.
        """
        if name not in self.player_pool:
            return False, "not_found"

        # Check if player is currently playing (in current_round_matches)
        is_playing = False
        if self.current_round_matches:
            for match in self.current_round_matches:
                if not self.is_doubles:
                    if name in [match["player_1"], match["player_2"]]:
                        is_playing = True
                        break
                else:  # Doubles
                    if name in match["team_1"] or name in match["team_2"]:
                        is_playing = True
                        break

        if is_playing:
            # Queue for removal after round confirmation
            self.queued_removals.add(name)
            return True, "queued"
        else:
            # Remove immediately
            self._remove_player_now(name)
            return True, "immediate"

    def _remove_player_now(self, name: str) -> None:
        """Internal method to actually remove a player from all structures."""
        if name in self.player_pool:
            del self.player_pool[name]
        if name in self._rest_rotation_queue:
            self._rest_rotation_queue.remove(name)
        if name in self.resting_players:
            self.resting_players.remove(name)
        if name in self.queued_removals:
            self.queued_removals.remove(name)
