# TrueSkill Through Time Parameters

## Configuration Summary

| Parameter | Value | Description |
|-----------|-------|-------------|
| **mu_good** | 32.0 | Skill level for good players |
| **mu_average** | 25.0 | Skill level for average players (baseline) |
| **mu_bad** | 18.0 | Skill level for weaker players |
| **sigma_certain** | 2.5 | Uncertainty for well-known players |
| **sigma_uncertain** | 6.0 | Uncertainty for new/rarely-seen players |
| **beta** | 4.0 | Performance variance per game |
| **gamma** | 0.1 | Skill drift per day (~0.5 sigma growth per 30 inactive days) |

## Player Prior Matrix

| Skill Level | Certain (σ=2.5) | Uncertain (σ=6.0) |
|-------------|-----------------|-------------------|
| Good | (32.0, 2.5) | (32.0, 6.0) |
| Average | (25.0, 2.5) | (25.0, 6.0) |
| Bad | (18.0, 2.5) | (18.0, 6.0) |

## Expected Win Probabilities (Doubles)

| Matchup | Win % for stronger team |
|---------|-------------------------|
| Good vs Bad | ~99% |
| Good vs Average | ~96% |
| Average vs Bad | ~96% |

## Parameter Meanings

- **mu**: Mean skill estimate (higher = better player)
- **sigma**: Uncertainty in skill estimate (higher = less certain)
- **beta**: Game randomness (lower = skill-dominant, higher = more upsets)
- **gamma**: How much sigma grows per day of inactivity (0 = no drift)

## Display Rating

Conservative rating for display: `mu - 3×sigma`

## Notes

- Library: `trueskillthroughtime` v2.0.0 (cloned from GitHub)
- Time unit: Days
- Spread of 14 points between skill levels calibrated for ~99% win rate (good vs bad)
