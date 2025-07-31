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
if 'session' not in st.session_state:
    session = SessionManager.load()
    if session:
        st.session_state.session = session
    else:
        # If loading fails or there's no session file, go back to the setup page.
        st.error("No active session found. Please start a new one.")
        st.switch_page("1_Setup.py")

# --- Main App Display ---
session = st.session_state.session
st.title("🏸 Current Round")

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
                        else:
                            winners_by_court[match['court']] = team_B
    
        submitted = st.form_submit_button("✅ Confirm Results & Prepare Next Round")
        if submitted:
            if winners_by_court:
                session.finalize_round(winners_by_court)
                session.prepare_round()
                SessionManager.save(session)  # Save the updated session state
                st.rerun()
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
    if st.button("⚠️ Terminate Session"):
        # Preserve the player table for the next session
        if 'session' in st.session_state:
            st.session_state.player_table = st.session_state.session.player_pool
        
        SessionManager.clear()  # Clear the session state file
        
        # Clear only the session object, keeping player list and other settings
        if 'session' in st.session_state:
            del st.session_state['session']
            
        st.switch_page("1_Setup.py")
