"""Runtime shutdown and segment management helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from mimolo.core.errors import SinkError
from mimolo.core.event import Event

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime

def flush_all_agents(runtime: Runtime) -> None:
    """Send flush command to all active Agents."""
    from mimolo.core.protocol import CommandType, OrchestratorCommand

    flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
    for label, handle in runtime.agent_manager.agents.items():
        try:
            handle.send_command(flush_cmd)
            if runtime.config.monitor.console_verbosity == "debug":
                runtime.console.print(f"[cyan]Sent flush to {label}[/cyan]")
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            runtime.console.print(f"[red]Error sending flush to {label}: {e}[/red]")

def close_segment(runtime: Runtime) -> None:
    """Close current segment and flush all agents.

    Agents handle their own aggregation, so this just sends flush commands.
    """
    # Send flush command to all Agents
    runtime._flush_all_agents()

    # Close cooldown segment
    try:
        runtime.cooldown.close_segment()
        if runtime.config.monitor.console_verbosity == "debug":
            runtime.console.print("[blue]Segment closed[/blue]")
    except RuntimeError as e:
        runtime._debug(f"[yellow]No open segment to close: {e}[/yellow]")

def shutdown_runtime(runtime: Runtime) -> None:
    """Clean shutdown: flush agents and close sinks."""
    runtime.console.print("[yellow]Shutting down...[/yellow]")
    runtime._shutting_down = True

    # Graceful stop sequence:
    # Emit an orchestrator-level event so the file log shows shutdown boundaries.
    try:
        now = datetime.now(UTC)
        agent_count = len(runtime.agent_manager.agents)
        expected_msgs = max(1, agent_count * 2)
        shutdown_event = Event(
            timestamp=now,
            label="orchestrator",
            event="shutdown_initiated",
            data={
                "agent_count": agent_count,
                "expected_shutdown_messages": expected_msgs,
                "note": "Following entries are agent shutdown/flush messages",
            },
        )
        try:
            runtime.file_sink.write_event(shutdown_event)
        except (SinkError, OSError, RuntimeError, ValueError, TypeError) as e:
            runtime._debug(
                f"[yellow]Failed to write shutdown_initiated event: {e}[/yellow]"
            )
        if runtime.config.monitor.console_verbosity in ("debug", "info"):
            runtime.console_sink.write_event(shutdown_event)
    except (AttributeError, RuntimeError, ValueError, TypeError, SinkError) as e:
        runtime._debug(
            f"[yellow]Failed to emit shutdown_initiated event: {e}[/yellow]"
        )

    # Graceful stop sequence using chained SEQUENCE command:
    # Send SEQUENCE([STOP, FLUSH, SHUTDOWN]) to all agents
    # Agent responds: ACK(stop) → ACK(flush) + summary → final heartbeat → exit
    # Orchestrator drains all messages and waits for responses

    # Initialize counters outside try block so they're available in except/finally
    summaries_count = 0
    logs_count = 0
    acks_count = 0

    from mimolo.core.protocol import CommandType, OrchestratorCommand

    sequence_cmd = OrchestratorCommand(
        cmd=CommandType.SEQUENCE,
        sequence=[
            CommandType.STOP,
            CommandType.FLUSH,
            CommandType.SHUTDOWN,
        ],
    )

    # Announce shutdown wait before sending sequence to avoid confusing ordering.
    runtime.console.print(
        "[yellow]Waiting for Agent processes to exit...[/yellow]"
    )

    shutdown_timeout_s = 4.0
    runtime._shutdown_deadlines = {}
    runtime._shutdown_phase = {}
    ordered_labels = sorted(runtime.agent_manager.agents.keys())

    for label in ordered_labels:
        handle = runtime.agent_manager.agents.get(label)
        if not handle:
            continue

        runtime._set_agent_state(label, "shutting-down", "orchestrator_shutdown")
        got_stop_ack = False
        got_summary = False
        agent_deadline = time.time() + shutdown_timeout_s
        runtime._shutdown_deadlines[label] = agent_deadline
        runtime._shutdown_phase[label] = "sequence_sent"

        try:
            ok = handle.send_command(sequence_cmd)
            if not ok:
                runtime.console.print(
                    f"[red]Failed to send SEQUENCE to {label} (stdin closed?)[/red]"
                )
                continue
            if runtime.config.monitor.console_verbosity == "debug":
                runtime.console.print(f"[cyan]Sent shutdown SEQUENCE to {label}[/cyan]")
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            runtime.console.print(f"[red]Exception sending SEQUENCE to {label}: {e}[/red]")
            continue

        while time.time() < agent_deadline:
            msg = handle.read_message(timeout=0.05)
            if msg is None:
                if got_stop_ack and got_summary and not handle.is_alive():
                    break
                continue

            try:
                mtype = getattr(msg, "type", None)
                if isinstance(mtype, str):
                    t = mtype
                else:
                    t = str(mtype).lower()

                if t == "ack" or t.endswith("ack"):
                    ack_cmd = getattr(msg, "ack_command", None)
                    acks_count += 1
                    if ack_cmd == "stop":
                        got_stop_ack = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "stop_ack"
                        if runtime.config.monitor.console_verbosity == "debug":
                            runtime.console.print(f"[cyan]Agent {label} ACK(stop)[/cyan]")
                    elif ack_cmd == "flush":
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "flush_ack"
                elif t == "summary" or t.endswith("summary"):
                    try:
                        runtime._handle_agent_summary(label, msg)
                        summaries_count += 1
                        got_summary = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "summary_received"
                    except (
                        AttributeError,
                        RuntimeError,
                        ValueError,
                        TypeError,
                        SinkError,
                    ) as e:
                        runtime._debug(
                            f"[yellow]Failed to handle shutdown summary from {label}: {e}[/yellow]"
                        )
                elif t == "log" or t.endswith("log"):
                    try:
                        runtime._handle_agent_log(label, msg)
                        logs_count += 1
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "log_received"
                    except (
                        AttributeError,
                        RuntimeError,
                        ValueError,
                        TypeError,
                        SinkError,
                    ) as e:
                        runtime._debug(
                            f"[yellow]Failed to handle shutdown log from {label}: {e}[/yellow]"
                        )
                elif t == "heartbeat" or t.endswith("heartbeat"):
                    runtime._handle_heartbeat(label, msg)
                    agent_deadline = time.time() + shutdown_timeout_s
                    runtime._shutdown_deadlines[label] = agent_deadline
                    runtime._shutdown_phase[label] = "heartbeat"
                elif t == "status" or t.endswith("status"):
                    agent_deadline = time.time() + shutdown_timeout_s
                    runtime._shutdown_deadlines[label] = agent_deadline
                    runtime._shutdown_phase[label] = "status"
            except (
                AttributeError,
                RuntimeError,
                ValueError,
                TypeError,
                SinkError,
            ) as e:
                runtime._debug(
                    f"[yellow]Failed to parse shutdown message from {label}: {e}[/yellow]"
                )

            if got_stop_ack and got_summary and not handle.is_alive():
                break

        if not got_stop_ack:
            runtime.console.print(f"[red]Agent {label} did not ACK STOP (timeout)[/red]")
            try:
                stop_exception = Event(
                    timestamp=datetime.now(UTC),
                    label="orchestrator",
                    event="shutdown_exception",
                    data={
                        "agent": label,
                        "phase": "stop",
                        "error": "No stop ACK received",
                    },
                )
                runtime.file_sink.write_event(stop_exception)
            except (SinkError, OSError, RuntimeError, ValueError, TypeError) as e:
                runtime._debug(
                    f"[yellow]Failed to write shutdown_exception (stop) for {label}: {e}[/yellow]"
                )

        if not got_summary:
            runtime.console.print(
                f"[red]Agent {label} did not send summary after FLUSH (timeout)[/red]"
            )
            try:
                flush_exception = Event(
                    timestamp=datetime.now(UTC),
                    label="orchestrator",
                    event="shutdown_exception",
                    data={
                        "agent": label,
                        "phase": "flush",
                        "error": "No summary received",
                    },
                )
                runtime.file_sink.write_event(flush_exception)
            except (SinkError, OSError, RuntimeError, ValueError, TypeError) as e:
                runtime._debug(
                    f"[yellow]Failed to write shutdown_exception (flush) for {label}: {e}[/yellow]"
                )

    # Agents should have shut down by now; wait for processes to exit
    handles = runtime.agent_manager.shutdown_all()

    # Drain any remaining messages produced during shutdown (short period)
    deadline = time.time() + 1.0
    while time.time() < deadline:
        got_any = False
        for handle in handles:
            while (msg := handle.read_message(timeout=0.01)) is not None:
                got_any = True
                try:
                    mtype = getattr(msg, "type", None)
                    if isinstance(mtype, str):
                        t = mtype
                    else:
                        t = str(mtype).lower()

                    if t == "summary" or t.endswith("summary"):
                        try:
                            runtime._handle_agent_summary(handle.label, msg)
                            summaries_count += 1
                        except (
                            AttributeError,
                            RuntimeError,
                            ValueError,
                            TypeError,
                            SinkError,
                        ) as e:
                            runtime._debug(
                                f"[yellow]Failed to handle late shutdown summary from {handle.label}: {e}[/yellow]"
                            )
                    elif t == "log" or t.endswith("log"):
                        try:
                            runtime._handle_agent_log(handle.label, msg)
                            logs_count += 1
                        except (
                            AttributeError,
                            RuntimeError,
                            ValueError,
                            TypeError,
                            SinkError,
                        ) as e:
                            runtime._debug(
                                f"[yellow]Failed to handle late shutdown log from {handle.label}: {e}[/yellow]"
                            )
                    elif t == "heartbeat" or t.endswith("heartbeat"):
                        runtime._handle_heartbeat(handle.label, msg)
                    elif t == "status" or t.endswith("status"):
                        runtime._debug(
                            f"[yellow]Late shutdown status from {handle.label} ignored[/yellow]"
                        )
                except (
                    AttributeError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                    SinkError,
                ) as e:
                    runtime._debug(
                        f"[yellow]Failed to handle late shutdown message from {handle.label}: {e}[/yellow]"
                    )

        if not got_any:
            break

    # Finally, remove references to the handles now we've drained them
    try:
        for h in handles:
            if h.label in runtime.agent_manager.agents:
                del runtime.agent_manager.agents[h.label]
            runtime._set_agent_state(h.label, "inactive", "stopped")
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError) as e:
        runtime._debug(
            f"[yellow]Failed to clear agent handles after shutdown: {e}[/yellow]"
        )

    # Flush and close sinks
    try:
        # Emit a final orchestrator event indicating shutdown complete
        try:
            now = datetime.now(UTC)
            complete_event = Event(
                timestamp=now,
                label="orchestrator",
                event="shutdown_complete",
                data={
                    "agent_count_final": len(runtime.agent_manager.agents),
                    "timestamp": now.isoformat(),
                    "note": "All agents shutdown and sinks closed",
                    "summaries_written_during_shutdown": summaries_count,
                    "logs_written_during_shutdown": logs_count,
                    "acks_received_during_shutdown": acks_count,
                },
            )
            try:
                runtime.file_sink.write_event(complete_event)
            except (SinkError, OSError, RuntimeError, ValueError, TypeError) as e:
                runtime._debug(
                    f"[yellow]Failed to write shutdown_complete event: {e}[/yellow]"
                )
            if runtime.config.monitor.console_verbosity in ("debug", "info"):
                runtime.console_sink.write_event(complete_event)
        except (AttributeError, RuntimeError, ValueError, TypeError, SinkError) as e:
            runtime._debug(
                f"[yellow]Failed to emit shutdown_complete event: {e}[/yellow]"
            )

        runtime.file_sink.flush()
        runtime.file_sink.close()
        runtime.console.print("[green]MiMoLo stopped.[/green]")
        # Final console-only confirmation after sinks are closed
        runtime.console.print("[green]Shutdown complete.[/green]")
    except (SinkError, OSError, RuntimeError, ValueError, TypeError) as e:
        runtime.console.print(f"[red]Error closing sinks: {e}[/red]")
    finally:
        runtime._stop_ipc_server()
