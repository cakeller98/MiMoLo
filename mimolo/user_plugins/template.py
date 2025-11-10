"""Template for creating new MiMoLo plugins.

Copy this file, rename it, and fill in your monitoring logic.
See developer_docs/agent_dev/AGENT_DEV_GUIDE.md for detailed instructions.
"""

from __future__ import annotations

from typing import Any

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class TemplateMonitor(BaseMonitor):
    """TODO: Brief description of what this plugin monitors."""

    spec = PluginSpec(
        label="template",              # TODO: Change to unique identifier
        data_header=None,              # TODO: Set to key name for aggregation, or leave None
        resets_cooldown=True,          # TODO: False if events shouldn't reset segment timer
        infrequent=False,              # TODO: True to bypass aggregation and write immediately
        poll_interval_s=5.0,           # TODO: Adjust polling frequency
    )

    def __init__(self) -> None:
        """Initialize the monitor.

        TODO: Add any parameters you need from config.
        Example: def __init__(self, paths: list[str]) -> None:
        """
        pass  # TODO: Initialize any state here

    def emit_event(self) -> Event | None:
        """Check for events and emit if detected.

        Returns:
            Event if something detected, None otherwise.
        """
        # TODO: Add your detection logic here
        # Example:
        # if self._something_changed():
        #     return Event(
        #         timestamp=datetime.now(UTC),
        #         label=self.spec.label,
        #         event="event_type",
        #         data={"items": ["detected_value"]} if self.spec.data_header else None,
        #     )

    @staticmethod
    def filter_method(items: list[Any]) -> list[Any]:
        """Aggregate collected data when segment closes.

        Only called if data_header is set in spec.
        Default implementation returns items unchanged.

        Args:
            items: List of values collected during segment.

        Returns:
            Aggregated result (must be JSON-serializable).
        """
        # TODO: Add custom aggregation logic
        # Examples:
        # - Deduplicate: return list(set(items))
        # - Sort: return sorted(items)
        # - Count: return {"count": len(items), "items": items}

        # Return a copy to avoid "unchanged" linting warnings
        return list(items)
