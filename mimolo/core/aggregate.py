"""Segment aggregation builder and filter application.

The aggregator collects events during an open segment, groups data by
data_header, and applies plugin-specific filters when the segment closes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mimolo.core.cooldown import SegmentState
from mimolo.core.errors import AggregationError
from mimolo.core.event import Event, EventRef, Segment
from mimolo.core.registry import PluginRegistry


class SegmentAggregator:
    """Builds segments by collecting events and applying aggregation filters.

    The aggregator:
    - Buffers events during an open segment
    - Groups data by plugin data_header
    - Applies each plugin's filter_method on segment close
    - Constructs final Segment objects
    """

    def __init__(self, registry: PluginRegistry) -> None:
        """Initialize aggregator with plugin registry.

        Args:
            registry: Plugin registry for accessing filter methods.
        """
        self._registry = registry
        self._event_refs: list[EventRef] = []
        self._data_buffers: dict[str, list[Any]] = defaultdict(list)

    def add_event(self, event: Event) -> None:
        """Add an event to the current segment.

        Args:
            event: Event to add.
        """
        # Store lightweight event reference
        self._event_refs.append(EventRef.from_event(event))

        # If the plugin has a data_header and event.data contains it, buffer the value
        spec = self._registry.get_spec(event.label)
        if spec and spec.data_header and event.data:
            if spec.data_header in event.data:
                value = event.data[spec.data_header]
                self._data_buffers[spec.data_header].append(value)

    def build_segment(self, segment_state: SegmentState) -> Segment:
        """Build final segment by applying filters and constructing Segment object.

        Args:
            segment_state: State tracking from cooldown timer.

        Returns:
            Constructed Segment with aggregated data.

        Raises:
            AggregationError: If any filter fails.
        """
        # Apply filters to each data_header buffer
        aggregated: dict[str, Any] = {}

        for data_header, items in self._data_buffers.items():
            # Find the plugin that owns this data_header
            plugin_spec = None
            plugin_instance = None

            for spec, instance in self._registry.list_all():
                if spec.data_header == data_header:
                    plugin_spec = spec
                    plugin_instance = instance
                    break

            if plugin_instance is None:
                # No plugin found for this data_header - shouldn't happen
                # but we'll handle it gracefully
                aggregated[data_header] = items
                continue

            # Apply the plugin's filter method
            try:
                filtered = plugin_instance.filter_method(items)
                aggregated[data_header] = filtered
            except Exception as e:
                raise AggregationError(
                    plugin_label=plugin_spec.label
                    if plugin_spec
                    else "unknown",
                    data_header=data_header,
                    original_error=e,
                ) from e

        # Calculate duration
        duration_s = (segment_state.last_event_time - segment_state.start_time).total_seconds()

        # Build segment
        segment = Segment(
            start=segment_state.start_time,
            end=segment_state.last_event_time,
            duration_s=duration_s,
            events=self._event_refs.copy(),
            aggregated=aggregated,
            resets_count=segment_state.resets_count,
        )

        # Clear buffers for next segment
        self.clear()

        return segment

    def clear(self) -> None:
        """Clear all buffered data (for next segment or cleanup)."""
        self._event_refs.clear()
        self._data_buffers.clear()

    @property
    def event_count(self) -> int:
        """Number of events in current segment."""
        return len(self._event_refs)

    @property
    def has_events(self) -> bool:
        """Check if there are any buffered events."""
        return len(self._event_refs) > 0
