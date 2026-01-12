"""
Tests for player registry operations.

These tests verify the behavior of processing player data from the UI,
including new players with default values.
"""

import math

import pandas as pd
import pytest

from constants import TTT_DEFAULT_MU, TTT_DEFAULT_SIGMA
from app_types import Gender
from player_registry import create_editor_dataframe, dataframe_to_players


class TestPlayerRegistryProcessing:
    """Tests for processing player data from the registry UI."""

    def test_new_player_row_produces_valid_player(self):
        """
        When a new player row is added to the registry with only a name entered,
        the resulting Player object should have valid mu and sigma values.

        Workflow:
        1. User goes to Member Registry (empty or with existing players)
        2. User clicks '+' to add a new row
        3. User types a name, leaves everything else at defaults
        4. User clicks 'Save Registry to Cloud'

        The resulting Player should have valid, non-NaN values for all fields.
        """
        # Arrange: Start with an empty registry and create a DataFrame
        initial_registry = {}
        registry_df = create_editor_dataframe(initial_registry)

        # Simulate: User adds a new row via data_editor (pandas concat)
        # Streamlit's data_editor with num_rows="dynamic" produces this when adding a row
        new_row = pd.DataFrame(
            [
                {
                    "#": 1,
                    "Player Name": "NewPlayer",
                    "Gender": "M",  # Default from SelectboxColumn config
                    "Prior Mu": TTT_DEFAULT_MU,  # Default from NumberColumn config
                    "Mu": None,  # Disabled column - no value for new row
                    "Sigma": None,  # Disabled column - no value for new row
                    "Rating": None,  # Disabled column - no value for new row
                    "database_id": None,  # Hidden column - no value for new row
                }
            ]
        )
        edited_df = pd.concat([registry_df, new_row], ignore_index=True)

        # Act: Process the DataFrame (production code)
        result = dataframe_to_players(edited_df)

        # Assert: The new player should have valid values
        assert "NewPlayer" in result
        player = result["NewPlayer"]

        assert player.name == "NewPlayer"
        assert player.gender == Gender.MALE
        assert not math.isnan(player.mu), "mu should not be NaN"
        assert not math.isnan(player.sigma), "sigma should not be NaN"
        assert player.mu == TTT_DEFAULT_MU
        assert player.sigma == TTT_DEFAULT_SIGMA
