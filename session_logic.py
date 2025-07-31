# session_logic.py
import os
import pickle
import random
from collections import defaultdict
from optimizer import generate_one_round

STATE_FILE = "session_state.pkl"

class SessionManager:
    """Handles loading, saving, and clearing the session state from a file."""

    @staticmethod
    def save(session_instance):
        """Saves the given session instance to the state file."""
        with open(STATE_FILE, "wb") as f:
            pickle.dump(session_instance, f)
        print("--- Session State Saved ---")

    @staticmethod
    def load():
        """
        Loads a session from the state file if it exists.
        Returns the session object or None.
        """
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "rb") as f:
                    session = pickle.load(f)
                    print("--- Session Resumed ---")
                    return session
            except (pickle.UnpicklingError, EOFError):
                print("Failed to load session file. It might be corrupted.")
                # Clean up corrupted file
                os.remove(STATE_FILE)
                return None
        return None

    @staticmethod
    def clear():
        """Clears the session by deleting the state file."""
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print("--- Session State Cleared ---")


class ClubNightSession:
    """
    Orchestrates a club night session using the optimizer for match generation.
    This class only contains game logic and no persistence code.
    """
    def __init__(self, players, num_courts, weights=None, ff_power_penalty=0):
        self.player_pool = players
        self.num_courts = num_courts
        self.players_per_court = 4
        self.round_num = 0
        self.ff_power_penalty = ff_power_penalty

        # State required for the optimizer
        self.historical_partners = defaultdict(int)
        self.weights = weights if weights is not None else {'skill': 1.0, 'power': 1.0, 'pairing': 1.0}

        # Session flow state
        self.current_round_matches = None
        self.resting_players = []
        self._rest_rotation_queue = list(self.player_pool.keys())
        random.shuffle(self._rest_rotation_queue)

    def prepare_round(self):
        """
        Determines resting players and generates optimized matches for the next round.
        """
        self.round_num += 1

        # 1. Determine who is resting
        num_players_to_play = self.num_courts * self.players_per_court
        num_to_rest = len(self.player_pool) - num_players_to_play
        
        if num_to_rest < 0:
            raise ValueError("Not enough players for the number of courts.")
            
        self.resting_players = self._rest_rotation_queue[:num_to_rest]
        
        # 2. Call the optimizer
        matches, updated_history = generate_one_round(
            players=list(self.player_pool.values()),
            players_to_rest=self.resting_players,
            num_courts=self.num_courts,
            historical_partners=self.historical_partners,
            weights=self.weights,
            ff_power_penalty=self.ff_power_penalty
        )

        if not matches:
            self.current_round_matches = None
        else:
            # 3. Update state
            self.historical_partners = updated_history
            self.current_round_matches = sorted(matches, key=lambda m: m['court'])
        
        # 4. Rotate the rest queue for the next round
        players_who_rested = self._rest_rotation_queue[:num_to_rest]
        random.shuffle(players_who_rested)
        self._rest_rotation_queue = self._rest_rotation_queue[num_to_rest:] + players_who_rested

    def finalize_round(self, winners_by_court):
        """
        Updates player ratings based on results.
        Args:
            winners_by_court (dict): A dictionary mapping court numbers to the winning team tuple.
        """
        if self.current_round_matches is None:
            raise ValueError("Cannot finalize a round that was not prepared.")

        for court_num, winning_team in winners_by_court.items():
            for player_name in winning_team:
                if player_name in self.player_pool:
                    self.player_pool[player_name].add_rating(1)

        # Add a small rating boost to resting players
        for player_name in self.resting_players:
            if player_name in self.player_pool:
                self.player_pool[player_name].add_rating(0.5)
        
        # Clear the matches for the completed round
        self.current_round_matches = None

    def get_standings(self):
        """Returns the current player ratings, sorted from highest to lowest."""
        standings = [(p.name, p.earned_rating) for p in self.player_pool.values()]
        return sorted(standings, key=lambda item: item[1], reverse=True)
