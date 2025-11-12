#!/usr/bin/env python3
"""Field-Agent Template for MiMoLo v0.3+

This template demonstrates the complete 3-thread Field-Agent architecture
with IPC-based logging that preserves Rich formatting.

Key sections to modify:
1. Agent metadata (agent_id, agent_label, version)
2. __init__ parameters for your specific monitoring needs
3. worker_loop() - your actual monitoring/sampling logic
4. _format_summary_data() - how you package accumulated data

LOGGING APPROACH (v0.3+):
This template uses AgentLogger, which sends structured log packets via the
IPC protocol. These logs are rendered by the orchestrator with full Rich
formatting (colors, styles, markup) on the orchestrator console.

Benefits:
- Logs work in separate terminals and remote agents
- Centralized orchestrator control over verbosity
- Preserves Rich formatting across process boundaries
- Testable (logs are structured IPC packets)

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
import sys
import threading
import time

# Standard library imports (alphabetical within group)
from collections import Counter
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any

import typer

# Third-party imports (alphabetical within group)
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# Import AgentLogger for IPC-based logging
from mimolo.core.agent_logging import AgentLogger

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


class FieldAgentTemplate:
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
        self.sample_interval = sample_interval
        self.heartbeat_interval = heartbeat_interval

        # TODO: Store your custom parameters
        # self.example_param = example_param

        # Accumulator for current segment (structured samples)
        self.data_accumulator: list[dict[str, Any]] = []
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Command queue for flush/shutdown/status
        self.command_queue: Queue[dict[str, Any]] = Queue()

        # Flush queue for summarizer
        self.flush_queue: Queue[tuple[datetime, datetime, list[Any]]] = Queue()

        # Control flags
        self.running = True
        self.shutdown_event = threading.Event()
        # Sampling enable/disable (controlled by START/STOP commands)
        self.sampling_enabled = True

        # IPC-based logger (sends log packets to orchestrator)
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
        """Log debug message via IPC logger.

        DEPRECATED: Use self.logger.debug() directly instead.
        Kept for backward compatibility with template examples.
        """
        # Old approach: stderr console
        # if self.debug:
        #     self.debug.print(f"[{style}][DEBUG {self.agent_label}][/{style}] {message}")

        # New approach: IPC log packet
        if DEBUG_MODE:
            styled_msg = f"[{style}]{message}[/{style}]"
            self.logger.debug(styled_msg)

    def _debug_panel(self, content: Any, title: str, style: str = "blue") -> None:
        """Display debug information via IPC logger.

        DEPRECATED: Use self.logger.debug() with Rich markup instead.
        Kept for backward compatibility.

        Note: Complex Rich panels (Syntax highlighting, tables) are converted
        to simplified text for IPC transmission. For full Rich rendering,
        use the deprecated stderr console approach.
        """
        # Old approach: Rich panel to stderr
        # if self.debug:
        #     self.debug.print(Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style))

        # New approach: Simplified IPC log
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
        """Write a JSON message to stdout.

        Args:
            msg: Message dictionary to serialize
        """
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
            print(json.dumps(error_msg), file=sys.stderr, flush=True)

    def command_listener(self) -> None:
        """Read commands from stdin (blocking thread)."""
        self._debug_log("🎧 Command listener thread started", "magenta")

        try:
            while not self.shutdown_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        self._debug_log("📭 stdin closed (EOF)", "yellow")
                        break

                    line = line.strip()
                    if not line:
                        continue

                    cmd = json.loads(line)
                    cmd_type = cmd.get("cmd", "unknown")

                    # Debug: show received command
                    if self.debug:
                        syntax = Syntax(json.dumps(cmd, indent=2), "json", theme="monokai")
                        self._debug_panel(syntax, f"📥 Received command: {cmd_type}", "yellow")

                    self.command_queue.put(cmd)

                except json.JSONDecodeError as e:
                    self._debug_log(f"❌ Invalid JSON: {e}", "red")
                    self.send_message({
                        "type": "error",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": PROTOCOL_VERSION,
                        "agent_version": AGENT_VERSION,
                        "data": {},
                        "message": f"Invalid JSON command: {e}",
                    })
                except EOFError:
                    self._debug_log("📭 stdin EOF", "yellow")
                    break
        except Exception as e:
            self._debug_log(f"❌ Command listener error: {e}", "red")
        finally:
            self._debug_log("🛑 Command listener shutting down", "magenta")
            self.shutdown_event.set()
            self.running = False

    def worker_loop(self) -> None:
        """Main work loop: sample/monitor continuously and accumulate data."""
        self._debug_log("⚙️  Worker thread started", "blue")

        last_heartbeat = time.time()
        last_sample = time.time()
        sample_count = 0

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)

            # Only sample when enabled AND interval elapsed
            if (
                self.sampling_enabled
                and (time.time() - last_sample) >= self.sample_interval
            ):
                # Initialize segment start if needed and perform sampling
                with self.data_lock:
                    if self.segment_start is None:
                        self.segment_start = now
                        self._debug_log(
                            f"📅 Segment started at {now.isoformat()}", "cyan"
                        )

                    # =========================================================
                    # TODO: IMPLEMENT YOUR MONITORING LOGIC HERE
                    # =========================================================
                    # Example: Sample something and accumulate
                    sample_count += 1
                    sample_data: dict[str, Any] = {
                        "timestamp": now.isoformat(),
                        "sample_id": sample_count,
                        "value": f"sample_{sample_count}",
                        # TODO: Add your actual sampled data
                    }
                    self.data_accumulator.append(sample_data)

                    self._debug_log(
                        f"📊 Sample #{sample_count} accumulated (total: {len(self.data_accumulator)})",
                        "cyan",
                    )
                    # =========================================================

                last_sample = time.time()
            else:
                # Optional: minimal debug signal while paused
                if not self.sampling_enabled:
                    self._debug_log(
                        "⏸️  Sampling paused (STOP active)", "yellow"
                    )

            # Send heartbeat if interval elapsed
            if time.time() - last_heartbeat >= self.heartbeat_interval:
                with self.data_lock:
                    accumulated_count = len(self.data_accumulator)

                self.send_message({
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "accumulated_count": accumulated_count,
                        "sample_count": sample_count,
                    },
                })
                last_heartbeat = time.time()

            # Drain and handle all pending commands (non-blocking)
            while True:
                try:
                    cmd = self.command_queue.get_nowait()
                except Empty:
                    break

                cmd_type = cmd.get("cmd", "").lower()

                if cmd_type == "sequence":
                    sequence_raw = cmd.get("sequence", [])
                    sequence: list[str] = [
                        s.lower() if isinstance(s, str) else str(s).lower()
                        for s in sequence_raw
                    ]
                    self._debug_log(
                        f"🔗 SEQUENCE command received: {sequence}", "magenta"
                    )

                    # Expected order: stop -> flush -> shutdown (others ignored)
                    # 1. STOP (pause sampling, send ACK inline)
                    if "stop" in sequence:
                        self._handle_single_command("stop", now, sample_count)

                    # 2. FLUSH (synchronous: build & emit summary BEFORE ACK)
                    if "flush" in sequence:
                        with self.data_lock:
                            snapshot = self.data_accumulator.copy()
                            snapshot_start = self.segment_start or now
                            snapshot_end = datetime.now(UTC)
                            self.data_accumulator.clear()
                            self.segment_start = snapshot_end
                        self._debug_log(
                            f"📸 (SEQ) Snapshot: {len(snapshot)} items from {snapshot_start.isoformat()} to {snapshot_end.isoformat()}",
                            "green",
                        )
                        summary_data = self._format_summary_data(
                            snapshot, snapshot_start, snapshot_end
                        )
                        # Emit summary first
                        self.send_message(
                            {
                                "type": "summary",
                                "timestamp": snapshot_end.isoformat(),
                                "agent_id": self.agent_id,
                                "agent_label": self.agent_label,
                                "protocol_version": PROTOCOL_VERSION,
                                "agent_version": AGENT_VERSION,
                                "data": summary_data,
                            }
                        )
                        # Then ACK(flush)
                        self.send_message(
                            {
                                "type": "ack",
                                "timestamp": snapshot_end.isoformat(),
                                "agent_id": self.agent_id,
                                "agent_label": self.agent_label,
                                "protocol_version": PROTOCOL_VERSION,
                                "agent_version": AGENT_VERSION,
                                "ack_command": "flush",
                                "message": f"Flushed {len(snapshot)} samples (sync)",
                                "data": {},
                                "metrics": {
                                    "flushed_count": len(snapshot),
                                    "queue": self.flush_queue.qsize(),
                                },
                            }
                        )

                    # 3. SHUTDOWN (after summary already emitted)
                    if "shutdown" in sequence:
                        self._handle_single_command(
                            "shutdown", datetime.now(UTC), sample_count
                        )
                else:
                    # Handle single command
                    self._handle_single_command(cmd_type, now, sample_count)

            # Sleep briefly to avoid busy-wait but allow responsive command handling
            # Use shorter interval (100ms) instead of full sample_interval for faster
            # response to STOP/FLUSH/SHUTDOWN commands
            time.sleep(0.1)

        self._debug_log("🛑 Worker thread shutting down", "blue")

    def _handle_single_command(
        self, cmd_type: str, now: datetime, sample_count: int
    ) -> None:
        """Handle a single command from orchestrator.

        Args:
            cmd_type: Command type string (lowercase)
            now: Current timestamp
            sample_count: Current sample count
        """
        if cmd_type == "flush":
            self._debug_log(
                "💾 FLUSH command received - taking snapshot", "yellow"
            )

            # Take snapshot and reset accumulator
            with self.data_lock:
                snapshot = self.data_accumulator.copy()
                snapshot_start = self.segment_start or now
                snapshot_end = now

                # Reset for next segment
                self.data_accumulator.clear()
                self.segment_start = now

            self._debug_log(
                f"📸 Snapshot taken: {len(snapshot)} items from {snapshot_start.isoformat()} "
                f"to {snapshot_end.isoformat()}",
                "green",
            )

            # Queue for summarizer
            self.flush_queue.put((snapshot_start, snapshot_end, snapshot))

            # Send ACK for flush
            with self.data_lock:
                accumulated_count = len(self.data_accumulator)
            self.send_message(
                {
                    "type": "ack",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "ack_command": "flush",
                    "message": f"Flushed {len(snapshot)} samples",
                    "data": {},
                    "metrics": {
                        "flushed_count": len(snapshot),
                        "queue": self.flush_queue.qsize(),
                    },
                }
            )

        elif cmd_type == "shutdown":
            self._debug_log("🛑 SHUTDOWN command received", "red")

            # Wait briefly for any pending summaries to be sent
            # (especially important when SHUTDOWN follows FLUSH in a SEQUENCE)
            if not self.flush_queue.empty():
                self._debug_log(
                    f"⏳ Waiting for {self.flush_queue.qsize()} pending summaries...",
                    "yellow",
                )
                # Give summarizer up to 500ms to drain queue
                deadline = time.time() + 0.5
                while not self.flush_queue.empty() and time.time() < deadline:
                    time.sleep(0.01)

            self.running = False
            self.shutdown_event.set()

        elif cmd_type == "status":
            self._debug_log("📊 STATUS command received", "yellow")
            # TODO: Send status message if needed

        elif cmd_type == "stop":
            # Pause sampling without stopping threads
            self._debug_log(
                "⏸️  STOP command received - pausing sampling",
                "magenta",
            )
            self.sampling_enabled = False

            # Send ACK for stop
            with self.data_lock:
                accumulated_count = len(self.data_accumulator)
            self.send_message(
                {
                    "type": "ack",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "ack_command": "stop",
                    "message": "Sampling stopped",
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "accumulated_count": accumulated_count,
                        "sample_count": sample_count,
                    },
                }
            )

        elif cmd_type == "start":
            # Resume sampling
            self._debug_log(
                "▶️  START command received - resuming sampling",
                "magenta",
            )
            self.sampling_enabled = True
            # Initialize segment start on resume if needed
            if self.segment_start is None:
                self.segment_start = now

            # Send ACK for start
            with self.data_lock:
                accumulated_count = len(self.data_accumulator)
            self.send_message(
                {
                    "type": "ack",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "ack_command": "start",
                    "message": "Sampling resumed",
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "accumulated_count": accumulated_count,
                        "sample_count": sample_count,
                    },
                }
            )

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

    def summarizer(self) -> None:
        """Package snapshots and emit summaries."""
        self._debug_log("📦 Summarizer thread started", "green")

        while self.running or not self.flush_queue.empty():
            try:
                # Wait for flush data (blocking with timeout)
                start, end, snapshot = self.flush_queue.get(timeout=1.0)

                self._debug_log(
                    f"🔄 Summarizing {len(snapshot)} items...",
                    "yellow"
                )

                # Format summary data
                summary_data = self._format_summary_data(snapshot, start, end)

                # Emit summary
                self.send_message({
                    "type": "summary",
                    "timestamp": end.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "data": summary_data,
                })

            except Empty:
                if not self.running:
                    break

        self._debug_log("🛑 Summarizer thread shutting down", "green")

    def run(self) -> None:
        """Main entry point - starts all threads and sends handshake."""
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

        # Send handshake
        self.send_message({
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": PROTOCOL_VERSION,
            "agent_version": AGENT_VERSION,
            "min_app_version": MIN_APP_VERSION,
            "capabilities": ["summary", "heartbeat", "status", "error"],
            "data": {},
        })

        # Start threads
        listener_thread = threading.Thread(target=self.command_listener, daemon=True, name="CommandListener")
        worker_thread = threading.Thread(target=self.worker_loop, daemon=False, name="Worker")
        summarizer_thread = threading.Thread(target=self.summarizer, daemon=False, name="Summarizer")

        listener_thread.start()
        worker_thread.start()
        summarizer_thread.start()

        self._debug_log("🎯 All threads started", "green")

        # Wait for shutdown (with timeout to allow Ctrl+C)
        try:
            while worker_thread.is_alive():
                worker_thread.join(timeout=0.5)
            while summarizer_thread.is_alive():
                summarizer_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self._debug_log("⚠️  KeyboardInterrupt - shutting down", "yellow")
            self.running = False
            self.shutdown_event.set()

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
