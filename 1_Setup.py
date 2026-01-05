import logging
import os
import tempfile

# Configure logging FIRST, before importing other modules that use loggers
from logger import setup_logging

# App log level from environment variable (default: INFO)
# Set LOG_LEVEL=DEBUG for verbose output (only affects app.* loggers)
_log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
setup_logging(app_level=_log_level)

import streamlit as st

if st.secrets.get("GUROBI_LIC"):
    # Define a fixed path for the license file in the system's temp directory
    temp_dir = tempfile.gettempdir()
    license_path = os.path.join(temp_dir, "gurobi.lic")

    # Write the license file only if it doesn't already exist
    if not os.path.exists(license_path):
        with open(license_path, "w") as f:
            f.write(st.secrets["GUROBI_LIC"])

    # Set the environment variable to point to the license file
    os.environ["GRB_LICENSE_FILE"] = license_path

import random
from datetime import datetime
from typing import Any

import pandas as pd

from constants import (
    DEFAULT_IS_DOUBLES,
    DEFAULT_NUM_COURTS,
    DEFAULT_WEIGHTS,
    PAGE_SESSION,
    PLAYERS_PER_COURT_DOUBLES,
    PLAYERS_PER_COURT_SINGLES,
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
)
from database import PlayerDB, SessionDB
from session_logic import ClubNightSession, SessionManager, Player
from app_types import Gender

# Setup Constants
DEFAULT_PLAYERS_TABLE = {
    f"P{i}": Player(name=f"P{i}", gender=Gender.MALE, mu=TTT_DEFAULT_MU)
    for i in range(1, 11)
}

# Random words for default session names
RANDOM_WORDS = [
    "Phoenix",
    "Dragon",
    "Tiger",
    "Eagle",
    "Falcon",
    "Hawk",
    "Wolf",
    "Lion",
    "Thunder",
    "Lightning",
    "Storm",
    "Blaze",
    "Frost",
    "Shadow",
    "Star",
    "Moon",
    "Solar",
    "Cosmic",
    "Nova",
    "Meteor",
    "Comet",
    "Galaxy",
    "Nebula",
    "Aurora",
    "Titan",
    "Atlas",
    "Zeus",
    "Apollo",
    "Orion",
    "Neptune",
    "Mercury",
    "Venus",
]


def generate_session_name() -> str:
    """Generates a unique session name using a random word and timestamp."""
    word = random.choice(RANDOM_WORDS)
    timestamp = datetime.now().strftime("%m%d-%H%M")
    return f"{word}-{timestamp}"


# Helper function to create editor DataFrame from player_table
def create_editor_dataframe(
    player_table: dict[str, Player], is_doubles: bool = DEFAULT_IS_DOUBLES
) -> pd.DataFrame:
    """Creates a DataFrame for the editor from player_table."""
    player_ranks = range(1, len(player_table) + 1)
    df_data = {
        "#": player_ranks,
        "Player Name": [p.name for p in player_table.values()],
        "Gender": [p.gender for p in player_table.values()],
        "Prior Mu": [p.prior_mu for p in player_table.values()],
        "Mu": [p.mu for p in player_table.values()],
        "Sigma": [p.sigma for p in player_table.values()],
        "Rating": [p.conservative_rating for p in player_table.values()],
        "database_id": [p.database_id for p in player_table.values()],  # Track DB ID
    }
    # Only add Team Name column for Doubles mode
    if is_doubles:
        df_data["Team Name"] = [
            p.team_name if hasattr(p, "team_name") else ""
            for p in player_table.values()
        ]
    return pd.DataFrame(df_data)


def validate_session_setup(
    player_ids: list, num_courts: int
) -> tuple[bool, str | None]:
    """Validates player list and court count. Returns (is_valid, error_message)."""
    if len(player_ids) != len(set(player_ids)):
        return False, "Error: Duplicate names found in the player list."

    if not player_ids:
        return False, "Please add players to the list before starting."

    # Allow starting even if there are more courts than players; extra courts will sit idle
    return True, None


def start_session(
    player_table: dict[str, Player],
    num_courts: int,
    weights: dict[str, Any],
    female_female_team_penalty: float,
    mixed_gender_team_penalty: float,
    female_singles_penalty: float,
    session_name: str,
    is_doubles: bool,
    is_recorded: bool = True,
) -> None:
    """Creates and starts a new badminton session.

    Raises:
        Stops execution via st.stop() if database session cannot be created.
    """
    # Create session record in Supabase only if recording is enabled
    database_id = None
    if is_recorded:
        try:
            database_id = SessionDB.create_session(session_name, is_doubles)
        except Exception as e:
            st.error(f"Could not create session in database: {e}")
            st.stop()

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
    session.prepare_round()

    SessionManager.save(session, session_name)
    st.session_state.session = session
    st.session_state.current_session_name = session_name

    st.switch_page(f"pages/{PAGE_SESSION}")


