"""Runtime event-loop tick helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mimolo.core.errors import SinkError
from mimolo.core.event import Event
from mimolo.core.protocol import CommandType, OrchestratorCommand

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def execute_tick(runtime: Runtime) -> None:
    """Execute one tick of the runtime event loop."""
    runtime._tick_count += 1
    now = datetime.now(UTC)
    runtime._process_control_actions()

    _reap_unexpected_agent_exits(runtime, now)

    if runtime.cooldown.check_expiration(now):
        runtime._close_segment()

    for label, handle in list(runtime.agent_manager.agents.items()):
        _maybe_send_flush(runtime, label, handle, now)
        _drain_agent_messages(runtime, label, handle)


def _reap_unexpected_agent_exits(runtime: Runtime, now: datetime) -> None:
    """Track and report unexpected agent exits, removing dead handles."""
    for label, handle in list(runtime.agent_manager.agents.items()):
        if handle.is_alive():
            continue
        exit_code = handle.process.poll()
        last_heartbeat = (
            handle.last_heartbeat.isoformat() if handle.last_heartbeat else None
        )
        runtime.console.print(
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
            runtime.file_sink.write_event(exit_event)
        except (SinkError, RuntimeError, ValueError, TypeError) as e:
            runtime._debug(
                f"[yellow]Failed to write agent_exit event for {label}: {e}[/yellow]"
            )
        detail = f"exit_code:{exit_code}" if exit_code is not None else "exit_code:unknown"
        runtime._set_agent_state(label, "error", detail)
        del runtime.agent_manager.agents[label]


def _maybe_send_flush(
    runtime: Runtime,
    label: str,
    handle: Any,
    now: datetime,
) -> None:
    """Send flush command when the agent's effective flush cadence has elapsed."""
    plugin_config = runtime.config.plugins.get(label)
    if plugin_config is None or plugin_config.plugin_type != "agent":
        return
    last_flush = runtime.agent_last_flush.get(label)
    flush_interval = runtime._effective_agent_flush_interval_s(plugin_config)

    if last_flush is not None and (now - last_flush).total_seconds() < flush_interval:
        return

    try:
        flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
        if handle.send_command(flush_cmd):
            runtime.agent_last_flush[label] = now
        if runtime.config.monitor.console_verbosity == "debug":
            runtime.console.print(f"[cyan]Sent flush to {label}[/cyan]")
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        runtime.console.print(f"[red]Error sending flush to {label}: {e}[/red]")


def _drain_agent_messages(runtime: Runtime, label: str, handle: Any) -> None:
    """Drain and route all pending messages for one agent."""
    while (msg := handle.read_message(timeout=0.001)) is not None:
        try:
            mtype = getattr(msg, "type", None)
            if isinstance(mtype, str):
                t = mtype
            else:
                t = str(mtype).lower()

            if t == "heartbeat" or t.endswith("heartbeat"):
                runtime._handle_heartbeat(label, msg)
            elif t == "summary" or t.endswith("summary"):
                runtime._handle_agent_summary(label, msg)
            elif t == "log" or t.endswith("log"):
                runtime._handle_agent_log(label, msg)
            elif t == "error" or t.endswith("error"):
                _report_agent_error(runtime, label, msg)
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            runtime.console.print(
                f"[red]Error handling agent message from {label}: {e}[/red]"
            )


def _report_agent_error(runtime: Runtime, label: str, msg: object) -> None:
    """Report agent-emitted error payloads to the orchestrator console."""
    try:
        message = getattr(msg, "message", None) or getattr(msg, "data", None)
        runtime.console.print(f"[red]Agent {label} error: {message}[/red]")
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        runtime.console.print(
            f"[red]Agent {label} reported an error (unreadable payload): {e}[/red]"
        )
