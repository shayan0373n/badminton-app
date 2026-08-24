# Badminton Club Night Manager

A Streamlit-based application for organizing badminton club night sessions with optimized match generation and skill-based player ratings.

## Features

- **Smart Match Optimization**: Uses Gurobi to solve a multi-objective integer linear program (ILP) that minimizes a weighted combination of:
  - *Skill spread* — difference between the strongest and weakest player on each court (uses tier ratings)
  - *Team power imbalance* — difference in combined ratings between opposing teams (uses real skills)
  - *Court repetition* — penalizes players who frequently share a court to encourage variety
- **TrueSkill Through Time Ratings**: Player skill tracking with uncertainty-aware ratings that improve over time
- **Flexible Game Modes**: Support for both singles and doubles matches
- **Session Management**: Create, pause, resume, and track multiple sessions
- **Player Registry**: Persistent player database with customizable prior skill estimates
- **Organic Gender Balancing**: Uses Z-score normalized tier ratings so top females group with top males naturally, without hard-coded penalties

> **[Mathematical Foundations](docs/math.md)** — Detailed write-up of the Bayesian rating model, ILP formulation, and constraint programming backend.

## Tech Stack

- **Frontend**: React + Vite (the Streamlit pages are still there while it settles)
- **API**: FastAPI
- **Optimization**: OR-Tools CP-SAT (Gurobi optional)
- **Database**: Supabase
- **Rating System**: TrueSkill Through Time

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   cd frontend && npm install && cd ..
   ```

2. Configure Supabase credentials, either as environment variables or in
   `.streamlit/secrets.toml`:
   ```toml
   SUPABASE_URL = "your-supabase-url"
   SUPABASE_KEY = "your-supabase-key"
   ```

## Running

**React client** — two processes in development:

```bash
uvicorn api:app --reload            # API on :8000
cd frontend && npm run dev          # client on :5173, proxying /api
```

For a single process, build the client first and let the API serve it:

```bash
cd frontend && npm run build && cd ..
uvicorn api:app                     # everything on :8000
```

**Streamlit pages** (unchanged):

```bash
streamlit run 1_Setup.py
```

## Usage

The night runs across three screens:

1. **Setup** — pick who might come, how many courts, and whether the night
   counts toward ratings.
2. **Check-in** — the hub. Players **tap** their name to check in, **press and
   hold** to check in wanting a harder game, and **drag** one name onto another
   to play together. The side menu holds every management action. Come back here
   between rounds to change anything; changes land on the next round and never
   disturb the one in play.
3. **Session** — courts, results, and standings. Tap the winning side. Back
   returns to the hub.

## Tests

```bash
pytest                              # domain, service, and API
cd frontend && npm test             # gestures and screens
```

## Deployment

Runs on the shared `iranfin.fi` host alongside the club's other apps, which
share a single Docker Compose project and one Traefik instance.

This repo owns its own deployment: `compose.yaml` defines the service, and the
host's `/root/docker-compose.yml` pulls it in with `include:`. Relative paths in
`compose.yaml` resolve against its own directory, so the repo describes its
deployment without knowing where it is checked out — and changes to ports,
labels or mounts arrive in a pull request instead of a hand-edit on the server.

Traefik owns :80 and :443 and routes by Docker label using a Cloudflare DNS-01
resolver, so this service publishes no host ports.

```bash
# on the server, first time only
cp .env.example /root/play/.env    # fill in SUPABASE_*
chmod 600 /root/play/.env
mkdir -p /root/play/sessions && chown -R 999:999 /root/play/sessions

docker compose -f /root/docker-compose.yml up -d --build play
```

The `sessions` directory must be owned by uid 999 — the image's non-root `app`
user — or the container cannot write to it. Pickled sessions live there, so
backing them up is an ordinary directory copy.

`play.iranfin.fi` needs a Cloudflare DNS record before Traefik can issue a
certificate.

Pushes to `main` deploy via `.github/workflows/deploy.yml`, which runs both test
suites first and checks `/api/health` afterwards. It needs the repo secrets
`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, and `VPS_PATH=/root/play`.


## Project Structure

```
├── api.py               # HTTP API over the service layer
├── frontend/            # React client (setup, check-in hub, session)
├── config.py            # Secrets from env, falling back to secrets.toml
├── 1_Setup.py           # Streamlit entry point and session setup UI
├── pages/
│   └── 2_Session.py     # Streamlit active session UI
├── session_logic.py     # Core session and player logic
├── optimizer.py         # Match generation optimization
├── rating_service.py    # Tier rating and real skill computation
├── database.py          # Supabase database operations
├── recalculate_ratings.py # TTT rating recalculation
└── constants.py         # Application constants
```

## License

MIT
