# tests/unit/test_player_service_registry.py
"""
Unit tests for player registry utilities in player_service.

Tests the contract of dataframe_to_players: all DataFrame columns
should be correctly converted to their corresponding Player attributes.
"""

import pandas as pd
import pytest

from app_types import Gender
from constants import TTT_DEFAULT_MU, TTT_DEFAULT_SIGMA
from player_service import dataframe_to_players


def test_dataframe_to_players_produces_correct_player_attributes():
    """
    dataframe_to_players should correctly convert all DataFrame columns
    to their corresponding Player attributes.
    """
    df = pd.DataFrame(
        {
            "Player Name": ["Alice"],
            "Gender": [Gender.FEMALE],
            "Prior Mu": [25.0],
            "Mu": [27.5],
            "Sigma": [5.0],
            "database_id": [42],
            "Team Name": ["TeamA"],
        }
    )

    result = dataframe_to_players(df)
    player = result["Alice"]

    assert player.name == "Alice"
    assert player.gender == Gender.FEMALE
    assert player.prior_mu == 25.0
    assert player.mu == 27.5
    assert player.sigma == 5.0
    assert player.database_id == 42
    assert player.team_name == "TeamA"


def test_dataframe_to_players_handles_nan_mu_and_sigma():
    """
    When Mu and Sigma are NaN (as with new players in the UI),
    the Player should receive prior_mu/prior_sigma via __post_init__.
    """
    df = pd.DataFrame(
        {
            "Player Name": ["NewPlayer"],
            "Gender": [Gender.MALE],
            "Prior Mu": [20.0],
            "Mu": [None],
            "Sigma": [None],
            "database_id": [None],
            "Team Name": [""],
        }
    )

    result = dataframe_to_players(df)
    player = result["NewPlayer"]

    assert player.name == "NewPlayer"
    assert player.gender == Gender.MALE
    assert player.prior_mu == 20.0
    # When mu/sigma are None, Player.__post_init__ sets them to prior values
    assert player.mu == player.prior_mu
    assert player.sigma == player.prior_sigma
    assert player.database_id is None
    assert player.team_name == ""
