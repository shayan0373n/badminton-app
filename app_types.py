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

# Mapping of player names to their gender ('M' or 'F')
PlayerGenders = dict[PlayerName, Gender]

# History of how often player pairs have been partnered together
PartnerHistory = dict[PlayerPair, int]

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
