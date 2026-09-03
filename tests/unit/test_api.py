"""Tests for the HTTP API.

The database is stubbed throughout: these cover routing, validation and the
snapshot contract the front end depends on, not Supabase.
"""

import pytest
from fastapi.testclient import TestClient

import api
import database
import session_logic
from app_types import Gender
from session_logic import Player


REGISTRY_MU = {
    "Alice": 26.0,
    "Bob": 24.0,
    "Charlie": 30.0,
    "Dave": 22.0,
    "Eve": 28.0,
    "Frank": 20.0,
    "Grace": 32.0,
    "Heidi": 18.0,
}


@pytest.fixture
def registry() -> dict[str, Player]:
    return {
        name: Player(
            name=name,
            gender=Gender.FEMALE if name in {"Alice", "Eve", "Grace", "Heidi"} else Gender.MALE,
            prior_mu=mu,
            database_id=i,
        )
        for i, (name, mu) in enumerate(REGISTRY_MU.items(), 1)
    }


@pytest.fixture
def client(tmp_path, monkeypatch, registry):
    """A TestClient with sessions on disk in tmp_path and the database stubbed."""
    monkeypatch.setattr(session_logic, "SESSIONS_DIR", str(tmp_path / "sessions"))

    monkeypatch.setattr(database.PlayerDB, "get_all_players", staticmethod(lambda: registry))
    monkeypatch.setattr(api.PlayerDB, "get_all_players", staticmethod(lambda: registry))
    monkeypatch.setattr(
        database.SessionDB, "create_session", staticmethod(lambda name, is_doubles: 1)
    )
    monkeypatch.setattr(database.MatchDB, "delete_by_session", staticmethod(lambda sid: None))
    monkeypatch.setattr(database.MatchDB, "add_match", staticmethod(lambda **kw: None))
    monkeypatch.setattr(database.PlayerDB, "upsert_players", staticmethod(lambda players: None))

    # Locks are keyed by name and cached across tests; a fresh mapping keeps
    # each test's locks bound to its own event loop.
    api._session_locks.clear()

    with TestClient(api.app) as c:
        yield c


