"""Runtime orchestrator for MiMoLo.

The orchestrator:
- Loads configuration
- Spawns and manages Agent processes
- Runs main event loop
- Handles agent JLP messages (heartbeats, summaries, logs)
- Sends flush commands to agents
- Writes output via sinks
"""

from __future__ import annotations

import os
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from rich.console import Console

from mimolo.core.config import Config, PluginConfig, save_config
from mimolo.core.cooldown import CooldownTimer
from mimolo.core.event import Event
from mimolo.core.plugin_store import PluginStore
from mimolo.core.runtime_agent_events import (
    coerce_timestamp,
    handle_agent_log,
    handle_agent_summary,
    handle_heartbeat,
)
from mimolo.core.runtime_ipc_commands import build_ipc_response
from mimolo.core.runtime_ipc_server import (
    handle_ipc_line,
    ipc_server_loop,
    send_ipc_response,
    serve_ipc_client_thread,
    serve_ipc_connection,
)
from mimolo.core.runtime_monitor_settings import update_monitor_settings
from mimolo.core.runtime_shutdown import close_segment, flush_all_agents, shutdown_runtime
from mimolo.core.runtime_widget_support import (
    build_screen_tracker_widget_manifest,
    build_screen_tracker_widget_render,
    resolve_screen_tracker_thumbnail,
    screen_tracker_thumbnail_data_uri,
)
from mimolo.core.sink import ConsoleSink, create_sink

AgentLifecycleState = Literal["running", "shutting-down", "inactive", "error"]


