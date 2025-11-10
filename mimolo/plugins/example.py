"""Example monitor plugin demonstrating the plugin API.

This plugin emits synthetic events for testing and demonstration purposes.

    For a full development guide, see:
    developer_docs/agent_dev/AGENT_DEV_GUIDE.md

    For the full Field-Agent protocol specification, see:

This example demonstrates:
- Basic event emission
- data_header usage
- Custom filter_method for aggregation
"""

from __future__ import annotations

from datetime import UTC, datetime
from random import randint

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class ExampleMonitor(BaseMonitor):
    """Example monitor that emits synthetic demo events.

    Demonstrates:
    - Basic event emission
    - data_header usage
    - Custom filter_method for aggregation
    """

    spec = PluginSpec(
        label="example",
        data_header="examples",
        resets_cooldown=True,
        infrequent=False,
        poll_interval_s=3.0,
    )

    def __init__(self, item_count: int = 5) -> None:
        """Initialize example monitor.

        Args:
            item_count: Number of unique items to generate.
        """
        self.item_count = item_count

    def emit_event(self) -> Event | None:
        """Emit a synthetic demo event.

        Returns:
            Event with random item from pool.
        """
        now = datetime.now(UTC)
        item = f"fake_item_{randint(1, self.item_count)}"
        payload = {"examples": [item]}

        return Event(
            timestamp=now,
            label=self.spec.label,
            event="demo",
            data=payload,
        )

    @staticmethod
    def filter_method(items: list[list[str]]) -> list[str]:
        """Aggregate example items by flattening and deduplicating.

        Args:
            items: List of lists of example items collected during segment.

        Returns:
            Sorted list of unique items.
        """
        # Flatten nested lists
        flat_items = [item for sublist in items for item in sublist]
        # Deduplicate and sort
        return sorted(set(flat_items))
