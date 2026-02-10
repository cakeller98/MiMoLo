"""Agent registry and template/instance snapshot helpers for Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from mimolo.core.config import PluginConfig

if TYPE_CHECKING:
    from mimolo.core.runtime import AgentLifecycleState, Runtime


def snapshot_running_agents(runtime: Runtime) -> list[str]:
    """Safely capture currently running agent labels."""
    try:
        running_labels = [
            label
            for label, handle in runtime.agent_manager.agents.items()
            if handle.is_alive()
        ]
        return sorted(running_labels)
    except RuntimeError:
        # RuntimeError: dict can mutate while iterating across threads.
        return []


def set_agent_state(
    runtime: Runtime,
    label: str,
    state: AgentLifecycleState,
    detail: str,
) -> None:
    """Set lifecycle state for one agent."""
    runtime._agent_states[label] = state
    runtime._agent_state_details[label] = detail


def snapshot_agent_states(runtime: Runtime) -> dict[str, dict[str, str]]:
    """Return lifecycle state snapshot for enabled configured agents."""
    snapshot: dict[str, dict[str, str]] = {}
    for label, plugin_cfg in runtime.config.plugins.items():
        if not plugin_cfg.enabled or plugin_cfg.plugin_type != "agent":
            continue
        snapshot[label] = {
            "state": runtime._agent_states.get(label, "inactive"),
            "detail": runtime._agent_state_details.get(label, "configured"),
        }
    return snapshot


def infer_template_id(runtime: Runtime, label: str, plugin_cfg: PluginConfig) -> str:
    """Infer template id from args path, falling back to label."""
    local_agents_root = (Path(__file__).parent.parent / "agents").resolve()
    installed_agents_root = (runtime._plugin_store.plugins_root / "agents").resolve()
    for arg in plugin_cfg.args:
        if not arg.endswith(".py"):
            continue

        script_path = Path(arg)
        if script_path.is_absolute():
            try:
                resolved = script_path.resolve()
            except OSError:
                resolved = script_path
            for root in (installed_agents_root, local_agents_root):
                try:
                    relative = resolved.relative_to(root)
                except ValueError:
                    continue
                if relative.parts:
                    candidate = relative.parts[0].strip()
                    if candidate:
                        return candidate

        normalized = arg.replace("\\", "/")
        if "/" not in normalized:
            continue
        head = normalized.split("/", 1)[0].strip()
        if head:
            return head
    return label


def discover_agent_templates(runtime: Runtime) -> dict[str, dict[str, Any]]:
    """Discover agent templates from local agents directory."""
    templates: dict[str, dict[str, Any]] = {}
    agents_root = Path(__file__).parent.parent / "agents"

    if agents_root.exists():
        for entry in sorted(agents_root.iterdir(), key=lambda p: p.name):
            if not entry.is_dir():
                continue
            if entry.name.startswith(".") or entry.name in {"repository", "__pycache__"}:
                continue
            default_script = entry / f"{entry.name}.py"
            if default_script.exists():
                script_path = default_script
            else:
                candidates = sorted(
                    [p for p in entry.glob("*.py") if p.name != "__init__.py"],
                    key=lambda p: p.name,
                )
                if not candidates:
                    continue
                script_path = candidates[0]

            script_rel = f"{entry.name}/{script_path.name}"
            templates[entry.name] = {
                "template_id": entry.name,
                "script": script_rel,
                "default_config": {
                    "enabled": True,
                    "plugin_type": "agent",
                    "executable": "poetry",
                    "args": ["run", "python", script_rel],
                    "heartbeat_interval_s": 15.0,
                    "agent_flush_interval_s": 60.0,
                    "launch_in_separate_terminal": False,
                },
            }

    # Installed plugins in app-data are source-of-truth for deployed artifacts.
    try:
        installed_agents = runtime._plugin_store.list_installed("agents")
    except ValueError:
        installed_agents = []
    installed_agents_root = (runtime._plugin_store.plugins_root / "agents").resolve()
    for installed_entry in installed_agents:
        plugin_id_raw = installed_entry.get("plugin_id")
        plugin_id = (
            str(plugin_id_raw).strip()
            if plugin_id_raw is not None and str(plugin_id_raw).strip()
            else ""
        )
        latest_path_raw = installed_entry.get("latest_path")
        latest_path_text = (
            str(latest_path_raw).strip()
            if latest_path_raw is not None and str(latest_path_raw).strip()
            else ""
        )
        latest_entry_raw = installed_entry.get("latest_entry")
        latest_entry = (
            str(latest_entry_raw).strip()
            if latest_entry_raw is not None and str(latest_entry_raw).strip()
            else ""
        )
        if not plugin_id or not latest_path_text or not latest_entry:
            continue

        script_path = (Path(latest_path_text) / latest_entry).resolve()
        if not script_path.exists() or not script_path.is_file():
            continue
        try:
            script_path.relative_to(installed_agents_root)
        except ValueError:
            continue

        script_abs = str(script_path)
        templates[plugin_id] = {
            "template_id": plugin_id,
            "script": script_abs,
            "default_config": {
                "enabled": True,
                "plugin_type": "agent",
                "executable": "poetry",
                "args": ["run", "python", script_abs],
                "heartbeat_interval_s": 15.0,
                "agent_flush_interval_s": 60.0,
                "launch_in_separate_terminal": False,
            },
        }

    # Ensure all currently-configured templates remain selectable even if
    # their source directory is moved/renamed.
    for label, plugin_cfg in runtime.config.plugins.items():
        if not plugin_cfg.enabled or plugin_cfg.plugin_type != "agent":
            continue
        template_id = infer_template_id(runtime, label, plugin_cfg)
        if template_id in templates:
            continue
        templates[template_id] = {
            "template_id": template_id,
            "script": plugin_cfg.args[-1] if plugin_cfg.args else "",
            "default_config": plugin_cfg.model_dump(),
        }

    return templates


def effective_interval_s(runtime: Runtime, requested_interval_s: float) -> float:
    """Apply global chatter floor to an agent-provided interval."""
    return max(runtime.config.monitor.poll_tick_s, requested_interval_s)


def effective_heartbeat_interval_s(runtime: Runtime, plugin_cfg: PluginConfig) -> float:
    """Effective heartbeat cadence after global floor enforcement."""
    return effective_interval_s(runtime, plugin_cfg.heartbeat_interval_s)


def effective_agent_flush_interval_s(runtime: Runtime, plugin_cfg: PluginConfig) -> float:
    """Effective periodic flush cadence after global floor enforcement."""
    return effective_interval_s(runtime, plugin_cfg.agent_flush_interval_s)


def snapshot_agent_instances(runtime: Runtime) -> dict[str, dict[str, Any]]:
    """Return configured agent instances with state and editable config."""
    instances: dict[str, dict[str, Any]] = {}
    for label, plugin_cfg in runtime.config.plugins.items():
        config_data = plugin_cfg.model_dump()
        if plugin_cfg.plugin_type == "agent":
            config_data["effective_heartbeat_interval_s"] = (
                effective_heartbeat_interval_s(runtime, plugin_cfg)
            )
            config_data["effective_agent_flush_interval_s"] = (
                effective_agent_flush_interval_s(runtime, plugin_cfg)
            )
        instances[label] = {
            "label": label,
            "state": runtime._agent_states.get(label, "inactive"),
            "detail": runtime._agent_state_details.get(label, "configured"),
            "template_id": infer_template_id(runtime, label, plugin_cfg),
            "config": config_data,
        }
    return instances
