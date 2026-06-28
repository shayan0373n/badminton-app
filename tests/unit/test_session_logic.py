import pytest
import session_logic
import session_service
import optimizer_ortools
from constants import DEFAULT_WEIGHTS
from session_logic import ClubNightSession, Player, SessionManager
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
        players=sample_players,
        num_courts=2,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    assert len(session.player_pool) == 8
    assert session.num_courts == 2
    assert session.is_doubles is True
    assert session.round_num == 0
    assert session.current_round_matches is None
    assert session.resting_players == set()


def test_add_remove_player(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players,
        num_courts=2,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
    )

    # Remove a player
    session.remove_player("Alice")
    assert "Alice" not in session.player_pool

    # Add a player back
    session.add_player(name="Zoe", gender=Gender.FEMALE)
    assert "Zoe" in session.player_pool


def test_prepare_round(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,  # Only 1 court, 4 players will play, 4 will rest
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    matches = session.current_round_matches

    assert len(matches) == 1
    assert len(session.resting_players) == 4
    assert session.round_num == 1
    assert len(session.round_history) == 1


def test_session_pairing_weight_changes_matchmaking(monkeypatch):
    players = {
        "P1": Player(name="P1", gender=Gender.MALE, prior_mu=3.0),
        "P2": Player(name="P2", gender=Gender.MALE, prior_mu=2.9),
        "P3": Player(name="P3", gender=Gender.MALE, prior_mu=2.5),
        "P4": Player(name="P4", gender=Gender.MALE, prior_mu=0.0),
    }
    gender_stats = compute_gender_statistics(players)

    monkeypatch.setattr(session_logic, "generate_one_round", optimizer_ortools.generate_one_round)
    monkeypatch.setattr(session_logic.random, "shuffle", lambda items: None)
    monkeypatch.setattr(optimizer_ortools.random, "shuffle", lambda items: None)

    low_pairing_session = ClubNightSession(
        players=players,
        num_courts=1,
        gender_stats=gender_stats,
        is_doubles=True,
        weights={"skill": 1.0, "power": 1.0, "pairing": 0.0},
    )
    high_pairing_session = ClubNightSession(
        players={
            name: Player(name=p.name, gender=p.gender, prior_mu=p.prior_mu)
            for name, p in players.items()
        },
        num_courts=1,
        gender_stats=gender_stats,
        is_doubles=True,
        weights={"skill": 1.0, "power": 1.0, "pairing": 10.0},
    )

    low_pairing_session.prepare_round()
    high_pairing_session.prepare_round()

    low_round1 = low_pairing_session.current_round_matches[0]
    high_round1 = high_pairing_session.current_round_matches[0]

    low_p1_team_round1 = low_round1.team_1 if "P1" in low_round1.team_1 else low_round1.team_2
    high_p1_team_round1 = high_round1.team_1 if "P1" in high_round1.team_1 else high_round1.team_2

    assert "P4" in low_p1_team_round1
    assert "P4" in high_p1_team_round1

    low_pairing_session.finalize_round()
    high_pairing_session.finalize_round()

    low_pairing_session.prepare_round()
    high_pairing_session.prepare_round()

    low_round2 = low_pairing_session.current_round_matches[0]
    high_round2 = high_pairing_session.current_round_matches[0]

    low_p1_team_round2 = low_round2.team_1 if "P1" in low_round2.team_1 else low_round2.team_2
    high_p1_team_round2 = high_round2.team_1 if "P1" in high_round2.team_1 else high_round2.team_2

    assert "P4" in low_p1_team_round2
    assert "P4" not in high_p1_team_round2


def test_finalize_round(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]

    # Set winners via round record (simulates auto-save)
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    # Winners have 1 win / 1 match; losers have 0 wins / 1 match.
    for name in match.team_1:
        assert session.wins(name) == 1
        assert session.matches_played(name) == 1
    for name in match.team_2:
        assert session.wins(name) == 0
        assert session.matches_played(name) == 1


def test_set_court_result_marks_results_dirty(sample_players, sample_gender_stats):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]

    assert session.results_dirty is False

    session.set_court_result(0, match.court, match.team_1)

    assert session.results_dirty is True


def test_clearing_court_result_marks_results_dirty(
    sample_players, sample_gender_stats
):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    session.set_court_result(0, match.court, match.team_1)
    session.results_dirty = False

    session.set_court_result(0, match.court, None)

    assert session.results_dirty is True


def test_submit_session_results_clears_results_dirty(
    monkeypatch, sample_players, sample_gender_stats
):
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
        database_id=123,
        is_recorded=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    session.set_court_result(0, match.court, match.team_1)

    monkeypatch.setattr(session_service.MatchDB, "delete_by_session", lambda _: None)
    monkeypatch.setattr(session_service.MatchDB, "add_match", lambda **kwargs: None)
    monkeypatch.setattr(SessionManager, "save", lambda *_: None)

    recorded, unreported = session_service.submit_session_results(session, "Test")

    assert session.results_dirty is False
    assert recorded == 1
    assert unreported == 0


