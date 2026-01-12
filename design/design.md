---
trigger: always_on
---

# Badminton App - Codebase Structure

This document provides an overview of the codebase architecture and conventions to help understand how things are organized and how to make changes.

## Architecture Overview

The app follows a **layered architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    UI Layer (Streamlit)                  │
│             1_Setup.py, pages/2_Session.py               │
├─────────────────────────────────────────────────────────┤
│                    Service Layer                         │
│       session_service.py, player_service.py              │
│   (Orchestrates domain logic + database interactions)    │
├─────────────────────────────────────────────────────────┤
│                    Domain Layer                          │
│        session_logic.py, optimizer.py, app_types.py      │
│        (Pure business logic, no database calls)          │
├─────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                    │
│           database.py, exceptions.py, logger.py          │
│           (External services and utilities)              │
└─────────────────────────────────────────────────────────┘
```

---

## File-by-File Breakdown

### UI Layer

| File | Purpose |
|------|---------|
| `1_Setup.py` | Main entry point. Session setup, player registry editing, session creation. Run with `streamlit run 1_Setup.py`. |
| `pages/2_Session.py` | Active session management. Match selection, winner recording, player/court management. |

### Service Layer

| File | Purpose |
|------|---------|
| `session_service.py` | Orchestrates session operations (create, record matches, add/remove players). Bridges UI and domain/database layers. |
| `player_service.py` | Handles player registry management. Converts between `Player` objects and DataFrames for the UI, and synchronizes changes to the database. |

### Domain Layer

| File | Purpose |
|------|---------|
| `session_logic.py` | Core domain logic. Contains `Player`, `SessionManager`, `RestRotationQueue`, and `ClubNightSession` classes. No DB calls. |
| `optimizer.py` | Match optimization using PuLP/Gurobi. `generate_one_round()` for doubles, `generate_singles_round()` for singles. |
| `app_types.py` | Type aliases and dataclasses (`Gender`, `OptimizerResult`, `SinglesMatch`, `DoublesMatch`, etc.). |
| `constants.py` | All configuration constants (TrueSkill params, optimizer settings, penalties, defaults). |
| `exceptions.py` | Domain exceptions: `DatabaseError`, `SessionError`, `OptimizerError`, `ValidationError`. |

### Infrastructure Layer

| File | Purpose |
|------|---------|
| `database.py` | Supabase database operations. Classes: `PlayerDB`, `SessionDB`, `MatchDB`. All methods are `@staticmethod`. |
| `logger.py` | Logging configuration with `setup_logging()`. |
| `recalculate_ratings.py` | Standalone script to rebuild all player ratings from match history using TrueSkill Through Time. |

### External Dependencies

| Directory | Purpose |
|-----------|---------|
| `TrueSkillThroughTime.py/` | Local copy of the TTT library. Documentation in `README.md`, `RELEASE.md`, and `examples/`. |

---

## Key Classes

### `Player` (session_logic.py)
A dataclass representing a player with TrueSkill ratings:
- `name`, `gender`, `prior_mu`, `prior_sigma` — static/prior values
- `mu`, `sigma` — current skill estimate (auto-initialized from priors via `__post_init__`)
- `database_id` — optional foreign key to the Supabase players table
- `team_name` — optional partnership group for doubles constraints

### `ClubNightSession` (session_logic.py)
Orchestrates a club night session:
- Holds the player table, round state, partner history
- Delegates match generation to the optimizer
- Methods: `prepare_round()`, `finalize_round()`, `add_player()`, `remove_player()`

### `SessionManager` (session_logic.py)
Static class for session file persistence (pickle to `sessions/` directory):
- `save()`, `load()`, `clear()`, `list_sessions()`

### `RestRotationQueue` (session_logic.py)
Manages fair rotation for resting players:
- Players at the front rest first, then rotate to the back

### Database Classes (database.py)
All use `@staticmethod` and translate Supabase exceptions to `DatabaseError`:
- `PlayerDB`: `get_all_players()`, `upsert_players()`, `delete_players_by_ids()`
- `SessionDB`: `create_session()`, `get_session_by_name()`, `get_all_sessions()`
- `MatchDB`: `add_match()`, `get_all_matches()`

---

## Conventions

### Error Handling
- Database operations raise `DatabaseError` (from `exceptions.py`)
- UI catches errors and displays via `st.error()`
- Supabase exceptions are wrapped, never exposed to higher layers

### Type Hints
- Extensive type hints throughout codebase
- Use type aliases from `app_types.py` for readability (e.g. `PlayerName`, `PlayerPair`, `PartnerHistory`)

### Logging
- Use `logging.getLogger("app.<module_name>")` pattern
- Loggers configured via `logger.setup_logging()`

### Default Values
- All defaults centralized in `constants.py`
- `Player.__post_init__` uses `TTT_DEFAULT_MU` / `TTT_DEFAULT_SIGMA` when values are None

### Doubles vs Singles
- Controlled by `is_doubles` flag
- `PLAYERS_PER_COURT_DOUBLES = 4`, `PLAYERS_PER_COURT_SINGLES = 2`
- Optimizer has separate logic paths for each mode

---

## Testing

Tests are in `tests/` and use pytest:

```
tests/
├── conftest.py         # Shared fixtures (sample_players, player_ratings, etc.)
├── utils.py            # Test utilities (generate_random_players, run_optimizer_rounds)
├── unit/
│   ├── test_optimizer.py
│   ├── test_session_logic.py
│   ├── test_rest_rotation_queue.py
│   └── test_hub_constraints.py
├── integration/        # (Integration tests)
└── e2e/                # (End-to-end tests)
```

Run tests with:
```bash
pytest
```

### Key Test Utilities
- `generate_random_players(n)` — Creates N players with random ratings
- `run_optimizer_rounds(...)` — Generator that simulates multiple rounds with state

---

## Session Flow

1. **Setup Page** (`1_Setup.py`)
   - Load/edit player registry from database
   - Configure courts, weights, penalties
   - Click "Start Session" → calls `session_service.create_new_session()`

2. **Session Page** (`pages/2_Session.py`)
   - Displays current round matches
   - User selects winners per court
   - "Submit" → calls `session_service.process_round_completion()`
   - Round results recorded to DB, next round generated

3. **Rating Recalculation** (`recalculate_ratings.py`)
   - Standalone script, run manually
   - Fetches all matches, rebuilds TTT history, updates player mu/sigma

---

## Design Notes

### Service Layer Pattern
The service layer (`*_service.py`) exists to:
1. Keep UI code focused on presentation
2. Keep domain logic (`session_logic.py`) free of database dependencies
3. Enable testing of business logic without mocking DB

### Optimizer Contract
- Input ratings are scaled to 0-5 range for stable optimization
- Output is `OptimizerResult` with `matches`, `partner_history`, `success`
- Gender penalties adjust effective "power" for balancing

### TrueSkill Through Time
- Uses local `TrueSkillThroughTime.py/` library
- `prior_mu`/`prior_sigma` are static; `mu`/`sigma` evolve with matches
- `conservative_rating = mu - 3*sigma` is the lower-bound estimate
