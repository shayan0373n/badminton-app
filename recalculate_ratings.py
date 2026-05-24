#!/usr/bin/env python3
"""
TrueSkill Through Time Rating Recalculation Script.

This standalone script rebuilds player ratings from the complete match history.
It fetches all sessions and matches, runs TTT convergence, and updates player
ratings (mu, sigma) in the database.
"""

import logging
from database import PlayerDB
from logger import setup_logging
from ttt_logic import get_ttt_history

# Configure logging using matching app pattern
setup_logging(logging.INFO)
logger = logging.getLogger("app.recalculate_ratings")


def recalculate_all_ratings() -> None:
    """Rebuild complete TTT history and update all player ratings."""
    logger.info("=== Starting TTT Rating Recalculation ===")

    history, learning_curves, players, _ = get_ttt_history()

    if not learning_curves:
        logger.info("No matches to process. Exiting.")
        return

    logger.info("Updating player ratings...")
    updated_count = 0
    for name, curve in learning_curves.items():
        if name in players:
            # Get the last estimate (most recent)
            final_time, final_estimate = curve[-1]
            players[name].mu = final_estimate.mu
            players[name].sigma = final_estimate.sigma
            updated_count += 1
        else:
            logger.warning(f"  Player '{name}' found in matches but not in database")

    # Save updated ratings to database
    logger.info(f"Saving {updated_count} updated player ratings to database...")
    PlayerDB.upsert_players(players)

    logger.info("=== Rating Recalculation Complete ===")
    
    # Print basic summary
    print("\n--- Final Rating Summary ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(
            f"{i:2}. {p.name:20} mu={p.mu:5.2f}  σ={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})"
        )

    print("\nTip: Run 'python analyze_ratings.py' for detailed improvement analysis and correlation plots.")


if __name__ == "__main__":
    recalculate_all_ratings()
