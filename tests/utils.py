import random
from typing import Generator

from app_types import Gender, OptimizerResult, RequiredPartners
from optimizer import generate_one_round
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
    player_ratings: dict[str, float],
    player_genders: dict[str, Gender],
    num_courts: int,
    num_rounds: int = 10,
    required_partners: RequiredPartners | None = None,
) -> Generator[tuple[int, OptimizerResult], None, None]:
    """
    Generator that runs the optimizer for multiple rounds.

    Simulates real usage by:
    - Maintaining historical_partners state between rounds
    - Automatically rotating which players rest based on court capacity
    - Moving rested players to end of rotation queue after each round

    Args:
        player_ratings: Dict mapping player names to ratings
        player_genders: Dict mapping player names to Gender
        num_courts: Number of courts to fill each round
        num_rounds: Number of rounds to run (default 10)
        required_partners: Optional partner constraints

    Yields:
        tuple: (round_number, OptimizerResult)
    """
    historical_partners = {}
    rest_queue = RestRotationQueue(list(player_ratings.keys()))
    players_per_court = 4  # doubles

    for round_num in range(num_rounds):
        # Determine who rests using the shared rotation logic
        players_to_rest = rest_queue.get_resting_players(num_courts, players_per_court)

        # Calculate active courts
        total_players = len(player_ratings)
        max_courts = total_players // players_per_court
        active_courts = min(num_courts, max_courts)

        result = generate_one_round(
            player_ratings=player_ratings,
            player_genders=player_genders,
            players_to_rest=players_to_rest,
            num_courts=active_courts,
            historical_partners=historical_partners,
            is_doubles=True,
            required_partners=required_partners,
        )

        yield round_num, result

        if result.success:
            historical_partners = result.partner_history
            rest_queue.rotate_after_round(players_to_rest)
