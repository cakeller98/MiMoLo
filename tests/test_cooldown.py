"""Tests for cooldown timer."""

from datetime import UTC, datetime, timedelta

import pytest

from mimolo.core.cooldown import CooldownState, CooldownTimer


def test_cooldown_initialization():
    """Test cooldown timer initialization."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    assert timer.cooldown_seconds == 10.0
    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None


def test_cooldown_invalid_duration():
    """Test that invalid duration raises ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        CooldownTimer(cooldown_seconds=-1.0)

    with pytest.raises(ValueError, match="must be positive"):
        CooldownTimer(cooldown_seconds=0.0)


def test_cooldown_resetting_event_opens_segment():
    """Test that resetting event opens segment from IDLE."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    opened = timer.on_resetting_event(now)

    assert opened is True
    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.start_time == now
    assert timer.segment_state.last_event_time == now
    assert timer.segment_state.resets_count == 0


def test_cooldown_resetting_event_resets_timer():
    """Test that resetting event resets timer in ACTIVE state."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    later = now + timedelta(seconds=5)
    opened = timer.on_resetting_event(later)

    assert opened is False
    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.last_event_time == later
    assert timer.segment_state.resets_count == 1


def test_cooldown_non_resetting_event():
    """Test that non-resetting event updates timestamp but doesn't reset timer."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    # Open segment
    timer.on_resetting_event(start)

    # Non-resetting event
    later = start + timedelta(seconds=3)
    timer.on_non_resetting_event(later)

    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.last_event_time == later
    assert timer.segment_state.resets_count == 0


def test_cooldown_expiration():
    """Test cooldown expiration detection."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    timer.on_resetting_event(start)

    # Check before expiration
    check_time = start + timedelta(seconds=5)
    expired = timer.check_expiration(check_time)
    assert expired is False
    assert timer.state == CooldownState.ACTIVE

    # Check after expiration
    check_time = start + timedelta(seconds=11)
    expired = timer.check_expiration(check_time)
    assert expired is True
    assert timer.state == CooldownState.CLOSING


def test_cooldown_close_segment():
    """Test segment closing."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    segment = timer.close_segment()

    assert segment is not None
    assert segment.start_time == now
    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None


def test_cooldown_close_segment_no_segment():
    """Test that closing without segment raises RuntimeError."""
    timer = CooldownTimer(cooldown_seconds=10.0)

    with pytest.raises(RuntimeError, match="no segment is open"):
        timer.close_segment()


def test_cooldown_time_until_expiration():
    """Test time until expiration calculation."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    # No segment
    assert timer.time_until_expiration(start) is None

    # Active segment
    timer.on_resetting_event(start)
    check_time = start + timedelta(seconds=3)
    remaining = timer.time_until_expiration(check_time)

    assert remaining is not None
    assert 6.9 < remaining < 7.1  # Should be ~7 seconds


def test_cooldown_reset():
    """Test timer reset."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    timer.reset()

    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None
