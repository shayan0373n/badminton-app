"""
Tests for guest player database synchronization.

These tests verify that guest players are properly synchronized to the database
and that appropriate errors are raised when synchronization fails.
"""

import pytest
from unittest.mock import patch, MagicMock

from app_types import Gender
from database import MatchDB, PlayerDB
from exceptions import DatabaseError
from session_logic import ClubNightSession, Player
import session_service


# Simulated set of players that "exist" in the database
PLAYERS_IN_DB = {"Alice", "Bob", "Charlie", "Dave"}


def mock_add_match_with_fk_constraint(
    session_id: int,
    player_1: str,
    player_2: str,
    winner_side: int,
    player_3: str | None = None,
    player_4: str | None = None,
) -> int:
    """Mock that simulates FK constraint - raises error if player not in DB."""
    all_players = [player_1, player_2]
    if player_3:
        all_players.append(player_3)
    if player_4:
        all_players.append(player_4)

    for player in all_players:
        if player not in PLAYERS_IN_DB:
            raise DatabaseError(
                f"Foreign key constraint violation: player '{player}' not found"
            )

    return 1  # Return fake match ID


@pytest.fixture
def db_players():
    """Players that exist in the database."""
    return {
        "Alice": Player(name="Alice", gender=Gender.FEMALE, prior_mu=25.0),
        "Bob": Player(name="Bob", gender=Gender.MALE, prior_mu=25.0),
        "Charlie": Player(name="Charlie", gender=Gender.MALE, prior_mu=25.0),
        "Dave": Player(name="Dave", gender=Gender.MALE, prior_mu=25.0),
    }


@pytest.fixture
def session_with_guest(db_players):
    """
    Creates a session with a guest player added.

    The guest exists in the session's player_pool but is simulated as
    not existing in the database (for FK constraint testing).
    """
    session = ClubNightSession(
        players=db_players,
        num_courts=1,
        is_doubles=True,
        is_recorded=True,
    )
    session.database_id = 123  # Simulate a recorded session with DB ID

    # Add guest to session (this succeeds locally)
    session.add_player(name="NewGuest", gender=Gender.MALE, mu=25.0)

    return session


class TestGuestPlayerSync:
    """Tests for guest player database synchronization."""

    def test_guest_addition_fails_when_db_sync_fails(self, db_players):
        """
        When database sync fails during guest addition, the operation
        should return failure so the user knows the guest wasn't saved.
        """
        session = ClubNightSession(
            players=db_players,
            num_courts=1,
            is_doubles=True,
            is_recorded=True,
        )
        session.database_id = 123

        # Mock PlayerDB.upsert_players to fail
        with patch.object(
            PlayerDB, "upsert_players", side_effect=DatabaseError("Network error")
        ):
            success, error = session_service.add_guest_player(
                session, "NewGuest", Gender.MALE, mu=25.0
            )

            assert success is False, "Guest addition should fail when DB sync fails"
            assert error is not None, "Error message should be provided"

    def test_match_recording_fails_when_player_not_in_db(self, session_with_guest):
        """
        When recording a match that includes a player not in the database,
        the operation should fail with a DatabaseError.
        """
        session = session_with_guest

        # Prepare a round - guest will be assigned to play
        session.prepare_round()

        # Find if guest is playing (they should be, with 5 players and 1 court)
        guest_is_playing = False
        for match in session.current_round_matches:
            if session.is_doubles:
                all_players = list(match["team_1"]) + list(match["team_2"])
            else:
                all_players = [match["player_1"], match["player_2"]]

            if "NewGuest" in all_players:
                guest_is_playing = True
                break

        # Guest should be playing (only 1 resting with 5 players, 1 court)
        assert guest_is_playing, "Guest should be playing for this test to be valid"

        # Create winners dict (team_1 wins)
        winners_by_court = {
            match["court"]: match["team_1"] for match in session.current_round_matches
        }

        # Mock MatchDB.add_match to simulate FK constraint
        with patch.object(
            MatchDB, "add_match", side_effect=mock_add_match_with_fk_constraint
        ):
            # This should raise DatabaseError because NewGuest is not in DB
            with pytest.raises(DatabaseError) as exc_info:
                session_service.record_matches_to_database(session, winners_by_court)

            assert "NewGuest" in str(exc_info.value)

    def test_match_recording_succeeds_when_all_players_in_db(self, db_players):
        """
        Match recording should succeed when all players exist in the database.
        """
        session = ClubNightSession(
            players=db_players,
            num_courts=1,
            is_doubles=True,
            is_recorded=True,
        )
        session.database_id = 123

        session.prepare_round()

        winners_by_court = {
            match["court"]: match["team_1"] for match in session.current_round_matches
        }

        # Mock MatchDB.add_match with FK constraint simulation
        with patch.object(
            MatchDB, "add_match", side_effect=mock_add_match_with_fk_constraint
        ):
            # Should NOT raise - all players are in PLAYERS_IN_DB
            session_service.record_matches_to_database(session, winners_by_court)
