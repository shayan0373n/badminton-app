"""
Centralized constants for the Badminton App.

This module contains all configuration constants used throughout the application.
"""

import os
from datetime import datetime

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
# Solver Backend
# =============================================================================
# "ortools" uses Google OR-Tools CP-SAT solver (free, open source)
# "gurobi" uses PuLP with Gurobi solver (requires commercial license)
# Use environment variable 'SOLVER' to override the default backend.
SOLVER_BACKEND = os.getenv("SOLVER", "gurobi").lower()

# =============================================================================
# Optimizer Constants
# =============================================================================

# The contract for the optimizer math: All ratings will be scaled to this range
OPTIMIZER_RANK_MIN = 0.0
OPTIMIZER_RANK_MAX = 5.0
OPTIMIZER_SKILL_RANGE = OPTIMIZER_RANK_MAX - OPTIMIZER_RANK_MIN

# Big-M constant for mixed-integer programming constraints
# Used to relax constraints when a binary variable is 0 (off).
# Must be significantly larger than any possible potential rating or power sum
OPTIMIZER_BIG_M = 1000.0

# Partner history multiplier: partners accumulate penalty faster than opponents
# If a pair are partners: Penalty = PARTNER_HISTORY_MULTIPLIER * partner_count
# If a pair are opponents: Penalty = opponent_count
PARTNER_HISTORY_MULTIPLIER = 2

# Court history normalization divisor for doubles
# With 2 partner pairs (×2 weight) + 4 opponent pairs (×1 weight) = 8 penalty units per court
# Dividing by 4 normalizes to ~2 units per court
COURT_HISTORY_NORMALIZATION = 4

# =============================================================================
# Session Setup Constants
# =============================================================================
DEFAULT_NUM_COURTS = 2

# Default optimizer weights (all 1 = equal importance)
DEFAULT_WEIGHTS = {
    "skill": 1,
    "power": 1,
    "pairing": 1,
}

# Default time limit for the optimizer in seconds
OPTIMIZER_TIME_LIMIT = 10.0

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
# Beta models within-game randomness: a player's performance in a single game
# is drawn from N(skill, beta²). With beta=4.0 and 1 level = 3.5 mu:
#   beta/level = 4.0/3.5 ≈ 1.14 — a 1-level gap gives the stronger player
#   ~76% win probability per rally. Higher beta = more upsets.
TTT_BETA = 4.0  # Performance noise std dev per game
# Gamma governs how much true skill can wander over time:
#   drift_per_season = sqrt(num_days) * gamma
# With weekly matches over 6 months (182 days):
#   sqrt(182) * 0.13 = 1.75 mu ≈ 0.5 levels (1 level = 3.5 mu)
# Previous value 0.55 allowed ~2.1 levels of drift per season.
TTT_GAMMA = 0.13  # Skill drift per day (std dev of random walk per time unit)

# =============================================================================
# Gender Statistics Fallback Constants
#
# Used when computing Z-scores for tier ratings when a gender has too few
# players or zero standard deviation.
# =============================================================================
FALLBACK_GENDER_MEAN = TTT_MU_AVERAGE  # 25.0
FALLBACK_GENDER_STD = 4.0
MIN_PLAYERS_FOR_GENDER_STATS = 3

# =============================================================================
# Time & Timestamp Constants
# =============================================================================
TTT_REFERENCE_DATE = datetime(2026, 1, 1)

# =============================================================================
# Page Navigation Constants
# =============================================================================
PAGE_SETUP = "1_Setup.py"
PAGE_SESSION = "2_Session.py"
