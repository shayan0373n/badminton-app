# In session_logic.py

import random

class BadmintonSession:
    def __init__(self, player_ids, rests_per_round=4, players_per_court=4):
        self.player_pool = [{'id': pid} for pid in player_ids]
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
        resting_ids = {p['id'] for p in self.resting_players}
        active_players = [p for p in self.player_pool if p['id'] not in resting_ids]
        original_courts = self._assign_courts(active_players)

        # 2. Rank players based on the provided winners
        intermediate_ranking = self._rank_from_results(original_courts, all_winners)
        
        # 3. Perform relegation
        new_ranked_active = self._perform_relegation(intermediate_ranking)
        
        # 4. Re-insert rested players
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
    
    def _rank_from_results(self, original_courts, all_winners):
        ranking = []
        all_winners_ids = {p['id'] for p in all_winners}
        
        for court in original_courts:
            winners_on_court = [p for p in court if p['id'] in all_winners_ids]
            losers_on_court = [p for p in court if p['id'] not in all_winners_ids]
            random.shuffle(winners_on_court)
            random.shuffle(losers_on_court)
            ranking.extend(winners_on_court + losers_on_court)
        return ranking

    def _perform_relegation(self, ranked_list):
        num_courts = len(ranked_list) // self.players_per_court
        for i in range(num_courts - 1):
            idx1 = (i * self.players_per_court) + self.players_per_court - 1
            idx2 = idx1 + 1
            ranked_list[idx1], ranked_list[idx2] = ranked_list[idx2], ranked_list[idx1]
        return ranked_list