"""
Service layer for player registry operations.

This module keeps the cloud database in sync with edits to the player
registry.
"""

import logging

from database import PlayerDB
from session_logic import Player

logger = logging.getLogger("app.player_service")


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
