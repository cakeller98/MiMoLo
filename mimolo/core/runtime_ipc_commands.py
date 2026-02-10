"""IPC command handlers for Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mimolo.core.runtime_ipc_agent_commands import maybe_handle_agent_control_command
from mimolo.core.runtime_ipc_plugin_commands import maybe_handle_plugin_store_command
from mimolo.core.runtime_ipc_widget_commands import maybe_handle_widget_command

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime

def build_ipc_response(runtime: Runtime, request: dict[str, Any]) -> dict[str, Any]:
    """Handle one IPC command and return response payload."""
    cmd_raw = request.get("cmd")
    cmd = str(cmd_raw) if cmd_raw is not None else ""
    now = datetime.now(UTC).isoformat()

    if cmd == "ping":
        return {"ok": True, "cmd": "ping", "timestamp": now, "data": {"pong": True}}

    if cmd == "control_orchestrator":
        action_raw = request.get("action")
        action = (
            str(action_raw).strip().lower()
            if action_raw is not None and str(action_raw).strip()
            else "status"
        )
        if action not in {"status", "stop"}:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "invalid_action",
                "data": {
                    "allowed_actions": ["status", "stop"],
                    "orchestrator": runtime._snapshot_orchestrator_state(),
                },
            }

        if action == "status":
            return {
                "ok": True,
                "cmd": cmd,
                "timestamp": now,
                "data": {
                    "accepted": True,
                    "action": "status",
                    "status": "ok",
                    "orchestrator": runtime._snapshot_orchestrator_state(),
                },
            }

        if runtime._running:
            runtime._running = False
            stop_status = "stop_requested"
        else:
            stop_status = "already_stopped"
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "action": "stop",
                "status": stop_status,
                "orchestrator": runtime._snapshot_orchestrator_state(),
            },
        }

    if cmd == "get_registered_plugins":
        registered_plugins = sorted(
            [label for label, plugin_cfg in runtime.config.plugins.items() if plugin_cfg.enabled]
        )
        return {
            "ok": True,
            "cmd": "get_registered_plugins",
            "timestamp": now,
            "data": {
                "registered_plugins": registered_plugins,
                "running_agents": runtime._snapshot_running_agents(),
                "agent_states": runtime._snapshot_agent_states(),
            },
        }

    if cmd == "list_agent_templates":
        return {
            "ok": True,
            "cmd": "list_agent_templates",
            "timestamp": now,
            "data": {
                "templates": runtime._discover_agent_templates(),
            },
        }

    plugin_store_response = maybe_handle_plugin_store_command(runtime, cmd, request, now)
    if plugin_store_response is not None:
        return plugin_store_response

    if cmd == "get_agent_instances":
        return {
            "ok": True,
            "cmd": "get_agent_instances",
            "timestamp": now,
            "data": {
                "instances": runtime._snapshot_agent_instances(),
            },
        }

    if cmd == "get_monitor_settings":
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": runtime._snapshot_monitor_settings(),
        }

    if cmd == "update_monitor_settings":
        updates_raw = request.get("updates")
        updates = updates_raw if isinstance(updates_raw, dict) else None
        if updates is None:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_updates",
            }

        updated, detail, payload = runtime._update_monitor_settings(updates)
        if not updated:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": detail,
                "data": payload,
            }
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": payload,
        }

    if cmd == "get_agent_states":
        return {
            "ok": True,
            "cmd": "get_agent_states",
            "timestamp": now,
            "data": {
                "agent_states": runtime._snapshot_agent_states(),
                "running_agents": runtime._snapshot_running_agents(),
                "instances": runtime._snapshot_agent_instances(),
            },
        }

    agent_control_response = maybe_handle_agent_control_command(runtime, cmd, request, now)
    if agent_control_response is not None:
        return agent_control_response

    widget_response = maybe_handle_widget_command(runtime, cmd, request, now)
    if widget_response is not None:
        return widget_response

    return {
        "ok": False,
        "cmd": cmd,
        "timestamp": now,
        "error": f"unknown_command:{cmd}",
    }
