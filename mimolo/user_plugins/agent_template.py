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

# Note: Counter imported for use in template examples (see _format_summary_data)
from collections import Counter  # noqa: F401
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any

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

        # Accumulator for current segment
        self.data_accumulator: list[Any] = []  # TODO: Use appropriate data structure
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Command queue for flush/shutdown/status
        self.command_queue: Queue[dict[str, Any]] = Queue()

        # Flush queue for summarizer
        self.flush_queue: Queue[tuple[datetime, datetime, list[Any]]] = Queue()

        # Control flags
        self.running = True
        self.shutdown_event = threading.Event()

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
        sample_count = 0

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)

            # Initialize segment start if needed
            with self.data_lock:
                if self.segment_start is None:
                    self.segment_start = now
                    self._debug_log(f"📅 Segment started at {now.isoformat()}", "cyan")

                # =============================================================
                # TODO: IMPLEMENT YOUR MONITORING LOGIC HERE
                # =============================================================
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
                    "cyan"
                )
                # =============================================================

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

            # Check for commands (non-blocking)
            try:
                cmd = self.command_queue.get_nowait()
                cmd_type = cmd.get("cmd", "").lower()

                if cmd_type == "flush":
                    self._debug_log("💾 FLUSH command received - taking snapshot", "yellow")

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
                        "green"
                    )

                    # Queue for summarizer
                    self.flush_queue.put((snapshot_start, snapshot_end, snapshot))

                elif cmd_type == "shutdown":
                    self._debug_log("🛑 SHUTDOWN command received", "red")
                    self.running = False
                    self.shutdown_event.set()

                elif cmd_type == "status":
                    self._debug_log("📊 STATUS command received", "yellow")
                    # TODO: Send status message if needed

            except Empty:
                pass

            # Sleep to avoid busy-wait
            time.sleep(self.sample_interval)

        self._debug_log("🛑 Worker thread shutting down", "blue")

    def _format_summary_data(
        self,
        snapshot: list[Any],
        start: datetime,
        end: datetime
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

        # Example: Count occurrences
        # if snapshot:
        #     counter = Counter(item["value"] for item in snapshot)
        #     summary_data["value_counts"] = dict(counter)

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


def main() -> None:
    """Entry point."""
    # TODO: Parse command-line arguments if needed
    # import argparse
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--sample-interval", type=float, default=5.0)
    # args = parser.parse_args()

    agent = FieldAgentTemplate(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        sample_interval=5.0,
        heartbeat_interval=15.0,
        # TODO: Pass your custom parameters
    )
    agent.run()


if __name__ == "__main__":
    main()
