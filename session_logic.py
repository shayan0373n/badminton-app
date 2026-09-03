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
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations

from constants import (
    DEFAULT_IS_DOUBLES,
    PLAYERS_PER_COURT_DOUBLES,
    PLAYERS_PER_COURT_SINGLES,
    SESSION_PERFORMANCE_FACTOR,
    SOLVER_BACKEND,
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
)
from exceptions import SessionError

if SOLVER_BACKEND == "ortools":
    from optimizer_ortools import generate_one_round
else:
    from optimizer import generate_one_round
from rating_service import prepare_optimizer_ratings
from app_types import (
    DoublesMatch,
    Gender,
    GenderStats,
    MatchList,
    CourtHistory,
    PlayerName,
    PlayerPair,
    RequiredPartners,
    RoundRecord,
)

logger = logging.getLogger("app.session_logic")

SESSIONS_DIR = "sessions"


def _default_court_history_value() -> tuple[int, int]:
    """Default value factory for CourtHistory (must be module-level for pickling)."""
    return (0, 0)


class RestRotationQueue:
    """Manages fair rotation of which players rest each round.

    Maintains a queue where players at the front rest first, then rotate
    to the back after resting. This ensures everyone gets roughly equal
    play time over multiple rounds.

    Precondition:
        Player names must be unique. Behavior is undefined if duplicates
        are present in the input list or added via add_player().
    """

    def __init__(self, players: list[PlayerName], shuffle: bool = True) -> None:
        """Initialize the rotation queue.

        Args:
            players: List of player names to include in rotation
            shuffle: Whether to randomize initial order (default True)
        """
        self._queue: list[PlayerName] = players.copy()
        if shuffle:
            random.shuffle(self._queue)

    def get_resting_players(
        self, num_courts: int, players_per_court: int = 4
    ) -> set[PlayerName]:
        """Determine which players should rest this round.

        Args:
            num_courts: Number of available courts
            players_per_court: Players needed per court (4 for doubles, 2 for singles)

        Returns:
            Set of player names who should rest this round
        """
        total_players = len(self._queue)
        max_courts = total_players // players_per_court
        active_courts = min(num_courts, max_courts)
        num_to_play = active_courts * players_per_court
        num_to_rest = total_players - num_to_play

        return set(self._queue[:num_to_rest])

    def rotate_after_round(self, who_rested: set[PlayerName]) -> None:
        """Move rested players to the end of the queue.

        Call this after a successful round to advance the rotation.

        Args:
            who_rested: Set of players who rested this round
        """
        rested_in_order = [p for p in self._queue if p in who_rested]
        random.shuffle(rested_in_order)
        self._queue = [p for p in self._queue if p not in who_rested] + rested_in_order

    def add_player(self, name: PlayerName) -> None:
        """Add a new player to the end of the queue (will rest first)."""
        if name not in self._queue:
            self._queue.append(name)

    def remove_player(self, name: PlayerName) -> None:
        """Remove a player from the queue."""
        if name in self._queue:
            self._queue.remove(name)

    def __len__(self) -> int:
        return len(self._queue)

    def __contains__(self, name: PlayerName) -> bool:
        return name in self._queue


