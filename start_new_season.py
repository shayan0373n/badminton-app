#!/usr/bin/env python3
"""
Start a new season.

Carries every player's end-of-season skill forward as the next season's TTT
prior (converged mu, drift-aged sigma), then closes the current season at the
given end date and opens a new one the following day. From then on, ratings are
computed from the carried priors plus only the new season's matches.

Usage:
    python start_new_season.py 2026-07-01
"""

import argparse
import logging
from datetime import date, datetime

from logger import setup_logging
from season_service import start_new_season

setup_logging(logging.INFO)
logger = logging.getLogger("app.start_new_season")


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Close the current season and open a new one.")
    parser.add_argument(
        "end_date",
        type=_parse_date,
        help="Intended last day of the season being closed (YYYY-MM-DD). The new season starts the next day.",
    )
    args = parser.parse_args()

    logger.info("=== Starting New Season ===")
    new_id = start_new_season(args.end_date)
    logger.info(f"=== Done. New season is now current (id={new_id}). ===")


if __name__ == "__main__":
    main()
