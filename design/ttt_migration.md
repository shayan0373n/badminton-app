# Database Migration: Glicko-2 to TrueSkill Through Time

## Overview
Migration from Glicko-2 rating system to TrueSkill Through Time (TTT).

## Players Table Changes

### Remove Old Columns
```sql
ALTER TABLE players DROP COLUMN IF EXISTS elo;
ALTER TABLE players DROP COLUMN IF EXISTS deviation;
ALTER TABLE players DROP COLUMN IF EXISTS volatility;
```

### Add New Columns
```sql
ALTER TABLE players ADD COLUMN mu FLOAT DEFAULT 25.0;
ALTER TABLE players ADD COLUMN sigma FLOAT DEFAULT 6.0;
```

### Migration for Existing Players
If you want to preserve approximate skill levels, you can map old ratings:
```sql
-- Map old Glicko-2 ratings to TTT scale
-- Glicko-2: 1500 = average, typical range 1000-2000
-- TTT: 25 = average, typical range 18-32

UPDATE players
SET 
  mu = 25.0 + (elo - 1500) / 1500 * 7.0,  -- Scale to ±7 around 25
  sigma = CASE 
    WHEN deviation < 50 THEN 2.5   -- Certain
    ELSE 6.0                        -- Uncertain
  END
WHERE elo IS NOT NULL;
```

Or simply reset all players to average (recommended for fresh start):
```sql
UPDATE players SET mu = 25.0, sigma = 6.0;
```

## Matches Table
No changes needed - the current structure already stores:
- `player_1`, `player_2`, `player_3`, `player_4` (player names)
- `winner_side` (1 or 2)
- `session_id`
- `processed` (boolean)

This is sufficient for TTT to rebuild history from matches.

## TTT History Rebuilding

When implementing rating updates, TTT will:

1. **Fetch all sessions** with their `created_at` timestamps
2. **Fetch all matches** with their `session_id`
3. **Convert timestamps to absolute weeks since epoch**:
   ```python
   SECONDS_PER_WEEK = 7 * 24 * 3600
   
   # No need to know first session - just use absolute time
   session_to_weeks = {
       s["id"]: s["created_at"].timestamp() / SECONDS_PER_WEEK
       for s in sessions
   }
   ```
4. **Build composition** (winner team first):
   ```python
   composition = []
   times = []
   for match in matches:
       if match["winner_side"] == 1:
           teams = [[p1, p2], [p3, p4]]
       else:
           teams = [[p3, p4], [p1, p2]]
       composition.append(teams)
       times.append(session_to_weeks[match["session_id"]])
   ```
5. **Build priors from database** (existing player skills):
   ```python
   from trueskillthroughtime import Player, Gaussian
   
   priors = {
       p["name"]: Player(Gaussian(mu=p["mu"], sigma=p["sigma"]))
       for p in all_players
   }
   ```
6. **Run TTT** with all parameters:
   ```python
   history = History(
       composition=composition,
       times=times,
       priors=priors,           # Existing player skills from DB
       mu=TTT_DEFAULT_MU,       # 25.0 - fallback for unknown players
       sigma=TTT_DEFAULT_SIGMA, # 6.0 - fallback for unknown players
       beta=TTT_BETA,           # 4.0 - performance noise
       gamma=TTT_GAMMA,         # 0.01 - skill drift per week
   )
   history.convergence()
   ```
7. **Extract final ratings** and update players table

### Key Design Decisions
- **All matches in one session share the same timestamp** (treated as simultaneous)
- **Absolute time** – no need to track "first session"; TTT only uses time *differences*
- **Gamma = 0.01 per week** means skill uncertainty grows slowly between sessions
- **No extra columns needed** – uses existing `sessions.created_at`

## Column Summary

| Old (Glicko-2) | New (TTT) | Default |
|----------------|-----------|---------|
| elo (1500) | mu | 25.0 |
| deviation (350) | sigma | 6.0 |
| volatility (0.06) | *(removed)* | - |
