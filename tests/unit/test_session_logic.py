import pytest
from session_logic import ClubNightSession, Player
from rating_service import compute_gender_statistics
from app_types import Gender, SinglesMatch, DoublesMatch


# =============================================================================
# Helper to set winners on a round record before finalizing
# =============================================================================


def _set_winners(session, winners_by_court):
    """Stores winners on the current round record (simulates auto-save)."""
    record = session.round_history[-1]
    for court_num, winner in winners_by_court.items():
        record.winners_by_court[court_num] = winner


# =============================================================================
# Session Initialization & Basic Flow
# =============================================================================


def test_session_initialization(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    assert len(session.player_pool) == 8
    assert session.num_courts == 2
    assert session.is_doubles is True
    assert session.round_num == 0
    assert session.current_round_matches is None
    assert session.resting_players == set()


def test_prepare_round(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,  # Only 1 court, 4 players will play, 4 will rest
        gender_stats=sample_gender_stats,
        is_doubles=True,
    )

    session.prepare_round()
    matches = session.current_round_matches

    assert len(matches) == 1
    assert len(session.resting_players) == 4
    assert session.round_num == 1
    assert len(session.round_history) == 1


def test_finalize_round(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]

    # Set winners via round record (simulates auto-save)
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    # Check that winners got points (default 1.0 for winning)
    for name in match.team_1:
        assert session.player_pool[name].earned_rating == 1.0
    for name in match.team_2:
        assert session.player_pool[name].earned_rating == 0.0


# =============================================================================
# Round History
# =============================================================================


def test_round_history_populated(sample_players, sample_gender_stats):
    """Round history should grow with each prepared round."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    for i in range(3):
        session.prepare_round()
        _set_winners(session, {m.court: m.team_1 for m in session.current_round_matches})
        session.finalize_round()

    assert len(session.round_history) == 3
    assert session.round_num == 3
    for i, record in enumerate(session.round_history):
        assert record.round_num == i + 1


def test_set_court_result_and_recompute(sample_players, sample_gender_stats):
    """Editing a past result and recomputing should update earned ratings."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    team_1, team_2 = match.team_1, match.team_2

    # Set team_1 as winner and finalize
    _set_winners(session, {1: team_1})
    session.finalize_round()

    # Verify initial ratings
    for name in team_1:
        assert session.player_pool[name].earned_rating == 1.0

    # Edit past result: change winner to team_2
    session.set_court_result(0, 1, team_2)
    session.recompute_earned_ratings()

    # team_2 should now have the win
    for name in team_2:
        assert session.player_pool[name].earned_rating == 1.0
    for name in team_1:
        # team_1 may have rest bonus if they were resting, otherwise 0
        if name in session.round_history[0].resting_players:
            assert session.player_pool[name].earned_rating == 0.5
        else:
            assert session.player_pool[name].earned_rating == 0.0


def test_advance_with_partial_results(sample_players, sample_gender_stats):
    """Advancing with partial results should succeed."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    session.prepare_round()
    assert len(session.current_round_matches) == 2

    # Only report one court
    match = session.current_round_matches[0]
    _set_winners(session, {match.court: match.team_1})

    # Finalize should succeed with partial results
    session.finalize_round()
    assert session.round_num == 1

    # Can prepare next round
    session.prepare_round()
    assert session.round_num == 2


def test_recompute_earned_ratings(sample_players, sample_gender_stats):
    """Recompute should produce the same totals as finalize-only awards."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    # Play 3 rounds
    for _ in range(3):
        session.prepare_round()
        match = session.current_round_matches[0]
        _set_winners(session, {1: match.team_1})
        session.finalize_round()

    # Snapshot earned ratings
    expected = {name: p.earned_rating for name, p in session.player_pool.items()}

    # Recompute and verify same result
    session.recompute_earned_ratings()
    for name, p in session.player_pool.items():
        assert p.earned_rating == expected[name], f"{name}: {p.earned_rating} != {expected[name]}"


def test_autosave_then_finalize_no_double_counting(sample_players, sample_gender_stats):
    """Auto-save (recompute) followed by finalize should not double-count ratings.

    This tests the actual app flow: the UI calls set_court_result + recompute
    on every winner selection, then advance_to_next_round calls finalize_round.
    """
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    team_1, team_2 = match.team_1, match.team_2

    # Simulate auto-save: set result then recompute (like save_court_result does)
    session.set_court_result(0, match.court, team_1)
    session.recompute_earned_ratings()

    # Snapshot after auto-save — these are the correct values
    expected = {name: p.earned_rating for name, p in session.player_pool.items()}

    # Now finalize (like advance_to_next_round does)
    session.finalize_round()

    # Ratings should be unchanged — no double-counting
    for name, p in session.player_pool.items():
        assert p.earned_rating == expected[name], (
            f"{name}: {p.earned_rating} after finalize != {expected[name]} after auto-save"
        )


# =============================================================================
# Mid-Session Player Management
# =============================================================================


def test_add_player_mid_session(sample_players, sample_gender_stats):
    """Adding player mid-session should give them retroactive rest points."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    # Play a round to accumulate some ratings
    session.prepare_round()
    match = session.current_round_matches[0]
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    # Add new player
    success = session.add_player(name="NewPlayer", gender=Gender.MALE)
    assert success is True
    assert "NewPlayer" in session.player_pool

    # New player should be in resting_players of round 1 (retroactive)
    assert "NewPlayer" in session.round_history[0].resting_players

    # New player should have 0.5 earned rating (rested round 1)
    new_player = session.player_pool["NewPlayer"]
    assert new_player.earned_rating == 0.5


def test_add_player_retroactive_resting_multiple_rounds(sample_players, sample_gender_stats):
    """Player joining after N rounds should get 0.5 * N catch-up."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    # Play 3 rounds
    for _ in range(3):
        session.prepare_round()
        match = session.current_round_matches[0]
        _set_winners(session, {1: match.team_1})
        session.finalize_round()

    # Add new player
    session.add_player(name="LateJoiner", gender=Gender.FEMALE)

    # Should be in resting_players for all 3 past rounds
    for record in session.round_history:
        assert "LateJoiner" in record.resting_players

    # Should have 3 * 0.5 = 1.5 earned rating
    assert session.player_pool["LateJoiner"].earned_rating == 1.5


def test_add_duplicate_player_fails(sample_players, sample_gender_stats):
    """Adding a player that already exists should fail."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    success = session.add_player(name="Alice", gender=Gender.FEMALE)
    assert success is False


def test_add_remove_player(sample_players, sample_gender_stats):
    session = ClubNightSession(players=sample_players, num_courts=2, gender_stats=sample_gender_stats)

    # Remove a player
    session.remove_player("Alice")
    assert "Alice" not in session.player_pool

    # Add a player back
    session.add_player(name="Zoe", gender=Gender.FEMALE)
    assert "Zoe" in session.player_pool


def test_remove_player_while_playing():
    """Removing a player mid-match should queue removal until round ends."""
    players = {
        "P1": Player(name="P1", gender=Gender.MALE, prior_mu=25.0),
        "P2": Player(name="P2", gender=Gender.MALE, prior_mu=25.0),
        "P3": Player(name="P3", gender=Gender.FEMALE, prior_mu=25.0),
        "P4": Player(name="P4", gender=Gender.FEMALE, prior_mu=25.0),
    }
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players, num_courts=1, gender_stats=gender_stats, is_doubles=True
    )

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
    _set_winners(session, {1: match.team_1})
    session.finalize_round()
    assert playing_player not in session.player_pool


def test_remove_resting_player():
    """Removing a resting player should happen immediately."""
    players = {
        f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, prior_mu=25.0)
        for i in range(1, 6)
    }
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players, num_courts=1, gender_stats=gender_stats, is_doubles=True
    )

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


def test_update_courts_mid_session(sample_players, sample_gender_stats):
    """Changing court count should affect next round."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    # First round with 2 courts
    session.prepare_round()
    assert len(session.current_round_matches) == 2
    _set_winners(session, {
        1: session.current_round_matches[0].team_1,
        2: session.current_round_matches[1].team_1,
    })
    session.finalize_round()

    # Change to 1 court
    session.update_courts(1)

    # Second round should have 1 court
    session.prepare_round()
    assert len(session.current_round_matches) == 1


def test_update_courts_to_zero_fails(sample_players, sample_gender_stats):
    """Setting courts to 0 should raise error."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    with pytest.raises(Exception):  # SessionError
        session.update_courts(0)


# =============================================================================
# Multiple Consecutive Rounds
# =============================================================================


def test_multiple_rounds_all_succeed(sample_players, sample_gender_stats):
    """Multiple consecutive rounds should all succeed."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

    for round_num in range(5):
        session.prepare_round()
        assert (
            session.current_round_matches is not None
        ), f"Round {round_num + 1} failed"
        assert len(session.current_round_matches) == 2

        # Finalize with team_1 winning on all courts
        winners = {i + 1: session.current_round_matches[i].team_1 for i in range(2)}
        _set_winners(session, winners)
        session.finalize_round()

    assert len(session.round_history) == 5


def test_resting_players_rotate_fairly(sample_players, sample_gender_stats):
    """Over multiple rounds, all players should get similar rest time."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    rest_counts = {name: 0 for name in sample_players}

    for _ in range(8):  # 8 rounds for 8 players
        session.prepare_round()

        for name in session.resting_players:
            rest_counts[name] += 1

        _set_winners(session, {1: session.current_round_matches[0].team_1})
        session.finalize_round()

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
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players, num_courts=2, gender_stats=gender_stats, is_doubles=False
    )

    assert session.players_per_court == 2

    session.prepare_round()
    assert len(session.current_round_matches) == 2

    for match in session.current_round_matches:
        assert isinstance(match, SinglesMatch)
        assert match.player_1 is not None
        assert match.player_2 is not None


# =============================================================================
# Session Performance & Standings
# =============================================================================


def test_session_performance_boosts_matchmaking():
    """Winners should be grouped together in subsequent rounds due to mu boost."""
    players = {
        f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, prior_mu=25.0)
        for i in range(1, 9)
    }
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players,
        num_courts=2,
        gender_stats=gender_stats,
        is_doubles=True,
        weights={"skill": 1.0, "power": 1.0, "pairing": 0.0},
    )

    # Round 1: all identical, matchmaking is arbitrary
    session.prepare_round()
    matches = session.current_round_matches
    assert len(matches) == 2

    # team_1 wins on both courts
    winners = set(matches[0].team_1 + matches[1].team_1)
    _set_winners(session, {
        matches[0].court: matches[0].team_1,
        matches[1].court: matches[1].team_1,
    })
    session.finalize_round()

    # Round 2: winners (boosted mu) should land on the same court
    session.prepare_round()
    matches = session.current_round_matches
    assert len(matches) == 2

    court1_players = set(matches[0].team_1 + matches[0].team_2)
    court2_players = set(matches[1].team_1 + matches[1].team_2)
    assert court1_players == winners or court2_players == winners


def test_get_standings_sorted(sample_players, sample_gender_stats):
    """Standings should be sorted by earned rating descending."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    # Play a round
    session.prepare_round()
    match = session.current_round_matches[0]
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    standings = session.get_standings()

    # Should be sorted descending
    ratings = [rating for _, rating in standings]
    assert ratings == sorted(ratings, reverse=True)


# =============================================================================
# Edge Cases
# =============================================================================


def test_set_court_result_invalid_index(sample_players, sample_gender_stats):
    """set_court_result with out-of-range index should raise SessionError."""
    from exceptions import SessionError

    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )
    session.prepare_round()

    with pytest.raises(SessionError):
        session.set_court_result(5, 1, ("Alice",))

    with pytest.raises(SessionError):
        session.set_court_result(-1, 1, ("Alice",))


