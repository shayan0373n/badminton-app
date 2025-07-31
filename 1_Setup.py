import streamlit as st
import pandas as pd
from utils import Player, PreRating
from session_logic import ClubNightSession, SessionManager
from constants import DEFAULT_NUM_COURTS, DEFAULT_WEIGHTS, PLAYERS_PER_COURT

# Setup Constants
DEFAULT_PLAYERS_TABLE = {
    "P" + str(i): Player(name="P" + str(i), gender="M", pre_rating=PreRating.INTERMEDIATE)
    for i in range(1, 11)
}

def validate_session_setup(player_ids, num_courts):
    """Validates player list and court count. Returns (is_valid, error_message)."""
    if len(player_ids) != len(set(player_ids)):
        return False, "Error: Duplicate names found in the player list."
    elif not player_ids:
        return False, "Please add players to the list before starting."
    else:
        total_players = len(player_ids)
        players_on_court = num_courts * PLAYERS_PER_COURT
        rests_per_round = total_players - players_on_court
        if rests_per_round < 0:
            return False, f"Error: Not enough players ({total_players}) for {num_courts} courts."
        return True, None

def start_session(player_table, num_courts, weights, ff_power_penalty):
    """Creates and starts a new badminton session."""
    session = ClubNightSession(
        players=player_table,
        num_courts=num_courts,
        weights=weights,
        ff_power_penalty=ff_power_penalty
    )
    session.prepare_round()
    
    # Save the session object to file and to the Streamlit state
    SessionManager.save(session)
    st.session_state.session = session
    
    st.switch_page("pages/2_Session.py")

st.set_page_config(layout="wide", page_title="Badminton Setup")

# If a session is already running, switch to the session page automatically
if 'session' in st.session_state:
    st.switch_page("pages/2_Session.py")

st.title("🏸 Badminton Club Rotation")

# --- Resume Session Logic ---
session = SessionManager.load()
if session:
    st.subheader("An unfinished session was found.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Resume Last Session", use_container_width=True):
            st.session_state.session = session
            st.switch_page("pages/2_Session.py")
    with col2:
        if st.button("🗑️ Start a New Session", type="primary", use_container_width=True):
            SessionManager.clear()
            st.rerun()
    st.stop()

# --- Main Setup UI ---
st.header("Session Setup")
st.subheader("1. Manage Players")
st.info("Add, edit, or remove players in the table, then click 'Confirm Player List'.")

# Initialize the editor's state ONCE
if 'editor_df' not in st.session_state:
    # Use default player list if nothing is in session state yet
    if 'player_table' not in st.session_state:
        st.session_state.player_table = DEFAULT_PLAYERS_TABLE.copy()

    # Create the initial DataFrame for the editor
    player_table = st.session_state.player_table
    player_ranks = range(1, len(player_table) + 1)
    st.session_state.editor_df = pd.DataFrame({
        "#": player_ranks,
        "Player Name": [p.name for p in player_table.values()],
        "Gender": [p.gender for p in player_table.values()],
        "Pre-Rating": [p.pre_rating.value for p in player_table.values()],
    })

# --- Display the data editor ---
# The editor's state is now persistent in st.session_state.editor_df
edited_df = st.data_editor(
    st.session_state.editor_df,
    column_config={
        "Gender": st.column_config.SelectboxColumn(
            "Gender",
            help="Player's gender",
            options=["M", "F"],
            required=True,
        ),
        "Pre-Rating": st.column_config.SelectboxColumn(
            "Pre-Rating",
            help="Player's pre-defined rating",
            options=[r.value for r in PreRating],
            required=True,
        ),
    },
    disabled=["#"],
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True,
)

