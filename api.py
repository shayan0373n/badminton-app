"""
HTTP API for the Badminton App.

This layer is deliberately thin: it routes, validates and serializes, and calls
the service layer for everything else. No business logic lives here -- the rules
about rounds, ratings and pairing stay in the domain and service layers, so the
front end can never drift from them.

Run locally with:
    uvicorn api:app --reload
"""

import asyncio
import logging
import os
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from logger import setup_logging

setup_logging(app_level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO))

import player_service
import season_service
import session_service
from app_types import Gender
from constants import DEFAULT_WEIGHTS, TTT_DEFAULT_SIGMA
from database import PlayerDB
from exceptions import DatabaseError, SessionError
from session_logic import ClubNightSession, Player, SessionManager

logger = logging.getLogger("app.api")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")


# =============================================================================
# Concurrency
# =============================================================================

# One shared device means a single writer, so a per-session lock is all the
# mutual exclusion needed: it serializes writes to the same pickled session
# without introducing any cross-session contention.
_session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@asynccontextmanager
async def session_lock(session_name: str):
    async with _session_locks[session_name]:
        yield


async def run_blocking(func, /, *args, **kwargs):
    """Runs blocking work in a worker thread.

    Round generation is a constraint solve bounded by OPTIMIZER_TIME_LIMIT, so
    running it inline would stall the event loop for every other request.
    """
    return await asyncio.to_thread(func, *args, **kwargs)


# =============================================================================
# Request models
# =============================================================================


# A session name becomes a file name under sessions/, so it may not contain a
# path separator or start with a dot.
SESSION_NAME_PATTERN = r"^[^/\\.][^/\\]*$"


class Weights(BaseModel, extra="forbid"):
    skill: float = Field(ge=0)
    power: float = Field(ge=0)
    pairing: float = Field(ge=0)


class WeightChanges(BaseModel, extra="forbid"):
    skill: float | None = Field(default=None, ge=0)
    power: float | None = Field(default=None, ge=0)
    pairing: float | None = Field(default=None, ge=0)


class CreateSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=SESSION_NAME_PATTERN)
    candidates: list[str] = Field(min_length=1)
    num_courts: int = Field(ge=1, le=20)
    is_doubles: bool
    is_recorded: bool
    # Omitted means DEFAULT_WEIGHTS; when given, all three must be named.
    weights: Weights | None = None


class SessionSettingsRequest(BaseModel):
    num_courts: int | None = Field(default=None, ge=1, le=20)
    weights: WeightChanges | None = None


class CheckInRequest(BaseModel):
    wants_challenge: bool = False


class ChallengeRequest(BaseModel):
    wants_challenge: bool


class PairRequest(BaseModel):
    first: str
    second: str


class WinnerRequest(BaseModel):
    winner: int | None = Field(default=None, description="1, 2, or null to clear")


class GuestRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    gender: Gender
    mu: float = Field(ge=0.0, le=60.0)


class RegistryPlayer(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    gender: Gender
    prior_mu: float = Field(ge=0.0, le=60.0)


class RegistryRequest(BaseModel):
    players: list[RegistryPlayer]


# =============================================================================
# App
# =============================================================================

app = FastAPI(title="Badminton Club Rotation", version="1.0.0")

# Only needed while the Vite dev server runs on its own port; the production
# build is served from this same origin and never triggers a preflight.
_dev_origins = os.environ.get("DEV_ORIGINS", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in _dev_origins.split(",") if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_session(name: str) -> ClubNightSession:
    """Loads a session by name; 404 if there is none, 500 if its file is unreadable."""
    try:
        session = SessionManager.load(name)
    except SessionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        ) from e
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No session named '{name}'"
        )
    return session


SessionName = Annotated[str, Path(min_length=1, max_length=80, pattern=SESSION_NAME_PATTERN)]


# =============================================================================
# Registry
# =============================================================================


@app.get("/api/players")
async def list_players() -> dict[str, Any]:
    """Returns the member registry in name order, so people can be found by name."""
    try:
        registry = await run_blocking(PlayerDB.get_all_players)
    except DatabaseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {
        "players": sorted(
            (
                {
                    "name": p.name,
                    "gender": p.gender.value,
                    "prior_mu": p.prior_mu,
                    "mu": p.mu,
                    "sigma": p.sigma,
                    "rating": p.conservative_rating,
                }
                for p in registry.values()
            ),
            key=lambda p: p["name"].casefold(),
        )
    }


