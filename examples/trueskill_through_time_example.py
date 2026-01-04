"""
TrueSkillThroughTime Library Example (v2.0.0)

This script demonstrates the key features of the TrueSkillThroughTime library,
showing how it can be used for rating players in a badminton doubles context.

Key Concepts:
- Gaussian: Represents a player's skill as a normal distribution (mu=mean, sigma=uncertainty)
- Player: Wraps a Gaussian with temporal dynamics (beta=performance variance, gamma=skill drift)
- Game: Models a single match between teams
- History: Tracks multiple games over time and computes skill evolution

Install with: pip install -e ./TrueSkillThroughTime.py  (from cloned repo for v2.0.0)
"""

from trueskillthroughtime import History, Player, Gaussian, Game


def example_1_basic_game():
    """
    Example 1: Basic single game between two doubles teams.

    Shows how evidence (probability of outcome) and posteriors work.
    """
    print("\n" + "=" * 60)
    print("Example 1: Basic Doubles Game")
    print("=" * 60)

    # Create four players with default skill (mu=0, sigma=6)
    player_a = Player()  # Team 1
    player_b = Player()
    player_c = Player()  # Team 2
    player_d = Player()

    # Create teams and a game (first team wins by default ordering)
    team_1 = [player_a, player_b]  # Winners
    team_2 = [player_c, player_d]  # Losers

    game = Game([team_1, team_2])

    print(f"Prior probability that Team 1 wins: {game.evidence:.3f}")
    print("(0.5 means both teams were equally matched)")

    # Get posterior skill estimates after the game
    posteriors = game.posteriors()
    print(f"\nPlayer A (winner) skill after game: {posteriors[0][0]}")
    print(f"Player C (loser) skill after game:  {posteriors[1][0]}")
    print("\nNotice: Winners have higher mu, losers have lower mu")


def example_2_history_with_string_names():
    """
    Example 2: Using History with player name strings.

    This is the most practical approach for a real application.
    Instead of creating Player objects, just use string identifiers.
    """
    print("\n" + "=" * 60)
    print("Example 2: History with String Player Names")
    print("=" * 60)

    # Define some doubles matches using player name strings
    # Each match: [[team1_players], [team2_players]]
    # First team is the winner
    matches = [
        [["Alice", "Bob"], ["Charlie", "Diana"]],  # Alice+Bob beat Charlie+Diana
        [["Charlie", "Eve"], ["Alice", "Frank"]],  # Charlie+Eve beat Alice+Frank
        [["Bob", "Diana"], ["Eve", "Frank"]],  # Bob+Diana beat Eve+Frank
        [["Alice", "Charlie"], ["Bob", "Eve"]],  # Alice+Charlie beat Bob+Eve
        [["Diana", "Frank"], ["Alice", "Bob"]],  # Diana+Frank beat Alice+Bob
    ]

    # Create history (gamma=0.03 is default skill drift per time unit)
    # Setting gamma=0 means skills don't change over time (useful for short tournaments)
    history = History(composition=matches, gamma=0.03)

    print("Initial TrueSkill estimates (before convergence):")
    learning_curves = history.learning_curves()
    for player in ["Alice", "Bob", "Charlie"]:
        latest = learning_curves[player][-1][1]  # Get last estimate
        print(f"  {player}: mu={latest.mu:.2f}, sigma={latest.sigma:.2f}")

    # Run convergence algorithm - this propagates information through time
    history.convergence(verbose=False)

    print("\nAfter TrueSkill Through Time convergence:")
    learning_curves = history.learning_curves()
    for player in sorted(learning_curves.keys()):
        latest = learning_curves[player][-1][1]
        print(f"  {player}: mu={latest.mu:.2f}, sigma={latest.sigma:.2f}")


def example_3_with_timestamps():
    """
    Example 3: Using explicit timestamps for matches.

    Real applications should use timestamps so the library can
    properly model skill drift over time.
    """
    print("\n" + "=" * 60)
    print("Example 3: Matches with Timestamps")
    print("=" * 60)

    # Matches with explicit timestamps (could be days, sessions, etc.)
    matches = [
        [["Alice", "Bob"], ["Charlie", "Diana"]],
        [["Charlie", "Eve"], ["Alice", "Frank"]],
        [["Bob", "Diana"], ["Eve", "Frank"]],
        [["Alice", "Charlie"], ["Bob", "Eve"]],
    ]

    # Timestamps for each match (e.g., session numbers or days)
    times = [1, 1, 2, 3]  # First two matches on day 1, etc.

    history = History(
        composition=matches,
        times=times,
        gamma=0.01,  # Smaller gamma = slower skill drift
        sigma=3.0,  # Initial uncertainty (smaller = more confident prior)
    )
    history.convergence(verbose=False)

    print("Player skills with temporal evolution:")
    learning_curves = history.learning_curves()
    for player in ["Alice", "Bob"]:
        print(f"\n{player}'s skill evolution:")
        for time, skill in learning_curves[player]:
            print(f"  Time {time}: mu={skill.mu:.2f}, sigma={skill.sigma:.2f}")


