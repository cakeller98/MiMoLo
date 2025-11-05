"""Tests for event primitives."""

from datetime import UTC, datetime

import pytest

from mimolo.core.event import Event, EventRef, Segment


def test_event_creation():
    """Test basic event creation."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    )

    assert event.timestamp == now
    assert event.label == "test"
    assert event.event == "test_event"
    assert event.data == {"key": "value"}
    assert event.id is None


def test_event_with_id():
    """Test event ID computation."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    )

    event_with_id = event.with_id()
    assert event_with_id.id is not None
    assert len(event_with_id.id) == 16


def test_event_compute_id_deterministic():
    """Test that event ID computation is deterministic."""
    now = datetime.now(UTC)
    data = {"key": "value"}

    id1 = Event.compute_id(now, "test", "event", data)
    id2 = Event.compute_id(now, "test", "event", data)

    assert id1 == id2


def test_event_validation_empty_label():
    """Test that empty label raises ValueError."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="label cannot be empty"):
        Event(timestamp=now, label="", event="test")


def test_event_validation_empty_event():
    """Test that empty event type raises ValueError."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="Event type cannot be empty"):
        Event(timestamp=now, label="test", event="")


def test_event_validation_naive_timestamp():
    """Test that naive timestamp raises ValueError."""
    now = datetime.now()  # No timezone
    with pytest.raises(ValueError, match="must be timezone-aware"):
        Event(timestamp=now, label="test", event="test")


def test_event_to_dict():
    """Test event to dictionary conversion."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    ).with_id()

    d = event.to_dict()
    assert d["timestamp"] == now.isoformat()
    assert d["label"] == "test"
    assert d["event"] == "test_event"
    assert d["data"] == {"key": "value"}
    assert d["id"] is not None


def test_event_from_dict():
    """Test event from dictionary conversion."""
    now = datetime.now(UTC)
    d = {
        "timestamp": now.isoformat(),
        "label": "test",
        "event": "test_event",
        "data": {"key": "value"},
        "id": "abc123",
    }

    event = Event.from_dict(d)
    assert event.label == "test"
    assert event.event == "test_event"
    assert event.data == {"key": "value"}
    assert event.id == "abc123"


def test_event_ref_from_event():
    """Test EventRef creation from Event."""
    now = datetime.now(UTC)
    event = Event(timestamp=now, label="test", event="test_event")
    ref = EventRef.from_event(event)

    assert ref.timestamp == event.timestamp
    assert ref.label == event.label
    assert ref.event == event.event


def test_event_ref_to_dict():
    """Test EventRef to dictionary conversion."""
    now = datetime.now(UTC)
    ref = EventRef(timestamp=now, label="test", event="test_event")

    d = ref.to_dict()
    assert d["t"] == now.isoformat()
    assert d["l"] == "test"
    assert d["e"] == "test_event"


def test_segment_creation():
    """Test Segment creation."""
    start = datetime.now(UTC)
    end = start
    refs = [EventRef(timestamp=start, label="test", event="test_event")]

    segment = Segment(
        start=start,
        end=end,
        duration_s=0.0,
        events=refs,
        aggregated={"test_header": [1, 2, 3]},
        resets_count=5,
    )

    assert segment.start == start
    assert segment.end == end
    assert segment.duration_s == 0.0
    assert len(segment.events) == 1
    assert segment.aggregated == {"test_header": [1, 2, 3]}
    assert segment.resets_count == 5


def test_segment_to_dict():
    """Test Segment to dictionary conversion."""
    start = datetime.now(UTC)
    end = start
    refs = [EventRef(timestamp=start, label="test", event="test_event")]

    segment = Segment(
        start=start,
        end=end,
        duration_s=10.5,
        events=refs,
        aggregated={"test": [1, 2]},
        resets_count=3,
    )

    d = segment.to_dict()
    assert d["type"] == "segment"
    assert d["start"] == start.isoformat()
    assert d["end"] == end.isoformat()
    assert d["duration_s"] == 10.5
    assert d["labels"] == ["test"]
    assert d["aggregated"] == {"test": [1, 2]}
    assert d["resets_count"] == 3
    assert len(d["events"]) == 1
