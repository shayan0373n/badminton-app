# optimizer_ortools.py
"""
Match optimization for badminton sessions using Google OR-Tools CP-SAT solver.

Same public API as optimizer.py but uses the CP-SAT constraint programming solver
instead of PuLP/Gurobi. Key improvements over the MILP approach:

1. OnlyEnforceIf replaces Big-M constraints — no magic constants, no numerical instability.
2. Native boolean logic (AddImplication, AddBoolOr) for variable linking.
3. Integer arithmetic throughout — float ratings scaled by RATING_SCALE (1000).
"""

import logging
from itertools import combinations
import random

from ortools.sat.python import cp_model

from constants import (
    PARTNER_HISTORY_MULTIPLIER,
    COURT_HISTORY_NORMALIZATION,
    OPTIMIZER_TIME_LIMIT,
)
from optimizer import get_partnership_penalty, get_same_court_penalty
from app_types import (
    OptimizerResult,
    CourtHistory,
    PlayerGenders,
    PlayerName,
    PlayerPair,
    RealSkills,
    RequiredPartners,
    SinglesMatch,
    DoublesMatch,
    TierRatings,
)

logger = logging.getLogger("app.optimizer")

# CP-SAT works with integers. Float ratings (0.0-5.0) are scaled by this factor,
# preserving 2 decimal places of precision.
RATING_SCALE = 100


def _scale(value: float) -> int:
    """Convert a float value to a scaled integer for CP-SAT."""
    return round(value * RATING_SCALE)


