import streamlit as st
import pandas as pd
from utils import validate_session_setup, start_session
from session_logic import SessionManager, ClubNightSession

# --- Constants ---
DEFAULT_PLAYERS = ["P" + str(i) for i in range(1, 11)]
DEFAULT_NUM_COURTS = 2
DEFAULT_WEIGHTS = {'skill': 5, 'power': 2, 'pairing': 1}

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
    if 'player_list' not in st.session_state:
        st.session_state.player_list = DEFAULT_PLAYERS.copy()

    # Create the initial DataFrame for the editor
    player_ranks = range(1, len(st.session_state.player_list) + 1)
    st.session_state.editor_df = pd.DataFrame({
        "#": player_ranks,
        "Player Name": st.session_state.player_list,
    })

# --- Display the data editor ---
# The editor's state is now persistent in st.session_state.editor_df
edited_df = st.data_editor(
    st.session_state.editor_df,
    disabled=["#"],
    hide_index=True,
    num_rows="dynamic",
    use_container_width=True
)

# --- Add a button to commit the changes ---
if st.button("✅ Confirm Player List"):
    # First, update the session state with the current editor changes
    st.session_state.editor_df = edited_df
    
    # The 'edited_df' variable now reliably contains the user's changes
    final_players = edited_df["Player Name"].dropna().tolist()
    
    # Update the master player list and the editor's DataFrame
    st.session_state.player_list = final_players
    
    # Re-create the editor's DataFrame to update the '#' column correctly
    player_ranks = range(1, len(final_players) + 1)
    st.session_state.editor_df = pd.DataFrame({
        "#": player_ranks,
        "Player Name": final_players,
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

    weights = st.session_state.weights
    weights['skill'] = st.number_input("Skill Balance", min_value=1, value=weights['skill'], step=1)
    weights['power'] = st.number_input("Power Balance", min_value=1, value=weights['power'], step=1)
    weights['pairing'] = st.number_input("Pairing History", min_value=1, value=weights['pairing'], step=1)

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
    # Ensure player_list exists - if not, use the current editor data
    if 'player_list' not in st.session_state:
        if 'editor_df' in st.session_state:
            # Get player list from current editor state
            st.session_state.player_list = st.session_state.editor_df["Player Name"].dropna().tolist()
        else:
            # Fall back to default
            st.session_state.player_list = DEFAULT_PLAYERS.copy()
    
    player_ids = st.session_state.player_list
    
    # Validate first
    is_valid, error_message = validate_session_setup(player_ids, num_courts)
    
    if is_valid:
        # If validation passes, start the session
        start_session(player_ids, num_courts, st.session_state.weights)
    else:
        # If validation fails, show error
        st.error(error_message)