# --- Add a button to commit the changes ---
if st.button("✅ Confirm Player List"):
    # First, update the session state with the current editor changes
    st.session_state.editor_df = edited_df
    
    # The 'edited_df' variable now reliably contains the user's changes
    edited_df.dropna(subset=["Player Name"], inplace=True)
    
    final_players_table = {
        row["Player Name"]: Player(
            name=row["Player Name"],
            gender=row["Gender"],
            pre_rating=PreRating(row["Pre-Rating"])
        )
        for _, row in edited_df.iterrows()
    }

    # Update the master player list and the editor's DataFrame
    st.session_state.player_table = final_players_table
    
    # Re-create the editor's DataFrame to update the '#' column correctly
    player_ranks = range(1, len(final_players_table) + 1)
    st.session_state.editor_df = pd.DataFrame({
        "#": player_ranks,
        "Player Name": [p.name for p in final_players_table.values()],
        "Gender": [p.gender for p in final_players_table.values()],
        "Pre-Rating": [p.pre_rating.value for p in final_players_table.values()],
    })
    
    # Set a flag to show success message after rerun
    st.session_state.show_success = True
    # Rerun to show the refreshed and saved table immediately
    st.rerun()

# Show success message if flag is set
if st.session_state.get('show_success', False):
    st.success("Player list saved!")
    # Clear the flag so message doesn't persist
    st.session_state.show_success = False

# --- Session Start Logic ---
st.subheader("2. Start Session")

with st.sidebar:
    st.header("Optimizer Weights")
    st.info("Adjust the importance of different factors for creating matches.")
    
    if 'weights' not in st.session_state:
        st.session_state.weights = DEFAULT_WEIGHTS.copy()

    # Initialize individual weight keys if they don't exist
    if 'skill_weight' not in st.session_state:
        st.session_state.skill_weight = st.session_state.weights.get('skill', DEFAULT_WEIGHTS['skill'])
    if 'power_weight' not in st.session_state:
        st.session_state.power_weight = st.session_state.weights.get('power', DEFAULT_WEIGHTS['power'])
    if 'pairing_weight' not in st.session_state:
        st.session_state.pairing_weight = st.session_state.weights.get('pairing', DEFAULT_WEIGHTS['pairing'])
    # Initialize ff_power_penalty within the sidebar context, from weights or default
    if 'ff_power_penalty' not in st.session_state:
        st.session_state.ff_power_penalty = st.session_state.weights.get('ff_power_penalty', DEFAULT_WEIGHTS['ff_power_penalty'])

    # Let the widgets manage their own state via keys
    st.number_input("Skill Balance", min_value=0, step=1, key='skill_weight')
    st.number_input("Power Balance", min_value=0, step=1, key='power_weight')
    st.number_input("Pairing History", min_value=0, step=1, key='pairing_weight')
    st.number_input("FF Power Penalty", min_value=-10, max_value=0, step=1, key='ff_power_penalty', help="Penalty for FF pairs")

    # Update the central weights dictionary from the widget states
    st.session_state.weights['skill'] = st.session_state.skill_weight
    st.session_state.weights['power'] = st.session_state.power_weight
    st.session_state.weights['pairing'] = st.session_state.pairing_weight
    st.session_state.weights['ff_power_penalty'] = st.session_state.ff_power_penalty # Update ff_power_penalty in weights
    if 'gender' in st.session_state.weights:
        del st.session_state.weights['gender']

# Initialize persistent number of courts (survives session resets)
if 'num_courts_persistent' not in st.session_state:
    st.session_state.num_courts_persistent = DEFAULT_NUM_COURTS

# Initialize the widget key if it doesn't exist or restore from persistent value
if 'num_courts_input' not in st.session_state:
    st.session_state.num_courts_input = st.session_state.num_courts_persistent

num_courts = st.number_input(
    "Number of Courts Available", 
    min_value=1, 
    step=1,
    key="num_courts_input"
)

# Keep the persistent value in sync with the widget
st.session_state.num_courts_persistent = num_courts

if st.button("🚀 Start New Session", type="primary"):
    # Ensure player_table exists
    if 'player_table' not in st.session_state or not st.session_state.player_table:
        st.error("Player list is empty. Please confirm players before starting.")
        st.stop()

    player_table = st.session_state.player_table
    player_ids = list(player_table.keys())
    
    # Validate first
    is_valid, error_message = validate_session_setup(player_ids, num_courts)
    
    if is_valid:
        # If validation passes, start the session
        start_session(player_table, num_courts, st.session_state.weights, st.session_state.weights['ff_power_penalty'])
    else:
        # If validation fails, show error
        st.error(error_message)
