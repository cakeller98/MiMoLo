"""Agent instance and control-action orchestration helpers for Runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from mimolo.core.config import PluginConfig, save_config
from mimolo.core.errors import ConfigError

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def next_available_label(runtime: Runtime, base_label: str) -> str:
    """Generate a unique config label for a new agent instance."""
    if base_label not in runtime.config.plugins:
        return base_label
    idx = 2
    while True:
        candidate = f"{base_label}_{idx}"
        if candidate not in runtime.config.plugins:
            return candidate
        idx += 1


def persist_runtime_config(runtime: Runtime) -> tuple[bool, str]:
    """Persist in-memory runtime config if a config path is available."""
    if runtime._config_path is None:
        return False, "config_path_not_set"
    try:
        save_config(runtime.config, runtime._config_path)
        return True, "saved"
    except ConfigError as e:
        detail = f"save_failed:{e}"
        runtime.console.print(f"[red]Failed to save config: {e}[/red]")
        return False, detail


def add_agent_instance(
    runtime: Runtime,
    template_id: str,
    requested_label: str | None,
) -> tuple[bool, str, str | None]:
    """Create and start one new agent instance from template defaults."""
    templates = runtime._discover_agent_templates()
    template = templates.get(template_id)
    if template is None:
        return False, "unknown_template", None

    base_label = (requested_label or template_id).strip()
    if not base_label:
        return False, "invalid_label", None
    new_label = next_available_label(runtime, base_label)

    try:
        raw_default = template.get("default_config", {})
        plugin_cfg = PluginConfig.model_validate(raw_default)
    except ValidationError as e:
        return False, f"default_config_invalid:{e}", None

    runtime.config.plugins[new_label] = plugin_cfg
    runtime._set_agent_state(new_label, "inactive", "configured")
    saved, save_detail = persist_runtime_config(runtime)
    if not saved:
        del runtime.config.plugins[new_label]
        runtime._agent_states.pop(new_label, None)
        runtime._agent_state_details.pop(new_label, None)
        return False, save_detail, None

    started, start_detail = runtime._spawn_agent_for_label(new_label)
    if not started and start_detail != "already_running":
        return True, f"added_not_started:{start_detail}", new_label
    return True, "added", new_label


def duplicate_agent_instance(runtime: Runtime, label: str) -> tuple[bool, str, str | None]:
    """Duplicate one configured agent instance."""
    source_cfg = runtime.config.plugins.get(label)
    if source_cfg is None or source_cfg.plugin_type != "agent":
        return False, "unknown_agent", None

    new_label = next_available_label(runtime, f"{label}_copy")
    try:
        dup_cfg = PluginConfig.model_validate(source_cfg.model_dump())
    except ValidationError as e:
        return False, f"duplicate_invalid:{e}", None

    runtime.config.plugins[new_label] = dup_cfg
    runtime._set_agent_state(new_label, "inactive", f"duplicated_from:{label}")
    saved, save_detail = persist_runtime_config(runtime)
    if not saved:
        del runtime.config.plugins[new_label]
        runtime._agent_states.pop(new_label, None)
        runtime._agent_state_details.pop(new_label, None)
        return False, save_detail, None

    started, start_detail = runtime._spawn_agent_for_label(new_label)
    if not started and start_detail != "already_running":
        return True, f"duplicated_not_started:{start_detail}", new_label
    return True, "duplicated", new_label


def remove_agent_instance(runtime: Runtime, label: str) -> tuple[bool, str]:
    """Remove one configured agent instance (and stop if running)."""
    source_cfg = runtime.config.plugins.get(label)
    if source_cfg is None or source_cfg.plugin_type != "agent":
        return False, "unknown_agent"

    if label in runtime.agent_manager.agents:
        stopped, stop_detail = runtime._stop_agent_for_label(label)
        if not stopped:
            return False, f"stop_before_remove_failed:{stop_detail}"

    del runtime.config.plugins[label]
    runtime.agent_last_flush.pop(label, None)
    runtime._agent_states.pop(label, None)
    runtime._agent_state_details.pop(label, None)

    saved, save_detail = persist_runtime_config(runtime)
    if not saved:
        # Restore only if save failed.
        runtime.config.plugins[label] = source_cfg
        runtime._set_agent_state(label, "inactive", "restore_after_save_failure")
        return False, save_detail

    return True, "removed"


def update_agent_instance(
    runtime: Runtime,
    label: str,
    updates: dict[str, Any],
) -> tuple[bool, str]:
    """Update one configured agent instance and persist changes."""
    current_cfg = runtime.config.plugins.get(label)
    if current_cfg is None or current_cfg.plugin_type != "agent":
        return False, "unknown_agent"

    allowed_update_keys = {
        "enabled",
        "executable",
        "args",
        "heartbeat_interval_s",
        "agent_flush_interval_s",
        "launch_in_separate_terminal",
    }
    sanitized_updates = {k: v for k, v in updates.items() if k in allowed_update_keys}

    merged = current_cfg.model_dump()
    merged.update(sanitized_updates)

    try:
        updated_cfg = PluginConfig.model_validate(merged)
    except ValidationError as e:
        return False, f"invalid_updates:{e}"

    restart_needed = (
        current_cfg.executable != updated_cfg.executable
        or current_cfg.args != updated_cfg.args
    )
    was_running = (
        label in runtime.agent_manager.agents and runtime.agent_manager.agents[label].is_alive()
    )

    runtime.config.plugins[label] = updated_cfg
    saved, save_detail = persist_runtime_config(runtime)
    if not saved:
        runtime.config.plugins[label] = current_cfg
        return False, save_detail

    if not updated_cfg.enabled:
        if was_running:
            runtime._stop_agent_for_label(label)
        runtime._set_agent_state(label, "inactive", "disabled")
        return True, "updated_disabled"

    if was_running and restart_needed:
        restarted, restart_detail = runtime._restart_agent_for_label(label)
        if not restarted:
            return False, restart_detail
        return True, "updated_restarted"

    if not was_running:
        runtime._set_agent_state(label, "inactive", "updated")
    else:
        runtime._set_agent_state(label, "running", "updated")
    return True, "updated"


def queue_control_action(
    runtime: Runtime,
    action: str,
    label: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Queue one control action for processing on the runtime loop."""
    with runtime._control_actions_lock:
        item: dict[str, Any] = {
            "action": action,
            "label": label,
        }
        if payload:
            item["payload"] = payload
        runtime._pending_control_actions.append(item)


