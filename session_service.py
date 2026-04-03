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
from rating_service import compute_gender_statistics
from session_logic import ClubNightSession, Player, SessionManager
from app_types import Gender, RoundRecord

logger = logging.getLogger("app.session_service")


def _record_round_to_database(session: ClubNightSession, record: RoundRecord) -> int:
    """Records matches from a single round record to the database.

    Only records matches with reported winners. Returns the number of matches recorded.

    Raises:
        DatabaseError: If match recording fails
    """
    recorded = 0
    for match in record.matches:
        court_num = match.court
        winner = record.winners_by_court.get(court_num)
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
        recorded += 1

    return recorded


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


def update_weights(
    session: ClubNightSession,
    session_name: str,
    skill: float,
    power: float,
    pairing: float,
) -> None:
    """
    Updates the optimizer weights and persists the change.

    Args:
        session: The active session
        session_name: Name of the session (for saving)
        skill: Weight for skill balance objective
        power: Weight for team power balance objective
        pairing: Weight for court history/pairing variety objective
    """
    session.weights = {
        "skill": skill,
        "power": power,
        "pairing": pairing,
    }
    SessionManager.save(session, session_name)


def advance_to_next_round(session: ClubNightSession, session_name: str) -> None:
    """Finalizes the current round and generates the next one.

    No database recording — use submit_session_results() for that.
    Partial results are OK (unreported courts are simply skipped).
    """
    session.finalize_round()
    session.prepare_round()
    SessionManager.save(session, session_name)


def save_court_result(
    session: ClubNightSession,
    session_name: str,
    round_idx: int,
    court_num: int,
    winner: tuple[str, ...] | None,
) -> None:
    """Saves a single court result and recomputes standings."""
    session.set_court_result(round_idx, court_num, winner)
    session.recompute_earned_ratings()
    SessionManager.save(session, session_name)


def submit_session_results(
    session: ClubNightSession, session_name: str
) -> tuple[int, int]:
    """Uploads all session match results to the database (idempotent).

    Deletes any previously uploaded matches for this session, then re-inserts
    all matches that have reported winners.

    Note: The delete + re-insert is not atomic. A failure midway through
    re-insertion may leave fewer matches than before. Re-submitting fixes this.

    Returns:
        Tuple of (matches_recorded, unreported_courts).
    """
    if not session.is_recorded or session.database_id is None:
        return 0, 0

    MatchDB.delete_by_session(session.database_id)

    total_recorded = 0
    total_unreported = 0
    for record in session.round_history:
        total_recorded += _record_round_to_database(session, record)
        total_unreported += len(record.matches) - len(record.winners_by_court)

    session.results_dirty = False
    SessionManager.save(session, session_name)
    return total_recorded, total_unreported


def create_new_session(
    player_table: dict[str, Player],
    num_courts: int,
    weights: dict,
    session_name: str,
    is_doubles: bool,
    is_recorded: bool = True,
) -> ClubNightSession:
    """
    Creates and initializes a new session.

    1. Computes gender statistics from all registered players
    2. Creates session record in Database (if recorded)
    3. Initializes ClubNightSession object
    4. Prepares the first round
    5. Saves session to disk

    Returns:
        The initialized ClubNightSession object.

    Raises:
        DatabaseError: If session creation in DB fails.
    """
    # 1. Compute gender statistics from all registered players
    all_players = PlayerDB.get_all_players()
    gender_stats = compute_gender_statistics(all_players)

    # 2. Create session record in Supabase
    database_id = None
    if is_recorded:
        database_id = SessionDB.create_session(session_name, is_doubles)

    # 3. Initialize Session Object
    session = ClubNightSession(
        players=player_table,
        num_courts=num_courts,
        gender_stats=gender_stats,
        database_id=database_id,
        weights=weights,
        is_doubles=is_doubles,
        is_recorded=is_recorded,
    )

    # 4. Prepare First Round
    session.prepare_round()

    # 5. Save to Disk
    SessionManager.save(session, session_name)

    return session