@dataclass
class Player:
    """Represents a player with their TrueSkill Through Time rating.

    Session standings (wins, matches, ratio) are derived from
    ClubNightSession.round_history, not stored on the Player.
    """

    name: str
    gender: Gender
    # TTT priors (input to TTT - set manually based on perceived skill level)
    prior_mu: float | None = None
    prior_sigma: float = TTT_DEFAULT_SIGMA
    # TTT posteriors (output from TTT - computed from match history)
    # Default to None so __post_init__ can set them to prior values
    mu: float | None = None  # TTT mean skill estimate
    sigma: float | None = None  # TTT uncertainty (standard deviation)
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
        gender_stats: GenderStats,
        weights: dict[str, float],
        is_doubles: bool = True,
        database_id: int | None = None,
        is_recorded: bool = True,
        teams: dict[PlayerName, str] | None = None,
        candidates: dict[PlayerName, "Player"] | None = None,
    ) -> None:
        # player_pool holds everyone currently checked in and eligible to play.
        self.player_pool = players
        # candidates is the setup-time guest list: who might turn up tonight.
        # Checking in copies a candidate into player_pool; checking out removes
        # them again. Nobody is ever removed from candidates by checking out.
        self.candidates: dict[PlayerName, "Player"] = (
            candidates if candidates is not None else dict(players)
        )
        # Session-scoped team memberships: player name -> comma-separated team
        # name(s). Teams exist only for the duration of a club night.
        self.teams: dict[PlayerName, str] = teams or {}
        self.num_courts = num_courts
        self._gender_stats = gender_stats
        self.database_id = database_id
        self.is_doubles = is_doubles
        self.is_recorded = is_recorded
        self.players_per_court = (
            PLAYERS_PER_COURT_DOUBLES if is_doubles else PLAYERS_PER_COURT_SINGLES
        )

        # State required for the optimizer
        # CourtHistory values are (partner_count, opponent_count)
        self.court_history: CourtHistory = defaultdict(_default_court_history_value)
        self.weights = weights

        # Session flow state
        self.round_history: list[RoundRecord] = []
        self._round_active: bool = False
        self._rest_queue = RestRotationQueue(list(self.player_pool.keys()))
        self.queued_removals: set[PlayerName] = set()  # Players marked for removal
        # Players who asked for a harder game. Session-scoped, like teams: a
        # challenge is a statement about tonight, not a property of the player.
        self.challengers: set[PlayerName] = set()
        self.results_dirty: bool = False

    def __setstate__(self, state: dict) -> None:
        """Restores a pickled session, defaulting fields added since it was saved."""
        self.__dict__.update(state)
        if "challengers" not in state:
            self.challengers = set()
        if "candidates" not in state:
            self.candidates = dict(self.player_pool)

    # -------------------------------------------------------------------------
    # Properties (derived from round_history)
    # -------------------------------------------------------------------------

    @property
    def round_num(self) -> int:
        return len(self.round_history)

    @property
    def current_round_matches(self) -> MatchList | None:
        if not self.round_history:
            return None
        return self.round_history[-1].matches

    @property
    def resting_players(self) -> set[PlayerName]:
        if not self.round_history:
            return set()
        return self.round_history[-1].resting_players

    def get_required_partners(self) -> RequiredPartners:
        """Build graph of required partner relationships from team memberships.

        Players can belong to multiple teams (comma-separated team names).
        Each team creates pairwise "must partner with" relationships between members.

        Returns:
            Dict mapping each player to the set of players they must partner with
            (when at least one is available).
        """
        # Parse comma-separated team names into groups
        team_groups: dict[str, list[PlayerName]] = defaultdict(list)
        for player_name, team_names in self.teams.items():
            if player_name not in self.player_pool:
                continue
            for team in team_names.split(","):
                team = team.strip()
                if team:
                    team_groups[team].append(player_name)

        # Build required partners graph from team memberships
        required: RequiredPartners = defaultdict(set)
        for members in team_groups.values():
            if len(members) >= 2:
                for p1, p2 in combinations(members, 2):
                    required[p1].add(p2)
                    required[p2].add(p1)
        return dict(required)

    # -------------------------------------------------------------------------
    # Pairing groups (a friendlier face on `teams`)
    # -------------------------------------------------------------------------

    def get_groups(self) -> dict[str, list[PlayerName]]:
        """Returns team name -> members, for members still in the session.

        Groups of one are dropped: a lone member imposes no partner constraint,
        so surfacing it would show a pairing that does not exist.
        """
        groups: dict[str, list[PlayerName]] = defaultdict(list)
        for player_name, team_names in self.teams.items():
            if player_name not in self.player_pool:
                continue
            for team in team_names.split(","):
                team = team.strip()
                if team:
                    groups[team].append(player_name)
        return {name: members for name, members in groups.items() if len(members) > 1}

    def _next_group_name(self) -> str:
        """Returns an unused generated group name."""
        existing = {
            team.strip()
            for names in self.teams.values()
            for team in names.split(",")
            if team.strip()
        }
        i = 1
        while f"G{i}" in existing:
            i += 1
        return f"G{i}"

    def _memberships(self, name: PlayerName) -> list[str]:
        """Returns the group names a player carries, in the order they joined."""
        return [team.strip() for team in self.teams.get(name, "").split(",") if team.strip()]

    def group_of(self, name: PlayerName) -> str | None:
        """Returns the first group a player belongs to, or None."""
        for group_name, members in self.get_groups().items():
            if name in members:
                return group_name
        return None

    def pair_players(self, first: PlayerName, second: PlayerName) -> str | None:
        """Pairs two players, leaving any pairs either already has intact.

        A pair is always exactly two people. Dragging C onto A when A is already
        with B gives A a second pair rather than a threesome, which the optimizer
        reads as "A partners B or C" -- a partner constraint only makes sense
        between two players, and A is free to honour either one in a given round.

        Returns:
            The group name, or None if either player is not checked in or the
            two are the same person.
        """
        if first == second:
            return None
        if first not in self.player_pool or second not in self.player_pool:
            return None

        # Dragging the same two together twice is a no-op, not a duplicate pair.
        shared = set(self._memberships(first)) & set(self._memberships(second))
        if shared:
            return sorted(shared)[0]

        group = self._next_group_name()
        for player in (first, second):
            self.teams[player] = ",".join([*self._memberships(player), group])
        return group

    def unpair_player(self, name: PlayerName) -> bool:
        """Removes a player from every group they are in. Returns True if any."""
        if self.group_of(name) is None:
            return False
        self.teams.pop(name, None)
        return True

    def dissolve_group(self, group_name: str) -> bool:
        """Breaks up one group, leaving its members' other pairs alone."""
        members = self.get_groups().get(group_name)
        if not members:
            return False
        for member in members:
            remaining = [g for g in self._memberships(member) if g != group_name]
            if remaining:
                self.teams[member] = ",".join(remaining)
            else:
                self.teams.pop(member, None)
        return True

    def prepare_round(self) -> None:
        """Determines resting players and generates optimized matches for the next round.

        On success, appends a new RoundRecord to round_history.
        On failure, no state is modified.
        """
        # Get required partners graph for this round (doubles only)
        required_partners = self.get_required_partners() if self.is_doubles else {}

        # Determine who is resting using the rotation queue
        resting = self._rest_queue.get_resting_players(
            self.num_courts, self.players_per_court
        )

        # Calculate active courts for optimizer
        total_players = len(self.player_pool)
        max_courts = total_players // self.players_per_court
        active_courts = min(self.num_courts, max_courts)

        # Boost mu by session performance for matchmaking: (wins - losses) * factor.
        # Symmetric around 50% win rate; resting is neutral.
        stats = self._compute_session_stats()
        boosted_pool = deepcopy(self.player_pool)
        for name, p in boosted_pool.items():
            matches, wins = stats.get(name, (0, 0))
            losses = matches - wins
            p.mu += (wins - losses) * SESSION_PERFORMANCE_FACTOR

        player_genders = {p.name: p.gender for p in self.player_pool.values()}
        tier_ratings, real_skills = prepare_optimizer_ratings(
            boosted_pool, self._gender_stats, self.challengers
        )

        # Call the optimizer with decoupled inputs
        result = generate_one_round(
            tier_ratings=tier_ratings,
            real_skills=real_skills,
            player_genders=player_genders,
            players_to_rest=resting,
            num_courts=active_courts,
            court_history=self.court_history,
            players_per_court=self.players_per_court,
            weights=self.weights,
            is_doubles=self.is_doubles,
            required_partners=required_partners,
        )

        if not result.success:
            return

        # Commit state only on success
        record = RoundRecord(
            round_num=len(self.round_history) + 1,
            matches=sorted(result.matches, key=lambda m: m.court),
            resting_players=resting,
        )
        self.round_history.append(record)
        self._round_active = True
        self.court_history = result.court_history
        self._rest_queue.rotate_after_round(resting)

    def finalize_round(self) -> None:
        """Finalizes the current round and processes any queued player removals.

        Standings are derived from round_history on demand, so no recompute is
        needed here -- winners stored in round_history[-1].winners_by_court are
        already the source of truth.

        Raises:
            SessionError: If no round has been prepared yet.
        """
        if not self.round_history:
            raise SessionError("Cannot finalize a round that was not prepared.")

        self._round_active = False

        # Process any queued player removals
        for player_name in list(self.queued_removals):
            self._remove_player_now(player_name)

    def update_courts(self, new_num_courts: int) -> None:
        """Updates available courts mid session; applies on the next prepared round."""
        new_num_courts = int(new_num_courts)
        if new_num_courts < 1:
            raise SessionError("Number of courts must be at least 1.")
        self.num_courts = new_num_courts

    def set_court_result(
        self, round_idx: int, court_num: int, winner: tuple[str, ...] | None
    ) -> None:
        """Sets or clears a single court result in round history.

        Args:
            round_idx: Index into round_history (0-based)
            court_num: Court number (1-indexed)
            winner: Winning team tuple, or None to clear
        """
        if round_idx < 0 or round_idx >= len(self.round_history):
            raise SessionError(f"Invalid round index: {round_idx}")

        record = self.round_history[round_idx]
        previous_winner = record.winners_by_court.get(court_num)
        if winner is None:
            record.winners_by_court.pop(court_num, None)
        else:
            record.winners_by_court[court_num] = winner

        if previous_winner != winner:
            self.results_dirty = True

    @staticmethod
    def _get_match_players(matches: MatchList) -> set[PlayerName]:
        """Extracts all player names from a list of matches."""
        players: set[PlayerName] = set()
        for match in matches:
            if isinstance(match, DoublesMatch):
                players.update(match.team_1)
                players.update(match.team_2)
            else:
                players.add(match.player_1)
                players.add(match.player_2)
        return players

    @staticmethod
    def _match_player_names(match) -> set[PlayerName]:
        """Returns the set of players in a single match (singles or doubles)."""
        if isinstance(match, DoublesMatch):
            return set(match.team_1) | set(match.team_2)
        return {match.player_1, match.player_2}

    def _compute_session_stats(self) -> dict[PlayerName, tuple[int, int]]:
        """Walks round_history once and returns {name: (matches, wins)} for every current player.

        A match counts only when its court has a recorded winner. Players in
        recorded matches get +1 matches; players on the winning team get +1 wins.
        """
        stats: dict[PlayerName, tuple[int, int]] = {
            name: (0, 0) for name in self.player_pool
        }
        for record in self.round_history:
            for match in record.matches:
                if match.court not in record.winners_by_court:
                    continue
                winners = set(record.winners_by_court[match.court])
                for name in self._match_player_names(match):
                    if name not in stats:
                        continue
                    m, w = stats[name]
                    stats[name] = (m + 1, w + (1 if name in winners else 0))
        return stats

    def wins(self, name: PlayerName) -> int:
        """Returns the number of matches this player has won so far this session."""
        return self._compute_session_stats().get(name, (0, 0))[1]

    def matches_played(self, name: PlayerName) -> int:
        """Returns the number of matches this player has played so far this session."""
        return self._compute_session_stats().get(name, (0, 0))[0]

    def get_standings(self) -> list[tuple[str, int, int, float]]:
        """Returns standings as (name, matches, wins, ratio) sorted by ratio desc then wins desc.

        Ratio is wins / matches, or 0.0 when matches == 0.
        """
        stats = self._compute_session_stats()
        rows = [
            (name, matches, wins, (wins / matches) if matches else 0.0)
            for name, (matches, wins) in stats.items()
        ]
        return sorted(rows, key=lambda r: (r[3], r[2]), reverse=True)

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
            "gender_stats": self._gender_stats,
        }

    def add_player(
        self,
        name: str,
        gender: Gender,
        prior_mu: float = TTT_DEFAULT_MU,
        prior_sigma: float = TTT_DEFAULT_SIGMA,
        mu: float | None = None,
        sigma: float | None = None,
        team_name: str = "",
    ) -> bool:
        """Adds a new player mid-session at the back of the rest queue.

        Args:
            name: Player's name (must be unique)
            gender: Gender.MALE ('M') or Gender.FEMALE ('F')
            prior_mu: TTT prior mean (manual skill estimate, input to rating recalc)
            prior_sigma: TTT prior uncertainty (standard deviation)
            mu: TTT posterior mean; defaults to prior_mu when None
            sigma: TTT posterior uncertainty; defaults to prior_sigma when None
            team_name: Optional comma-separated team name(s) for fixed pairing

        Returns:
            True if added successfully, False if name already exists.
        """
        if name in self.player_pool:
            return False

        player = Player(
            name=name,
            gender=gender,
            prior_mu=prior_mu,
            prior_sigma=prior_sigma,
            mu=mu,
            sigma=sigma,
        )
        self.player_pool[name] = player
        self.candidates.setdefault(name, player)
        if team_name:
            self.teams[name] = team_name
        self._rest_queue.add_player(name)
        return True

    def check_in(self, name: PlayerName, wants_challenge: bool = False) -> bool:
        """Moves a candidate into the playing pool.

        Checking in *is* joining the pool, so this reuses add_player and the
        rest rotation needs no notion of presence beyond who is in the pool.

        Args:
            name: A name from `candidates`
            wants_challenge: Set when the player long-pressed for a harder game

        Returns:
            True if they were checked in, False if unknown or already in.
        """
        if name in self.player_pool:
            return False

        candidate = self.candidates.get(name)
        if candidate is None:
            return False

        added = self.add_player(
            name=candidate.name,
            gender=candidate.gender,
            prior_mu=candidate.prior_mu,
            prior_sigma=candidate.prior_sigma,
            mu=candidate.mu,
            sigma=candidate.sigma,
        )
        if added and wants_challenge:
            self.set_challenge(name, True)
        return added

    def check_out(self, name: PlayerName) -> tuple[bool, str]:
        """Removes a player from the pool, keeping them on the candidate list.

        Returns:
            Tuple of (success, status) where status is 'immediate', 'queued', or
            'not_found' -- queued when they are mid-round, exactly as removal works.
        """
        return self.remove_player(name)

    def set_challenge(self, name: PlayerName, wants_challenge: bool) -> bool:
        """Flags or clears a player's request for a harder game.

        The flag persists until cleared; it is not consumed by being honoured.

        Args:
            name: The player's name
            wants_challenge: True to flag, False to clear

        Returns:
            True if the player is in the session, False otherwise.
        """
        if name not in self.player_pool:
            return False

        if wants_challenge:
            self.challengers.add(name)
        else:
            self.challengers.discard(name)
        return True

    def toggle_challenge(self, name: PlayerName) -> bool:
        """Flips a player's challenge flag. Returns the resulting state."""
        self.set_challenge(name, name not in self.challengers)
        return name in self.challengers

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

        # Check if player is currently playing in an active (non-finalized) round
        is_playing = (
            self._round_active
            and self.current_round_matches is not None
            and name in self._get_match_players(self.current_round_matches)
        )

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
        self.teams.pop(name, None)
        self.challengers.discard(name)
        self._rest_queue.remove_player(name)
        self.queued_removals.discard(name)
