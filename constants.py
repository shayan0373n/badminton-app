"""
Centralized constants for the Badminton App.

This module contains all configuration constants used throughout the application.
"""

# =============================================================================
# Game Mode Constants
# =============================================================================
# is_doubles=True means Doubles mode (4 players per court)
# is_doubles=False means Singles mode (2 players per court)
DEFAULT_IS_DOUBLES = True

# Players per court by game mode
PLAYERS_PER_COURT_DOUBLES = 4
PLAYERS_PER_COURT_SINGLES = 2

# =============================================================================
# Optimizer Constants
# =============================================================================

# The contract for the optimizer math: All ratings will be scaled to this range
OPTIMIZER_RANK_MIN = 0.0
OPTIMIZER_RANK_MAX = 5.0
OPTIMIZER_SKILL_RANGE = OPTIMIZER_RANK_MAX - OPTIMIZER_RANK_MIN

# =============================================================================
# Gender Penalty Constants (relative to optimizer's 0-5 scale)
#
# These penalties adjust the effective "power" of teams/players for balancing:
# - PENALTY_FEMALE_FEMALE_TEAM: Applied to doubles teams with two female players
# - PENALTY_MIXED_GENDER_TEAM: Applied to doubles teams with one male + one female
# - PENALTY_FEMALE_SINGLES: Applied to female players in singles matches
# =============================================================================
DEFAULT_PENALTY_FEMALE_FEMALE_TEAM = -5.0
DEFAULT_PENALTY_MIXED_GENDER_TEAM = -3.0
DEFAULT_PENALTY_FEMALE_SINGLES = -2.0

# =============================================================================
# Session Setup Constants
# =============================================================================
DEFAULT_NUM_COURTS = 2

# Default optimizer weights
DEFAULT_WEIGHTS = {
    "skill": 1,
    "power": 3,
    "pairing": 2,
    "female_female_team_penalty": DEFAULT_PENALTY_FEMALE_FEMALE_TEAM,
    "mixed_gender_team_penalty": DEFAULT_PENALTY_MIXED_GENDER_TEAM,
    "female_singles_penalty": DEFAULT_PENALTY_FEMALE_SINGLES,
}

# =============================================================================
# Glicko-2 Rating System Constants
# =============================================================================
GLICKO2_TAU = 0.5  # System volatility constraint (typically 0.3-1.2)
GLICKO2_EPSILON = 0.000001  # Convergence tolerance
GLICKO2_DEFAULT_RATING = 1500.0
GLICKO2_DEFAULT_RD = 350.0
GLICKO2_DEFAULT_VOLATILITY = 0.06
GLICKO2_SCALE = 173.7178  # Scaling factor (400/ln(10))
