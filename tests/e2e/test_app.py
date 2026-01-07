from streamlit.testing.v1 import AppTest
import pytest
import os
from session_logic import ClubNightSession


def test_setup_page_smoke():
    """Basic smoke test to ensure the setup page loads without crashing."""
    at = AppTest.from_file(os.path.abspath("1_Setup.py"))
    at.run(timeout=30)

    assert not at.exception
    # Check for the main title or some key text
    assert "Badminton" in at.title[0].value


def test_session_page_smoke(sample_players):
    """Basic smoke test for the Session page."""
    at = AppTest.from_file(os.path.abspath("pages/2_Session.py"))

    at.session_state.session = ClubNightSession(
        players=sample_players, num_courts=2, is_doubles=True
    )
    at.session_state.current_session_name = "Test Session"

    at.run(timeout=30)

    assert not at.exception
