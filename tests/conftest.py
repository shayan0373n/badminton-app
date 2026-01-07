import pytest
import os
from app_types import Gender
from session_logic import Player


@pytest.fixture
def sample_players():
    """Returns a dictionary of sample players."""
    return {
        "Alice": Player(
            name="Alice", gender=Gender.FEMALE, prior_mu=25.0, prior_sigma=8.33
        ),
        "Bob": Player(name="Bob", gender=Gender.MALE, prior_mu=25.0, prior_sigma=8.33),
        "Charlie": Player(
            name="Charlie", gender=Gender.MALE, prior_mu=30.0, prior_sigma=8.33
        ),
        "Dave": Player(
            name="Dave", gender=Gender.MALE, prior_mu=30.0, prior_sigma=8.33
        ),
        "Eve": Player(
            name="Eve", gender=Gender.FEMALE, prior_mu=20.0, prior_sigma=8.33
        ),
        "Frank": Player(
            name="Frank", gender=Gender.MALE, prior_mu=20.0, prior_sigma=8.33
        ),
        "Grace": Player(
            name="Grace", gender=Gender.FEMALE, prior_mu=28.0, prior_sigma=8.33
        ),
        "Heidi": Player(
            name="Heidi", gender=Gender.FEMALE, prior_mu=28.0, prior_sigma=8.33
        ),
    }


@pytest.fixture
def player_ratings(sample_players):
    """Returns a mapping of player names to their ratings."""
    return {name: p.prior_mu for name, p in sample_players.items()}


@pytest.fixture
def player_genders(sample_players):
    """Returns a mapping of player names to their genders."""
    return {name: p.gender for name, p in sample_players.items()}
