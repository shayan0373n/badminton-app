import streamlit as st
import os
import pickle
from session_logic import BadmintonSession

# --- App Configuration ---
st.set_page_config(layout="wide", page_title="Badminton Setup")
STATE_FILE = "session_state.pkl"

# --- Helper Functions ---
def save_state():
    """Saves the entire session object to a file."""
    if 'session' in st.session_state:
        print("Saving session state to file...")
        with open(STATE_FILE, "wb") as f:
            pickle.dump(st.session_state.session, f)

def add_player_callback():
    """Callback to add a new player to the session."""
    new_player = st.session_state.new_player_input.strip()
    if new_player and new_player not in st.session_state.player_list:
        st.session_state.player_list.append(new_player)
        st.session_state.new_player_input = "" # Clear input field

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
st.header("Session Setup")
st.subheader("1. Manage Players")

if 'player_list' not in st.session_state:
    st.session_state.player_list = ["P" + str(i) for i in range(1, 11)]  # Default players P1 to P10

st.text_input("New Player Name", key="new_player_input", on_change=add_player_callback)
st.button("Add Player", on_click=add_player_callback)

st.subheader("Initial Player Ranking")
for i, player_name in enumerate(st.session_state.player_list):
    name_col, buttons_col = st.columns([3, 1], vertical_alignment="center")
    with name_col:
        st.text(f"{i+1}. {player_name}")
    with buttons_col:
        up_col, down_col, del_col = st.columns(3, gap="small")
        with up_col:
            if st.button("🔼", key=f"up_{i}", use_container_width=True, disabled=(i==0)):
                st.session_state.player_list.insert(i-1, st.session_state.player_list.pop(i))
                st.rerun()
        with down_col:
            if st.button("🔽", key=f"down_{i}", use_container_width=True, disabled=(i==len(st.session_state.player_list)-1)):
                st.session_state.player_list.insert(i+1, st.session_state.player_list.pop(i))
                st.rerun()
        with del_col:
            if st.button("🗑️", key=f"del_{i}", use_container_width=True):
                st.session_state.player_list.pop(i)
                st.rerun()

st.subheader("2. Start Session")
num_courts = st.number_input("Number of Courts Available", min_value=1, value=2, step=1)

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
            
            # --- FIX ---
            # Save the state immediately after creating the first round
            save_state()
            
            st.switch_page("pages/2_Session.py")
    else:
        st.error("Please add players to the list before starting.")