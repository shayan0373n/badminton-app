import streamlit as st
from session_logic import SessionManager

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

col1, col2 = st.columns(2)

with col1:
    st.header(f"Enter Results for Round {session.round_num}")

    # Resting players info
    st.info(f"**Resting:** {', '.join(session.resting_players)}")

    # Results form
    with st.form(key='results_form'):
        winners_by_court = {}
        if not session.current_round_matches:
             st.warning("No courts could be formed with the current number of active players.")
        else:
            cols = st.columns(len(session.current_round_matches))
            for i, match in enumerate(session.current_round_matches):
                with cols[i]:
                    st.markdown(f"**Court {match['court']}**")
                    team_A = match['team_1']
                    team_B = match['team_2']
                    team_A_names = f"{team_A[0]} & {team_A[1]}"
                    team_B_names = f"{team_B[0]} & {team_B[1]}"

                    winner_selection = st.radio("Select Winner", (team_A_names, team_B_names), key=f"court_{match['court']}")
                    
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
    standings = session.get_standings()
    st.dataframe(standings,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "_index": "Rank",
                        "0": "Player",
                        "1": "Score"
                    })

# --- Session Management in Sidebar ---
with st.sidebar:
    st.header("Manage Session")
    if st.button("⚠️ Terminate Session"):
        # Preserve the player list for the next session
        if 'session' in st.session_state:
            st.session_state.player_list = st.session_state.session.player_names
        
        SessionManager.clear()  # Clear the session state file
        
        # Clear only the session object, keeping player list and other settings
        if 'session' in st.session_state:
            del st.session_state['session']
            
        st.switch_page("1_Setup.py")
