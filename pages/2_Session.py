import streamlit as st
from session_logic import SessionManager
import os
import pandas as pd

def inject_css(file_path: str):
    """Injects custom CSS from the specified file path."""
    try:
        with open(file_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"CSS file not found at {file_path}. Make sure it's in the root directory.")

st.set_page_config(
    initial_sidebar_state="collapsed",
    layout="wide"
)

inject_css("styles.css")

# --- Page Entry Logic ---
# If the session object is lost (e.g., page reload), try to load it from the file.
if 'session' not in st.session_state or 'current_session_name' not in st.session_state:
    st.error("No active session found. Please start or resume a session.")
    st.switch_page("1_Setup.py")

# --- Main App Display ---
session = st.session_state.session
session_name = st.session_state.current_session_name
st.title(f"🏸 {session_name}")

col1, col2 = st.columns([2, 1])

with col1:
    st.header(f"Select Winners for Round {session.round_num}")

    # Resting players info
    st.info(f"**Resting:** {', '.join(session.resting_players)}")

    # Results form
    with st.form(key='results_form'):
        winners_by_court = {}
        if not session.current_round_matches:
             st.warning("No courts could be formed with the current number of active players.")
        else:
            for i, match in enumerate(session.current_round_matches):
                with st.container(border=True): # Wrap each match in a container
                    cols = st.columns([1, 3], vertical_alignment="center")
                    with cols[0]:
                        st.markdown(f"#### Court {match['court']}")
                    with cols[1]:
                        team_A = match['team_1']
                        team_B = match['team_2']
                        team_A_names = f"{team_A[0]} -- {team_A[1]}"
                        team_B_names = f"{team_B[0]} -- {team_B[1]}"
                        winner_selection = st.segmented_control(
                            "Select Winner", 
                            (team_A_names, team_B_names), 
                            key=f"court_{match['court']}",
                            label_visibility="collapsed"
                        )
                        if winner_selection == team_A_names:
                            winners_by_court[match['court']] = team_A
                        elif winner_selection == team_B_names:
                            winners_by_court[match['court']] = team_B
                        else:
                            winners_by_court[match['court']] = None
    
        submitted = st.form_submit_button("✅ Confirm Results")
        if submitted:
            if winners_by_court:
                if all(v is not None for v in winners_by_court.values()):
                    session.finalize_round(winners_by_court)
                    session.prepare_round()
                    SessionManager.save(session, session_name)  # Save the updated session state
                    st.rerun()
                else:
                    st.warning("Please select a winner for each court before submitting.")
            else:
                st.warning("Cannot process results as no courts were available.")

with col2:
    st.header("Current Standings")
    standings_data = session.get_standings()
    
    # Create a DataFrame for better display control
    if standings_data:
        df_standings = pd.DataFrame(standings_data, columns=["Player", "Earned Score"])
        df_standings.index += 1  # Start rank from 1
    else:
        df_standings = pd.DataFrame(columns=["Player", "Earned Score"])

    st.dataframe(df_standings, use_container_width=True)

# --- Session Management in Sidebar ---
with st.sidebar:
    st.header("Manage Session")
    with st.expander("➕ Add Player", expanded=False):
        new_name = st.text_input("Player Name", key="mid_add_name")
        new_gender = st.selectbox("Gender", options=["M", "F"], key="mid_add_gender")
        new_pre = st.number_input("Pre-Rating", min_value=0, step=1, value=1, key="mid_add_pre")
        if st.button("Add Player Now", key="mid_add_btn"):
            if not new_name.strip():
                st.warning("Please enter a player name.")
            else:
                added = session.add_player(new_name.strip(), new_gender, int(new_pre))
                if added:
                    SessionManager.save(session, session_name)
                    st.success(f"Added {new_name}: resting this round (earns 0.5) and queued for next round with average earned score.")
                    st.rerun()
                else:
                    st.warning("A player with that name already exists.")
    if st.button("⚠️ Terminate Session"):
        # Preserve the player table and session parameters for the next session
        if 'session' in st.session_state:
            st.session_state.player_table = st.session_state.session.player_pool
            st.session_state.player_table_updated = True  # Flag to refresh editor
            
            # Preserve session parameters
            st.session_state.num_courts_persistent = st.session_state.session.num_courts
            st.session_state.weights = st.session_state.session.weights.copy()
            st.session_state.skill_weight = st.session_state.weights.get('skill', 1.0)
            st.session_state.power_weight = st.session_state.weights.get('power', 1.0)
            st.session_state.pairing_weight = st.session_state.weights.get('pairing', 1.0)
            st.session_state.ff_power_penalty = st.session_state.session.ff_power_penalty
            st.session_state.mf_power_penalty = st.session_state.session.mf_power_penalty
        
        SessionManager.clear(session_name)  # Clear the session state file
        
        # Clear session objects from state
        if 'session' in st.session_state:
            del st.session_state['session']
        if 'current_session_name' in st.session_state:
            del st.session_state['current_session_name']
            
        st.switch_page("1_Setup.py")
