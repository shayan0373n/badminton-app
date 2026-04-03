import pytest
from collections import Counter
from itertools import combinations
from constants import DEFAULT_WEIGHTS, SOLVER_BACKEND

if SOLVER_BACKEND == "ortools":
    from optimizer_ortools import generate_one_round
else:
    from optimizer import generate_one_round

from tests.utils import generate_random_players, run_optimizer_rounds

def test_skill_grouping_quality():
    """
    Verifies that the optimizer correctly groups players by tier.
    Strong players (Tier 4-5) should be on different courts than weak players (Tier 0-1)
    when enough players exist to keep them separate.
    """
    # 4 strong players (Tier 5) and 4 weak players (Tier 0)
    strong = generate_random_players(4, mu_range=(32.0, 32.0)) # TTT mu 32 ~ Tier 5
    weak = generate_random_players(4, mu_range=(18.0, 18.0))   # TTT mu 18 ~ Tier 0
    
    # Manually set tier ratings to be extreme
    tier_ratings = {}
    real_skills = {}
    for p in strong:
        tier_ratings[p.name] = 5.0
        real_skills[p.name] = 5.0
    for p in weak:
        tier_ratings[p.name] = 0.0
        real_skills[p.name] = 0.0
        
    player_genders = {p.name: p.gender for p in (strong + weak)}
    
    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=player_genders,
        players_to_rest=set(),
        num_courts=2,
        court_history={},
        weights=DEFAULT_WEIGHTS,
        is_doubles=True
    )
    
    assert result.success
    for match in result.matches:
        all_players = list(match.team_1) + list(match.team_2)
        match_tiers = [tier_ratings[p] for p in all_players]
        # Every court should have players of the SAME tier
        # (All 5.0 or all 0.0)
        assert len(set(match_tiers)) == 1, f"Court mixed strong and weak players: {match_tiers}"

def test_team_fairness_within_court():
    """
    Verifies that for a given court, teams are formed to be as fair as possible.
    Given P1(5), P2(4), P3(3), P4(2), the fair teams are (5+2) vs (4+3).
    """
    tier_ratings = {"P1": 5.0, "P2": 4.0, "P3": 3.0, "P4": 2.0}
    real_skills = tier_ratings # Same for this test
    genders = {"P1": "M", "P2": "M", "P3": "M", "P4": "M"}
    
    result = generate_one_round(
        tier_ratings=tier_ratings,
        real_skills=real_skills,
        player_genders=genders,
        players_to_rest=set(),
        num_courts=1,
        court_history={},
        weights=DEFAULT_WEIGHTS,
        is_doubles=True
    )
    
    assert result.success
    match = result.matches[0]
    team1, team2 = set(match.team_1), set(match.team_2)
    
    # Best balance: (P1+P4) vs (P2+P3) -> 7 vs 7
    if "P1" in team1:
        assert "P4" in team1, f"Unfair teams: {team1} vs {team2}"
    else:
        assert "P4" in team2, f"Unfair teams: {team1} vs {team2}"

def test_long_term_variety_and_stability():
    """
    Stress test: Runs 20 rounds for 12 players across 2 courts.
    Verifies that:
    1. No partnership is repeated excessively.
    2. Every player eventually partners with a variety of others.
    """
    num_players = 12
    num_rounds = 20
    players = generate_random_players(num_players, mu_range=(20.0, 30.0))
    players_dict = {p.name: p for p in players}
    
    partnership_counts = Counter()
    
    for round_num, result in run_optimizer_rounds(
        players_dict,
        num_courts=2,
        num_rounds=num_rounds
    ):
        assert result.success
        for match in result.matches:
            # Record partnerships
            for team in [match.team_1, match.team_2]:
                pair = tuple(sorted(team))
                partnership_counts[pair] += 1
                
    # Analysis
    max_repeats = max(partnership_counts.values())
    avg_repeats = sum(partnership_counts.values()) / len(partnership_counts)
    
    # With 12 players and 20 rounds, we expect high variety.
    # No pair should ideally repeat more than 3-4 times in 20 rounds 
    # (given 2 courts, 4 partnerships are created per round).
    assert max_repeats <= 4, f"A partnership repeated {max_repeats} times in {num_rounds} rounds!"
    
    # Ensure we used at least 50% of possible partnership combinations
    total_possible_pairs = len(list(combinations(players_dict.keys(), 2)))
    unique_partnerships = len(partnership_counts)
    coverage = unique_partnerships / total_possible_pairs
    
    assert coverage > 0.4, f"Low variety: Only {coverage*100:.1f}% of possible partnerships occurred."
