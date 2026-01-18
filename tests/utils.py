import random
from typing import Generator

from app_types import Gender, OptimizerResult, RequiredPartners, TierRatings, RealSkills
from optimizer import generate_one_round
from rating_service import compute_gender_statistics, prepare_optimizer_ratings
from session_logic import Player, RestRotationQueue


def generate_random_players(n, mu_range=(10.0, 30.0), sigma=6.0):
    """
    Generates N players with names P1 to Pn, random ratings, and alternating genders.

    Args:
        n: Number of players to generate
        mu_range: Tuple of (min_mu, max_mu)
        sigma: Skill uncertainty (default 6.0)

    Returns:
        List of Player objects.
    """
    players = []
    for i in range(1, n + 1):
        name = f"P{i}"
        # Alternate genders for variety
        gender = Gender.MALE if i % 2 == 1 else Gender.FEMALE
        mu = random.uniform(*mu_range)
        players.append(Player(name=name, gender=gender, prior_mu=mu, prior_sigma=sigma))
    return players


def run_optimizer_rounds(
    players: dict[str, Player],
    num_courts: int,
    num_rounds: int = 10,
    required_partners: RequiredPartners | None = None,
) -> Generator[tuple[int, OptimizerResult], None, None]:
    """
    Generator that runs the optimizer for multiple rounds.

    Simulates real usage by:
    - Maintaining court_history state between rounds
    - Automatically rotating which players rest based on court capacity
    - Moving rested players to end of rotation queue after each round

    Args:
        players: Dict mapping player names to Player objects
        num_courts: Number of courts to fill each round
        num_rounds: Number of rounds to run (default 10)
        required_partners: Optional partner constraints

    Yields:
        tuple: (round_number, OptimizerResult)
    """
    court_history = {}
    rest_queue = RestRotationQueue(list(players.keys()))
    players_per_court = 4  # doubles

    # Compute gender stats once for all rounds
    gender_stats = compute_gender_statistics(players)
    player_genders = {name: p.gender for name, p in players.items()}

    for round_num in range(num_rounds):
        # Determine who rests using the shared rotation logic
        players_to_rest = rest_queue.get_resting_players(num_courts, players_per_court)

        # Calculate active courts
        total_players = len(players)
        max_courts = total_players // players_per_court
        active_courts = min(num_courts, max_courts)

        # Prepare ratings for optimizer
        tier_ratings, real_skills = prepare_optimizer_ratings(players, gender_stats)

        result = generate_one_round(
            tier_ratings=tier_ratings,
            real_skills=real_skills,
            player_genders=player_genders,
            players_to_rest=players_to_rest,
            num_courts=active_courts,
            court_history=court_history,
            is_doubles=True,
            required_partners=required_partners,
        )

        yield round_num, result

        if result.success:
            court_history = result.court_history
            rest_queue.rotate_after_round(players_to_rest)
