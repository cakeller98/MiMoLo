"""Adapter to make legacy plugins look like Field-Agents."""

from __future__ import annotations

from datetime import UTC, datetime

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor
from mimolo.core.protocol import HeartbeatMessage, SummaryMessage


class LegacyPluginAdapter:
    """Makes a legacy BaseMonitor plugin behave like a Field-Agent.

    This adapter:
    - Wraps emit_event() and converts to SummaryMessage
    - Generates synthetic heartbeats
    - Provides consistent interface for orchestrator
    """

    def __init__(self, plugin: BaseMonitor, label: str):
        """Initialize adapter.

        Args:
            plugin: Legacy plugin instance
            label: Plugin label
        """
        self.plugin = plugin
        self.label = label
        self.agent_id = f"legacy-{label}"
        self.last_heartbeat = datetime.now(UTC)

    def emit_event(self) -> Event | None:
        """Call wrapped plugin's emit_event."""
        return self.plugin.emit_event()

    def to_summary_message(self, event: Event) -> SummaryMessage:
        """Convert Event to SummaryMessage format.

        Args:
            event: Event from legacy plugin

        Returns:
            SummaryMessage compatible with Field-Agent protocol
        """
        return SummaryMessage(
            timestamp=event.timestamp,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            data=event.data or {},
        )

    def generate_heartbeat(self) -> HeartbeatMessage:
        """Generate synthetic heartbeat for legacy plugin."""
        self.last_heartbeat = datetime.now(UTC)
        return HeartbeatMessage(
            timestamp=self.last_heartbeat,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            metrics={"mode": "legacy", "synthetic": True},
        )