def example_4_custom_priors():
    """
    Example 4: Setting custom prior skills for players.

    Useful when you have existing rating information for some players.
    """
    print("\n" + "=" * 60)
    print("Example 4: Custom Prior Skills")
    print("=" * 60)

    matches = [
        [["Pro"], ["Beginner"]],  # Pro beats Beginner
        [["Pro"], ["Beginner"]],  # Pro beats Beginner again
        [["Beginner"], ["Pro"]],  # Upset! Beginner wins
    ]

    # Set custom priors: Pro starts with high skill, Beginner with low
    priors = {
        "Pro": Player(Gaussian(mu=3.0, sigma=1.0)),  # High skill, confident
        "Beginner": Player(Gaussian(mu=-2.0, sigma=2.0)),  # Low skill, less certain
    }

    history = History(
        composition=matches,
        priors=priors,
        gamma=0.0,  # No skill drift
    )
    history.convergence(verbose=False)

    print("After 3 matches (2 expected wins, 1 upset):")
    learning_curves = history.learning_curves()
    for player in ["Pro", "Beginner"]:
        latest = learning_curves[player][-1][1]
        print(f"  {player}: mu={latest.mu:.2f}, sigma={latest.sigma:.2f}")
    print("\nNote: The upset slightly lowered Pro's rating and raised Beginner's")


def example_5_checking_match_probability():
    """
    Example 5: Predicting match outcomes.

    After computing ratings, you can predict the probability
    of different outcomes for future matches.
    """
    print("\n" + "=" * 60)
    print("Example 5: Match Probability Prediction")
    print("=" * 60)

    # First, establish some history
    matches = [
        [["Strong1", "Strong2"], ["Weak1", "Weak2"]],
        [["Strong1", "Strong2"], ["Weak1", "Weak2"]],
        [["Strong1", "Weak1"], ["Strong2", "Weak2"]],
    ]

    history = History(composition=matches, gamma=0.0)
    history.convergence(verbose=False)

    # Get current skill estimates
    learning_curves = history.learning_curves()
    skills = {player: learning_curves[player][-1][1] for player in learning_curves}

    print("Current skill estimates:")
    for player, skill in sorted(skills.items()):
        print(f"  {player}: mu={skill.mu:.2f}, sigma={skill.sigma:.2f}")

    # Create a hypothetical future game to check probability
    future_team1 = [
        Player(skills["Strong1"]),
        Player(skills["Weak2"]),
    ]
    future_team2 = [
        Player(skills["Strong2"]),
        Player(skills["Weak1"]),
    ]

    hypothetical_game = Game([future_team1, future_team2])
    print(f"\nProbability that Strong1+Weak2 beats Strong2+Weak1:")
    print(f"  {hypothetical_game.evidence:.1%}")


def example_6_incremental_updates():
    """
    Example 6: Adding new matches to existing history.

    Version 2.0.0 feature: Use add_history() to incrementally add games
    without rebuilding the entire history.
    """
    print("\n" + "=" * 60)
    print("Example 6: Incremental History Updates (v2.0.0)")
    print("=" * 60)

    # Initial history
    initial_matches = [
        [["Alice", "Bob"], ["Charlie", "Diana"]],
    ]
    history = History(composition=initial_matches, gamma=0.03)
    history.convergence(verbose=False)

    print("After initial match:")
    lc = history.learning_curves()
    print(f"  Alice: mu={lc['Alice'][-1][1].mu:.2f}")
    print(f"  Charlie: mu={lc['Charlie'][-1][1].mu:.2f}")

    # Add more matches later using add_history()
    new_matches = [
        [["Charlie", "Diana"], ["Alice", "Bob"]],  # Revenge!
        [["Alice", "Charlie"], ["Bob", "Diana"]],
    ]

    # Use add_history to append new games (v2.0.0 feature)
    history.add_history(composition=new_matches)
    history.convergence(verbose=False)

    print("\nAfter adding 2 more matches with add_history():")
    lc = history.learning_curves()
    for player in ["Alice", "Bob", "Charlie", "Diana"]:
        print(f"  {player}: mu={lc[player][-1][1].mu:.2f}")


if __name__ == "__main__":
    print("TrueSkillThroughTime Library Examples (v2.0.0)")
    print("For Badminton Doubles Rating System")

    example_1_basic_game()
    example_2_history_with_string_names()
    example_3_with_timestamps()
    example_4_custom_priors()
    example_5_checking_match_probability()
    example_6_incremental_updates()

    print("\n" + "=" * 60)
    print("All examples complete!")
    print("=" * 60)
