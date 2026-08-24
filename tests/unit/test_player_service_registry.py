"""Tests for registry synchronisation.

Covers the deletion-detection contract: a player who disappears from the
registry is deleted by database id, and one who never had an id is not.
"""

import player_service
from app_types import Gender
from session_logic import Player


def test_sync_registry_deletes_removed_players(monkeypatch):
    """Players whose database_id disappears from the registry are deleted;
    the remaining registry is upserted. New players (no id) are never deleted."""
    deleted: list[int] = []
    upserted: dict[str, Player] = {}
    monkeypatch.setattr(
        player_service.PlayerDB,
        "delete_players_by_ids",
        lambda ids: deleted.extend(ids),
    )
    monkeypatch.setattr(
        player_service.PlayerDB,
        "upsert_players",
        lambda registry: upserted.update(registry),
    )

    alice = Player(name="Alice", gender=Gender.FEMALE, prior_mu=25.0, database_id=1)
    bob = Player(name="Bob", gender=Gender.MALE, prior_mu=25.0, database_id=2)
    newbie = Player(name="Newbie", gender=Gender.MALE, prior_mu=25.0)

    player_service.sync_registry_to_database(
        old_registry={"Alice": alice, "Bob": bob},
        new_registry={"Alice": alice, "Newbie": newbie},
    )

    assert deleted == [2]
    assert set(upserted) == {"Alice", "Newbie"}
