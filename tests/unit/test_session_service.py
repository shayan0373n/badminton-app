import pytest

import session_service
from constants import DEFAULT_WEIGHTS
from exceptions import DatabaseError, SessionError
from session_logic import ClubNightSession, Player
from tests.utils import make_session
from app_types import Gender


def _make_session(sample_players, sample_gender_stats) -> ClubNightSession:
    """Builds a doubles session from the shared sample fixtures."""
    return make_session(dict(sample_players), num_courts=1, gender_stats=sample_gender_stats)


@pytest.fixture
def saves(monkeypatch) -> list[str]:
    """Records the name of every session the service layer saves."""
    saved: list[str] = []
    monkeypatch.setattr(
        session_service.SessionManager, "save", lambda session, name: saved.append(name)
    )
    return saved


@pytest.fixture
def registry(monkeypatch, sample_players) -> dict[str, Player]:
    """Stubs the member registry with the sample players; returns what was upserted."""
    upserted: dict[str, Player] = {}
    monkeypatch.setattr(session_service.PlayerDB, "get_all_players", lambda: dict(sample_players))
    monkeypatch.setattr(
        session_service.PlayerDB, "upsert_players", lambda players: upserted.update(players)
    )
    return upserted


def test_add_guest_player_persists_entered_skill_as_prior(
    saves, registry, sample_players, sample_gender_stats
):
    """A guest's entered skill must become prior_mu in the pool and in the persisted record."""
    session = _make_session(sample_players, sample_gender_stats)
    success, error = session_service.add_guest_player(
        session, "test_session", name="Guest", gender=Gender.MALE, mu=32.0
    )

    assert success is True
    assert error is None
    assert saves == ["test_session"]

    pool_player = session.player_pool["Guest"]
    assert pool_player.prior_mu == 32.0
    assert pool_player.mu == 32.0

    # The record written to the registry must carry the prior, since rating
    # recalculation reads prior_mu, not mu.
    assert registry["Guest"].prior_mu == 32.0


def test_guest_cannot_take_a_members_name(saves, registry, sample_players, sample_gender_stats):
    """A guest named like a registry member is refused, so the member's row is never overwritten."""
    session = _make_session({}, sample_gender_stats)

    success, error = session_service.add_guest_player(
        session, "test_session", name="Alice", gender=Gender.FEMALE, mu=10.0
    )

    assert success is False
    assert "member" in error
    assert registry == {}
    assert saves == []
    assert "Alice" not in session.candidates


def test_guest_cannot_take_a_candidates_name(saves, registry, sample_players, sample_gender_stats):
    session = _make_session(sample_players, sample_gender_stats)

    success, error = session_service.add_guest_player(
        session, "test_session", name="Alice", gender=Gender.FEMALE, mu=10.0
    )

    assert success is False
    assert "tonight's list" in error
    assert registry == {}
    assert saves == []


def test_failed_guest_sync_leaves_no_trace(
    monkeypatch, saves, sample_players, sample_gender_stats
):
    """A guest the registry rejects is neither checked in, left on tonight's list, nor saved."""

    def reject(players_dict):
        raise DatabaseError("down")

    monkeypatch.setattr(session_service.PlayerDB, "get_all_players", lambda: {})
    monkeypatch.setattr(session_service.PlayerDB, "upsert_players", reject)

    session = _make_session(sample_players, sample_gender_stats)
    success, error = session_service.add_guest_player(
        session, "test_session", name="Guest", gender=Gender.MALE, mu=32.0
    )

    assert success is False
    assert error is not None
    assert "Guest" not in session.player_pool
    assert "Guest" not in session.candidates
    assert saves == []


def test_add_candidate_then_check_in_preserves_prior_and_posterior(
    saves, sample_players, sample_gender_stats
):
    """Adding a registry member and checking them in keeps prior_mu and learned mu/sigma."""
    session = _make_session(sample_players, sample_gender_stats)
    member = Player(
        name="Returning",
        gender=Gender.MALE,
        prior_mu=28.0,
        prior_sigma=6.0,
        mu=31.5,
        sigma=3.0,
    )

    assert session_service.add_candidate(session, "test_session", member) is True
    assert "Returning" not in session.player_pool
    assert session_service.check_in_player(session, "test_session", "Returning") is True
    assert saves == ["test_session", "test_session"]

    pool_player = session.player_pool["Returning"]
    assert pool_player is member
    assert pool_player.prior_mu == 28.0
    assert pool_player.prior_sigma == 6.0
    assert pool_player.mu == 31.5
    assert pool_player.sigma == 3.0


def test_duplicate_candidate_is_not_saved(saves, sample_players, sample_gender_stats):
    session = _make_session(sample_players, sample_gender_stats)

    assert session_service.add_candidate(session, "s", sample_players["Alice"]) is False
    assert saves == []


def test_remove_candidate_checks_out_and_saves(saves, sample_players, sample_gender_stats):
    session = _make_session(sample_players, sample_gender_stats)

    assert session_service.remove_candidate(session, "s", "Alice") is True
    assert "Alice" not in session.player_pool
    assert "Alice" not in session.candidates
    assert saves == ["s"]

    assert session_service.remove_candidate(session, "s", "Alice") is False
    assert saves == ["s"]


def test_update_settings_saves_once(saves, sample_players, sample_gender_stats):
    session = _make_session(sample_players, sample_gender_stats)

    session_service.update_settings(session, "s", num_courts=3, weights={"skill": 2.5})

    assert session.num_courts == 3
    assert session.weights == {**DEFAULT_WEIGHTS, "skill": 2.5}
    assert saves == ["s"]


def test_update_settings_rejects_unknown_weight_without_saving(
    saves, sample_players, sample_gender_stats
):
    session = _make_session(sample_players, sample_gender_stats)

    with pytest.raises(SessionError):
        session_service.update_settings(session, "s", weights={"skil": 9.0})

    assert session.weights == dict(DEFAULT_WEIGHTS)
    assert saves == []
