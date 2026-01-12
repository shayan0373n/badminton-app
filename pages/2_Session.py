# pages/2_Session.py
"""
Session management page for the Badminton App.

This page displays the current round's matches and allows users to:
- Select winners for each court
- View current standings
- Manage courts and players mid-session
- Match data is saved for TrueSkill Through Time rating updates
"""

import logging
import pandas as pd
import streamlit as st

from constants import PAGE_SETUP, TTT_DEFAULT_MU
from database import MatchDB, PlayerDB, SessionDB
from exceptions import DatabaseError
from session_logic import ClubNightSession, Player, SessionManager
import session_service
from app_types import Gender

logger = logging.getLogger("app.session_page")


# =============================================================================
# Core UI Rendering Functions
# =============================================================================


def render_match_selection(
    session: ClubNightSession, locked_pairs_set: set[tuple[str, str]]
) -> dict[int, tuple[str, ...] | None]:
    """Renders match selection controls and returns winner selections by court.

    Args:
        session: The active club night session
        locked_pairs_set: Set of player name tuples representing locked teammate pairs

    Returns:
        Dictionary mapping court numbers to selected winner tuples (or None if not selected)
    """
    winners_by_court: dict[int, tuple[str, ...] | None] = {}

    if not session.current_round_matches:
        st.warning(
            "No courts could be formed with the current number of active players."
        )
        return winners_by_court

    for match in session.current_round_matches:
        with st.container(border=True):
            cols = st.columns([1, 3], vertical_alignment="center")
            with cols[0]:
                st.markdown(f"#### Court {match['court']}")
            with cols[1]:
                if session.is_doubles:
                    winner = _render_doubles_match(match, locked_pairs_set)
                else:
                    winner = _render_singles_match(match)
                winners_by_court[match["court"]] = winner

    return winners_by_court


def _render_singles_match(match: dict) -> tuple[str, ...] | None:
    """Renders a singles match selector and returns the winner."""
    p1, p2 = match["player_1"], match["player_2"]
    selection = st.segmented_control(
        "Select Winner",
        (p1, p2),
        key=f"court_{match['court']}",
        label_visibility="collapsed",
    )
    if selection == p1:
        return (p1,)
    elif selection == p2:
        return (p2,)
    return None


def _render_doubles_match(
    match: dict, locked_pairs_set: set[tuple[str, str]]
) -> tuple[str, ...] | None:
    """Renders a doubles match selector with lock indicators for fixed pairs."""
    team_1, team_2 = match["team_1"], match["team_2"]
    lock_icon = "🔗"

    # Build display names with lock indicators
    team_1_display = f"{team_1[0]} -- {team_1[1]}"
    team_2_display = f"{team_2[0]} -- {team_2[1]}"

    if tuple(sorted(team_1)) in locked_pairs_set:
        team_1_display = f"{lock_icon} {team_1_display}"
    if tuple(sorted(team_2)) in locked_pairs_set:
        team_2_display = f"{lock_icon} {team_2_display}"

    selection = st.segmented_control(
        "Select Winner",
        (team_1_display, team_2_display),
        key=f"court_{match['court']}",
        label_visibility="collapsed",
    )

    if selection == team_1_display:
        return team_1
    elif selection == team_2_display:
        return team_2
    return None


# =============================================================================
# Match Recording and Round Processing
# =============================================================================


def process_round_results(
    session: ClubNightSession,
    session_name: str,
    winners_by_court: dict[int, tuple[str, ...]],
) -> bool:
    """Validates, records, and finalizes round results.

    Returns:
        True if processing succeeded and a rerun is needed, False otherwise.
    """
    # Validate all courts have winners selected
    if not winners_by_court:
        st.warning("Cannot process results as no courts were available.")
        return False

    if not all(v is not None for v in winners_by_court.values()):
        st.warning("Please select a winner for each court before submitting.")
        return False

    # Process round completion via service
    try:
        session_service.process_round_completion(
            session, session_name, winners_by_court
        )
    except DatabaseError as e:
        # Check if it was a partial failure (matches recorded but maybe not all?)
        # Actually session_service raises before finalizing if recording fails,
        # preventing state corruption.
        st.warning(f"Could not record matches to cloud: {e}")
        # Behavior decision: Do we stop or continue?
        # Current logic allowed continuing but warned.
        # The service method aborted.
        # Let's assume strict consistency for now -> return False
        return False

    return True


