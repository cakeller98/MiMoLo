#!/usr/bin/env python3
"""Client folder activity agent.

Polls configured folders and emits lightweight summary metadata on flush.
"""

from __future__ import annotations

import fnmatch
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from mimolo.agents.base_agent import BaseAgent

AGENT_LABEL = "client_folder_activity"
AGENT_ID = "client_folder_activity-001"
AGENT_VERSION = "0.1.0"
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"


class ClientFolderActivityAgent(BaseAgent):
    """Folder polling agent that emits bounded activity summaries."""

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        client_id: str,
        client_name: str,
        watch_paths: list[str],
        include_globs: list[str],
        exclude_globs: list[str],
        follow_symlinks: bool,
        coalesce_window_s: float,
        sample_interval: float,
        heartbeat_interval: float,
        emit_path_samples_limit: int,
    ) -> None:
        super().__init__(
            agent_id=agent_id,
            agent_label=agent_label,
            sample_interval=sample_interval,
            heartbeat_interval=heartbeat_interval,
            protocol_version=PROTOCOL_VERSION,
            agent_version=AGENT_VERSION,
            min_app_version=MIN_APP_VERSION,
        )
        self.client_id = client_id
        self.client_name = client_name
        self.watch_paths = [Path(p).expanduser() for p in watch_paths]
        self.include_globs = include_globs
        self.exclude_globs = exclude_globs
        self.follow_symlinks = follow_symlinks
        self.coalesce_window_s = coalesce_window_s
        self.emit_path_samples_limit = max(1, emit_path_samples_limit)

        self._segment_start: datetime | None = None
        self._last_snapshot: dict[str, tuple[int, int]] = {}
        self._counts: Counter[str] = Counter()
        self._top_extensions: Counter[str] = Counter()
        self._path_samples: list[str] = []
        self._dropped_events = 0
        self._events_seen_total = 0
        self._last_event_ts: datetime | None = None
        self._degraded_paths: set[str] = set()
        self._degraded_emitted = False

    def _path_included(self, root: Path, file_path: Path) -> bool:
        try:
            rel_path = file_path.relative_to(root).as_posix()
        except ValueError:
            rel_path = file_path.name
        include_ok = any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.include_globs)
        if not include_ok:
            return False
        excluded = any(fnmatch.fnmatch(rel_path, pattern) for pattern in self.exclude_globs)
        return not excluded

    def _scan_filesystem(self) -> tuple[dict[str, tuple[int, int]], set[str]]:
        snapshot: dict[str, tuple[int, int]] = {}
        degraded_paths: set[str] = set()

        for root in self.watch_paths:
            if not root.exists() or not root.is_dir():
                degraded_paths.add(str(root))
                continue

            try:
                walker = os.walk(root, followlinks=self.follow_symlinks)
                for dirpath, _dirnames, filenames in walker:
                    dir_root = Path(dirpath)
                    for name in filenames:
                        file_path = dir_root / name
                        if not self._path_included(root, file_path):
                            continue
                        try:
                            stat_result = file_path.stat()
                        except OSError:
                            # External I/O races are expected while files are changing.
                            continue
                        snapshot[str(file_path)] = (stat_result.st_mtime_ns, stat_result.st_size)
            except OSError:
                # External filesystem failures should mark this root degraded, not crash agent.
                degraded_paths.add(str(root))

        return snapshot, degraded_paths

    def _to_sample_path(self, path_text: str) -> str:
        file_path = Path(path_text)
        for root in self.watch_paths:
            try:
                return file_path.relative_to(root).as_posix()
            except ValueError:
                continue
        return file_path.as_posix()

    def _record_sample_path(self, path_text: str) -> None:
        if len(self._path_samples) < self.emit_path_samples_limit:
            self._path_samples.append(self._to_sample_path(path_text))
        else:
            self._dropped_events += 1

    def _emit_health_transition(self, now: datetime, degraded_paths: set[str]) -> None:
        if degraded_paths:
            if not self._degraded_emitted or degraded_paths != self._degraded_paths:
                self.send_message(
                    {
                        "type": "status",
                        "timestamp": now.isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": self.protocol_version,
                        "agent_version": self.agent_version,
                        "health": "degraded",
                        "message": "One or more watch paths are unavailable.",
                        "data": {
                            "degraded_paths": sorted(degraded_paths),
                            "degraded_path_count": len(degraded_paths),
                        },
                    }
                )
            self._degraded_emitted = True
            self._degraded_paths = set(degraded_paths)
            return

        if self._degraded_emitted:
            self.send_message(
                {
                    "type": "status",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": self.protocol_version,
                    "agent_version": self.agent_version,
                    "health": "ok",
                    "message": "Watch paths recovered.",
                    "data": {},
                }
            )
        self._degraded_emitted = False
        self._degraded_paths = set()

    def _accumulate(self, now: datetime) -> None:
        if self._segment_start is None:
            self._segment_start = now

        current_snapshot, degraded_paths = self._scan_filesystem()
        self._emit_health_transition(now, degraded_paths)

        current_keys = set(current_snapshot.keys())
        previous_keys = set(self._last_snapshot.keys())

        created = current_keys - previous_keys
        deleted = previous_keys - current_keys
        modified = {
            path
            for path in current_keys & previous_keys
            if current_snapshot[path] != self._last_snapshot[path]
        }

        event_total = len(created) + len(modified) + len(deleted)
        if event_total > 0:
            self._last_event_ts = now
            self._events_seen_total += event_total
            self._counts["created"] += len(created)
            self._counts["modified"] += len(modified)
            self._counts["deleted"] += len(deleted)
            self._counts["renamed"] += 0
            self._counts["total"] += event_total

            for path in sorted(created | modified | deleted):
                ext = Path(path).suffix.lower() or "[no_ext]"
                self._top_extensions[ext] += 1
                self._record_sample_path(path)

        self._last_snapshot = current_snapshot

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, dict[str, Any]]:
        start = self._segment_start or now
        end = now
        snapshot: dict[str, Any] = {
            "counts": dict(self._counts),
            "top_extensions": dict(self._top_extensions),
            "path_samples": list(self._path_samples),
            "dropped_events": self._dropped_events,
            "degraded_paths": sorted(self._degraded_paths),
        }
        self._counts.clear()
        self._top_extensions.clear()
        self._path_samples.clear()
        self._dropped_events = 0
        self._segment_start = now
        return start, end, snapshot

    def _format_summary(
        self, snapshot: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        counts = snapshot.get("counts", {})
        top_ext = snapshot.get("top_extensions", {})
        items = sorted(top_ext.items(), key=lambda pair: pair[1], reverse=True)
        return {
            "schema": "client_folder_activity.summary.v1",
            "client_id": self.client_id,
            "client_name": self.client_name,
            "watch_paths": [str(p) for p in self.watch_paths],
            "window": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "duration_s": (end - start).total_seconds(),
            },
            "counts": {
                "created": int(counts.get("created", 0)),
                "modified": int(counts.get("modified", 0)),
                "deleted": int(counts.get("deleted", 0)),
                "renamed": int(counts.get("renamed", 0)),
                "total": int(counts.get("total", 0)),
            },
            "top_extensions": [{"ext": ext, "count": int(count)} for ext, count in items[:10]],
            "path_samples": list(snapshot.get("path_samples", [])),
            "dropped_events": int(snapshot.get("dropped_events", 0)),
        }

    def _accumulated_count(self) -> int:
        return int(self._counts.get("total", 0))

    def _heartbeat_metrics(self) -> dict[str, Any]:
        metrics = super()._heartbeat_metrics()
        metrics["events_seen_total"] = self._events_seen_total
        metrics["events_buffered"] = int(self._counts.get("total", 0))
        if self._last_event_ts is None:
            metrics["last_event_age_s"] = None
        else:
            metrics["last_event_age_s"] = max(
                0.0, (datetime.now(UTC) - self._last_event_ts).total_seconds()
            )
        metrics["watch_path_count"] = len(self.watch_paths)
        metrics["degraded_path_count"] = len(self._degraded_paths)
        return metrics


