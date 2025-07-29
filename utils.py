# --- App Configuration ---
import streamlit as st
from session_logic import ClubNightSession, SessionManager

PLAYERS_PER_COURT = 4

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

def start_session(player_ids, num_courts, weights):
    """Creates and starts a new badminton session."""
    session = ClubNightSession(player_names=player_ids, num_courts=num_courts, weights=weights)
    session.prepare_round()
    
    # Save the session object to file and to the Streamlit state
    SessionManager.save(session)
    st.session_state.session = session
    
    st.switch_page("pages/2_Session.py")
