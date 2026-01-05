# test_required_partners.py
"""
Test script for the required partners feature.
Run with: python test_required_partners.py
"""

from collections import defaultdict
from session_logic import ClubNightSession, Player
from app_types import Gender


def test_get_required_partners():
    """Test that required partners are correctly extracted from team names."""

    # Create players with various team configurations
    players = {
        "Alice": Player(
            name="Alice", gender=Gender.FEMALE, team_name="T1, T2"
        ),  # In both teams
        "Bob": Player(name="Bob", gender=Gender.MALE, team_name="T1"),  # Only in T1
        "Charlie": Player(
            name="Charlie", gender=Gender.MALE, team_name="T2"
        ),  # Only in T2
        "Diana": Player(name="Diana", gender=Gender.FEMALE, team_name=""),  # No team
        "Eve": Player(name="Eve", gender=Gender.FEMALE, team_name="T3"),  # Alone in T3
        "Frank": Player(name="Frank", gender=Gender.MALE),  # No team
    }

    session = ClubNightSession(
        players=players,
        num_courts=1,
        is_doubles=True,
    )

    required = session.get_required_partners()

    print("Team assignments:")
    for name, player in players.items():
        print(f"  {name}: '{player.team_name}'")

    print("\nRequired partners graph:")
    for player, partners in sorted(required.items()):
        print(f"  {player} -> {sorted(partners)}")

    # Validate the expected relationships
    # Alice (T1, T2) should be connected to Bob (T1) and Charlie (T2)
    assert "Alice" in required
    assert required["Alice"] == {
        "Bob",
        "Charlie",
    }, f"Alice should have {{Bob, Charlie}}, got {required['Alice']}"

    # Bob (T1) should only be connected to Alice
    assert "Bob" in required
    assert required["Bob"] == {
        "Alice"
    }, f"Bob should have {{Alice}}, got {required['Bob']}"

    # Charlie (T2) should only be connected to Alice
    assert "Charlie" in required
    assert required["Charlie"] == {
        "Alice"
    }, f"Charlie should have {{Alice}}, got {required['Charlie']}"

    # Diana, Eve, Frank should NOT be in the graph (no valid team connections)
    assert "Diana" not in required, "Diana should not be in required partners"
    assert "Eve" not in required, "Eve should not be in required partners (alone in T3)"
    assert "Frank" not in required, "Frank should not be in required partners"

    print("\n✅ All tests passed!")


def test_single_team_backward_compatibility():
    """Test that single team names (old format) still work."""
    players = {
        "Alice": Player(name="Alice", gender=Gender.FEMALE, team_name="TeamX"),
        "Bob": Player(name="Bob", gender=Gender.MALE, team_name="TeamX"),
        "Charlie": Player(name="Charlie", gender=Gender.MALE),
    }

    session = ClubNightSession(
        players=players,
        num_courts=1,
        is_doubles=True,
    )

    required = session.get_required_partners()

    print("\n--- Backward Compatibility Test ---")
    print("Required partners graph:")
    for player, partners in sorted(required.items()):
        print(f"  {player} -> {sorted(partners)}")

    # Alice and Bob should be mutual required partners
    assert required.get("Alice") == {"Bob"}
    assert required.get("Bob") == {"Alice"}
    assert "Charlie" not in required

    print("\n✅ Backward compatibility test passed!")


if __name__ == "__main__":
    test_get_required_partners()
    test_single_team_backward_compatibility()
