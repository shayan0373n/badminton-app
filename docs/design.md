---
trigger: always_on
---

# Badminton App — Architecture & Contracts

This document records the architecture rules, cross-file contracts, and design rationale that cannot be read directly from the code. File inventories and class field listings are deliberately omitted — module docstrings and the code itself are the source of truth for those.

## Architecture

The app follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    UI Layer (Streamlit)                  │
│             1_Setup.py, pages/2_Session.py               │
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
│           database.py, exceptions.py, logger.py          │
│           (External services and utilities)              │
└─────────────────────────────────────────────────────────┘
```

Rules (these are norms for future changes, not just descriptions):

- The domain layer must contain no database calls and no Streamlit imports.
- The service layer (`*_service.py`) is the only bridge between UI and domain/database. It exists to keep UI code presentational, keep domain logic DB-free, and make business logic testable without mocking the DB.
- Infrastructure wraps external services; its exceptions never leak upward (see Error Handling).

## Conventions

- **Error handling** — Database operations raise `DatabaseError` (from `exceptions.py`); Supabase exceptions are wrapped, never exposed to higher layers. The UI catches errors and displays them via `st.error()`.
- **Type hints** — Extensive throughout; use the aliases in `app_types.py` (`PlayerName`, `PlayerPair`, `CourtHistory`, …).
- **Logging** — `logging.getLogger("app.<module_name>")`, configured via `logger.setup_logging()`.
- **Defaults** — All configuration constants live in `constants.py`.
- **Doubles vs singles** — Controlled by the `is_doubles` flag; the optimizer has separate logic paths for each mode.
- **Tests** — pytest, in `tests/unit` and `tests/e2e`; shared fixtures in `tests/conftest.py`.

## Domain contracts

- Session state is **derived from `round_history`**: round number, current matches, resting players, and standings are computed properties, not stored counters. Missing keys in `RoundRecord.winners_by_court` mean unreported courts.
- `Player` models a persistent registry member: every field is persisted to the players table. Session-scoped state does not belong on it.
- Team pairing is session state: `ClubNightSession.teams` maps player name → comma-separated team name(s), feeds `get_required_partners()`, and is never persisted to the players table.
- `prior_mu`/`prior_sigma` are the season-start baseline fed into rating recalculation (set manually, or carried forward at season rollover); `mu`/`sigma` are TTT outputs that evolve with the current season's matches. `conservative_rating = mu - 3*sigma`.
- Sessions persist as pickles in `sessions/` via `SessionManager`; the database records only players, sessions, and match results.

## Session Flow

1. **Setup Page** (`1_Setup.py`)
   - Load/edit player registry from database
   - Configure courts and optimizer weights
   - Click "Start Session" → calls `session_service.create_new_session()`

2. **Session Page** (`pages/2_Session.py`)
   - Navigate between rounds with prev/next buttons
   - Select winners per court (auto-saved on change via `session_service.save_court_result()`)
   - "Next ▶" on latest round → calls `session_service.advance_to_next_round()` (partial results OK)
   - "Submit Results" in sidebar → calls `session_service.submit_session_results()` (idempotent: deletes + re-inserts all matches for the session)
   - Unentered games from other rounds are displayed at the bottom of the page in chronological order, allowing quick result entry without navigating away.

3. **Rating Recalculation** (`recalculate_ratings.py`)
   - Standalone script, run manually
   - Rebuilds TTT history for the current season and writes each player's `mu`/`sigma`, aging uncertainty to today (see Seasons)

## Design Notes

### Optimizer Contract
- Uses **decoupled inputs** for different optimization objectives:
  - `tier_ratings` (female skill constant-shifted onto male scale): used for court grouping (skill spread minimization)
  - `real_skills` (raw normalized 0-5): used for team fairness (power balance)
- This enables **organic gender balancing**: a constant shift aligns the female and male mean skill for grouping
- Output is `OptimizerResult` with `matches`, `court_history`, `success`

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
- **Rollover** (`season_service.start_new_season`) converges the closing window and carries each player's end-of-season skill forward as the next season's TTT prior: `prior_mu` = converged `mu`, `prior_sigma` = that endpoint's uncertainty aged to season end. The new season then computes from these priors plus only its own matches. Ordering is retry-safe — priors are written while the old season is still current, then the season is rolled, so a mid-rollover failure self-heals on re-run.
- Uncertainty inflates with inactivity via `ttt_logic.age_sigma` (drift per idle day, capped at `TTT_DEFAULT_SIGMA`). The same helper is the single source of this rule for recalculation, carry-forward, and the improvement leaderboard.
