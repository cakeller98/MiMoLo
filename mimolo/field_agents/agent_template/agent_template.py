#!/usr/bin/env python3
"""Field-Agent Template for MiMoLo v0.3+

This template demonstrates the complete 3-thread Field-Agent architecture
with Agent JLP-based logging that preserves Rich formatting.

Key sections to modify:
1. Agent metadata (agent_id, agent_label, version)
2. __init__ parameters for your specific monitoring needs
3. worker_loop() - your actual monitoring/sampling logic
4. _format_summary_data() - how you package accumulated data

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
- Worker Loop: Samples/monitors continuously, accumulates data
- Summarizer: Packages snapshots and emits summaries on flush
"""

from __future__ import annotations

import json
import threading
import time

# Standard library imports (alphabetical within group)
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import typer

# Third-party imports (alphabetical within group)
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

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
    """Template Field-Agent with full 3-thread architecture and debugging."""

    def __init__(
        self,
        agent_id: str = AGENT_ID,
        agent_label: str = AGENT_LABEL,
        sample_interval: float = 5.0,
        heartbeat_interval: float = 15.0,
        # TODO: Add your custom parameters here
        # example_param: str = "default_value",
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique runtime identifier
            agent_label: Logical plugin name
            sample_interval: Seconds between samples in worker loop
            heartbeat_interval: Seconds between heartbeat emissions
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

        # Accumulator for current segment (structured samples)
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
        self.debug = Console(stderr=True, force_terminal=True) if DEBUG_MODE else None

    def _debug_log(self, message: str, style: str = "cyan") -> None:
        """Log debug message via Agent JLP logger.

        DEPRECATED: Use self.logger.debug() directly instead.
        Kept for backward compatibility with template examples.
        """
        # Old approach: stderr console
        # if self.debug:
        #     self.debug.print(f"[{style}][DEBUG {self.agent_label}][/{style}] {message}")

        # New approach: Agent JLP log packet
        if DEBUG_MODE:
            styled_msg = f"[{style}]{message}[/{style}]"
            self.logger.debug(styled_msg)

    def _debug_panel(self, content: Any, title: str, style: str = "blue") -> None:
        """Display debug information via Agent JLP logger.

        DEPRECATED: Use self.logger.debug() with Rich markup instead.
        Kept for backward compatibility.

        Note: Complex Rich panels (Syntax highlighting, tables) are converted
        to simplified text for Agent JLP transmission. For full Rich rendering,
        use the deprecated stderr console approach.
        """
        # Old approach: Rich panel to stderr
        # if self.debug:
        #     self.debug.print(Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style))

        # New approach: Simplified Agent JLP log
        if DEBUG_MODE:
            # Convert content to string representation
            if isinstance(content, Syntax):
                # For Syntax objects, just log the code
                content_str = str(content.code) if hasattr(content, 'code') else str(content)
            else:
                content_str = str(content)

            # Log as debug message with title (avoid special Unicode that might cause issues)
            msg = f"[{style}]=== {title} ===[/{style}]\n{content_str}"
            self.logger.debug(msg)

    def send_message(self, msg: dict[str, Any]) -> None:
        """Write a JSON message to stdout."""
        try:
            json_str = json.dumps(msg)
            print(json_str, flush=True)

            # Debug output
            if self.debug:
                msg_type = msg.get("type", "unknown")
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                self._debug_panel(syntax, f"📤 Sent: {msg_type}", "green")

        except Exception as e:
            error_msg = {"type": "error", "message": f"Failed to send message: {e}"}
            print(json.dumps(error_msg), flush=True)

    def _format_summary_data(
        self,
        snapshot: list[dict[str, Any]],
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        """Format accumulated data into summary payload.

        TODO: Customize this to aggregate/summarize your data appropriately.

        Args:
            snapshot: Copy of accumulated data from segment
            start: Segment start time
            end: Segment end time

        Returns:
            Dictionary to include in summary message data field
        """
        duration = (end - start).total_seconds()

        # =================================================================
        # TODO: IMPLEMENT YOUR SUMMARIZATION LOGIC HERE
        # =================================================================
        # Example: Just pass through the raw samples
        summary_data: dict[str, Any] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_s": duration,
            "sample_count": len(snapshot),
            "samples": snapshot,  # TODO: Aggregate/summarize instead of raw dump
        }
        # Example aggregation actually applied so Counter import is used
        if snapshot:
            # Count string values only for deterministic typing
            typed_values: list[str] = []
            for raw in snapshot:
                # raw is dict[str, Any] by type declaration
                val = raw.get("value")
                if isinstance(val, str):
                    typed_values.append(val)
            if typed_values:
                value_counts: Counter[str] = Counter(typed_values)
                summary_data["value_counts"] = dict(value_counts)

        return summary_data
        # =================================================================

    def _accumulate(self, now: datetime) -> None:
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
        return self._format_summary_data(snapshot, start, end)

    def _accumulated_count(self) -> int:
        return len(self.data_accumulator)

    def _heartbeat_metrics(self) -> dict[str, Any]:
        return {
            "queue": self.flush_queue.qsize(),
            "accumulated_count": len(self.data_accumulator),
            "sample_count": len(self.data_accumulator),
        }

    def run(self) -> None:
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

        super().run()

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
) -> None:
    """Entry point using Typer for CLI parsing."""

    agent = FieldAgentTemplate(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        sample_interval=sample_interval,
        heartbeat_interval=heartbeat_interval,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
