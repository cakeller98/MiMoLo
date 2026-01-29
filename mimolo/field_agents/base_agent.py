"""Base class for Field-Agent plugins (Python reference implementation)."""

from __future__ import annotations

import json
import sys
import threading
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any


class BaseFieldAgent(ABC):
    """Reference base class for Field-Agent plugins.

    Subclasses implement data accumulation and summary formatting.
    """

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        sample_interval: float,
        heartbeat_interval: float,
        protocol_version: str,
        agent_version: str,
        min_app_version: str,
        capabilities: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.agent_label = agent_label
        self.sample_interval = sample_interval
        self.heartbeat_interval = heartbeat_interval
        self.protocol_version = protocol_version
        self.agent_version = agent_version
        self.min_app_version = min_app_version
        self.capabilities = capabilities or ["summary", "heartbeat", "status", "error"]

        self.command_queue: Queue[dict[str, Any]] = Queue()
        self.flush_queue: Queue[tuple[datetime, datetime, Any]] = Queue()

        self.running = True
        self.shutdown_event = threading.Event()
        self.sampling_enabled = True

    @abstractmethod
    def _accumulate(self, now: datetime) -> None:
        """Collect a sample and update internal accumulator."""

    @abstractmethod
    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, Any]:
        """Return (start, end, snapshot) and reset internal accumulator."""

    @abstractmethod
    def _format_summary(
        self, snapshot: Any, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Return summary payload to embed in `data`."""

    def _accumulated_count(self) -> int:
        """Return count for metrics (override if needed)."""
        return 0

    def _heartbeat_metrics(self) -> dict[str, Any]:
        """Return metrics for heartbeat payload (override if needed)."""
        return {"queue": self.flush_queue.qsize(), "accumulated_count": self._accumulated_count()}

    def send_message(self, msg: dict[str, Any]) -> None:
        """Write a JSON message to stdout."""
        print(json.dumps(msg), flush=True)

    def command_listener(self) -> None:
        """Read commands from stdin (blocking thread)."""
        try:
            while not self.shutdown_event.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                    self.command_queue.put(cmd)
                except json.JSONDecodeError as e:
                    self.send_message({
                        "type": "error",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": self.protocol_version,
                        "agent_version": self.agent_version,
                        "data": {},
                        "message": f"Invalid JSON command: {e}",
                    })
        except Exception:
            pass
        finally:
            self.shutdown_event.set()
            self.running = False

    def worker_loop(self) -> None:
        """Main work loop."""
        last_heartbeat = time.time()
        last_sample = time.time()

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)
            if self.sampling_enabled and (time.time() - last_sample) >= self.sample_interval:
                self._accumulate(now)
                last_sample = time.time()

            if time.time() - last_heartbeat >= self.heartbeat_interval:
                self.send_message({
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": self.protocol_version,
                    "agent_version": self.agent_version,
                    "data": {},
                    "metrics": self._heartbeat_metrics(),
                })
                last_heartbeat = time.time()

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
                    for step in sequence:
                        if step == "flush":
                            self._handle_single_command("flush", now, sync_summary=True)
                        else:
                            self._handle_single_command(step, now)
                else:
                    self._handle_single_command(cmd_type, now)

            time.sleep(0.1)

    def _handle_single_command(
        self, cmd_type: str, now: datetime, sync_summary: bool = False
    ) -> None:
        if cmd_type == "flush":
            start, end, snapshot = self._take_snapshot(now)
            if sync_summary:
                self._emit_summary(start, end, snapshot)
                self._ack_flush(now, snapshot, sync=True)
            else:
                self.flush_queue.put((start, end, snapshot))
                self._ack_flush(now, snapshot, sync=False)
        elif cmd_type == "stop":
            self.sampling_enabled = False
            self._ack_stop(now)
        elif cmd_type == "start":
            self.sampling_enabled = True
        elif cmd_type == "shutdown":
            self.running = False
            self.shutdown_event.set()
        elif cmd_type == "status":
            pass

    def _ack_stop(self, now: datetime) -> None:
        self.send_message({
            "type": "ack",
            "timestamp": now.isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": self.protocol_version,
            "agent_version": self.agent_version,
            "ack_command": "stop",
            "message": "Sampling stopped",
            "data": {},
            "metrics": {"queue": self.flush_queue.qsize(), "accumulated_count": self._accumulated_count()},
        })

    def _ack_flush(self, now: datetime, snapshot: Any, sync: bool) -> None:
        msg = "Flushed (sync)" if sync else "Flushed"
        self.send_message({
            "type": "ack",
            "timestamp": now.isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": self.protocol_version,
            "agent_version": self.agent_version,
            "ack_command": "flush",
            "message": msg,
            "data": {},
            "metrics": {"queue": self.flush_queue.qsize()},
        })

    def _emit_summary(self, start: datetime, end: datetime, snapshot: Any) -> None:
        summary = self._format_summary(snapshot, start, end)
        self.send_message({
            "type": "summary",
            "timestamp": end.isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": self.protocol_version,
            "agent_version": self.agent_version,
            "data": summary,
        })

    def summarizer(self) -> None:
        """Package snapshots and emit summaries."""
        while self.running or not self.flush_queue.empty():
            try:
                start, end, snapshot = self.flush_queue.get(timeout=1.0)
                self._emit_summary(start, end, snapshot)
            except Empty:
                if not self.running:
                    break

    def run(self) -> None:
        """Main entry point."""
        self.send_message({
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": self.protocol_version,
            "agent_version": self.agent_version,
            "min_app_version": self.min_app_version,
            "capabilities": self.capabilities,
            "data": {},
        })

        listener_thread = threading.Thread(target=self.command_listener, daemon=True)
        worker_thread = threading.Thread(target=self.worker_loop, daemon=False)
        summarizer_thread = threading.Thread(target=self.summarizer, daemon=False)

        listener_thread.start()
        worker_thread.start()
        summarizer_thread.start()

        try:
            while worker_thread.is_alive():
                worker_thread.join(timeout=0.5)
            while summarizer_thread.is_alive():
                summarizer_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self.running = False
            self.shutdown_event.set()
