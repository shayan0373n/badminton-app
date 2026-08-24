"""Tests for challenge mode: the tier-only rating boost and its session state."""

import pickle

import pytest

from app_types import Gender
from constants import CHALLENGE_TIER_BOOST_MU, DEFAULT_WEIGHTS
from rating_service import (
    compute_gender_statistics,
    compute_real_skill,
    compute_tier_rating,
    prepare_optimizer_ratings,
)
from session_logic import ClubNightSession, Player


# =============================================================================
# The boost itself
# =============================================================================


def test_no_challengers_leaves_ratings_unchanged(sample_players, sample_gender_stats):
    """Passing no challengers must reproduce the pre-feature behaviour exactly."""
    baseline = prepare_optimizer_ratings(sample_players, sample_gender_stats)

    assert prepare_optimizer_ratings(sample_players, sample_gender_stats, None) == baseline
    assert prepare_optimizer_ratings(sample_players, sample_gender_stats, set()) == baseline


def test_challenge_raises_tier_but_not_real_skill(sample_players, sample_gender_stats):
    """The whole point: court grouping moves, team balancing does not."""
    base_tier, base_skill = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    tier, skill = prepare_optimizer_ratings(
        sample_players, sample_gender_stats, {"Bob"}
    )

    assert tier["Bob"] > base_tier["Bob"]
    assert skill["Bob"] == base_skill["Bob"]


def test_boost_equals_one_club_level(sample_players, sample_gender_stats):
    """The tier gain must match adding CHALLENGE_TIER_BOOST_MU to mu."""
    _, _ = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    tier, _ = prepare_optimizer_ratings(sample_players, sample_gender_stats, {"Bob"})

    bob = sample_players["Bob"]
    expected = compute_tier_rating(
        bob.mu + CHALLENGE_TIER_BOOST_MU, bob.gender, sample_gender_stats
    )
    assert tier["Bob"] == pytest.approx(expected)


def test_boost_applies_to_female_players_too(sample_players, sample_gender_stats):
    """The gender shift and the challenge boost must compose, not conflict."""
    base_tier, _ = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    tier, _ = prepare_optimizer_ratings(
        sample_players, sample_gender_stats, {"Alice"}
    )

    alice = sample_players["Alice"]
    expected = compute_tier_rating(
        alice.mu + CHALLENGE_TIER_BOOST_MU, alice.gender, sample_gender_stats
    )
    assert tier["Alice"] == pytest.approx(expected)
    assert tier["Alice"] > base_tier["Alice"]


def test_only_named_challengers_are_boosted(sample_players, sample_gender_stats):
    base_tier, _ = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    tier, _ = prepare_optimizer_ratings(
        sample_players, sample_gender_stats, {"Bob", "Eve"}
    )

    for name in sample_players:
        if name in {"Bob", "Eve"}:
            assert tier[name] > base_tier[name]
        else:
            assert tier[name] == base_tier[name]


def test_unknown_challenger_name_is_ignored(sample_players, sample_gender_stats):
    """A stale name must not raise or disturb anyone else's rating."""
    baseline = prepare_optimizer_ratings(sample_players, sample_gender_stats)
    assert (
        prepare_optimizer_ratings(sample_players, sample_gender_stats, {"Nobody"})
        == baseline
    )


def test_boost_lifts_a_challenger_above_a_stronger_peer(sample_gender_stats):
    """A one-level boost must be enough to reorder adjacent players."""
    players = {
        "Weak": Player(name="Weak", gender=Gender.MALE, prior_mu=20.0),
        "Strong": Player(name="Strong", gender=Gender.MALE, prior_mu=24.0),
    }
    stats = compute_gender_statistics(players)

    tier, _ = prepare_optimizer_ratings(players, stats, {"Weak"})

    # 7 mu of boost must clear the 4 mu gap between them
    assert tier["Weak"] > tier["Strong"]


# =============================================================================
# Session state
# =============================================================================


def _session(players, gender_stats) -> ClubNightSession:
    return ClubNightSession(
        players=players,
        num_courts=2,
        gender_stats=gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )


def test_new_session_has_no_challengers(sample_players, sample_gender_stats):
    assert _session(sample_players, sample_gender_stats).challengers == set()


def test_set_and_clear_challenge(sample_players, sample_gender_stats):
    session = _session(sample_players, sample_gender_stats)

    assert session.set_challenge("Bob", True) is True
    assert session.challengers == {"Bob"}

    assert session.set_challenge("Bob", False) is True
    assert session.challengers == set()