def create(client, name="Night", candidates=None, **kwargs) -> dict:
    body = {"name": name, "candidates": candidates or list(REGISTRY_MU), **kwargs}
    response = client.post("/api/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def check_in_all(client, name="Night", players=None) -> dict:
    snapshot = {}
    for player in players or list(REGISTRY_MU):
        response = client.post(f"/api/sessions/{name}/checkin/{player}")
        assert response.status_code == 200, response.text
        snapshot = response.json()
    return snapshot


# =============================================================================
# Registry
# =============================================================================


def test_list_players_sorted_by_name(client):
    players = client.get("/api/players").json()["players"]

    assert len(players) == len(REGISTRY_MU)
    names = [p["name"] for p in players]
    assert names == sorted(names, key=str.casefold)


# =============================================================================
# Session lifecycle
# =============================================================================


def test_create_session_starts_with_nobody_checked_in(client):
    snapshot = create(client)

    assert snapshot["round_num"] == 0
    assert len(snapshot["candidates"]) == len(REGISTRY_MU)
    assert all(not c["checked_in"] for c in snapshot["candidates"])
    assert snapshot["rounds"] == []


def test_create_rejects_duplicate_name(client):
    create(client)
    response = client.post(
        "/api/sessions", json={"name": "Night", "candidates": ["Alice"]}
    )
    assert response.status_code == 409


def test_create_rejects_unknown_candidate(client):
    response = client.post(
        "/api/sessions", json={"name": "Night", "candidates": ["Nobody"]}
    )
    assert response.status_code == 400
    assert "Nobody" in response.json()["detail"]


def test_create_rejects_empty_candidate_list(client):
    response = client.post("/api/sessions", json={"name": "Night", "candidates": []})
    assert response.status_code == 422


def test_get_unknown_session_is_404(client):
    assert client.get("/api/sessions/ghost").status_code == 404


def test_list_and_delete_sessions(client):
    create(client, "Night")
    create(client, "Other")

    names = [s["name"] for s in client.get("/api/sessions").json()["sessions"]]
    assert names == ["Night", "Other"]

    assert client.delete("/api/sessions/Night").status_code == 204
    names = [s["name"] for s in client.get("/api/sessions").json()["sessions"]]
    assert names == ["Other"]


# =============================================================================
# Check-in
# =============================================================================


def test_check_in_puts_a_player_in_the_pool(client):
    create(client)
    snapshot = client.post("/api/sessions/Night/checkin/Alice").json()

    alice = next(c for c in snapshot["candidates"] if c["name"] == "Alice")
    assert alice["checked_in"] is True
    assert alice["challenging"] is False


def test_long_press_checks_in_with_challenge(client):
    create(client)
    snapshot = client.post(
        "/api/sessions/Night/checkin/Alice", json={"wants_challenge": True}
    ).json()

    alice = next(c for c in snapshot["candidates"] if c["name"] == "Alice")
    assert alice["checked_in"] is True
    assert alice["challenging"] is True


def test_double_check_in_conflicts(client):
    create(client)
    client.post("/api/sessions/Night/checkin/Alice")
    assert client.post("/api/sessions/Night/checkin/Alice").status_code == 409


def test_check_in_unknown_player_conflicts(client):
    create(client, candidates=["Alice", "Bob"])
    assert client.post("/api/sessions/Night/checkin/Charlie").status_code == 409


def test_check_out_returns_them_to_the_candidate_list(client):
    create(client)
    client.post("/api/sessions/Night/checkin/Alice")
    snapshot = client.delete("/api/sessions/Night/checkin/Alice").json()

    alice = next(c for c in snapshot["candidates"] if c["name"] == "Alice")
    assert alice["checked_in"] is False
    # Still listed for tonight -- checking out is not the same as leaving.
    assert "Alice" in [c["name"] for c in snapshot["candidates"]]


def test_check_out_when_not_checked_in_is_404(client):
    create(client)
    assert client.delete("/api/sessions/Night/checkin/Alice").status_code == 404


def test_challenge_can_be_toggled_after_check_in(client):
    create(client)
    client.post("/api/sessions/Night/checkin/Alice")

    on = client.post(
        "/api/sessions/Night/challenge/Alice", json={"wants_challenge": True}
    ).json()
    assert next(c for c in on["candidates"] if c["name"] == "Alice")["challenging"]

    off = client.post(
        "/api/sessions/Night/challenge/Alice", json={"wants_challenge": False}
    ).json()
    assert not next(c for c in off["candidates"] if c["name"] == "Alice")["challenging"]


def test_challenge_requires_check_in(client):
    create(client)
    response = client.post(
        "/api/sessions/Night/challenge/Alice", json={"wants_challenge": True}
    )
    assert response.status_code == 404


# =============================================================================
# Pairing groups
# =============================================================================


def test_pairing_two_players_creates_a_group(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob"])

    snapshot = client.post(
        "/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"}
    ).json()

    assert len(snapshot["groups"]) == 1
    assert snapshot["groups"][0]["members"] == ["Alice", "Bob"]
    assert all(
        c["groups"] == [snapshot["groups"][0]["name"]]
        for c in snapshot["candidates"]
        if c["name"] in {"Alice", "Bob"}
    )


def test_dragging_a_third_player_makes_a_second_pair(client):
    """A pair is always two people, so Alice ends up in two of them."""
    create(client)
    check_in_all(client, players=["Alice", "Bob", "Charlie"])
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})

    snapshot = client.post(
        "/api/sessions/Night/groups", json={"first": "Charlie", "second": "Alice"}
    ).json()

    assert [g["members"] for g in snapshot["groups"]] == [
        ["Alice", "Bob"],
        ["Alice", "Charlie"],
    ]
    by_name = {c["name"]: c for c in snapshot["candidates"]}
    assert len(by_name["Alice"]["groups"]) == 2
    assert len(by_name["Bob"]["groups"]) == 1


def test_pairing_across_two_groups_does_not_merge_them(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob", "Charlie", "Dave"])
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})
    client.post("/api/sessions/Night/groups", json={"first": "Charlie", "second": "Dave"})

    snapshot = client.post(
        "/api/sessions/Night/groups", json={"first": "Bob", "second": "Charlie"}
    ).json()

    assert [g["members"] for g in snapshot["groups"]] == [
        ["Alice", "Bob"],
        ["Charlie", "Dave"],
        ["Bob", "Charlie"],
    ]


def test_pairing_the_same_two_again_is_a_no_op(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob"])
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})

    snapshot = client.post(
        "/api/sessions/Night/groups", json={"first": "Bob", "second": "Alice"}
    ).json()

    assert len(snapshot["groups"]) == 1


