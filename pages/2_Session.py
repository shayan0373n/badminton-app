# pages/2_Session.py
"""
Session management page for the Badminton App.

This page displays the current round's matches and allows users to:
- Select winners for each court
- View current standings
- Manage courts and players mid-session
- Apply Glicko-2 rating updates
"""

import pandas as pd
import streamlit as st

from database import MatchDB, PlayerDB, SessionDB
from rating import Glicko2Rating, process_session_matches
from session_logic import Player, SessionManager
from app_types import Gender


def inject_css(file_path: str) -> None:
    """Injects custom CSS from the specified file path."""
    try:
        with open(file_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(
            f"CSS file not found at {file_path}. Make sure it's in the root directory."
        )


st.set_page_config(initial_sidebar_state="collapsed", layout="wide")

inject_css("styles.css")

# --- Page Entry Logic ---
# If the session object is lost (e.g., page reload), try to load it from the file.
if "session" not in st.session_state or "current_session_name" not in st.session_state:
    st.error("No active session found. Please start or resume a session.")
    st.switch_page("1_Setup.py")

# --- Main App Display ---
session = st.session_state.session
session_name = st.session_state.current_session_name
game_mode_str = "Doubles" if session.is_doubles else "Singles"
st.title(f"🏸 {session_name} ({game_mode_str})")

col1, col2 = st.columns([2, 1])

with col1:
    st.header(f"Select Winners for Round {session.round_num}")

    # Resting players info
    st.info(f"**Resting:** {', '.join(session.resting_players)}")

    # Get locked pairs for visual indicators
    locked_pairs = []
    if session.is_doubles:
        teammate_pairs = session.get_teammate_pairs()
        locked_pairs_set = set(tuple(sorted(pair)) for pair in teammate_pairs)
    else:
        locked_pairs_set = set()

    # Results form
    with st.form(key="results_form"):
        winners_by_court = {}
        if not session.current_round_matches:
            st.warning(
                "No courts could be formed with the current number of active players."
            )
        else:
            for i, match in enumerate(session.current_round_matches):
                with st.container(border=True):  # Wrap each match in a container
                    cols = st.columns([1, 3], vertical_alignment="center")
                    with cols[0]:
                        st.markdown(f"#### Court {match['court']}")
                    with cols[1]:
                        if not session.is_doubles:
                            # Singles: 1v1 match
                            player_1 = match["player_1"]
                            player_2 = match["player_2"]
                            player_1_name = player_1
                            player_2_name = player_2
                            winner_selection = st.segmented_control(
                                "Select Winner",
                                (player_1_name, player_2_name),
                                key=f"court_{match['court']}",
                                label_visibility="collapsed",
                            )
                            if winner_selection == player_1_name:
                                winners_by_court[match["court"]] = (player_1,)
                            elif winner_selection == player_2_name:
                                winners_by_court[match["court"]] = (player_2,)
                            else:
                                winners_by_court[match["court"]] = None
                        else:
                            # Doubles: 2v2 match
                            team_A = match["team_1"]
                            team_B = match["team_2"]

                            # Add visual indicator for locked pairs
                            team_A_key = tuple(sorted(team_A))
                            team_B_key = tuple(sorted(team_B))
                            team_A_locked = team_A_key in locked_pairs_set
                            team_B_locked = team_B_key in locked_pairs_set

                            lock_icon = "🔗"
                            team_A_names = f"{team_A[0]} -- {team_A[1]}"
                            team_B_names = f"{team_B[0]} -- {team_B[1]}"

                            if team_A_locked:
                                team_A_names = f"{lock_icon} {team_A_names}"
                            if team_B_locked:
                                team_B_names = f"{lock_icon} {team_B_names}"

                            winner_selection = st.segmented_control(
                                "Select Winner",
                                (team_A_names, team_B_names),
                                key=f"court_{match['court']}",
                                label_visibility="collapsed",
                            )
                            if winner_selection == team_A_names:
                                winners_by_court[match["court"]] = team_A
                            elif winner_selection == team_B_names:
                                winners_by_court[match["court"]] = team_B
                            else:
                                winners_by_court[match["court"]] = None

        submitted = st.form_submit_button("✅ Confirm Results")
        if submitted:
            if winners_by_court:
                if all(v is not None for v in winners_by_court.values()):
                    # Record matches to Supabase before finalizing
                    session_id = st.session_state.get("current_session_id")
                    if session_id and session.current_round_matches:
                        try:
                            for match in session.current_round_matches:
                                court_num = match["court"]
                                winner = winners_by_court.get(court_num)
                                if winner:
                                    if not session.is_doubles:
                                        p1 = match["player_1"]
                                        p2 = match["player_2"]
                                        winner_side = 1 if winner[0] == p1 else 2
                                        MatchDB.add_match(
                                            session_id=session_id,
                                            player_1=p1,
                                            player_2=p2,
                                            winner_side=winner_side,
                                        )
                                    else:  # Doubles
                                        team_1 = match["team_1"]
                                        team_2 = match["team_2"]
                                        winner_side = (
                                            1 if set(winner) == set(team_1) else 2
                                        )
                                        MatchDB.add_match(
                                            session_id=session_id,
                                            player_1=team_1[0],
                                            player_2=team_1[1],
                                            winner_side=winner_side,
                                            player_3=team_2[0],
                                            player_4=team_2[1],
                                        )
                        except Exception as e:
                            st.warning(f"Could not record matches to cloud: {e}")

                    session.finalize_round(winners_by_court)
                    session.prepare_round()
                    SessionManager.save(
                        session, session_name
                    )  # Save the updated session state
                    st.rerun()
                else:
                    st.warning(
                        "Please select a winner for each court before submitting."
                    )
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

    with st.expander("🎾 Courts", expanded=False):
        st.markdown(f"**Courts:** {int(session.num_courts)}")
        col_add, col_remove = st.columns(2)
        with col_add:
            if st.button("Add court", key="add_court_btn", use_container_width=True):
                session.update_courts(session.num_courts + 1)
                SessionManager.save(session, session_name)
                st.rerun()
        with col_remove:
            if st.button(
                "Remove court", key="remove_court_btn", use_container_width=True
            ):
                if session.num_courts > 1:
                    session.update_courts(session.num_courts - 1)
                    SessionManager.save(session, session_name)
                    st.rerun()
                else:
                    st.info("Minimum 1 court.")

    with st.expander("➕ Add Player", expanded=False):
        # 1. Load the master registry
        try:
            master_registry = PlayerDB.get_all_players()
        except Exception:
            master_registry = {}
            st.warning("Could not load registry. Manual entry only.")

        # Filter out players already in the session
        current_names = set(session.player_pool.keys())
        available_from_registry = [
            name for name in master_registry.keys() if name not in current_names
        ]

        add_method = st.radio(
            "Method",
            ["Pick from Registry", "New Guest"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if add_method == "Pick from Registry":
            selected_reg_name = st.selectbox(
                "Select Member", options=[""] + sorted(available_from_registry)
            )
            if st.button("Add Member to Session", key="add_reg_btn"):
                if selected_reg_name:
                    p = master_registry[selected_reg_name]
                    added = session.add_player(
                        name=p.name,
                        gender=p.gender,
                        elo=p.elo,
                        deviation=p.deviation,
                        volatility=p.volatility,
                    )
                    if added:
                        SessionManager.save(session, session_name)
                        st.success(f"Added {selected_reg_name} to tonight's session!")
                        st.rerun()
                else:
                    st.warning("Please select a member.")
        else:
            # New Guest Entry
            new_name = st.text_input("Guest Name", key="mid_add_name")
            new_gender = st.selectbox(
                "Gender", options=["M", "F"], key="mid_add_gender"
            )
            new_elo = st.number_input(
                "ELO", min_value=0, step=1, value=1500, key="mid_add_elo"
            )

            new_team_name = ""
            if session.is_doubles:
                new_team_name = st.text_input(
                    "Team Name (optional)", key="mid_add_team"
                )

            if st.button("Create & Add Guest", key="mid_add_btn"):
                if not new_name.strip():
                    st.warning("Please enter a name.")
                else:
                    # Create Player Object
                    guest_player = Player(
                        name=new_name.strip(),
                        gender=Gender(new_gender),
                        elo=float(new_elo),
                        team_name=new_team_name.strip(),
                    )

                    # 1. Add to Session
                    added = session.add_player(
                        name=guest_player.name,
                        gender=guest_player.gender,
                        elo=guest_player.elo,
                        team_name=guest_player.team_name,
                    )

                    if added:
                        # Save to Supabase
                        try:
                            PlayerDB.upsert_players({guest_player.name: guest_player})
                        except Exception as e:
                            st.error(f"Failed to sync guest to cloud registry: {e}")

                        SessionManager.save(session, session_name)
                        st.success(f"Added {new_name} and saved to Member Registry!")
                        st.rerun()
                    else:
                        st.warning("A player with that name already exists.")

    with st.expander("➖ Remove Player", expanded=False):
        # Show queued removals if any
        if session.queued_removals:
            st.warning(
                f"⏳ Queued for removal: {', '.join(sorted(session.queued_removals))}"
            )
            st.caption(
                "These players will be removed when you confirm the current round results."
            )

        # Get list of all players
        all_players = list(session.player_pool.keys())
        if all_players:
            player_to_remove = st.selectbox(
                "Select Player to Remove",
                options=sorted(all_players),
                key="remove_player_select",
            )
            if st.button("Remove Player", key="mid_remove_btn", type="secondary"):
                success, status = session.remove_player(player_to_remove)
                if success:
                    if status == "immediate":
                        SessionManager.save(session, session_name)
                        st.success(f"✅ Removed {player_to_remove} from the session.")
                        st.rerun()
                    elif status == "queued":
                        SessionManager.save(session, session_name)
                        st.info(
                            f"⏳ {player_to_remove} is currently playing and will be removed after you confirm this round's results."
                        )
                        st.rerun()
                else:
                    st.error(f"Player {player_to_remove} not found.")
        else:
            st.info("No players to remove.")

    with st.expander("📊 Rating Updates", expanded=False):
        session_id = st.session_state.get("current_session_id")

        if session_id:
            st.caption("Apply Glicko-2 rating updates based on match results.")

            if st.button(
                "🎯 Apply Rating Updates",
                key="apply_ratings_btn",
                use_container_width=True,
            ):
                try:
                    # Get unprocessed matches
                    unprocessed = MatchDB.get_unprocessed_matches(session_id)

                    if not unprocessed:
                        st.info("No unprocessed matches found.")
                    else:
                        # Get current player ratings from database
                        all_players = PlayerDB.get_all_players()

                        # Process matches and get new ratings
                        new_ratings = process_session_matches(
                            matches=unprocessed,
                            players=all_players,
                            is_doubles=session.is_doubles,
                        )

                        # Update players with new ratings
                        updated_players = {}
                        rating_changes = []
                        for name, new_rating in new_ratings.items():
                            if name in all_players:
                                player = all_players[name]
                                old_elo = player.elo
                                player.elo = new_rating.rating
                                player.deviation = new_rating.rd
                                player.volatility = new_rating.volatility
                                updated_players[name] = player

                                change = new_rating.rating - old_elo
                                rating_changes.append((name, change))

                        # Save to database
                        PlayerDB.upsert_players(updated_players)

                        # Mark matches as processed
                        match_ids = [m["id"] for m in unprocessed]
                        MatchDB.mark_matches_processed(match_ids)

                        # Show results
                        st.success(
                            f"Updated ratings for {len(updated_players)} players!"
                        )

                        # Show rating changes summary
                        rating_changes.sort(key=lambda x: x[1], reverse=True)
                        changes_text = []
                        for name, change in rating_changes:
                            if change >= 0:
                                changes_text.append(f"**{name}**: +{change:.1f}")
                            else:
                                changes_text.append(f"**{name}**: {change:.1f}")

                        if changes_text:
                            st.markdown("**Rating Changes:**")
                            st.markdown(" | ".join(changes_text[:6]))  # Show top 6
                            if len(changes_text) > 6:
                                st.caption(f"...and {len(changes_text) - 6} more")

                except Exception as e:
                    st.error(f"Failed to update ratings: {e}")
        else:
            st.warning("Session not connected to cloud. Rating updates unavailable.")

    if st.button("⚠️ Terminate Session"):
        # Preserve the player table and session parameters for the next session
        if "session" in st.session_state:
            st.session_state.player_table = st.session_state.session.player_pool
            st.session_state.player_table_updated = True  # Flag to refresh editor

            # Preserve session parameters
            st.session_state.num_courts_persistent = st.session_state.session.num_courts
            st.session_state.is_doubles_persistent = st.session_state.session.is_doubles
            st.session_state.weights = st.session_state.session.weights.copy()
            st.session_state.skill_weight = st.session_state.weights.get("skill", 1.0)
            st.session_state.power_weight = st.session_state.weights.get("power", 1.0)
            st.session_state.pairing_weight = st.session_state.weights.get(
                "pairing", 1.0
            )
            st.session_state.female_female_team_penalty = (
                st.session_state.session.female_female_team_penalty
            )
            st.session_state.mixed_gender_team_penalty = (
                st.session_state.session.mixed_gender_team_penalty
            )
            st.session_state.female_singles_penalty = (
                st.session_state.session.female_singles_penalty
            )

        SessionManager.clear(session_name)  # Clear the session state file

        # Clear session objects from state
        if "session" in st.session_state:
            del st.session_state["session"]
        if "current_session_name" in st.session_state:
            del st.session_state["current_session_name"]

        st.switch_page("1_Setup.py")
