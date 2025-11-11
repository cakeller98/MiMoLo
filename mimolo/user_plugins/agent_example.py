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

import json
import sys
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from queue import Empty, Queue
from random import randint
from typing import Any


class AgentExample:
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
        self.sample_interval = sample_interval
        self.heartbeat_interval = heartbeat_interval

        # Accumulator for current segment
        self.item_counts: Counter[str] = Counter()
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Command queue for flush/shutdown
        self.command_queue: Queue[dict[str, Any]] = Queue()

        # Flush queue for summarizer
        self.flush_queue: Queue[tuple[datetime, datetime, Counter[str]]] = Queue()

        # Control flags
        self.running = True
        self.shutdown_event = threading.Event()

    def send_message(self, msg: dict[str, Any]) -> None:
        """Write a JSON message to stdout.

        Args:
            msg: Message dictionary to serialize
        """
        try:
            print(json.dumps(msg), flush=True)
        except Exception as e:
            print(json.dumps({"type": "error", "message": f"Failed to send message: {e}"}), file=sys.stderr, flush=True)

    def command_listener(self) -> None:
        """Read commands from stdin (blocking thread)."""
        try:
            while not self.shutdown_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        break

                    line = line.strip()
                    if not line:
                        continue

                    cmd = json.loads(line)
                    self.command_queue.put(cmd)
                except json.JSONDecodeError as e:
                    self.send_message({
                        "type": "error",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": "0.3",
                        "agent_version": "1.0.0",
                        "data": {},
                        "message": f"Invalid JSON command: {e}",
                    })
                except EOFError:
                    break
        except Exception:
            # stdin closed or other error
            pass
        finally:
            # Trigger shutdown when stdin closes
            self.shutdown_event.set()
            self.running = False

    def worker_loop(self) -> None:
        """Generate fake items continuously and accumulate them."""
        last_heartbeat = time.time()

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)

            # Initialize segment start if needed
            with self.data_lock:
                if self.segment_start is None:
                    self.segment_start = now

                # Generate a fake item
                item = f"fake_item_{randint(1, self.item_count)}"
                self.item_counts[item] += 1

            # Send heartbeat if interval elapsed
            if time.time() - last_heartbeat >= self.heartbeat_interval:
                self.send_message({
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": "0.3",
                    "agent_version": "1.0.0",
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "items_accumulated": sum(self.item_counts.values()),
                    },
                })
                last_heartbeat = time.time()

            # Check for commands (non-blocking)
            try:
                cmd = self.command_queue.get_nowait()
                cmd_type = cmd.get("cmd", "").lower()

                if cmd_type == "flush":
                    # Take snapshot and reset accumulator
                    with self.data_lock:
                        snapshot_counts = self.item_counts.copy()
                        snapshot_start = self.segment_start or now
                        snapshot_end = now

                        # Reset for next segment
                        self.item_counts.clear()
                        self.segment_start = now

                    # Queue for summarizer
                    self.flush_queue.put((snapshot_start, snapshot_end, snapshot_counts))

                elif cmd_type == "shutdown":
                    self.running = False
                    self.shutdown_event.set()

            except Empty:
                pass

            # Sleep to avoid busy-wait
            time.sleep(self.sample_interval)

    def summarizer(self) -> None:
        """Package snapshots and emit summaries."""
        while self.running or not self.flush_queue.empty():
            try:
                # Wait for flush data (blocking with timeout)
                start, end, counts = self.flush_queue.get(timeout=1.0)

                # Calculate duration
                duration = (end - start).total_seconds()

                # Format data as list of {item, count}
                items_list: list[dict[str, Any]] = [
                    {"item": item, "count": count}
                    for item, count in sorted(counts.items())
                ]

                # Emit summary
                self.send_message({
                    "type": "summary",
                    "timestamp": end.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": "0.3",
                    "agent_version": "1.0.0",
                    "data": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "length": duration,
                        "items": items_list,
                        "total_events": sum(counts.values()),
                        "unique_items": len(counts),
                    },
                })

            except Empty:
                if not self.running:
                    break

    def run(self) -> None:
        """Main entry point - starts all threads and sends handshake."""
        # Send handshake
        self.send_message({
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": "0.3",
            "agent_version": "1.0.0",
            "min_app_version": "0.3.0",
            "capabilities": ["summary", "heartbeat", "status", "error"],
            "data": {},
        })

        # Start threads
        listener_thread = threading.Thread(target=self.command_listener, daemon=True)
        worker_thread = threading.Thread(target=self.worker_loop, daemon=False)
        summarizer_thread = threading.Thread(target=self.summarizer, daemon=False)

        listener_thread.start()
        worker_thread.start()
        summarizer_thread.start()

        # Wait for shutdown (with timeout to allow Ctrl+C)
        try:
            while worker_thread.is_alive():
                worker_thread.join(timeout=0.5)
            while summarizer_thread.is_alive():
                summarizer_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self.running = False
            self.shutdown_event.set()


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