def test_set_court_result_clear(sample_players, sample_gender_stats):
    """Setting winner to None should remove the court result."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )
    session.prepare_round()
    match = session.current_round_matches[0]

    # Set a winner
    session.set_court_result(0, match.court, match.team_1)
    assert match.court in session.round_history[0].winners_by_court

    # Clear it
    session.set_court_result(0, match.court, None)
    assert match.court not in session.round_history[0].winners_by_court


def test_finalize_round_no_history(sample_players, sample_gender_stats):
    """finalize_round with no rounds prepared should raise SessionError."""
    from exceptions import SessionError

    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    with pytest.raises(SessionError):
        session.finalize_round()


def test_add_player_before_any_rounds(sample_players, sample_gender_stats):
    """Adding a player before any rounds are prepared should work without error."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    # No prepare_round called — round_history is empty
    success = session.add_player(name="EarlyJoiner", gender=Gender.MALE)
    assert success is True
    assert "EarlyJoiner" in session.player_pool
    assert session.player_pool["EarlyJoiner"].earned_rating == 0.0


def test_readd_removed_player_skips_played_rounds():
    """Re-adding a removed player should not mark them as resting in rounds they played."""
    players = {
        "P1": Player(name="P1", gender=Gender.MALE, prior_mu=25.0),
        "P2": Player(name="P2", gender=Gender.MALE, prior_mu=25.0),
        "P3": Player(name="P3", gender=Gender.FEMALE, prior_mu=25.0),
        "P4": Player(name="P4", gender=Gender.FEMALE, prior_mu=25.0),
        "P5": Player(name="P5", gender=Gender.MALE, prior_mu=25.0),
    }
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players, num_courts=1, gender_stats=gender_stats, is_doubles=True
    )

    # Round 1: 4 play, 1 rests
    session.prepare_round()
    match = session.current_round_matches[0]
    playing_round_1 = set(match.team_1 + match.team_2)
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    # Pick a player who played in round 1
    played_player = list(playing_round_1)[0]

    # Remove and re-add
    session.remove_player(played_player)
    session.add_player(name=played_player, gender=Gender.MALE, mu=25.0)

    # Players who played should NOT be retroactively marked as resting
    assert played_player not in session.round_history[0].resting_players


def test_recompute_excludes_removed_players(sample_players, sample_gender_stats):
    """Recompute should not award points to players no longer in the pool."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    winner_name = match.team_1[0]

    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    assert session.player_pool[winner_name].earned_rating == 1.0

    # After finalize, round is no longer active — removal is immediate
    success, status = session.remove_player(winner_name)
    assert success is True
    assert status == "immediate"
    assert winner_name not in session.player_pool

    # Recompute should not crash or award points to the removed player
    session.recompute_earned_ratings()

    for p in session.player_pool.values():
        assert p.earned_rating >= 0.0