def test_dissolving_one_pair_leaves_the_others(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob", "Charlie"])
    first = client.post(
        "/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"}
    ).json()["groups"][0]["name"]
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Charlie"})

    snapshot = client.delete(f"/api/sessions/Night/groups/{first}").json()

    assert [g["members"] for g in snapshot["groups"]] == [["Alice", "Charlie"]]
    by_name = {c["name"]: c for c in snapshot["candidates"]}
    assert len(by_name["Alice"]["groups"]) == 1
    assert by_name["Bob"]["groups"] == []


def test_pairing_requires_both_checked_in(client):
    create(client)
    check_in_all(client, players=["Alice"])

    response = client.post(
        "/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"}
    )
    assert response.status_code == 400


def test_pairing_a_player_with_themselves_is_rejected(client):
    create(client)
    check_in_all(client, players=["Alice"])

    response = client.post(
        "/api/sessions/Night/groups", json={"first": "Alice", "second": "Alice"}
    )
    assert response.status_code == 400


def test_removing_one_member_leaves_the_rest_paired(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob", "Charlie"])
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})
    client.post("/api/sessions/Night/groups", json={"first": "Charlie", "second": "Alice"})

    snapshot = client.delete("/api/sessions/Night/groups/members/Charlie").json()

    assert [g["members"] for g in snapshot["groups"]] == [["Alice", "Bob"]]
    assert next(c for c in snapshot["candidates"] if c["name"] == "Charlie")["groups"] == []


def test_dissolving_a_group_frees_everyone(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob"])
    group = client.post(
        "/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"}
    ).json()["groups"][0]["name"]

    snapshot = client.delete(f"/api/sessions/Night/groups/{group}").json()

    assert snapshot["groups"] == []
    assert all(c["groups"] == [] for c in snapshot["candidates"])


def test_a_group_of_one_is_not_reported(client):
    """A lone member imposes no partner constraint, so it is not a group."""
    create(client)
    check_in_all(client, players=["Alice", "Bob"])
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})

    snapshot = client.delete("/api/sessions/Night/groups/members/Bob").json()

    assert snapshot["groups"] == []


# =============================================================================
# Rounds
# =============================================================================


def test_round_needs_enough_players(client):
    create(client)
    check_in_all(client, players=["Alice", "Bob"])

    response = client.post("/api/sessions/Night/rounds")
    assert response.status_code == 400


def test_first_round_starts_the_night(client):
    create(client)
    check_in_all(client)

    snapshot = client.post("/api/sessions/Night/rounds").json()

    assert snapshot["round_num"] == 1
    assert len(snapshot["rounds"]) == 1
    assert snapshot["rounds"][0]["matches"]


def test_matches_name_four_distinct_players_per_court(client):
    create(client)
    check_in_all(client)
    snapshot = client.post("/api/sessions/Night/rounds").json()

    for match in snapshot["rounds"][0]["matches"]:
        players = match["team_1"] + match["team_2"]
        assert len(players) == 4
        assert len(set(players)) == 4


def test_paired_players_share_a_team(client):
    create(client)
    check_in_all(client)
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})

    snapshot = client.post("/api/sessions/Night/rounds").json()

    teams = [
        set(side)
        for match in snapshot["rounds"][0]["matches"]
        for side in (match["team_1"], match["team_2"])
    ]
    playing = {p for team in teams for p in team}
    if {"Alice", "Bob"} <= playing:
        assert any({"Alice", "Bob"} <= team for team in teams)


def test_locked_flag_marks_required_partners(client):
    create(client)
    check_in_all(client)
    client.post("/api/sessions/Night/groups", json={"first": "Alice", "second": "Bob"})
    snapshot = client.post("/api/sessions/Night/rounds").json()

    for match in snapshot["rounds"][0]["matches"]:
        if set(match["team_1"]) == {"Alice", "Bob"}:
            assert match["locked_1"] is True
        if set(match["team_2"]) == {"Alice", "Bob"}:
            assert match["locked_2"] is True


def test_next_round_appends_to_history(client):
    create(client)
    check_in_all(client)
    client.post("/api/sessions/Night/rounds")

    snapshot = client.post("/api/sessions/Night/rounds").json()

    assert snapshot["round_num"] == 2
    assert [r["round_num"] for r in snapshot["rounds"]] == [1, 2]


# =============================================================================
# Results
# =============================================================================


