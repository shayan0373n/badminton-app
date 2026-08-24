"""
Season rollover service.

A season is a date window. Rolling a season carries each player's end-of-season
skill forward as the next season's TTT prior, then opens the new window so that
new-season ratings are computed from the carried priors plus only the new
season's matches. Carry-forward and season creation are always one operation.
"""

import logging
from datetime import date, datetime, timedelta

from constants import SEASON_MIN_PRIOR_SIGMA
from database import PlayerDB, SeasonDB
from ttt_logic import age_sigma, get_ttt_history

logger = logging.getLogger("app.season_service")


def carry_forward_priors(end_day: int) -> dict:
    """Converge over the current window and set each player's next-season prior.

    prior_mu is the converged mu as of end_day (the player's last match on or
    before end_day, ignoring any later matches). prior_sigma is that endpoint
    sigma aged forward by TTT drift to end_day (see ttt_logic.age_sigma), floored
    at SEASON_MIN_PRIOR_SIGMA to prevent rating inertia in the new season.
    Players with no matches on or before end_day keep their existing priors.
    Converged mu/sigma are also persisted (the end-of-season standings).

    Args:
        end_day: The season's end, as a date ordinal (date.toordinal()). Used to
            age each player's uncertainty from their last session to season end.

    Returns:
        The players dict (post-update), for summary reporting.
    """
    _, learning_curves, players, _ = get_ttt_history()

    if not learning_curves:
        logger.warning("No matches in the current window; priors left unchanged.")
        return players

    updated = 0
    for name, curve in learning_curves.items():
        if name not in players:
            logger.warning(f"Player '{name}' in matches but not in database; skipped.")
            continue
        in_window = [(day, g) for day, g in curve if day <= end_day]
        if not in_window:
            continue
        final_day, final = in_window[-1]

        player = players[name]
        player.mu = final.mu
        player.sigma = final.sigma
        player.prior_mu = final.mu
        player.prior_sigma = max(
            age_sigma(final.sigma, end_day - final_day), SEASON_MIN_PRIOR_SIGMA
        )
        updated += 1

    logger.info(f"Carried forward priors for {updated} player(s).")
    PlayerDB.upsert_players(players)
    return players


def start_new_season(end_date: date) -> int:
    """Roll the current season over: carry priors forward, then open a new season.

    Ordering is deliberate and retry-safe: priors are computed and written while
    the closing season is still current, then the season is rolled. A failure
    after the prior write self-heals on re-run.

    Args:
        end_date: Intended last day of the season being closed. The new season
            starts the following day.

    Returns:
        The new season's ID.
    """
    end_day = end_date.toordinal()
    end_iso = datetime(end_date.year, end_date.month, end_date.day).isoformat()
    new_start_iso = (
        datetime(end_date.year, end_date.month, end_date.day) + timedelta(days=1)
    ).isoformat()

    carry_forward_priors(end_day)

    current = SeasonDB.get_current_season()
    if current is not None:
        SeasonDB.close_season(current["id"], end_iso)
        logger.info(f"Closed season (id={current['id']}) at {end_iso}.")
    else:
        logger.info("No open season to close; opening the first season.")

    new_id = SeasonDB.create_season(new_start_iso)
    logger.info(f"Opened season (id={new_id}) starting {new_start_iso}.")
    return new_id
