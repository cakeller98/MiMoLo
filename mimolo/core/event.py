"""Event primitives for MiMoLo framework."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """Instantaneous event emitted by a monitor plugin.

    Attributes:
        timestamp: UTC timestamp when the event occurred.
        label: Plugin label that emitted this event (e.g., "folderwatch").
        event: Short event type identifier (e.g., "file_mod").
        data: Optional arbitrary event payload.
        id: Optional deterministic hash for deduplication.
    """

    timestamp: datetime
    label: str
    event: str
    data: dict[str, Any] | None = None
    id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        """Validate event fields after initialization."""
        if not self.label:
            raise ValueError("Event label cannot be empty")
        if not self.event:
            raise ValueError("Event type cannot be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must be timezone-aware (UTC)")

    @staticmethod
    def compute_id(timestamp: datetime, label: str, event: str, data: dict[str, Any] | None) -> str:
        """Compute deterministic hash ID for an event.

        Args:
            timestamp: Event timestamp.
            label: Plugin label.
            event: Event type.
            data: Event data payload.

        Returns:
            Hex digest of SHA256 hash.
        """
        content = {
            "timestamp": timestamp.isoformat(),
            "label": label,
            "event": event,
            "data": data,
        }
        json_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()[:16]

    def with_id(self) -> Event:
        """Return a copy of this event with computed ID.

        Returns:
            New Event instance with id field populated.
        """
        if self.id is not None:
            return self
        computed_id = self.compute_id(self.timestamp, self.label, self.event, self.data)
        # We need to use object.__setattr__ since the dataclass is frozen
        new_event = object.__new__(Event)
        object.__setattr__(new_event, "timestamp", self.timestamp)
        object.__setattr__(new_event, "label", self.label)
        object.__setattr__(new_event, "event", self.event)
        object.__setattr__(new_event, "data", self.data)
        object.__setattr__(new_event, "id", computed_id)
        return new_event

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation.

        Returns:
            Dictionary with all event fields.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "label": self.label,
            "event": self.event,
            "data": self.data,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create Event from dictionary representation.

        Args:
            data: Dictionary with event fields.

        Returns:
            New Event instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        timestamp_str = data.get("timestamp")
        if not timestamp_str:
            raise ValueError("Missing required field: timestamp")

        timestamp = datetime.fromisoformat(timestamp_str)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            timestamp=timestamp,
            label=data["label"],
            event=data["event"],
            data=data.get("data"),
            id=data.get("id"),
        )


@dataclass(frozen=True, slots=True)
class EventRef:
    """Lightweight reference to an event (for segment storage).

    Attributes:
        timestamp: Event timestamp.
        label: Plugin label.
        event: Event type.
    """

    timestamp: datetime
    label: str
    event: str

    @classmethod
    def from_event(cls, event: Event) -> EventRef:
        """Create EventRef from full Event.

        Args:
            event: Full event instance.

        Returns:
            Lightweight event reference.
        """
        return cls(timestamp=event.timestamp, label=event.label, event=event.event)

    def to_dict(self) -> dict[str, Any]:
        """Convert event reference to dictionary.

        Returns:
            Dictionary with timestamp (as 't'), label (as 'l'), event (as 'e').
        """
        return {
            "t": self.timestamp.isoformat(),
            "l": self.label,
            "e": self.event,
        }


@dataclass(slots=True)
class Segment:
    """A time segment containing aggregated events.

    Segments are opened by the first resetting event and closed
    when the cooldown timer expires.

    Attributes:
        start: Segment start timestamp (first event).
        end: Segment end timestamp (last event or last_event + epsilon).
        duration_s: Duration in seconds.
        events: Lightweight event references.
        aggregated: Mapping from data_header to filtered/aggregated result.
        resets_count: Number of cooldown resets during this segment.
    """

    start: datetime
    end: datetime
    duration_s: float
    events: list[EventRef]
    aggregated: dict[str, Any]
    resets_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert segment to dictionary representation.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        # Extract unique labels from events
        labels = sorted({ref.label for ref in self.events})

        return {
            "type": "segment",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_s": self.duration_s,
            "labels": labels,
            "aggregated": self.aggregated,
            "resets_count": self.resets_count,
            "events": [ref.to_dict() for ref in self.events],
        }
