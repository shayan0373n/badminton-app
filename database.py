# database.py
"""
Database operations for the Badminton App.

This module handles all Supabase database interactions for players, sessions, and matches.
All methods translate Supabase exceptions to DatabaseError for consistent error handling.
"""

import logging

import streamlit as st
from supabase import create_client, Client


from exceptions import DatabaseError
from session_logic import Player
from app_types import Gender

logger = logging.getLogger("app.database")


# Initialize Supabase client
@st.cache_resource
def get_supabase_client() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


class PlayerDB:
    """Handles player persistence in Supabase."""

    @staticmethod
    def get_all_players() -> dict[str, Player]:
        """Fetches all players from the Supabase 'players' table.

        Returns:
            Dict mapping player names to Player objects.

        Raises:
            DatabaseError: If the query fails.
        """

        try:
            supabase = get_supabase_client()
            response = supabase.table("players").select("*").execute()
        except Exception as e:
            logger.exception("Supabase API call failed: get_all_players")
            raise DatabaseError("Failed to fetch players from database") from e

        players: dict[str, Player] = {}
        for row in response.data:
            players[row["name"]] = Player(
                name=row["name"],
                gender=Gender(row["gender"]),
                prior_mu=row["prior_mu"],
                prior_sigma=row["prior_sigma"],
                mu=row["mu"],
                sigma=row["sigma"],
                database_id=row["id"],
            )
        return players

    @staticmethod
    def upsert_players(players_dict: dict[str, Player]) -> None:
        """Upserts Player objects into the Supabase 'players' table.

        New players (without database_id) are inserted. Existing players
        (with database_id) are updated using their known ID.

        Args:
            players_dict: A dictionary mapping player names to Player objects.

        Raises:
            DatabaseError: If the upsert fails.
        """
        new_players = []
        existing_players = []

        for p in players_dict.values():
            player_data = {
                "name": p.name,
                "gender": p.gender,
                "prior_mu": p.prior_mu,
                "prior_sigma": p.prior_sigma,
                "mu": p.mu,
                "sigma": p.sigma,
            }
            if p.database_id is not None:
                player_data["id"] = p.database_id
                existing_players.append(player_data)
            else:
                new_players.append(player_data)

        try:
            supabase = get_supabase_client()
            if new_players:
                supabase.table("players").upsert(
                    new_players, on_conflict="name"
                ).execute()

            if existing_players:
                supabase.table("players").upsert(
                    existing_players, on_conflict="id"
                ).execute()
        except Exception as e:
            logger.exception("Supabase API call failed: upsert_players")
            raise DatabaseError("Failed to save players to database") from e

    @staticmethod
    def delete_players_by_ids(player_ids: list[int]) -> None:
        """Deletes players from the database by their IDs.

        Args:
            player_ids: List of database IDs for players to delete.

        Raises:
            DatabaseError: If the delete fails.
        """
        if not player_ids:
            return

        try:
            supabase = get_supabase_client()
            supabase.table("players").delete().in_("id", player_ids).execute()
        except Exception as e:
            logger.exception("Supabase API call failed: delete_players_by_ids")
            raise DatabaseError("Failed to delete players from database") from e


class SessionDB:
    """Handles session persistence in Supabase."""

    @staticmethod
    def create_session(session_name: str, is_doubles: bool) -> int:
        """Creates a session record in Supabase.

        Args:
            session_name: Unique name for the session
            is_doubles: True for doubles mode, False for singles mode

        Returns:
            The session ID from the database

        Raises:
            DatabaseError: If the session could not be created
        """
        game_mode = "Doubles" if is_doubles else "Singles"

        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("sessions")
                .insert({"name": session_name, "game_mode": game_mode})
                .execute()
            )
        except Exception as e:
            logger.exception(
                f"Supabase API call failed: create_session '{session_name}'"
            )
            raise DatabaseError(f"Failed to create session '{session_name}'") from e

        if response.data:
            return response.data[0]["id"]

        logger.error(f"Session creation returned empty data for '{session_name}'")
        raise DatabaseError(
            f"Failed to create session '{session_name}' - No ID returned"
        )

    @staticmethod
    def get_session_by_name(session_name: str) -> dict | None:
        """Retrieves a session by name.

        Args:
            session_name: Name of the session to retrieve

        Returns:
            Session dict or None if not found

        Raises:
            DatabaseError: If the query fails.
        """
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("sessions")
                .select("*")
                .eq("name", session_name)
                .execute()
            )
        except Exception as e:
            logger.exception(
                f"Supabase API call failed: get_session_by_name '{session_name}'"
            )
            raise DatabaseError(f"Failed to retrieve session '{session_name}'") from e

        if response.data:
            return response.data[0]
        return None

    @staticmethod
    def get_all_sessions() -> list[dict]:
        """Fetches all sessions from the database.

        Returns:
            List of session dictionaries with id, name, game_mode, created_at.

        Raises:
            DatabaseError: If the query fails.
        """
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("sessions").select("*").order("created_at").execute()
            )
        except Exception as e:
            logger.exception("Supabase API call failed: get_all_sessions")
            raise DatabaseError("Failed to fetch sessions from database") from e

        return response.data if response.data else []


class MatchDB:
    """Handles match persistence in Supabase."""

    @staticmethod
    def add_match(
        session_id: int,
        player_1: str,
        player_2: str,
        winner_side: int,
        player_3: str | None = None,
        player_4: str | None = None,
    ) -> int:
        """Records a match result in Supabase.

        Args:
            session_id: ID of the session this match belongs to
            player_1: First player (Singles) or Team 1 Player A (Doubles)
            player_2: Second player (Singles) or Team 1 Player B (Doubles)
            winner_side: 1 if player_1/2 won, 2 if player_3/4 won
            player_3: Team 2 Player A (Doubles only)
            player_4: Team 2 Player B (Doubles only)

        Returns:
            The match ID from the database

        Raises:
            DatabaseError: If the match could not be recorded
        """
        data = {
            "session_id": session_id,
            "player_1": player_1,
            "player_2": player_2,
            "winner_side": winner_side,
        }
        if player_3 and player_4:
            data["player_3"] = player_3
            data["player_4"] = player_4

        try:
            supabase = get_supabase_client()
            response = supabase.table("matches").insert(data).execute()
        except Exception as e:
            logger.exception("Supabase API call failed: add_match")
            raise DatabaseError("Failed to record match in database") from e

        if response.data:
            return response.data[0]["id"]

        logger.error("Match creation returned empty data")
        raise DatabaseError("Failed to record match - No ID returned")

    @staticmethod
    def get_all_matches() -> list[dict]:
        """Fetches all matches from the database, ordered by session and creation time.

        Returns:
            List of match dictionaries.

        Raises:
            DatabaseError: If the query fails.
        """
        try:
            supabase = get_supabase_client()
            response = (
                supabase.table("matches")
                .select("*")
                .order("session_id")
                .order("id")
                .execute()
            )
        except Exception as e:
            logger.exception("Supabase API call failed: get_all_matches")
            raise DatabaseError("Failed to fetch matches from database") from e

        return response.data if response.data else []
