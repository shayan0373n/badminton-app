#!/usr/bin/env python3
"""
Ranking Progression and True Improvement Leaderboard analysis script.
"""
import logging
import numpy as np
import matplotlib.pyplot as plt
from logger import setup_logging
from ttt_logic import age_sigma, get_ttt_history, today_ordinal

setup_logging(logging.INFO)
logger = logging.getLogger("app.analyze_ratings")

def analyze_ratings(z=1.0):
    """Print rating summary, LCB-ranked improvement leaderboard, and matches-vs-improvement study.

    z scales the uncertainty penalty in the improvement lower confidence bound.
    """
    logger.info("=== Starting Rating Analysis ===")
    history, learning_curves, players, match_counts = get_ttt_history()

    if not learning_curves:
        logger.info("No data available for analysis.")
        return

    # Print current rating summary
    print("\n--- Current Rating Summary ---")
    sorted_players = sorted(players.values(), key=lambda p: p.mu, reverse=True)
    for i, p in enumerate(sorted_players, 1):
        print(f"{i:2}. {p.name:20} mu={p.mu:5.2f}  sigma={p.sigma:4.2f}  (conservative={p.conservative_rating:5.2f})")

    # Most Active Players
    print("\n--- Most Active Players (Top 10 by Matches Played) ---")
    most_active = sorted(match_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
    for i, (name, count) in enumerate(most_active, 1):
        print(f"{i:2}. {name:20} {count} matches")

    # True Improvement Leaderboard
    # Ranked by a lower confidence bound on the seasonal skill change:
    #   LCB = Δμ - z * sqrt(σ_initial² + σ_final_eff²)
    # so a large gain resting on an uncertain endpoint cannot beat a tighter, smaller one.
    # z trades leniency (low) for required certainty (high). σ_final is first aged from the
    # player's last session to today via TTT's drift (see ttt_logic.age_sigma), so an
    # improvement nobody has seen confirmed for months is discounted accordingly.
    today_day = today_ordinal()
    print(f"\n--- True Improvement Leaderboard (Min 5 Sessions, ranked by LCB, z={z}) ---")
    improvement_data = []
    for name, curve in learning_curves.items():
        if len(curve) >= 5:
            initial, (final_day, final) = curve[0][1], curve[-1]
            improvement = final.mu - initial.mu
            idle_days = max(0, today_day - final_day)
            sigma_final_eff = age_sigma(final.sigma, idle_days)
            sigma_delta = (initial.sigma**2 + sigma_final_eff**2) ** 0.5
            improvement_data.append({
                "name": name,
                "initial": initial.mu,
                "final": final.mu,
                "sigma_initial": initial.sigma,
                "sigma_final_eff": sigma_final_eff,
                "idle_days": idle_days,
                "improvement": improvement,
                "lcb": improvement - z * sigma_delta,
                "sessions": len(curve),
                "matches": match_counts.get(name, 0)
            })

    improvement_data.sort(key=lambda x: x["lcb"], reverse=True)
    for i, data in enumerate(improvement_data, 1):
        print(f"{i:2}. {data['name']:20} {data['initial']:5.2f} -> {data['final']:5.2f}  "
              f"delta_mu={data['improvement']:+5.2f}  LCB={data['lcb']:+6.2f}  "
              f"(sigma {data['sigma_initial']:4.2f}/{data['sigma_final_eff']:4.2f}, idle {data['idle_days']:>3}d) - "
              f"{data['sessions']:2} sessions ({data['matches']} matches)")

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
    import argparse
    parser = argparse.ArgumentParser(description="Rating progression and improvement analysis.")
    parser.add_argument("-z", type=float, default=1.0,
                        help="Uncertainty penalty for the improvement LCB (0=raw Δμ, higher=stricter).")
    args = parser.parse_args()
    analyze_ratings(z=args.z)
