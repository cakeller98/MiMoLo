#!/usr/bin/env python3
"""Field-Agent Template for MiMoLo v0.3+

This template demonstrates the BaseFieldAgent hook pattern and
Agent JLP-based logging that preserves Rich formatting.

Key sections to modify:
1. Agent metadata (agent_id, agent_label, version)
2. __init__ parameters for your specific monitoring needs
3. _accumulate() - your actual monitoring/sampling logic
4. _take_snapshot() - how you capture a snapshot of accumulated observations
5. _format_summary() - how you package accumulated data

LOGGING APPROACH (v0.3+):
This template uses AgentLogger, which sends structured log packets via the
Agent JLP. These logs are rendered by the orchestrator with full Rich
formatting (colors, styles, markup) on the orchestrator console.

Benefits:
- Logs work in separate terminals and remote agents
- Centralized orchestrator control over verbosity
- Preserves Rich formatting across process boundaries
- Testable (logs are structured Agent JLP packets)

Usage:
    from mimolo.core.agent_logging import AgentLogger

    self.logger = AgentLogger(self.agent_id, self.agent_label)

    # Basic logging
    self.logger.debug("Processing started")
    self.logger.info("[green]✓[/green] Task complete")
    self.logger.warning("[yellow]⚠[/yellow] Cache at 85%")
    self.logger.error("[red]✗[/red] Connection failed")

    # With extra context
    self.logger.info("Batch processed", count=100, duration=1.23)

The template includes debugging helpers to help you understand:
- Message flow (handshake, heartbeat, summary, errors)
- Command reception (flush, shutdown, status)
- Thread coordination and data flow
- Internal state and accumulation

To use:
1. Copy to a new file: cp agent_template.py my_agent.py
2. Update AGENT_LABEL and AGENT_ID
3. Implement your monitoring logic in worker_loop()
4. Configure in mimolo.toml:
   [plugins.my_agent]
   enabled = true
   plugin_type = "field_agent"
   executable = "python"
   args = ["my_agent.py"]
   heartbeat_interval_s = 15.0
   agent_flush_interval_s = 60.0

Architecture:
- Command Listener: Reads stdin for flush/shutdown/status commands
- Worker Loop: Calls _accumulate() to collect data into your accumulator
- Summarizer: Uses _take_snapshot() + _format_summary() to emit summaries
"""

from __future__ import annotations

import json
import sys
import threading

# Standard library imports (alphabetical within group)
from collections import Counter
from datetime import datetime
from typing import Any

import typer

# Third-party imports (alphabetical within group)
from rich.console import Console
from rich.panel import Panel

# Import AgentLogger for Agent JLP-based logging
from mimolo.core.agent_logging import AgentLogger
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

# =============================================================================
# Field-Agent Implementation
# =============================================================================


