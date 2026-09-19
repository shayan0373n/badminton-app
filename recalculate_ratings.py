#!/usr/bin/env python3
"""
TrueSkill Through Time Rating Recalculation Script.

Command-line entry point for season_service.recalculate_ratings(): rebuilds the
current season's TTT history, writes each player's mu/sigma to the database,
and prints the resulting standings.
"""

import logging

from logger import setup_logging
from season_service import recalculate_ratings

setup_logging(logging.INFO)
logger = logging.getLogger("app.recalculate_ratings")


def main() -> None:
    logger.info("=== Starting TTT Rating Recalculation ===")
    players, match_count = recalculate_ratings()
    logger.info("=== Rating Recalculation Complete ===")

    print(f"\n--- Final Rating Summary ({match_count} matches this season) ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(
            f"{i:2}. {p.name:20} mu={p.mu:5.2f}  sigma={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})"
        )

    print("\nTip: Run 'python analyze_ratings.py' for detailed improvement analysis and correlation plots.")


if __name__ == "__main__":
    main()
