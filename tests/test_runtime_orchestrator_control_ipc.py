from __future__ import annotations

from mimolo.core.config import Config
from mimolo.core.runtime import Runtime


def test_control_orchestrator_status_reports_runtime_state() -> None:
    runtime = Runtime(Config())
    runtime._running = True

    response = runtime._build_ipc_response(
        {"cmd": "control_orchestrator", "action": "status"}
    )

    assert response["ok"] is True
    assert response["cmd"] == "control_orchestrator"
    data = response["data"]
    assert data["accepted"] is True
    assert data["action"] == "status"
    assert data["status"] == "ok"
    assert data["orchestrator"]["running"] is True


def test_control_orchestrator_stop_transitions_running_flag() -> None:
    runtime = Runtime(Config())
    runtime._running = True

    response = runtime._build_ipc_response(
        {"cmd": "control_orchestrator", "action": "stop"}
    )

    assert response["ok"] is True
    data = response["data"]
    assert data["accepted"] is True
    assert data["action"] == "stop"
    assert data["status"] == "stop_requested"
    assert data["orchestrator"]["running"] is False
    assert runtime._running is False

