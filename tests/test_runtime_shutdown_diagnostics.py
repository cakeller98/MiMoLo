from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import mimolo.core.runtime_shutdown as runtime_shutdown_mod


class _FakeConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, message: object, *args: object, **kwargs: object) -> None:
        self.lines.append(str(message))


class _FakeSink:
    def __init__(self) -> None:
        self.flushed = False
        self.closed = False

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, *, pid: int = 1001) -> None:
        self.pid = pid
        self._exit_code: int | None = None

    def poll(self) -> int | None:
        return self._exit_code

    def set_exit(self, code: int) -> None:
        self._exit_code = code


class _FakeHandle:
    def __init__(self, label: str, messages: list[object]) -> None:
        self.label = label
        self.process = _FakeProcess()
        self._messages = list(messages)
        self.sent_commands: list[object] = []

    def send_command(self, cmd: object) -> bool:
        self.sent_commands.append(cmd)
        return True

    def read_message(self, timeout: float = 0.001) -> object | None:
        if self._messages:
            message = self._messages.pop(0)
            if not self._messages:
                self.process.set_exit(0)
            return message
        return None

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def shutdown(self) -> None:
        self.process.set_exit(0)


class _FakeAgentManager:
    def __init__(self, handle: _FakeHandle) -> None:
        self.agents = {handle.label: handle}

    def shutdown_all(self) -> list[_FakeHandle]:
        handles = list(self.agents.values())
        for handle in handles:
            if handle.is_alive():
                handle.shutdown()
        return handles


@dataclass
class _FakeMonitorConfig:
    console_verbosity: str = "warning"


@dataclass
class _FakeConfig:
    monitor: _FakeMonitorConfig = field(default_factory=_FakeMonitorConfig)


class _FakeRuntime:
    def __init__(self, handle: _FakeHandle) -> None:
        self.console = _FakeConsole()
        self.config = _FakeConfig()
        self.agent_manager = _FakeAgentManager(handle)
        self.file_sink = _FakeSink()
        self.diagnostics_sink = _FakeSink()
        self._shutting_down = False
        self._shutdown_deadlines: dict[str, float] = {}
        self._shutdown_phase: dict[str, str] = {}
        self.diagnostics: list[dict[str, Any]] = []
        self.handled_summaries: list[object] = []
        self._agent_states: dict[str, str] = {}
        self._agent_state_details: dict[str, str] = {}

    def _write_diagnostic_event(
        self,
        label: str,
        event: str,
        timestamp: datetime,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.diagnostics.append(
            {
                "label": label,
                "event": event,
                "timestamp": timestamp,
                "data": data or {},
            }
        )

    def _set_agent_state(self, label: str, state: str, detail: str) -> None:
        self._agent_states[label] = state
        self._agent_state_details[label] = detail

    def _handle_agent_summary(self, label: str, msg: object) -> None:
        self.handled_summaries.append((label, msg))

    def _handle_agent_log(self, label: str, msg: object) -> None:
        return None

    def _handle_heartbeat(self, label: str, msg: object) -> None:
        return None

    def _handle_status(self, label: str, msg: object) -> None:
        return None

    def _handle_agent_ack(self, label: str, msg: object) -> None:
        return None

    def _handle_agent_error(self, label: str, msg: object) -> None:
        return None

    def _debug(self, text: str) -> None:
        return None

    def _stop_ipc_server(self) -> None:
        return None


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def time(self) -> float:
        self.value += 0.25
        return self.value


def _ack_message(timestamp: str, ack_command: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="ack",
        timestamp=timestamp,
        ack_command=ack_command,
    )


def _summary_message(timestamp: str, event_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="summary",
        timestamp=timestamp,
        data={"event": event_name},
    )


def _step_status_pairs(runtime: _FakeRuntime) -> set[tuple[str, str]]:
    return {
        (entry["data"].get("step", ""), entry["data"].get("status", ""))
        for entry in runtime.diagnostics
        if entry["event"] == "shutdown_agent_step"
    }


def test_shutdown_runtime_records_clean_sequence_steps(monkeypatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(runtime_shutdown_mod.time, "time", clock.time)

    handle = _FakeHandle(
        "alpha",
        [
            _ack_message("2026-04-12T10:00:00+00:00", "stop"),
            _ack_message("2026-04-12T10:00:01+00:00", "flush"),
            _summary_message("2026-04-12T10:00:02+00:00", "creo_trail_activity"),
            _ack_message("2026-04-12T10:00:03+00:00", "shutdown"),
        ],
    )
    runtime = _FakeRuntime(handle)

    runtime_shutdown_mod.shutdown_runtime(runtime)

    steps = _step_status_pairs(runtime)
    assert ("sequence", "sent") in steps
    assert ("stop", "ack") in steps
    assert ("flush", "ack") in steps
    assert ("summary", "received") in steps
    assert ("shutdown", "ack") in steps
    assert ("process", "exited") in steps

    result = next(
        entry for entry in runtime.diagnostics if entry["event"] == "shutdown_agent_result"
    )
    assert result["data"]["agent"] == "alpha"
    assert result["data"]["clean_shutdown"] is True
    assert result["data"]["summary_received"] is True
    assert result["data"]["process_exited"] is True
    assert result["data"]["exit_code"] == 0
    assert runtime.file_sink.flushed is True
    assert runtime.file_sink.closed is True
    assert runtime.diagnostics_sink.flushed is True
    assert runtime.diagnostics_sink.closed is True


def test_shutdown_runtime_records_missing_summary_timeout(monkeypatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(runtime_shutdown_mod.time, "time", clock.time)

    handle = _FakeHandle(
        "beta",
        [
            _ack_message("2026-04-12T11:00:00+00:00", "stop"),
            _ack_message("2026-04-12T11:00:01+00:00", "flush"),
            _ack_message("2026-04-12T11:00:02+00:00", "shutdown"),
        ],
    )
    runtime = _FakeRuntime(handle)

    runtime_shutdown_mod.shutdown_runtime(runtime)

    steps = _step_status_pairs(runtime)
    assert ("summary", "timeout") in steps
    result = next(
        entry for entry in runtime.diagnostics if entry["event"] == "shutdown_agent_result"
    )
    assert result["data"]["agent"] == "beta"
    assert result["data"]["clean_shutdown"] is False
    assert result["data"]["summary_received"] is False

    exceptions = [
        entry for entry in runtime.diagnostics if entry["event"] == "shutdown_exception"
    ]
    assert any(entry["data"].get("phase") == "flush" for entry in exceptions)
