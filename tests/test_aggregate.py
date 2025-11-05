"""Tests for segment aggregation."""

from datetime import UTC, datetime

import pytest

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.cooldown import SegmentState
from mimolo.core.errors import AggregationError
from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry


class TestMonitor(BaseMonitor):
    """Test monitor for aggregation tests."""

    spec = PluginSpec(label="test", data_header="items", resets_cooldown=True)

    def emit_event(self):
        return None

    @staticmethod
    def filter_method(items):
        """Deduplicate and sort."""
        return sorted(set(items))


def test_aggregator_initialization():
    """Test aggregator initialization."""
    registry = PluginRegistry()
    aggregator = SegmentAggregator(registry)

    assert aggregator.event_count == 0
    assert not aggregator.has_events


def test_aggregator_add_event():
    """Test adding events to aggregator."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"items": "item1"},
    )

    aggregator.add_event(event)

    assert aggregator.event_count == 1
    assert aggregator.has_events


def test_aggregator_build_segment():
    """Test building segment with aggregation."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    start = datetime.now(UTC)

    # Add events
    for _i, item in enumerate(["item1", "item2", "item1", "item3"]):
        event = Event(
            timestamp=start,
            label="test",
            event="test_event",
            data={"items": item},
        )
        aggregator.add_event(event)

    # Build segment
    segment_state = SegmentState(
        start_time=start,
        last_event_time=start,
        resets_count=3,
    )

    segment = aggregator.build_segment(segment_state)

    assert segment.start == start
    assert len(segment.events) == 4
    assert segment.aggregated["items"] == ["item1", "item2", "item3"]  # Deduplicated and sorted
    assert segment.resets_count == 3


def test_aggregator_clear():
    """Test clearing aggregator buffers."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(timestamp=now, label="test", event="test_event", data={"items": "item1"})
    aggregator.add_event(event)

    assert aggregator.has_events

    aggregator.clear()

    assert not aggregator.has_events
    assert aggregator.event_count == 0


def test_aggregator_filter_error():
    """Test aggregation error handling."""

    class BrokenMonitor(BaseMonitor):
        spec = PluginSpec(label="broken", data_header="items")

        def emit_event(self):
            return None

        @staticmethod
        def filter_method(items):
            raise ValueError("Filter failed!")

    registry = PluginRegistry()
    registry.add(BrokenMonitor.spec, BrokenMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(timestamp=now, label="broken", event="test", data={"items": "item1"})
    aggregator.add_event(event)

    segment_state = SegmentState(start_time=now, last_event_time=now, resets_count=0)

    with pytest.raises(AggregationError, match="Filter failed"):
        aggregator.build_segment(segment_state)
