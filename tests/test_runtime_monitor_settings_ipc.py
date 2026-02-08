from __future__ import annotations

from pathlib import Path

from mimolo.core.config import Config, load_config
from mimolo.core.runtime import Runtime


def _runtime_with_config_path(tmp_path: Path) -> Runtime:
    return Runtime(Config(), config_path=tmp_path / "runtime.toml")


def test_get_monitor_settings_returns_policy_and_monitor_defaults(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_config_path(tmp_path)
    response = runtime._build_ipc_response({"cmd": "get_monitor_settings"})
    assert response["ok"] is True
    assert response["cmd"] == "get_monitor_settings"
    data = response["data"]
    monitor = data["monitor"]
    assert monitor["poll_tick_s"] > 0
    assert monitor["cooldown_seconds"] > 0
    policy = data["cadence_policy"]
    assert policy["strategy"] == "max(global_poll_tick_s, agent_requested_interval_s)"


def test_update_monitor_settings_persists_and_updates_runtime_state(
    tmp_path: Path,
) -> None:
    runtime = _runtime_with_config_path(tmp_path)
    response = runtime._build_ipc_response(
        {
            "cmd": "update_monitor_settings",
            "updates": {
                "poll_tick_s": 3.5,
                "cooldown_seconds": 45.0,
                "console_verbosity": "warning",
            },
        }
    )
    assert response["ok"] is True
    data = response["data"]
    monitor = data["monitor"]
    assert monitor["poll_tick_s"] == 3.5
    assert monitor["cooldown_seconds"] == 45.0
    assert monitor["console_verbosity"] == "warning"
    assert runtime.config.monitor.poll_tick_s == 3.5
    assert runtime.cooldown.cooldown_seconds == 45.0

    reloaded = load_config(tmp_path / "runtime.toml")
    assert reloaded.monitor.poll_tick_s == 3.5
    assert reloaded.monitor.cooldown_seconds == 45.0
    assert reloaded.monitor.console_verbosity == "warning"


def test_update_monitor_settings_rejects_unknown_keys(tmp_path: Path) -> None:
    runtime = _runtime_with_config_path(tmp_path)
    previous = runtime.config.monitor.poll_tick_s
    response = runtime._build_ipc_response(
        {
            "cmd": "update_monitor_settings",
            "updates": {
                "poll_tick_ms": 200,
            },
        }
    )
    assert response["ok"] is False
    assert str(response["error"]).startswith("unknown_keys:")
    assert response["data"]["unknown_keys"] == ["poll_tick_ms"]
    assert runtime.config.monitor.poll_tick_s == previous


def test_update_monitor_settings_rolls_back_on_validation_error(tmp_path: Path) -> None:
    runtime = _runtime_with_config_path(tmp_path)
    previous = runtime.config.monitor.poll_tick_s
    response = runtime._build_ipc_response(
        {
            "cmd": "update_monitor_settings",
            "updates": {
                "poll_tick_s": -1,
            },
        }
    )
    assert response["ok"] is False
    assert str(response["error"]).startswith("invalid_updates:")
    assert runtime.config.monitor.poll_tick_s == previous


def test_update_monitor_settings_without_config_path_returns_save_error() -> None:
    runtime = Runtime(Config())
    previous = runtime.config.monitor.poll_tick_s
    response = runtime._build_ipc_response(
        {
            "cmd": "update_monitor_settings",
            "updates": {
                "poll_tick_s": 1.25,
            },
        }
    )
    assert response["ok"] is False
    assert response["error"] == "config_path_not_set"
    assert runtime.config.monitor.poll_tick_s == previous

