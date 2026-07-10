import logging
from datetime import datetime, date
from trueskillthroughtime import History, Player as TTTPlayer, Gaussian
from constants import (
    TTT_DEFAULT_MU,
    TTT_DEFAULT_SIGMA,
    TTT_BETA,
    TTT_GAMMA,
)
from database import PlayerDB, SessionDB, MatchDB, SeasonDB

logger = logging.getLogger("app.ttt_logic")

def parse_timestamp(timestamp_str: str) -> float:
    """Parse ISO timestamp string to Unix timestamp."""
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


def to_day_ordinal(timestamp: str) -> int:
    """Day ordinal (date.toordinal) of a DB ISO timestamp: the TTT time axis.

    TTT works in day units where only differences matter, so the absolute epoch
    is irrelevant; a session sits on its local calendar date.
    """
    return datetime.fromtimestamp(parse_timestamp(timestamp)).date().toordinal()


def today_ordinal() -> int:
    """Today on the same day axis as to_day_ordinal."""
    return date.today().toordinal()


def age_sigma(sigma: float, idle_days: int) -> float:
    """Inflate a TTT uncertainty forward across idle days via drift.

    Uncertainty grows by the random-walk drift (TTT_GAMMA) per idle day and is
    capped at TTT_DEFAULT_SIGMA (a never-seen player); aging never shrinks it.
    """
    idle_days = max(0, idle_days)
    aged = (sigma**2 + idle_days * TTT_GAMMA**2) ** 0.5
    return min(aged, TTT_DEFAULT_SIGMA)


def get_ttt_history():
    """Fetch data and run TTT convergence. Returns (history, learning_curves, players, match_counts)."""
    players = PlayerDB.get_all_players()
    sessions = SessionDB.get_all_sessions()
    matches = MatchDB.get_all_matches()

    # Restrict to the current season's window. Before any season exists, all
    # history is one implicit preseason (no filtering).
    current_season = SeasonDB.get_current_season()
    if current_season is not None:
        season_start = parse_timestamp(current_season["start_date"])
        sessions = [
            s for s in sessions if parse_timestamp(s["created_at"]) >= season_start
        ]
        in_season = {s["id"] for s in sessions}
        matches = [m for m in matches if m["session_id"] in in_season]

    if not matches:
        return None, {}, players, {}

    match_counts = {}
    session_to_time = {}
    for s in sessions:
        session_to_time[s["id"]] = to_day_ordinal(s["created_at"])

    composition = []
    times = []
    for match in matches:
        p1, p2 = match["player_1"], match["player_2"]
        p3, p4 = match.get("player_3"), match.get("player_4")
        winner_side, session_id = match["winner_side"], match["session_id"]

        if session_id not in session_to_time:
            continue

        # Update match counts
        for p in [p1, p2, p3, p4]:
            if p:
                match_counts[p] = match_counts.get(p, 0) + 1

        team1 = [p1, p2] if (p3 and p4) else [p1]
        team2 = [p3, p4] if (p3 and p4) else [p2]
        teams = [team1, team2] if winner_side == 1 else [team2, team1]

        composition.append(teams)
        times.append(session_to_time[session_id])

    priors = {}
    for name, p in players.items():
        if p.prior_mu is None:
            raise ValueError(
                f"Player '{name}' has no prior_mu set; a skill prior is required to recalculate ratings."
            )
        priors[name] = TTTPlayer(
            Gaussian(mu=p.prior_mu, sigma=p.prior_sigma), beta=TTT_BETA, gamma=TTT_GAMMA
        )

    history = History(
        composition=composition,
        times=times,
        priors=priors,
        mu=TTT_DEFAULT_MU,
        sigma=TTT_DEFAULT_SIGMA,
        beta=TTT_BETA,
        gamma=TTT_GAMMA,
    )
    history.convergence(iterations=50)
    return history, history.learning_curves(), players, match_counts
