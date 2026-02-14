import time
import pytest
from session_logic import ClubNightSession, Player
from app_types import Gender

BACKUP_WAIT_TIMEOUT = 15

@pytest.fixture
def session(sample_players, sample_gender_stats):
    return ClubNightSession(
        players=sample_players, num_courts=2, gender_stats=sample_gender_stats, is_doubles=True
    )

def test_prepare_round_starts_backup(session):
    """Calling prepare_round should start a backup calculation."""
    session.prepare_round()
    assert session.current_state.round_num == 1
    
    # Wait for backup to complete
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    assert session.backup_state is not None
    assert session.backup_state.round_num == 2

def test_promotion_of_backup(session):
    """Confirming a round should promote the backup if valid."""
    session.prepare_round()
    
    # Wait for backup
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    backup = session.backup_state
    assert backup.round_num == 2
    
    # Finalize current round
    match = session.current_state.matches[0]
    session.finalize_round({1: match.team_1, 2: session.current_state.matches[1].team_1})
    
    # Prepare next round - should promote backup
    session.prepare_round()
    
    assert session.current_state == backup
    assert session.current_state.round_num == 2

def test_invalidation_on_add_player(session):
    """Adding a player should invalidate the backup."""
    session.prepare_round()
    
    # Wait for backup
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    assert session.backup_state is not None
    
    # Invasive change
    session.add_player(name="InvasivePlayer", gender=Gender.MALE)
    
    assert session.backup_state is None

def test_invalidation_on_remove_player(session):
    """Removing a player should invalidate the backup."""
    # Force 1 court so we have resting players to remove immediately
    session.update_courts(1)
    session.prepare_round()
    
    # Wait for backup
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    assert session.backup_state is not None
    
    # Invasive change
    resting_player = list(session.current_state.resting_players)[0]
    session.remove_player(resting_player)
    
    assert session.backup_state is None

def test_invalidation_on_court_update(session):
    """Updating court count should invalidate the backup."""
    session.prepare_round()
    
    # Wait for backup
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    assert session.backup_state is not None
    
    # Invasive change
    session.update_courts(1)
    
    assert session.backup_state is None

def test_invalidation_on_weight_update(session):
    """Updating weights should invalidate the backup."""
    session.prepare_round()
    
    # Wait for backup
    start_time = time.time()
    while session.backup_state is None and time.time() - start_time < BACKUP_WAIT_TIMEOUT:
        time.sleep(0.1)
    
    assert session.backup_state is not None
    
    # Invasive change
    session.update_weights({"skill": 5.0, "power": 1.0, "pairing": 1.0})
    
    assert session.backup_state is None