# ============================================================================
# Singles mode matching logic
# ============================================================================
def generate_singles_round(
    available_players: list[PlayerName],
    num_courts: int,
    real_skills: RealSkills,
    court_history: CourtHistory,
    weights: dict[str, float],
    time_limit: float = OPTIMIZER_TIME_LIMIT,
) -> OptimizerResult:
    """
    Generates a singles round with 1v1 matches using CP-SAT.

    Uses simpler optimization focusing on skill balance and opponent history.
    Matches players with similar real skills for competitive 1v1 games.

    Args:
        available_players: List of player names available to play
        num_courts: Number of courts to fill
        real_skills: Dict mapping player names to their real skill ratings (0-5 scale)
        court_history: Dict tracking how often player pairs have shared a court
        weights: Dict with 'skill', 'power', 'pairing' weight values (int)

    Returns:
        OptimizerResult with matches and updated court history
    """
    max_courts = len(available_players) // 2
    num_courts = min(num_courts, max_courts)

    if num_courts == 0:
        return OptimizerResult(matches=[], court_history=court_history)

    model = cp_model.CpModel()

    # Scale ratings and weights to integers
    skill_s = {p: _scale(real_skills[p]) for p in available_players}
    min_possible = min(skill_s.values())
    max_possible = max(skill_s.values())
    w_skill = int(weights["skill"])
    w_pairing = int(weights["pairing"])

    # --- Variables ---
    # x[p, c]: player p is on court c
    x = {}
    for p in available_players:
        for c in range(num_courts):
            x[p, c] = model.NewBoolVar(f"x_{p}_{c}")

    # o[pair, c]: both players in pair are opponents on court c
    player_pairs = list(combinations(sorted(available_players), 2))
    o = {}
    for pair in player_pairs:
        for c in range(num_courts):
            o[pair, c] = model.NewBoolVar(f"o_{pair[0]}_{pair[1]}_{c}")

    # Skill balance tracking per court
    max_r = {}
    min_r = {}
    for c in range(num_courts):
        max_r[c] = model.NewIntVar(min_possible, max_possible, f"max_r_{c}")
        min_r[c] = model.NewIntVar(min_possible, max_possible, f"min_r_{c}")

    # --- Constraints ---
    # Exactly 2 players per court
    for c in range(num_courts):
        model.Add(sum(x[p, c] for p in available_players) == 2)

    # Each player plays at most once
    for p in available_players:
        model.Add(sum(x[p, c] for c in range(num_courts)) <= 1)

    # Total players on all courts
    model.Add(
        sum(x[p, c] for p in available_players for c in range(num_courts))
        == num_courts * 2
    )

    # Link opponent variables: o[pair, c] = 1 iff both players on court c
    for p1, p2 in player_pairs:
        for c in range(num_courts):
            # o => x1 AND x2
            model.AddImplication(o[(p1, p2), c], x[p1, c])
            model.AddImplication(o[(p1, p2), c], x[p2, c])
            # x1 AND x2 => o
            model.AddBoolOr([o[(p1, p2), c], x[p1, c].Not(), x[p2, c].Not()])

    # Skill balance: OnlyEnforceIf replaces Big-M
    for c in range(num_courts):
        for p in available_players:
            model.Add(max_r[c] >= skill_s[p]).OnlyEnforceIf(x[p, c])
            model.Add(min_r[c] <= skill_s[p]).OnlyEnforceIf(x[p, c])

    # --- Objective ---
    # Skill: minimize rating spread per court (scaled by RATING_SCALE)
    skill_obj = sum(max_r[c] - min_r[c] for c in range(num_courts))

    # Pairing: minimize repeated opponents (penalty * RATING_SCALE for scale parity)
    pairing_obj = sum(
        o[pair, c] * int(get_same_court_penalty(pair, court_history)) * RATING_SCALE
        for pair in player_pairs
        for c in range(num_courts)
    )

    model.Minimize(w_skill * skill_obj + w_pairing * pairing_obj)

    # --- Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    status = solver.Solve(model)

    if status == cp_model.INFEASIBLE:
        logger.error("No optimal solution found for singles (INFEASIBLE)")
        return OptimizerResult(matches=None, court_history=court_history)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.error("Solver returned unexpected status for singles: %s", status)
        return OptimizerResult(matches=None, court_history=court_history)

    # Log debug info
    logger.debug(
        "Max Rating on Court: %s",
        {c: solver.Value(max_r[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug(
        "Min Rating on Court: %s",
        {c: solver.Value(min_r[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug("Objective Value: %s", solver.ObjectiveValue())

    # --- Build matches ---
    matches = []
    updated_court_history = court_history.copy()

    for c in range(num_courts):
        court_players = [
            p for p in available_players if solver.BooleanValue(x[p, c])
        ]

        if len(court_players) == 2:
            p1, p2 = sorted(court_players)
            pair_key = tuple(sorted((p1, p2)))
            partner_count, opponent_count = updated_court_history.get(
                pair_key, (0, 0)
            )
            updated_court_history[pair_key] = (partner_count, opponent_count + 1)

            matches.append(
                SinglesMatch(court=c + 1, player_1=p1, player_2=p2)
            )

    return OptimizerResult(matches=matches, court_history=updated_court_history)


# ============================================================================
# Doubles mode and main entry point
# ============================================================================
def generate_one_round(
    tier_ratings: TierRatings,
    real_skills: RealSkills,
    player_genders: PlayerGenders,
    players_to_rest: set[PlayerName],
    num_courts: int,
    court_history: CourtHistory,
    weights: dict[str, float],
    players_per_court: int = 4,
    is_doubles: bool = True,
    required_partners: RequiredPartners | None = None,
    time_limit: float = OPTIMIZER_TIME_LIMIT,
) -> OptimizerResult:
    """
    Generates a single, optimized round of badminton matches using CP-SAT.

    Supports both Doubles (4 players per court) and Singles (2 players per court).

    Uses decoupled inputs for different objectives:
    - tier_ratings: Z-score normalized ratings for court grouping (social hierarchy)
    - real_skills: Direct normalized ratings for team fairness (win probability)

    Args:
        tier_ratings: Dict mapping player names to tier ratings (0-5 scale)
        real_skills: Dict mapping player names to real skill ratings (0-5 scale)
        player_genders: Dict mapping player names to 'M' or 'F'
        players_to_rest: Set of player names who should rest this round
        num_courts: Number of courts to fill
        court_history: Dict tracking how often player pairs have shared a court
        players_per_court: Number of players per court (2 for singles, 4 for doubles)
        weights: Dict with 'skill', 'power', 'pairing' weight values (int)
        is_doubles: True for doubles mode, False for singles mode
        required_partners: Optional dict mapping players to their required partners

    Returns:
        OptimizerResult with matches and updated court history
    """
    logger.debug("Tier ratings: %s", tier_ratings)
    logger.debug("Real skills: %s", real_skills)

    if required_partners is None:
        required_partners = {}

    all_players = list(tier_ratings.keys())
    available_players = [p for p in all_players if p not in players_to_rest]
    random.shuffle(available_players)

    num_available = len(available_players)
    max_courts = num_available // players_per_court
    num_courts = min(num_courts, max_courts)

    if num_courts == 0:
        return OptimizerResult(matches=[], court_history=court_history)

    players_needed = num_courts * players_per_court

    # For singles mode, use simpler matching logic
    if not is_doubles:
        return generate_singles_round(
            available_players,
            num_courts,
            real_skills,
            court_history,
            weights,
            time_limit=time_limit,
        )

    # --- Doubles CP-SAT model ---
    model = cp_model.CpModel()

    # Scale ratings to integers
    tier_s = {p: _scale(tier_ratings[p]) for p in available_players}
    skill_s = {p: _scale(real_skills[p]) for p in available_players}

    min_tier = min(tier_s.values())
    max_tier = max(tier_s.values())

    # Scale weights to integers
    w_skill = int(weights["skill"])
    w_power = int(weights["power"])
    w_pairing = int(weights["pairing"])

    # Pre-compute scaled pair powers (team average skill)
    player_pairs = list(combinations(sorted(available_players), 2))
    pair_power_s = {}
    for p1, p2 in player_pairs:
        pair_power_s[(p1, p2)] = round(
            (real_skills[p1] + real_skills[p2]) / 2 * RATING_SCALE
        )

    min_power = min(pair_power_s.values())
    max_power = max(pair_power_s.values())

    # --- Variables ---
    # x[p, c]: player p is on court c
    x = {}
    for p in available_players:
        for c in range(num_courts):
            x[p, c] = model.NewBoolVar(f"x_{p}_{c}")

    # t[pair, c]: pair are partners on court c
    t = {}
    # s[pair, c]: pair share court c (partners or opponents)
    s = {}
    for pair in player_pairs:
        for c in range(num_courts):
            t[pair, c] = model.NewBoolVar(f"t_{pair[0]}_{pair[1]}_{c}")
            s[pair, c] = model.NewBoolVar(f"s_{pair[0]}_{pair[1]}_{c}")

    # Rating/power tracking per court
    max_rating = {}
    min_rating = {}
    max_team_pw = {}
    min_team_pw = {}
    for c in range(num_courts):
        max_rating[c] = model.NewIntVar(min_tier, max_tier, f"max_r_{c}")
        min_rating[c] = model.NewIntVar(min_tier, max_tier, f"min_r_{c}")
        max_team_pw[c] = model.NewIntVar(min_power, max_power, f"max_pw_{c}")
        min_team_pw[c] = model.NewIntVar(min_power, max_power, f"min_pw_{c}")

    # --- Constraints ---
    # Exactly players_per_court per court
    for c in range(num_courts):
        model.Add(sum(x[p, c] for p in available_players) == players_per_court)

    # Each player at most once
    for p in available_players:
        model.Add(sum(x[p, c] for c in range(num_courts)) <= 1)

    # Total players on all courts
    model.Add(
        sum(x[p, c] for p in available_players for c in range(num_courts))
        == players_needed
    )

    # Partner constraints: t => both players on court
    for p1, p2 in player_pairs:
        for c in range(num_courts):
            model.AddImplication(t[(p1, p2), c], x[p1, c])
            model.AddImplication(t[(p1, p2), c], x[p2, c])

    # Each player has exactly one partner per court when playing
    for p in available_players:
        for c in range(num_courts):
            model.Add(
                sum(t[pair, c] for pair in player_pairs if p in pair) == x[p, c]
            )

    # Same-court variables: s[pair, c] = 1 iff both players on court c
    for p1, p2 in player_pairs:
        for c in range(num_courts):
            # s => x1 AND x2
            model.AddImplication(s[(p1, p2), c], x[p1, c])
            model.AddImplication(s[(p1, p2), c], x[p2, c])
            # x1 AND x2 => s
            model.AddBoolOr(
                [s[(p1, p2), c], x[p1, c].Not(), x[p2, c].Not()]
            )

    # Required partners: satisfaction constraint
    for player, partners in required_partners.items():
        if player not in available_players:
            continue

        active_partners = [p for p in partners if p in available_players]

        if active_partners:
            for c in range(num_courts):
                satisfaction_terms = []
                for p in active_partners:
                    # Direct partnership
                    satisfaction_terms.append(t[tuple(sorted((player, p))), c])

                    # Indirect excuse: partner p is with another teammate k
                    p_partners = required_partners.get(p, set())
                    for k in p_partners:
                        if k != player and k in available_players:
                            satisfaction_terms.append(
                                t[tuple(sorted((p, k))), c]
                            )

                model.Add(sum(satisfaction_terms) >= x[player, c])

    # Skill balance: OnlyEnforceIf replaces Big-M
    # tier_ratings control court grouping (social hierarchy)
    for c in range(num_courts):
        for p in available_players:
            model.Add(max_rating[c] >= tier_s[p]).OnlyEnforceIf(x[p, c])
            model.Add(min_rating[c] <= tier_s[p]).OnlyEnforceIf(x[p, c])

        # Team power: real_skills control fairness (win probability)
        for p1, p2 in player_pairs:
            pw = pair_power_s[(p1, p2)]
            model.Add(max_team_pw[c] >= pw).OnlyEnforceIf(t[(p1, p2), c])
            model.Add(min_team_pw[c] <= pw).OnlyEnforceIf(t[(p1, p2), c])

    # --- Objective ---
    skill_obj = sum(max_rating[c] - min_rating[c] for c in range(num_courts))
    power_obj = sum(max_team_pw[c] - min_team_pw[c] for c in range(num_courts))

    # Pairing: scale penalty to match rating domain
    # RATING_SCALE / COURT_HISTORY_NORMALIZATION = 1000 / 4 = 250
    PAIRING_SCALE = RATING_SCALE // COURT_HISTORY_NORMALIZATION

    pairing_obj = sum(
        (
            s[pair, c] * int(get_same_court_penalty(pair, court_history))
            + t[pair, c] * int(get_partnership_penalty(pair, court_history))
        )
        * PAIRING_SCALE
        for pair in player_pairs
        for c in range(num_courts)
    )

    model.Minimize(
        w_skill * skill_obj + w_power * power_obj + w_pairing * pairing_obj
    )

    # --- Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    status = solver.Solve(model)

    if status == cp_model.INFEASIBLE:
        logger.error("No optimal solution found for doubles (INFEASIBLE)")
        return OptimizerResult(matches=None, court_history=court_history)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        logger.error("Solver returned unexpected status for doubles: %s", status)
        return OptimizerResult(matches=None, court_history=court_history)

    # Log debug info
    logger.debug(
        "Max Rating on Court: %s",
        {c: solver.Value(max_rating[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug(
        "Min Rating on Court: %s",
        {c: solver.Value(min_rating[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug(
        "Max Team Power: %s",
        {c: solver.Value(max_team_pw[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug(
        "Min Team Power: %s",
        {c: solver.Value(min_team_pw[c]) / RATING_SCALE for c in range(num_courts)},
    )
    logger.debug(
        "Total Skill Objective: %s",
        solver.Value(skill_obj) / RATING_SCALE,
    )
    logger.debug(
        "Total Power Objective: %s",
        solver.Value(power_obj) / RATING_SCALE,
    )
    logger.debug("Objective Value: %s", solver.ObjectiveValue())

    # --- Build matches ---
    matches = []
    updated_court_history = court_history.copy()
    for c in range(num_courts):
        court_players = [
            p for p in available_players if solver.BooleanValue(x[p, c])
        ]

        # Identify partner pairs (2 pairs per court in doubles)
        partner_pairs: set[PlayerPair] = set()
        for p1, p2 in combinations(court_players, 2):
            pair_key = tuple(sorted((p1, p2)))
            if solver.BooleanValue(t[pair_key, c]):
                partner_pairs.add(pair_key)

        # Update court history for ALL pairs that shared this court
        for p1, p2 in combinations(sorted(court_players), 2):
            pair_key = tuple(sorted((p1, p2)))
            partner_count, opponent_count = updated_court_history.get(
                pair_key, (0, 0)
            )
            if pair_key in partner_pairs:
                updated_court_history[pair_key] = (partner_count + 1, opponent_count)
            else:
                updated_court_history[pair_key] = (partner_count, opponent_count + 1)

        if len(partner_pairs) == players_per_court / 2:
            partnerships = list(partner_pairs)
            team1 = partnerships[0]
            team2 = partnerships[1]

            matches.append(
                DoublesMatch(court=c + 1, team_1=team1, team_2=team2)
            )

    return OptimizerResult(matches=matches, court_history=updated_court_history)
