#!/usr/bin/env python3
"""
Ranking Progression and True Improvement Leaderboard analysis script.
"""
import logging
import numpy as np
import matplotlib.pyplot as plt
from logger import setup_logging
from ttt_logic import get_ttt_history

setup_logging(logging.INFO)
logger = logging.getLogger("app.analyze_ratings")

def analyze_ratings():
    logger.info("=== Starting Rating Analysis ===")
    history, learning_curves, players, match_counts = get_ttt_history()

    if not learning_curves:
        logger.info("No data available for analysis.")
        return

    # Print current rating summary
    print("\n--- Current Rating Summary ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(f"{i:2}. {p.name:20} mu={p.mu:5.2f}  σ={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})")

    # True Improvement Leaderboard
    print("\n--- True Improvement Leaderboard (Inferred Growth, Min 5 Sessions) ---")
    improvement_data = []
    for name, curve in learning_curves.items():
        if len(curve) >= 5:
            initial_mu = curve[0][1].mu
            final_mu = curve[-1][1].mu
            improvement = final_mu - initial_mu
            improvement_data.append({
                "name": name,
                "initial": initial_mu,
                "final": final_mu,
                "improvement": improvement,
                "sessions": len(curve),
                "matches": match_counts.get(name, 0)
            })
    
    improvement_data.sort(key=lambda x: x["improvement"], reverse=True)
    for i, data in enumerate(improvement_data, 1):
        print(f"{i:2}. {data['name']:20} {data['initial']:5.2f} -> {data['final']:5.2f} ({data['improvement']:+5.2f}) - {data['sessions']} sessions ({data['matches']} matches)")

    # Correlation Analysis: Matches vs Improvement
    print("\n--- Correlation Study: Matches vs. Improvement ---")
    
    # Collect data for all players with at least 5 matches
    study_data = []
    for name, count in match_counts.items():
        if count >= 5 and name in learning_curves:
            curve = learning_curves[name]
            improvement = curve[-1][1].mu - curve[0][1].mu
            study_data.append((count, improvement))
    
    if len(study_data) < 2:
        print("Not enough data points for correlation study.")
    else:
        x = np.array([d[0] for d in study_data])
        y = np.array([d[1] for d in study_data])
        
        # Pearson Correlation
        correlation = np.corrcoef(x, y)[0, 1]
        
        # Linear Regression (y = mx + b)
        m, b = np.polyfit(x, y, 1)
        
        print(f"Sample size: {len(study_data)} players")
        print(f"Pearson Correlation Coefficient: {correlation:.4f}")
        print(f"Linear Fit: improvement = {m:.4f} * matches + ({b:.4f})")
        
        # Plotting
        try:
            plt.figure(figsize=(10, 6))
            plt.scatter(x, y, alpha=0.6, label='Players')
            
            # Add regression line
            if len(x) > 0:
                x_range = np.array([min(x), max(x)])
                plt.plot(x_range, m * x_range + b, color='red', linestyle='--', 
                         label=f'Linear Fit (r={correlation:.2f})')
            
            plt.title('Correlation: Number of Matches vs. Rating Improvement')
            plt.xlabel('Number of Matches Played')
            plt.ylabel('Total Mu Improvement (Final - Initial)')
            plt.grid(True, linestyle=':', alpha=0.7)
            plt.legend()
            
            plot_filename = "improvement_correlation.png"
            plt.savefig(plot_filename)
            print(f"Plot saved to: {plot_filename}")
        except Exception as e:
            print(f"Could not generate plot: {e}")

if __name__ == "__main__":
    analyze_ratings()
