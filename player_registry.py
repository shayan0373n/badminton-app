# player_registry.py
"""
Player registry data processing utilities.

This module handles conversion between Player objects and pandas DataFrames
for the registry UI editor.
"""

import pandas as pd

from app_types import Gender
from constants import DEFAULT_IS_DOUBLES, TTT_DEFAULT_SIGMA
from session_logic import Player


def create_editor_dataframe(
    player_table: dict[str, Player], is_doubles: bool = DEFAULT_IS_DOUBLES
) -> pd.DataFrame:
    """Creates a DataFrame for the editor from player_table."""
    player_ranks = range(1, len(player_table) + 1)
    df_data = {
        "#": player_ranks,
        "Player Name": [p.name for p in player_table.values()],
        "Gender": [p.gender for p in player_table.values()],
        "Prior Mu": [p.prior_mu for p in player_table.values()],
        "Mu": [p.mu for p in player_table.values()],
        "Sigma": [p.sigma for p in player_table.values()],
        "Rating": [p.conservative_rating for p in player_table.values()],
        "database_id": [p.database_id for p in player_table.values()],
    }
    # Only add Team Name column for Doubles mode
    if is_doubles:
        df_data["Team Name"] = [
            p.team_name if hasattr(p, "team_name") else ""
            for p in player_table.values()
        ]
    return pd.DataFrame(df_data)


def dataframe_to_players(edited_df: pd.DataFrame) -> dict[str, Player]:
    """
    Converts an edited registry DataFrame into a Player dict.

    Handles new players that have empty/NaN values for Mu and Sigma
    (disabled columns in the UI) by converting them to None.
    The Player dataclass handles None via __post_init__.

    Args:
        edited_df: DataFrame from the Streamlit data_editor

    Returns:
        Dictionary mapping player names to Player objects
    """
    new_registry = {}
    for _, row in edited_df.dropna(subset=["Player Name"]).iterrows():
        # Convert NaN to None for nullable fields (database accepts NULL)
        db_id = None if pd.isna(row.get("database_id")) else int(row["database_id"])
        mu = None if pd.isna(row["Mu"]) else float(row["Mu"])
        sigma = None if pd.isna(row["Sigma"]) else float(row["Sigma"])

        new_registry[row["Player Name"]] = Player(
            name=row["Player Name"],
            gender=Gender(row["Gender"]),
            prior_mu=float(row["Prior Mu"]),
            prior_sigma=TTT_DEFAULT_SIGMA,
            mu=mu,
            sigma=sigma,
            database_id=db_id,
        )

    return new_registry
