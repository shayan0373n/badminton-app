# rating.py
"""
Glicko-2 Rating System Implementation

This module implements the Glicko-2 rating algorithm for both singles and doubles matches.
For doubles, it uses the Composite Opponent Method where each player is updated against
the average rating, RD, and volatility of the opposing team.

Reference: http://www.glicko.net/glicko/glicko2.pdf
"""

import math
from dataclasses import dataclass

from constants import (
    GLICKO2_TAU,
    GLICKO2_EPSILON,
    GLICKO2_DEFAULT_RATING,
    GLICKO2_DEFAULT_RD,
    GLICKO2_DEFAULT_VOLATILITY,
    GLICKO2_SCALE,
)


@dataclass
class Glicko2Rating:
    """Represents a player's Glicko-2 rating components."""

    rating: float = GLICKO2_DEFAULT_RATING
    rd: float = GLICKO2_DEFAULT_RD
    volatility: float = GLICKO2_DEFAULT_VOLATILITY

    def to_glicko2_scale(self) -> tuple[float, float]:
        """Convert to Glicko-2 internal scale (mu, phi)."""
        mu = (self.rating - GLICKO2_DEFAULT_RATING) / GLICKO2_SCALE
        phi = self.rd / GLICKO2_SCALE
        return mu, phi

    @staticmethod
    def from_glicko2_scale(mu: float, phi: float, volatility: float) -> "Glicko2Rating":
        """Convert from Glicko-2 internal scale back to rating scale."""
        rating = mu * GLICKO2_SCALE + GLICKO2_DEFAULT_RATING
        rd = phi * GLICKO2_SCALE
        return Glicko2Rating(rating=rating, rd=rd, volatility=volatility)


def _g(phi: float) -> float:
    """Glicko-2 g function."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _e(mu: float, mu_j: float, phi_j: float) -> float:
    """Glicko-2 E function (expected score)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _compute_variance(mu: float, opponents: list[tuple[float, float]]) -> float:
    """
    Compute the estimated variance of the player's rating.

    Args:
        mu: Player's rating on Glicko-2 scale
        opponents: List of (mu_j, phi_j) tuples for each opponent

    Returns:
        Variance v
    """
    if not opponents:
        return float("inf")

    total = 0.0
    for mu_j, phi_j in opponents:
        g_phi = _g(phi_j)
        e_val = _e(mu, mu_j, phi_j)
        total += g_phi * g_phi * e_val * (1.0 - e_val)

    return 1.0 / total if total > 0 else float("inf")


def _compute_delta(
    mu: float, opponents: list[tuple[float, float]], outcomes: list[float], v: float
) -> float:
    """
    Compute the estimated improvement in rating.

    Args:
        mu: Player's rating on Glicko-2 scale
        opponents: List of (mu_j, phi_j) tuples
        outcomes: List of game outcomes (1=win, 0.5=draw, 0=loss)
        v: Variance from _compute_variance

    Returns:
        Delta value
    """
    total = 0.0
    for (mu_j, phi_j), s in zip(opponents, outcomes):
        total += _g(phi_j) * (s - _e(mu, mu_j, phi_j))

    return v * total


def _compute_new_volatility(sigma: float, phi: float, v: float, delta: float) -> float:
    """
    Compute the new volatility using the iterative algorithm from Glicko-2.

    Uses the Illinois algorithm variant for finding the root.
    """
    a = math.log(sigma * sigma)

    def f(x: float) -> float:
        ex = math.exp(x)
        phi_sq = phi * phi
        d_sq = delta * delta

        num1 = ex * (d_sq - phi_sq - v - ex)
        denom1 = 2.0 * (phi_sq + v + ex) ** 2

        num2 = x - a
        denom2 = GLICKO2_TAU * GLICKO2_TAU

        return num1 / denom1 - num2 / denom2

    # Set initial values for A and B
    A = a

    if delta * delta > phi * phi + v:
        B = math.log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * GLICKO2_TAU) < 0:
            k += 1
        B = a - k * GLICKO2_TAU

    # Iteratively find the value
    fA = f(A)
    fB = f(B)

    iterations = 0
    max_iterations = 100

    while abs(B - A) > GLICKO2_EPSILON and iterations < max_iterations:
        C = A + (A - B) * fA / (fB - fA)
        fC = f(C)

        if fC * fB <= 0:
            A = B
            fA = fB
        else:
            fA = fA / 2.0

        B = C
        fB = fC
        iterations += 1

    return math.exp(A / 2.0)


