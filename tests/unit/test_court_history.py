import pytest
from constants import DEFAULT_WEIGHTS, SOLVER_BACKEND

if SOLVER_BACKEND == "ortools":
    from optimizer_ortools import generate_one_round
else:
    from optimizer import generate_one_round
from app_types import Gender, DoublesMatch, SinglesMatch
from tests.utils import generate_random_players


def test_court_history_partnership_minimization():
    """
    Verifies that the optimizer avoids repeating partnerships when possible.
    Given 8 players with identical skills, Round 2 should have different
    partners than Round 1.
    """
    # 1. Setup 8 identical players
    players = generate_random_players(8, mu_range=(25.0, 25.0))  # All same mu
    # For tests, we use normalized tier_ratings and real_skills
    tier_ratings = {p.name: 2.5 for p in players}
    real_skills = {p.name: 2.5 for p in players}
    player_genders = {p.name: p.gender for p in players}

    # 2. Run Round 1
    result1 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history={},
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )
    assert result1.success

    # 3. Run Round 2 with history from Round 1
    result2 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history=result1.court_history,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )
    assert result2.success

    # 4. Verify no partnerships were repeated using the returned history
    # In result2.court_history, every pair that has played should have partner_count <= 1
    for pair, (partner_count, opponent_count) in result2.court_history.items():
        assert (
            partner_count <= 1
        ), f"Pair {pair} repeated a partnership! History: {partner_count} partnerings."


def test_court_history_opponent_minimization():
    """
    Verifies that the optimizer also tries to avoid repeating opponents.
    In singles, we only have opponents.
    """
    # 4 Players for 2 singles courts
    players = generate_random_players(4, mu_range=(25.0, 25.0))
    tier_ratings = {p.name: 2.5 for p in players}
    real_skills = {p.name: 2.5 for p in players}
    player_genders = {p.name: p.gender for p in players}

    # Round 1
    result1 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history={},
        players_per_court=2,
        weights=DEFAULT_WEIGHTS,
        is_doubles=False,
    )
    assert result1.success

    # Round 2
    result2 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history=result1.court_history,
        players_per_court=2,
        weights=DEFAULT_WEIGHTS,
        is_doubles=False,
    )
    assert result2.success

    # Verify no opponents were repeated (in singles, all court sharing is opponent count)
    for pair, (partner_count, opponent_count) in result2.court_history.items():
        assert (
            opponent_count <= 1
        ), f"Pair {pair} played twice as opponents! History: {opponent_count} games."


def test_court_history_weight_dominance():
    """
    Verifies that the pairing weight can overrule a small skill difference.
    If P1+P2 is the 'perfect' balance but they just played together,
    the optimizer should choose a slightly 'worse' balance to ensure variety.
    """
    # 1. P1 and P2 are slightly better than P3 and P4
    # Power Balance scores:
    # (P1,P2) vs (P3,P4) -> Power 2.9 vs 2.1 (Diff 0.8)
    # (P1,P3) vs (P2,P4) -> Power 2.5 vs 2.5 (Diff 0.0) -- Wait, let's make it more distinct.

    # Setup: P1(3.0), P2(2.9), P3(2.5), P4(0.0)
    # Option A: (P1+P4) vs (P2+P3) -> (3.0+0.0)/2 = 1.5 vs (2.9+2.5)/2 = 2.7. Diff = 1.2
    # Option B: (P1+P2) vs (P3+P4) -> (3.0+2.9)/2 = 2.95 vs (2.5+0.0)/2 = 1.25. Diff = 1.7
    # Option A is much fairer (Diff 1.2 vs 1.7).

    tier_ratings = {"P1": 3.0, "P2": 2.9, "P3": 2.5, "P4": 0.0}
    real_skills = tier_ratings
    genders = {p: Gender.MALE for p in tier_ratings}

    # Round 1: No history. Optimizer should choose the 'fairer' Option A (P1+P4 vs P2+P3)
    result1 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )
    assert result1.success
    m1 = result1.matches[0]
    # Verify P1 is with P4 in Round 1
    p1_team = m1.team_1 if "P1" in m1.team_1 else m1.team_2
    assert "P4" in p1_team, f"Round 1 should pair P1+P4 for best balance. Got {p1_team}"

    # Round 2: P1+P4 now has history.
    # Even though P1+P4 is fairer, the optimizer should now prefer P1+P3 or P1+P2 to avoid repeating.
    result2 = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest=set(),
        num_courts=1,
        court_history=result1.court_history,
        is_doubles=True,
        weights={"skill": 1.0, "power": 1.0, "pairing": 10.0},  # Boost pairing weight
    )
    assert result2.success
    m2 = result2.matches[0]
    p1_team_r2 = m2.team_1 if "P1" in m2.team_1 else m2.team_2
    assert (
        "P4" not in p1_team_r2
    ), "Round 2 should NOT repeat P1+P4 partnership when pairing weight is high"
