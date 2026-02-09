from __future__ import annotations

from pathlib import Path

from mimolo.core.ops_singleton import OperationsSingletonLock


def test_acquire_and_release_lock(tmp_path: Path) -> None:
    lock = OperationsSingletonLock(tmp_path)
    acquired = lock.acquire()
    assert acquired.acquired is True
    assert acquired.detail in {"acquired", "acquired_after_stale_cleanup"}

    released = lock.release()
    assert released.acquired is True
    assert released.detail == "released"


def test_existing_live_pid_blocks_acquire(tmp_path: Path, monkeypatch) -> None:
    first = OperationsSingletonLock(tmp_path)
    first_status = first.acquire()
    assert first_status.acquired is True

    second = OperationsSingletonLock(tmp_path)

    original_is_pid_running = second._is_pid_running

    def _always_running(pid: int) -> bool:
        return pid > 0 or original_is_pid_running(pid)

    monkeypatch.setattr(second, "_is_pid_running", _always_running)
    second_status = second.acquire()
    assert second_status.acquired is False
    assert second_status.detail == "already_running"
    assert isinstance(second_status.existing_pid, int)

    first.release()


def test_stale_lock_is_reclaimed(tmp_path: Path) -> None:
    lock_dir = tmp_path / "operations" / "ops.lock"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner.json").write_text('{"pid": 999999}', encoding="utf-8")

    lock = OperationsSingletonLock(tmp_path)
    status = lock.acquire()
    assert status.acquired is True
    assert status.detail == "acquired_after_stale_cleanup"

    lock.release()

