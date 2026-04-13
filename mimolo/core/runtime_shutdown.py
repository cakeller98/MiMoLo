"""Runtime shutdown and segment management helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mimolo.core.runtime_agent_events import coerce_timestamp

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime


def _write_shutdown_agent_step(
    runtime: Runtime,
    *,
    agent: str,
    step: str,
    status: str,
    timestamp: datetime | None = None,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write one structured shutdown sequencing diagnostic for an agent."""
    data: dict[str, Any] = {
        "agent": agent,
        "step": step,
        "status": status,
    }
    if detail:
        data["detail"] = detail
    if extra:
        data.update(extra)
    runtime._write_diagnostic_event(
        label="orchestrator",
        event="shutdown_agent_step",
        timestamp=timestamp or datetime.now(UTC),
        data=data,
    )


def _write_shutdown_agent_result(
    runtime: Runtime,
    *,
    agent: str,
    result: dict[str, Any],
    timestamp: datetime | None = None,
) -> None:
    """Write one final per-agent shutdown outcome record."""
    payload = {"agent": agent}
    payload.update(result)
    runtime._write_diagnostic_event(
        label="orchestrator",
        event="shutdown_agent_result",
        timestamp=timestamp or datetime.now(UTC),
        data=payload,
    )


def _summary_event_name(msg: object) -> str:
    """Extract summary event label for shutdown diagnostics."""
    raw_data = getattr(msg, "data", None)
    if not isinstance(raw_data, dict):
        return "summary"
    summary_event = raw_data.get("summary_event")
    if summary_event:
        return str(summary_event)
    event_name = raw_data.get("event")
    if event_name:
        return str(event_name)
    return "summary"

def flush_all_agents(runtime: Runtime) -> None:
    """Send flush command to all active Agents."""
    from mimolo.core.protocol import CommandType, OrchestratorCommand

    flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
    for label, handle in runtime.agent_manager.agents.items():
        try:
            handle.send_command(flush_cmd)
            if runtime.config.monitor.console_verbosity == "debug":
                runtime._console_print_safe(f"[cyan]Sent flush to {label}[/cyan]")
        except (OSError, RuntimeError, ValueError, TypeError) as e:
            runtime._console_print_safe(
                f"[red]Error sending flush to {label}: {e}[/red]"
            )

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
            runtime._console_print_safe("[blue]Segment closed[/blue]")
    except RuntimeError as e:
        runtime._debug(f"[yellow]No open segment to close: {e}[/yellow]")

