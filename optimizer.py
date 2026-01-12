# optimizer.py
"""
Match optimization for badminton sessions.

This module uses PuLP with Gurobi solver to generate optimal match assignments
balancing skill levels, power balance, and pairing history.
"""

import logging
from collections import defaultdict
from itertools import combinations
import random

import pulp

from constants import OPTIMIZER_RANK_MIN, OPTIMIZER_RANK_MAX, OPTIMIZER_BIG_M
from logger import log_optimizer_debug
from app_types import (
    MatchList,
    OptimizerResult,
    PartnerHistory,
    PlayerGenders,
    PlayerName,
    PlayerPair,
    PlayerRatings,
    RequiredPartners,
    Gender,
    SinglesMatch,
    DoublesMatch,
)

logger = logging.getLogger("app.optimizer")


# ============================================================================
# Singles mode matching logic
# ============================================================================
def generate_singles_round(
    available_players: list[PlayerName],
    num_courts: int,
    player_ratings: PlayerRatings,
    player_genders: PlayerGenders,
    historical_partners: PartnerHistory,
    female_singles_penalty: float = 0,
    weights: dict[str, float] | None = None,
) -> OptimizerResult:
    """
    Generates a singles round with 1v1 matches.

    Uses simpler optimization focusing on skill balance and opponent history.
    The female_singles_penalty reduces each female player's effective rating for power balance.

    Args:
        available_players: List of player names available to play
        num_courts: Number of courts to fill. If more courts are requested than
            players can fill, the optimizer will auto-reduce to the maximum
            feasible number of courts.
        player_ratings: Dict mapping player names to their normalized ratings
        player_genders: Dict mapping player names to 'M' or 'F'
        historical_partners: Dict tracking how often player pairs have faced each other
        female_singles_penalty: Rating adjustment for female players (typically negative)
        weights: Dict with 'skill', 'power', 'pairing' weight values

    Returns:
        OptimizerResult with matches and updated partner history
    """
    if weights is None:
        weights = {"skill": 1.0, "power": 1.0, "pairing": 1.0}

    # Auto-reduce courts if not enough players
    max_courts = len(available_players) // 2
    num_courts = min(num_courts, max_courts)

    if num_courts == 0:
        return OptimizerResult(matches=[], partner_history=historical_partners)

    # Apply female penalty to female players' ratings (using normalized values for math)
    normalized_adjusted: PlayerRatings = {}
    for p in available_players:
        if player_genders[p] == Gender.FEMALE:
            normalized_adjusted[p] = (
                player_ratings[p] + female_singles_penalty
            )  # female_singles_penalty is relative to 0-5 scale
        else:
            normalized_adjusted[p] = player_ratings[p]

    prob = pulp.LpProblem("Badminton_Singles_Optimizer", pulp.LpMinimize)

    # x: Binary variable indicating if a player is on a court
    x = pulp.LpVariable.dicts(
        "OnCourt", (available_players, range(num_courts)), cat="Binary"
    )

    # For singles, we track opponents (not partners)
    player_pairs = list(combinations(sorted(available_players), 2))
    o = pulp.LpVariable.dicts(
        "Opponents", (player_pairs, range(num_courts)), cat="Binary"
    )

    # Skill balance variables (using normalized values based on the 0-5 contract)
    max_rating_on_court = pulp.LpVariable.dicts("MaxRatingOnCourt", range(num_courts))
    min_rating_on_court = pulp.LpVariable.dicts("MinRatingOnCourt", range(num_courts))
    total_skill_objective = pulp.lpSum(
        max_rating_on_court[c] - min_rating_on_court[c] for c in range(num_courts)
    )

    # Opponent history objective (minimize playing same opponents)
    total_pairing_objective = pulp.lpSum(
        o[pair][c] * historical_partners.get(tuple(sorted(pair)), 0)
        for pair in player_pairs
        for c in range(num_courts)
    )

    prob += (
        weights["skill"] * total_skill_objective
        + weights["pairing"] * total_pairing_objective
    ), "Minimize_Weighted_Objectives"

    # Constraints: exactly 2 players per court
    for c in range(num_courts):
        prob += pulp.lpSum(x[p][c] for p in available_players) == 2

    # Each player plays at most once
    for p in available_players:
        prob += pulp.lpSum(x[p][c] for c in range(num_courts)) <= 1

    # Total players on all courts
    prob += (
        pulp.lpSum(x[p][c] for p in available_players for c in range(num_courts))
        == num_courts * 2
    )

    # Link opponent variables
    for p1, p2 in player_pairs:
        for c in range(num_courts):
            prob += o[(p1, p2)][c] <= x[p1][c]
            prob += o[(p1, p2)][c] <= x[p2][c]
            prob += o[(p1, p2)][c] >= x[p1][c] + x[p2][c] - 1

    # Skill balance constraints
    for c in range(num_courts):
        for p in available_players:
            prob += max_rating_on_court[c] >= normalized_adjusted[
                p
            ] - OPTIMIZER_BIG_M * (1 - x[p][c])
            prob += min_rating_on_court[c] <= normalized_adjusted[
                p
            ] + OPTIMIZER_BIG_M * (1 - x[p][c])

    # Solve
    solver = pulp.GUROBI(msg=False, timeLimit=10)
    prob.solve(solver)

    if prob.status == pulp.LpStatusInfeasible:
        logger.error(
            "No optimal solution found for singles. Status: %s",
            pulp.LpStatus[prob.status],
        )
        return OptimizerResult(matches=None, partner_history=historical_partners)

    # Log debug info
    log_optimizer_debug(
        logger=logger,
        num_courts=num_courts,
        max_rating_on_court=max_rating_on_court,
        min_rating_on_court=min_rating_on_court,
        total_skill_objective=pulp.value(total_skill_objective),
        total_pairing_objective=pulp.value(total_pairing_objective),
        objective_value=pulp.value(prob.objective),
    )

    # Build matches
    matches = []
    updated_historical_partners = historical_partners.copy()

    for c in range(num_courts):
        court_players = [p for p in available_players if x[p][c].value() > 0.5]

        if len(court_players) == 2:
            p1, p2 = sorted(court_players)
            pair_key = tuple(sorted((p1, p2)))
            updated_historical_partners[pair_key] = (
                updated_historical_partners.get(pair_key, 0) + 1
            )

            matches.append(
                SinglesMatch(
                    court=c + 1,
                    player_1=p1,
                    player_2=p2,
                )
            )

    return OptimizerResult(matches=matches, partner_history=updated_historical_partners)


