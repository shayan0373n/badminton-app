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
from session_logic import ClubNightSession, SessionManager, Player
from constants import DEFAULT_NUM_COURTS, DEFAULT_WEIGHTS, PLAYERS_PER_COURT

# Setup Constants
DEFAULT_PLAYERS_TABLE = {
    "P" + str(i): Player(name="P" + str(i), gender="M", pre_rating=2)
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

def start_session(player_table, num_courts, weights, ff_power_penalty, mf_power_penalty):
    """Creates and starts a new badminton session."""
    session = ClubNightSession(
        players=player_table,
        num_courts=num_courts,
        weights=weights,
    ff_power_penalty=ff_power_penalty,
    mf_power_penalty=mf_power_penalty
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
st.info("Add, edit, or remove players in the table, or upload a CSV file.")

# --- CSV Upload Logic ---
uploaded_file = st.file_uploader("Upload Players CSV", type=['csv'])
if uploaded_file is not None:
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

            # Re-create the DataFrame for the editor to reflect the loaded data
            player_ranks = range(1, len(player_table) + 1)
            st.session_state.editor_df = pd.DataFrame({
                "#": player_ranks,
                "Player Name": [p.name for p in player_table.values()],
                "Gender": [p.gender for p in player_table.values()],
                "Pre-Rating": [p.pre_rating for p in player_table.values()],
            })
            
            st.success("Successfully loaded players from CSV!")

    except Exception as e:
        st.error(f"An error occurred while processing the CSV: {e}")

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
        "Pre-Rating": [p.pre_rating for p in player_table.values()],
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
        "Pre-Rating": st.column_config.NumberColumn(
            "Pre-Rating",
            help="Player's numerical rating (e.g., 1, 2, 4)",
            min_value=0,
            step=1,
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
    
    # Ensure Pre-Rating is numeric
    edited_df["Pre-Rating"] = pd.to_numeric(edited_df["Pre-Rating"], errors='coerce').fillna(0).astype(int)
    
    final_players_table = {
        row["Player Name"]: Player(
            name=row["Player Name"],
            gender=row["Gender"],
            pre_rating=row["Pre-Rating"]
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
        "Pre-Rating": [p.pre_rating for p in final_players_table.values()],
    })
    
    # Set a flag to show success message after rerun
    st.session_state.show_success = True
    
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
    st.session_state.weights['ff_power_penalty'] = st.session_state.ff_power_penalty # Update ff_power_penalty in weights
    st.session_state.weights['mf_power_penalty'] = st.session_state.mf_power_penalty # Update mf_power_penalty in weights
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
        start_session(
            player_table,
            num_courts,
            st.session_state.weights,
            st.session_state.weights['ff_power_penalty'],
            st.session_state.weights['mf_power_penalty']
        )
    else:
        # If validation fails, show error
        st.error(error_message)
