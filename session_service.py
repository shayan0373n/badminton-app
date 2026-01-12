"""
Service layer for orchestrating session operations that involve both
domain logic and database interactions.

This module sits between the UI (pages) and the lower-level logic/database modules,
ensuring that business rules are applied consistently regardless of where
the operation is initiated (UI or Tests).
"""

import logging

from database import MatchDB, PlayerDB, SessionDB
from exceptions import DatabaseError
from session_logic import ClubNightSession, Player, SessionManager
from app_types import Gender

logger = logging.getLogger("app.session_service")


def record_matches_to_database(
    session: ClubNightSession, winners_by_court: dict[int, tuple[str, ...]]
) -> None:
    """
    Records completed matches to the database for rating updates.

    Args:
        session: The active session with current round matches
        winners_by_court: Mapping of court numbers to winning teams

    Raises:
        DatabaseError: If match recording fails
    """
    if not session.current_round_matches or session.database_id is None:
        return

    for match in session.current_round_matches:
        court_num = match.court
        winner = winners_by_court.get(court_num)
        if not winner:
            continue

        if session.is_doubles:
            team_1, team_2 = match.team_1, match.team_2
            winner_side = 1 if set(winner) == set(team_1) else 2
            MatchDB.add_match(
                session_id=session.database_id,
                player_1=team_1[0],
                player_2=team_1[1],
                winner_side=winner_side,
                player_3=team_2[0],
                player_4=team_2[1],
            )
        else:
            p1, p2 = match.player_1, match.player_2
            winner_side = 1 if winner[0] == p1 else 2
            MatchDB.add_match(
                session_id=session.database_id,
                player_1=p1,
                player_2=p2,
                winner_side=winner_side,
            )


def add_player_from_registry(
    session: ClubNightSession,
    session_name: str,
    player: Player,
    team_name: str = "",
) -> bool:
    """
    Adds a player from the registry to the current session and persists state.

    Args:
        session: The active session
        session_name: Name of the session
        player: The player object from the registry
        team_name: Optional team name for doubles

    Returns:
        True if added successfully, False if player already exists in session.
    """
    added = session.add_player(
        name=player.name,
        gender=player.gender,
        mu=player.mu,
        sigma=player.sigma,
        team_name=team_name,
    )

    if added:
        SessionManager.save(session, session_name)

    return added


def add_guest_player(
    session: ClubNightSession,
    name: str,
    gender: Gender,
    mu: float,
    team_name: str = "",
) -> tuple[bool, str | None]:
    """
    Adds a guest player to the session and syncs them to the database.

    Args:
        session: The active session
        name: Name of the guest
        gender: Gender of the guest
        mu: Initial skill rating
        team_name: Optional team name

    Returns:
        Tuple of (success, error_message).
        If success is True, error_message is None (or a warning).
    """
    guest = Player(
        name=name,
        gender=gender,
        mu=mu,
        team_name=team_name,
    )

    added = session.add_player(
        name=guest.name,
        gender=guest.gender,
        mu=guest.mu,
        team_name=guest.team_name,
    )

    if not added:
        return False, "Player already exists"

    # Sync to cloud registry
    try:
        PlayerDB.upsert_players({guest.name: guest})
    except DatabaseError as e:
        logger.error(f"Failed to sync guest {name} to cloud: {e}. Rolling back.")
        session.remove_player(guest.name)
        return False, f"Failed to sync to database: {e}"

    return True, None


def remove_player_from_session(
    session: ClubNightSession, session_name: str, player_name: str
) -> tuple[bool, str]:
    """
    Removes a player from the session and persists the change.

    Args:
        session: The active session
        session_name: Name of the session (for saving)
        player_name: The player to remove

    Returns:
        Tuple of (success, status) where status is 'immediate', 'queued', or 'not_found'.
    """
    # 1. Modify session state
    success, status = session.remove_player(player_name)

    # 2. Persist state if successful
    if success:
        SessionManager.save(session, session_name)

    return success, status


def update_court_count(
    session: ClubNightSession, session_name: str, new_count: int
) -> None:
    """
    Updates the number of courts and persists the change.

    Args:
        session: The active session
        session_name: Name of the session (for saving)
        new_count: New number of courts
    """
    # 1. Modify session state
    session.update_courts(new_count)

    # 2. Persist state
    SessionManager.save(session, session_name)


def process_round_completion(
    session: ClubNightSession,
    session_name: str,
    winners_by_court: dict[int, tuple[str, ...]],
) -> None:
    """
    Orchestrates the completion of a round:
    1. Records matches to DB (if enabled)
    2. Finalizes the round (updates scores)
    3. Prepares the next round (generates matches)
    4. Persists the session state

    Args:
        session: The active session
        session_name: Name of the session (for saving)
        winners_by_court: Map of court ID to winning team tuple

    Raises:
        DatabaseError: If recording matches fails.
    """
    # 1. Record to database
    if session.is_recorded and session.database_id is not None:
        record_matches_to_database(session, winners_by_court)

    # 2. Finalize and prepare next round
    session.finalize_round(winners_by_court)
    session.prepare_round()

    # 3. Save to disk
    SessionManager.save(session, session_name)


def create_new_session(
    player_table: dict[str, Player],
    num_courts: int,
    weights: dict,
    female_female_team_penalty: float,
    mixed_gender_team_penalty: float,
    female_singles_penalty: float,
    session_name: str,
    is_doubles: bool,
    is_recorded: bool = True,
) -> ClubNightSession:
    """
    Creates and initializes a new session.

    1. Creates session record in Database (if recorded)
    2. Initializes ClubNightSession object
    3. Prepares the first round
    4. Saves session to disk

    Returns:
        The initialized ClubNightSession object.

    Raises:
        DatabaseError: If session creation in DB fails.
    """
    # 1. Create session record in Supabase
    database_id = None
    if is_recorded:
        database_id = SessionDB.create_session(session_name, is_doubles)

    # 2. Initialize Session Object
    session = ClubNightSession(
        players=player_table,
        num_courts=num_courts,
        database_id=database_id,
        weights=weights,
        female_female_team_penalty=female_female_team_penalty,
        mixed_gender_team_penalty=mixed_gender_team_penalty,
        female_singles_penalty=female_singles_penalty,
        is_doubles=is_doubles,
        is_recorded=is_recorded,
    )

    # 3. Prepare First Round
    session.prepare_round()

    # 4. Save to Disk
    SessionManager.save(session, session_name)

    return session