# ============================================================================
# Doubles mode and main entry point
# ============================================================================
def generate_one_round(
    player_ratings: PlayerRatings,
    player_genders: PlayerGenders,
    players_to_rest: set[PlayerName],
    num_courts: int,
    historical_partners: PartnerHistory,
    female_female_team_penalty: float = 0,
    mixed_gender_team_penalty: float = 0,
    female_singles_penalty: float = 0,
    players_per_court: int = 4,
    weights: dict[str, float] | None = None,
    is_doubles: bool = True,
    required_partners: RequiredPartners | None = None,
) -> OptimizerResult:
    """
    Generates a single, optimized round of badminton matches.

    Supports both Doubles (4 players per court) and Singles (2 players per court).

    Args:
        player_ratings: Dict mapping player names to normalized ratings (0-5 scale)
        player_genders: Dict mapping player names to 'M' or 'F'
        players_to_rest: Set of player names who should rest this round
        num_courts: Number of courts to fill. If more courts are requested than
            available players can fill, the optimizer will auto-reduce to the
            maximum feasible number. Check len(result.matches) to see actual
            courts used.
        historical_partners: Dict tracking partner history
        female_female_team_penalty: Rating adjustment for FF teams in doubles
        mixed_gender_team_penalty: Rating adjustment for MF teams in doubles
        female_singles_penalty: Rating adjustment for female players in singles
        players_per_court: Number of players per court (2 for singles, 4 for doubles)
        weights: Dict with 'skill', 'power', 'pairing' weight values
        is_doubles: True for doubles mode, False for singles mode
        required_partners: Optional dict mapping players to their required partners (doubles only)

    Returns:
        OptimizerResult with matches and updated partner history
    """
    if weights is None:
        weights = {"skill": 1.0, "power": 1.0, "pairing": 1.0}

    if required_partners is None:
        required_partners = {}

    all_players = list(player_ratings.keys())
    available_players = [p for p in all_players if p not in players_to_rest]
    random.shuffle(available_players)

    num_available = len(available_players)

    # Auto-reduce courts if not enough players
    max_courts = num_available // players_per_court
    num_courts = min(num_courts, max_courts)

    if num_courts == 0:
        return OptimizerResult(matches=[], partner_history=historical_partners)

    players_needed = num_courts * players_per_court

    # For singles mode, use simpler matching logic
    if not is_doubles:
        return generate_singles_round(
            available_players,
            num_courts,
            player_ratings,
            player_genders,
            historical_partners,
            female_singles_penalty,
            weights,
        )

    prob = pulp.LpProblem("Badminton_Full_Optimizer", pulp.LpMinimize)

    # x: Binary variable indicating if a player is on a court
    x = pulp.LpVariable.dicts(
        "OnCourt", (available_players, range(num_courts)), cat="Binary"
    )
    # t: Binary variable indicating if a pair of players are partners on a court
    player_pairs = list(combinations(sorted(available_players), 2))
    t = pulp.LpVariable.dicts(
        "Partners", (player_pairs, range(num_courts)), cat="Binary"
    )

    max_rating_on_court = pulp.LpVariable.dicts("MaxRatingOnCourt", range(num_courts))
    min_rating_on_court = pulp.LpVariable.dicts("MinRatingOnCourt", range(num_courts))
    total_skill_objective = pulp.lpSum(
        max_rating_on_court[c] - min_rating_on_court[c] for c in range(num_courts)
    )

    max_team_power = pulp.LpVariable.dicts("MaxTeamPower", range(num_courts))
    min_team_power = pulp.LpVariable.dicts("MinTeamPower", range(num_courts))
    total_power_objective = pulp.lpSum(
        max_team_power[c] - min_team_power[c] for c in range(num_courts)
    )

    # Exclude required partner pairs from pairing history penalty (they're forced anyway)
    locked_pairs_set: set[tuple[str, str]] = set()
    for player, partners in required_partners.items():
        for partner in partners:
            locked_pairs_set.add(tuple(sorted((player, partner))))
    total_pairing_objective = pulp.lpSum(
        t[pair][c] * historical_partners.get(tuple(sorted(pair)), 0)
        for pair in player_pairs
        for c in range(num_courts)
        if tuple(sorted(pair)) not in locked_pairs_set
    )

    prob += (
        weights["skill"] * total_skill_objective
        + weights["power"] * total_power_objective
        + weights["pairing"] * total_pairing_objective
    ), "Minimize_Weighted_Objectives"

    for c in range(num_courts):
        prob += pulp.lpSum(x[p][c] for p in available_players) == players_per_court
    for p in available_players:
        prob += pulp.lpSum(x[p][c] for c in range(num_courts)) <= 1
    prob += (
        pulp.lpSum(x[p][c] for p in available_players for c in range(num_courts))
        == players_needed
    )

    for p1, p2 in player_pairs:
        for c in range(num_courts):
            prob += t[(p1, p2)][c] <= x[p1][c]
            prob += t[(p1, p2)][c] <= x[p2][c]
    for p in available_players:
        for c in range(num_courts):
            prob += (
                pulp.lpSum(t[pair][c] for pair in player_pairs if p in pair) == x[p][c]
            )

    # Hard constraints for required partners:
    # If a player plays, they must be with a required partner,
    # OR their required partners must be "validly occupied" with another mutual teammate.
    for player, partners in required_partners.items():
        if player not in available_players:
            continue

        # Filter to only available partners
        active_partners = [p for p in partners if p in available_players]

        if active_partners:
            for c in range(num_courts):
                satisfaction_terms = []
                for p in active_partners:
                    # 1. Direct partnership: Player is with Partner p
                    satisfaction_terms.append(t[tuple(sorted((player, p)))][c])

                    # 2. Indirect excuse: Partner p is with another Teammate k
                    # If my partner is playing with another valid teammate, I am excused.
                    p_partners = required_partners.get(p, set())
                    for k in p_partners:
                        if k != player and k in available_players:
                            # Note: This may add duplicate terms if the friendship graph is dense
                            # (e.g. triangle), but for boolean LP constraints (sum >= 1),
                            # redundancy is harmless and ensures correctness.
                            satisfaction_terms.append(t[tuple(sorted((p, k)))][c])

                prob += pulp.lpSum(satisfaction_terms) >= x[player][c]

    for c in range(num_courts):
        for p in available_players:
            # Robust Big-M constraints for ratings
            # If x=1: max >= rating. If x=0: max >= rating - OPTIMIZER_BIG_M (trivially true)
            prob += max_rating_on_court[c] >= player_ratings[p] - OPTIMIZER_BIG_M * (
                1 - x[p][c]
            )
            # If x=1: min <= rating. If x=0: min <= rating + OPTIMIZER_BIG_M (trivially true)
            prob += min_rating_on_court[c] <= player_ratings[p] + OPTIMIZER_BIG_M * (
                1 - x[p][c]
            )

        for p1, p2 in player_pairs:
            pair_power = player_ratings[p1] + player_ratings[p2]
            # Apply penalty if both players are female
            if (
                player_genders[p1] == Gender.FEMALE
                and player_genders[p2] == Gender.FEMALE
            ):
                pair_power += female_female_team_penalty
            # Apply penalty if pair is mixed (one male, one female)
            elif {player_genders[p1], player_genders[p2]} == {
                Gender.MALE,
                Gender.FEMALE,
            }:
                pair_power += mixed_gender_team_penalty

            # Robust Big-M constraints for team power
            prob += max_team_power[c] >= pair_power - OPTIMIZER_BIG_M * (
                1 - t[(p1, p2)][c]
            )
            prob += min_team_power[c] <= pair_power + OPTIMIZER_BIG_M * (
                1 - t[(p1, p2)][c]
            )

    # Use the Gurobi solver with a 10s time limit.
    solver = pulp.GUROBI(
        msg=False,
        timeLimit=10,
    )
    prob.solve(solver)

    if prob.status == pulp.LpStatusInfeasible:
        logger.error(
            "No optimal solution found for doubles. Status: %s",
            pulp.LpStatus[prob.status],
        )
        return OptimizerResult(matches=None, partner_history=historical_partners)

    # Log debug info
    log_optimizer_debug(
        logger=logger,
        num_courts=num_courts,
        max_rating_on_court=max_rating_on_court,
        min_rating_on_court=min_rating_on_court,
        total_skill_objective=pulp.value(total_skill_objective),
        total_pairing_objective=pulp.value(total_pairing_objective),
        objective_value=pulp.value(prob.objective),
        max_team_power=max_team_power,
        min_team_power=min_team_power,
        total_power_objective=pulp.value(total_power_objective),
    )

    matches = []
    updated_historical_partners = historical_partners.copy()
    for c in range(num_courts):
        court_players = [p for p in available_players if x[p][c].value() > 0.5]

        partnerships = []
        for p1, p2 in combinations(court_players, 2):
            pair_key = tuple(sorted((p1, p2)))
            if t[pair_key][c].value() > 0.5:
                partnerships.append(pair_key)

        if len(partnerships) == players_per_court / 2:
            for p1, p2 in partnerships:
                pair_key = tuple(sorted((p1, p2)))
                updated_historical_partners[pair_key] = (
                    updated_historical_partners.get(pair_key, 0) + 1
                )

            team1 = partnerships[0]
            team2 = partnerships[1]

            matches.append(
                DoublesMatch(
                    court=c + 1,
                    team_1=team1,
                    team_2=team2,
                )
            )

    return OptimizerResult(matches=matches, partner_history=updated_historical_partners)