# =============================================================================
# Round History
# =============================================================================


def test_round_history_populated(sample_players, sample_gender_stats):
    """Round history should grow with each prepared round."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )

    for i in range(3):
        session.prepare_round()
        _set_winners(session, {m.court: m.team_1 for m in session.current_round_matches})
        session.finalize_round()

    assert len(session.round_history) == 3
    assert session.round_num == 3
    for i, record in enumerate(session.round_history):
        assert record.round_num == i + 1


def test_set_court_result_updates_standings(sample_players, sample_gender_stats):
    """Editing a past result should be reflected immediately in derived standings."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    team_1, team_2 = match.team_1, match.team_2

    _set_winners(session, {1: team_1})
    session.finalize_round()

    for name in team_1:
        assert session.wins(name) == 1
    for name in team_2:
        assert session.wins(name) == 0

    # Edit past result: change winner to team_2. No recompute call needed --
    # standings derive from round_history on read.
    session.set_court_result(0, 1, team_2)

    for name in team_2:
        assert session.wins(name) == 1
    for name in team_1:
        assert session.wins(name) == 0


def test_advance_with_partial_results(sample_players, sample_gender_stats):
    """Advancing with partial results should succeed."""
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
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


# =============================================================================
# Mid-Session Player Management
# =============================================================================


def test_add_player_mid_session(sample_players, sample_gender_stats):
    """Adding a player mid-session should put them in the pool with 0 stats and not touch past rounds."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    success = session.add_player(name="NewPlayer", gender=Gender.MALE)
    assert success is True
    assert "NewPlayer" in session.player_pool

    # Past round must not be mutated by the join (the bug this guards against).
    assert "NewPlayer" not in session.round_history[0].resting_players

    # New player has no match history yet.
    assert session.wins("NewPlayer") == 0
    assert session.matches_played("NewPlayer") == 0


def test_add_player_skill_lands_in_prior_mu(sample_players, sample_gender_stats):
    """A mid-session player's entered skill must populate prior_mu, the input to rating recalc."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    success = session.add_player(name="NewPlayer", gender=Gender.MALE, prior_mu=32.0)
    assert success is True

    player = session.player_pool["NewPlayer"]
    assert player.prior_mu == 32.0
    # With no match history, the posterior starts equal to the prior.
    assert player.mu == 32.0