st.set_page_config(layout="wide", page_title="Badminton Setup")

st.title("🏸 Badminton Club Rotation")

# --- Session Selection Logic ---
existing_sessions = SessionManager.list_sessions()

if existing_sessions:
    st.subheader("Active Sessions")
    for session_name in existing_sessions:
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"### {session_name}")
            with col2:
                if st.button("▶️ Resume", key=f"resume_{session_name}", width="stretch"):
                    session = SessionManager.load(session_name)
                    if session:
                        st.session_state.session = session
                        st.session_state.current_session_name = session_name
                        st.switch_page(f"pages/{PAGE_SESSION}")
                    else:
                        st.error(f"Failed to load session '{session_name}'")
            with col3:
                if st.button("🗑️ Delete", key=f"delete_{session_name}", width="stretch"):
                    SessionManager.clear(session_name)
                    st.rerun()

    st.divider()

# --- Main Setup UI ---
st.header("Session Setup")

# Initialize master registry if not exists
# Initialize master registry if not exists or requested to update
should_refresh_players = st.session_state.get("player_table_updated", False)

if "master_registry" not in st.session_state or should_refresh_players:
    try:
        st.session_state.master_registry = PlayerDB.get_all_players()
    except Exception as e:
        st.warning(f"Could not connect to Supabase: {e}")
        if "master_registry" not in st.session_state:
            st.session_state.master_registry = {}

# Sync session_player_selection if needed (re-sync from player_table when returning from session)
# Ensure persistent state exists
if "session_player_selection" not in st.session_state:
    st.session_state.session_player_selection = []

# Handle restoration from session termination
if should_refresh_players and "player_table" in st.session_state:
    # Filter to ensure we only select players currently in the registry
    valid_keys = [
        k
        for k in st.session_state.player_table.keys()
        if k in st.session_state.master_registry
    ]
    st.session_state.session_player_selection = valid_keys

# Now satisfied, delete the flag
if "player_table_updated" in st.session_state:
    del st.session_state["player_table_updated"]

tab1, tab2 = st.tabs(["👥 Session Players", "🗃️ Member Registry"])

with tab2:
    st.subheader("Manage Member Registry")
    st.info("This is your master database. Add new members or update ratings here.")

    # Create DF for registry
    registry_df = create_editor_dataframe(st.session_state.master_registry)

    # Column configuration for registry
    reg_column_config = {
        "Gender": st.column_config.SelectboxColumn(
            "Gender", options=["M", "F"], default="M", required=True
        ),
        "Prior Mu": st.column_config.NumberColumn(
            "Prior Mu",
            help="Initial skill estimate (18=weak, 25=avg, 32=strong). Edit this!",
            default=TTT_DEFAULT_MU,
            min_value=10.0,
            max_value=40.0,
            step=1.0,
            format="%.1f",
            required=True,
        ),
        "Mu": st.column_config.NumberColumn(
            "Mu",
            help="Current skill (computed by TTT from match history)",
            format="%.1f",
        ),
        "Sigma": st.column_config.NumberColumn(
            "Sigma",
            help="Uncertainty (computed by TTT)",
            format="%.2f",
        ),
        "Rating": st.column_config.NumberColumn(
            "Rating",
            help="Conservative skill rating (mu - 3*sigma)",
            format="%.1f",
        ),
        "database_id": None,  # Hide from user - internal tracking only
    }

    edited_reg_df = st.data_editor(
        registry_df,
        column_config=reg_column_config,
        disabled=[
            "#",
            "Mu",
            "Sigma",
            "Rating",
            "database_id",
        ],  # Only Prior Mu is editable (besides Name/Gender)
        hide_index=True,
        num_rows="dynamic",
        width="stretch",
        key="registry_editor",
    )

    if st.button("💾 Save Registry to Cloud", type="secondary"):
        # Process and save
        new_registry = {}
        for _, row in edited_reg_df.dropna(subset=["Player Name"]).iterrows():
            # Preserve database_id if it exists (for existing players)
            db_id = row.get("database_id")
            # Handle NaN values - convert to None
            if pd.isna(db_id):
                db_id = None
            else:
                db_id = int(db_id)

            new_registry[row["Player Name"]] = Player(
                name=row["Player Name"],
                gender=Gender(row["Gender"]),
                prior_mu=float(row["Prior Mu"]),
                prior_sigma=TTT_DEFAULT_SIGMA,  # Fixed for now
                mu=float(row["Mu"]),
                sigma=float(row["Sigma"]),
                database_id=db_id,  # Preserve DB ID for proper updates
            )

        try:
            PlayerDB.upsert_players(new_registry)
            st.session_state.master_registry = new_registry
            st.success("Registry saved to Supabase!")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save registry: {e}")

