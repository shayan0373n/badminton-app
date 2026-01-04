# app_types.py
"""
Type aliases for the Badminton App.

This module defines type aliases to improve code readability and provide
semantic meaning to complex type hints.
"""

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# Basic Type Aliases
# =============================================================================

from enum import Enum


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

# Mapping of player names to their gender ('M' or 'F')
PlayerGenders = dict[PlayerName, Gender]

# History of how often player pairs have been partnered together
PartnerHistory = dict[PlayerPair, int]

# A single match assignment (keys vary between singles/doubles)
Match = dict[str, Any]

# List of match assignments for a round
MatchList = list[Match]


# =============================================================================
# Result Data Classes
# =============================================================================


@dataclass
class OptimizerResult:
    """Result from the match optimizer.

    Attributes:
        matches: List of match assignments, or None if optimization failed
        partner_history: Updated partner history after this round
        success: Whether the optimization succeeded
    """

    matches: MatchList | None
    partner_history: PartnerHistory
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        self.success = self.matches is not None


@dataclass
class SinglesMatch:
    """A singles match assignment.

    Attributes:
        court: Court number (1-indexed)
        player_1: First player's name
        player_2: Second player's name
        player_1_rating: First player's rating
        player_2_rating: Second player's rating
        rating_diff: Absolute difference in ratings
    """

    court: int
    player_1: PlayerName
    player_2: PlayerName
    player_1_rating: float
    player_2_rating: float
    rating_diff: float


@dataclass
class DoublesMatch:
    """A doubles match assignment.

    Attributes:
        court: Court number (1-indexed)
        team_1: Tuple of player names for team 1
        team_2: Tuple of player names for team 2
        team_1_power: Combined rating of team 1
        team_2_power: Combined rating of team 2
        power_diff: Absolute difference in team powers
    """

    court: int
    team_1: PlayerPair
    team_2: PlayerPair
    team_1_power: float
    team_2_power: float
    power_diff: float
