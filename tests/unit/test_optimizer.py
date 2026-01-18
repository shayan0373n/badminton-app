import pytest
from optimizer import generate_one_round
from app_types import Gender, SinglesMatch, DoublesMatch
from session_logic import Player
from tests.utils import generate_random_players, run_optimizer_rounds


def _make_ratings(players):
    """Helper to create tier_ratings and real_skills from player list."""
    # For tests, we use the same values for both (normalized prior_mu)
    ratings = {p.name: p.prior_mu for p in players}
    return ratings, ratings  # tier_ratings, real_skills


def test_more_player_than_courts_with_no_rest():
    players = generate_random_players(5)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}
    num_courts = 1

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=num_courts,
        court_history={},
        is_doubles=True,
    )
    assert result.success is True
    matches = result.matches
    assert len(matches) == 1


def test_generate_one_round_doubles(sample_players, sample_gender_stats):
    from rating_service import prepare_optimizer_ratings

    tier_ratings, real_skills = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    player_genders = {name: p.gender for name, p in sample_players.items()}
    num_courts = 2

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=num_courts,
        court_history={},
        is_doubles=True,
    )

    assert result.success is True
    matches = result.matches
    assert len(matches) == 2
    for match in matches:
        assert isinstance(match, DoublesMatch)
        assert len(match.team_1) == 2
        assert len(match.team_2) == 2
        # Check that all players in the match are unique
        all_players = list(match.team_1) + list(match.team_2)
        assert len(set(all_players)) == 4


def test_generate_one_round_singles(sample_players, sample_gender_stats):
    from rating_service import prepare_optimizer_ratings

    tier_ratings, real_skills = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    player_genders = {name: p.gender for name, p in sample_players.items()}
    available_players = list(tier_ratings.keys())[:4]
    num_courts = 2

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(list(tier_ratings.keys())[4:]),
        num_courts=num_courts,
        court_history={},
        players_per_court=2,
        is_doubles=False,
    )

    assert result.success is True
    matches = result.matches
    assert len(matches) == 2
    for match in matches:
        assert isinstance(match, SinglesMatch)
        assert match.player_1 in available_players
        assert match.player_2 in available_players
        assert match.player_1 != match.player_2


def test_optimizer_insufficient_players(sample_players, sample_gender_stats):
    from rating_service import prepare_optimizer_ratings

    tier_ratings, real_skills = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    player_genders = {name: p.gender for name, p in sample_players.items()}
    # Only 3 players for doubles (requires 4)
    available_players = ["Alice", "Bob", "Charlie"]
    num_courts = 1

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(list(tier_ratings.keys())) - set(available_players),
        num_courts=num_courts,
        court_history={},
        is_doubles=True,
    )

    # 3 players cannot fill 1 doubles court = 0 courts = empty matches
    assert result.success is True
    assert result.matches == []


def test_locked_pair_multi_round():
    """
    Two players with mutual required_partners constraint must always partner if none of them rest.
    Verifies constraint holds across multiple rounds with randomization.
    Graph: P1 -- P2
    """
    players = generate_random_players(8)
    players_dict = {p.name: p for p in players}

    # P1 and P2 are a locked pair
    required_partners = {
        "P1": {"P2"},
        "P2": {"P1"},
    }

    for round_num, result in run_optimizer_rounds(
        players_dict,
        num_courts=2,
        required_partners=required_partners,
        num_rounds=10,
    ):
        assert result.success, f"Round {round_num + 1} failed"

        # If P1 plays, P2 must be their partner
        for match in result.matches:
            team1, team2 = set(match.team_1), set(match.team_2)
            if "P1" in team1:
                assert "P2" in team1, f"Round {round_num + 1}: P1 in {team1} without P2"
            elif "P1" in team2:
                assert "P2" in team2, f"Round {round_num + 1}: P1 in {team2} without P2"


def test_square_graph_constraint():
    """
    Four players with square graph constraints (edges on perimeter only).
    Each player can partner with 2 of the other 3, forming valid pairings.
    Graph: P1 -- P2
            |    |
           P3 -- P4
    """
    players = generate_random_players(8)
    players_dict = {p.name: p for p in players}

    required_partners = {
        "P1": {"P2", "P3"},
        "P2": {"P1", "P4"},
        "P3": {"P1", "P4"},
        "P4": {"P2", "P3"},
    }
    group = {"P1", "P2", "P3", "P4"}

    for round_num, result in run_optimizer_rounds(
        players_dict,
        num_courts=2,
        required_partners=required_partners,
        num_rounds=10,
    ):
        assert result.success, f"Round {round_num + 1} failed"

        # Verify: if a group member plays, their partner must also be from the group
        for match in result.matches:
            team1, team2 = set(match.team_1), set(match.team_2)

            for team in [team1, team2]:
                group_in_team = team & group
                if group_in_team:
                    # At least 2 group members must be together
                    assert len(group_in_team) >= 2, (
                        f"Round {round_num + 1}: Group member(s) {group_in_team} "
                        f"in team {team} without another group partner"
                    )