# =============================================================================
# Sidebar Sections
# =============================================================================


def render_court_controls(session: ClubNightSession, session_name: str) -> None:
    """Renders court add/remove controls in the sidebar."""
    with st.expander("🎾 Courts", expanded=False):
        st.markdown(f"**Courts:** {int(session.num_courts)}")
        col_add, col_remove = st.columns(2)

        with col_add:
            if st.button("Add court", key="add_court_btn", width="stretch"):
                session_service.update_court_count(
                    session, session_name, session.num_courts + 1
                )
                st.rerun()

        with col_remove:
            if st.button("Remove court", key="remove_court_btn", width="stretch"):
                if session.num_courts > 1:
                    session_service.update_court_count(
                        session, session_name, session.num_courts - 1
                    )
                    st.rerun()
                else:
                    st.info("Minimum 1 court.")


def render_add_player_section(session: ClubNightSession, session_name: str) -> None:
    """Renders the add player section with registry selection or guest entry."""
    with st.expander("➕ Add Player", expanded=False):
        # Load master registry
        try:
            master_registry = PlayerDB.get_all_players()
        except DatabaseError:
            master_registry = {}
            st.warning("Could not load registry. Manual entry only.")

        # Filter out players already in session
        current_names = set(session.player_pool.keys())
        available_from_registry = [
            name for name in master_registry.keys() if name not in current_names
        ]

        add_method = st.radio(
            "Method",
            ["Pick from Registry", "New Guest"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if add_method == "Pick from Registry":
            _render_registry_player_add(
                session, session_name, master_registry, available_from_registry
            )
        else:
            _render_guest_player_add(session, session_name)


def _render_registry_player_add(
    session: ClubNightSession,
    session_name: str,
    master_registry: dict[str, Player],
    available_names: list[str],
) -> None:
    """Handles adding a player from the registry."""
    selected_name = st.selectbox(
        "Select Member", options=[""] + sorted(available_names)
    )

    # Show team name input in doubles mode (session-specific, not from database)
    team_name = ""
    if session.is_doubles:
        team_name = st.text_input(
            "Team Name(s)",
            key="reg_add_team",
            help="Comma-separated for multiple teams (e.g., 'TeamA, TeamB')",
        )

    if st.button("Add Member to Session", key="add_reg_btn"):
        if selected_name:
            p = master_registry[selected_name]
            added = session.add_player(
                name=p.name,
                gender=p.gender,
                mu=p.mu,
                sigma=p.sigma,
                team_name=team_name.strip() if session.is_doubles else "",
            )
            if added:
                SessionManager.save(session, session_name)
                st.success(f"Added {selected_name} to the session!")
                st.rerun()
        else:
            st.warning("Please select a member.")


def _render_guest_player_add(session: ClubNightSession, session_name: str) -> None:
    """Handles creating and adding a new guest player."""
    new_name = st.text_input("Guest Name", key="mid_add_name")
    new_gender = st.selectbox("Gender", options=["M", "F"], key="mid_add_gender")
    new_mu = st.number_input(
        "Skill (Mu)",
        min_value=0.0,
        step=0.5,
        value=TTT_DEFAULT_MU,
        key="mid_add_mu",
    )

    new_team_name = ""
    if session.is_doubles:
        new_team_name = st.text_input(
            "Team Name(s)",
            key="mid_add_team",
            help="Comma-separated for multiple teams (e.g., 'TeamA, TeamB')",
        )

    if st.button("Create & Add Guest", key="mid_add_btn"):
        if not new_name.strip():
            st.warning("Please enter a name.")
            return

        success, error_msg = session_service.add_guest_player(
            session=session,
            name=new_name.strip(),
            gender=Gender(new_gender),
            mu=float(new_mu),
            team_name=new_team_name.strip(),
        )

        if success:
            if error_msg:
                st.warning(f"Guest added locally, but cloud sync failed: {error_msg}")

            SessionManager.save(session, session_name)
            st.success(f"Added {new_name} and saved to Member Registry!")
            st.rerun()
        else:
            st.warning(error_msg or "Failed to add player.")


def render_remove_player_section(session: ClubNightSession, session_name: str) -> None:
    """Renders the remove player section with queued removal display."""
    with st.expander("➖ Remove Player", expanded=False):
        # Show queued removals
        if session.queued_removals:
            st.warning(
                f"⏳ Queued for removal: {', '.join(sorted(session.queued_removals))}"
            )
            st.caption(
                "These players will be removed when you confirm the current round results."
            )

        all_players = list(session.player_pool.keys())
        if not all_players:
            st.info("No players to remove.")
            return

        player_to_remove = st.selectbox(
            "Select Player to Remove",
            options=sorted(all_players),
            key="remove_player_select",
        )

        if st.button("Remove Player", key="mid_remove_btn", type="secondary"):
            success, status = session_service.remove_player_from_session(
                session, session_name, player_to_remove
            )
            if success:
                if status == "immediate":
                    st.success(f"✅ Removed {player_to_remove} from the session.")
                elif status == "queued":
                    st.info(
                        f"⏳ {player_to_remove} is currently playing and will be "
                        "removed after you confirm this round's results."
                    )
                st.rerun()
            else:
                st.error(f"Player {player_to_remove} not found.")


def handle_session_termination(session: ClubNightSession, session_name: str) -> None:
    """Handles session termination with state preservation."""
    if not st.button("⚠️ Terminate Session"):
        return

    # Preserve session state for next session
    persistent = session.get_persistent_state()
    st.session_state.player_table = persistent["player_pool"]
    st.session_state.player_table_updated = True
    st.session_state.num_courts_persistent = persistent["num_courts"]
    st.session_state.is_doubles_persistent = persistent["is_doubles"]
    st.session_state.weights = persistent["weights"]
    st.session_state.skill_weight = persistent["weights"]["skill"]
    st.session_state.power_weight = persistent["weights"]["power"]
    st.session_state.pairing_weight = persistent["weights"]["pairing"]
    st.session_state.female_female_team_penalty = persistent[
        "female_female_team_penalty"
    ]
    st.session_state.mixed_gender_team_penalty = persistent["mixed_gender_team_penalty"]
    st.session_state.female_singles_penalty = persistent["female_singles_penalty"]
    st.session_state.is_recorded_persistent = persistent["is_recorded"]

    # Clean up
    SessionManager.clear(session_name)
    st.session_state.pop("session", None)
    st.session_state.pop("current_session_name", None)

    st.switch_page(PAGE_SETUP)


# =============================================================================
# Page Setup and Main Layout
# =============================================================================


def inject_css(file_path: str) -> None:
    """Injects custom CSS from the specified file path."""
    try:
        with open(file_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSS file not found at {file_path}.")


st.set_page_config(initial_sidebar_state="collapsed", layout="wide")
inject_css("styles.css")

# --- Page Entry Validation ---
if "session" not in st.session_state or "current_session_name" not in st.session_state:
    st.error("No active session found. Please start or resume a session.")
    st.switch_page(PAGE_SETUP)

session: ClubNightSession = st.session_state.session
session_name: str = st.session_state.current_session_name

# --- Main Layout ---
game_mode_str = "Doubles" if session.is_doubles else "Singles"
st.title(f"🏸 {session_name} ({game_mode_str})", anchor=False)
if not session.is_recorded:
    st.caption("⚠️ This session is not being recorded to the dataset.")

col_matches, col_standings = st.columns([2, 1])

# Left column: Match selection form
with col_matches:
    st.header(f"Select Winners for Round {session.round_num}")
    st.info(f"**Resting:** {', '.join(session.resting_players)}")

    # Build locked pairs set for visual indicators from required partners graph
    locked_pairs_set: set[tuple[str, str]] = set()
    if session.is_doubles:
        required_partners = session.get_required_partners()
        for player, partners in required_partners.items():
            for partner in partners:
                locked_pairs_set.add(tuple(sorted((player, partner))))

    with st.form(key="results_form"):
        winners_by_court = render_match_selection(session, locked_pairs_set)
        submitted = st.form_submit_button("✅ Confirm Results")

        if submitted and process_round_results(session, session_name, winners_by_court):
            st.rerun()

# Right column: Standings
with col_standings:
    st.header("Current Standings")
    standings_data = session.get_standings()
    if standings_data:
        df_standings = pd.DataFrame(standings_data, columns=["Player", "Earned Score"])
        df_standings.index += 1
    else:
        df_standings = pd.DataFrame(columns=["Player", "Earned Score"])
    st.dataframe(df_standings, width="stretch")

# --- Sidebar ---
with st.sidebar:
    st.header("Manage Session")
    render_court_controls(session, session_name)
    render_add_player_section(session, session_name)
    render_remove_player_section(session, session_name)
    handle_session_termination(session, session_name)
