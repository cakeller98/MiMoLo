from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mimolo.core.ipc_slowpoke import SlowpokeChannel
from mimolo.core.runtime_ipc_server import _ipc_server_loop_slowpoke


class _FakeFileSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def write_event(self, event: object) -> None:
        self.events.append(event)


@dataclass
class _FakeStopEvent:
    state: bool = False

    def is_set(self) -> bool:
        return self.state


class _FakeRuntime:
    def __init__(self, socket_path: str) -> None:
        self._ipc_socket_path = socket_path
        self._ipc_slowpoke_root = None
        self._ipc_stop_event = _FakeStopEvent()
        self._ipc_slowpoke_channel = None
        self.file_sink = _FakeFileSink()
        self.console_lines: list[str] = []
        self.diagnostics: list[dict[str, object]] = []
        self.debug_lines: list[str] = []

    def _console_print_safe(self, text: object, *, markup: bool = True) -> None:
        self.console_lines.append(str(text))

    def _write_diagnostic_event(
        self,
        label: str,
        event: str,
        timestamp: datetime,
        data: dict[str, object] | None = None,
    ) -> None:
        self.diagnostics.append(
            {
                "label": label,
                "event": event,
                "timestamp": timestamp,
                "data": data or {},
            }
        )

    def _debug(self, text: str) -> None:
        self.debug_lines.append(text)


def test_ipc_server_loop_slowpoke_emits_alert_on_start_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _FakeRuntime(str(tmp_path / "operations.sock"))

    def _boom(*args: object, **kwargs: object) -> object:
        raise PermissionError("locked by another process")

    monkeypatch.setattr(
        "mimolo.core.ipc_slowpoke.SlowpokeChannel",
        _boom,
    )

    _ipc_server_loop_slowpoke(runtime)  # type: ignore[arg-type]

    assert any("IPC slowpoke server failed to start" in line for line in runtime.console_lines)
    assert any(entry["event"] == "ipc_slowpoke_server_failure" for entry in runtime.diagnostics)
    assert len(runtime.file_sink.events) == 1
    event = runtime.file_sink.events[0]
    assert getattr(event, "label") == "orchestrator"
    assert getattr(event, "event") == "ipc_slowpoke_server_failure"


def test_slowpoke_read_line_skips_locked_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    read_dir = tmp_path / "read"
    write_dir = tmp_path / "write"
    read_dir.mkdir()
    write_dir.mkdir()
    locked_file = read_dir / "stuck.json"
    locked_file.write_text('{"cmd":"ping"}', encoding="utf-8")

    channel = SlowpokeChannel(str(read_dir), str(write_dir), create=False)
    monkeypatch.setattr(SlowpokeChannel, "POLL_INTERVAL", 0.0)

    original_read_text = Path.read_text

    def _read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == locked_file:
            raise PermissionError("locked")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _read_text)

    assert channel.read_line() is None
