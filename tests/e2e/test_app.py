from streamlit.testing.v1 import AppTest
import pytest
import os
from constants import DEFAULT_WEIGHTS
from session_logic import ClubNightSession


def test_setup_page_smoke():
    """Basic smoke test to ensure the setup page loads without crashing."""
    at = AppTest.from_file(os.path.abspath("1_Setup.py"))
    at.run(timeout=30)

    assert not at.exception
    # Check for the main title or some key text
    assert "Badminton" in at.title[0].value


def test_session_page_smoke(sample_players, sample_gender_stats):
    """Basic smoke test for the Session page."""
    at = AppTest.from_file(os.path.abspath("pages/2_Session.py"))

    at.session_state.session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )
    at.session_state.current_session_name = "Test Session"

    at.run(timeout=30)

    assert not at.exception


def test_session_page_unentered_games(sample_players, sample_gender_stats):
    """Test that unentered games from previous rounds are displayed on the session page."""
    at = AppTest.from_file(os.path.abspath("pages/2_Session.py"))

    # Set up a session with 2 rounds
    session = ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, weights=DEFAULT_WEIGHTS, is_doubles=True
    )
    # Generate Round 1
    session.prepare_round()
    match1, match2 = session.current_round_matches[0], session.current_round_matches[1]

    # Set only one court winner in Round 1
    session.set_court_result(0, match1.court, match1.team_1)
    # Leave match2 unentered (Winners by court has no entry for match2.court)

    # Advance to Round 2
    session.finalize_round()
    session.prepare_round()

    at.session_state.session = session
    at.session_state.current_session_name = "Test Session"
    # View Round 2 (index 1)
    at.session_state.viewing_round_idx = 1

    at.run(timeout=30)

    assert not at.exception

    # Assert that the "⏳ Unentered Games" header is rendered
    subheaders = [s.value for s in at.subheader]
    assert any("Unentered Games" in sh for sh in subheaders)
