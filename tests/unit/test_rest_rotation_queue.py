import pytest
from collections import Counter

from session_logic import RestRotationQueue


class TestRestRotationQueue:
    """Tests for the RestRotationQueue class."""

    def test_initialization_shuffles_by_default(self):
        """Queue should shuffle players on init by default."""
        players = ["P1", "P2", "P3", "P4", "P5"]

        # Run multiple times - at least one should differ from input order
        # (vanishingly small chance all 10 runs preserve order)
        orders_differ = False
        for _ in range(10):
            queue = RestRotationQueue(players)
            resting = queue.get_resting_players(num_courts=1, players_per_court=4)
            if resting != {"P1"}:  # First player in original order
                orders_differ = True
                break

        assert orders_differ, "Queue should shuffle by default"

    def test_initialization_no_shuffle(self):
        """Queue should preserve order when shuffle=False."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        queue = RestRotationQueue(players, shuffle=False)

        # With 5 players and 1 court, 1 player rests (first in queue)
        resting = queue.get_resting_players(num_courts=1, players_per_court=4)
        assert resting == {"P1"}

    def test_get_resting_players_calculates_correctly(self):
        """Should calculate correct number of resting players based on courts."""
        players = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9"]
        queue = RestRotationQueue(players, shuffle=False)

        # 9 players, 2 courts = 8 play, 1 rests
        resting = queue.get_resting_players(num_courts=2, players_per_court=4)
        assert len(resting) == 1
        assert resting == {"P1"}

        # 9 players, 1 court = 4 play, 5 rest
        resting = queue.get_resting_players(num_courts=1, players_per_court=4)
        assert len(resting) == 5
        assert resting == {"P1", "P2", "P3", "P4", "P5"}

    def test_get_resting_players_more_courts_than_possible(self):
        """Should cap courts at what's possible with available players."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        queue = RestRotationQueue(players, shuffle=False)

        # 5 players can only fill 1 court (4 players), even if 3 courts requested
        resting = queue.get_resting_players(num_courts=3, players_per_court=4)
        assert len(resting) == 1  # 5 - 4 = 1 rests

    def test_fair_rotation_all_players_rest_once(self):
        """After N rounds with N players (and 1 resting per round), all should rest once."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        queue = RestRotationQueue(players, shuffle=False)

        rest_counts = Counter()

        for _ in range(5):  # 5 rounds for 5 players
            resting = queue.get_resting_players(num_courts=1, players_per_court=4)
            assert len(resting) == 1, "Exactly 1 player should rest per round"
            rest_counts.update(resting)
            queue.rotate_after_round(resting)

        # Each player should have rested exactly once
        for player in players:
            assert (
                rest_counts[player] == 1
            ), f"{player} rested {rest_counts[player]} times, expected 1"

    def test_fair_rotation_multiple_resting(self):
        """With 6 players and 1 court, 2 rest per round. After 3 rounds, all rest once."""
        players = ["P1", "P2", "P3", "P4", "P5", "P6"]
        queue = RestRotationQueue(players, shuffle=False)

        rest_counts = Counter()

        for _ in range(3):  # 6 players / 2 resting per round = 3 rounds
            resting = queue.get_resting_players(num_courts=1, players_per_court=4)
            assert len(resting) == 2, "Exactly 2 players should rest per round"
            rest_counts.update(resting)
            queue.rotate_after_round(resting)

        # Each player should have rested exactly once
        for player in players:
            assert (
                rest_counts[player] == 1
            ), f"{player} rested {rest_counts[player]} times, expected 1"

    def test_add_player(self):
        """New player should be added to end of queue."""
        players = ["P1", "P2", "P3", "P4"]
        queue = RestRotationQueue(players, shuffle=False)

        # Initially no one rests (4 players, 1 court, 4 per court)
        resting = queue.get_resting_players(num_courts=1, players_per_court=4)
        assert len(resting) == 0

        # Add player - they go to end of queue
        queue.add_player("P5")

        # Now 5 players, 1 rests - should be P1 (front of queue)
        resting = queue.get_resting_players(num_courts=1, players_per_court=4)
        assert resting == {"P1"}

    def test_add_player_duplicate_ignored(self):
        """Adding existing player should be silently ignored."""
        players = ["P1", "P2", "P3", "P4"]
        queue = RestRotationQueue(players, shuffle=False)

        queue.add_player("P1")  # Already exists
        assert len(queue) == 4  # No change

    def test_remove_player(self):
        """Removing player should shrink queue."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        queue = RestRotationQueue(players, shuffle=False)

        queue.remove_player("P1")

        # Now 4 players, no one rests
        resting = queue.get_resting_players(num_courts=1, players_per_court=4)
        assert len(resting) == 0
        assert len(queue) == 4

    def test_remove_player_not_found_ignored(self):
        """Removing non-existent player should be silently ignored."""
        players = ["P1", "P2", "P3", "P4"]
        queue = RestRotationQueue(players, shuffle=False)

        queue.remove_player("P99")  # Doesn't exist
        assert len(queue) == 4  # No change

    def test_contains(self):
        """Should support 'in' operator."""
        players = ["P1", "P2", "P3"]
        queue = RestRotationQueue(players, shuffle=False)

        assert "P1" in queue
        assert "P99" not in queue

    def test_len(self):
        """Should support len()."""
        players = ["P1", "P2", "P3", "P4", "P5"]
        queue = RestRotationQueue(players, shuffle=False)

        assert len(queue) == 5
