from __future__ import annotations

from pathlib import Path

import pytest

from mimolo import cli


class _FakeChannel:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.writes: list[dict[str, object]] = []
        self.closed = False
        self.read_count = 0

    def write_line(self, data: dict[str, object]) -> None:
        self.writes.append(data)

    def read_line(self) -> str | None:
        self.read_count += 1
        if self.read_count == 1:
            return None
        index = self.read_count - 2
        if index >= len(self.responses):
            return None
        return cli.json.dumps(self.responses[index])

    def close(self) -> None:
        self.closed = True


def test_resolve_ops_ipc_settings_uses_launcher_override_when_env_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "mml.toml"
    config_path.write_text('[launcher]\nipc_path = "./runtime/custom.sock"\n', encoding="utf-8")

    monkeypatch.delenv("MIMOLO_IPC_PATH", raising=False)
    monkeypatch.delenv("MIMOLO_IPC_SLOWPOKE_ROOT", raising=False)
    monkeypatch.delenv("MIMOLO_IPC_MODE", raising=False)
    monkeypatch.setattr(cli, "effective_ipc_mode", lambda _raw: "unix")

    ipc_path, slowpoke_root, ipc_mode = cli._resolve_ops_ipc_settings(config_path)

    assert ipc_path == str((tmp_path / "runtime" / "custom.sock").resolve(strict=False))
    assert slowpoke_root == f"{ipc_path}.slowpoke"
    assert ipc_mode == "unix"


def test_send_ops_control_request_uses_unix_channel(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    channel = _FakeChannel([])

    monkeypatch.setattr(
        cli,
        "_resolve_ops_ipc_settings",
        lambda _config: (str(tmp_path / "operations.sock"), str(tmp_path / "slowpoke"), "unix"),
    )
    monkeypatch.setattr(cli, "create_ipc_channel", lambda _path, server=False: channel)

    def _write_line(data: dict[str, object]) -> None:
        channel.writes.append(data)
        channel.responses[:] = [
            {
                "ok": True,
                "cmd": "control_orchestrator",
                "request_id": data["request_id"],
                "data": {"action": "stop", "status": "stop_requested"},
            }
        ]

    channel.write_line = _write_line

    response = cli._send_ops_control_request(
        action="stop",
        config_path=tmp_path / "mml.toml",
        timeout_s=1.0,
    )

    assert response["ok"] is True
    assert len(channel.writes) == 1
    assert channel.writes[0]["cmd"] == "control_orchestrator"
    assert channel.writes[0]["action"] == "stop"
    assert isinstance(channel.writes[0]["request_id"], str)
    assert channel.closed is True


def test_send_ops_control_request_ignores_unrelated_slowpoke_responses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    channel = _FakeChannel([])

    monkeypatch.setattr(
        cli,
        "_resolve_ops_ipc_settings",
        lambda _config: (str(tmp_path / "operations.sock"), str(tmp_path / "slowpoke"), "slowpoke"),
    )

    def _create_slowpoke_channel(*, read_dir: str, write_dir: str, create: bool = False) -> _FakeChannel:
        assert create is False
        return channel

    monkeypatch.setattr(
        "mimolo.core.ipc_slowpoke.create_slowpoke_channel",
        _create_slowpoke_channel,
    )

    def _write_line(data: dict[str, object]) -> None:
        channel.writes.append(data)
        channel.responses[:] = [
            {
                "ok": True,
                "cmd": "control_orchestrator",
                "request_id": "someone-else",
                "data": {"action": "status", "status": "ok"},
            },
            {
                "ok": True,
                "cmd": "control_orchestrator",
                "request_id": data["request_id"],
                "data": {"action": "status", "status": "ok"},
            },
        ]

    channel.write_line = _write_line

    response = cli._send_ops_control_request(
        action="status",
        config_path=tmp_path / "mml.toml",
        timeout_s=1.0,
    )

    assert response["ok"] is True
    assert response["request_id"] == channel.writes[0]["request_id"]
    assert channel.closed is True
