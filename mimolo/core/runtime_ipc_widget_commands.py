"""Widget-related IPC command handling for Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mimolo.core.protocol import CommandType, OrchestratorCommand

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


WIDGET_SPEC_PATH = "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md"


def maybe_handle_widget_command(
    runtime: Runtime,
    cmd: str,
    request: dict[str, Any],
    now: str,
) -> dict[str, Any] | None:
    """Handle widget IPC commands and return response payload when matched."""
    if cmd not in {
        "get_widget_manifest",
        "request_widget_render",
        "dispatch_widget_action",
    }:
        return None

    plugin_id_raw = request.get("plugin_id")
    plugin_id = str(plugin_id_raw).strip() if plugin_id_raw is not None else ""
    if not plugin_id:
        return {
            "ok": False,
            "cmd": cmd,
            "timestamp": now,
            "error": "missing_plugin_id",
        }

    instance_id_raw = request.get("instance_id")
    instance_id = str(instance_id_raw).strip() if instance_id_raw is not None else ""
    if not instance_id:
        return {
            "ok": False,
            "cmd": cmd,
            "timestamp": now,
            "error": "missing_instance_id",
        }

    plugin_cfg = runtime.config.plugins.get(instance_id)
    if plugin_cfg is None or plugin_cfg.plugin_type != "agent":
        return {
            "ok": False,
            "cmd": cmd,
            "timestamp": now,
            "error": f"unknown_instance:{instance_id}",
        }

    template_id = runtime._infer_template_id(instance_id, plugin_cfg)
    if template_id != plugin_id:
        return {
            "ok": False,
            "cmd": cmd,
            "timestamp": now,
            "error": f"plugin_instance_mismatch:{plugin_id}:{instance_id}",
        }

    if cmd == "dispatch_widget_action":
        return _handle_widget_dispatch_action(runtime, request, now, plugin_id, instance_id)

    if template_id == "screen_tracker":
        return _handle_screen_tracker_widget_command(runtime, cmd, request, now, plugin_id, instance_id)

    return _build_not_implemented_widget_response(cmd, request, now, plugin_id, instance_id)


def _handle_screen_tracker_widget_command(
    runtime: Runtime,
    cmd: str,
    request: dict[str, Any],
    now: str,
    plugin_id: str,
    instance_id: str,
) -> dict[str, Any]:
    if cmd == "get_widget_manifest":
        screen_response_data = runtime._build_screen_tracker_widget_manifest(instance_id)
        screen_response_data.update(
            {
                "plugin_id": plugin_id,
                "instance_id": instance_id,
                "spec": WIDGET_SPEC_PATH,
            }
        )
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": screen_response_data,
        }

    if cmd == "request_widget_render":
        request_id_raw = request.get("request_id")
        request_id = (
            str(request_id_raw).strip()
            if request_id_raw is not None and str(request_id_raw).strip()
            else None
        )
        mode_raw = request.get("mode")
        mode = (
            str(mode_raw).strip()
            if mode_raw is not None and str(mode_raw).strip()
            else "html_fragment_v1"
        )
        screen_response_data = runtime._build_screen_tracker_widget_render(
            instance_id, request_id, mode
        )
        screen_response_data.update(
            {
                "plugin_id": plugin_id,
                "instance_id": instance_id,
                "spec": WIDGET_SPEC_PATH,
            }
        )
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": screen_response_data,
        }

    return _build_not_implemented_widget_response(cmd, request, now, plugin_id, instance_id)


def _handle_widget_dispatch_action(
    runtime: Runtime,
    request: dict[str, Any],
    now: str,
    plugin_id: str,
    instance_id: str,
) -> dict[str, Any]:
    action_raw = request.get("action")
    action = (
        str(action_raw).strip()
        if action_raw is not None and str(action_raw).strip()
        else "refresh"
    )
    if action != "refresh":
        return {
            "ok": True,
            "cmd": "dispatch_widget_action",
            "timestamp": now,
            "data": {
                "accepted": False,
                "status": "unsupported_action",
                "plugin_id": plugin_id,
                "instance_id": instance_id,
                "action": action,
                "supported_actions": ["refresh"],
                "spec": WIDGET_SPEC_PATH,
            },
        }

    handle = runtime.agent_manager.agents.get(instance_id)
    if handle is None:
        return {
            "ok": True,
            "cmd": "dispatch_widget_action",
            "timestamp": now,
            "data": {
                "accepted": True,
                "status": "ok",
                "detail": "agent_not_running_noop",
                "plugin_id": plugin_id,
                "instance_id": instance_id,
                "action": action,
                "supported_actions": ["refresh"],
                "spec": WIDGET_SPEC_PATH,
            },
        }

    flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
    try:
        sent = handle.send_command(flush_cmd)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "cmd": "dispatch_widget_action",
            "timestamp": now,
            "error": "dispatch_failed",
            "data": {
                "accepted": False,
                "status": "dispatch_failed",
                "detail": str(exc),
                "plugin_id": plugin_id,
                "instance_id": instance_id,
                "action": action,
                "supported_actions": ["refresh"],
                "spec": WIDGET_SPEC_PATH,
            },
        }

    if sent:
        runtime.agent_last_flush[instance_id] = datetime.now(UTC)
    return {
        "ok": True,
        "cmd": "dispatch_widget_action",
        "timestamp": now,
        "data": {
            "accepted": sent,
            "status": "ok" if sent else "dispatch_rejected",
            "plugin_id": plugin_id,
            "instance_id": instance_id,
            "action": action,
            "supported_actions": ["refresh"],
            "spec": WIDGET_SPEC_PATH,
        },
    }


def _build_not_implemented_widget_response(
    cmd: str,
    request: dict[str, Any],
    now: str,
    plugin_id: str,
    instance_id: str,
) -> dict[str, Any]:
    response_data: dict[str, Any] = {
        "accepted": False,
        "status": "not_implemented_yet",
        "plugin_id": plugin_id,
        "instance_id": instance_id,
        "spec": WIDGET_SPEC_PATH,
    }

    if cmd == "get_widget_manifest":
        response_data["widget"] = {
            "supports_render": False,
            "default_aspect_ratio": "16:9",
            "min_refresh_ms": 1000,
            "supported_actions": [],
            "content_modes": ["html_fragment_v1"],
        }
    elif cmd == "request_widget_render":
        request_id_raw = request.get("request_id")
        request_id = (
            str(request_id_raw).strip()
            if request_id_raw is not None and str(request_id_raw).strip()
            else None
        )
        mode_raw = request.get("mode")
        mode = (
            str(mode_raw).strip()
            if mode_raw is not None and str(mode_raw).strip()
            else "html_fragment_v1"
        )
        response_data["request_id"] = request_id
        response_data["render"] = {
            "mode": mode,
            "html": "",
            "ttl_ms": 0,
            "state_token": None,
            "warnings": ["not_implemented_yet"],
        }
    elif cmd == "dispatch_widget_action":
        action_raw = request.get("action")
        stub_action: str | None = (
            str(action_raw).strip()
            if action_raw is not None and str(action_raw).strip()
            else None
        )
        response_data["action"] = stub_action

    return {
        "ok": False,
        "cmd": cmd,
        "timestamp": now,
        "error": "not_implemented_yet",
        "data": response_data,
    }
