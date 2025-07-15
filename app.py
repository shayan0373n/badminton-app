# app.py

import streamlit as st
from session_logic import BadmintonSession

st.set_page_config(layout="wide")
st.title("🏸 Badminton Club Rotation")

# --- Sidebar for Session Setup ---
with st.sidebar:
    st.header("Setup New Session")
    
    player_names_str = st.text_area(
        "Enter Player Names (one per line)", 
        "Shayan\nTara\nDavid\nMaria\nChen\nAlex\nBob\nAlice\nPlayer9\nPlayer10\nPlayer11\nPlayer12\nPlayer13\nPlayer14\nPlayer15\nPlayer16",
        height=400  # Makes the text box taller
    )
    
    # Input for number of courts instead of rests
    num_courts = st.number_input("Number of Courts Available", min_value=1, value=3, step=1)
    
    if st.button("🚀 Start New Session"):
        player_ids = [name.strip() for name in player_names_str.split('\n') if name.strip()]
        
        # Validation for duplicate names
        if len(player_ids) != len(set(player_ids)):
            st.error("Error: Duplicate names found. Please ensure every player has a unique name.")
        elif player_ids:
            total_players = len(player_ids)
            players_on_court = num_courts * 4
            
            # Calculate the number of rests
            rests_per_round = total_players - players_on_court

            # Add validation for player/court numbers
            if rests_per_round < 0:
                st.error(f"Error: You have {num_courts} courts for {total_players} players, which isn't possible. Please reduce the number of courts.")
            else:
                st.session_state.session = BadmintonSession(
                    player_ids=player_ids, 
                    rests_per_round=rests_per_round
                )
                st.session_state.session.prepare_round() # Prepare round 1
                st.rerun()
        else:
            st.error("Please enter at least one player name.")

# --- Main App Display ---
if 'session' in st.session_state:
    session = st.session_state.session
    
    st.header(f"Enter Results for Round {session.round_num}")
    
    # Display Resting Players
    resting_ids = [p['id'] for p in session.resting_players]
    st.info(f"**Resting:** {', '.join(resting_ids)}")

    # Create a form to select all winners at once
    with st.form(key='results_form'):
        all_selections = []
        
        # Check if there are any courts to display
        if not session.courts:
             st.warning("No courts could be formed with the current number of active players.")
        else:
            cols = st.columns(len(session.courts))
            for i, court_players in enumerate(session.courts):
                with cols[i]:
                    st.markdown(f"**Court {i+1}**")
                    team_A_players = [court_players[0], court_players[3]]
                    team_B_players = [court_players[1], court_players[2]]

                    team_A_names = f"{team_A_players[0]['id']} & {team_A_players[1]['id']}"
                    team_B_names = f"{team_B_players[0]['id']} & {team_B_players[1]['id']}"

                    # Radio button to select the winner
                    winner_selection = st.radio(
                        "Select Winner", 
                        (team_A_names, team_B_names), 
                        key=f'court_{i}'
                    )
                    
                    # Store the actual player objects based on selection
                    if winner_selection == team_A_names:
                        all_selections.extend(team_A_players)
                    else:
                        all_selections.extend(team_B_players)

        submitted = st.form_submit_button("✅ Confirm Results & Prepare Next Round")
        if submitted:
            session.finalize_round(all_selections) # Process the results
            session.prepare_round() # Set up the next round's matches
            st.rerun()

else:
    st.info("Enter player names in the sidebar and click 'Start New Session' to begin.")