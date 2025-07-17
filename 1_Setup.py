import streamlit as st
import os
import pickle
import pandas as pd  # Import pandas for the data editor
from session_logic import BadmintonSession

# --- App Configuration ---
st.set_page_config(layout="wide", page_title="Badminton Setup")
STATE_FILE = "session_state.pkl"

# --- Helper Functions ---
def save_state():
    """Saves the entire session object to a file."""
    if 'session' in st.session_state:
        with open(STATE_FILE, "wb") as f:
            pickle.dump(st.session_state.session, f)

# 'add_player_callback' is no longer needed with st.data_editor

# If a session is already running, switch to the session page automatically
if 'session' in st.session_state:
    st.switch_page("pages/2_Session.py")

st.title("🏸 Badminton Club Rotation")

# --- Resume Session Logic ---
if os.path.exists(STATE_FILE):
    st.subheader("An unfinished session was found.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Resume Last Session", use_container_width=True):
            try:
                with open(STATE_FILE, "rb") as f:
                    st.session_state.session = pickle.load(f)
                st.switch_page("pages/2_Session.py")
            except Exception as e:
                st.error(f"Could not load session file: {e}")
    with col2:
        if st.button("🗑️ Start a New Session", type="primary", use_container_width=True):
            os.remove(STATE_FILE)
            st.rerun()
    st.stop()

# --- Main Setup UI ---
# --- Main Setup UI ---
st.header("Session Setup")
st.subheader("1. Manage Players")
st.info("Add, edit, or remove players in the table, then click 'Confirm Player List'.")

# Initialize the editor's state ONCE
if 'editor_df' not in st.session_state:
    # Use default player list if nothing is in session state yet
    if 'player_list' not in st.session_state:
        st.session_state.player_list = ["P" + str(i) for i in range(1, 13)]

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
    
    st.success("Player list saved!")
    # Rerun to show the refreshed and saved table immediately
    st.rerun()

# --- Session Start Logic ---
st.subheader("2. Start Session")
num_courts = st.number_input("Number of Courts Available", min_value=1, value=4, step=1)

if st.button("🚀 Start New Session", type="primary"):
    player_ids = st.session_state.player_list
    if len(player_ids) != len(set(player_ids)):
        st.error("Error: Duplicate names found in the player list.")
    elif player_ids:
        total_players = len(player_ids)
        players_on_court = num_courts * 4
        rests_per_round = total_players - players_on_court
        if rests_per_round < 0:
            st.error(f"Error: Not enough players ({total_players}) for {num_courts} courts.")
        else:
            st.session_state.session = BadmintonSession(
                player_ids=player_ids, 
                rests_per_round=rests_per_round
            )
            st.session_state.session.prepare_round()
            save_state()
            st.switch_page("pages/2_Session.py")
    else:
        st.error("Please add players to the list before starting.")