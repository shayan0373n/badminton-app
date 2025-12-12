# session_logic.py
import os
import pickle
import random
from collections import defaultdict
from dataclasses import dataclass, field
from optimizer import generate_one_round

SESSIONS_DIR = "sessions"

@dataclass
class Player:
    name: str
    gender: str
    pre_rating: float
    rating: float = field(init=False)
    earned_rating: float = 0.0
    team_name: str = ""  # Optional team name for permanent pairing

    def __post_init__(self):
        self.rating = self.pre_rating

    def add_rating(self, amount: float):
        """Adds rating to the player."""
        self.rating += amount
        self.earned_rating += amount


class SessionManager:
    """Handles loading, saving, and clearing named session states."""

    @staticmethod
    def _get_session_path(session_name: str) -> str:
        """Returns the file path for a given session name."""
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        return os.path.join(SESSIONS_DIR, f"{session_name}.pkl")

    @staticmethod
    def save(session_instance, session_name: str):
        """Saves the given session instance to a named file."""
        path = SessionManager._get_session_path(session_name)
        with open(path, "wb") as f:
            pickle.dump(session_instance, f)
        print(f"--- Session '{session_name}' Saved ---")

    @staticmethod
    def load(session_name: str):
        """
        Loads a session from a named file if it exists.
        Returns the session object or None.
        """
        path = SessionManager._get_session_path(session_name)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    session = pickle.load(f)
                    print(f"--- Session '{session_name}' Loaded ---")
                    return session
            except (pickle.UnpicklingError, EOFError):
                print(f"Failed to load session '{session_name}'. It might be corrupted.")
                os.remove(path)
                return None
        return None

    @staticmethod
    def clear(session_name: str):
        """Clears a named session by deleting its file."""
        path = SessionManager._get_session_path(session_name)
        if os.path.exists(path):
            os.remove(path)
            print(f"--- Session '{session_name}' Cleared ---")

    @staticmethod
    def list_sessions():
        """Returns a list of all available session names."""
        if not os.path.exists(SESSIONS_DIR):
            return []
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.pkl')]
        return [f[:-4] for f in files]  # Remove .pkl extension


