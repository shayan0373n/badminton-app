# app_types.py
"""
Type aliases for the Badminton App.

This module defines type aliases to improve code readability and provide
semantic meaning to complex type hints.
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

# =============================================================================
# Basic Type Aliases
# =============================================================================


class Gender(str, Enum):
    """Player gender enumeration for strict type checking."""

    MALE = "M"
    FEMALE = "F"


# A player's name (unique identifier)
PlayerName = str

# A pair of player names (used for partners/opponents tracking)
PlayerPair = tuple[PlayerName, PlayerName]

# =============================================================================
# Optimizer Type Aliases
# =============================================================================

# Mapping of player names to their normalized ratings (0-5 scale)
PlayerRatings = dict[PlayerName, float]

# Mapping of player names to their tier ratings (Z-score normalized, 0-5 scale)
TierRatings = dict[PlayerName, float]

# Mapping of player names to their real skill (direct normalized, 0-5 scale)
RealSkills = dict[PlayerName, float]

# Mapping of player names to their gender ('M' or 'F')
PlayerGenders = dict[PlayerName, Gender]

# Gender statistics: maps Gender -> (mean_mu, std_mu, player_count)
GenderStats = dict[Gender, tuple[float, float, int]]

# History of how often player pairs have shared a court together
# Value is (partner_count, opponent_count) for debugging and weighted penalty calculation
CourtHistory = dict[PlayerPair, tuple[int, int]]

# Graph of required partner relationships (player -> set of players they must partner with)
RequiredPartners = dict[PlayerName, set[PlayerName]]


# =============================================================================
# Match Data Classes
# =============================================================================


@dataclass
class SinglesMatch:
    """A singles match assignment.

    Attributes:
        court: Court number (1-indexed)
        player_1: First player's name
        player_2: Second player's name
    """

    court: int
    player_1: PlayerName
    player_2: PlayerName


@dataclass
class DoublesMatch:
    """A doubles match assignment.

    Attributes:
        court: Court number (1-indexed)
        team_1: Tuple of player names for team 1
        team_2: Tuple of player names for team 2
    """

    court: int
    team_1: PlayerPair
    team_2: PlayerPair


# A single match assignment
Match = SinglesMatch | DoublesMatch

# List of match assignments for a round
MatchList = list[Match]


@dataclass
class Round:
    """Complete state of a match round.

    Attributes:
        matches: List of match assignments
        court_history: State of court history AFTER this round's matches
        resting_players: Set of player names who rested during this round
        rest_queue: Order of the rest queue AFTER this round's rotation
        round_num: The round number (1-indexed)
    """

    matches: MatchList
    court_history: CourtHistory
    resting_players: set[PlayerName]
    rest_queue: list[PlayerName]
    round_num: int


@dataclass
class SessionConfig:
    """Session-wide configuration parameters."""

    num_courts: int
    is_doubles: bool
    players_per_court: int
    weights: dict[str, float]
    gender_stats: GenderStats


# =============================================================================
# Result Data Classes
# =============================================================================


@dataclass
class OptimizerResult:
    """Result from the match optimizer.

    Attributes:
        matches: List of match assignments, or None if optimization failed
        court_history: Updated court history after this round
        success: Whether the optimization succeeded
    """

    matches: MatchList | None
    court_history: CourtHistory
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        self.success = self.matches is not None
