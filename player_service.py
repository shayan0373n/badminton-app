"""
Service layer for player registry operations.

This module handles business logic for player management, including
conversion between Player objects and UI DataFrames, and keeping
the cloud database in sync.
"""

import logging
from dataclasses import replace

import pandas as pd

from app_types import Gender
from database import PlayerDB
from exceptions import DatabaseError
from session_logic import Player

logger = logging.getLogger("app.player_service")

# Display label -> Player attribute for the registry grid, in column order.
# Fields absent from this map are never surfaced in the grid, so they are
# preserved as-is on save (see dataframe_to_players) and can't be silently reset.
REGISTRY_COLUMN_TO_FIELD = {
    "Player Name": "name",
    "Gender": "gender",
    "Prior Mu": "prior_mu",
    "Mu": "mu",
    "Sigma": "sigma",
}


def create_registry_dataframe(player_table: dict[str, Player]) -> pd.DataFrame:
    """Creates a DataFrame for the master member registry."""
    players = list(player_table.values())
    data: dict = {"#": list(range(1, len(players) + 1))}
    for column, field_name in REGISTRY_COLUMN_TO_FIELD.items():
        data[column] = [getattr(p, field_name) for p in players]
    data["Rating"] = [p.conservative_rating for p in players]
    data["database_id"] = [p.database_id for p in players]
    return pd.DataFrame(data)


def dataframe_to_players(
    edited_df: pd.DataFrame,
    existing_registry: dict[str, Player] | None = None,
) -> dict[str, Player]:
    """
    Converts an edited registry DataFrame into a Player dict.

    The grid is a lossy view of a Player: it only exposes the columns in
    REGISTRY_COLUMN_TO_FIELD. Each edited row is applied onto the existing
    Player it refers to (matched by database_id), so any field the grid does
    not expose (e.g. prior_sigma) is preserved rather than reset. Rows with no
    matching database_id are treated as new players.

    Args:
        edited_df: DataFrame from the Streamlit data_editor.
        existing_registry: The registry as loaded from the database, the source
            of truth for fields the grid does not expose.

    Returns:
        Dictionary mapping player names to Player objects.
    """
    existing_by_id = {
        p.database_id: p
        for p in (existing_registry or {}).values()
        if p.database_id is not None
    }

    new_registry: dict[str, Player] = {}
    for _, row in edited_df.dropna(subset=["Player Name"]).iterrows():
        db_id = None if pd.isna(row.get("database_id")) else int(row["database_id"])

        base = existing_by_id.get(db_id)
        # Start from the existing record (preserving unexposed fields) or a fresh
        # Player for new rows.
        player = (
            replace(base)
            if base is not None
            else Player(name=str(row["Player Name"]), gender=Gender(row["Gender"]))
        )

        player.name = str(row["Player Name"])
        player.gender = Gender(row["Gender"])
        player.prior_mu = float(row["Prior Mu"])
        # Mu/Sigma are TTT outputs (disabled in the grid); blank means the
        # value was never computed, so keep the existing/default one.
        if not pd.isna(row["Mu"]):
            player.mu = float(row["Mu"])
        if not pd.isna(row["Sigma"]):
            player.sigma = float(row["Sigma"])
        player.database_id = db_id
        # Mirror Player.__post_init__ for new players whose mu/sigma weren't given.
        if player.mu is None:
            player.mu = player.prior_mu
        if player.sigma is None:
            player.sigma = player.prior_sigma

        new_registry[player.name] = player

    return new_registry


def sync_registry_to_database(
    old_registry: dict[str, Player], new_registry: dict[str, Player]
) -> None:
    """
    Synchronizes the player registry to the database.

    Detects players that were removed (by comparing database IDs) and deletes
    them, then upserts the remaining/new players.

    Args:
        old_registry: The original registry state (before edits)
        new_registry: The edited registry state (after user changes)

    Raises:
        DatabaseError: If delete or upsert fails.
    """
    # Detect deleted players by comparing database IDs
    old_db_ids = {
        p.database_id for p in old_registry.values() if p.database_id is not None
    }
    new_db_ids = {
        p.database_id for p in new_registry.values() if p.database_id is not None
    }
    deleted_ids = list(old_db_ids - new_db_ids)

    # Delete removed players first
    if deleted_ids:
        logger.info(f"Deleting {len(deleted_ids)} player(s) from database")
        PlayerDB.delete_players_by_ids(deleted_ids)

    # Then upsert remaining/new players
    PlayerDB.upsert_players(new_registry)
    logger.info(f"Synced {len(new_registry)} player(s) to database")
