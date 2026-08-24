"""
Centralized constants for the Badminton App.

This module contains all configuration constants used throughout the application.
"""

import os

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
SOLVER_BACKEND = os.getenv("SOLVER", "ortools").lower()

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
# Used as an additional penalty on top of the base same-court penalty.
PARTNER_HISTORY_MULTIPLIER = 1

# Court history normalization divisor for doubles
# With 6 pair combinations sharing a court (base 1) + 2 partner pairs (added multiplier 1) = 8 penalty units
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

# Default values for new players
TTT_DEFAULT_MU = TTT_MU_AVERAGE
# Sigma (uncertainty) of an unknown player. Also the ceiling age_sigma inflates
# toward, so no one is ever treated as more uncertain than a never-seen player.
TTT_DEFAULT_SIGMA = 6.0

# Minimum uncertainty (sigma) carried forward into a new season at rollover.
# Prevents rating inertia for highly active players so ratings adapt to new-season form.
SEASON_MIN_PRIOR_SIGMA = 3.0

# Game dynamics
# Beta models within-game randomness: a player's performance in a single game
# is drawn from N(skill, beta²). With beta=4.0 and 1 level = 3.5 mu:
#   beta/level = 4.0/3.5 ≈ 1.14 — a 1-level gap gives the stronger player
#   ~73% win probability per rally (Φ(3.5/(4·√2))). Higher beta = more upsets.
TTT_BETA = 4.0  # Performance noise std dev per game
# Gamma governs how much true skill can wander over time:
#   drift_per_season = sqrt(num_days) * gamma
# With weekly matches over 6 months (182 days):
#   sqrt(182) * 0.25 = 3.375 mu ≈ 1 level (1 level = 3.5 mu)
# Previous value 0.13 allowed ~0.5 levels of drift per season.
TTT_GAMMA = 0.25  # Skill drift per day (std dev of random walk per time unit)

# Challenge mode: mu added to a player's TIER rating only (court grouping),
# never to their real skill (team balancing). One club skill level is 7 mu --
# 25 is intermediate, 32 intermediate-plus, 18 intermediate-minus -- so a
# challenger is grouped roughly one court higher while team balancing still
# uses their true strength, giving them a stronger partner rather than a weaker one.
CHALLENGE_TIER_BOOST_MU = 7.0

# Session performance feedback: amount of mu added per (wins - losses) for
# matchmaking within a session. +0.5 mu per win, -0.5 mu per loss; rest is
# neutral. Symmetric around a 50% win rate.
SESSION_PERFORMANCE_FACTOR = 0.5

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
# Page Navigation Constants
# =============================================================================
PAGE_SETUP = "1_Setup.py"
PAGE_SESSION = "2_Session.py"
