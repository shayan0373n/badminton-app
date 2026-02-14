import argparse
import random
import logging
import sys
from itertools import combinations
import pandas as pd

from constants import (
    OPTIMIZER_TIME_LIMIT,
    COURT_HISTORY_NORMALIZATION,
)
from app_types import (
    Gender,
    PlayerName,
    PlayerPair,
    RealSkills,
    TierRatings,
    PlayerGenders,
    CourtHistory,
    DoublesMatch,
)
import optimizer
import optimizer_ortools

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("compare_optimizers")

class CostEvaluator:
    @staticmethod
    def calculate_costs(matches, tier_ratings, real_skills, court_history):
        if matches is None:
            return None
        
        total_skill_spread = 0.0
        total_power_spread = 0.0
        total_pairing_cost = 0.0
        
        for match in matches:
            if isinstance(match, DoublesMatch):
                # Court players
                p1, p2 = match.team_1
                p3, p4 = match.team_2
                players = [p1, p2, p3, p4]
                
                # Skill spread (tier ratings)
                ratings = [tier_ratings[p] for p in players]
                total_skill_spread += max(ratings) - min(ratings)
                
                # Power spread (real skills)
                team1_power = (real_skills[p1] + real_skills[p2]) / 2
                team2_power = (real_skills[p3] + real_skills[p4]) / 2
                total_power_spread += abs(team1_power - team2_power)
                
                # Pairing cost (history)
                # 2 partner pairs, 4 opponent pairs
                partner_pairs = [tuple(sorted(match.team_1)), tuple(sorted(match.team_2))]
                all_pairs = list(combinations(sorted(players), 2))
                
                court_penalty = 0.0
                for pair in all_pairs:
                    pair_key = tuple(sorted(pair))
                    if pair_key in partner_pairs:
                        court_penalty += optimizer.get_partnership_penalty(pair_key, court_history)
                    else:
                        court_penalty += optimizer.get_opponent_penalty(pair_key, court_history)
                
                total_pairing_cost += court_penalty / COURT_HISTORY_NORMALIZATION
            else:
                # Singles match evaluation (if needed, but user specified 30 players/6 courts which implies doubles)
                p1 = match.player_1
                p2 = match.player_2
                players = [p1, p2]
                
                ratings = [real_skills[p] for p in players]
                total_skill_spread += max(ratings) - min(ratings)
                
                # Pairing cost
                pair_key = tuple(sorted((p1, p2)))
                total_pairing_cost += optimizer.get_opponent_penalty(pair_key, court_history)
                
        return {
            "skill_spread": total_skill_spread,
            "power_spread": total_power_spread,
            "pairing_cost": total_pairing_cost,
            "total_cost": total_skill_spread + total_power_spread + total_pairing_cost
        }

def generate_random_players(num_players):
    players = []
    tier_ratings = {}
    real_skills = {}
    player_genders = {}
    
    for i in range(num_players):
        name = f"Player_{i+1:02d}"
        players.append(name)
        # Ratings between 1.0 and 5.0
        rating = random.uniform(1.0, 5.0)
        tier_ratings[name] = rating
        real_skills[name] = rating
        player_genders[name] = random.choice([Gender.MALE, Gender.FEMALE])
        
    return players, tier_ratings, real_skills, player_genders