@app.put("/api/players")
async def save_players(payload: RegistryRequest) -> dict[str, Any]:
    """Applies registry edits: adds, renames by name, and prior_mu changes."""
    try:
        old = await run_blocking(PlayerDB.get_all_players)
        new: dict[str, Player] = {}
        for entry in payload.players:
            existing = old.get(entry.name)
            new[entry.name] = Player(
                name=entry.name,
                gender=entry.gender,
                prior_mu=entry.prior_mu,
                prior_sigma=existing.prior_sigma if existing else TTT_DEFAULT_SIGMA,
                mu=existing.mu if existing else None,
                sigma=existing.sigma if existing else None,
                database_id=existing.database_id if existing else None,
            )
        await run_blocking(player_service.sync_registry_to_database, old, new)
    except DatabaseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return {"saved": len(payload.players)}


@app.post("/api/ratings/recalculate")
async def recalculate_ratings() -> dict[str, Any]:
    """Rebuilds this season's ratings from match history and writes them back."""
    try:
        players, match_count = await run_blocking(season_service.recalculate_ratings)
    except DatabaseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    return {"players": len(players), "matches": match_count}


# =============================================================================
# Session lifecycle
# =============================================================================


@app.get("/api/sessions")
async def list_sessions() -> dict[str, Any]:
    """Returns resumable sessions with just enough detail to pick one.

    A session whose file cannot be read is left out of the list (and logged by
    SessionManager); the file itself is kept.
    """
    summaries = []
    for name in SessionManager.list_sessions():
        try:
            session = SessionManager.load(name)
        except SessionError:
            continue
        if session is None:
            continue
        summaries.append(
            {
                "name": name,
                "round_num": session.round_num,
                "checked_in": len(session.player_pool),
                "candidates": len(session.candidates),
                "is_doubles": session.is_doubles,
                "is_recorded": session.is_recorded,
            }
        )
    return {"sessions": sorted(summaries, key=lambda s: s["name"])}


@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(payload: CreateSessionRequest) -> dict[str, Any]:
    """Creates a session with an open roster; nobody is checked in yet."""
    if payload.name in SessionManager.list_sessions():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A session named '{payload.name}' already exists",
        )

    try:
        registry = await run_blocking(PlayerDB.get_all_players)
    except DatabaseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    unknown = [n for n in payload.candidates if n not in registry]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not in the registry: {', '.join(sorted(unknown))}",
        )

    candidates = {name: registry[name] for name in payload.candidates}

    try:
        session = await run_blocking(
            session_service.create_new_session,
            session_name=payload.name,
            candidates=candidates,
            num_courts=payload.num_courts,
            weights=payload.weights.model_dump() if payload.weights else dict(DEFAULT_WEIGHTS),
            is_doubles=payload.is_doubles,
            is_recorded=payload.is_recorded,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return session_service.build_session_snapshot(session, payload.name)


@app.get("/api/sessions/{name}")
async def get_session(name: SessionName) -> dict[str, Any]:
    """Returns the full computed view of a session."""
    session = load_session(name)
    return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(name: SessionName) -> None:
    """Discards a session. Submitted results already in the database survive."""
    load_session(name)
    async with session_lock(name):
        SessionManager.clear(name)


@app.patch("/api/sessions/{name}")
async def update_settings(
    name: SessionName, payload: SessionSettingsRequest
) -> dict[str, Any]:
    """Changes courts or weights. Both take effect from the next round."""
    async with session_lock(name):
        session = load_session(name)
        try:
            weights = (
                payload.weights.model_dump(exclude_none=True) if payload.weights else None
            )
            session_service.update_settings(
                session, name, num_courts=payload.num_courts, weights=weights
            )
        except SessionError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}/match-history")
async def reset_match_history(name: SessionName) -> dict[str, Any]:
    """Forgets who has played with and against whom, from the next round."""
    async with session_lock(name):
        session = load_session(name)
        session_service.reset_match_history(session, name)
        return session_service.build_session_snapshot(session, name)


# =============================================================================
# Check-in hub
# =============================================================================


@app.post("/api/sessions/{name}/checkin/{player}")
async def check_in(
    name: SessionName, player: str, payload: CheckInRequest = Body(default=CheckInRequest())
) -> dict[str, Any]:
    """Checks a candidate in, optionally flagging them as wanting a harder game."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.check_in_player(
            session, name, player, wants_challenge=payload.wants_challenge
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{player} is unknown to this session or already checked in",
            )
        return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}/checkin/{player}")
async def check_out(name: SessionName, player: str) -> dict[str, Any]:
    """Checks a player out, at once, whether or not they are on a court."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.check_out_player(session, name, player):
            raise HTTPException(status_code=404, detail=f"{player} is not checked in")
        return session_service.build_session_snapshot(session, name)


