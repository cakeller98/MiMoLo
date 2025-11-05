"""Cooldown timer and segment state machine.

The cooldown mechanism tracks activity and determines segment boundaries:

States:
- IDLE: No active segment, waiting for first resetting event
- ACTIVE: Segment open, cooldown timer running
- CLOSING: Cooldown expired, segment ready to close

Transitions:
- IDLE + resetting event → ACTIVE (open segment)
- ACTIVE + resetting event → ACTIVE (reset timer, increment resets_count)
- ACTIVE + non-resetting event → ACTIVE (no timer change)
- ACTIVE + cooldown expired → CLOSING
- CLOSING + segment closed → IDLE
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto


class CooldownState(Enum):
    """Cooldown state machine states."""

    IDLE = auto()
    ACTIVE = auto()
    CLOSING = auto()


@dataclass
class SegmentState:
    """Current segment tracking state.

    Attributes:
        start_time: When the segment opened (first event).
        last_event_time: Most recent event timestamp.
        resets_count: Number of times cooldown was reset.
    """

    start_time: datetime
    last_event_time: datetime
    resets_count: int = 0


class CooldownTimer:
    """Manages cooldown state and segment boundaries.

    The timer tracks when events occur and determines when to close segments
    based on a configurable cooldown period.
    """

    def __init__(self, cooldown_seconds: float) -> None:
        """Initialize cooldown timer.

        Args:
            cooldown_seconds: Duration in seconds after last resetting event
                             before segment closes.
        """
        if cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be positive: {cooldown_seconds}")

        self.cooldown_seconds = cooldown_seconds
        self._state = CooldownState.IDLE
        self._segment: SegmentState | None = None

    @property
    def state(self) -> CooldownState:
        """Current cooldown state."""
        return self._state

    @property
    def segment_state(self) -> SegmentState | None:
        """Current segment state (None if IDLE)."""
        return self._segment

    def on_resetting_event(self, timestamp: datetime) -> bool:
        """Process a resetting event (resets cooldown timer).

        Args:
            timestamp: Event timestamp.

        Returns:
            True if a new segment was opened, False if existing segment was reset.
        """
        if self._state == CooldownState.IDLE:
            # Open new segment
            self._segment = SegmentState(
                start_time=timestamp,
                last_event_time=timestamp,
                resets_count=0,
            )
            self._state = CooldownState.ACTIVE
            return True

        elif self._state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            # Reset timer and update tracking
            if self._segment is None:
                raise RuntimeError("Invalid state: ACTIVE/CLOSING without segment")

            self._segment.last_event_time = timestamp
            self._segment.resets_count += 1
            self._state = CooldownState.ACTIVE
            return False

        return False

    def on_non_resetting_event(self, timestamp: datetime) -> None:
        """Process a non-resetting event (does not reset timer).

        Args:
            timestamp: Event timestamp.
        """
        if self._state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            if self._segment is None:
                raise RuntimeError("Invalid state: ACTIVE/CLOSING without segment")

            # Update last event time but don't reset cooldown
            # Note: This doesn't affect the cooldown calculation which is based
            # on the last *resetting* event
            if timestamp > self._segment.last_event_time:
                self._segment.last_event_time = timestamp

    def check_expiration(self, current_time: datetime) -> bool:
        """Check if cooldown has expired.

        Args:
            current_time: Current time to check against.

        Returns:
            True if cooldown expired and segment should close.
        """
        if self._state != CooldownState.ACTIVE:
            return False

        if self._segment is None:
            raise RuntimeError("Invalid state: ACTIVE without segment")

        # Check if enough time has passed since last event
        elapsed = (current_time - self._segment.last_event_time).total_seconds()
        if elapsed >= self.cooldown_seconds:
            self._state = CooldownState.CLOSING
            return True

        return False

    def close_segment(self) -> SegmentState:
        """Close the current segment and return to IDLE.

        Returns:
            The closed segment state.

        Raises:
            RuntimeError: If no segment is open.
        """
        if self._segment is None:
            raise RuntimeError("Cannot close segment: no segment is open")

        segment = self._segment
        self._segment = None
        self._state = CooldownState.IDLE
        return segment

    def reset(self) -> None:
        """Reset timer to IDLE state (for testing/cleanup)."""
        self._state = CooldownState.IDLE
        self._segment = None

    def time_until_expiration(self, current_time: datetime) -> float | None:
        """Calculate seconds remaining until cooldown expires.

        Args:
            current_time: Current time.

        Returns:
            Seconds remaining, or None if not in ACTIVE state.
        """
        if self._state != CooldownState.ACTIVE or self._segment is None:
            return None

        elapsed = (current_time - self._segment.last_event_time).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)