def drain_control_actions(runtime: Runtime) -> list[dict[str, Any]]:
    """Drain pending control actions."""
    with runtime._control_actions_lock:
        actions = list(runtime._pending_control_actions)
        runtime._pending_control_actions.clear()
    return actions


def process_control_actions(runtime: Runtime) -> None:
    """Apply queued control actions."""
    for action_item in drain_control_actions(runtime):
        action_raw = action_item.get("action")
        label_raw = action_item.get("label")
        if not isinstance(action_raw, str) or not isinstance(label_raw, str):
            continue
        action = action_raw
        label = label_raw
        payload = action_item.get("payload")
        payload_dict = payload if isinstance(payload, dict) else {}

        if action == "start_agent":
            runtime._spawn_agent_for_label(label)
        elif action == "stop_agent":
            runtime._stop_agent_for_label(label)
        elif action == "restart_agent":
            runtime._restart_agent_for_label(label)
        elif action == "add_agent_instance":
            template_id_raw = payload_dict.get("template_id")
            requested_label_raw = payload_dict.get("requested_label")
            if isinstance(template_id_raw, str):
                requested_label = (
                    str(requested_label_raw)
                    if isinstance(requested_label_raw, str)
                    else None
                )
                add_agent_instance(runtime, template_id_raw, requested_label)
        elif action == "duplicate_agent_instance":
            duplicate_agent_instance(runtime, label)
        elif action == "remove_agent_instance":
            remove_agent_instance(runtime, label)
        elif action == "update_agent_instance":
            updates = payload_dict.get("updates")
            if isinstance(updates, dict):
                update_agent_instance(runtime, label, updates)