def main():
    parser = argparse.ArgumentParser(description="Compare Badminton Optimizers")
    parser.add_argument("-t", "--time", type=float, default=OPTIMIZER_TIME_LIMIT, help=f"Solver time limit in seconds (default: {OPTIMIZER_TIME_LIMIT})")
    parser.add_argument("-r", "--rounds", type=int, default=10, help="Number of rounds to simulate (default: 10)")
    parser.add_argument("-p", "--players", type=int, default=30, help="Number of players (default: 30)")
    parser.add_argument("-c", "--courts", type=int, default=6, help="Number of courts (default: 6)")
    
    # Custom weights (must be integers)
    parser.add_argument("--w_skill", type=int, default=1, help="Weight for Skill Spread (default: 1)")
    parser.add_argument("--w_power", type=int, default=1, help="Weight for Power Spread (default: 1)")
    parser.add_argument("--w_pairing", type=int, default=1, help="Weight for Pairing Cost (default: 1)")
    
    args = parser.parse_args()
    
    weights = {
        "skill": args.w_skill,
        "power": args.w_power,
        "pairing": args.w_pairing
    }
    
    random.seed(42) # For reproducibility of player pool
    players, tier_ratings, real_skills, player_genders = generate_random_players(args.players)
    
    logger.info(f"Starting comparison: {args.players} players, {args.courts} courts, {args.rounds} rounds, {args.time}s limit")
    logger.info(f"Weights: Skill={args.w_skill}, Power={args.w_power}, Pairing={args.w_pairing}")
    
    # Initialize separate histories and totals
    gurobi_history = {}
    ortools_history = {}
    gurobi_total = {"skill_spread": 0.0, "power_spread": 0.0, "pairing_cost": 0.0, "total_cost": 0.0}
    ortools_total = {"skill_spread": 0.0, "power_spread": 0.0, "pairing_cost": 0.0, "total_cost": 0.0}
    
    # Print results header
    print("\nComparison Results (Reporting live):")
    print(f"{'Round':<6} | {'Backend':<10} | {'Skill Spread':<12} | {'Power Spread':<12} | {'Pairing Cost':<12} | {'Total Cost':<12}")
    print("-" * 85)
    
    for r in range(args.rounds):
        # Ensure identical player rest selection for both backends
        round_seed = 1000 + r
        random.seed(round_seed)
        
        players_to_rest = set()
        if len(players) > args.courts * 4:
            players_to_rest = set(random.sample(players, len(players) - args.courts * 4))
            
        # 1. Gurobi Round
        random.seed(round_seed) # Ensure identical shuffle inside optimizer
        g_result = optimizer.generate_one_round(
            tier_ratings=tier_ratings,
            real_skills=real_skills,
            player_genders=player_genders,
            players_to_rest=players_to_rest,
            num_courts=args.courts,
            court_history=gurobi_history,
            time_limit=args.time,
            weights=weights
        )
        
        if g_result.success:
            g_costs = CostEvaluator.calculate_costs(g_result.matches, tier_ratings, real_skills, gurobi_history)
            gurobi_history = g_result.court_history
            for k in gurobi_total: gurobi_total[k] += g_costs[k]
            print(f"{r+1:<6} | {'Gurobi':<10} | {g_costs['skill_spread']:<12.2f} | {g_costs['power_spread']:<12.2f} | {g_costs['pairing_cost']:<12.2f} | {g_costs['total_cost']:<12.2f}")
        else:
            print(f"{r+1:<6} | {'Gurobi':<10} | {'FAILED':<12} | {'FAILED':<12} | {'FAILED':<12} | {'FAILED':<12}")

        # 2. OR-Tools Round
        random.seed(round_seed) # Ensure identical shuffle inside optimizer
        o_result = optimizer_ortools.generate_one_round(
            tier_ratings=tier_ratings,
            real_skills=real_skills,
            player_genders=player_genders,
            players_to_rest=players_to_rest,
            num_courts=args.courts,
            court_history=ortools_history,
            time_limit=args.time,
            weights=weights
        )
        
        if o_result.success:
            o_costs = CostEvaluator.calculate_costs(o_result.matches, tier_ratings, real_skills, ortools_history)
            ortools_history = o_result.court_history
            for k in ortools_total: ortools_total[k] += o_costs[k]
            print(f"{'':<6} | {'OR-Tools':<10} | {o_costs['skill_spread']:<12.2f} | {o_costs['power_spread']:<12.2f} | {o_costs['pairing_cost']:<12.2f} | {o_costs['total_cost']:<12.2f}")
        else:
            print(f"{'':<6} | {'OR-Tools':<10} | {'FAILED':<12} | {'FAILED':<12} | {'FAILED':<12} | {'FAILED':<12}")
        
        print("-" * 85)
        sys.stdout.flush() # Force print to terminal immediately
        
    print(f"{'TOTAL':<6} | {'Gurobi':<10} | {gurobi_total['skill_spread']:<12.2f} | {gurobi_total['power_spread']:<12.2f} | {gurobi_total['pairing_cost']:<12.2f} | {gurobi_total['total_cost']:<12.2f}")
    print(f"{'TOTAL':<6} | {'OR-Tools':<10} | {ortools_total['skill_spread']:<12.2f} | {ortools_total['power_spread']:<12.2f} | {ortools_total['pairing_cost']:<12.2f} | {ortools_total['total_cost']:<12.2f}")

if __name__ == "__main__":
    main()
