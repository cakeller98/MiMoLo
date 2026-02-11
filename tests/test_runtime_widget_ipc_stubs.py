from __future__ import annotations

from pathlib import Path

import pytest

from mimolo.core.config import Config, PluginConfig
from mimolo.core.runtime import Runtime


def _make_runtime() -> Runtime:
    return Runtime(Config())


def _make_runtime_with_plugins() -> Runtime:
    cfg = Config()
    cfg.plugins["screen_widget"] = PluginConfig(
        enabled=True,
        plugin_type="agent",
        executable="poetry",
        args=["run", "python", "screen_tracker/screen_tracker.py"],
        heartbeat_interval_s=15.0,
        agent_flush_interval_s=60.0,
    )
    cfg.plugins["folder_widget"] = PluginConfig(
        enabled=True,
        plugin_type="agent",
        executable="poetry",
        args=["run", "python", "client_folder_activity/client_folder_activity.py"],
        heartbeat_interval_s=15.0,
        agent_flush_interval_s=60.0,
    )
    return Runtime(cfg)


def test_widget_stub_missing_plugin_id() -> None:
    runtime = _make_runtime()
    commands = (
        "get_widget_manifest",
        "request_widget_render",
        "dispatch_widget_action",
    )
    for cmd in commands:
        payload = {"cmd": cmd, "instance_id": "inst_123"}
        response = runtime._build_ipc_response(payload)
        assert response["ok"] is False
        assert response["cmd"] == cmd
        assert response["error"] == "missing_plugin_id"


def test_widget_stub_missing_instance_id() -> None:
    runtime = _make_runtime()
    commands = (
        "get_widget_manifest",
        "request_widget_render",
        "dispatch_widget_action",
    )
    for cmd in commands:
        payload = {"cmd": cmd, "plugin_id": "screen_tracker"}
        response = runtime._build_ipc_response(payload)
        assert response["ok"] is False
        assert response["cmd"] == cmd
        assert response["error"] == "missing_instance_id"


def test_widget_screen_tracker_unknown_instance() -> None:
    runtime = _make_runtime()
    response = runtime._build_ipc_response(
        {
            "cmd": "get_widget_manifest",
            "plugin_id": "screen_tracker",
            "instance_id": "missing_instance",
        }
    )
    assert response["ok"] is False
    assert response["error"] == "unknown_instance:missing_instance"


def test_get_widget_manifest_screen_tracker_payload() -> None:
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "get_widget_manifest",
            "plugin_id": "screen_tracker",
            "instance_id": "screen_widget",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["accepted"] is True
    assert data["status"] == "ok"
    assert data["plugin_id"] == "screen_tracker"
    assert data["instance_id"] == "screen_widget"
    widget = data["widget"]
    assert widget["supports_render"] is True
    assert widget["default_aspect_ratio"] == "16:9"
    assert widget["min_refresh_ms"] >= 1000
    assert widget["supported_actions"] == ["refresh"]
    assert widget["content_modes"] == ["html_fragment_v1"]


def test_request_widget_render_screen_tracker_waiting_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIMOLO_DATA_DIR", str(tmp_path))
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "screen_tracker",
            "instance_id": "screen_widget",
            "request_id": "req_001",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["request_id"] == "req_001"
    render = data["render"]
    assert render["mode"] == "html_fragment_v1"
    assert "screen tracker waiting for captures" in render["html"]
    assert render["ttl_ms"] >= 1000
    assert render["state_token"] is None
    assert render["warnings"]


def test_request_widget_render_screen_tracker_returns_file_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MIMOLO_DATA_DIR", str(tmp_path))
    thumb_dir = (
        tmp_path
        / "agents"
        / "screen_tracker"
        / "screen_widget"
        / "artifacts"
        / "thumb"
        / "2026"
        / "02"
        / "09"
    )
    thumb_dir.mkdir(parents=True, exist_ok=True)
    image_path = thumb_dir / "frame_001.svg"
    image_path.write_text("<svg></svg>", encoding="utf-8")

    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "screen_tracker",
            "instance_id": "screen_widget",
            "request_id": "req_002",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is True
    render = response["data"]["render"]
    assert "screen-widget-image" in render["html"]
    assert "data:image/svg+xml;base64," in render["html"]
    assert render["warnings"] == []
    assert render["state_token"] is not None


def test_dispatch_widget_action_screen_tracker_refresh_supported() -> None:
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "dispatch_widget_action",
            "plugin_id": "screen_tracker",
            "instance_id": "screen_widget",
            "action": "refresh",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["accepted"] is True
    assert data["status"] == "ok"
    assert data["supported_actions"] == ["refresh"]


