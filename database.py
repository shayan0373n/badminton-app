# database.py
"""
Database operations for the Badminton App.

This module handles all Supabase database interactions for players, sessions, and matches.
"""

import streamlit as st
from supabase import create_client, Client

from constants import (
    GLICKO2_DEFAULT_RATING,
    GLICKO2_DEFAULT_RD,
    GLICKO2_DEFAULT_VOLATILITY,
)
from exceptions import DatabaseError
from session_logic import Player
from app_types import Gender


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
        """
        supabase = get_supabase_client()
        response = supabase.table("players").select("*").execute()

        players: dict[str, Player] = {}
        for row in response.data:
            players[row["name"]] = Player(
                name=row["name"],
                gender=Gender(row["gender"]),
                elo=row.get("elo", GLICKO2_DEFAULT_RATING),
                deviation=row.get("deviation", GLICKO2_DEFAULT_RD),
                volatility=row.get("volatility", GLICKO2_DEFAULT_VOLATILITY),
                database_id=row.get("id"),  # Store the Supabase row ID
            )
        return players

    @staticmethod
    def upsert_players(players_dict: dict[str, Player]) -> None:
        """
        Upserts a dictionary of Player objects into the Supabase 'players' table.

        Uses the database_id (if present) to update existing rows. This allows
        editing player names without creating duplicate entries.

        Args:
            players_dict: A dictionary mapping player names to Player objects.
        """
        supabase = get_supabase_client()
        data = []
        for p in players_dict.values():
            player_data = {
                "name": p.name,
                "gender": p.gender,
                "elo": p.elo,
                "deviation": p.deviation,
                "volatility": p.volatility,
            }
            # Include the database ID if present for proper update matching
            if p.database_id is not None:
                player_data["id"] = p.database_id
            data.append(player_data)

        if data:
            # Use on_conflict="id" to update existing rows by their primary key
            supabase.table("players").upsert(data, on_conflict="id").execute()


class SessionDB:
    """Handles session persistence in Supabase."""

    @staticmethod
    def create_session(session_name: str, is_doubles: bool) -> int:
        """
        Creates a session record in Supabase.

        Args:
            session_name: Unique name for the session
            is_doubles: True for doubles mode, False for singles mode

        Returns:
            The session ID from the database

        Raises:
            DatabaseError: If the session could not be created
        """
        supabase = get_supabase_client()
        game_mode = "Doubles" if is_doubles else "Singles"
        response = (
            supabase.table("sessions")
            .insert({"name": session_name, "game_mode": game_mode})
            .execute()
        )

        if response.data:
            return response.data[0]["id"]
        raise DatabaseError(f"Failed to create session '{session_name}' in database")

    @staticmethod
    def get_session_by_name(session_name: str) -> dict | None:
        """
        Retrieves a session by name.

        Args:
            session_name: Name of the session to retrieve

        Returns:
            Session dict or None if not found
        """
        supabase = get_supabase_client()
        response = (
            supabase.table("sessions").select("*").eq("name", session_name).execute()
        )

        if response.data:
            return response.data[0]
        return None


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
        """
        Records a match result in Supabase.

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
        supabase = get_supabase_client()
        data = {
            "session_id": session_id,
            "player_1": player_1,
            "player_2": player_2,
            "winner_side": winner_side,
            "processed": False,
        }
        if player_3 and player_4:
            data["player_3"] = player_3
            data["player_4"] = player_4

        response = supabase.table("matches").insert(data).execute()

        if response.data:
            return response.data[0]["id"]
        raise DatabaseError("Failed to record match in database")

    @staticmethod
    def get_unprocessed_matches(session_id: int) -> list[dict]:
        """
        Gets all unprocessed matches for a session.

        Args:
            session_id: ID of the session

        Returns:
            List of match dictionaries
        """
        supabase = get_supabase_client()
        response = (
            supabase.table("matches")
            .select("*")
            .eq("session_id", session_id)
            .eq("processed", False)
            .execute()
        )

        return response.data if response.data else []

    @staticmethod
    def mark_matches_processed(match_ids: list[int]) -> None:
        """
        Marks matches as processed after rating update.

        Args:
            match_ids: List of match IDs to mark as processed
        """
        if not match_ids:
            return

        supabase = get_supabase_client()
        supabase.table("matches").update({"processed": True}).in_(
            "id", match_ids
        ).execute()