with tab1:
    st.subheader("Select Session Players")

    all_member_names = sorted(list(st.session_state.master_registry.keys()))

    # Use multiselect to pick from registry with stable key-based state
    selected_names = st.multiselect(
        "Who is playing in this session?",
        options=all_member_names,
        key="session_player_selection",
        help="Start typing to search for existing members",
    )

    st.divider()

    if selected_names:
        st.markdown(f"**{len(selected_names)} players selected**")

        # Build the session player table from registry
        session_players = {
            name: st.session_state.master_registry[name] for name in selected_names
        }

        # If Doubles, allow setting temporary team names for this session
        if st.session_state.get("is_doubles_persistent", DEFAULT_IS_DOUBLES):
            st.write("### (Optional) Pair Fixed Teams")
            st.caption(
                "Enter a matching name for two players to keep them together in this session."
            )

            # Simple editor for team names only for selected players
            player_ranks = range(1, len(session_players) + 1)
            temp_team_df = pd.DataFrame(
                {
                    "Player": [p.name for p in session_players.values()],
                    "Team Name": [""] * len(session_players),
                }
            )

            edited_teams = st.data_editor(
                temp_team_df,
                hide_index=True,
                width="stretch",
                key="session_team_editor",
            )

            # Update team names in our temporary session object
            for _, row in edited_teams.iterrows():
                if row["Player"] in session_players:
                    session_players[row["Player"]].team_name = row["Team Name"]

        # Store in session state for the 'Start' button below
        st.session_state.player_table = session_players
    else:
        st.warning("Select at least one player to start.")
        st.session_state.player_table = {}

st.divider()


# Initialize the editor's DataFrame if it doesn't exist
if "editor_df" not in st.session_state:
    # Need to get is_doubles early, use default if not set
    current_is_doubles = st.session_state.get(
        "is_doubles_persistent", DEFAULT_IS_DOUBLES
    )
    st.session_state.editor_df = create_editor_dataframe(
        st.session_state.player_table, current_is_doubles
    )

# Note: Confirm button is removed in favor of Tab management

# --- Session Start Logic ---
st.subheader("2. Start New Session")

session_name = st.text_input(
    "Session Name",
    placeholder="e.g., Monday Night, Weekend Game",
    key="new_session_name",
)

with st.sidebar:
    st.header("Optimizer Weights")
    st.info("Adjust the importance of different factors for creating matches.")

    if "weights" not in st.session_state:
        st.session_state.weights = DEFAULT_WEIGHTS.copy()

    # Initialize individual weight keys if they don't exist
    if "skill_weight" not in st.session_state:
        st.session_state.skill_weight = st.session_state.weights["skill"]
    if "power_weight" not in st.session_state:
        st.session_state.power_weight = st.session_state.weights["power"]
    if "pairing_weight" not in st.session_state:
        st.session_state.pairing_weight = st.session_state.weights["pairing"]
    if "female_female_team_penalty" not in st.session_state:
        st.session_state.female_female_team_penalty = st.session_state.weights[
            "female_female_team_penalty"
        ]
    if "mixed_gender_team_penalty" not in st.session_state:
        st.session_state.mixed_gender_team_penalty = st.session_state.weights[
            "mixed_gender_team_penalty"
        ]
    if "female_singles_penalty" not in st.session_state:
        st.session_state.female_singles_penalty = st.session_state.weights[
            "female_singles_penalty"
        ]

    # Let the widgets manage their own state via keys
    st.number_input("Skill Balance", min_value=0, step=1, key="skill_weight")
    st.number_input("Power Balance", min_value=0, step=1, key="power_weight")
    st.number_input("Pairing History", min_value=0, step=1, key="pairing_weight")
    st.number_input(
        "FF Team Penalty",
        min_value=-10,
        max_value=0,
        step=1,
        key="female_female_team_penalty",
        help="Penalty for female-female teams (doubles)",
    )
    st.number_input(
        "MF Team Penalty",
        min_value=-10,
        max_value=0,
        step=1,
        key="mixed_gender_team_penalty",
        help="Penalty for mixed-gender teams (doubles)",
    )
    st.number_input(
        "Female Singles Penalty",
        min_value=-10,
        max_value=0,
        step=1,
        key="female_singles_penalty",
        help="Penalty for female players in singles mode",
    )

    # Update the central weights dictionary from the widget states
    st.session_state.weights["skill"] = st.session_state.skill_weight
    st.session_state.weights["power"] = st.session_state.power_weight
    st.session_state.weights["pairing"] = st.session_state.pairing_weight
    st.session_state.weights["female_female_team_penalty"] = (
        st.session_state.female_female_team_penalty
    )
    st.session_state.weights["mixed_gender_team_penalty"] = (
        st.session_state.mixed_gender_team_penalty
    )
    st.session_state.weights["female_singles_penalty"] = (
        st.session_state.female_singles_penalty
    )

