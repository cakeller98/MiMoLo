"""IPC command handlers for Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    if cmd == "list_installed_plugins":
        plugin_class_raw = request.get("plugin_class")
        plugin_class = (
            str(plugin_class_raw).strip().lower()
            if plugin_class_raw is not None and str(plugin_class_raw).strip()
            else "all"
        )
        try:
            installed = runtime._plugin_store.list_installed(plugin_class)
        except ValueError as e:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": str(e),
            }
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "plugin_class": plugin_class,
                "installed_plugins": installed,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

    if cmd == "inspect_plugin_archive":
        zip_path_raw = request.get("zip_path")
        zip_path = (
            str(zip_path_raw).strip()
            if zip_path_raw is not None and str(zip_path_raw).strip()
            else ""
        )
        if not zip_path:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_zip_path",
            }

        ok, detail, payload = runtime._plugin_store.inspect_plugin_archive(
            Path(zip_path)
        )
        if not ok:
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
            "data": {
                "accepted": True,
                "inspection": payload,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

    if cmd in {"install_plugin", "upgrade_plugin"}:
        zip_path_raw = request.get("zip_path")
        zip_path = (
            str(zip_path_raw).strip()
            if zip_path_raw is not None and str(zip_path_raw).strip()
            else ""
        )
        if not zip_path:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_zip_path",
            }

        plugin_class_raw = request.get("plugin_class")
        plugin_class = (
            str(plugin_class_raw).strip().lower()
            if plugin_class_raw is not None and str(plugin_class_raw).strip()
            else "agents"
        )

        ok, detail, payload = runtime._plugin_store.install_plugin_archive(
            Path(zip_path),
            plugin_class,
            require_newer=(cmd == "upgrade_plugin"),
        )
        if not ok:
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
            "data": {
                "accepted": True,
                "install_result": payload,
                "source_of_truth": "filesystem",
                "registry_role": "cache_only",
            },
        }

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

    if cmd in {"start_agent", "stop_agent", "restart_agent"}:
        label_raw = request.get("label")
        label = str(label_raw).strip() if label_raw is not None else ""
        if not label:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_label",
            }

        plugin_cfg = runtime.config.plugins.get(label)
        if (
            plugin_cfg is None
            or not plugin_cfg.enabled
            or plugin_cfg.plugin_type != "agent"
        ):
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": f"unknown_agent:{label}",
            }

        runtime._queue_control_action(cmd, label)
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "label": label,
            },
        }

    if cmd == "add_agent_instance":
        template_id_raw = request.get("template_id")
        template_id = str(template_id_raw).strip() if template_id_raw is not None else ""
        if not template_id:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_template_id",
            }

        requested_label_raw = request.get("requested_label")
        requested_label = (
            str(requested_label_raw).strip()
            if isinstance(requested_label_raw, str) and requested_label_raw.strip()
            else None
        )

        # Precompute final label for immediate UI feedback.
        final_label = runtime._next_available_label(requested_label or template_id)
        runtime._queue_control_action(
            "add_agent_instance",
            final_label,
            {
                "template_id": template_id,
                "requested_label": requested_label,
            },
        )
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "label": final_label,
                "template_id": template_id,
            },
        }

    if cmd == "duplicate_agent_instance":
        label_raw = request.get("label")
        label = str(label_raw).strip() if label_raw is not None else ""
        if not label:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_label",
            }
        if label not in runtime.config.plugins:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": f"unknown_agent:{label}",
            }
        final_label = runtime._next_available_label(f"{label}_copy")
        runtime._queue_control_action("duplicate_agent_instance", label)
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "label": final_label,
                "source_label": label,
            },
        }

    if cmd == "remove_agent_instance":
        label_raw = request.get("label")
        label = str(label_raw).strip() if label_raw is not None else ""
        if not label:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_label",
            }
        if label not in runtime.config.plugins:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": f"unknown_agent:{label}",
            }
        runtime._queue_control_action("remove_agent_instance", label)
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "label": label,
            },
        }

    if cmd == "update_agent_instance":
        label_raw = request.get("label")
        label = str(label_raw).strip() if label_raw is not None else ""
        updates_raw = request.get("updates")
        updates = updates_raw if isinstance(updates_raw, dict) else None
        if not label:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_label",
            }
        if updates is None:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_updates",
            }
        if label not in runtime.config.plugins:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": f"unknown_agent:{label}",
            }
        runtime._queue_control_action(
            "update_agent_instance",
            label,
            {"updates": updates},
        )
        return {
            "ok": True,
            "cmd": cmd,
            "timestamp": now,
            "data": {
                "accepted": True,
                "label": label,
            },
        }

    if cmd in {
        "get_widget_manifest",
        "request_widget_render",
        "dispatch_widget_action",
    }:
        plugin_id_raw = request.get("plugin_id")
        plugin_id = (
            str(plugin_id_raw).strip() if plugin_id_raw is not None else ""
        )
        if not plugin_id:
            return {
                "ok": False,
                "cmd": cmd,
                "timestamp": now,
                "error": "missing_plugin_id",
            }

        instance_id_raw = request.get("instance_id")
        instance_id = (
            str(instance_id_raw).strip()
            if instance_id_raw is not None
            else ""
        )
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

        if template_id == "screen_tracker":
            if cmd == "get_widget_manifest":
                screen_response_data = runtime._build_screen_tracker_widget_manifest(
                    instance_id
                )
                screen_response_data.update(
                    {
                        "plugin_id": plugin_id,
                        "instance_id": instance_id,
                        "spec": "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md",
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
                        "spec": "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md",
                    }
                )
                return {
                    "ok": True,
                    "cmd": cmd,
                    "timestamp": now,
                    "data": screen_response_data,
                }
            if cmd == "dispatch_widget_action":
                action_raw = request.get("action")
                dispatch_action: str | None = (
                    str(action_raw).strip()
                    if action_raw is not None and str(action_raw).strip()
                    else None
                )
                return {
                    "ok": True,
                    "cmd": cmd,
                    "timestamp": now,
                    "data": {
                        "accepted": dispatch_action == "refresh",
                        "status": "ok"
                        if dispatch_action == "refresh"
                        else "unsupported_action",
                        "plugin_id": plugin_id,
                        "instance_id": instance_id,
                        "action": dispatch_action,
                        "supported_actions": ["refresh"],
                        "spec": "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md",
                    },
                }

        response_data: dict[str, Any] = {
            "accepted": False,
            "status": "not_implemented_yet",
            "plugin_id": plugin_id,
            "instance_id": instance_id,
            "spec": "developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md",
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

    return {
        "ok": False,
        "cmd": cmd,
        "timestamp": now,
        "error": f"unknown_command:{cmd}",
    }
