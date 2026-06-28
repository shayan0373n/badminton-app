import session_service
from constants import DEFAULT_WEIGHTS
from session_logic import ClubNightSession, Player
from app_types import Gender


def _make_session(sample_players, sample_gender_stats) -> ClubNightSession:
    """Builds a doubles session from the shared sample fixtures."""
    return ClubNightSession(
        players=dict(sample_players),
        num_courts=1,
        gender_stats=sample_gender_stats,
        weights=DEFAULT_WEIGHTS,
        is_doubles=True,
    )


def test_add_guest_player_persists_entered_skill_as_prior(
    monkeypatch, sample_players, sample_gender_stats
):
    """A guest's entered skill must become prior_mu in the pool and in the persisted record."""
    persisted = {}
    monkeypatch.setattr(
        session_service.PlayerDB,
        "upsert_players",
        lambda players_dict: persisted.update(players_dict),
    )

    session = _make_session(sample_players, sample_gender_stats)
    success, error = session_service.add_guest_player(
        session, name="Guest", gender=Gender.MALE, mu=32.0
    )

    assert success is True
    assert error is None

    pool_player = session.player_pool["Guest"]
    assert pool_player.prior_mu == 32.0
    assert pool_player.mu == 32.0

    # The record written to the registry must carry the prior, since rating
    # recalculation reads prior_mu, not mu.
    assert persisted["Guest"].prior_mu == 32.0


def test_add_player_from_registry_preserves_prior_and_posterior(
    monkeypatch, sample_players, sample_gender_stats
):
    """Re-adding a registry member keeps both their prior_mu and learned mu/sigma."""
    monkeypatch.setattr(
        session_service.SessionManager, "save", lambda *args, **kwargs: None
    )

    session = _make_session(sample_players, sample_gender_stats)
    member = Player(
        name="Returning",
        gender=Gender.MALE,
        prior_mu=28.0,
        prior_sigma=6.0,
        mu=31.5,
        sigma=3.0,
    )

    added = session_service.add_player_from_registry(
        session, session_name="test_session", player=member
    )

    assert added is True

    pool_player = session.player_pool["Returning"]
    assert pool_player.prior_mu == 28.0
    assert pool_player.prior_sigma == 6.0
    assert pool_player.mu == 31.5
    assert pool_player.sigma == 3.0
