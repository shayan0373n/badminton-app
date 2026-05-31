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
    """Compute trimmed mean and standard deviation of mu for each gender.

    Args:
        players: Dict mapping player names to Player objects

    Returns:
        Dict mapping Gender to (mean_mu, std_mu, count) tuples.
        Uses 10% trimmed statistics to ignore extreme outliers.
    """
    stats: GenderStats = {}

    for gender in Gender:
        mu_values = [p.mu for p in players.values() if p.gender == gender]
        count = len(mu_values)

        if count >= MIN_PLAYERS_FOR_GENDER_STATS:
            # Sort and trim top 10% and bottom 10%
            sorted_mus = sorted(mu_values)
            trim_count = int(count * 0.1)
            
            if trim_count > 0:
                trimmed_mus = sorted_mus[trim_count:-trim_count]
            else:
                trimmed_mus = sorted_mus
                
            gender_mean = mean(trimmed_mus)
            # stdev requires at least 2 values
            gender_std = stdev(trimmed_mus) if len(trimmed_mus) >= 2 else FALLBACK_GENDER_STD
            
            # Guard against zero std (all same rating)
            if gender_std < 0.1:
                gender_std = FALLBACK_GENDER_STD
        else:
            gender_mean = FALLBACK_GENDER_MEAN
            gender_std = FALLBACK_GENDER_STD

        stats[gender] = (gender_mean, gender_std, count)

    return stats


def compute_tier_rating(
    mu: float, player_gender: Gender, stats: GenderStats
) -> float:
    """Compute tier rating using Trimmed Constant Shift mapping.

    Projects the player's skill onto the male scale for gender-neutral grouping.
    A top female maps to the same tier as a top male.

    Args:
        mu: Raw TrueSkill mu value
        player_gender: Player's gender
        stats: Dictionary of GenderStats

    Returns:
        Adjusted tier rating on optimizer scale
    """
    if player_gender == Gender.MALE:
        tier_mu = mu
    elif player_gender not in stats or Gender.MALE not in stats:
        tier_mu = mu
    else:
        g_mean, _, _ = stats[player_gender]
        m_mean, _, _ = stats[Gender.MALE]
        # Trimmed Constant Shift
        shift = max(0.0, m_mean - g_mean)
        tier_mu = mu + shift

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
