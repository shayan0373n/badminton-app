# TrueSkill Through Time Parameters

## Configuration Summary

| Parameter | Value | Description |
|-----------|-------|-------------|
| **mu_good** | 32.0 | Skill level for good players |
| **mu_average** | 25.0 | Skill level for average players (baseline) |
| **mu_bad** | 18.0 | Skill level for weaker players |
| **sigma_certain** | 2.5 | Uncertainty for well-known players |
| **sigma_uncertain** | 6.0 | Uncertainty for new/rarely-seen players |
| **beta** | 4.0 | Performance noise std dev per game |
| **gamma** | 0.13 | Skill drift per day (std dev of true skill random walk) |

## Skill Scale

- **1 level gap** = 3.5 mu (e.g., average 25.0 → good 32.0 = 2 levels)
- **Full range** = 14 mu (bad 18.0 → good 32.0 = 4 levels)

## Player Prior Matrix

| Skill Level | Certain (σ=2.5) | Uncertain (σ=6.0) |
|-------------|-----------------|-------------------|
| Good | (32.0, 2.5) | (32.0, 6.0) |
| Average | (25.0, 2.5) | (25.0, 6.0) |
| Bad | (18.0, 2.5) | (18.0, 6.0) |

## Expected Win Probabilities

### Doubles (2v2, homogeneous teams)

| Matchup | Win % for stronger team |
|---------|-------------------------|
| Good vs Bad (2 levels) | ~100% |
| Good vs Average (1 level) | ~96% |
| Average vs Bad (1 level) | ~96% |

### Singles (1v1)

| Matchup | Win % for stronger player |
|---------|---------------------------|
| Good vs Bad (2 levels) | ~99% |
| Good vs Average (1 level) | ~89% |
| Average vs Bad (1 level) | ~89% |

## Parameter Meanings

- **mu**: Mean skill estimate (higher = better player)
- **sigma**: Uncertainty in skill estimate (higher = less certain)
- **beta**: Performance noise per game. With beta=4.0 and 1 level=3.5 mu,
  beta/level ≈ 1.14 — a 1-level gap gives ~89% singles win probability.
  Higher beta = more upsets.
- **gamma**: How much true skill can drift per day (std dev of random walk).
  Drift over a period = sqrt(num_days) × gamma.
  With gamma=0.13 over a 6-month season (182 days):
  sqrt(182) × 0.13 = 1.75 mu ≈ 0.5 levels of potential skill change.

## Display Rating

Conservative rating for display: `mu - 3×sigma`

## Notes

- Library: `trueskillthroughtime` v2.0.0 (cloned from GitHub)
- Time unit: Days
- Observation model: Ordinal (win/loss only, no scores)
- Spread of 14 points between skill levels calibrated for ~99% singles win rate (good vs bad)