def test_set_challenge_rejects_unknown_player(sample_players, sample_gender_stats):
    session = _session(sample_players, sample_gender_stats)

    assert session.set_challenge("Nobody", True) is False
    assert session.challengers == set()


def test_toggle_challenge_flips_and_reports_state(sample_players, sample_gender_stats):
    session = _session(sample_players, sample_gender_stats)

    assert session.toggle_challenge("Bob") is True
    assert session.challengers == {"Bob"}
    assert session.toggle_challenge("Bob") is False
    assert session.challengers == set()


def test_challenge_survives_rounds(sample_players, sample_gender_stats):
    """The flag is not consumed by being honoured -- it persists until cleared."""
    session = _session(sample_players, sample_gender_stats)
    session.set_challenge("Bob", True)

    session.prepare_round()
    session.finalize_round()
    session.prepare_round()

    assert session.challengers == {"Bob"}


def test_removing_a_player_clears_their_challenge(sample_players, sample_gender_stats):
    session = _session(sample_players, sample_gender_stats)
    session.set_challenge("Bob", True)

    session.remove_player("Bob")

    assert "Bob" not in session.challengers


def test_old_pickles_load_without_challengers(sample_players, sample_gender_stats):
    """Sessions saved before this feature must still unpickle."""
    session = _session(sample_players, sample_gender_stats)
    state = session.__dict__.copy()
    del state["challengers"]

    restored = ClubNightSession.__new__(ClubNightSession)
    restored.__setstate__(state)

    assert restored.challengers == set()


def test_round_trip_pickle_preserves_challengers(sample_players, sample_gender_stats):
    session = _session(sample_players, sample_gender_stats)
    session.set_challenge("Bob", True)

    restored = pickle.loads(pickle.dumps(session))

    assert restored.challengers == {"Bob"}


# =============================================================================
# End-to-end effect on court assignment
# =============================================================================


def _ladder_session() -> ClubNightSession:
    """Eight men on an even skill ladder, two courts.

    A continuous spread is what makes the boost bite: with two clumps of equal
    players, lifting one costs more spread than it saves, which is the documented
    limit of a soft nudge.
    """
    mus = [32.0, 30.0, 28.0, 26.0, 24.0, 22.0, 20.0, 18.0]
    players = {
        f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, prior_mu=mu)
        for i, mu in enumerate(mus, 1)
    }
    return ClubNightSession(
        players=players,
        num_courts=2,
        gender_stats=compute_gender_statistics(players),
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )


def _courtmate_strength(session: ClubNightSession, name: str) -> float:
    """Mean real skill of everyone sharing a court with `name`, excluding them."""
    match = next(
        m
        for m in session.round_history[-1].matches
        if name in set(m.team_1) | set(m.team_2)
    )
    others = (set(match.team_1) | set(match.team_2)) - {name}
    return sum(compute_real_skill(session.player_pool[n].mu) for n in others) / len(others)


def test_challenger_lands_among_stronger_players():
    """A mid-ladder player who challenges should get tougher court-mates."""
    baseline = _ladder_session()
    baseline.prepare_round()
    before = _courtmate_strength(baseline, "P5")

    challenged = _ladder_session()
    challenged.set_challenge("P5", True)
    challenged.prepare_round()
    after = _courtmate_strength(challenged, "P5")

    assert after > before


def test_challenger_gets_a_stronger_partner_not_a_weaker_one():
    """Real skill is untouched, so the optimizer compensates with a good partner.

    This is what boosting mu directly would have got wrong: it would inflate the
    challenger's apparent strength and hand them a weaker partner to balance.
    """
    session = _ladder_session()
    session.set_challenge("P5", True)
    session.prepare_round()

    match = next(
        m
        for m in session.round_history[-1].matches
        if "P5" in set(m.team_1) | set(m.team_2)
    )
    team = match.team_1 if "P5" in match.team_1 else match.team_2
    partner = next(p for p in team if p != "P5")
    opponents = match.team_2 if "P5" in match.team_1 else match.team_1

    # The partner must carry at least as much as the average opponent for the
    # match to be fair, given P5 is the weak link on an elevated court.
    opponent_avg = sum(session.player_pool[o].mu for o in opponents) / 2
    assert session.player_pool[partner].mu >= opponent_avg
