import streamlit as st
import os
from session_logic import BadmintonSession

# --- App Configuration ---
st.set_page_config(layout="wide", page_title="Badminton Setup")

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
st.header("Session Setup")

# --- Player Management ---
st.subheader("1. Manage Players")

# Initialize the player list in the session state if it doesn't exist
if 'player_list' not in st.session_state:
    st.session_state.player_list = ["Shayan", "Tara"]

# Add player input
st.text_input("New Player Name", key="new_player_input", on_change=add_player_callback)
st.button("Add Player", on_click=add_player_callback)

# Display and manage the list of players
st.subheader("Initial Player Ranking")
for i, player_name in enumerate(st.session_state.player_list):
    name_col, buttons_col = st.columns([1, 3], vertical_alignment="center", gap=None)
    
    with name_col:
        st.markdown(f"**{i+1}. {player_name}**")
    
    with buttons_col:
        up_col, down_col, del_col = st.columns(3, gap=None)
        
        with up_col:
            # Disable 'Up' button for the first item
            if st.button("🔼", key=f"up_{i}", use_container_width=False, disabled=(i==0)):
                st.session_state.player_list.insert(i-1, st.session_state.player_list.pop(i))
                st.rerun()

        with down_col:
            # Disable 'Down' button for the last item
            if st.button("🔽", key=f"down_{i}", use_container_width=False, disabled=(i==len(st.session_state.player_list)-1)):
                st.session_state.player_list.insert(i+1, st.session_state.player_list.pop(i))
                st.rerun()

        with del_col:
            if st.button("🗑️", key=f"del_{i}", use_container_width=False):
                st.session_state.player_list.pop(i)
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
            
            # Switch to the session page
            st.switch_page("pages/2_Session.py")
    else:
        st.error("Please add players to the list before starting.")