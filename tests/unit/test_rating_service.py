# tests/unit/test_rating_service.py
"""
Unit tests for the rating_service module.

Tests the Z-score normalization and tier rating calculations for the
Decoupled Organic Inputs architecture.
"""

import pytest
from statistics import mean, stdev

from app_types import Gender
from constants import (
    FALLBACK_GENDER_MEAN,
    FALLBACK_GENDER_STD,
    MIN_PLAYERS_FOR_GENDER_STATS,
    OPTIMIZER_SKILL_RANGE,
    TTT_MU_BAD,
    TTT_MU_GOOD,
)
from rating_service import (
    compute_gender_statistics,
    compute_real_skill,
    compute_tier_rating,
    prepare_optimizer_ratings,
)
from session_logic import Player


class TestComputeGenderStatistics:
    """Tests for compute_gender_statistics function."""

    def test_balanced_genders(self):
        """Test stats computation with balanced gender distribution."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=30.0),
            "M2": Player(name="M2", gender=Gender.MALE, mu=20.0),
            "M3": Player(name="M3", gender=Gender.MALE, mu=25.0),
            "F1": Player(name="F1", gender=Gender.FEMALE, mu=28.0),
            "F2": Player(name="F2", gender=Gender.FEMALE, mu=22.0),
            "F3": Player(name="F3", gender=Gender.FEMALE, mu=25.0),
        }

        stats = compute_gender_statistics(players)

        # Male stats
        male_mean, male_std, male_count = stats[Gender.MALE]
        assert male_count == 3
        assert male_mean == pytest.approx(25.0, rel=0.01)
        assert male_std == pytest.approx(stdev([30.0, 20.0, 25.0]), rel=0.01)

        # Female stats
        female_mean, female_std, female_count = stats[Gender.FEMALE]
        assert female_count == 3
        assert female_mean == pytest.approx(25.0, rel=0.01)
        assert female_std == pytest.approx(stdev([28.0, 22.0, 25.0]), rel=0.01)

    def test_insufficient_players_uses_fallback(self):
        """Test that fallback values are used when fewer than MIN players."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=25.0),
            "M2": Player(name="M2", gender=Gender.MALE, mu=30.0),
            # Only 2 males, below MIN_PLAYERS_FOR_GENDER_STATS (3)
            "F1": Player(name="F1", gender=Gender.FEMALE, mu=25.0),
            # Only 1 female
        }

        stats = compute_gender_statistics(players)

        # Male stats should use fallback (only 2 players)
        male_mean, male_std, male_count = stats[Gender.MALE]
        assert male_count == 2
        assert male_mean == FALLBACK_GENDER_MEAN
        assert male_std == FALLBACK_GENDER_STD

        # Female stats should use fallback (only 1 player)
        female_mean, female_std, female_count = stats[Gender.FEMALE]
        assert female_count == 1
        assert female_mean == FALLBACK_GENDER_MEAN
        assert female_std == FALLBACK_GENDER_STD

    def test_zero_std_uses_fallback(self):
        """Test that fallback std is used when all players have same rating."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=25.0),
            "M2": Player(name="M2", gender=Gender.MALE, mu=25.0),
            "M3": Player(name="M3", gender=Gender.MALE, mu=25.0),
        }

        stats = compute_gender_statistics(players)

        male_mean, male_std, male_count = stats[Gender.MALE]
        assert male_count == 3
        assert male_mean == pytest.approx(25.0)
        # std would be 0, so fallback should be used
        assert male_std == FALLBACK_GENDER_STD

    def test_empty_gender_uses_fallback(self):
        """Test that missing gender uses fallback values."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=25.0),
            "M2": Player(name="M2", gender=Gender.MALE, mu=30.0),
            "M3": Player(name="M3", gender=Gender.MALE, mu=20.0),
            # No females
        }

        stats = compute_gender_statistics(players)

        # Female stats should use fallback (0 players)
        female_mean, female_std, female_count = stats[Gender.FEMALE]
        assert female_count == 0
        assert female_mean == FALLBACK_GENDER_MEAN
        assert female_std == FALLBACK_GENDER_STD


class TestComputeTierRating:
    """Tests for compute_tier_rating function."""

    def test_male_at_mean_maps_to_male_mean(self):
        """A male at his gender's mean should stay at that mean."""
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier = compute_tier_rating(25.0, Gender.MALE, gender_stats)

        # z-score = (25 - 25) / 4 = 0
        # tier_mu = 25 + 0 * 4 = 25
        # tier = (25 - 18) / 14 * 5 = 2.5
        expected = (25.0 - TTT_MU_BAD) / (TTT_MU_GOOD - TTT_MU_BAD) * OPTIMIZER_SKILL_RANGE
        assert tier == pytest.approx(expected, rel=0.01)

    def test_female_at_mean_maps_to_male_mean(self):
        """A female at her gender's mean should map to male mean."""
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        # Female at female mean (22) should have z=0, projecting to male mean (25)
        tier = compute_tier_rating(22.0, Gender.FEMALE, gender_stats)

        # z-score = (22 - 22) / 3 = 0
        # tier_mu = 25 + 0 * 4 = 25
        expected = (25.0 - TTT_MU_BAD) / (TTT_MU_GOOD - TTT_MU_BAD) * OPTIMIZER_SKILL_RANGE
        assert tier == pytest.approx(expected, rel=0.01)

    def test_female_shifted_by_constant_mean_gap(self):
        """A female's mu is shifted onto the male scale by the constant male-female mean gap."""
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier = compute_tier_rating(25.0, Gender.FEMALE, gender_stats)

        # Shift = male_mean - female_mean = 3, applied regardless of spread.
        # tier_mu = 25 + 3 = 28
        expected = (28.0 - TTT_MU_BAD) / (TTT_MU_GOOD - TTT_MU_BAD) * OPTIMIZER_SKILL_RANGE
        assert tier == pytest.approx(expected, rel=0.01)

    def test_top_female_maps_below_top_male(self):
        """Under constant shift, a top female maps below a same-z-score top male."""
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        # Male at +2 std (33) is unshifted.
        male_tier = compute_tier_rating(33.0, Gender.MALE, gender_stats)

        # Female at +2 std (28) is shifted only by the mean gap (3) -> 31, not up to 33.
        female_tier = compute_tier_rating(28.0, Gender.FEMALE, gender_stats)

        expected_female = (31.0 - TTT_MU_BAD) / (TTT_MU_GOOD - TTT_MU_BAD) * OPTIMIZER_SKILL_RANGE
        assert female_tier == pytest.approx(expected_female, rel=0.01)
        assert female_tier < male_tier

    def test_missing_gender_uses_fallback(self):
        """With only males, females should use fallback stats."""
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            # No females in stats
        }

        # Should not crash, uses fallback
        tier = compute_tier_rating(22.0, Gender.FEMALE, gender_stats)

        # Uses FALLBACK_GENDER_MEAN and FALLBACK_GENDER_STD for female
        # z = (22 - 25) / 4 = -0.75
        # tier_mu = 25 + (-0.75) * 4 = 22
        assert isinstance(tier, float)


