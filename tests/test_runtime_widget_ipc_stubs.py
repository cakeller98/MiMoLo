from mimolo.core.config import Config
from mimolo.core.runtime import Runtime


def _make_runtime() -> Runtime:
    return Runtime(Config())


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


def test_get_widget_manifest_stub_payload() -> None:
    runtime = _make_runtime()
    response = runtime._build_ipc_response(
        {
            "cmd": "get_widget_manifest",
            "plugin_id": "screen_tracker",
            "instance_id": "inst_123",
        }
    )
    assert response["ok"] is False
    assert response["error"] == "not_implemented_yet"
    data = response["data"]
    assert data["accepted"] is False
    assert data["status"] == "not_implemented_yet"
    assert data["plugin_id"] == "screen_tracker"
    assert data["instance_id"] == "inst_123"
    assert data["spec"] == "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md"
    widget = data["widget"]
    assert widget["supports_render"] is False
    assert widget["default_aspect_ratio"] == "16:9"
    assert widget["min_refresh_ms"] == 1000
    assert widget["supported_actions"] == []
    assert widget["content_modes"] == ["html_fragment_v1"]


def test_request_widget_render_stub_payload() -> None:
    runtime = _make_runtime()
    response = runtime._build_ipc_response(
        {
            "cmd": "request_widget_render",
            "plugin_id": "screen_tracker",
            "instance_id": "inst_123",
            "request_id": "req_001",
            "mode": "html_fragment_v1",
        }
    )
    assert response["ok"] is False
    assert response["error"] == "not_implemented_yet"
    data = response["data"]
    assert data["request_id"] == "req_001"
    render = data["render"]
    assert render["mode"] == "html_fragment_v1"
    assert render["html"] == ""
    assert render["ttl_ms"] == 0
    assert render["state_token"] is None
    assert render["warnings"] == ["not_implemented_yet"]


def test_dispatch_widget_action_stub_payload() -> None:
    runtime = _make_runtime()
    response = runtime._build_ipc_response(
        {
            "cmd": "dispatch_widget_action",
            "plugin_id": "client_folder_activity",
            "instance_id": "inst_acme",
            "action": "set_filter",
        }
    )
    assert response["ok"] is False
    assert response["error"] == "not_implemented_yet"
    data = response["data"]
    assert data["plugin_id"] == "client_folder_activity"
    assert data["instance_id"] == "inst_acme"
    assert data["action"] == "set_filter"


def test_handle_ipc_line_echoes_request_id() -> None:
    runtime = _make_runtime()
    raw_request = (
        '{"cmd":"get_widget_manifest","plugin_id":"screen_tracker",'
        '"instance_id":"inst_001","request_id":"req_abc"}'
    )
    response = runtime._handle_ipc_line(raw_request)
    assert response["cmd"] == "get_widget_manifest"
    assert response["request_id"] == "req_abc"


def test_handle_ipc_line_omits_empty_request_id() -> None:
    runtime = _make_runtime()
    raw_request = (
        '{"cmd":"get_widget_manifest","plugin_id":"screen_tracker",'
        '"instance_id":"inst_001","request_id":"  "}'
    )
    response = runtime._handle_ipc_line(raw_request)
    assert response["cmd"] == "get_widget_manifest"
    assert "request_id" not in response