def main(
    client_id: str = typer.Option("default-client", help="Client identifier for attribution."),
    client_name: str = typer.Option("Default Client", help="Client display name."),
    watch_paths: str = typer.Option(
        ".",
        "--watch-paths",
        help="Comma-separated folder paths to monitor.",
    ),
    include_globs: str = typer.Option(
        "**/*",
        "--include-globs",
        help="Comma-separated include glob patterns.",
    ),
    exclude_globs: str = typer.Option(
        "**/__pycache__/**,**/.mypy_cache/**,**/.git/**,**/*.tmp,**/*.swp",
        "--exclude-globs",
        help="Comma-separated exclude glob patterns.",
    ),
    follow_symlinks: bool = typer.Option(
        False,
        "--follow-symlinks/--no-follow-symlinks",
        help="Follow directory symlinks while walking paths.",
    ),
    coalesce_window_s: float = typer.Option(
        2.0,
        help="Burst coalescing window in seconds.",
    ),
    poll_interval_s: float = typer.Option(
        2.0,
        help="Polling interval in seconds.",
    ),
    heartbeat_interval_s: float = typer.Option(
        15.0,
        help="Heartbeat interval in seconds.",
    ),
    emit_path_samples_limit: int = typer.Option(
        50,
        help="Maximum path samples emitted in each summary.",
    ),
) -> None:
    """Run the client folder activity agent."""
    resolved_watch_paths = [part.strip() for part in watch_paths.split(",") if part.strip()]
    if not resolved_watch_paths:
        resolved_watch_paths = ["."]
    resolved_include_globs = [part.strip() for part in include_globs.split(",") if part.strip()]
    if not resolved_include_globs:
        resolved_include_globs = ["**/*"]
    resolved_exclude_globs = [part.strip() for part in exclude_globs.split(",") if part.strip()]
    if not resolved_exclude_globs:
        resolved_exclude_globs = ["**/__pycache__/**", "**/.mypy_cache/**", "**/.git/**"]

    agent = ClientFolderActivityAgent(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        client_id=client_id,
        client_name=client_name,
        watch_paths=resolved_watch_paths,
        include_globs=resolved_include_globs,
        exclude_globs=resolved_exclude_globs,
        follow_symlinks=follow_symlinks,
        coalesce_window_s=coalesce_window_s,
        sample_interval=max(0.25, poll_interval_s),
        heartbeat_interval=max(1.0, heartbeat_interval_s),
        emit_path_samples_limit=emit_path_samples_limit,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