class TestComputeRealSkill:
    """Tests for compute_real_skill function."""

    def test_mu_at_bad_maps_to_zero(self):
        """TTT_MU_BAD (18) should map to 0."""
        skill = compute_real_skill(TTT_MU_BAD)
        assert skill == pytest.approx(0.0)

    def test_mu_at_good_maps_to_max(self):
        """TTT_MU_GOOD (32) should map to OPTIMIZER_SKILL_RANGE (5)."""
        skill = compute_real_skill(TTT_MU_GOOD)
        assert skill == pytest.approx(OPTIMIZER_SKILL_RANGE)

    def test_mu_at_average_maps_to_midpoint(self):
        """TTT_MU_AVERAGE (25) should map to 2.5."""
        skill = compute_real_skill(25.0)
        expected = (25.0 - TTT_MU_BAD) / (TTT_MU_GOOD - TTT_MU_BAD) * OPTIMIZER_SKILL_RANGE
        assert skill == pytest.approx(expected)

    def test_extrapolation_above(self):
        """Mu above TTT_MU_GOOD should extrapolate beyond OPTIMIZER_SKILL_RANGE."""
        skill = compute_real_skill(39.0)  # 7 above TTT_MU_GOOD
        # (39 - 18) / 14 * 5 = 21/14 * 5 = 7.5
        assert skill == pytest.approx(7.5)

    def test_extrapolation_below(self):
        """Mu below TTT_MU_BAD should extrapolate to negative."""
        skill = compute_real_skill(10.0)  # 8 below TTT_MU_BAD
        # (10 - 18) / 14 * 5 = -8/14 * 5 ≈ -2.86
        assert skill == pytest.approx(-8 / 14 * 5, rel=0.01)


class TestPrepareOptimizerRatings:
    """Tests for prepare_optimizer_ratings function."""

    def test_returns_both_rating_types(self):
        """Should return both tier_ratings and real_skills dicts."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=30.0),
            "F1": Player(name="F1", gender=Gender.FEMALE, mu=25.0),
        }
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier_ratings, real_skills = prepare_optimizer_ratings(players, gender_stats)

        assert "M1" in tier_ratings and "M1" in real_skills
        assert "F1" in tier_ratings and "F1" in real_skills

    def test_male_tier_equals_real_skill(self):
        """For males, tier rating should equal real skill (same reference scale)."""
        players = {
            "M1": Player(name="M1", gender=Gender.MALE, mu=25.0),
        }
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier_ratings, real_skills = prepare_optimizer_ratings(players, gender_stats)

        # Male at mean: tier = real_skill (both project to male scale)
        assert tier_ratings["M1"] == pytest.approx(real_skills["M1"], rel=0.01)

    def test_female_tier_differs_from_real_skill(self):
        """For females not at male mean equivalent, tier != real skill."""
        players = {
            "F1": Player(name="F1", gender=Gender.FEMALE, mu=22.0),  # At female mean
        }
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier_ratings, real_skills = prepare_optimizer_ratings(players, gender_stats)

        # Female at female mean (22) maps to male mean (25) for tier
        # But real skill is just (22 - 18) / 14 * 5
        # tier = (25 - 18) / 14 * 5 = 2.5
        # real = (22 - 18) / 14 * 5 ≈ 1.43

        assert tier_ratings["F1"] > real_skills["F1"]

    def test_constant_shift_applied_through_pipeline(self):
        """Females are shifted onto the male scale by the constant mean gap, end-to-end."""
        players = {
            "TopMale": Player(name="TopMale", gender=Gender.MALE, mu=33.0),  # +2 std
            "TopFemale": Player(name="TopFemale", gender=Gender.FEMALE, mu=28.0),  # +2 std
            "AvgMale": Player(name="AvgMale", gender=Gender.MALE, mu=25.0),  # mean
        }
        gender_stats = {
            Gender.MALE: (25.0, 4.0, 10),
            Gender.FEMALE: (22.0, 3.0, 8),
        }

        tier_ratings, real_skills = prepare_optimizer_ratings(players, gender_stats)

        # Female shifted by the mean gap (3): 28 -> 31, still below the top male's 33.
        assert tier_ratings["TopFemale"] < tier_ratings["TopMale"]

        # Real skills are raw mu, unshifted: 33 > 28.
        assert real_skills["TopMale"] > real_skills["TopFemale"]
