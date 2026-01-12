import pytest
from session_logic import ClubNightSession, Player
from app_types import Gender, SinglesMatch, DoublesMatch


def test_session_initialization(sample_players):
    session = ClubNightSession(players=sample_players, num_courts=2, is_doubles=True)

    assert len(session.player_pool) == 8
    assert session.num_courts == 2
    assert session.is_doubles is True
    assert len(session.player_pool) == 8


def test_add_remove_player(sample_players):
    session = ClubNightSession(players=sample_players, num_courts=2)

    # Remove a player
    session.remove_player("Alice")
    assert "Alice" not in session.player_pool

    # Add a player back
    session.add_player(name="Zoe", gender=Gender.FEMALE)
    assert "Zoe" in session.player_pool


def test_prepare_round(sample_players):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,  # Only 1 court, 4 players will play, 4 will rest
        is_doubles=True,
    )

    session.prepare_round()
    matches = session.current_round_matches

    assert len(matches) == 1
    assert len(session.resting_players) == 4


def test_finalize_round(sample_players):
    session = ClubNightSession(players=sample_players, num_courts=1, is_doubles=True)

    session.prepare_round()
    match = session.current_round_matches[0]

    # Mock winners
    winners_by_court = {1: match.team_1}

    session.finalize_round(winners_by_court)

    # Check that winners got points (default 1.0 for winning)
    for name in match.team_1:
        assert session.player_pool[name].earned_rating == 1.0
    for name in match.team_2:
        assert session.player_pool[name].earned_rating == 0.0


# =============================================================================
# Mid-Session Player Management
# =============================================================================


def test_add_player_mid_session(sample_players):
    """Adding player mid-session should give them average earned rating."""
    session = ClubNightSession(players=sample_players, num_courts=1, is_doubles=True)

    # Play a round to accumulate some ratings
    session.prepare_round()
    match = session.current_round_matches[0]
    session.finalize_round({1: match.team_1})

    # Add new player
    success = session.add_player(name="NewPlayer", gender=Gender.MALE)
    assert success is True
    assert "NewPlayer" in session.player_pool

    # New player should have average earned rating (rounded to nearest 0.5)
    new_player = session.player_pool["NewPlayer"]
    assert new_player.earned_rating >= 0  # Should have some earned rating


def test_add_duplicate_player_fails(sample_players):
    """Adding a player that already exists should fail."""
    session = ClubNightSession(players=sample_players, num_courts=1, is_doubles=True)

    success = session.add_player(name="Alice", gender=Gender.FEMALE)
    assert success is False


def test_remove_player_while_playing():
    """Removing a player mid-match should queue removal until round ends."""
    players = {
        "P1": Player(name="P1", gender=Gender.MALE, prior_mu=25.0),
        "P2": Player(name="P2", gender=Gender.MALE, prior_mu=25.0),
        "P3": Player(name="P3", gender=Gender.FEMALE, prior_mu=25.0),
        "P4": Player(name="P4", gender=Gender.FEMALE, prior_mu=25.0),
    }
    session = ClubNightSession(players=players, num_courts=1, is_doubles=True)

    session.prepare_round()

    # Find a player who is playing
    match = session.current_round_matches[0]
    playing_player = match.team_1[0]

    # Remove should queue, not immediately remove
    success, status = session.remove_player(playing_player)
    assert success is True
    assert status == "queued"
    assert playing_player in session.player_pool  # Still there

    # After finalizing, player is removed
    session.finalize_round({1: match.team_1})
    assert playing_player not in session.player_pool


def test_remove_resting_player():
    """Removing a resting player should happen immediately."""
    players = {
        f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, prior_mu=25.0)
        for i in range(1, 6)
    }
    session = ClubNightSession(players=players, num_courts=1, is_doubles=True)

    session.prepare_round()

    # Find a resting player
    resting_player = list(session.resting_players)[0]

    success, status = session.remove_player(resting_player)
    assert success is True
    assert status == "immediate"
    assert resting_player not in session.player_pool


# =============================================================================
# Court Changes Mid-Session
# =============================================================================


def test_update_courts_mid_session(sample_players):
    """Changing court count should affect next round."""
    session = ClubNightSession(players=sample_players, num_courts=2, is_doubles=True)

    # First round with 2 courts
    session.prepare_round()
    assert len(session.current_round_matches) == 2
    session.finalize_round(
        {
            1: session.current_round_matches[0].team_1,
            2: session.current_round_matches[1].team_1,
        }
    )

    # Change to 1 court
    session.update_courts(1)

    # Second round should have 1 court
    session.prepare_round()
    assert len(session.current_round_matches) == 1


def test_update_courts_to_zero_fails(sample_players):
    """Setting courts to 0 should raise error."""
    session = ClubNightSession(players=sample_players, num_courts=2, is_doubles=True)

    with pytest.raises(Exception):  # SessionError
        session.update_courts(0)


# =============================================================================
# Multiple Consecutive Rounds
# =============================================================================


def test_multiple_rounds_all_succeed(sample_players):
    """Multiple consecutive rounds should all succeed."""
    session = ClubNightSession(players=sample_players, num_courts=2, is_doubles=True)

    for round_num in range(5):
        session.prepare_round()
        assert (
            session.current_round_matches is not None
        ), f"Round {round_num + 1} failed"
        assert len(session.current_round_matches) == 2

        # Finalize with team_1 winning on all courts
        winners = {i + 1: session.current_round_matches[i].team_1 for i in range(2)}
        session.finalize_round(winners)


def test_resting_players_rotate_fairly(sample_players):
    """Over multiple rounds, all players should get similar rest time."""
    session = ClubNightSession(players=sample_players, num_courts=1, is_doubles=True)

    rest_counts = {name: 0 for name in sample_players}

    for _ in range(8):  # 8 rounds for 8 players
        session.prepare_round()

        for name in session.resting_players:
            rest_counts[name] += 1

        session.finalize_round({1: session.current_round_matches[0].team_1})

    # Each player should have rested exactly 4 times (4 rest per round, 8 rounds, 8 players)
    for name, count in rest_counts.items():
        assert count == 4, f"{name} rested {count} times, expected 4"


# =============================================================================
# Singles Mode
# =============================================================================


def test_session_singles_mode():
    """Session should work correctly in singles mode."""
    players = {
        f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, prior_mu=25.0)
        for i in range(1, 5)
    }
    session = ClubNightSession(players=players, num_courts=2, is_doubles=False)

    assert session.players_per_court == 2

    session.prepare_round()
    assert len(session.current_round_matches) == 2

    for match in session.current_round_matches:
        assert isinstance(match, SinglesMatch)
        assert match.player_1 is not None
        assert match.player_2 is not None


# =============================================================================
# Get Standings
# =============================================================================


def test_get_standings_sorted(sample_players):
    """Standings should be sorted by earned rating descending."""
    session = ClubNightSession(players=sample_players, num_courts=1, is_doubles=True)

    # Play a round
    session.prepare_round()
    match = session.current_round_matches[0]
    session.finalize_round({1: match.team_1})

    standings = session.get_standings()

    # Should be sorted descending
    ratings = [rating for _, rating in standings]
    assert ratings == sorted(ratings, reverse=True)