class ClubNightSession:
    """
    Orchestrates a club night session using the optimizer for match generation.
    This class only contains game logic and no persistence code.
    """
    def __init__(self, players, num_courts, weights=None, ff_power_penalty=0, mf_power_penalty=0, game_mode="Doubles"):
        self.player_pool = players
        self.num_courts = num_courts
        self.game_mode = game_mode
        self.players_per_court = 2 if game_mode == "Singles" else 4
        self.round_num = 0
        self.ff_power_penalty = ff_power_penalty
        self.mf_power_penalty = mf_power_penalty

        # State required for the optimizer
        self.historical_partners = defaultdict(int)
        self.weights = weights if weights is not None else {'skill': 1.0, 'power': 1.0, 'pairing': 1.0}

        # Session flow state
        self.current_round_matches = None
        self.resting_players = set()
        self._rest_rotation_queue = list(self.player_pool.keys())
        random.shuffle(self._rest_rotation_queue)
        self.queued_removals = set()  # Players marked for removal
        
    def get_teammate_pairs(self):
        """Extract teammate pairs from player team names. Returns list of (player1, player2) tuples."""
        team_groups = defaultdict(list)
        for player_name, player in self.player_pool.items():
            if player.team_name and player.team_name.strip():
                team_groups[player.team_name.strip()].append(player_name)
        
        pairs = []
        for team_name, members in team_groups.items():
            if len(members) == 2:
                pairs.append(tuple(sorted(members)))
        return pairs

    def prepare_round(self):
        """
        Determines resting players and generates optimized matches for the next round.
        """
        self.round_num += 1

        # Get teammate pairs for this round
        teammate_pairs = self.get_teammate_pairs() if self.game_mode == "Doubles" else []
        
        # Create a set of all players who are in a locked pair
        paired_players = set()
        for p1, p2 in teammate_pairs:
            paired_players.add(p1)
            paired_players.add(p2)
        
        # 1. Determine who is resting and adjust courts if needed
        total_players = len(self.player_pool)
        max_courts = total_players // self.players_per_court
        active_courts = min(self.num_courts, max_courts)
        
        num_players_to_play = active_courts * self.players_per_court
        num_to_rest = total_players - num_players_to_play
        
        # Rest rotation with pair coordination
        # Build a map of player -> their partner (if any)
        partner_map = {}
        for p1, p2 in teammate_pairs:
            partner_map[p1] = p2
            partner_map[p2] = p1
        
        resting = []
        already_processed = set()
        
        # Go through the rotation queue in order
        for player in self._rest_rotation_queue:
            if player in already_processed:
                continue
                
            if len(resting) >= num_to_rest:
                break
            
            # Add this player to resting list
            resting.append(player)
            already_processed.add(player)
            
            # If they have a teammate AND we still need more resting players, add teammate too
            if player in partner_map and len(resting) < num_to_rest:
                partner = partner_map[player]
                if partner not in already_processed:
                    resting.append(partner)
                    already_processed.add(partner)
        
        self.resting_players = set(resting)
        
        # 2. Call the optimizer with adjusted court count and teammate pairs
        matches, updated_history = generate_one_round(
            players=list(self.player_pool.values()),
            players_to_rest=self.resting_players,
            num_courts=active_courts,
            historical_partners=self.historical_partners,
            weights=self.weights,
            ff_power_penalty=self.ff_power_penalty,
            mf_power_penalty=self.mf_power_penalty,
            players_per_court=self.players_per_court,
            game_mode=self.game_mode,
            teammate_pairs=teammate_pairs
        )

        if not matches:
            self.current_round_matches = None
        else:
            # 3. Update state
            self.historical_partners = updated_history
            self.current_round_matches = sorted(matches, key=lambda m: m['court'])
        
        # 4. Rotate the rest queue for the next round
        players_who_rested = [p for p in self._rest_rotation_queue if p in self.resting_players]
        random.shuffle(players_who_rested)
        self._rest_rotation_queue = [p for p in self._rest_rotation_queue if p not in self.resting_players] + players_who_rested

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
        
        # Process any queued player removals
        for player_name in list(self.queued_removals):
            self._remove_player_now(player_name)

    def update_courts(self, new_num_courts: int):
        """Updates available courts mid session; applies on the next prepared round."""
        new_num_courts = int(new_num_courts)
        if new_num_courts < 1:
            raise ValueError("Number of courts must be at least 1.")
        self.num_courts = new_num_courts

    def get_standings(self):
        """Returns the current player ratings, sorted from highest to lowest."""
        standings = [(p.name, p.earned_rating) for p in self.player_pool.values()]
        return sorted(standings, key=lambda item: item[1], reverse=True)

    def add_player(self, name: str, gender: str, pre_rating: int, team_name: str = "") -> bool:
        """
        Adds a new player mid-session.
        - Appends the player to the end of the rest rotation queue.
        - Initializes the player's earned score to the average earned score of existing players
          so they are not disadvantaged in standings or court balance.

        Returns True if added, False if the name already exists.
        """
        # Prevent duplicates by exact name match
        if name in self.player_pool:
            return False

        # Create the player with base rating
        new_player = Player(name=name, gender=gender, pre_rating=pre_rating, team_name=team_name)

        # Compute average earned among existing players (exclude the new one)
        existing_players = self.player_pool.values()
        avg_earned = 0.0
        if existing_players:
            avg_earned = sum(p.earned_rating for p in existing_players) / len(existing_players)
            # Round to nearest half point
            avg_earned = round(avg_earned * 2) / 2

        # Use add_rating to keep rating and earned_rating in sync
        if avg_earned:
            new_player.add_rating(avg_earned)

        # Add to rest queue and player pool
        self.player_pool[name] = new_player
        self._rest_rotation_queue.append(name)
        self.resting_players.add(name)

        return True

    def remove_player(self, name: str) -> tuple[bool, str]:
        """
        Marks a player for removal from the session.
        - If player is currently playing, queues them for removal after round confirmation
        - If player is resting or no round active, removes immediately

        Returns (success, status) where status is 'immediate', 'queued', or 'not_found'.
        """
        if name not in self.player_pool:
            return False, 'not_found'
        
        # Check if player is currently playing (in current_round_matches)
        is_playing = False
        if self.current_round_matches:
            for match in self.current_round_matches:
                if self.game_mode == "Singles":
                    if name in [match['player_1'], match['player_2']]:
                        is_playing = True
                        break
                else:  # Doubles
                    if name in match['team_1'] or name in match['team_2']:
                        is_playing = True
                        break
        
        if is_playing:
            # Queue for removal after round confirmation
            self.queued_removals.add(name)
            return True, 'queued'
        else:
            # Remove immediately
            self._remove_player_now(name)
            return True, 'immediate'
    
    def _remove_player_now(self, name: str):
        """Internal method to actually remove a player from all structures."""
        if name in self.player_pool:
            del self.player_pool[name]
        if name in self._rest_rotation_queue:
            self._rest_rotation_queue.remove(name)
        if name in self.resting_players:
            self.resting_players.remove(name)
        if name in self.queued_removals:
            self.queued_removals.remove(name)
