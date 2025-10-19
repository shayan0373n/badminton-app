import os
import tempfile
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

import pandas as pd
import random
from session_logic import ClubNightSession, SessionManager, Player
from constants import DEFAULT_NUM_COURTS, DEFAULT_WEIGHTS, PLAYERS_PER_COURT

# Setup Constants
DEFAULT_PLAYERS_TABLE = {
    "P" + str(i): Player(name="P" + str(i), gender="M", pre_rating=2)
    for i in range(1, 11)
}

# Random words for default session names
RANDOM_WORDS = [
    "Phoenix", "Dragon", "Tiger", "Eagle", "Falcon", "Hawk", "Wolf", "Lion",
    "Thunder", "Lightning", "Storm", "Blaze", "Frost", "Shadow", "Star", "Moon",
    "Solar", "Cosmic", "Nova", "Meteor", "Comet", "Galaxy", "Nebula", "Aurora",
    "Titan", "Atlas", "Zeus", "Apollo", "Orion", "Neptune", "Mercury", "Venus"
]

def generate_session_name():
    """Generates a unique session name using a random word and timestamp."""
    from datetime import datetime
    word = random.choice(RANDOM_WORDS)
    timestamp = datetime.now().strftime("%m%d-%H%M")
    return f"{word}-{timestamp}"

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

def start_session(player_table, num_courts, weights, ff_power_penalty, mf_power_penalty, session_name):
    """Creates and starts a new badminton session."""
    session = ClubNightSession(
        players=player_table,
        num_courts=num_courts,
        weights=weights,
        ff_power_penalty=ff_power_penalty,
        mf_power_penalty=mf_power_penalty
    )
    session.prepare_round()
    
    SessionManager.save(session, session_name)
    st.session_state.session = session
    st.session_state.current_session_name = session_name
    
    st.switch_page("pages/2_Session.py")

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
                if st.button("▶️ Resume", key=f"resume_{session_name}", use_container_width=True):
                    session = SessionManager.load(session_name)
                    if session:
                        st.session_state.session = session
                        st.session_state.current_session_name = session_name
                        st.switch_page("pages/2_Session.py")
                    else:
                        st.error(f"Failed to load session '{session_name}'")
            with col3:
                if st.button("🗑️ Delete", key=f"delete_{session_name}", use_container_width=True):
                    SessionManager.clear(session_name)
                    st.rerun()
    
    st.divider()

# --- Main Setup UI ---
st.header("Session Setup")
st.subheader("1. Manage Players")
st.info("Add, edit, or remove players in the table, or upload a CSV file.")

# Initialize player table if not exists (do this early)
if 'player_table' not in st.session_state:
    st.session_state.player_table = DEFAULT_PLAYERS_TABLE.copy()

# Helper function to create editor DataFrame from player_table
def create_editor_dataframe(player_table):
    """Creates a DataFrame for the editor from player_table."""
    player_ranks = range(1, len(player_table) + 1)
    return pd.DataFrame({
        "#": player_ranks,
        "Player Name": [p.name for p in player_table.values()],
        "Gender": [p.gender for p in player_table.values()],
        "Pre-Rating": [p.pre_rating for p in player_table.values()],
    })

# Initialize the editor's DataFrame if it doesn't exist
if 'editor_df' not in st.session_state:
    st.session_state.editor_df = create_editor_dataframe(st.session_state.player_table)

# --- CSV Upload Logic ---
uploaded_file = st.file_uploader("Upload Players CSV", type=['csv'])
if uploaded_file is not None:
    # Only process if it's a new file (prevent re-processing on reruns)
    file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if 'last_uploaded_file_id' not in st.session_state or st.session_state.last_uploaded_file_id != file_id:
        st.session_state.last_uploaded_file_id = file_id
        try:
            # Read the uploaded CSV file
            new_players_df = pd.read_csv(uploaded_file)

            # --- Validation ---
            required_columns = ["Player Name", "Gender", "Pre-Rating"]
            if not all(col in new_players_df.columns for col in required_columns):
                st.error(f"CSV must contain the following columns: {', '.join(required_columns)}")
            else:
                # Drop rows with missing names
                new_players_df.dropna(subset=["Player Name"], inplace=True)

                # --- Data Processing ---
                # Ensure Pre-Rating is numeric
                new_players_df["Pre-Rating"] = pd.to_numeric(new_players_df["Pre-Rating"], errors='coerce').fillna(0).astype(int)
                # Create the player table from the CSV data
                player_table = {
                    row["Player Name"]: Player(
                        name=row["Player Name"],
                        gender=row["Gender"],
                        pre_rating=row["Pre-Rating"]
                    )
                    for _, row in new_players_df.iterrows()
                }

                # Update the session state
                st.session_state.player_table = player_table
                st.session_state.editor_df = create_editor_dataframe(player_table)
                
                st.success("Successfully loaded players from CSV!")

        except Exception as e:
            st.error(f"An error occurred while processing the CSV: {e}")