@app.post("/api/sessions/{name}/challenge/{player}")
async def set_challenge(
    name: SessionName, player: str, payload: ChallengeRequest
) -> dict[str, Any]:
    """Sets or clears a player's request for a harder game."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.set_player_challenge(
            session, name, player, payload.wants_challenge
        ):
            raise HTTPException(status_code=404, detail=f"{player} is not checked in")
        return session_service.build_session_snapshot(session, name)


@app.post("/api/sessions/{name}/groups")
async def create_pair(name: SessionName, payload: PairRequest) -> dict[str, Any]:
    """Puts two checked-in players in the same group, merging existing groups."""
    async with session_lock(name):
        session = load_session(name)
        if session_service.pair_players(session, name, payload.first, payload.second) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both players must be checked in, and cannot be the same person",
            )
        return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}/groups/{group}")
async def remove_group(name: SessionName, group: str) -> dict[str, Any]:
    """Breaks up a whole group."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.dissolve_group(session, name, group):
            raise HTTPException(status_code=404, detail=f"No group named '{group}'")
        return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}/groups/members/{player}")
async def remove_from_group(name: SessionName, player: str) -> dict[str, Any]:
    """Pulls one player out of their group, leaving the rest intact."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.unpair_player(session, name, player):
            raise HTTPException(status_code=404, detail=f"{player} is not in a group")
        return session_service.build_session_snapshot(session, name)


@app.post("/api/sessions/{name}/players", status_code=status.HTTP_201_CREATED)
async def add_guest(name: SessionName, payload: GuestRequest) -> dict[str, Any]:
    """Creates a guest, saves them to the registry, and checks them in."""
    async with session_lock(name):
        session = load_session(name)
        try:
            success, error = await run_blocking(
                session_service.add_guest_player,
                session,
                name,
                payload.name,
                payload.gender,
                payload.mu,
            )
        except DatabaseError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        if not success:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error)
        return session_service.build_session_snapshot(session, name)


@app.post("/api/sessions/{name}/candidates/{player}", status_code=status.HTTP_201_CREATED)
async def add_candidate(name: SessionName, player: str) -> dict[str, Any]:
    """Adds a registry member to tonight's candidate list without checking them in."""
    async with session_lock(name):
        session = load_session(name)
        if player in session.candidates:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{player} is already on tonight's list",
            )
        try:
            registry = await run_blocking(PlayerDB.get_all_players)
        except DatabaseError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        if player not in registry:
            raise HTTPException(status_code=404, detail=f"{player} is not in the registry")

        session_service.add_candidate(session, name, registry[player])
        return session_service.build_session_snapshot(session, name)


@app.delete("/api/sessions/{name}/candidates/{player}")
async def remove_candidate(name: SessionName, player: str) -> dict[str, Any]:
    """Drops someone from tonight's list entirely, checking them out first."""
    async with session_lock(name):
        session = load_session(name)
        if not session_service.remove_candidate(session, name, player):
            raise HTTPException(status_code=404, detail=f"{player} is not on tonight's list")
        return session_service.build_session_snapshot(session, name)


# =============================================================================
# Rounds and results
# =============================================================================


@app.post("/api/sessions/{name}/rounds")
async def next_round(name: SessionName) -> dict[str, Any]:
    """Generates a round.

    The first call starts the night; each later call solves the next one, which
    is when setting changes land.
    """
    async with session_lock(name):
        session = load_session(name)

        if len(session.player_pool) < session.players_per_court:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not enough players checked in to fill a court",
            )

        before = session.round_num
        await run_blocking(session_service.advance_to_next_round, session, name)

        if session.round_num == before:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No valid round could be formed with these players and pairings",
            )
        return session_service.build_session_snapshot(session, name)


@app.put("/api/sessions/{name}/rounds/{round_index}/courts/{court}")
async def set_winner(
    name: SessionName, round_index: int, court: int, payload: WinnerRequest
) -> dict[str, Any]:
    """Records or clears the winning side of one court."""
    if payload.winner not in (None, 1, 2):
        raise HTTPException(status_code=400, detail="winner must be 1, 2, or null")

    async with session_lock(name):
        session = load_session(name)
        try:
            session_service.save_court_result(
                session, name, round_index, court, payload.winner
            )
        except SessionError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return session_service.build_session_snapshot(session, name)


@app.post("/api/sessions/{name}/submit")
async def submit_results(name: SessionName) -> dict[str, Any]:
    """Uploads every reported result to the database. Safe to call repeatedly."""
    async with session_lock(name):
        session = load_session(name)
        try:
            recorded, unreported = await run_blocking(
                session_service.submit_session_results, session, name
            )
        except DatabaseError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        return {
            "recorded": recorded,
            "unreported": unreported,
            "session": session_service.build_session_snapshot(session, name),
        }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# =============================================================================
# Static front end
# =============================================================================

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """Serves the built client, letting it own its own routing."""
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
