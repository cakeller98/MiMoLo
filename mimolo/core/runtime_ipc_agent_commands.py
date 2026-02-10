"""Agent lifecycle and instance IPC command handling for Runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def maybe_handle_agent_control_command(
    runtime: Runtime,
    cmd: str,
    request: dict[str, Any],
    now: str,
) -> dict[str, Any] | None:
    """Handle agent lifecycle/instance control commands when matched."""
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

    return None
