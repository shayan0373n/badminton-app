# pages/2_Session.py
"""
Session management page for the Badminton App.

This page displays the current round's matches and allows users to:
- Navigate between rounds with prev/next buttons
- Select winners for each court (auto-saved on change)
- View current standings
- Manage courts and players mid-session
- Submit all match results to the database
"""

import logging
import pandas as pd
import streamlit as st

from constants import PAGE_SETUP, TTT_DEFAULT_MU
from database import PlayerDB
from exceptions import DatabaseError
from session_logic import ClubNightSession, Player, SessionManager
import session_service
from app_types import Gender, SinglesMatch, DoublesMatch, RoundRecord

logger = logging.getLogger("app.session_page")


# =============================================================================
# UI Utilities
# =============================================================================


def format_display_name(name: str, max_length: int = 14) -> str:
    """Shortens a name for display (e.g., 'Christopher Smith' -> 'Christopher S.')."""
    if len(name) <= max_length:
        return name

    parts = name.split()
    if len(parts) > 1:
        # Try 'First L.' format
        first = parts[0]
        last_initial = parts[-1][0]
        formatted = f"{first} {last_initial}."
        if len(formatted) <= max_length:
            return formatted
        # Try just 'First' if still too long
        if len(first) <= max_length:
            return first

    # Fallback to simple truncation
    return name[: max_length - 2] + ".."


# =============================================================================
# Core UI Rendering Functions
# =============================================================================


def render_round_matches(
    session: ClubNightSession,
    session_name: str,
    record: RoundRecord,
    round_idx: int,
    locked_pairs_set: set[tuple[str, str]],
) -> None:
    """Renders match selection controls for a round with auto-save.

    Args:
        session: The active club night session
        session_name: Session name for persistence
        record: The round record to display
        round_idx: Index of this round in round_history (0-based)
        locked_pairs_set: Set of player name tuples representing locked teammate pairs
    """
    if not record.matches:
        st.warning(
            "No courts could be formed with the current number of active players."
        )
        return

    for match in record.matches:
        with st.container(border=True):
            cols = st.columns([1, 3], vertical_alignment="center")
            with cols[0]:
                st.markdown(f"#### Court {match.court}")
            with cols[1]:
                stored = record.winners_by_court.get(match.court)
                if session.is_doubles:
                    selected = _render_doubles_match(
                        match, locked_pairs_set, record.round_num, stored
                    )
                else:
                    selected = _render_singles_match(match, record.round_num, stored)

                # Auto-save on change
                if selected != stored:
                    session_service.save_court_result(
                        session, session_name, round_idx, match.court, selected
                    )