class FieldAgentTemplate(BaseFieldAgent):
    """Template Field-Agent showing the BaseFieldAgent hook pattern."""

    def __init__(
        self,
        agent_id: str = AGENT_ID,
        agent_label: str = AGENT_LABEL,
        sample_interval: float = 5.0,
        heartbeat_interval: float = 15.0,
        dev_pretty: bool = False,
        # TODO: Add your custom parameters here
        # example_param: str = "default_value",
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique runtime identifier
            agent_label: Logical plugin name
            sample_interval: Seconds between samples in worker loop
            heartbeat_interval: Seconds between heartbeat emissions
            dev_pretty: Pretty-print JSON messages to stderr when True
            # TODO: Document your custom parameters
        """
        self.agent_id = agent_id
        self.agent_label = agent_label
        super().__init__(
            agent_id=agent_id,
            agent_label=agent_label,
            sample_interval=sample_interval,
            heartbeat_interval=heartbeat_interval,
            protocol_version=PROTOCOL_VERSION,
            agent_version=AGENT_VERSION,
            min_app_version=MIN_APP_VERSION,
        )

        # TODO: Store your custom parameters
        # self.example_param = example_param
        self.dev_pretty = dev_pretty

        # Accumulator for current segment (structured observations)
        self.data_accumulator: list[dict[str, Any]] = []
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Agent JLP-based logger (sends log packets to orchestrator)
        self.logger = AgentLogger(
            agent_id=self.agent_id,
            agent_label=self.agent_label,
            protocol_version=PROTOCOL_VERSION,
            agent_version=AGENT_VERSION,
        )

        # Optional: Keep Rich console for complex debug panels (deprecated)
        # New approach: Use logger instead for all debug output
        self.debug = (
            Console(stderr=True, force_terminal=True) if DEBUG_MODE else None
        )

    def _debug_log(self, message: str, style: str = "cyan") -> None:
        """Emit a debug log for development-time visibility."""
        if DEBUG_MODE:
            styled_msg = f"[{style}]{message}[/{style}]"
            self.logger.debug(styled_msg)

    def _debug_json(self, label: str, payload: dict[str, Any]) -> None:
        """Pretty-print a JSON payload for quick inspection."""
        if not DEBUG_MODE:
            return
        pretty = json.dumps(payload, indent=2, sort_keys=True)
        self.logger.debug(f"[magenta]=== {label} ===[/magenta]\n{pretty}")

    def send_message(self, msg: dict[str, Any]) -> None:
        """Send a protocol message, optionally mirrored as pretty JSON on stderr."""
        if self.dev_pretty:
            pretty = json.dumps(msg, indent=2, sort_keys=True)
            print(pretty, file=sys.stderr, flush=True)
        super().send_message(msg)

    def _accumulate(self, now: datetime) -> None:
        """Collect one observation and append it to the in-memory accumulator."""
        if self.segment_start is None:
            self.segment_start = now
            self._debug_log(f"📅 Segment started at {now.isoformat()}", "cyan")

        sample_id = len(self.data_accumulator) + 1
        sample_data: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "sample_id": sample_id,
            "value": f"sample_{sample_id}",
        }
        self.data_accumulator.append(sample_data)
        self._debug_log(
            f"📊 Sample #{sample_id} accumulated (total: {len(self.data_accumulator)})",
            "cyan",
        )

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, list[Any]]:
        """Snapshot the accumulated observations and reset the accumulator.

        Returns:
            (snapshot_start, snapshot_end, snapshot_data)
        """
        snapshot = self.data_accumulator.copy()
        snapshot_start = self.segment_start or now
        snapshot_end = now
        self.data_accumulator.clear()
        self.segment_start = snapshot_end
        self._debug_log(
            f"📸 Snapshot taken: {len(snapshot)} items from {snapshot_start.isoformat()} "
            f"to {snapshot_end.isoformat()}",
            "green",
        )
        return snapshot_start, snapshot_end, snapshot

    def _format_summary(
        self, snapshot: list[dict[str, Any]], start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Aggregate a snapshot of observations into a summary payload."""
        duration = (end - start).total_seconds()

        summary_data: dict[str, Any] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_s": duration,
            "sample_count": len(snapshot),
            "samples": snapshot,
        }

        if snapshot:
            typed_values: list[str] = []
            for raw in snapshot:
                val = raw.get("value")
                if isinstance(val, str):
                    typed_values.append(val)
            if typed_values:
                value_counts: Counter[str] = Counter(typed_values)
                summary_data["value_counts"] = dict(value_counts)

        return summary_data

    def _accumulated_count(self) -> int:
        return len(self.data_accumulator)

    def _heartbeat_metrics(self) -> dict[str, Any]:
        """
        Provide custom heartbeat metrics for monitoring agent health.

        """
        metrics = super()._heartbeat_metrics()
        # Keep base metrics (queue, accumulated_count) and add sample_count.
        metrics["sample_count"] = len(self.data_accumulator)
        return metrics

    def run(self) -> None:
        """Run the agent with optional pre/post hooks around BaseFieldAgent.run()."""
        if self.debug:
            self.debug.print(Panel.fit(
                f"[bold cyan]{self.agent_label}[/bold cyan]\n"
                f"ID: {self.agent_id}\n"
                f"Version: {AGENT_VERSION}\n"
                f"Protocol: {PROTOCOL_VERSION}\n"
                f"Sample Interval: {self.sample_interval}s\n"
                f"Heartbeat Interval: {self.heartbeat_interval}s",
                title="[bold green]🚀 Field-Agent Starting[/bold green]",
                border_style="green"
            ))

        # after our pre-run hook, start the BaseFieldAgent main loop

        super().run()

        # the following runs after clean shutdown of BaseFieldAgent

        if self.debug:
            self.debug.print(Panel.fit(
                "[bold yellow]Agent stopped cleanly[/bold yellow]",
                border_style="yellow"
            ))


def main(
    sample_interval: float = typer.Option(
        5.0, help="Seconds between samples"
    ),
    heartbeat_interval: float = typer.Option(
        15.0, help="Seconds between heartbeats"
    ),
    dev_pretty: bool = typer.Option(
        False, help="Pretty-print JSON messages to stderr"
    ),
) -> None:
    """Entry point using Typer for CLI parsing."""

    agent = FieldAgentTemplate(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        sample_interval=sample_interval,
        heartbeat_interval=heartbeat_interval,
        dev_pretty=dev_pretty,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
