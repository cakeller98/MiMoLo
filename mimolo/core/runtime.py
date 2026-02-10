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
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

from rich.console import Console

from mimolo.core.config import Config, PluginConfig
from mimolo.core.cooldown import CooldownTimer
from mimolo.core.plugin_store import PluginStore
from mimolo.core.runtime_agent_events import (
    coerce_timestamp,
    handle_agent_log,
    handle_agent_summary,
    handle_heartbeat,
)
from mimolo.core.runtime_agent_lifecycle import (
    restart_agent_for_label,
    spawn_agent_for_label,
    start_agents,
    stop_agent_for_label,
)
from mimolo.core.runtime_agent_registry import (
    discover_agent_templates,
    effective_agent_flush_interval_s,
    effective_heartbeat_interval_s,
    effective_interval_s,
    infer_template_id,
    set_agent_state,
    snapshot_agent_instances,
    snapshot_agent_states,
    snapshot_running_agents,
)
from mimolo.core.runtime_control_actions import (
    add_agent_instance,
    drain_control_actions,
    duplicate_agent_instance,
    next_available_label,
    persist_runtime_config,
    process_control_actions,
    queue_control_action,
    remove_agent_instance,
    update_agent_instance,
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
from mimolo.core.runtime_tick import execute_tick
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
        start_agents(self)

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
            # Socket file already absent; cleanup path is idempotent.
            self._debug(
                f"[dim]IPC socket already absent: {self._ipc_socket_path}[/dim]"
            )
        except OSError as e:
            # OSError: filesystem cleanup can fail on shutdown races.
            self._debug(f"[yellow]IPC socket cleanup failed: {e}[/yellow]")

    def _snapshot_running_agents(self) -> list[str]:
        """Safely capture currently running agent labels."""
        return snapshot_running_agents(self)

    def _set_agent_state(
        self, label: str, state: AgentLifecycleState, detail: str
    ) -> None:
        """Set lifecycle state for one agent."""
        set_agent_state(self, label, state, detail)

    def _snapshot_agent_states(self) -> dict[str, dict[str, str]]:
        """Return lifecycle state snapshot for enabled configured agents."""
        return snapshot_agent_states(self)

    def _infer_template_id(self, label: str, plugin_cfg: PluginConfig) -> str:
        """Infer template id from args path, falling back to label."""
        return infer_template_id(self, label, plugin_cfg)

    def _discover_agent_templates(self) -> dict[str, dict[str, Any]]:
        """Discover agent templates from local agents directory."""
        return discover_agent_templates(self)

    def _snapshot_agent_instances(self) -> dict[str, dict[str, Any]]:
        """Return configured agent instances with state and editable config."""
        return snapshot_agent_instances(self)

    def _effective_interval_s(self, requested_interval_s: float) -> float:
        """Apply global chatter floor to an agent-provided interval."""
        return effective_interval_s(self, requested_interval_s)

    def _effective_heartbeat_interval_s(self, plugin_cfg: PluginConfig) -> float:
        """Effective heartbeat cadence after global floor enforcement."""
        return effective_heartbeat_interval_s(self, plugin_cfg)

    def _effective_agent_flush_interval_s(self, plugin_cfg: PluginConfig) -> float:
        """Effective periodic flush cadence after global floor enforcement."""
        return effective_agent_flush_interval_s(self, plugin_cfg)

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
        return next_available_label(self, base_label)

    def _persist_runtime_config(self) -> tuple[bool, str]:
        """Persist in-memory runtime config if a config path is available."""
        return persist_runtime_config(self)

    def _add_agent_instance(
        self, template_id: str, requested_label: str | None
    ) -> tuple[bool, str, str | None]:
        """Create and start one new agent instance from template defaults."""
        return add_agent_instance(self, template_id, requested_label)

    def _duplicate_agent_instance(self, label: str) -> tuple[bool, str, str | None]:
        """Duplicate one configured agent instance."""
        return duplicate_agent_instance(self, label)

    def _remove_agent_instance(self, label: str) -> tuple[bool, str]:
        """Remove one configured agent instance (and stop if running)."""
        return remove_agent_instance(self, label)

    def _update_agent_instance(
        self, label: str, updates: dict[str, Any]
    ) -> tuple[bool, str]:
        """Update one configured agent instance and persist changes."""
        return update_agent_instance(self, label, updates)

    def _spawn_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Spawn one configured agent by label."""
        return spawn_agent_for_label(self, label)

    def _stop_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Stop one running agent by label."""
        return stop_agent_for_label(self, label)

    def _restart_agent_for_label(self, label: str) -> tuple[bool, str]:
        """Restart one configured agent by label."""
        return restart_agent_for_label(self, label)

    def _queue_control_action(
        self, action: str, label: str, payload: dict[str, Any] | None = None
    ) -> None:
        """Queue one control action for processing on the runtime loop."""
        queue_control_action(self, action, label, payload)

    def _drain_control_actions(self) -> list[dict[str, Any]]:
        """Drain pending control actions."""
        return drain_control_actions(self)

    def _process_control_actions(self) -> None:
        """Apply queued control actions."""
        process_control_actions(self)

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
        execute_tick(self)

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