def _render_singles_match(
    match: SinglesMatch,
    round_num: int,
    stored_winner: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Renders a singles match selector and returns the winner."""
    p1, p2 = match.player_1, match.player_2

    # Map display names to actual names
    display_to_real = {format_display_name(p1): p1, format_display_name(p2): p2}
    real_to_display = {v: k for k, v in display_to_real.items()}

    # Compute default from stored winner
    default = None
    if stored_winner and stored_winner[0] in real_to_display:
        default = real_to_display[stored_winner[0]]

    selection = st.segmented_control(
        "Select Winner",
        options=list(display_to_real.keys()),
        default=default,
        key=f"round_{round_num}_court_{match.court}",
        label_visibility="collapsed",
    )

    real_winner = display_to_real.get(selection)
    return (real_winner,) if real_winner else None


def _render_doubles_match(
    match: DoublesMatch,
    locked_pairs_set: set[tuple[str, str]],
    round_num: int,
    stored_winner: tuple[str, ...] | None,
) -> tuple[str, ...] | None:
    """Renders a doubles match selector with lock indicators for fixed pairs."""
    team_1, team_2 = match.team_1, match.team_2
    lock_icon = "🔗"

    # Format names for display
    t1_p1 = format_display_name(team_1[0], max_length=10)
    t1_p2 = format_display_name(team_1[1], max_length=10)
    t2_p1 = format_display_name(team_2[0], max_length=10)
    t2_p2 = format_display_name(team_2[1], max_length=10)

    # Build display names
    team_1_display = f"{t1_p1} & {t1_p2}"
    team_2_display = f"{t2_p1} & {t2_p2}"

    if tuple(sorted(team_1)) in locked_pairs_set:
        team_1_display = f"{lock_icon} {team_1_display}"
    if tuple(sorted(team_2)) in locked_pairs_set:
        team_2_display = f"{lock_icon} {team_2_display}"

    # Map display names back to actual team tuples
    display_to_real = {team_1_display: team_1, team_2_display: team_2}
    real_to_display = {team_1: team_1_display, team_2: team_2_display}

    # Compute default from stored winner
    default = None
    if stored_winner and stored_winner in real_to_display:
        default = real_to_display[stored_winner]

    selection = st.segmented_control(
        "Select Winner",
        options=list(display_to_real.keys()),
        default=default,
        key=f"round_{round_num}_court_{match.court}",
        label_visibility="collapsed",
    )

    return display_to_real.get(selection)


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
            added = session_service.add_player_from_registry(
                session=session,
                session_name=session_name,
                player=p,
                team_name=team_name.strip() if session.is_doubles else "",
            )
            if added:
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
                "These players will be removed when you advance to the next round."
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
                    st.success(f"Removed {player_to_remove} from the session.")
                elif status == "queued":
                    st.info(
                        f"⏳ {player_to_remove} is currently playing and will be "
                        "removed when you advance to the next round."
                    )
                st.rerun()
            else:
                st.error(f"Player {player_to_remove} not found.")


def render_weights_section(session: ClubNightSession, session_name: str) -> None:
    """Renders the optimizer weights adjustment section."""
    with st.expander("⚖️ Optimizer Weights", expanded=False):
        st.caption("Higher = more important. Changes apply to next round.")

        skill = st.number_input(
            "Skill Balance",
            min_value=0.0,
            max_value=10.0,
            value=float(session.weights.get("skill", 1.0)),
            step=0.5,
            key="weight_skill",
            help="Group similar skill levels on the same court",
        )
        power = st.number_input(
            "Team Power Balance",
            min_value=0.0,
            max_value=10.0,
            value=float(session.weights.get("power", 1.0)),
            step=0.5,
            key="weight_power",
            help="Balance team strength within each court",
        )
        pairing = st.number_input(
            "Pairing Variety",
            min_value=0.0,
            max_value=10.0,
            value=float(session.weights.get("pairing", 1.0)),
            step=0.5,
            key="weight_pairing",
            help="Avoid repeating player matchups",
        )

        # Only update if values changed
        current = session.weights
        if (
            skill != current.get("skill")
            or power != current.get("power")
            or pairing != current.get("pairing")
        ):
            if st.button("Apply Weights", key="apply_weights_btn"):
                session_service.update_weights(
                    session, session_name, skill, power, pairing
                )
                st.success("Weights updated!")
                st.rerun()


def render_submit_results(session: ClubNightSession, session_name: str) -> None:
    """Renders the submit results button for uploading matches to DB."""
    if not session.is_recorded:
        return

    with st.expander("📤 Submit Results", expanded=False):
        st.caption("Upload all match results to the database.")

        # Count unreported courts across all rounds
        total_unreported = sum(
            len(r.matches) - len(r.winners_by_court)
            for r in session.round_history
        )
        if total_unreported > 0:
            st.warning(f"{total_unreported} court(s) have no winner selected.")

        if st.button("Submit Results to Database", key="submit_results_btn"):
            try:
                recorded, unreported = session_service.submit_session_results(
                    session, session_name
                )
                st.success(f"Uploaded {recorded} match(es).")
                if unreported > 0:
                    st.info(f"{unreported} court(s) skipped (no winner selected).")
            except DatabaseError as e:
                st.error(f"Failed to submit results: {e}")


def terminate_session(
    session: ClubNightSession, session_name: str, confirm_key: str | None = None
) -> None:
    """Preserves setup state, clears current session, and navigates to setup page."""
    persistent = session.get_persistent_state()
    st.session_state.player_table = persistent["player_pool"]
    st.session_state.player_table_updated = True
    st.session_state.num_courts_persistent = persistent["num_courts"]
    st.session_state.is_doubles_persistent = persistent["is_doubles"]
    st.session_state.weights = persistent["weights"]
    st.session_state.skill_weight = persistent["weights"]["skill"]
    st.session_state.power_weight = persistent["weights"]["power"]
    st.session_state.pairing_weight = persistent["weights"]["pairing"]
    st.session_state.is_recorded_persistent = persistent["is_recorded"]

    SessionManager.clear(session_name)
    st.session_state.pop("session", None)
    st.session_state.pop("current_session_name", None)
    if confirm_key is not None:
        st.session_state.pop(confirm_key, None)
    st.switch_page(PAGE_SETUP)


def handle_session_termination(session: ClubNightSession, session_name: str) -> None:
    """Handles session termination with state preservation."""
    confirm_key = "confirm_terminate_unsaved_results"

    if not (session.is_recorded and session.results_dirty):
        st.session_state.pop(confirm_key, None)
        if st.button("⚠️ Terminate Session"):
            terminate_session(session, session_name, confirm_key)
        return

    if st.session_state.get(confirm_key):
        st.warning(
            "Some results have not been submitted to the database. "
            "Terminating now will discard those unsaved results."
        )
        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button("Confirm Terminate", key="confirm_terminate_btn"):
                terminate_session(session, session_name, confirm_key)
        with cancel_col:
            if st.button("Cancel", key="cancel_terminate_btn"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
        return

    if st.button("⚠️ Terminate Session"):
        st.session_state[confirm_key] = True
        st.rerun()


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

# Left column: Matches with round navigation
with col_matches:
    if not session.round_history:
        st.warning("No rounds generated yet.")
    else:
        # Initialize viewing index to latest round
        if "viewing_round_idx" not in st.session_state:
            st.session_state.viewing_round_idx = len(session.round_history) - 1

        # Clamp to valid range (in case rounds were added)
        max_idx = len(session.round_history) - 1
        view_idx = min(st.session_state.viewing_round_idx, max_idx)
        view_idx = max(view_idx, 0)

        is_latest = view_idx == max_idx
        record = session.round_history[view_idx]

        # Round navigation: < | Round N of M | > / Generate Next Round
        nav_cols = st.columns([1, 3, 1])
        with nav_cols[0]:
            if view_idx > 0:
                if st.button("◀", key="prev_round", use_container_width=True):
                    st.session_state.viewing_round_idx = view_idx - 1
                    st.rerun()
        with nav_cols[1]:
            st.markdown(
                f"<h3 style='text-align: center; margin: 0;'>Round {record.round_num} of {session.round_num}</h3>",
                unsafe_allow_html=True,
            )
        with nav_cols[2]:
            if is_latest:
                if st.button("Next ▶", key="next_round", use_container_width=True):
                    session_service.advance_to_next_round(session, session_name)
                    st.session_state.viewing_round_idx = len(session.round_history) - 1
                    st.rerun()
            else:
                if st.button("▶", key="next_round", use_container_width=True):
                    st.session_state.viewing_round_idx = view_idx + 1
                    st.rerun()

        # Resting players
        resting_names = [
            format_display_name(p, max_length=10)
            for p in sorted(record.resting_players)
            if p in session.player_pool  # exclude removed players
        ]
        if resting_names:
            st.info(f"**Resting:** {', '.join(resting_names)}")

        # Build locked pairs set for visual indicators
        locked_pairs_set: set[tuple[str, str]] = set()
        if session.is_doubles:
            required_partners = session.get_required_partners()
            for player, partners in required_partners.items():
                for partner in partners:
                    locked_pairs_set.add(tuple(sorted((player, partner))))

        # Render matches with auto-save
        render_round_matches(
            session, session_name, record, view_idx, locked_pairs_set
        )

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
    render_weights_section(session, session_name)
    render_submit_results(session, session_name)
    handle_session_termination(session, session_name)
