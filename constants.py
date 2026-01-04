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
# TrueSkill Through Time Rating System Constants
# =============================================================================
# Skill levels (mu) - spread calibrated for ~99% win rate (good vs bad)
TTT_MU_GOOD = 32.0
TTT_MU_AVERAGE = 25.0
TTT_MU_BAD = 18.0

# Uncertainty levels (sigma)
TTT_SIGMA_CERTAIN = 2.5  # Well-known player
TTT_SIGMA_UNCERTAIN = 6.0  # New or rarely-seen player

# Default values for new players
TTT_DEFAULT_MU = TTT_MU_AVERAGE
TTT_DEFAULT_SIGMA = TTT_SIGMA_UNCERTAIN

# Game dynamics
TTT_BETA = 4.0  # Performance variance (higher = more randomness)
TTT_GAMMA = 0.01  # Skill drift per time unit (weekly sessions)
