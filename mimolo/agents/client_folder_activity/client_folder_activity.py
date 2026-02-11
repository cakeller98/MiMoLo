#!/usr/bin/env python3
"""Client folder activity agent.

Monitors configured folders and emits lightweight summary metadata on flush.
"""

from __future__ import annotations

import fnmatch
import importlib.util
import os
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from mimolo.agents.base_agent import BaseAgent

AGENT_LABEL = "client_folder_activity"
AGENT_ID = "client_folder_activity-001"
AGENT_VERSION = "0.2.0"
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"
WATCHFILES_AVAILABLE = importlib.util.find_spec("watchfiles") is not None
if WATCHFILES_AVAILABLE:
    from watchfiles import watch as watchfiles_watch  # type: ignore[import-not-found]
else:
    watchfiles_watch = None

WATCH_PATH_OPTION = typer.Option(
    None,
    "--watch-path",
    "--watch-paths",
    help="Absolute folder path(s) to monitor. Repeat flag for multiple paths.",
)


@dataclass
class _WindowPathRecord:
    abs_path: str
    created: bool
    modified: bool
    deleted: bool
    first_seen: datetime
    last_seen: datetime
    last_reported: datetime | None
    pending_report: bool


class ClientFolderActivityAgent(BaseAgent):
    """Folder monitoring agent that emits bounded activity summaries."""

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
        capture_window_s: float,
        reemit_cooldown_s: float,
        watchfiles_debounce_ms: int,
        sample_interval: float,
        heartbeat_interval: float,
        emit_path_samples_limit: int,
        use_watchfiles: bool,
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
        self.coalesce_window_s = max(0.0, coalesce_window_s)
        self.capture_window_s = max(1.0, capture_window_s)
        self.reemit_cooldown_s = max(0.0, reemit_cooldown_s)
        self.watchfiles_debounce_ms = max(0, watchfiles_debounce_ms)
        self.emit_path_samples_limit = max(1, emit_path_samples_limit)
        self.use_watchfiles = bool(use_watchfiles)

        self._segment_start: datetime | None = None
        self._last_snapshot: dict[str, tuple[int, int]] = {}
        self._window_records: dict[str, _WindowPathRecord] = {}
        self._events_seen_total = 0
        self._last_event_ts: datetime | None = None
        self._degraded_paths: set[str] = set()
        self._degraded_emitted = False
        self._watch_path_available: dict[str, bool] = {}
        self._watch_overlap_warning_emitted = False

        self._watch_backend = "watchfiles" if WATCHFILES_AVAILABLE and self.use_watchfiles else "polling"
        self._watch_thread_started = False
        self._watch_stop_event = threading.Event()
        self._watch_event_buffer: list[tuple[datetime, str, str]] = []
        self._watch_event_lock = threading.Lock()
        self._watch_backend_status_emitted = False

    def _path_included(self, root: Path, file_path: Path) -> bool:
        try:
            rel_path = file_path.relative_to(root).as_posix()
        except ValueError:
            rel_path = file_path.name
        include_ok = any(
            pattern in {"*", "**/*"}
            or fnmatch.fnmatch(rel_path, pattern)
            or fnmatch.fnmatch(file_path.name, pattern)
            for pattern in self.include_globs
        )
        if not include_ok:
            return False
        excluded = any(
            fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(file_path.name, pattern)
            for pattern in self.exclude_globs
        )
        return not excluded

    def _resolve_watch_root(self, file_path: Path) -> Path | None:
        for root in self.watch_paths:
            try:
                file_path.relative_to(root)
                return root
            except ValueError:
                continue
        return None

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

    def _map_watchfiles_change(self, raw_change: object) -> str:
        change_name_raw = getattr(raw_change, "name", raw_change)
        change_name = str(change_name_raw).lower()
        if "add" in change_name or change_name == "1":
            return "created"
        if "delete" in change_name or "remove" in change_name or change_name == "3":
            return "deleted"
        return "modified"

    def _watch_loop(self, roots: list[str]) -> None:
        if watchfiles_watch is None:
            return
        watch_step_ms = max(50, int(round(self.sample_interval * 1000.0)))
        rust_timeout_ms = max(250, watch_step_ms)
        for changes in watchfiles_watch(
            *roots,
            recursive=True,
            debounce=self.watchfiles_debounce_ms,
            step=watch_step_ms,
            stop_event=self._watch_stop_event,
            rust_timeout=rust_timeout_ms,
            yield_on_timeout=True,
        ):
            if self._watch_stop_event.is_set():
                break
            if not changes:
                continue
            now = datetime.now(UTC)
            buffered: list[tuple[datetime, str, str]] = []
            for raw_change, raw_path in changes:
                path_obj = Path(str(raw_path))
                root = self._resolve_watch_root(path_obj)
                if root is None:
                    continue
                if not self._path_included(root, path_obj):
                    continue
                event_kind = self._map_watchfiles_change(raw_change)
                buffered.append((now, str(path_obj), event_kind))
            if buffered:
                with self._watch_event_lock:
                    self._watch_event_buffer.extend(buffered)

    def _ensure_watch_thread(self) -> None:
        if self._watch_backend != "watchfiles":
            return
        if self._watch_thread_started:
            return
        roots: list[str] = []
        for root in self.watch_paths:
            if root.exists() and root.is_dir():
                roots.append(str(root))
        if not roots:
            return
        self._watch_stop_event.clear()
        watch_thread = threading.Thread(target=self._watch_loop, args=(roots,), daemon=True)
        watch_thread.start()
        self._watch_thread_started = True

    def _drain_watch_events(self) -> list[tuple[datetime, str, str]]:
        with self._watch_event_lock:
            if not self._watch_event_buffer:
                return []
            drained = list(self._watch_event_buffer)
            self._watch_event_buffer.clear()
        return drained

    def _to_sample_path(self, path_text: str) -> str:
        file_path = Path(path_text)
        for root in self.watch_paths:
            try:
                return file_path.relative_to(root).as_posix()
            except ValueError:
                continue
        return file_path.as_posix()

    def _event_record_for_path(self, path_text: str) -> dict[str, Any]:
        """Build one lightweight created/modified/deleted path record."""
        source_path = Path(path_text)
        record: dict[str, Any] = {
            "path": self._to_sample_path(path_text),
            "ext": source_path.suffix.lower() or "[no_ext]",
        }
        try:
            stat_result = source_path.stat()
            record["mtime_ns"] = stat_result.st_mtime_ns
            record["size"] = stat_result.st_size
        except OSError:
            # OSError: path may disappear between event and record creation.
            record["mtime_ns"] = None
            record["size"] = None
        return record

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

    def _emit_watch_path_transition_logs(self, now: datetime, degraded_paths: set[str]) -> None:
        degraded_set = set(degraded_paths)
        for root in sorted(self.watch_paths, key=lambda path: str(path)):
            path_text = str(root)
            available = path_text not in degraded_set
            previous = self._watch_path_available.get(path_text)
            self._watch_path_available[path_text] = available
            if previous is None:
                if not available:
                    self._emit_watch_path_log(
                        now,
                        level="warning",
                        message="Watch path unavailable; monitoring paused for this path.",
                        path_text=path_text,
                    )
                continue
            if previous == available:
                continue
            if available:
                self._emit_watch_path_log(
                    now,
                    level="info",
                    message="Watch path restored; monitoring resumed for this path.",
                    path_text=path_text,
                )
            else:
                self._emit_watch_path_log(
                    now,
                    level="warning",
                    message="Watch path unavailable; monitoring paused for this path.",
                    path_text=path_text,
                )

    def _emit_watch_path_log(
        self,
        now: datetime,
        *,
        level: str,
        message: str,
        path_text: str,
    ) -> None:
        self.send_message(
            {
                "type": "log",
                "timestamp": now.isoformat(),
                "agent_id": self.agent_id,
                "agent_label": self.agent_label,
                "protocol_version": self.protocol_version,
                "agent_version": self.agent_version,
                "level": level,
                "message": message,
                "markup": False,
                "data": {},
                "extra": {"watch_path": path_text},
            }
        )

    def _runtime_managed_roots(self) -> list[Path]:
        roots: dict[str, Path] = {}
        data_dir_raw = os.getenv("MIMOLO_DATA_DIR")
        if data_dir_raw:
            data_dir = Path(data_dir_raw).expanduser()
            roots[str(data_dir / "operations" / "logs")] = data_dir / "operations" / "logs"
            roots[str(data_dir / "operations" / "journal")] = data_dir / "operations" / "journal"
            roots[str(data_dir / "runtime")] = data_dir / "runtime"
        ops_log_path_raw = os.getenv("MIMOLO_OPS_LOG_PATH")
        if ops_log_path_raw:
            log_parent = Path(ops_log_path_raw).expanduser().parent
            roots[str(log_parent)] = log_parent
        return sorted(roots.values(), key=lambda path: str(path))

    def _paths_overlap(self, left: Path, right: Path) -> bool:
        return left == right or left.is_relative_to(right) or right.is_relative_to(left)

    def _emit_watch_overlap_warning_once(self, now: datetime) -> None:
        if self._watch_overlap_warning_emitted:
            return
        runtime_roots = self._runtime_managed_roots()
        overlaps: list[dict[str, str]] = []
        for watch_root in self.watch_paths:
            for runtime_root in runtime_roots:
                if not self._paths_overlap(watch_root, runtime_root):
                    continue
                overlaps.append(
                    {
                        "watch_path": str(watch_root),
                        "runtime_path": str(runtime_root),
                    }
                )
        if overlaps:
            self.send_message(
                {
                    "type": "log",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": self.protocol_version,
                    "agent_version": self.agent_version,
                    "level": "warning",
                    "message": (
                        "Watch path overlaps MiMoLo runtime-managed directories; "
                        "self-generated churn is likely."
                    ),
                    "markup": False,
                    "data": {},
                    "extra": {"overlaps": overlaps},
                }
            )
        self._watch_overlap_warning_emitted = True

    def _register_window_event(self, now: datetime, path_text: str, event_kind: str) -> None:
        record = self._window_records.get(path_text)
        if record is None:
            record = _WindowPathRecord(
                abs_path=path_text,
                created=False,
                modified=False,
                deleted=False,
                first_seen=now,
                last_seen=now,
                last_reported=None,
                pending_report=True,
            )
            self._window_records[path_text] = record

        record.last_seen = now
        if event_kind == "created":
            record.created = True
            record.deleted = False
        elif event_kind == "deleted":
            record.deleted = True
        else:
            record.modified = True

        if event_kind == "deleted":
            record.pending_report = True
            return

        if record.last_reported is None:
            record.pending_report = True
            return

        since_report_s = (now - record.last_reported).total_seconds()
        if since_report_s >= self.reemit_cooldown_s:
            record.pending_report = True

    def _collect_polling_events(self, now: datetime) -> tuple[list[tuple[datetime, str, str]], set[str]]:
        events: list[tuple[datetime, str, str]] = []
        current_snapshot, degraded_paths = self._scan_filesystem()

        current_keys = set(current_snapshot.keys())
        previous_keys = set(self._last_snapshot.keys())

        created = current_keys - previous_keys
        deleted = previous_keys - current_keys
        modified = {
            path
            for path in current_keys & previous_keys
            if current_snapshot[path] != self._last_snapshot[path]
        }

        for path_text in sorted(created):
            events.append((now, path_text, "created"))
        for path_text in sorted(modified):
            events.append((now, path_text, "modified"))
        for path_text in sorted(deleted):
            events.append((now, path_text, "deleted"))

        self._last_snapshot = current_snapshot
        return events, degraded_paths

    def _prune_window_records(self, now: datetime) -> None:
        stale_paths: list[str] = []
        for path_text, record in self._window_records.items():
            age_s = (now - record.last_seen).total_seconds()
            if age_s > self.capture_window_s and not record.pending_report:
                stale_paths.append(path_text)
        for path_text in stale_paths:
            self._window_records.pop(path_text, None)

    def _accumulate(self, now: datetime) -> None:
        if self._segment_start is None:
            self._segment_start = now
        self._emit_watch_overlap_warning_once(now)

        degraded_paths: set[str] = {
            str(root) for root in self.watch_paths if not root.exists() or not root.is_dir()
        }

        if self._watch_backend == "watchfiles":
            self._ensure_watch_thread()
            if not self._watch_backend_status_emitted:
                self.send_message(
                    {
                        "type": "log",
                        "timestamp": now.isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": self.protocol_version,
                        "agent_version": self.agent_version,
                        "level": "info",
                        "message": "Folder watcher backend: watchfiles",
                        "markup": False,
                        "data": {},
                        "extra": {"backend": "watchfiles"},
                    }
                )
                self._watch_backend_status_emitted = True
            events = self._drain_watch_events()
        else:
            if not self._watch_backend_status_emitted:
                self.send_message(
                    {
                        "type": "log",
                        "timestamp": now.isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": self.protocol_version,
                        "agent_version": self.agent_version,
                        "level": "info",
                        "message": "Folder watcher backend: polling_fallback",
                        "markup": False,
                        "data": {},
                        "extra": {"backend": "polling_fallback"},
                    }
                )
                self._watch_backend_status_emitted = True
            events, poll_degraded = self._collect_polling_events(now)
            degraded_paths.update(poll_degraded)

        self._emit_watch_path_transition_logs(now, degraded_paths)
        self._emit_health_transition(now, degraded_paths)

        if events:
            self._last_event_ts = now
        self._events_seen_total += len(events)
        for event_time, path_text, event_kind in events:
            self._register_window_event(event_time, path_text, event_kind)

        self._prune_window_records(now)

    def _take_snapshot(self, now: datetime) -> tuple[datetime, datetime, dict[str, Any]]:
        # Flush/manual renders should evaluate the same event pipeline as scheduled sampling.
        self._accumulate(now)
        start = self._segment_start or now
        end = now

        created_paths: list[dict[str, Any]] = []
        modified_paths: list[dict[str, Any]] = []
        deleted_paths: list[dict[str, Any]] = []
        path_samples: list[str] = []
        top_extensions: Counter[str] = Counter()
        dropped_events = 0
        counts: Counter[str] = Counter()

        reportable_paths = sorted(
            path_text
            for path_text, record in self._window_records.items()
            if record.pending_report
        )

        for path_text in reportable_paths:
            record = self._window_records[path_text]
            counts["total"] += 1

            if record.created:
                counts["created"] += 1
                if len(created_paths) < self.emit_path_samples_limit:
                    created_paths.append(self._event_record_for_path(path_text))
                else:
                    dropped_events += 1
            if record.modified:
                counts["modified"] += 1
                if len(modified_paths) < self.emit_path_samples_limit:
                    modified_paths.append(self._event_record_for_path(path_text))
                else:
                    dropped_events += 1
            if record.deleted:
                counts["deleted"] += 1
                if len(deleted_paths) < self.emit_path_samples_limit:
                    deleted_paths.append(self._event_record_for_path(path_text))
                else:
                    dropped_events += 1

            if len(path_samples) < self.emit_path_samples_limit:
                path_samples.append(self._to_sample_path(path_text))
            else:
                dropped_events += 1

            ext = Path(path_text).suffix.lower() or "[no_ext]"
            top_extensions[ext] += 1

            record.pending_report = False
            record.last_reported = now

        snapshot: dict[str, Any] = {
            "counts": {
                "created": int(counts.get("created", 0)),
                "modified": int(counts.get("modified", 0)),
                "deleted": int(counts.get("deleted", 0)),
                "renamed": 0,
                "total": int(counts.get("total", 0)),
            },
            "top_extensions": dict(top_extensions),
            "path_samples": path_samples,
            "created_paths": created_paths,
            "modified_paths": modified_paths,
            "deleted_paths": deleted_paths,
            "dropped_events": dropped_events,
            "degraded_paths": sorted(self._degraded_paths),
            "capture_window_s": self.capture_window_s,
            "reemit_cooldown_s": self.reemit_cooldown_s,
            "backend": self._watch_backend,
        }
        self._segment_start = now
        return start, end, snapshot

    def _format_summary(
        self, snapshot: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        counts = snapshot.get("counts", {})
        top_ext = snapshot.get("top_extensions", {})
        items = sorted(top_ext.items(), key=lambda pair: pair[1], reverse=True)
        return {
            "schema": "client_folder_activity.summary.v2",
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
            "created_paths": list(snapshot.get("created_paths", [])),
            "modified_paths": list(snapshot.get("modified_paths", [])),
            "deleted_paths": list(snapshot.get("deleted_paths", [])),
            "top_extensions": [{"ext": ext, "count": int(count)} for ext, count in items[:10]],
            "path_samples": list(snapshot.get("path_samples", [])),
            "dropped_events": int(snapshot.get("dropped_events", 0)),
            "capture_window_s": float(snapshot.get("capture_window_s", self.capture_window_s)),
            "reemit_cooldown_s": float(
                snapshot.get("reemit_cooldown_s", self.reemit_cooldown_s)
            ),
            "backend": str(snapshot.get("backend", self._watch_backend)),
        }

    def _activity_signal(
        self, snapshot: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        counts_raw = snapshot.get("counts", {})
        if not isinstance(counts_raw, dict):
            total_changes = 0
        else:
            total_changes = int(counts_raw.get("total", 0))
        if total_changes > 0:
            reason = f"{total_changes} tracked file paths changed"
            keep_alive: bool | None = True
        else:
            reason = "no tracked file changes in window"
            keep_alive = False
        return {
            "mode": "active",
            "keep_alive": keep_alive,
            "reason": reason,
        }

    def _accumulated_count(self) -> int:
        pending = 0
        for record in self._window_records.values():
            if record.pending_report:
                pending += 1
        return pending

    def _heartbeat_metrics(self) -> dict[str, Any]:
        metrics = super()._heartbeat_metrics()
        metrics["events_seen_total"] = self._events_seen_total
        metrics["events_buffered"] = self._accumulated_count()
        if self._last_event_ts is None:
            metrics["last_event_age_s"] = None
        else:
            metrics["last_event_age_s"] = max(
                0.0, (datetime.now(UTC) - self._last_event_ts).total_seconds()
            )
        metrics["watch_path_count"] = len(self.watch_paths)
        metrics["degraded_path_count"] = len(self._degraded_paths)
        metrics["backend"] = self._watch_backend
        metrics["capture_window_s"] = self.capture_window_s
        metrics["reemit_cooldown_s"] = self.reemit_cooldown_s
        return metrics


def main(
    client_id: str = typer.Option("default-client", help="Client identifier for attribution."),
    client_name: str = typer.Option("Default Client", help="Client display name."),
    watch_paths: list[str] | None = WATCH_PATH_OPTION,
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
    capture_window_s: float = typer.Option(
        300.0,
        help="Rolling event capture window in seconds.",
    ),
    reemit_cooldown_s: float = typer.Option(
        60.0,
        help="Minimum seconds before the same file path is re-emitted.",
    ),
    watchfiles_debounce_ms: int = typer.Option(
        1000,
        help="watchfiles debounce window in milliseconds.",
    ),
    poll_interval_s: float = typer.Option(
        15.0,
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
    use_watchfiles: bool = typer.Option(
        True,
        "--use-watchfiles/--no-use-watchfiles",
        help="Use watchfiles event backend when available.",
    ),
) -> None:
    """Run the client folder activity agent."""
    if not watch_paths:
        raise typer.BadParameter("at least one --watch-path is required")
    resolved_watch_paths: list[str] = []
    for raw_value in watch_paths:
        for part in raw_value.split(","):
            trimmed = part.strip()
            if not trimmed:
                continue
            resolved = Path(trimmed).expanduser()
            if not resolved.is_absolute():
                raise typer.BadParameter(f"--watch-path must be absolute: {trimmed}")
            resolved_watch_paths.append(str(resolved))
    if not resolved_watch_paths:
        raise typer.BadParameter("at least one non-empty --watch-path is required")

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
        coalesce_window_s=max(0.0, coalesce_window_s),
        capture_window_s=max(1.0, capture_window_s),
        reemit_cooldown_s=max(0.0, reemit_cooldown_s),
        watchfiles_debounce_ms=max(0, watchfiles_debounce_ms),
        sample_interval=max(0.25, poll_interval_s),
        heartbeat_interval=max(1.0, heartbeat_interval_s),
        emit_path_samples_limit=emit_path_samples_limit,
        use_watchfiles=use_watchfiles,
    )
    agent.run()


if __name__ == "__main__":
    typer.run(main)
