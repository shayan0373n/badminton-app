#!/usr/bin/env python3
"""
TrueSkill Through Time Rating Recalculation Script.

This standalone script rebuilds player ratings from the complete match history.
It fetches all sessions and matches, runs TTT convergence, and updates player
ratings (mu, sigma) in the database.
"""

import logging
from datetime import datetime
from database import PlayerDB, SessionDB, MatchDB, SeasonDB
from logger import setup_logging
from ttt_logic import age_sigma, get_ttt_history, parse_timestamp, to_day_ordinal, today_ordinal

# Configure logging using matching app pattern
setup_logging(logging.INFO)
logger = logging.getLogger("app.recalculate_ratings")


def recalculate_all_ratings() -> None:
    """Rebuild complete TTT history and update all player ratings."""
    logger.info("=== Starting TTT Rating Recalculation ===")

    # Load sessions and matches to display summary stats
    sessions = SessionDB.get_all_sessions()
    matches = MatchDB.get_all_matches()
    session_map = {s["id"]: s for s in sessions}
    processed_matches = [m for m in matches if m.get("session_id") in session_map]
    unique_sessions = {m["session_id"] for m in processed_matches if m.get("session_id") is not None}

    session_dates = []
    for s_id in unique_sessions:
        session = session_map[s_id]
        if "created_at" in session:
            ts = parse_timestamp(session["created_at"])
            session_dates.append(datetime.fromtimestamp(ts))

    logger.info(f"Processing {len(processed_matches)} matches across {len(unique_sessions)} unique sessions.")
    if session_dates:
        start_date = min(session_dates).strftime("%Y-%m-%d")
        end_date = max(session_dates).strftime("%Y-%m-%d")
        logger.info(f"Match date range: {start_date} to {end_date}")

    history, learning_curves, players, _ = get_ttt_history()

    if not learning_curves:
        logger.info("No matches to process. Exiting.")
        return

    logger.info("Updating player ratings...")
    today_day = today_ordinal()

    current_season = SeasonDB.get_current_season()
    if current_season is None:
        raise RuntimeError("No current season found; rating recalculation requires an active season.")
    season_start_day = to_day_ordinal(current_season["start_date"])

    for name in learning_curves:
        if name not in players:
            logger.warning(f"  Player '{name}' found in matches but not in database")

    updated_count = 0
    for name, player in players.items():
        curve = learning_curves.get(name)
        if curve:
            # Played this season: use the last in-season estimate, aged to today.
            final_day, final_estimate = curve[-1]
            base_sigma = final_estimate.sigma
            player.mu = final_estimate.mu
        else:
            # No matches this season yet: age the carried-forward prior instead.
            final_day = season_start_day
            base_sigma = player.prior_sigma

        player.sigma = age_sigma(base_sigma, today_day - final_day)
        updated_count += 1

    # Save updated ratings to database
    logger.info(f"Saving {updated_count} updated player ratings to database...")
    PlayerDB.upsert_players(players)

    logger.info("=== Rating Recalculation Complete ===")
    
    # Print basic summary
    print("\n--- Final Rating Summary ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(
            f"{i:2}. {p.name:20} mu={p.mu:5.2f}  sigma={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})"
        )

    print("\nTip: Run 'python analyze_ratings.py' for detailed improvement analysis and correlation plots.")


if __name__ == "__main__":
    recalculate_all_ratings()
