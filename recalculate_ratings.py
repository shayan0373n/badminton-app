#!/usr/bin/env python3
"""
TrueSkill Through Time Rating Recalculation Script.

This standalone script rebuilds player ratings from the complete match history.
It fetches all sessions and matches, runs TTT convergence, and updates player
ratings (mu, sigma) in the database.

Usage:
    python recalculate_ratings.py

Requirements:
    - SUPABASE_URL and SUPABASE_KEY environment variables or .streamlit/secrets.toml
"""

import logging
from datetime import datetime

from trueskillthroughtime import History, Player as TTTPlayer, Gaussian

from constants import (
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
    TTT_BETA,
    TTT_GAMMA,
    TTT_REFERENCE_DATE,
)
from database import PlayerDB, SessionDB, MatchDB
from session_logic import Player
from logger import setup_logging

# Configure logging using matching app pattern
setup_logging(logging.INFO)
logger = logging.getLogger("app.recalculate_ratings")


def parse_timestamp(timestamp_str: str) -> float:
    """Parse ISO timestamp string to Unix timestamp."""
    # Handle various formats from Supabase
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(timestamp_str, fmt)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {timestamp_str}")


def recalculate_all_ratings() -> None:
    """Rebuild complete TTT history and update all player ratings."""

    logger.info("=== Starting TTT Rating Recalculation ===")

    # Fetch all data
    logger.info("Fetching players from database...")
    players = PlayerDB.get_all_players()
    logger.info(f"  Found {len(players)} players")

    logger.info("Fetching sessions from database...")
    sessions = SessionDB.get_all_sessions()
    logger.info(f"  Found {len(sessions)} sessions")

    logger.info("Fetching matches from database...")
    matches = MatchDB.get_all_matches()
    logger.info(f"  Found {len(matches)} matches")

    if not matches:
        logger.info("No matches to process. Exiting.")
        return

    # Build session ID to time (days since reference date) mapping
    session_to_time: dict[int, int] = {}
    for s in sessions:
        timestamp = parse_timestamp(s["created_at"])
        dt = datetime.fromtimestamp(timestamp)
        days_since_ref = (dt.date() - TTT_REFERENCE_DATE.date()).days
        session_to_time[s["id"]] = days_since_ref

    logger.info(
        f"  Session time range: {min(session_to_time.values())} to {max(session_to_time.values())} days since {TTT_REFERENCE_DATE.date()}"
    )

    # Build TTT composition (winner team first)
    composition: list[list[list[str]]] = []
    times: list[int] = []

    for match in matches:
        p1 = match["player_1"]
        p2 = match["player_2"]
        p3 = match.get("player_3")
        p4 = match.get("player_4")
        winner_side = match["winner_side"]
        session_id = match["session_id"]

        if session_id not in session_to_time:
            logger.warning(
                f"  Match {match['id']} references unknown session {session_id}, skipping"
            )
            continue

        # Determine teams based on whether it's doubles or singles
        if p3 and p4:
            # Doubles match
            team1 = [p1, p2]
            team2 = [p3, p4]
        else:
            # Singles match
            team1 = [p1]
            team2 = [p2]

        # TTT expects winner first
        if winner_side == 1:
            teams = [team1, team2]
        else:
            teams = [team2, team1]

        composition.append(teams)
        times.append(session_to_time[session_id])

    logger.info(f"  Built composition with {len(composition)} games")

    # 4. Build priors from database (prior_mu, prior_sigma)
    priors: dict[str, TTTPlayer] = {}
    for name, player in players.items():
        priors[name] = TTTPlayer(Gaussian(mu=player.prior_mu, sigma=player.prior_sigma), beta=TTT_BETA, gamma=TTT_GAMMA)

    logger.info(f"  Built priors for {len(priors)} players")

    # 5. Run TTT
    logger.info("Running TrueSkill Through Time...")
    logger.info(
        f"  Parameters: mu={TTT_DEFAULT_MU}, sigma={TTT_DEFAULT_SIGMA}, beta={TTT_BETA}, gamma={TTT_GAMMA}"
    )

    history = History(
        composition=composition,
        times=times,
        priors=priors,
        mu=TTT_DEFAULT_MU,  # Fallback for unknown players
        sigma=TTT_DEFAULT_SIGMA,
        beta=TTT_BETA,
        gamma=TTT_GAMMA,
    )

    iterations = history.convergence(iterations=30)
    logger.info(f"  Converged in {iterations} iterations")

    # 6. Extract final ratings
    learning_curves = history.learning_curves()

    logger.info("Updating player ratings...")
    updated_count = 0
    for name, curve in learning_curves.items():
        if name in players:
            # Get the last estimate (most recent)
            final_time, final_estimate = curve[-1]
            old_mu = players[name].mu
            old_sigma = players[name].sigma

            players[name].mu = final_estimate.mu
            players[name].sigma = final_estimate.sigma

            logger.debug(
                f"  {name}: mu {old_mu:.2f} -> {final_estimate.mu:.2f}, "
                f"sigma {old_sigma:.2f} -> {final_estimate.sigma:.2f}"
            )
            updated_count += 1
        else:
            # Player appeared in matches but not in database
            logger.warning(f"  Player '{name}' found in matches but not in database")

    # 7. Save updated ratings to database
    logger.info(f"Saving {updated_count} updated player ratings to database...")
    PlayerDB.upsert_players(players)

    logger.info("=== Rating Recalculation Complete ===")

    # Print summary
    print("\n--- Rating Summary ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(
            f"{i:2}. {p.name:20} mu={p.mu:5.2f}  σ={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})"
        )


if __name__ == "__main__":
    recalculate_all_ratings()