def shutdown_runtime(runtime: Runtime) -> None:
    """Clean shutdown: flush agents and close sinks."""
    runtime._console_print_safe("[yellow]Shutting down...[/yellow]")
    runtime._shutting_down = True

    now = datetime.now(UTC)
    agent_count = len(runtime.agent_manager.agents)
    expected_msgs = max(1, agent_count * 3)
    runtime._write_diagnostic_event(
        label="orchestrator",
        event="shutdown_initiated",
        timestamp=now,
        data={
            "agent_count": agent_count,
            "expected_shutdown_messages": expected_msgs,
            "note": "Expecting ACK(stop), ACK(flush), summary, ACK(shutdown), then process exit",
        },
    )

    # Graceful stop sequence using chained SEQUENCE command:
    # Send SEQUENCE([STOP, FLUSH, SHUTDOWN]) to all agents
    # Agent responds: ACK(stop) → ACK(flush) + summary → ACK(shutdown) → exit
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
    runtime._console_print_safe("[yellow]Waiting for Agent processes to exit...[/yellow]")

    shutdown_timeout_s = 4.0
    runtime._shutdown_deadlines = {}
    runtime._shutdown_phase = {}
    ordered_labels = sorted(runtime.agent_manager.agents.keys())

    agent_results: dict[str, dict[str, Any]] = {}

    for label in ordered_labels:
        handle = runtime.agent_manager.agents.get(label)
        if not handle:
            continue

        runtime._set_agent_state(label, "shutting-down", "orchestrator_shutdown")
        got_stop_ack = False
        got_flush_ack = False
        got_summary = False
        got_shutdown_ack = False
        agent_deadline = time.time() + shutdown_timeout_s
        runtime._shutdown_deadlines[label] = agent_deadline
        runtime._shutdown_phase[label] = "sequence_sent"
        agent_results[label] = {
            "stop_ack_received": False,
            "flush_ack_received": False,
            "summary_received": False,
            "shutdown_ack_received": False,
            "process_exited": False,
            "exit_code": None,
            "final_phase": "sequence_sent",
            "clean_shutdown": False,
        }

        try:
            ok = handle.send_command(sequence_cmd)
            if not ok:
                runtime._console_print_safe(
                    f"[red]Failed to send SEQUENCE to {label} (stdin closed?)[/red]"
                )
                _write_shutdown_agent_step(
                    runtime,
                    agent=label,
                    step="sequence",
                    status="send_failed",
                    detail="stdin_closed_or_process_dead",
                )
                agent_results[label]["final_phase"] = "sequence_send_failed"
                continue
            if runtime.config.monitor.console_verbosity == "debug":
                runtime._console_print_safe(
                    f"[cyan]Sent shutdown SEQUENCE to {label}[/cyan]"
                )
            _write_shutdown_agent_step(
                runtime,
                agent=label,
                step="sequence",
                status="sent",
            )
        except (OSError, RuntimeError, ValueError, TypeError) as e:
                runtime._console_print_safe(
                    f"[red]Exception sending SEQUENCE to {label}: {e}[/red]"
                )
                _write_shutdown_agent_step(
                    runtime,
                    agent=label,
                    step="sequence",
                    status="send_exception",
                    detail=str(e),
                )
                agent_results[label]["final_phase"] = "sequence_send_exception"
                continue

        while time.time() < agent_deadline:
            msg = handle.read_message(timeout=0.05)
            if msg is None:
                if (
                    got_stop_ack
                    and got_flush_ack
                    and got_summary
                    and got_shutdown_ack
                    and not handle.is_alive()
                ):
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
                        agent_results[label]["stop_ack_received"] = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "stop_ack"
                        agent_results[label]["final_phase"] = "stop_ack"
                        _write_shutdown_agent_step(
                            runtime,
                            agent=label,
                            step="stop",
                            status="ack",
                            timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
                        )
                        if runtime.config.monitor.console_verbosity == "debug":
                            runtime._console_print_safe(
                                f"[cyan]Agent {label} ACK(stop)[/cyan]"
                            )
                    elif ack_cmd == "flush":
                        got_flush_ack = True
                        agent_results[label]["flush_ack_received"] = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "flush_ack"
                        agent_results[label]["final_phase"] = "flush_ack"
                        _write_shutdown_agent_step(
                            runtime,
                            agent=label,
                            step="flush",
                            status="ack",
                            timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
                        )
                    elif ack_cmd == "shutdown":
                        got_shutdown_ack = True
                        agent_results[label]["shutdown_ack_received"] = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "shutdown_ack"
                        agent_results[label]["final_phase"] = "shutdown_ack"
                        _write_shutdown_agent_step(
                            runtime,
                            agent=label,
                            step="shutdown",
                            status="ack",
                            timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
                        )
                elif t == "summary" or t.endswith("summary"):
                    try:
                        runtime._handle_agent_summary(label, msg)
                        summaries_count += 1
                        got_summary = True
                        agent_results[label]["summary_received"] = True
                        agent_deadline = time.time() + shutdown_timeout_s
                        runtime._shutdown_deadlines[label] = agent_deadline
                        runtime._shutdown_phase[label] = "summary_received"
                        agent_results[label]["final_phase"] = "summary_received"
                        _write_shutdown_agent_step(
                            runtime,
                            agent=label,
                            step="summary",
                            status="received",
                            timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
                            extra={"summary_event": _summary_event_name(msg)},
                        )
                    except (
                        AttributeError,
                        RuntimeError,
                        ValueError,
                        TypeError,
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
                    runtime._handle_status(label, msg)
                    agent_deadline = time.time() + shutdown_timeout_s
                    runtime._shutdown_deadlines[label] = agent_deadline
                    runtime._shutdown_phase[label] = "status"
                elif t == "error" or t.endswith("error"):
                    runtime._handle_agent_error(label, msg)
                    agent_deadline = time.time() + shutdown_timeout_s
                    runtime._shutdown_deadlines[label] = agent_deadline
                    runtime._shutdown_phase[label] = "error"
            except (
                AttributeError,
                RuntimeError,
                ValueError,
                TypeError,
            ) as e:
                runtime._debug(
                    f"[yellow]Failed to parse shutdown message from {label}: {e}[/yellow]"
                )

            if (
                got_stop_ack
                and got_flush_ack
                and got_summary
                and got_shutdown_ack
                and not handle.is_alive()
            ):
                break

        if not got_stop_ack:
            runtime._console_print_safe(
                f"[red]Agent {label} did not ACK STOP (timeout)[/red]"
            )
            _write_shutdown_agent_step(
                runtime,
                agent=label,
                step="stop",
                status="timeout",
                detail="no_stop_ack_received",
            )
            runtime._write_diagnostic_event(
                label="orchestrator",
                event="shutdown_exception",
                timestamp=datetime.now(UTC),
                data={
                    "agent": label,
                    "phase": "stop",
                    "error": "No stop ACK received",
                },
            )

        if not got_summary:
            runtime._console_print_safe(
                f"[red]Agent {label} did not send summary after FLUSH (timeout)[/red]"
            )
            _write_shutdown_agent_step(
                runtime,
                agent=label,
                step="summary",
                status="timeout",
                detail="no_summary_received_after_flush",
            )
            runtime._write_diagnostic_event(
                label="orchestrator",
                event="shutdown_exception",
                timestamp=datetime.now(UTC),
                data={
                    "agent": label,
                    "phase": "flush",
                    "error": "No summary received",
                },
            )
        if not got_flush_ack:
            runtime._console_print_safe(
                f"[red]Agent {label} did not ACK FLUSH (timeout)[/red]"
            )
            _write_shutdown_agent_step(
                runtime,
                agent=label,
                step="flush",
                status="timeout",
                detail="no_flush_ack_received",
            )
            runtime._write_diagnostic_event(
                label="orchestrator",
                event="shutdown_exception",
                timestamp=datetime.now(UTC),
                data={
                    "agent": label,
                    "phase": "flush_ack",
                    "error": "No flush ACK received",
                },
            )
        if not got_shutdown_ack:
            runtime._console_print_safe(
                f"[red]Agent {label} did not ACK SHUTDOWN (timeout)[/red]"
            )
            _write_shutdown_agent_step(
                runtime,
                agent=label,
                step="shutdown",
                status="timeout",
                detail="no_shutdown_ack_received",
            )
            runtime._write_diagnostic_event(
                label="orchestrator",
                event="shutdown_exception",
                timestamp=datetime.now(UTC),
                data={
                    "agent": label,
                    "phase": "shutdown_ack",
                    "error": "No shutdown ACK received",
                },
            )
        agent_results[label]["clean_shutdown"] = bool(
            got_stop_ack and got_flush_ack and got_summary and got_shutdown_ack
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
                            if handle.label in agent_results:
                                agent_results[handle.label]["summary_received"] = True
                                agent_results[handle.label]["final_phase"] = "summary_received_late"
                            _write_shutdown_agent_step(
                                runtime,
                                agent=handle.label,
                                step="summary",
                                status="received_late",
                                timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
                                extra={"summary_event": _summary_event_name(msg)},
                            )
                        except (
                            AttributeError,
                            RuntimeError,
                            ValueError,
                            TypeError,
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
                        ) as e:
                            runtime._debug(
                                f"[yellow]Failed to handle late shutdown log from {handle.label}: {e}[/yellow]"
                            )
                    elif t == "heartbeat" or t.endswith("heartbeat"):
                        runtime._handle_heartbeat(handle.label, msg)
                    elif t == "status" or t.endswith("status"):
                        runtime._handle_status(handle.label, msg)
                    elif t == "ack" or t.endswith("ack"):
                        runtime._handle_agent_ack(handle.label, msg)
                        acks_count += 1
                    elif t == "error" or t.endswith("error"):
                        runtime._handle_agent_error(handle.label, msg)
                except (
                    AttributeError,
                    RuntimeError,
                    ValueError,
                    TypeError,
                ) as e:
                    runtime._debug(
                        f"[yellow]Failed to handle late shutdown message from {handle.label}: {e}[/yellow]"
                    )

        if not got_any:
            break

    # Finally, remove references to the handles now we've drained them
    try:
        for h in handles:
            exit_code = h.process.poll()
            process_exited = exit_code is not None
            if h.label in agent_results:
                agent_results[h.label]["process_exited"] = process_exited
                agent_results[h.label]["exit_code"] = exit_code
                if process_exited and agent_results[h.label]["clean_shutdown"]:
                    agent_results[h.label]["final_phase"] = "process_exit_observed"
            _write_shutdown_agent_step(
                runtime,
                agent=h.label,
                step="process",
                status="exited" if process_exited else "still_running",
                extra={"exit_code": exit_code},
            )
            if h.label in agent_results:
                _write_shutdown_agent_result(
                    runtime,
                    agent=h.label,
                    result=agent_results[h.label],
                )
            if h.label in runtime.agent_manager.agents:
                del runtime.agent_manager.agents[h.label]
            runtime._set_agent_state(h.label, "inactive", "stopped")
    except (AttributeError, RuntimeError, ValueError, TypeError, KeyError) as e:
        runtime._debug(
            f"[yellow]Failed to clear agent handles after shutdown: {e}[/yellow]"
        )

    # Flush and close sinks
    try:
        runtime._write_diagnostic_event(
            label="orchestrator",
            event="shutdown_complete",
            timestamp=datetime.now(UTC),
            data={
                "agent_count_final": len(runtime.agent_manager.agents),
                "note": "All agents shutdown and sinks closed",
                "summaries_written_during_shutdown": summaries_count,
                "logs_written_during_shutdown": logs_count,
                "acks_received_during_shutdown": acks_count,
            },
        )

        runtime.file_sink.flush()
        runtime.file_sink.close()
        if runtime.diagnostics_sink is not None:
            runtime.diagnostics_sink.flush()
            runtime.diagnostics_sink.close()
        runtime._console_print_safe("[green]MiMoLo stopped.[/green]")
        # Final console-only confirmation after sinks are closed
        runtime._console_print_safe("[green]Shutdown complete.[/green]")
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        runtime._console_print_safe(f"[red]Error closing sinks: {e}[/red]")
    finally:
        runtime._stop_ipc_server()
