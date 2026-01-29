#!/usr/bin/env python3
"""Example Field-Agent demonstrating the v0.3 protocol.

This agent generates synthetic events with fake items and aggregates them internally.
When flushed, it returns a summary with item counts.

Three-thread architecture:
- Command Listener: reads flush/shutdown commands from stdin
- Worker Loop: generates fake items continuously
- Summarizer: packages accumulated data on flush
"""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime
from random import randint
from typing import Any

# Third-party imports (alphabetical within group)
from rich.console import Console
from rich.panel import Panel

# Local application imports (alphabetical within group)
from mimolo.field_agents.base_agent import BaseFieldAgent

# =============================================================================
# CUSTOMIZE THESE VALUES FOR YOUR AGENT
# =============================================================================

AGENT_LABEL = "template_agent"  # TODO: Change to your agent name
AGENT_ID = "template_agent-001"  # TODO: Change to unique ID
AGENT_VERSION = "1.0.0"  # TODO: Update as you develop
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"

# Debug output (set to False in production)
DEBUG_MODE = True  # Shows rich debugging output to stderr


class AgentExample(BaseFieldAgent):
    """Field-Agent that generates synthetic monitoring events."""

    def __init__(
        self,
        agent_id: str = "agent_example-001",
        agent_label: str = "agent_example",
        item_count: int = 5,
        sample_interval: float = 3.0,
        heartbeat_interval: float = 15.0,
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique runtime identifier
            agent_label: Logical plugin name
            item_count: Number of unique fake items to generate
            sample_interval: Seconds between generating fake items
            heartbeat_interval: Seconds between heartbeat emissions
        """
        self.agent_id = agent_id
        self.agent_label = agent_label
        self.item_count = item_count
        super().__init__(
            agent_id=agent_id,
            agent_label=agent_label,
            sample_interval=sample_interval,
            heartbeat_interval=heartbeat_interval,
            protocol_version="0.3",
            agent_version="1.0.0",
            min_app_version="0.3.0",
        )

        # Accumulator for current segment
        self.item_counts: Counter[str] = Counter()
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Optional: Keep Rich console for complex debug panels (deprecated)
        # New approach: Use logger instead for all debug output
        self.debug = (
            Console(stderr=True, force_terminal=True) if DEBUG_MODE else None
        )

    def _accumulate(self, now: datetime) -> None:
        with self.data_lock:
            if self.segment_start is None:
                self.segment_start = now
            item = f"fake_item_{randint(1, self.item_count)}"
            self.item_counts[item] += 1

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, Counter[str]]:
        with self.data_lock:
            snapshot_counts = self.item_counts.copy()
            snapshot_start = self.segment_start or now
            snapshot_end = now
            self.item_counts.clear()
            self.segment_start = now
        return snapshot_start, snapshot_end, snapshot_counts

    def _format_summary(
        self, snapshot: Counter[str], start: datetime, end: datetime
    ) -> dict[str, Any]:
        duration = (end - start).total_seconds()
        items_list: list[dict[str, Any]] = [
            {"item": item, "count": count}
            for item, count in sorted(snapshot.items())
        ]
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "length": duration,
            "items": items_list,
            "total_events": sum(snapshot.values()),
            "unique_items": len(snapshot),
        }

    def _accumulated_count(self) -> int:
        return sum(self.item_counts.values())

    def run(self) -> None:
        """Main entry point."""
        super().run()

        if self.debug:
            self.debug.print(
                Panel.fit(
                    f"[bold yellow]Agent {self.agent_id} stopped[/bold yellow]",
                    border_style="yellow",
                )
            )

def main() -> None:
    """Entry point."""
    agent = AgentExample(
        agent_id="agent_example-001",
        agent_label="agent_example",
        item_count=5,
        sample_interval=3.0,
        heartbeat_interval=15.0,
    )
    agent.run()


if __name__ == "__main__":
    main()