class Runtime:
    """Main orchestrator for MiMoLo framework."""

    def __init__(
        self,
        config: Config,
        console: Console | None = None,
        config_path: Path | None = None,
    ) -> None:
        """Initialize runtime.

        Args:
            config: Configuration object.
            console: Optional rich console for output.
            config_path: Optional path used to persist config mutations.
        """
        self.config = config
        self.console = console or Console()
        self._config_path = config_path

        # Core components
        self.cooldown = CooldownTimer(config.monitor.cooldown_seconds)

        # Sinks
        log_dir = Path(config.monitor.log_dir)
        log_format = cast(Literal["jsonl", "yaml", "md"], config.monitor.log_format)
        self.file_sink = create_sink(log_format, log_dir)
        self.console_sink = ConsoleSink(config.monitor.console_verbosity)

        # Runtime state
        self._running = False
        self._tick_count = 0
        self._shutting_down = False

        # Agent support
        from mimolo.core.agent_process import AgentProcessManager

        self.agent_manager = AgentProcessManager(config)
        self.agent_last_flush: dict[str, datetime] = {}  # Track last flush time per agent
        self._agents_started = False
        self._shutdown_deadlines: dict[str, float] = {}
        self._shutdown_phase: dict[str, str] = {}
        self._agent_states: dict[str, AgentLifecycleState] = {}
        self._agent_state_details: dict[str, str] = {}
        self._pending_control_actions: list[dict[str, Any]] = []
        self._control_actions_lock = threading.Lock()

        for label, plugin_cfg in self.config.plugins.items():
            if plugin_cfg.enabled and plugin_cfg.plugin_type == "agent":
                self._set_agent_state(label, "inactive", "configured")

        # IPC server support for Control prototype
        self._ipc_socket_path: str | None = os.environ.get("MIMOLO_IPC_PATH")
        self._ipc_stop_event = threading.Event()
        self._ipc_thread: threading.Thread | None = None
        self._ipc_server_socket: socket.socket | None = None
        self._plugin_store = PluginStore()

    def _start_agents(self) -> None:
        """Spawn Agent plugins from config."""
        if self._agents_started:
            return
        self._agents_started = True

        for label, plugin_config in self.config.plugins.items():
            if not plugin_config.enabled:
                continue
            if not plugin_config.executable:
                self._set_agent_state(label, "error", "missing_executable")
                continue
            self._spawn_agent_for_label(label)

    def run(self, max_iterations: int | None = None) -> None:
        """Run the main event loop.

        Args:
            max_iterations: Optional maximum iterations (for testing/dry-run).
        """
        self._running = True
        self._start_ipc_server()
        self._start_agents()
        self.console.print("[bold green]MiMoLo starting...[/bold green]")
        self.console.print(f"Cooldown: {self.config.monitor.cooldown_seconds}s")
        self.console.print(f"Poll tick: {self.config.monitor.poll_tick_s}s")

        agent_count = len(self.agent_manager.agents)
        self.console.print(f"Agents: {agent_count}")
        self.console.print()

        if agent_count == 0:
            self.console.print("[yellow]No Agents configured. Nothing to monitor.[/yellow]")
            return

        try:
            while self._running:
                self._tick()

                if max_iterations is not None:
                    max_iterations -= 1
                    if max_iterations <= 0:
                        break

                # Sleep for poll tick duration
                time.sleep(self.config.monitor.poll_tick_s)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            self._shutdown()

    def _debug(self, message: str) -> None:
        """Print a debug-only message to the console."""
        if self.config.monitor.console_verbosity == "debug":
            self.console.print(message)

    def _start_ipc_server(self) -> None:
        """Start background IPC server for Control commands."""
        if not self._ipc_socket_path:
            self._debug("[dim]IPC disabled (MIMOLO_IPC_PATH not set).[/dim]")
            return

        if self._ipc_thread and self._ipc_thread.is_alive():
            return

        self._ipc_stop_event.clear()
        self._ipc_thread = threading.Thread(
            target=self._ipc_server_loop,
            name="mimolo-ipc-server",
            daemon=True,
        )
        self._ipc_thread.start()

    def _stop_ipc_server(self) -> None:
        """Stop IPC server thread and clean up socket file."""
        self._ipc_stop_event.set()

        if self._ipc_server_socket is not None:
            try:
                self._ipc_server_socket.close()
            except OSError:
                # OSError: server socket may already be closed by worker thread.
                pass

        if self._ipc_thread is not None:
            self._ipc_thread.join(timeout=1.0)
            self._ipc_thread = None

        self._cleanup_ipc_socket_file()

    def _cleanup_ipc_socket_file(self) -> None:
        """Remove IPC socket file if it exists."""
        if not self._ipc_socket_path:
            return
        try:
            os.unlink(self._ipc_socket_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            # OSError: filesystem cleanup can fail on shutdown races.
            self._debug(f"[yellow]IPC socket cleanup failed: {e}[/yellow]")

    def _snapshot_running_agents(self) -> list[str]:
        """Safely capture currently running agent labels."""
        try:
            running_labels = [
                label
                for label, handle in self.agent_manager.agents.items()
                if handle.is_alive()
            ]
            return sorted(running_labels)
        except RuntimeError:
            # RuntimeError: dict can mutate while iterating across threads.
            return []

    def _set_agent_state(
        self, label: str, state: AgentLifecycleState, detail: str
    ) -> None:
        """Set lifecycle state for one agent."""
        self._agent_states[label] = state
        self._agent_state_details[label] = detail

    def _snapshot_agent_states(self) -> dict[str, dict[str, str]]:
        """Return lifecycle state snapshot for enabled configured agents."""
        snapshot: dict[str, dict[str, str]] = {}
        for label, plugin_cfg in self.config.plugins.items():
            if not plugin_cfg.enabled or plugin_cfg.plugin_type != "agent":
                continue
            snapshot[label] = {
                "state": self._agent_states.get(label, "inactive"),
                "detail": self._agent_state_details.get(label, "configured"),
            }
        return snapshot

    def _infer_template_id(self, label: str, plugin_cfg: PluginConfig) -> str:
        """Infer template id from args path, falling back to label."""
        local_agents_root = (Path(__file__).parent.parent / "agents").resolve()
        installed_agents_root = (self._plugin_store.plugins_root / "agents").resolve()
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

    def _discover_agent_templates(self) -> dict[str, dict[str, Any]]:
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
            installed_agents = self._plugin_store.list_installed("agents")
        except ValueError:
            installed_agents = []
        installed_agents_root = (self._plugin_store.plugins_root / "agents").resolve()
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
        for label, plugin_cfg in self.config.plugins.items():
            if not plugin_cfg.enabled or plugin_cfg.plugin_type != "agent":
                continue
            template_id = self._infer_template_id(label, plugin_cfg)
            if template_id in templates:
                continue
            templates[template_id] = {
                "template_id": template_id,
                "script": plugin_cfg.args[-1] if plugin_cfg.args else "",
                "default_config": plugin_cfg.model_dump(),
            }

        return templates

    def _snapshot_agent_instances(self) -> dict[str, dict[str, Any]]:
        """Return configured agent instances with state and editable config."""
        instances: dict[str, dict[str, Any]] = {}
        for label, plugin_cfg in self.config.plugins.items():
            config_data = plugin_cfg.model_dump()
            if plugin_cfg.plugin_type == "agent":
                config_data["effective_heartbeat_interval_s"] = (
                    self._effective_heartbeat_interval_s(plugin_cfg)
                )
                config_data["effective_agent_flush_interval_s"] = (
                    self._effective_agent_flush_interval_s(plugin_cfg)
                )
            instances[label] = {
                "label": label,
                "state": self._agent_states.get(label, "inactive"),
                "detail": self._agent_state_details.get(label, "configured"),
                "template_id": self._infer_template_id(label, plugin_cfg),
                "config": config_data,
            }
        return instances

    def _effective_interval_s(self, requested_interval_s: float) -> float:
        """Apply global chatter floor to an agent-provided interval."""
        return max(self.config.monitor.poll_tick_s, requested_interval_s)

    def _effective_heartbeat_interval_s(self, plugin_cfg: PluginConfig) -> float:
        """Effective heartbeat cadence after global floor enforcement."""
        return self._effective_interval_s(plugin_cfg.heartbeat_interval_s)

    def _effective_agent_flush_interval_s(self, plugin_cfg: PluginConfig) -> float:
        """Effective periodic flush cadence after global floor enforcement."""
        return self._effective_interval_s(plugin_cfg.agent_flush_interval_s)

    def _snapshot_monitor_settings(self) -> dict[str, Any]:
        """Return monitor settings plus cadence policy metadata."""
        return {
            "monitor": self.config.monitor.model_dump(),
            "control": self.config.control.model_dump(),
            "cadence_policy": {
                "strategy": "max(global_poll_tick_s, agent_requested_interval_s)",
                "description": (
                    "Global poll_tick_s acts as a one-sided chatter floor; "
                    "effective per-agent cadence is never faster than poll_tick_s."
                ),
            },
        }

    def _snapshot_orchestrator_state(self) -> dict[str, Any]:
        """Return current runtime lifecycle state for control-plane callers."""
        return {
            "running": self._running,
            "shutting_down": self._shutting_down,
            "ipc_enabled": bool(self._ipc_socket_path),
        }

    def _resolve_screen_tracker_thumbnail(
        self, instance_id: str
    ) -> tuple[Path | None, str | None]:
        """Return latest screen-tracker thumbnail path if available."""
        return resolve_screen_tracker_thumbnail(self, instance_id)

    def _screen_tracker_thumbnail_data_uri(
        self, thumbnail_path: Path
    ) -> tuple[str | None, str | None]:
        """Encode one thumbnail artifact as data URI for renderer-safe embedding."""
        return screen_tracker_thumbnail_data_uri(self, thumbnail_path)

    def _build_screen_tracker_widget_manifest(
        self, instance_id: str
    ) -> dict[str, Any]:
        """Build widget manifest for screen_tracker."""
        return build_screen_tracker_widget_manifest(self, instance_id)

    def _build_screen_tracker_widget_render(
        self, instance_id: str, request_id: str | None, mode: str
    ) -> dict[str, Any]:
        """Build widget render payload for screen_tracker."""
        return build_screen_tracker_widget_render(self, instance_id, request_id, mode)

    def _update_monitor_settings(
        self, updates: dict[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        """Update monitor settings with strict key validation and persistence."""
        return update_monitor_settings(self, updates)

    def _next_available_label(self, base_label: str) -> str:
        """Generate a unique config label for a new agent instance."""
        if base_label not in self.config.plugins:
            return base_label
        idx = 2
        while True:
            candidate = f"{base_label}_{idx}"
            if candidate not in self.config.plugins:
                return candidate
            idx += 1

    def _persist_runtime_config(self) -> tuple[bool, str]:
        """Persist in-memory runtime config if a config path is available."""
        if self._config_path is None:
            return False, "config_path_not_set"
        try:
            save_config(self.config, self._config_path)
            return True, "saved"
        except Exception as e:
            detail = f"save_failed:{e}"
            self.console.print(f"[red]Failed to save config: {e}[/red]")
            return False, detail

    def _add_agent_instance(
        self, template_id: str, requested_label: str | None
    ) -> tuple[bool, str, str | None]:
        """Create and start one new agent instance from template defaults."""
        templates = self._discover_agent_templates()
        template = templates.get(template_id)
        if template is None:
            return False, "unknown_template", None

        base_label = (requested_label or template_id).strip()
        if not base_label:
            return False, "invalid_label", None
        new_label = self._next_available_label(base_label)

        try:
            raw_default = template.get("default_config", {})
            plugin_cfg = PluginConfig.model_validate(raw_default)
        except Exception as e:
            return False, f"default_config_invalid:{e}", None

        self.config.plugins[new_label] = plugin_cfg
        self._set_agent_state(new_label, "inactive", "configured")
        saved, save_detail = self._persist_runtime_config()
        if not saved:
            del self.config.plugins[new_label]
            self._agent_states.pop(new_label, None)
            self._agent_state_details.pop(new_label, None)
            return False, save_detail, None

        started, start_detail = self._spawn_agent_for_label(new_label)
        if not started and start_detail != "already_running":
            return True, f"added_not_started:{start_detail}", new_label
        return True, "added", new_label

    def _duplicate_agent_instance(self, label: str) -> tuple[bool, str, str | None]:
        """Duplicate one configured agent instance."""
        source_cfg = self.config.plugins.get(label)
        if source_cfg is None or source_cfg.plugin_type != "agent":
            return False, "unknown_agent", None

        new_label = self._next_available_label(f"{label}_copy")
        try:
            dup_cfg = PluginConfig.model_validate(source_cfg.model_dump())
        except Exception as e:
            return False, f"duplicate_invalid:{e}", None

        self.config.plugins[new_label] = dup_cfg
        self._set_agent_state(new_label, "inactive", f"duplicated_from:{label}")
        saved, save_detail = self._persist_runtime_config()
        if not saved:
            del self.config.plugins[new_label]
            self._agent_states.pop(new_label, None)
            self._agent_state_details.pop(new_label, None)
            return False, save_detail, None

        started, start_detail = self._spawn_agent_for_label(new_label)
        if not started and start_detail != "already_running":
            return True, f"duplicated_not_started:{start_detail}", new_label
        return True, "duplicated", new_label

    def _remove_agent_instance(self, label: str) -> tuple[bool, str]:
        """Remove one configured agent instance (and stop if running)."""
        source_cfg = self.config.plugins.get(label)
        if source_cfg is None or source_cfg.plugin_type != "agent":
            return False, "unknown_agent"

        if label in self.agent_manager.agents:
            stopped, stop_detail = self._stop_agent_for_label(label)
            if not stopped:
                return False, f"stop_before_remove_failed:{stop_detail}"

        del self.config.plugins[label]
        self.agent_last_flush.pop(label, None)
        self._agent_states.pop(label, None)
        self._agent_state_details.pop(label, None)

        saved, save_detail = self._persist_runtime_config()
        if not saved:
            # Restore only if save failed.
            self.config.plugins[label] = source_cfg
            self._set_agent_state(label, "inactive", "restore_after_save_failure")
            return False, save_detail

        return True, "removed"

    def _update_agent_instance(
        self, label: str, updates: dict[str, Any]
    ) -> tuple[bool, str]:
        """Update one configured agent instance and persist changes."""
        current_cfg = self.config.plugins.get(label)
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
        sanitized_updates = {
            k: v for k, v in updates.items() if k in allowed_update_keys
        }

        merged = current_cfg.model_dump()
        merged.update(sanitized_updates)

        try:
            updated_cfg = PluginConfig.model_validate(merged)
        except Exception as e:
            return False, f"invalid_updates:{e}"

        restart_needed = (
            current_cfg.executable != updated_cfg.executable
            or current_cfg.args != updated_cfg.args
        )
        was_running = label in self.agent_manager.agents and self.agent_manager.agents[label].is_alive()

        self.config.plugins[label] = updated_cfg
        saved, save_detail = self._persist_runtime_config()
        if not saved:
            self.config.plugins[label] = current_cfg
            return False, save_detail

        if not updated_cfg.enabled:
            if was_running:
                self._stop_agent_for_label(label)
            self._set_agent_state(label, "inactive", "disabled")
            return True, "updated_disabled"

        if was_running and restart_needed:
            restarted, restart_detail = self._restart_agent_for_label(label)
            if not restarted:
                return False, restart_detail
            return True, "updated_restarted"

        if not was_running:
            self._set_agent_state(label, "inactive", "updated")
        else:
            self._set_agent_state(label, "running", "updated")
        return True, "updated"

    def _spawn_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Spawn one configured agent by label."""
        plugin_config = self.config.plugins.get(label)
        if (
            plugin_config is None
            or not plugin_config.enabled
            or plugin_config.plugin_type != "agent"
        ):
            self._set_agent_state(label, "error", "not_configured")
            return False, "not_configured"

        if not plugin_config.executable:
            self._set_agent_state(label, "error", "missing_executable")
            return False, "missing_executable"

        existing = self.agent_manager.agents.get(label)
        if existing and existing.is_alive():
            self._set_agent_state(label, "running", "already_running")
            return False, "already_running"

        if existing and not existing.is_alive():
            del self.agent_manager.agents[label]

        try:
            handle = self.agent_manager.spawn_agent(label, plugin_config)
            if (
                getattr(plugin_config, "launch_in_separate_terminal", False)
                and handle.stderr_log
            ):
                from mimolo.core.agent_debug import open_tail_window

                open_tail_window(handle.stderr_log)
            self._set_agent_state(label, "running", "spawned")
            self.console.print(f"[green]Spawned Agent: {label}[/green]")
            return True, "started"
        except Exception as e:
            detail = f"spawn_failed:{e}"
            self._set_agent_state(label, "error", detail)
            self.console.print(f"[red]Failed to spawn agent {label}: {e}[/red]")
            return False, detail

    def _stop_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Stop one running agent by label."""
        handle = self.agent_manager.agents.get(label)
        if handle is None:
            self._set_agent_state(label, "inactive", "not_running")
            return False, "not_running"

        self._set_agent_state(label, "shutting-down", "stop_requested")

        try:
            handle.shutdown()
        except Exception as e:
            detail = f"stop_failed:{e}"
            self._set_agent_state(label, "error", detail)
            self.console.print(f"[red]Failed stopping agent {label}: {e}[/red]")
            return False, detail

        self.agent_manager.agents.pop(label, None)
        self.agent_last_flush.pop(label, None)
        self._set_agent_state(label, "inactive", "stopped")
        return True, "stopped"

    def _restart_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Restart one configured agent by label."""
        if label in self.agent_manager.agents:
            stopped, stop_detail = self._stop_agent_for_label(label)
            if not stopped:
                return False, f"restart_stop_failed:{stop_detail}"

        started, start_detail = self._spawn_agent_for_label(label)
        if not started:
            return False, f"restart_start_failed:{start_detail}"
        return True, "restarted"

    def _queue_control_action(
        self, action: str, label: str, payload: dict[str, Any] | None = None
    ) -> None:
        """Queue one control action for processing on the runtime loop."""
        with self._control_actions_lock:
            item: dict[str, Any] = {
                "action": action,
                "label": label,
            }
            if payload:
                item["payload"] = payload
            self._pending_control_actions.append(item)

    def _drain_control_actions(self) -> list[dict[str, Any]]:
        """Drain pending control actions."""
        with self._control_actions_lock:
            actions = list(self._pending_control_actions)
            self._pending_control_actions.clear()
        return actions

    def _process_control_actions(self) -> None:
        """Apply queued control actions."""
        for action_item in self._drain_control_actions():
            action_raw = action_item.get("action")
            label_raw = action_item.get("label")
            if not isinstance(action_raw, str) or not isinstance(label_raw, str):
                continue
            action = action_raw
            label = label_raw
            payload = action_item.get("payload")
            payload_dict = payload if isinstance(payload, dict) else {}

            if action == "start_agent":
                self._spawn_agent_for_label(label)
            elif action == "stop_agent":
                self._stop_agent_for_label(label)
            elif action == "restart_agent":
                self._restart_agent_for_label(label)
            elif action == "add_agent_instance":
                template_id_raw = payload_dict.get("template_id")
                requested_label_raw = payload_dict.get("requested_label")
                if isinstance(template_id_raw, str):
                    requested_label = (
                        str(requested_label_raw)
                        if isinstance(requested_label_raw, str)
                        else None
                    )
                    self._add_agent_instance(template_id_raw, requested_label)
            elif action == "duplicate_agent_instance":
                self._duplicate_agent_instance(label)
            elif action == "remove_agent_instance":
                self._remove_agent_instance(label)
            elif action == "update_agent_instance":
                updates = payload_dict.get("updates")
                if isinstance(updates, dict):
                    self._update_agent_instance(label, updates)

    def _build_ipc_response(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle one IPC command and return response payload."""
        return build_ipc_response(self, request)


    def _handle_ipc_line(self, line: str) -> dict[str, Any]:
        """Parse one JSON-line request and produce a response."""
        return handle_ipc_line(self, line)

    def _send_ipc_response(self, conn: socket.socket, payload: dict[str, Any]) -> bool:
        """Send a single JSON-line response to an IPC client."""
        return send_ipc_response(conn, payload)

    def _serve_ipc_connection(self, conn: socket.socket) -> None:
        """Serve one IPC client connection until disconnect/stop."""
        serve_ipc_connection(self, conn)

    def _ipc_server_loop(self) -> None:
        """Accept IPC connections and process control commands."""
        ipc_server_loop(self)

    def _serve_ipc_client_thread(self, conn: socket.socket) -> None:
        """Serve one IPC client connection on its own thread."""
        serve_ipc_client_thread(self, conn)

    def _tick(self) -> None:
        """Execute one tick of the event loop."""
        self._tick_count += 1
        now = datetime.now(UTC)
        self._process_control_actions()

        # Track and report unexpected agent exits
        for label, handle in list(self.agent_manager.agents.items()):
            if not handle.is_alive():
                exit_code = handle.process.poll()
                last_heartbeat = (
                    handle.last_heartbeat.isoformat()
                    if handle.last_heartbeat
                    else None
                )
                self.console.print(
                    f"[red]Agent {label} exited unexpectedly (code={exit_code})[/red]"
                )
                try:
                    exit_event = Event(
                        timestamp=now,
                        label="orchestrator",
                        event="agent_exit",
                        data={
                            "agent": label,
                            "exit_code": exit_code,
                            "last_heartbeat": last_heartbeat,
                            "note": "Agent process exited without shutdown sequence",
                        },
                    )
                    self.file_sink.write_event(exit_event)
                except Exception as e:
                    self._debug(
                        f"[yellow]Failed to write agent_exit event for {label}: {e}[/yellow]"
                    )
                # Remove dead handle to avoid repeated alerts
                detail = f"exit_code:{exit_code}" if exit_code is not None else "exit_code:unknown"
                self._set_agent_state(label, "error", detail)
                del self.agent_manager.agents[label]
                continue

        # Check for cooldown expiration
        if self.cooldown.check_expiration(now):
            self._close_segment()

        # Poll Agent messages
        from mimolo.core.protocol import CommandType, OrchestratorCommand

        for label, handle in list(self.agent_manager.agents.items()):
            # Check if it's time to send flush command
            plugin_config = self.config.plugins.get(label)
            if plugin_config and plugin_config.plugin_type == "agent":
                last_flush = self.agent_last_flush.get(label)
                flush_interval = self._effective_agent_flush_interval_s(plugin_config)

                # Send flush if interval elapsed or never flushed
                if last_flush is None or (now - last_flush).total_seconds() >= flush_interval:
                    try:
                        flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
                        if handle.send_command(flush_cmd):
                            self.agent_last_flush[label] = now
                        if self.config.monitor.console_verbosity == "debug":
                            self.console.print(f"[cyan]Sent flush to {label}[/cyan]")
                    except Exception as e:
                        self.console.print(f"[red]Error sending flush to {label}: {e}[/red]")

            # Drain all available messages from this agent
            while (msg := handle.read_message(timeout=0.001)) is not None:
                try:
                    # Message routing by type (msg.type may be str or Enum)
                    mtype = getattr(msg, "type", None)
                    if isinstance(mtype, str):
                        t = mtype
                    else:
                        t = str(mtype).lower()

                    if t == "heartbeat" or t.endswith("heartbeat"):
                        self._handle_heartbeat(label, msg)
                    elif t == "summary" or t.endswith("summary"):
                        self._handle_agent_summary(label, msg)
                    elif t == "log" or t.endswith("log"):
                        self._handle_agent_log(label, msg)
                    elif t == "error" or t.endswith("error"):
                        # Log agent-reported error
                        try:
                            message = getattr(msg, "message", None) or getattr(msg, "data", None)
                            self.console.print(f"[red]Agent {label} error: {message}[/red]")
                        except Exception as e:
                            self.console.print(
                                f"[red]Agent {label} reported an error (unreadable payload): {e}[/red]"
                            )
                except Exception as e:
                    self.console.print(
                        f"[red]Error handling agent message from {label}: {e}[/red]"
                    )

    def _coerce_timestamp(self, ts: object) -> datetime:
        """Coerce a timestamp value (str or datetime) into timezone-aware datetime."""
        return coerce_timestamp(self, ts)

    def _handle_agent_summary(self, label: str, msg: object) -> None:
        """Write Agent summary directly to file.

        Agents pre-aggregate their own data, so we don't re-aggregate.
        Just log the summary event directly.

        Args:
            label: agent label
            msg: parsed message object with attributes `timestamp`, `agent_label`, `data`.
        """
        handle_agent_summary(self, label, msg)

    def _handle_heartbeat(self, label: str, msg: object) -> None:
        """Handle a heartbeat message from a Agent.

        Updates agent health state and optionally logs to console.
        Heartbeats are NOT written to file - they're for health monitoring only.
        """
        handle_heartbeat(self, label, msg)

    def _handle_agent_log(self, label: str, msg: object) -> None:
        """Handle a structured log message from a Agent.

        Log messages flow through Agent JLP and are rendered on the
        orchestrator console with Rich formatting. The orchestrator respects
        console_verbosity settings to filter log messages by level.

        Args:
            label: Agent label (plugin name)
            msg: LogMessage instance with level, message, and markup fields
        """
        handle_agent_log(self, label, msg)

    def _flush_all_agents(self) -> None:
        """Send flush command to all active Agents."""
        flush_all_agents(self)

    def _close_segment(self) -> None:
        """Close current segment and flush all agents.

        Agents handle their own aggregation, so this just sends flush commands.
        """
        close_segment(self)

    def _shutdown(self) -> None:
        """Clean shutdown: flush agents and close sinks."""
        shutdown_runtime(self)

    def stop(self) -> None:
        """Request graceful stop."""
        self._running = False