def update_rating(
    player: Glicko2Rating, opponents: list[Glicko2Rating], outcomes: list[float]
) -> Glicko2Rating:
    """
    Update a player's rating based on game outcomes.

    Args:
        player: The player's current rating
        opponents: List of opponent ratings
        outcomes: List of outcomes (1.0=win, 0.5=draw, 0.0=loss) for each opponent

    Returns:
        New Glicko2Rating with updated values
    """
    if not opponents or not outcomes:
        # No games played, just increase RD
        mu, phi = player.to_glicko2_scale()
        new_phi = math.sqrt(phi * phi + player.volatility * player.volatility)
        return Glicko2Rating.from_glicko2_scale(mu, new_phi, player.volatility)

    # Convert to Glicko-2 scale
    mu, phi = player.to_glicko2_scale()
    sigma = player.volatility

    # Convert opponents
    opp_data = [opp.to_glicko2_scale() for opp in opponents]

    # Step 3: Compute variance
    v = _compute_variance(mu, opp_data)

    # Step 4: Compute delta
    delta = _compute_delta(mu, opp_data, outcomes, v)

    # Step 5: Compute new volatility
    new_sigma = _compute_new_volatility(sigma, phi, v, delta)

    # Step 6: Update phi to new pre-rating period value
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)

    # Step 7: Update phi and mu
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)

    # Compute new mu
    total = 0.0
    for (mu_j, phi_j), s in zip(opp_data, outcomes):
        total += _g(phi_j) * (s - _e(mu, mu_j, phi_j))
    new_mu = mu + new_phi * new_phi * total

    return Glicko2Rating.from_glicko2_scale(new_mu, new_phi, new_sigma)


def create_composite_opponent(players: list[Glicko2Rating]) -> Glicko2Rating:
    """
    Create a composite opponent from multiple players (for doubles).
    Averages rating, RD, and volatility.

    Args:
        players: List of player ratings to combine

    Returns:
        A composite Glicko2Rating representing the team
    """
    if not players:
        return Glicko2Rating()

    avg_rating = sum(p.rating for p in players) / len(players)
    avg_rd = sum(p.rd for p in players) / len(players)
    avg_volatility = sum(p.volatility for p in players) / len(players)

    return Glicko2Rating(rating=avg_rating, rd=avg_rd, volatility=avg_volatility)


def process_session_matches(
    matches: list[dict], players: dict[str, "Player"], is_doubles: bool
) -> dict[str, Glicko2Rating]:
    """
    Process all matches from a session and calculate new ratings for all players.

    Args:
        matches: List of match dictionaries from database
        players: Dict mapping player names to Player objects
        is_doubles: True for doubles mode, False for singles mode

    Returns:
        Dict mapping player names to their new Glicko2Rating
    """
    # Build current ratings for all players
    current_ratings: dict[str, Glicko2Rating] = {}
    for name, player in players.items():
        current_ratings[name] = Glicko2Rating(
            rating=player.elo, rd=player.deviation, volatility=player.volatility
        )

    # Collect all opponents and outcomes for each player
    player_games: dict[str, tuple[list[Glicko2Rating], list[float]]] = {
        name: ([], []) for name in players
    }

    for match in matches:
        if not is_doubles:
            p1 = match["player_1"]
            p2 = match["player_2"]
            winner_side = match["winner_side"]

            if p1 in player_games and p2 in player_games:
                # Player 1's perspective
                player_games[p1][0].append(current_ratings[p2])
                player_games[p1][1].append(1.0 if winner_side == 1 else 0.0)

                # Player 2's perspective
                player_games[p2][0].append(current_ratings[p1])
                player_games[p2][1].append(1.0 if winner_side == 2 else 0.0)
        else:
            # Doubles - use composite opponent
            team1 = [match["player_1"], match["player_2"]]
            team2 = [match["player_3"], match["player_4"]]
            winner_side = match["winner_side"]

            # Create composite opponents
            team1_ratings = [current_ratings[p] for p in team1 if p in current_ratings]
            team2_ratings = [current_ratings[p] for p in team2 if p in current_ratings]

            if team1_ratings and team2_ratings:
                composite_team1 = create_composite_opponent(team1_ratings)
                composite_team2 = create_composite_opponent(team2_ratings)

                # Team 1 players vs composite Team 2
                for p in team1:
                    if p in player_games:
                        player_games[p][0].append(composite_team2)
                        player_games[p][1].append(1.0 if winner_side == 1 else 0.0)

                # Team 2 players vs composite Team 1
                for p in team2:
                    if p in player_games:
                        player_games[p][0].append(composite_team1)
                        player_games[p][1].append(1.0 if winner_side == 2 else 0.0)

    # Calculate new ratings for each player
    new_ratings: dict[str, Glicko2Rating] = {}
    for name, (opponents, outcomes) in player_games.items():
        new_ratings[name] = update_rating(current_ratings[name], opponents, outcomes)

    return new_ratings
