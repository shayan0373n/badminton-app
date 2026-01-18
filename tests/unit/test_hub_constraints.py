import pytest
from app_types import Gender, OptimizerResult
from optimizer import generate_one_round


def test_hub_scenario_feasibility():
    """
    Test the "Hub" scenario where P1 can partner with P2 or P3.
    If P1 partners with P2, P3 should be 'excused' and allowed to play (e.g. with P4).
    Strict constraint logic would force P3 to rest, making a 4-player game impossible.
    """
    # 4 Players available for 1 court (doubles)
    # P1 is the Hub. P2 and P3 are spokes. P4 is a stranger.
    players = ["P1", "P2", "P3", "P4"]
    # For tests with uniform ratings, tier_ratings == real_skills
    tier_ratings = {p: 2.5 for p in players}
    real_skills = {p: 2.5 for p in players}
    genders = {p: Gender.MALE for p in players}

    # Hub constraints
    required_partners = {"P1": {"P2", "P3"}, "P2": {"P1"}, "P3": {"P1"}, "P4": set()}

    # Force 1 court, 0 resting
    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        required_partners=required_partners,
        is_doubles=True,
    )

    assert result.success is True, "Hub scenario should be feasible"
    matches = result.matches
    assert len(matches) == 1

    # Verify partnerships
    # P1 must be with P2 or P3
    match = matches[0]
    team1 = set(match.team_1)
    team2 = set(match.team_2)

    # P1's partner
    p1_partner = None
    if "P1" in team1:
        p1_partner = (team1 - {"P1"}).pop()
    elif "P1" in team2:
        p1_partner = (team2 - {"P1"}).pop()

    assert p1_partner in [
        "P2",
        "P3",
    ], f"P1 must partner with P2 or P3, got {p1_partner}"

    # Verify P3 played (if P1 picked P2) or P2 played (if P1 picked P3)
    playing_players = team1.union(team2)
    assert "P3" in playing_players
    assert "P2" in playing_players


def test_hub_forced_rest_feasibility():
    """
    Test that if the Hub (P1) is forced to rest, the spokes (P2, P3)
    are released from their constraints and can playing with others.
    """
    # 5 Players. P1 is rest. P2, P3, P4, P5 should play.
    active_players = ["P2", "P3", "P4", "P5"]
    tier_ratings = {p: 2.5 for p in active_players}
    real_skills = {p: 2.5 for p in active_players}
    genders = {p: Gender.MALE for p in active_players}

    # P1 is technically in the requirement definitions, but is in the rest set
    required_partners = {
        "P1": {"P2", "P3"},
        "P2": {"P1"},
        "P3": {"P1"},
    }

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest={"P1"},  # P1 is forced to rest
        num_courts=1,
        court_history={},
        required_partners=required_partners,
        is_doubles=True,
    )

    assert (
        result.success is True
    ), "Scenario with resting Hub should be feasible (spokes become free agents)"
    assert len(result.matches) == 1

    match = result.matches[0]
    playing = set(match.team_1) | set(match.team_2)
    assert "P2" in playing
    assert "P3" in playing


def test_triangle_scenario():
    """
    Test a Triangle {P1, P2, P3} where everyone requires everyone.
    If P2 and P3 pair up, P1 should be excused to play with P4.
    """
    players = ["P1", "P2", "P3", "P4"]  # Ends up as P2-P3 vs P1-P4 ideally
    tier_ratings = {p: 2.5 for p in players}
    real_skills = {p: 2.5 for p in players}
    genders = {p: Gender.MALE for p in players}

    required_partners = {"P1": {"P2", "P3"}, "P2": {"P1", "P3"}, "P3": {"P1", "P2"}}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        required_partners=required_partners,
        is_doubles=True,
    )

    assert (
        result.success is True
    ), "Triangle scenario with odd-one-out should be feasible"
    # Logic: One pair must form from the triangle (e.g. P1-P2), leaving P3.
    # P3 is excused because P1 is with P2 (teammate) AND P2 is with P1 (teammate).

    matches = result.matches
    teams = [set(m.team_1) for m in matches] + [set(m.team_2) for m in matches]

    # Check if a triangle pair exists
    triangle_pairs = [{"P1", "P2"}, {"P2", "P3"}, {"P1", "P3"}]
    found_triangle_pair = False
    for team in teams:
        if team in triangle_pairs:
            found_triangle_pair = True
            break

    assert found_triangle_pair, "At least one pair from the triangle should form"
