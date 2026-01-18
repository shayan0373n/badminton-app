# rating_service.py
"""
Rating service for computing tier ratings and real skills.

This module implements the "Decoupled Organic Inputs" architecture:
- Tier Rating: Z-score normalized for court grouping (social hierarchy)
- Real Skill: Direct normalized for team fairness (win probability)

The Z-score approach ensures top females are grouped with top males
while preserving accurate win probability for team balancing.
"""

from statistics import mean, stdev

from app_types import Gender, GenderStats, PlayerName, RealSkills, TierRatings
from constants import (
    FALLBACK_GENDER_MEAN,
    FALLBACK_GENDER_STD,
    MIN_PLAYERS_FOR_GENDER_STATS,
    OPTIMIZER_SKILL_RANGE,
    TTT_MU_BAD,
    TTT_MU_GOOD,
)

# Protocol-like type hint for Player (avoids circular import)
from typing import Protocol


class PlayerLike(Protocol):
    """Protocol for objects with player-like attributes."""

    name: str
    gender: Gender
    mu: float


def compute_gender_statistics(
    players: dict[PlayerName, PlayerLike],
) -> GenderStats:
    """Compute mean and standard deviation of mu for each gender.

    Args:
        players: Dict mapping player names to Player objects

    Returns:
        Dict mapping Gender to (mean_mu, std_mu, count) tuples.
        Uses fallback values when insufficient data.
    """
    stats: GenderStats = {}

    for gender in Gender:
        mu_values = [p.mu for p in players.values() if p.gender == gender]
        count = len(mu_values)

        if count >= MIN_PLAYERS_FOR_GENDER_STATS:
            gender_mean = mean(mu_values)
            # stdev requires at least 2 values
            gender_std = stdev(mu_values) if count >= 2 else FALLBACK_GENDER_STD
            # Guard against zero std (all same rating)
            if gender_std < 0.1:
                gender_std = FALLBACK_GENDER_STD
        else:
            gender_mean = FALLBACK_GENDER_MEAN
            gender_std = FALLBACK_GENDER_STD

        stats[gender] = (gender_mean, gender_std, count)

    return stats


def compute_tier_rating(
    mu: float,
    gender: Gender,
    gender_stats: GenderStats,
) -> float:
    """Compute a player's tier rating using Z-score normalization.

    Projects the player's skill onto the male scale for gender-neutral grouping.
    A top female (high Z-score in female pool) maps to the same tier as a
    top male (high Z-score in male pool).

    Args:
        mu: Player's raw TTT mu value
        gender: Player's gender
        gender_stats: Dict of (mean, std, count) per gender

    Returns:
        Tier rating on optimizer scale (typically 0-5, can extrapolate)
    """
    # Get stats for this player's gender
    g_mean, g_std, _ = gender_stats.get(
        gender, (FALLBACK_GENDER_MEAN, FALLBACK_GENDER_STD, 0)
    )

    # Get male stats as projection target
    m_mean, m_std, _ = gender_stats.get(
        Gender.MALE, (FALLBACK_GENDER_MEAN, FALLBACK_GENDER_STD, 0)
    )

    # Compute Z-score relative to own gender
    z_score = (mu - g_mean) / g_std

    # Project onto male scale
    tier_mu = m_mean + z_score * m_std

    # Normalize to optimizer scale
    rating_range = TTT_MU_GOOD - TTT_MU_BAD
    return (tier_mu - TTT_MU_BAD) / rating_range * OPTIMIZER_SKILL_RANGE


def compute_real_skill(mu: float) -> float:
    """Compute a player's real skill rating (direct normalization).

    This is the unchanged current logic - linear scaling of mu to optimizer range.

    Args:
        mu: Player's raw TTT mu value

    Returns:
        Real skill on optimizer scale (typically 0-5, can extrapolate)
    """
    rating_range = TTT_MU_GOOD - TTT_MU_BAD
    return (mu - TTT_MU_BAD) / rating_range * OPTIMIZER_SKILL_RANGE


def prepare_optimizer_ratings(
    players: dict[PlayerName, PlayerLike],
    gender_stats: GenderStats,
) -> tuple[TierRatings, RealSkills]:
    """Prepare both tier ratings and real skills for the optimizer.

    Args:
        players: Dict mapping player names to Player objects
        gender_stats: Pre-computed gender statistics

    Returns:
        Tuple of (tier_ratings, real_skills) dicts, both on optimizer scale.
    """
    tier_ratings: TierRatings = {}
    real_skills: RealSkills = {}

    for name, player in players.items():
        tier_ratings[name] = compute_tier_rating(player.mu, player.gender, gender_stats)
        real_skills[name] = compute_real_skill(player.mu)

    return tier_ratings, real_skills
