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

def get_ttt_history():
    """Fetch data and run TTT convergence. Returns (history, learning_curves, players, match_counts)."""
    players = PlayerDB.get_all_players()
    sessions = SessionDB.get_all_sessions()
    matches = MatchDB.get_all_matches()

    if not matches:
        return None, {}, players, {}

    match_counts = {}
    session_to_time = {}
    for s in sessions:
        timestamp = parse_timestamp(s["created_at"])
        dt = datetime.fromtimestamp(timestamp)
        days_since_ref = (dt.date() - TTT_REFERENCE_DATE.date()).days
        session_to_time[s["id"]] = days_since_ref

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

    priors = {
        name: TTTPlayer(Gaussian(mu=p.prior_mu, sigma=p.prior_sigma), beta=TTT_BETA, gamma=TTT_GAMMA)
        for name, p in players.items()
    }

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