def test_add_player_keeps_distinct_prior_and_posterior(sample_players, sample_gender_stats):
    """Re-adding a player with a learned posterior keeps mu/sigma distinct from the prior."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    success = session.add_player(
        name="Returning",
        gender=Gender.MALE,
        prior_mu=28.0,
        prior_sigma=6.0,
        mu=31.5,
        sigma=3.0,
    )
    assert success is True

    player = session.player_pool["Returning"]
    assert player.prior_mu == 28.0
    assert player.prior_sigma == 6.0
    assert player.mu == 31.5
    assert player.sigma == 3.0


def _max_consecutive_rests(round_history, player_name):
    """Returns the longest run of consecutive rounds in which player_name is marked resting."""
    longest = current = 0
    for record in round_history:
        if player_name in record.resting_players:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _build_players(n):
    """Builds n players with alternating gender and uniform priors."""
    return {
        f"P{i}": Player(
            name=f"P{i}",
            gender=Gender.MALE if i % 2 else Gender.FEMALE,
            prior_mu=25.0,
        )
        for i in range(1, n + 1)
    }


def _play_round(session):
    """Prepares one round and records team_1 as the winner on every court."""
    session.prepare_round()
    winners = {m.court: m.team_1 for m in session.current_round_matches}
    _set_winners(session, winners)
    session.finalize_round()


def test_rest_rotation_fair_when_player_joins_mid_session():
    """No player should ever appear as resting in consecutive rounds when joining mid-session.

    Setup: 13 players x 3 courts (1 rest/round) for 3 rounds, then a 14th player
    joins (14 players x 3 courts -> 2 rest/round) for 5 more rounds.

    Invariant under test: at every point in this session, rest_count_per_round <
    play_count_per_round, so the rotation queue can always pick resters from
    players who didn't rest last round. Therefore the rest history must show
    each player resting in at most 1 consecutive round. Any apparent streak >= 2
    in any player's history is a bug in the rest bookkeeping, not a real
    rotation outcome.
    """
    players = _build_players(13)
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players,
        num_courts=3,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    for _ in range(3):
        _play_round(session)

    session.add_player(name="LateJoiner", gender=Gender.MALE)

    for _ in range(5):
        _play_round(session)

    for name in session.player_pool:
        streak = _max_consecutive_rests(session.round_history, name)
        assert streak <= 1, (
            f"{name} is marked resting in {streak} consecutive rounds across the "
            f"session, but rotation never assigns consecutive rests when "
            f"rest_count < play_count."
        )


def test_rest_rotation_fair_when_player_leaves_and_rejoins():
    """No player should appear as resting in consecutive rounds across a leave-and-rejoin cycle.

    Setup: 13 players x 3 courts (1 rest/round). The round 1 rester leaves; play 2
    rounds with 12 players (0 rest); the same player rejoins; play 5 more rounds.

    Invariant under test: rest_count < play_count holds in every round, so the
    rotation can always avoid consecutive rests. A player who was absent for
    rounds 2-3 didn't rest then -- they were gone -- and after rejoining they
    sit at the back of the queue, so the next rotation-driven rest is many
    rounds away. The displayed rest history must therefore show <= 1 consecutive
    rest for every player.
    """
    players = _build_players(13)
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players,
        num_courts=3,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    leaver = next(iter(session.resting_players))
    winners = {m.court: m.team_1 for m in session.current_round_matches}
    _set_winners(session, winners)
    session.finalize_round()

    session.remove_player(leaver)
    assert leaver not in session.player_pool

    for _ in range(2):
        _play_round(session)

    session.add_player(name=leaver, gender=Gender.MALE)

    for _ in range(5):
        _play_round(session)

    for name in session.player_pool:
        streak = _max_consecutive_rests(session.round_history, name)
        assert streak <= 1, (
            f"{name} is marked resting in {streak} consecutive rounds across the "
            f"session, but rotation never assigns consecutive rests with these "
            f"pool sizes."
        )


def test_add_duplicate_player_fails(sample_players, sample_gender_stats):
    """Adding a player that already exists should fail."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

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
    gender_stats = compute_gender_statistics(players)
    session = ClubNightSession(
        players=players,
        num_courts=1,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
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
        players=players,
        num_courts=1,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
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
        players=sample_players,
        num_courts=2,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
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
        players=sample_players,
        num_courts=2,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    with pytest.raises(Exception):  # SessionError
        session.update_courts(0)


# =============================================================================
# Multiple Consecutive Rounds
# =============================================================================


def test_multiple_rounds_all_succeed(sample_players, sample_gender_stats):
    """Multiple consecutive rounds should all succeed."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=2,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
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
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
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
        players=players,
        num_courts=2,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=False,
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
    """Standings should be sorted by ratio desc, then wins desc as tiebreaker."""
    session = ClubNightSession(
        players=sample_players,
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    standings = session.get_standings()

    # Rows are (name, matches, wins, ratio). Sort key is (ratio, wins) descending.
    sort_keys = [(ratio, wins) for _, _, wins, ratio in standings]
    assert sort_keys == sorted(sort_keys, reverse=True)


# =============================================================================
# Edge Cases
# =============================================================================


def test_set_court_result_invalid_index(sample_players, sample_gender_stats):
    """set_court_result with out-of-range index should raise SessionError."""
    from exceptions import SessionError

    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )
    session.prepare_round()

    with pytest.raises(SessionError):
        session.set_court_result(5, 1, ("Alice",))

    with pytest.raises(SessionError):
        session.set_court_result(-1, 1, ("Alice",))


def test_set_court_result_clear(sample_players, sample_gender_stats):
    """Setting winner to None should remove the court result."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
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
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )

    with pytest.raises(SessionError):
        session.finalize_round()


def test_add_player_before_any_rounds(sample_players, sample_gender_stats):
    """Adding a player before any rounds are prepared should work without error."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )

    # No prepare_round called — round_history is empty
    success = session.add_player(name="EarlyJoiner", gender=Gender.MALE)
    assert success is True
    assert "EarlyJoiner" in session.player_pool
    assert session.wins("EarlyJoiner") == 0
    assert session.matches_played("EarlyJoiner") == 0


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
        players=players, num_courts=1, gender_stats=gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
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


def test_standings_exclude_removed_players(sample_players, sample_gender_stats):
    """Derived standings should not include players who were removed from the pool."""
    session = ClubNightSession(
        players=sample_players, num_courts=1, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )

    session.prepare_round()
    match = session.current_round_matches[0]
    winner_name = match.team_1[0]

    _set_winners(session, {1: match.team_1})
    session.finalize_round()

    assert session.wins(winner_name) == 1

    # After finalize, round is no longer active — removal is immediate
    success, status = session.remove_player(winner_name)
    assert success is True
    assert status == "immediate"
    assert winner_name not in session.player_pool

    # Standings (derived from round_history) should silently exclude the removed player.
    standings_names = [row[0] for row in session.get_standings()]
    assert winner_name not in standings_names
