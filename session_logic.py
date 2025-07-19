# In session_logic.py

import random

class BadmintonSession:
    def __init__(self, player_ids, rests_per_round=4, players_per_court=4):
        self.player_pool = [{'id': pid, 'tiebreak_priority': 0} for pid in player_ids]
        self.rest_queue = list(self.player_pool)
        random.shuffle(self.rest_queue)
        
        self.rests_per_round = rests_per_round
        self.players_per_court = players_per_court
        self.round_num = 0
        
        self.courts = []
        self.resting_players = []

    def prepare_round(self):
        """Sets up the courts and resting players for the upcoming round."""
        self.round_num += 1
        self._rotate_rest_queue()
        
        resting_ids = {p['id'] for p in self.resting_players}
        active_players = [p for p in self.player_pool if p['id'] not in resting_ids]
        
        self.courts = self._assign_courts(active_players)

    def finalize_round(self, all_winners):
        """Takes the winners, calculates new rankings, and prepares for the next round."""
        # 1. Get active players and court setup to find losers
        # active_players = [p for p in self.player_pool if p['id'] not in resting_ids]
        # original_courts = self._assign_courts(active_players)

        # 2. Rank players based on the provided winners
        intermediate_ranking = self._rank_from_results(self.courts, all_winners)
        
        # 3. Perform relegation
        new_ranked_active = self._perform_relegation(intermediate_ranking)
        
        # 4. Re-insert rested players
        resting_ids = {p['id'] for p in self.resting_players}
        current_resting_info = []
        for index, player in enumerate(self.player_pool):
            if player['id'] in resting_ids:
                current_resting_info.append({'player': player, 'original_index': index})
        current_resting_info.sort(key=lambda x: x['original_index'])

        final_list = list(new_ranked_active)
        for r in current_resting_info:
            final_list.insert(r['original_index'], r['player'])
            
        self.player_pool = final_list

    def _rotate_rest_queue(self):
        self.resting_players = self.rest_queue[:self.rests_per_round]
        self.rest_queue = self.rest_queue[self.rests_per_round:]
        random.shuffle(self.resting_players)
        self.rest_queue.extend(self.resting_players)
    
    def _assign_courts(self, active_players):
        courts_list = []
        num_courts = len(active_players) // self.players_per_court
        for i in range(num_courts):
            start = i * self.players_per_court
            end = start + self.players_per_court
            courts_list.append(active_players[start:end])
        return courts_list
    
    def _resolve_ties(self, players):
        """
        Sorts players involved in a tie.
        - Higher tiebreak_priority wins.
        - Randomly breaks ties in priority.
        - Updates priority scores post-resolution.
        """
        if not players:
            return []
            
        # Sort by priority (desc) and then randomly
        sorted_players = sorted(
            players, 
            key=lambda p: (p['tiebreak_priority'], random.random()), 
            reverse=True
        )
        
        # Update priorities: winners of the tie go down, losers go up
        # Assuming a 50/50 split for simplicity
        split_point = len(sorted_players) // 2
        for i, player in enumerate(sorted_players):
            if i < split_point:
                player['tiebreak_priority'] -= 1  # Won the tie
            else:
                player['tiebreak_priority'] += 1  # Lost the tie
                
        return sorted_players
    
    def _rank_from_results(self, original_courts, all_winners):
        ranking = []
        all_winners_ids = {p['id'] for p in all_winners}
        
        for court in original_courts:
            winners_on_court = [p for p in court if p['id'] in all_winners_ids]
            losers_on_court = [p for p in court if p['id'] not in all_winners_ids]
            
            # Resolve ties using the new weighted method
            ranked_winners = self._resolve_ties(winners_on_court)
            ranked_losers = self._resolve_ties(losers_on_court)
            
            ranking.extend(ranked_winners + ranked_losers)
            
        return ranking
    
    def _perform_relegation(self, ranked_list):
        num_courts = len(ranked_list) // self.players_per_court
        for i in range(num_courts - 1):
            idx1 = (i * self.players_per_court) + self.players_per_court - 1
            idx2 = idx1 + 1
            ranked_list[idx1], ranked_list[idx2] = ranked_list[idx2], ranked_list[idx1]
        return ranked_list
    
def test_logic():
    # Example test case
    session = BadmintonSession(['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Frank'], rests_per_round=2)
    for _ in range(3):
        session.prepare_round()
        print(f"Resting Players: {[p['id'] for p in session.resting_players]}")
        print(f"Round {session.round_num} Courts: {session.courts}")
        # Simulate results
        winners = [session.courts[0][0], session.courts[0][1]]  # Assume first court's first two players win
        session.finalize_round(winners)
        print(f"After Round {session.round_num}, Player Pool: {[p['id'] for p in session.player_pool]}")
        print("-" * 40)

if __name__ == "__main__":
    test_logic()