def test_dispatch_widget_action_screen_tracker_unknown_action() -> None:
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "dispatch_widget_action",
            "plugin_id": "screen_tracker",
            "instance_id": "screen_widget",
            "action": "set_filter",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["accepted"] is False
    assert data["status"] == "unsupported_action"


def test_get_widget_manifest_client_folder_activity_payload() -> None:
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "get_widget_manifest",
            "plugin_id": "client_folder_activity",
            "instance_id": "folder_widget",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["accepted"] is True
    assert data["status"] == "ok"
    assert data["plugin_id"] == "client_folder_activity"
    assert data["instance_id"] == "folder_widget"
    widget = data["widget"]
    assert widget["supports_render"] is True
    assert widget["supported_actions"] == ["refresh"]
    assert widget["content_modes"] == ["html_fragment_v1"]


def test_request_widget_render_client_folder_activity_waiting_payload() -> None:
    runtime = _make_runtime_with_plugins()
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "client_folder_activity",
            "instance_id": "folder_widget",
            "request_id": "req_folder_001",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is True
    data = response["data"]
    assert data["request_id"] == "req_folder_001"
    render = data["render"]
    assert render["mode"] == "html_fragment_v1"
    assert "folder watcher waiting for summary data" in render["html"]
    assert render["warnings"] == ["no_summary_yet"]


def test_request_widget_render_client_folder_activity_summary_payload() -> None:
    runtime = _make_runtime_with_plugins()
    runtime.agent_last_summary["folder_widget"] = {
        "counts": {"created": 1, "modified": 2, "deleted": 3, "total": 6},
        "created_paths": [{"path": "new.txt", "size": 120, "mtime_ns": 1_700_000_000_000_000_000}],
        "modified_paths": [{"path": "edit.txt", "size": 50, "mtime_ns": 1_700_000_100_000_000_000}],
        "deleted_paths": [{"path": "gone.txt", "size": None, "mtime_ns": None}],
        "window": {"end": "2026-02-11T12:00:00+00:00"},
    }
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "client_folder_activity",
            "instance_id": "folder_widget",
            "request_id": "req_folder_002",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is True
    render = response["data"]["render"]
    assert "folder-widget-root" in render["html"]
    assert "created 1" in render["html"]
    assert "modified 2" in render["html"]
    assert "deleted 3" in render["html"]
    assert render["warnings"] == []


def test_request_widget_render_client_folder_activity_prefers_recent_rows() -> None:
    runtime = _make_runtime_with_plugins()
    runtime.agent_last_summary["folder_widget"] = {
        "counts": {"created": 1, "modified": 1, "deleted": 1, "total": 3},
        "recent_widget_rows": [
            {
                "event": "modified",
                "path": "newest.txt",
                "size": 10,
                "mtime_ns": 1_700_000_200_000_000_000,
            },
            {
                "event": "created",
                "path": "older.txt",
                "size": 8,
                "mtime_ns": 1_700_000_100_000_000_000,
            },
        ],
        # Deliberately conflicting fallback lists to prove recent rows are preferred.
        "created_paths": [{"path": "fallback.txt", "size": 1, "mtime_ns": 1_700_000_000_000_000_000}],
        "modified_paths": [],
        "deleted_paths": [],
        "window": {"end": "2026-02-11T12:05:00+00:00"},
    }
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "client_folder_activity",
            "instance_id": "folder_widget",
            "request_id": "req_folder_003",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is True
    render = response["data"]["render"]
    html_body = render["html"]
    assert "newest.txt" in html_body
    assert "older.txt" in html_body
    assert "fallback.txt" not in html_body


def test_handle_ipc_line_echoes_request_id() -> None:
    runtime = _make_runtime_with_plugins()
    raw_request = (
        '{"cmd":"get_widget_manifest","plugin_id":"screen_tracker",'
        '"instance_id":"screen_widget","request_id":"req_abc"}'
    )
    response = runtime._handle_ipc_line(raw_request)
    assert response["cmd"] == "get_widget_manifest"
    assert response["request_id"] == "req_abc"


def test_handle_ipc_line_omits_empty_request_id() -> None:
    runtime = _make_runtime_with_plugins()
    raw_request = (
        '{"cmd":"get_widget_manifest","plugin_id":"screen_tracker",'
        '"instance_id":"screen_widget","request_id":"  "}'
    )
    response = runtime._handle_ipc_line(raw_request)
    assert response["cmd"] == "get_widget_manifest"
    assert "request_id" not in response
