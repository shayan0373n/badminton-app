# Badminton Club Night Manager

A Streamlit-based application for organizing badminton club night sessions with optimized match generation and skill-based player ratings.

## Features

- **Smart Match Optimization**: Uses Gurobi to solve a multi-objective integer linear program (ILP) that minimizes a weighted combination of:
  - *Skill spread* — difference between the strongest and weakest player on each court
  - *Team power imbalance* — difference in combined ratings between opposing teams (doubles)
  - *Partner repetition* — penalizes frequently repeated pairings to encourage variety
- **TrueSkill Through Time Ratings**: Player skill tracking with uncertainty-aware ratings that improve over time
- **Flexible Game Modes**: Support for both singles and doubles matches
- **Session Management**: Create, pause, resume, and track multiple sessions
- **Player Registry**: Persistent player database with customizable prior skill estimates
- **Gender Balancing**: Optional penalties for team compositions to encourage mixed-gender play

## Tech Stack

- **Frontend**: Streamlit
- **Optimization**: Gurobi
- **Database**: Supabase
- **Rating System**: TrueSkill Through Time

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure Supabase credentials in `.streamlit/secrets.toml`:
   ```toml
   SUPABASE_URL = "your-supabase-url"
   SUPABASE_KEY = "your-supabase-key"
   ```

3. Run the application:
   ```bash
   streamlit run 1_Setup.py
   ```

## Usage

1. **Setup Page**: Configure player registry, session parameters, and court count
2. **Session Page**: Run matches, record results, and view standings

## Project Structure

```
├── 1_Setup.py           # Main entry point and session setup UI
├── pages/
│   └── 2_Session.py     # Active session management UI
├── session_logic.py     # Core session and player logic
├── optimizer.py         # Match generation optimization
├── database.py          # Supabase database operations
├── recalculate_ratings.py # TTT rating recalculation
└── constants.py         # Application constants
```

## License

MIT