# Initialize persistent game mode (is_doubles boolean)
if "is_doubles_persistent" not in st.session_state:
    st.session_state.is_doubles_persistent = DEFAULT_IS_DOUBLES

is_doubles = st.toggle(
    "Doubles Mode",
    value=st.session_state.is_doubles_persistent,
    help="Enable for 4-player doubles, disable for 2-player singles",
)

# Detect game mode change and refresh editor
if st.session_state.is_doubles_persistent != is_doubles:
    st.session_state.is_doubles_persistent = is_doubles
    # Refresh the editor dataframe to add/remove Team Name column
    st.session_state.editor_df = create_editor_dataframe(
        st.session_state.player_table, is_doubles
    )
    st.rerun()

# Initialize persistent number of courts (survives session resets)
if "num_courts_persistent" not in st.session_state:
    st.session_state.num_courts_persistent = DEFAULT_NUM_COURTS

# Initialize the widget key if it doesn't exist or restore from persistent value
if "num_courts_input" not in st.session_state:
    st.session_state.num_courts_input = st.session_state.num_courts_persistent

num_courts = st.number_input(
    "Number of Courts Available", min_value=1, step=1, key="num_courts_input"
)

# Keep the persistent value in sync with the widget
st.session_state.num_courts_persistent = num_courts

# Initialize is_recorded persistent state
if "is_recorded_persistent" not in st.session_state:
    st.session_state.is_recorded_persistent = True

is_recorded = st.checkbox(
    "Record to Dataset",
    value=st.session_state.is_recorded_persistent,
    help="When enabled, session matches are saved to the database for rating calculations",
)
st.session_state.is_recorded_persistent = is_recorded

if st.button("🚀 Start New Session", type="primary"):
    # Validate player_table
    if "player_table" not in st.session_state or not st.session_state.player_table:
        st.error("Player list is empty. Please add players before starting.")
        st.stop()

    player_table = st.session_state.player_table

    # Generate default session name if none provided
    final_session_name = (
        session_name.strip()
        if session_name and session_name.strip()
        else generate_session_name()
    )

    # Check if session name already exists
    if final_session_name in SessionManager.list_sessions():
        st.error(
            f"A session named '{final_session_name}' already exists. Please choose a different name or delete the existing session."
        )
        st.stop()

    player_ids = list(player_table.keys())

    # Validate first
    is_valid, error_message = validate_session_setup(player_ids, num_courts)

    # Provide a heads-up if there are more courts than can be filled
    players_per_court = (
        PLAYERS_PER_COURT_DOUBLES if is_doubles else PLAYERS_PER_COURT_SINGLES
    )
    game_mode_str = "Doubles" if is_doubles else "Singles"
    total_players = len(player_ids)
    possible_courts = total_players // players_per_court
    if num_courts > possible_courts:
        st.info(
            f"Only {possible_courts} court(s) can be filled with {total_players} players in {game_mode_str} mode. "
            "Extra courts will remain idle until more players join."
        )

    if is_valid:
        # If validation passes, start the session
        start_session(
            player_table,
            num_courts,
            st.session_state.weights,
            st.session_state.weights["female_female_team_penalty"],
            st.session_state.weights["mixed_gender_team_penalty"],
            st.session_state.weights["female_singles_penalty"],
            final_session_name,
            is_doubles,
            is_recorded,
        )
    else:
        # If validation fails, show error
        st.error(error_message)