# =============================================================================
# Singles Tests
# =============================================================================


def test_singles_exact_players_for_one_court():
    """Exactly 2 players for 1 singles court - no one rests."""
    players = generate_random_players(2)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        players_per_court=2,
        is_doubles=False,
    )

    assert result.success is True
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.player_1 != match.player_2
    assert {match.player_1, match.player_2} == {"P1", "P2"}


def test_singles_multiple_courts():
    """4 players for 2 singles courts."""
    players = generate_random_players(4)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history={},
        players_per_court=2,
        is_doubles=False,
    )

    assert result.success is True
    assert len(result.matches) == 2

    # All 4 unique players should be in matches
    all_players = set()
    for match in result.matches:
        all_players.add(match.player_1)
        all_players.add(match.player_2)
    assert len(all_players) == 4


def test_singles_insufficient_players():
    """Only 1 player for singles - returns empty matches."""
    players = generate_random_players(1)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        players_per_court=2,
        is_doubles=False,
    )

    # 1 player cannot fill 1 singles court = 0 courts = empty matches
    assert result.success is True
    assert result.matches == []


# =============================================================================
# Doubles Boundary Tests
# =============================================================================


def test_doubles_exact_players_for_one_court():
    """Exactly 4 players for 1 doubles court - no one rests."""
    players = generate_random_players(4)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        is_doubles=True,
    )

    assert result.success is True
    assert len(result.matches) == 1
    match = result.matches[0]
    all_players = set(match.team_1) | set(match.team_2)
    assert all_players == {"P1", "P2", "P3", "P4"}


def test_doubles_exact_players_for_two_courts():
    """Exactly 8 players for 2 doubles courts - no one rests."""
    players = generate_random_players(8)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history={},
        is_doubles=True,
    )

    assert result.success is True
    assert len(result.matches) == 2

    # All 8 unique players should be playing
    all_players = set()
    for match in result.matches:
        all_players.update(match.team_1)
        all_players.update(match.team_2)
    assert len(all_players) == 8


def test_doubles_more_courts_than_players_allow():
    """Requesting more courts than players can fill auto-reduces to max feasible.

    The optimizer automatically reduces court count to what's possible.
    """
    players = generate_random_players(5)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    # Rest 1 player to have exactly 4 available, request 3 courts
    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest={"P5"},
        num_courts=3,  # Request 3 but only 4 players = 1 court possible
        court_history={},
        is_doubles=True,
    )

    # Optimizer auto-reduces to 1 court
    assert result.success is True
    assert len(result.matches) == 1


# =============================================================================
# Edge Cases
# =============================================================================


def test_all_players_resting():
    """All players resting - returns empty matches (no one to play)."""
    players = generate_random_players(4)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest={"P1", "P2", "P3", "P4"},  # Everyone resting
        num_courts=1,
        court_history={},
        is_doubles=True,
    )

    # No available players = 0 courts = empty matches
    assert result.success is True
    assert result.matches == []


def test_zero_courts():
    """Zero courts requested - returns empty matches (valid edge case)."""
    players = generate_random_players(4)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=0,
        court_history={},
        is_doubles=True,
    )

    # Zero courts = zero matches, but technically success
    assert result.success is True
    assert result.matches == []


def test_empty_player_pool():
    """No players at all - returns empty matches."""
    result = generate_one_round(
        tier_ratings={},
        real_skills={},
        player_genders={},
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        is_doubles=True,
    )

    # No players = 0 courts = empty matches
    assert result.success is True
    assert result.matches == []


def test_no_duplicate_players_across_matches():
    """Players should only appear in one match per round."""
    players = generate_random_players(12)
    tier_ratings, real_skills = _make_ratings(players)
    player_genders = {p.name: p.gender for p in players}

    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=3,
        court_history={},
        is_doubles=True,
    )

    assert result.success is True
    assert len(result.matches) == 3

    # Collect all players
    all_players = []
    for match in result.matches:
        all_players.extend(match.team_1)
        all_players.extend(match.team_2)

    # No duplicates
    assert len(all_players) == len(
        set(all_players)
    ), "Players should not appear in multiple matches"
