"""Agent lifecycle orchestration helpers for Runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def start_agents(runtime: Runtime) -> None:
    """Spawn Agent plugins from config."""
    if runtime._agents_started:
        return
    runtime._agents_started = True

    for label, plugin_config in runtime.config.plugins.items():
        if not plugin_config.enabled:
            continue
        if not plugin_config.executable:
            runtime._set_agent_state(label, "error", "missing_executable")
            continue
        spawn_agent_for_label(runtime, label)


def spawn_agent_for_label(runtime: Runtime, label: str) -> tuple[bool, str]:
    """Spawn one configured agent by label."""
    plugin_config = runtime.config.plugins.get(label)
    if (
        plugin_config is None
        or not plugin_config.enabled
        or plugin_config.plugin_type != "agent"
    ):
        runtime._set_agent_state(label, "error", "not_configured")
        return False, "not_configured"

    if not plugin_config.executable:
        runtime._set_agent_state(label, "error", "missing_executable")
        return False, "missing_executable"

    existing = runtime.agent_manager.agents.get(label)
    if existing and existing.is_alive():
        runtime._set_agent_state(label, "running", "already_running")
        return False, "already_running"

    if existing and not existing.is_alive():
        del runtime.agent_manager.agents[label]

    try:
        handle = runtime.agent_manager.spawn_agent(label, plugin_config)
        if getattr(plugin_config, "launch_in_separate_terminal", False) and handle.stderr_log:
            from mimolo.core.agent_debug import open_tail_window

            open_tail_window(handle.stderr_log)
        runtime._set_agent_state(label, "running", "spawned")
        runtime.console.print(f"[green]Spawned Agent: {label}[/green]")
        return True, "started"
    except (FileNotFoundError, OSError, PermissionError, RuntimeError, ValueError) as e:
        detail = f"spawn_failed:{e}"
        runtime._set_agent_state(label, "error", detail)
        runtime.console.print(f"[red]Failed to spawn agent {label}: {e}[/red]")
        return False, detail


def stop_agent_for_label(runtime: Runtime, label: str) -> tuple[bool, str]:
    """Stop one running agent by label."""
    handle = runtime.agent_manager.agents.get(label)
    if handle is None:
        runtime._set_agent_state(label, "inactive", "not_running")
        return False, "not_running"

    runtime._set_agent_state(label, "shutting-down", "stop_requested")

    try:
        handle.shutdown()
    except (OSError, RuntimeError, ValueError) as e:
        detail = f"stop_failed:{e}"
        runtime._set_agent_state(label, "error", detail)
        runtime.console.print(f"[red]Failed stopping agent {label}: {e}[/red]")
        return False, detail

    runtime.agent_manager.agents.pop(label, None)
    runtime.agent_last_flush.pop(label, None)
    runtime._set_agent_state(label, "inactive", "stopped")
    return True, "stopped"


def restart_agent_for_label(runtime: Runtime, label: str) -> tuple[bool, str]:
    """Restart one configured agent by label."""
    if label in runtime.agent_manager.agents:
        stopped, stop_detail = stop_agent_for_label(runtime, label)
        if not stopped:
            return False, f"restart_stop_failed:{stop_detail}"

    started, start_detail = spawn_agent_for_label(runtime, label)
    if not started:
        return False, f"restart_start_failed:{start_detail}"
    return True, "restarted"