def test_recording_a_winner_updates_standings(client):
    create(client)
    check_in_all(client)
    snapshot = client.post("/api/sessions/Night/rounds").json()
    match = snapshot["rounds"][0]["matches"][0]

    updated = client.put(
        f"/api/sessions/Night/rounds/0/courts/{match['court']}", json={"winner": 1}
    ).json()

    assert updated["rounds"][0]["matches"][0]["winner"] == 1
    standings = {s["name"]: s for s in updated["standings"]}
    for winner in match["team_1"]:
        assert standings[winner]["wins"] == 1
        assert standings[winner]["matches"] == 1
    for loser in match["team_2"]:
        assert standings[loser]["wins"] == 0
        assert standings[loser]["matches"] == 1


def test_winner_can_be_cleared(client):
    create(client)
    check_in_all(client)
    snapshot = client.post("/api/sessions/Night/rounds").json()
    court = snapshot["rounds"][0]["matches"][0]["court"]

    client.put(f"/api/sessions/Night/rounds/0/courts/{court}", json={"winner": 2})
    cleared = client.put(
        f"/api/sessions/Night/rounds/0/courts/{court}", json={"winner": None}
    ).json()

    assert cleared["rounds"][0]["matches"][0]["winner"] is None
    assert all(s["matches"] == 0 for s in cleared["standings"])


def test_winner_must_be_one_or_two(client):
    create(client)
    check_in_all(client)
    snapshot = client.post("/api/sessions/Night/rounds").json()
    court = snapshot["rounds"][0]["matches"][0]["court"]

    response = client.put(
        f"/api/sessions/Night/rounds/0/courts/{court}", json={"winner": 3}
    )
    assert response.status_code == 400


def test_unknown_round_or_court_is_404(client):
    create(client)
    check_in_all(client)
    client.post("/api/sessions/Night/rounds")

    assert (
        client.put("/api/sessions/Night/rounds/9/courts/1", json={"winner": 1}).status_code
        == 404
    )
    assert (
        client.put("/api/sessions/Night/rounds/0/courts/99", json={"winner": 1}).status_code
        == 404
    )


def test_submit_reports_recorded_and_unreported(client):
    create(client)
    check_in_all(client)
    snapshot = client.post("/api/sessions/Night/rounds").json()
    courts = [m["court"] for m in snapshot["rounds"][0]["matches"]]
    client.put(f"/api/sessions/Night/rounds/0/courts/{courts[0]}", json={"winner": 1})

    result = client.post("/api/sessions/Night/submit").json()

    assert result["recorded"] == 1
    assert result["unreported"] == len(courts) - 1
    assert result["session"]["results_dirty"] is False


# =============================================================================
# Settings
# =============================================================================


def test_courts_and_weights_can_be_changed(client):
    create(client)
    snapshot = client.patch(
        "/api/sessions/Night", json={"num_courts": 3, "weights": {"skill": 4.0}}
    ).json()

    assert snapshot["num_courts"] == 3
    assert snapshot["weights"]["skill"] == 4.0
    # Untouched weights keep their previous value rather than resetting.
    assert "power" in snapshot["weights"]


def test_court_count_must_be_positive(client):
    create(client)
    assert client.patch("/api/sessions/Night", json={"num_courts": 0}).status_code == 422


# =============================================================================
# Candidate list management
# =============================================================================


def test_candidate_can_be_added_and_removed(client):
    create(client, candidates=["Alice", "Bob"])

    added = client.post("/api/sessions/Night/candidates/Charlie").json()
    assert "Charlie" in [c["name"] for c in added["candidates"]]

    removed = client.delete("/api/sessions/Night/candidates/Charlie").json()
    assert "Charlie" not in [c["name"] for c in removed["candidates"]]


def test_removing_a_checked_in_candidate_checks_them_out_first(client):
    create(client, candidates=["Alice", "Bob"])
    client.post("/api/sessions/Night/checkin/Alice")

    snapshot = client.delete("/api/sessions/Night/candidates/Alice").json()

    assert "Alice" not in [c["name"] for c in snapshot["candidates"]]


def test_guest_is_created_and_checked_in(client):
    create(client, candidates=["Alice"])

    snapshot = client.post(
        "/api/sessions/Night/players", json={"name": "Zoe", "gender": "F", "mu": 25.0}
    ).json()

    zoe = next(c for c in snapshot["candidates"] if c["name"] == "Zoe")
    assert zoe["checked_in"] is True


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
