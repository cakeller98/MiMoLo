#!/usr/bin/env python3
"""Creo trail file activity agent.

Polls a configured Creo trail directory for trail.txt.# metadata changes and
emits compact summary breadcrumbs. It never reads trail file contents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from mimolo.agents.base_agent import BaseAgent

AGENT_LABEL = "trail_tracker"
AGENT_ID = "trail_tracker-001"
AGENT_VERSION = "0.1.0"
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"

TRAIL_NAME_RE = re.compile(r"^trail\.txt\.(\d+)$")


@dataclass(frozen=True)
class TrailFileState:
    """Stable metadata for one Creo trail file."""

    name: str
    number: int
    modified_at: datetime
    mtime_ns: int
    size_bytes: int


class TrailTrackerAgent(BaseAgent):
    """Lightweight poller for Creo trail file writes."""

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        trail_folder: str,
        poll_interval_s: float,
        heartbeat_interval_s: float,
        active_window_s: float,
        max_trail_age_s: float,
        max_changed_files: int,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_label=agent_label,
            sample_interval=poll_interval_s,
            heartbeat_interval=heartbeat_interval_s,
            protocol_version=PROTOCOL_VERSION,
            agent_version=AGENT_VERSION,
            min_app_version=MIN_APP_VERSION,
        )
        self.trail_folder = Path(trail_folder).expanduser()
        self.active_window_s = active_window_s
        self.max_trail_age_s = max_trail_age_s
        self.max_changed_files = max(1, max_changed_files)

        self._known: dict[str, TrailFileState] = {}
        self._pending_changes: list[dict[str, Any]] = []
        self._first_scan_done = False
        self._trail_folder_available: bool | None = None

        self._session_id: str | None = None
        self._session_started_at: datetime | None = None
        self._last_activity_at: datetime | None = None
        self._latest_file: dict[str, Any] | None = None
        self._pending_session_open = False

        self._changes_seen_total = 0
        self._summaries_sent_total = 0

    def _log_transition(self, level: str, message: str, extra: dict[str, Any]) -> None:
        self.send_message(
            {
                "type": "log",
                "timestamp": datetime.now(UTC).isoformat(),
                "agent_id": self.agent_id,
                "agent_label": self.agent_label,
                "protocol_version": self.protocol_version,
                "agent_version": self.agent_version,
                "level": level,
                "message": message,
                "markup": False,
                "data": {},
                "extra": extra,
            }
        )

    def _scan_trail_files(self, now: datetime) -> list[TrailFileState]:
        if not self.trail_folder.exists() or not self.trail_folder.is_dir():
            if self._trail_folder_available is not False:
                self._log_transition(
                    "warning",
                    f"Trail folder unavailable: {self.trail_folder}",
                    {"trail_folder": str(self.trail_folder)},
                )
            self._trail_folder_available = False
            return []

        if self._trail_folder_available is False:
            self._log_transition(
                "info",
                f"Trail folder restored: {self.trail_folder}",
                {"trail_folder": str(self.trail_folder)},
            )
        self._trail_folder_available = True

        states: list[TrailFileState] = []
        for path in self.trail_folder.glob("trail.txt.*"):
            match = TRAIL_NAME_RE.match(path.name)
            if match is None or not path.is_file():
                continue
            try:
                stat_result = path.stat()
            except OSError:
                continue

            modified_at = datetime.fromtimestamp(stat_result.st_mtime, UTC)
            age_s = max(0.0, (now - modified_at).total_seconds())
            if age_s > self.max_trail_age_s:
                continue

            states.append(
                TrailFileState(
                    name=path.name,
                    number=int(match.group(1)),
                    modified_at=modified_at,
                    mtime_ns=stat_result.st_mtime_ns,
                    size_bytes=stat_result.st_size,
                )
            )

        states.sort(key=lambda item: (item.mtime_ns, item.number), reverse=True)
        return states

    def _change_payload(
        self, current: TrailFileState, previous: TrailFileState | None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": current.name,
            "modified_at": current.modified_at.isoformat(),
            "size_bytes": current.size_bytes,
        }
        if previous is not None:
            payload["size_delta_bytes"] = current.size_bytes - previous.size_bytes
        return payload

    def _ensure_session(self, now: datetime, latest: TrailFileState) -> None:
        last_activity = self._last_activity_at
        if (
            self._session_id is None
            or last_activity is None
            or (now - last_activity).total_seconds() > self.active_window_s
        ):
            self._session_id = f"trail-{now.strftime('%Y%m%dT%H%M%SZ')}-{latest.number}"
            self._session_started_at = now
            self._pending_session_open = True

    def _record_activity(
        self,
        now: datetime,
        current: TrailFileState,
        previous: TrailFileState | None,
    ) -> None:
        self._ensure_session(now, current)
        payload = self._change_payload(current, previous)
        self._pending_changes.append(payload)
        self._pending_changes = self._pending_changes[-self.max_changed_files :]
        self._latest_file = payload
        self._last_activity_at = current.modified_at
        self._changes_seen_total += 1

    def _accumulate(self, now: datetime) -> None:
        """Poll trail metadata and record changes since the previous poll."""
        states = self._scan_trail_files(now)
        current_by_name = {state.name: state for state in states}

        if not self._first_scan_done:
            self._first_scan_done = True
            self._known = current_by_name
            latest = states[0] if states else None
            if latest is not None:
                age_s = max(0.0, (now - latest.modified_at).total_seconds())
                if age_s <= self.active_window_s:
                    self._record_activity(now, latest, None)
            return

        for state in states:
            previous = self._known.get(state.name)
            if previous is None:
                age_s = max(0.0, (now - state.modified_at).total_seconds())
                if age_s <= self.active_window_s:
                    self._record_activity(now, state, None)
                continue
            if previous.mtime_ns != state.mtime_ns or previous.size_bytes != state.size_bytes:
                self._record_activity(now, state, previous)

        self._known = current_by_name

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, dict[str, Any]]:
        """Return one compact evidence snapshot for the current flush."""
        # During shutdown we flush buffered state only; avoid rescanning the
        # trail directory after STOP so ACK(flush) is prompt and deterministic.
        if self.sampling_enabled:
            self._accumulate(now)
        start = self._session_started_at or now
        last_activity = self._last_activity_at
        pending_changes = list(self._pending_changes)
        session_active = (
            last_activity is not None
            and (now - last_activity).total_seconds() <= self.active_window_s
        )

        if pending_changes:
            event = (
                "creo_trail_session_open"
                if self._pending_session_open
                else "creo_trail_activity"
            )
            emit = True
        elif self._session_id is not None and session_active:
            event = "creo_trail_activity_heartbeat"
            emit = True
        elif self._session_id is not None:
            event = "creo_trail_session_close"
            emit = True
        else:
            event = "trail_tracker_idle"
            emit = False

        snapshot: dict[str, Any] = {
            "emit": emit,
            "event": event,
            "session_id": self._session_id,
            "session_started_at": (
                self._session_started_at.isoformat()
                if self._session_started_at is not None
                else None
            ),
            "last_activity_at": (
                last_activity.isoformat() if last_activity is not None else None
            ),
            "latest_file": self._latest_file,
            "changed_files": pending_changes,
            "dead_period_s": self.active_window_s,
        }

        self._pending_changes.clear()
        self._pending_session_open = False
        if event == "creo_trail_session_close":
            self._session_id = None
            self._session_started_at = None
            self._last_activity_at = None
            self._latest_file = None

        return start, now, snapshot

    def _format_summary(
        self, snapshot: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Format the smallest evidence payload needed for trail activity."""
        event = str(snapshot.get("event") or "trail_tracker_idle")
        latest_file = snapshot.get("latest_file")
        changed_files = snapshot.get("changed_files")

        data: dict[str, Any] = {
            "schema": "trail_tracker.summary.v1",
            "event": event,
            "trail_dir": str(self.trail_folder),
        }
        if snapshot.get("session_id") is not None:
            data["session_id"] = snapshot["session_id"]
        if snapshot.get("session_started_at") is not None:
            data["session_started_at"] = snapshot["session_started_at"]
        if snapshot.get("last_activity_at") is not None:
            data["last_activity_at"] = snapshot["last_activity_at"]
        if isinstance(latest_file, dict):
            data["file"] = latest_file
        if isinstance(changed_files, list) and len(changed_files) > 1:
            data["changed_files"] = changed_files
        if event == "creo_trail_session_close":
            data["dead_period_s"] = float(snapshot.get("dead_period_s", self.active_window_s))

        data["activity_signal"] = self._activity_signal(snapshot, start, end)
        return data

    def _activity_signal(
        self, snapshot: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        event = str(snapshot.get("event") or "")
        if event.startswith("creo_trail_activity") or event == "creo_trail_session_open":
            return {
                "mode": "active",
                "keep_alive": True,
                "reason": "Creo trail file activity observed",
            }
        return {
            "mode": "active",
            "keep_alive": False,
            "reason": "No recent Creo trail file activity",
        }

    def _emit_summary(self, start: datetime, end: datetime, snapshot: Any) -> None:
        if isinstance(snapshot, dict) and not bool(snapshot.get("emit")):
            if not self.sampling_enabled:
                snapshot = dict(snapshot)
                snapshot["emit"] = True
            else:
                return
        super()._emit_summary(start, end, snapshot)
        self._summaries_sent_total += 1

    def _accumulated_count(self) -> int:
        return len(self._pending_changes)

    def _heartbeat_metrics(self) -> dict[str, Any]:
        metrics = super()._heartbeat_metrics()
        metrics["trail_folder_available"] = self._trail_folder_available
        metrics["pending_change_count"] = len(self._pending_changes)
        metrics["changes_seen_total"] = self._changes_seen_total
        metrics["summaries_sent_total"] = self._summaries_sent_total
        if self._last_activity_at is None:
            metrics["last_activity_age_s"] = None
        else:
            metrics["last_activity_age_s"] = max(
                0.0, (datetime.now(UTC) - self._last_activity_at).total_seconds()
            )
        metrics["active_session"] = self._session_id is not None
        return metrics


def main(
    trail_folder: str = typer.Option(
        "M:/Library/Standards10/__Startup__/Trails",
        "--trail-folder",
        help="Absolute folder containing Creo trail.txt.# files.",
    ),
    poll_interval_s: float = typer.Option(
        30.0,
        help="Seconds between metadata polls.",
    ),
    heartbeat_interval_s: float = typer.Option(
        15.0,
        help="Seconds between diagnostics heartbeats.",
    ),
    active_window_s: float = typer.Option(
        300.0,
        help="Seconds since last trail modification before observed session close.",
    ),
    max_trail_age_s: float = typer.Option(
        86400.0,
        help="Ignore trail files older than this many seconds while scanning.",
    ),
    max_changed_files: int = typer.Option(
        3,
        help="Maximum changed trail files to retain in a single summary.",
    ),
) -> None:
    """Run the Creo trail tracker agent."""
    resolved = Path(trail_folder).expanduser()
    if not resolved.is_absolute():
        raise typer.BadParameter(f"--trail-folder must be absolute: {trail_folder}")

    agent = TrailTrackerAgent(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        trail_folder=str(resolved),
        poll_interval_s=max(1.0, poll_interval_s),
        heartbeat_interval_s=max(1.0, heartbeat_interval_s),
        active_window_s=max(1.0, active_window_s),
        max_trail_age_s=max(1.0, max_trail_age_s),
        max_changed_files=max(1, max_changed_files),
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
