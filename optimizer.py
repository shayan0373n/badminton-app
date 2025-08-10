# optimizer.py
import pulp
from itertools import combinations
from collections import defaultdict
from utils import setup_gurobi_license

# Set up the Gurobi license
setup_gurobi_license()

# ============================================================================
# This is the core function from our previous work. It is included here
# so this script can be run as a standalone file.
# ============================================================================
def generate_one_round(
    players,
    players_to_rest,
    num_courts,
    historical_partners,
    ff_power_penalty=0,
    players_per_court=4,
    weights=None
):
    """
    Generates a single, optimized round of badminton matches.
    """
    player_ratings = {p.name: p.rating for p in players}
    player_genders = {p.name: p.gender for p in players}

    if weights is None:
        weights = {'skill': 1.0, 'power': 1.0, 'pairing': 1.0}

    all_players = sorted(list(player_ratings.keys()))
    available_players = sorted([p for p in all_players if p not in players_to_rest])
    
    num_available = len(available_players)
    players_needed = num_courts * players_per_court

    if num_available < players_needed:
        print(f"Error: Not enough players ({num_available}) for the courts ({players_needed} needed).")
        return None, historical_partners

    prob = pulp.LpProblem("Badminton_Full_Optimizer", pulp.LpMinimize)

    # x: Binary variable indicating if a player is on a court
    x = pulp.LpVariable.dicts("OnCourt", (available_players, range(num_courts)), cat='Binary')
    # t: Binary variable indicating if a pair of players are partners on a court
    player_pairs = list(combinations(available_players, 2))
    t = pulp.LpVariable.dicts("Partners", (player_pairs, range(num_courts)), cat='Binary')

    max_rating_on_court = pulp.LpVariable.dicts("MaxRatingOnCourt", range(num_courts), lowBound=0)
    min_rating_on_court = pulp.LpVariable.dicts("MinRatingOnCourt", range(num_courts), lowBound=0)
    total_skill_objective = pulp.lpSum(max_rating_on_court[c] - min_rating_on_court[c] for c in range(num_courts))

    max_team_power = pulp.LpVariable.dicts("MaxTeamPower", range(num_courts), lowBound=0)
    min_team_power = pulp.LpVariable.dicts("MinTeamPower", range(num_courts), lowBound=min(ff_power_penalty, 0))
    total_power_objective = pulp.lpSum(max_team_power[c] - min_team_power[c] for c in range(num_courts))

    total_pairing_objective = pulp.lpSum(
        t[pair][c] * historical_partners.get(tuple(sorted(pair)), 0)
        for pair in player_pairs for c in range(num_courts)
    )

    prob += (
        weights.get('skill', 1.0) * total_skill_objective +
        weights.get('power', 1.0) * total_power_objective +
        weights.get('pairing', 1.0) * total_pairing_objective
    ), "Minimize_Weighted_Objectives"

    for c in range(num_courts):
        prob += pulp.lpSum(x[p][c] for p in available_players) == players_per_court
    for p in available_players:
        prob += pulp.lpSum(x[p][c] for c in range(num_courts)) <= 1
    prob += pulp.lpSum(x[p][c] for p in available_players for c in range(num_courts)) == players_needed

    for p1, p2 in player_pairs:
        for c in range(num_courts):
            prob += t[(p1, p2)][c] <= x[p1][c]
            prob += t[(p1, p2)][c] <= x[p2][c]
    for p in available_players:
        for c in range(num_courts):
            prob += pulp.lpSum(t[pair][c] for pair in player_pairs if p in pair) == x[p][c]

    max_possible_rating = max(player_ratings.values()) if player_ratings else 0
    max_possible_team_power = 2 * max_possible_rating

    for c in range(num_courts):
        for p in available_players:
            prob += max_rating_on_court[c] >= player_ratings[p] * x[p][c]
            prob += min_rating_on_court[c] <= player_ratings[p] * x[p][c] + max_possible_rating * (1 - x[p][c])

        for p1, p2 in player_pairs:
            pair_power = player_ratings[p1] + player_ratings[p2]
            # Apply penalty if both players are female
            if player_genders[p1] == 'F' and player_genders[p2] == 'F':
                pair_power += ff_power_penalty
            prob += max_team_power[c] >= pair_power * t[(p1, p2)][c]
            prob += min_team_power[c] <= pair_power * t[(p1, p2)][c] + max_possible_team_power * (1 - t[(p1, p2)][c])

    # Use the Gurobi solver with multiple threads and a 10% relative gap tolerance.
    prob.solve(pulp.GUROBI(msg=False, timeLimit=10, threads=None))

    if prob.status == pulp.LpStatusInfeasible:
        print(f"ERROR: No optimal solution found. Status: {pulp.LpStatus[prob.status]}")
        return None, historical_partners
    
    ## DEBUG ##
    print("Max Rating on Court:", {c: max_rating_on_court[c].value() for c in range(num_courts)})
    print("Min Rating on Court:", {c: min_rating_on_court[c].value() for c in range(num_courts)})
    print("Max Team Power:", {c: max_team_power[c].value() for c in range(num_courts)})
    print("Min Team Power:", {c: min_team_power[c].value() for c in range(num_courts)})
    print("Total Skill Objective:", pulp.value(total_skill_objective))
    print("Total Power Objective:", pulp.value(total_power_objective))
    print("Total Pairing Objective:", pulp.value(total_pairing_objective))
    print("Objective Value:", pulp.value(prob.objective))
    ## END DEBUG ##
    
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
                updated_historical_partners[tuple(sorted((p1, p2)))] += 1

            team1 = partnerships[0]
            team2 = partnerships[1]
            team1_rating = player_ratings[team1[0]] + player_ratings[team1[1]]
            team2_rating = player_ratings[team2[0]] + player_ratings[team2[1]]
            
            matches.append({
                "court": c + 1,
                "team_1": team1,
                "team_2": team2,
                "team_1_power": team1_rating,
                "team_2_power": team2_rating,
                "power_diff": abs(team1_rating - team2_rating)
            })

    return matches, updated_historical_partners
