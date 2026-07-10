# tests/unit/test_player_service_registry.py
"""
Unit tests for player registry utilities in player_service.

Tests the contract of dataframe_to_players (grid columns are correctly
converted to Player attributes; fields the grid does not expose are
preserved) and of sync_registry_to_database (deletion detection).
"""

import pandas as pd

import player_service
from app_types import Gender
from player_service import dataframe_to_players
from session_logic import Player


def test_dataframe_to_players_produces_correct_player_attributes():
    """
    dataframe_to_players should correctly convert all DataFrame columns
    to their corresponding Player attributes.
    """
    df = pd.DataFrame(
        {
            "Player Name": ["Alice"],
            "Gender": [Gender.FEMALE],
            "Prior Mu": [25.0],
            "Mu": [27.5],
            "Sigma": [5.0],
            "database_id": [42],
        }
    )

    result = dataframe_to_players(df)
    player = result["Alice"]

    assert player.name == "Alice"
    assert player.gender == Gender.FEMALE
    assert player.prior_mu == 25.0
    assert player.mu == 27.5
    assert player.sigma == 5.0
    assert player.database_id == 42


def test_dataframe_to_players_handles_nan_mu_and_sigma():
    """
    When Mu and Sigma are NaN (as with new players in the UI),
    the Player should receive prior_mu/prior_sigma via __post_init__.
    """
    df = pd.DataFrame(
        {
            "Player Name": ["NewPlayer"],
            "Gender": [Gender.MALE],
            "Prior Mu": [20.0],
            "Mu": [None],
            "Sigma": [None],
            "database_id": [None],
        }
    )

    result = dataframe_to_players(df)
    player = result["NewPlayer"]

    assert player.name == "NewPlayer"
    assert player.gender == Gender.MALE
    assert player.prior_mu == 20.0
    # When mu/sigma are None, Player.__post_init__ sets them to prior values
    assert player.mu == player.prior_mu
    assert player.sigma == player.prior_sigma
    assert player.database_id is None


def _registry_row(
    name="Alice",
    gender=Gender.FEMALE,
    prior_mu=25.0,
    mu=27.5,
    sigma=5.0,
    database_id=42,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Player Name": [name],
            "Gender": [gender],
            "Prior Mu": [prior_mu],
            "Mu": [mu],
            "Sigma": [sigma],
            "database_id": [database_id],
        }
    )


def test_dataframe_to_players_preserves_unexposed_fields():
    """
    Fields the grid does not expose (e.g. prior_sigma) must survive a save:
    edited rows are applied onto the existing Player matched by database_id.
    The existing registry object itself must not be mutated.
    """
    existing = {
        "Alice": Player(
            name="Alice",
            gender=Gender.FEMALE,
            prior_mu=25.0,
            prior_sigma=6.0,
            mu=27.5,
            sigma=5.0,
            database_id=42,
        )
    }

    result = dataframe_to_players(
        _registry_row(prior_mu=26.0), existing_registry=existing
    )
    player = result["Alice"]

    assert player.prior_mu == 26.0  # edited in the grid
    assert player.prior_sigma == 6.0  # not in the grid: preserved
    assert existing["Alice"].prior_mu == 25.0  # source object untouched


def test_dataframe_to_players_rename_keeps_identity():
    """A rename with the same database_id keeps the player's unexposed fields."""
    existing = {
        "Alice": Player(
            name="Alice",
            gender=Gender.FEMALE,
            prior_mu=25.0,
            prior_sigma=6.0,
            database_id=42,
        )
    }

    result = dataframe_to_players(
        _registry_row(name="Alicia"), existing_registry=existing
    )

    assert "Alice" not in result
    assert result["Alicia"].database_id == 42
    assert result["Alicia"].prior_sigma == 6.0


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
