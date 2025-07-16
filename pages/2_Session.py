import streamlit as st
import pickle
import os

STATE_FILE = "session_state.pkl"

def save_state():
    """Saves the entire session object to a file."""
    if 'session' in st.session_state:
        with open(STATE_FILE, "wb") as f:
            pickle.dump(st.session_state.session, f)

# --- Page Entry Logic ---
# If session state is lost (e.g., page reload), try to load from file.
if 'session' not in st.session_state:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "rb") as f:
                st.session_state.session = pickle.load(f)
        except (pickle.UnpicklingError, EOFError):
            st.error("Could not load saved session. Please start a new one.")
            # If loading fails, clear any corrupted file and go back to setup
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            st.switch_page("1_Setup.py")
    else:
        # If there's no session and no file, go back to setup.
        st.switch_page("1_Setup.py")

# --- Main App Display ---
session = st.session_state.session
st.title("🏸 Current Round")
st.header(f"Enter Results for Round {session.round_num}")

# Resting players info
resting_ids = [p['id'] for p in session.resting_players]
st.info(f"**Resting:** {', '.join(resting_ids)}")

# Results form
with st.form(key='results_form'):
    all_selections = []
    if not session.courts:
         st.warning("No courts could be formed with the current number of active players.")
    else:
        cols = st.columns(len(session.courts))
        for i, court_players in enumerate(cols):
            with court_players:
                st.markdown(f"**Court {i+1}**")
                team_A_players = [session.courts[i][0], session.courts[i][3]]
                team_B_players = [session.courts[i][1], session.courts[i][2]]
                team_A_names = f"{team_A_players[0]['id']} & {team_A_players[1]['id']}"
                team_B_names = f"{team_B_players[0]['id']} & {team_B_players[1]['id']}"

                winner_selection = st.radio("Select Winner", (team_A_names, team_B_names), key=f'court_{i}')
                
                if winner_selection == team_A_names:
                    all_selections.extend(team_A_players)
                else:
                    all_selections.extend(team_B_players)

    submitted = st.form_submit_button("✅ Confirm Results & Prepare Next Round")
    if submitted:
        if all_selections:
            session.finalize_round(all_selections)
            session.prepare_round()
            save_state()
            st.rerun()
        else:
            st.warning("Cannot process results as no courts were available.")

# --- Session Management in Sidebar ---
with st.sidebar:
    st.header("Manage Session")
    if st.button("⚠️ Clear & Reset Session"):
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        # Clear session state keys
        for key in ['session', 'player_list']:
            if key in st.session_state:
                del st.session_state[key]
        st.switch_page("1_Setup.py")