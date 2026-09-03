---
trigger: always_on
---

# Badminton App — Architecture & Contracts

This document records the architecture rules, cross-file contracts, and design rationale that cannot be read directly from the code. File inventories and class field listings are deliberately omitted — module docstrings and the code itself are the source of truth for those.

## Architecture

The app follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                       UI Layer                           │
│                   frontend/ (React SPA)                  │
├─────────────────────────────────────────────────────────┤
│                       API Layer                          │
│                         api.py                           │
│       (Routing and serialization only, no logic)         │
├─────────────────────────────────────────────────────────┤
│                    Service Layer                         │
│  session_service.py, player_service.py, rating_service.py│
│   (Orchestrates domain logic + database interactions)    │
├─────────────────────────────────────────────────────────┤
│                    Domain Layer                          │
│  session_logic.py, optimizer*.py, app_types.py           │
│        (Pure business logic, no database calls)          │
├─────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                    │
│    config.py, database.py, exceptions.py, logger.py      │
│           (External services and utilities)              │
└─────────────────────────────────────────────────────────┘
```

Rules (these are norms for future changes, not just descriptions):

- The domain layer must contain no database calls and no UI or framework imports.
- The service layer (`*_service.py`) is the only bridge between UI and domain/database. It exists to keep UI code presentational, keep domain logic DB-free, and make business logic testable without mocking the DB.
- Infrastructure wraps external services; its exceptions never leak upward (see Error Handling).
- **Secrets come from `config.py`**, which reads the environment and falls back to a local `.env`. Deployment passes the same file through compose's `env_file`, so there is one credential format and one place to put it.
- **`api.py` holds no business logic.** It validates input, calls a service function, and serializes the result. A rule belonging to the domain must never be re-expressed as a route.
- **The client never recomputes derived state.** `session_service.build_session_snapshot()` is the single read model: it computes standings, resting players, round numbering and pairing locks, and the client renders that. Duplicating any of it client-side would create a second source of truth.

## Conventions

- **Error handling** — Database operations raise `DatabaseError` (from `exceptions.py`); Supabase exceptions are wrapped, never exposed to higher layers. The UI catches errors and displays them via `st.error()`.
- **Type hints** — Extensive throughout; use the aliases in `app_types.py` (`PlayerName`, `PlayerPair`, `CourtHistory`, …).
- **Logging** — `logging.getLogger("app.<module_name>")`, configured via `logger.setup_logging()`.
- **Defaults** — All configuration constants live in `constants.py`.
- **Doubles vs singles** — Controlled by the `is_doubles` flag; the optimizer has separate logic paths for each mode.
- **Tests** — pytest in `tests/unit` with shared fixtures in `tests/conftest.py`; Vitest in `frontend/src`.

## Domain contracts

- Session state is **derived from `round_history`**: round number, current matches, resting players, and standings are computed properties, not stored counters. Missing keys in `RoundRecord.winners_by_court` mean unreported courts.
- `Player` models a persistent registry member: every field is persisted to the players table. Session-scoped state does not belong on it.
- Team pairing is session state: `ClubNightSession.teams` maps player name → comma-separated team name(s), feeds `get_required_partners()`, and is never persisted to the players table. Drag-to-pair is a face on this: `pair_players()` puts two players in one generated group and never merges or grows an existing one, so a group is always exactly two people and a player may belong to several. `get_required_partners()` therefore reads as a disjunction — a player with two pairs must partner *one* of them in a given round, which is what the optimizer's satisfaction constraint enforces.
- `player_pool` is who is **checked in**; `candidates` is who might turn up. Checking in copies a candidate into the pool via `add_player`; checking out removes them and leaves them a candidate. Presence is pool membership, so the rest queue needs no separate notion of it.
- `challengers` is the set of players asking for a harder game. It persists until cleared rather than being consumed, and is dropped when a player leaves. Like `teams`, it is session-scoped and never reaches the players table.
- Changes made between rounds never disturb the round in play. Court count, weights, check-outs and pairing all land when the next round is prepared — which is what lets the check-in page double as the mid-session management screen.
- `prior_mu`/`prior_sigma` are the season-start baseline fed into rating recalculation (set manually, or carried forward at season rollover); `mu`/`sigma` are TTT outputs that evolve with the current season's matches. `conservative_rating = mu - 3*sigma`.
- Sessions persist as pickles in `sessions/` via `SessionManager`; the database records only players, sessions, and match results.

## Session Flow

### Club night (`frontend/`)

Three screens. Setup picks who might come and how many courts; the check-in hub
is where the night is run from; the session screen is for playing only.

1. **Setup** — choose candidates, courts, and whether the night counts toward
   ratings. `POST /api/sessions` creates the session with an open roster and no
   first round.
2. **Check-in hub** — tap a name to check in, press and hold to check in wanting
   a harder game, drag one name onto another to pair. The side menu holds every
   management action: add or remove players, adjust courts and weights, upload
   results, end the night. Start generates round one and goes to the courts.
3. **Session** — courts, results, games from earlier rounds still needing a
   result, and standings. No controls but round navigation and Back, which
   returns to the hub. Pressing Start there again returns to the round in play;
   only "Next round" advances.

### Rating recalculation

**Rating Recalculation** (`recalculate_ratings.py`)
   - Standalone script, run manually
   - Rebuilds TTT history for the current season and writes each player's `mu`/`sigma`, aging uncertainty to today (see Seasons)

## Design Notes

### Optimizer Contract
- Uses **decoupled inputs** for different optimization objectives:
  - `tier_ratings` (female skill constant-shifted onto male scale): used for court grouping (skill spread minimization)
  - `real_skills` (raw normalized 0-5): used for team fairness (power balance)
- This enables **organic gender balancing**: a constant shift aligns the female and male mean skill for grouping
- Output is `OptimizerResult` with `matches`, `court_history`, `success`

**Challenge mode** boosts `tier_ratings` only, by `CHALLENGE_TIER_BOOST_MU`
(7 mu, one club skill level). Tier ratings drive court grouping, so the
challenger is pulled toward a stronger court; `real_skills` is left alone, so
team balancing still sees their true strength and gives them a *stronger*
partner to cover the gap. Boosting `mu` instead would move both channels and
hand them a weaker partner — the opposite of the intent. The boost is a soft
nudge, not a guarantee: the objective minimizes spread, so a lone challenger can
still be grouped back down when lifting them costs more elsewhere.

Note that `SESSION_PERFORMANCE_FACTOR` does mutate `mu`, and so moves both
channels. That is deliberate for win/loss form — playing well tonight genuinely
means both — but it is the same mechanism challenge mode avoids, so the two
should not be assumed to work alike.

### Solver Backends
The `SOLVER_BACKEND` constant in `constants.py` selects between two optimizer implementations:

| Backend | Module | Solver | License |
|---------|--------|--------|---------|
| `"ortools"` (default) | `optimizer_ortools.py` | Google OR-Tools CP-SAT | Free, Apache 2.0 |
| `"gurobi"` | `optimizer.py` | PuLP + Gurobi | Commercial |

Both have identical public APIs and produce valid matches satisfying all constraints.

**Key differences in the OR-Tools implementation:**
- **`OnlyEnforceIf`** replaces Big-M constraints — no magic constants, no numerical instability
- **Integer arithmetic** — float ratings (0.0–5.0) are scaled to integers (0–5000) via `RATING_SCALE = 1000`
- **Native boolean logic** (`AddImplication`, `AddBoolOr`) for variable linking

### TrueSkill Through Time
- Uses the local `TrueSkillThroughTime.py/` library; docs in its `README.md`, `RELEASE.md`, and `examples/`

### Seasons
- A season is a **date window**. Sessions belong to a season implicitly via their `created_at` (there is no `season_id` FK). The open season is the single `seasons` row with `end_date IS NULL`; before any season exists, all history is one implicit preseason.
- **All rating computation is season-scoped.** `ttt_logic.get_ttt_history()` restricts sessions and matches to the current window, so `mu`/`sigma`, the improvement leaderboard, and recalculation reflect only the current season computed on top of carried priors — not the full match history.
- **Rollover** (`season_service.start_new_season`) converges the closing window and carries each player's end-of-season skill forward as the next season's TTT prior: `prior_mu` = converged `mu`, `prior_sigma` = that endpoint's uncertainty aged to season end, floored at `SEASON_MIN_PRIOR_SIGMA` to prevent rating inertia. The new season then computes from these priors plus only its own matches. Ordering is retry-safe — priors are written while the old season is still current, then the season is rolled, so a mid-rollover failure self-heals on re-run.
- Uncertainty inflates with inactivity via `ttt_logic.age_sigma` (drift per idle day, capped at `TTT_DEFAULT_SIGMA`). The same helper is the single source of this rule for recalculation, carry-forward, and the improvement leaderboard.