# If player_table was updated from a terminated session, refresh the editor
if 'player_table_updated' in st.session_state:
    st.session_state.editor_df = create_editor_dataframe(st.session_state.player_table)
    del st.session_state.player_table_updated

# Ensure editor_df is always a DataFrame before rendering
if not isinstance(st.session_state.editor_df, pd.DataFrame):
    st.session_state.editor_df = create_editor_dataframe(st.session_state.player_table)

# --- Display the data editor ---
# Use data_editor with a key to capture changes
edited_df = st.data_editor(
    st.session_state.editor_df,
    column_config={
        "Gender": st.column_config.SelectboxColumn(
            "Gender",
            help="Player's gender",
            options=["M", "F"],
            default="M",
            required=True,
        ),
        "Pre-Rating": st.column_config.NumberColumn(
            "Pre-Rating",
            help="Player's numerical rating (e.g., 1, 2, 4)",
            default=2,
            min_value=0,
            step=1,
            required=True,
        ),
    },
    disabled=["#"],
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True,
    key="player_editor"
)

# --- Add a button to commit the changes ---
if st.button("✅ Confirm Player List"):
    # Use the DataFrame returned by the data_editor
    current_df = edited_df.copy()
    current_df.dropna(subset=["Player Name"], inplace=True)
    
    # Ensure Pre-Rating is numeric
    current_df["Pre-Rating"] = pd.to_numeric(current_df["Pre-Rating"], errors='coerce').fillna(0).astype(int)
    
    final_players_table = {
        row["Player Name"]: Player(
            name=row["Player Name"],
            gender=row["Gender"],
            pre_rating=row["Pre-Rating"]
        )
        for _, row in current_df.iterrows()
    }

    # Update the master player list and the editor's DataFrame
    st.session_state.player_table = final_players_table
    st.session_state.editor_df = create_editor_dataframe(final_players_table)
    st.session_state.show_success = True

    st.rerun()
    
# Show success message if flag is set
if st.session_state.get('show_success', False):
    st.success("Player list saved!")
    # Clear the flag so message doesn't persist
    st.session_state.show_success = False

# --- Session Start Logic ---
st.subheader("2. Start New Session")

session_name = st.text_input("Session Name", placeholder="e.g., Monday Night, Weekend Game", key="new_session_name")

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
    if 'ff_power_penalty' not in st.session_state:
        st.session_state.ff_power_penalty = st.session_state.weights.get('ff_power_penalty', DEFAULT_WEIGHTS['ff_power_penalty'])
    if 'mf_power_penalty' not in st.session_state:
        st.session_state.mf_power_penalty = st.session_state.weights.get('mf_power_penalty', DEFAULT_WEIGHTS['mf_power_penalty'])

    # Let the widgets manage their own state via keys
    st.number_input("Skill Balance", min_value=0, step=1, key='skill_weight')
    st.number_input("Power Balance", min_value=0, step=1, key='power_weight')
    st.number_input("Pairing History", min_value=0, step=1, key='pairing_weight')
    st.number_input("FF Power Penalty", min_value=-10, max_value=0, step=1, key='ff_power_penalty', help="Penalty for FF pairs")
    st.number_input("MF Power Penalty", min_value=-10, max_value=0, step=1, key='mf_power_penalty', help="Penalty for MF pairs")

    # Update the central weights dictionary from the widget states
    st.session_state.weights['skill'] = st.session_state.skill_weight
    st.session_state.weights['power'] = st.session_state.power_weight
    st.session_state.weights['pairing'] = st.session_state.pairing_weight
    st.session_state.weights['ff_power_penalty'] = st.session_state.ff_power_penalty
    st.session_state.weights['mf_power_penalty'] = st.session_state.mf_power_penalty
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
    # Validate player_table
    if 'player_table' not in st.session_state or not st.session_state.player_table:
        st.error("Player list is empty. Please add players before starting.")
        st.stop()
    
    player_table = st.session_state.player_table
    
    # Generate default session name if none provided
    final_session_name = session_name.strip() if session_name and session_name.strip() else generate_session_name()
    
    # Check if session name already exists
    if final_session_name in SessionManager.list_sessions():
        st.error(f"A session named '{final_session_name}' already exists. Please choose a different name or delete the existing session.")
        st.stop()
    
    player_ids = list(player_table.keys())
    
    # Validate first
    is_valid, error_message = validate_session_setup(player_ids, num_courts)
    
    if is_valid:
        # If validation passes, start the session
        start_session(
            player_table,
            num_courts,
            st.session_state.weights,
            st.session_state.weights['ff_power_penalty'],
            st.session_state.weights['mf_power_penalty'],
            final_session_name
        )
    else:
        # If validation fails, show error
        st.error(error_message)
