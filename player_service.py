"""
Service layer for player registry operations.

This module handles business logic for player management, including
conversion between Player objects and UI DataFrames, and keeping
the cloud database in sync.
"""

import logging
import pandas as pd

from app_types import Gender
from constants import DEFAULT_IS_DOUBLES, TTT_DEFAULT_SIGMA
from database import PlayerDB
from exceptions import DatabaseError
from session_logic import Player

logger = logging.getLogger("app.player_service")


def _get_base_player_data(player_table: dict[str, Player]) -> dict:
    """Internal helper to extract common player data for DataFrames."""
    return {
        "#": range(1, len(player_table) + 1),
        "Player Name": [p.name for p in player_table.values()],
        "Gender": [p.gender for p in player_table.values()],
        "Prior Mu": [p.prior_mu for p in player_table.values()],
        "Mu": [p.mu for p in player_table.values()],
        "Sigma": [p.sigma for p in player_table.values()],
        "Rating": [p.conservative_rating for p in player_table.values()],
        "database_id": [p.database_id for p in player_table.values()],
    }


def create_registry_dataframe(player_table: dict[str, Player]) -> pd.DataFrame:
    """Creates a DataFrame for the master member registry."""
    return pd.DataFrame(_get_base_player_data(player_table))


def create_session_setup_dataframe(
    player_table: dict[str, Player], is_doubles: bool = DEFAULT_IS_DOUBLES
) -> pd.DataFrame:
    """
    Creates a DataFrame for session setup, potentially including team names.
    Includes 'Team Name' column only if in doubles mode.
    """
    df_data = _get_base_player_data(player_table)
    if is_doubles:
        df_data["Team Name"] = [
            p.team_name if hasattr(p, "team_name") else ""
            for p in player_table.values()
        ]
    return pd.DataFrame(df_data)


def dataframe_to_players(edited_df: pd.DataFrame) -> dict[str, Player]:
    """
    Converts an edited registry DataFrame into a Player dict.

    Handles new players that have empty/NaN values for Mu and Sigma
    (disabled columns in the UI) by converting them to None.
    The Player dataclass handles None via __post_init__.

    Args:
        edited_df: DataFrame from the Streamlit data_editor

    Returns:
        Dictionary mapping player names to Player objects
    """
    new_registry = {}
    for _, row in edited_df.dropna(subset=["Player Name"]).iterrows():
        # Convert NaN to None for nullable fields (database accepts NULL)
        db_id = None if pd.isna(row.get("database_id")) else int(row["database_id"])
        mu = None if pd.isna(row["Mu"]) else float(row["Mu"])
        sigma = None if pd.isna(row["Sigma"]) else float(row["Sigma"])

        new_registry[row["Player Name"]] = Player(
            name=row["Player Name"],
            gender=Gender(row["Gender"]),
            prior_mu=float(row["Prior Mu"]),
            prior_sigma=TTT_DEFAULT_SIGMA,
            mu=mu,
            sigma=sigma,
            database_id=db_id,
            team_name=row.get("Team Name", ""),
        )

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
