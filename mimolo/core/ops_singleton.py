"""Singleton guard for MiMoLo Operations runtime."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OperationsLockStatus:
    """Result of attempting to acquire/release an operations singleton lock."""

    acquired: bool
    detail: str
    existing_pid: int | None = None


class OperationsSingletonLock:
    """Cross-platform singleton lock based on an atomic lock directory."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._lock_dir = base_dir / "operations" / "ops.lock"
        self._meta_path = self._lock_dir / "owner.json"
        self._pid = os.getpid()
        self._held = False

    def _is_pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _read_existing_pid(self) -> int | None:
        if not self._meta_path.exists():
            return None
        try:
            raw_text = self._meta_path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        pid_raw = payload.get("pid")
        if isinstance(pid_raw, int):
            return pid_raw
        return None

    def _write_owner_metadata(self) -> None:
        payload = {
            "pid": self._pid,
            "ppid": os.getppid(),
        }
        text = json.dumps(payload, separators=(",", ":"))
        self._meta_path.write_text(text, encoding="utf-8")

    def _clear_stale_lock(self) -> None:
        if self._meta_path.exists():
            self._meta_path.unlink()
        self._lock_dir.rmdir()

    def acquire(self) -> OperationsLockStatus:
        """Acquire lock if no other live operations process holds it."""
        self._lock_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_dir.mkdir()
            self._write_owner_metadata()
            self._held = True
            return OperationsLockStatus(acquired=True, detail="acquired")
        except FileExistsError:
            existing_pid = self._read_existing_pid()
            if existing_pid is not None and self._is_pid_running(existing_pid):
                return OperationsLockStatus(
                    acquired=False,
                    detail="already_running",
                    existing_pid=existing_pid,
                )
            try:
                self._clear_stale_lock()
            except OSError:
                # Another process may be replacing the stale lock concurrently.
                pass
            try:
                self._lock_dir.mkdir()
                self._write_owner_metadata()
                self._held = True
                return OperationsLockStatus(acquired=True, detail="acquired_after_stale_cleanup")
            except FileExistsError:
                existing_pid = self._read_existing_pid()
                return OperationsLockStatus(
                    acquired=False,
                    detail="already_running",
                    existing_pid=existing_pid,
                )

    def release(self) -> OperationsLockStatus:
        """Release lock if current process owns it."""
        if not self._held:
            return OperationsLockStatus(acquired=False, detail="not_held")
        existing_pid = self._read_existing_pid()
        if existing_pid is not None and existing_pid != self._pid:
            self._held = False
            return OperationsLockStatus(
                acquired=False,
                detail="ownership_mismatch",
                existing_pid=existing_pid,
            )
        try:
            if self._meta_path.exists():
                self._meta_path.unlink()
            self._lock_dir.rmdir()
        except OSError:
            self._held = False
            return OperationsLockStatus(acquired=False, detail="release_failed")
        self._held = False
        return OperationsLockStatus(acquired=True, detail="released")

