"""Runtime orchestrator for MiMoLo.

The orchestrator:
- Loads configuration
- Spawns and manages Field-Agent processes
- Runs main event loop
- Handles agent IPC messages (heartbeats, summaries, logs)
- Sends flush commands to agents
- Writes output via sinks
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from rich.console import Console

from mimolo.core.config import Config
from mimolo.core.cooldown import CooldownTimer
from mimolo.core.errors import SinkError
from mimolo.core.event import Event
from mimolo.core.sink import ConsoleSink, create_sink


class Runtime:
    """Main orchestrator for MiMoLo framework."""

    def __init__(
        self,
        config: Config,
        console: Console | None = None,
    ) -> None:
        """Initialize runtime.

        Args:
            config: Configuration object.
            console: Optional rich console for output.
        """
        self.config = config
        self.console = console or Console()

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

        # Field-Agent support
        from mimolo.core.agent_process import AgentProcessManager

        self.agent_manager = AgentProcessManager(config)
        self.agent_last_flush: dict[str, datetime] = {}  # Track last flush time per agent

        # Spawn Field-Agent plugins from config
        for label, plugin_config in config.plugins.items():
            if not plugin_config.enabled:
                continue

            if plugin_config.plugin_type == "field_agent":
                if plugin_config.executable:
                    try:
                        self.agent_manager.spawn_agent(label, plugin_config)
                        self.console.print(f"[green]Spawned Field-Agent: {label}[/green]")
                    except Exception as e:
                        self.console.print(f"[red]Failed to spawn agent {label}: {e}[/red]")
                        import traceback

                        self.console.print(f"[red]{traceback.format_exc()}[/red]")

    def run(self, max_iterations: int | None = None) -> None:
        """Run the main event loop.

        Args:
            max_iterations: Optional maximum iterations (for testing/dry-run).
        """
        self._running = True
        self.console.print("[bold green]MiMoLo starting...[/bold green]")
        self.console.print(f"Cooldown: {self.config.monitor.cooldown_seconds}s")
        self.console.print(f"Poll tick: {self.config.monitor.poll_tick_ms}ms")

        agent_count = len(self.agent_manager.agents)
        self.console.print(f"Field-Agents: {agent_count}")
        self.console.print()

        if agent_count == 0:
            self.console.print("[yellow]No Field-Agents configured. Nothing to monitor.[/yellow]")
            return

        try:
            while self._running:
                self._tick()

                if max_iterations is not None:
                    max_iterations -= 1
                    if max_iterations <= 0:
                        break

                # Sleep for poll tick duration
                time.sleep(self.config.monitor.poll_tick_ms / 1000.0)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            self._shutdown()

    def _tick(self) -> None:
        """Execute one tick of the event loop."""
        self._tick_count += 1
        now = datetime.now(UTC)

        # Check for cooldown expiration
        if self.cooldown.check_expiration(now):
            self._close_segment()

        # Poll Field-Agent messages
        from mimolo.core.protocol import CommandType, OrchestratorCommand

        for label, handle in list(self.agent_manager.agents.items()):
            # Check if it's time to send flush command
            plugin_config = self.config.plugins.get(label)
            if plugin_config and plugin_config.plugin_type == "field_agent":
                last_flush = self.agent_last_flush.get(label)
                flush_interval = plugin_config.agent_flush_interval_s

                # Send flush if interval elapsed or never flushed
                if last_flush is None or (now - last_flush).total_seconds() >= flush_interval:
                    try:
                        flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
                        handle.send_command(flush_cmd)
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
                        except Exception:
                            self.console.print(f"[red]Agent {label} reported an error[/red]")
                except Exception as e:
                    self.console.print(f"[red]Error handling agent message from {label}: {e}[/red]")

    def _coerce_timestamp(self, ts: object) -> datetime:
        """Coerce a timestamp value (str or datetime) into timezone-aware datetime."""
        if isinstance(ts, datetime):
            timestamp = ts
        else:
            # Try parsing ISO format string
            try:
                timestamp = datetime.fromisoformat(str(ts))
            except Exception:
                timestamp = datetime.now(UTC)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp

    def _handle_agent_summary(self, label: str, msg: object) -> None:
        """Write Field-Agent summary directly to file.

        Field-Agents pre-aggregate their own data, so we don't re-aggregate.
        Just log the summary event directly.

        Args:
            label: agent label
            msg: parsed message object with attributes `timestamp`, `agent_label`, `data`.
        """
        try:
            ts = getattr(msg, "timestamp", None)
            timestamp = self._coerce_timestamp(ts)
            agent_label = getattr(msg, "agent_label", label)
            raw_data: Any = getattr(msg, "data", None)
            # Ensure data is always a dict
            if not isinstance(raw_data, dict):
                data: dict[str, Any] = {}
            else:
                data = cast(dict[str, Any], raw_data)

            # Determine event type if provided, else default to 'summary'
            event_type: str = "summary"
            evt = data.get("event")
            typ = data.get("type")
            if evt:
                event_type = str(evt)
            elif typ:
                event_type = str(typ)

            event = Event(timestamp=timestamp, label=agent_label, event=event_type, data=data)

            # Write summary directly to file (agent already aggregated the data)
            try:
                self.file_sink.write_event(event)
            except SinkError as e:
                self.console.print(f"[red]Sink error writing agent summary: {e}[/red]")

            # Also log to console if verbose
            if self.config.monitor.console_verbosity in ("debug", "info"):
                self.console_sink.write_event(event)

        except Exception as e:
            self.console.print(f"[red]Error handling agent summary {label}: {e}[/red]")

    def _handle_heartbeat(self, label: str, msg: object) -> None:
        """Handle a heartbeat message from a Field-Agent.

        Updates agent health state and optionally logs to console.
        Heartbeats are NOT written to file - they're for health monitoring only.
        """
        try:
            ts = getattr(msg, "timestamp", None)
            timestamp = self._coerce_timestamp(ts)

            # Update AgentProcessManager handle state if present
            agm = getattr(self, "agent_manager", None)
            if agm is not None:
                try:
                    handle = agm.agents.get(label)
                    if handle is not None:
                        handle.last_heartbeat = timestamp
                except Exception:
                    pass

            # Log to console in debug mode
            if self.config.monitor.console_verbosity == "debug":
                metrics = getattr(msg, "metrics", {})
                metrics_str = f" | {metrics}" if metrics else ""
                self.console.print(f"[cyan]❤️  {label}{metrics_str}[/cyan]")
        except Exception as e:
            self.console.print(f"[red]Error handling heartbeat from {label}: {e}[/red]")

    def _handle_agent_log(self, label: str, msg: object) -> None:
        """Handle a structured log message from a Field-Agent.

        Log messages flow through the IPC protocol and are rendered on the
        orchestrator console with Rich formatting. The orchestrator respects
        console_verbosity settings to filter log messages by level.

        Args:
            label: Agent label (plugin name)
            msg: LogMessage instance with level, message, and markup fields
        """
        try:

            # Extract log level (may be string or enum)
            level_raw = getattr(msg, "level", "info")
            if isinstance(level_raw, str):
                level = level_raw.lower()
            else:
                level = str(level_raw).lower()

            # Map verbosity setting to allowed log levels
            verbosity_map = {
                "debug": ["debug", "info", "warning", "error"],
                "info": ["info", "warning", "error"],
                "warning": ["warning", "error"],
                "error": ["error"],
            }

            allowed_levels = verbosity_map.get(
                self.config.monitor.console_verbosity, ["info", "warning", "error"]
            )

            # Filter based on verbosity
            if level not in allowed_levels:
                return

            # Extract message and markup flag
            message_text = getattr(msg, "message", "")
            markup = getattr(msg, "markup", True)

            # Pre-process message to handle Unicode issues on Windows console
            # Replace non-ASCII characters that might cause encoding errors
            try:
                # Test if the message can be encoded to the console encoding
                message_text.encode(self.console.encoding or 'utf-8')
            except (UnicodeEncodeError, AttributeError):
                # Fallback: replace non-ASCII with '?' to avoid crashes
                message_text = message_text.encode('ascii', errors='replace').decode('ascii')

            # Render with Rich console (prefix with agent label)
            prefix = f"[dim][{label}][/dim] "

            # Handle multiline messages by splitting and printing each line
            if "\n" in message_text:
                lines = message_text.split("\n")
                for line in lines:
                    if markup:
                        self.console.print(prefix + line)
                    else:
                        self.console.print(prefix + line, markup=False)
            else:
                if markup:
                    self.console.print(prefix + message_text)
                else:
                    self.console.print(prefix + message_text, markup=False)

        except Exception as e:
            # Fallback: display error without crashing
            self.console.print(f"[red]Error handling log from {label}: {e}[/red]")

    def _flush_all_agents(self) -> None:
        """Send flush command to all active Field-Agents."""
        from mimolo.core.protocol import CommandType, OrchestratorCommand

        flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
        for label, handle in self.agent_manager.agents.items():
            try:
                handle.send_command(flush_cmd)
                if self.config.monitor.console_verbosity == "debug":
                    self.console.print(f"[cyan]Sent flush to {label}[/cyan]")
            except Exception as e:
                self.console.print(f"[red]Error sending flush to {label}: {e}[/red]")

    def _close_segment(self) -> None:
        """Close current segment and flush all agents.

        Field-Agents handle their own aggregation, so this just sends flush commands.
        """
        # Send flush command to all Field-Agents
        self._flush_all_agents()

        # Close cooldown segment
        try:
            self.cooldown.close_segment()
            if self.config.monitor.console_verbosity == "debug":
                self.console.print("[blue]Segment closed[/blue]")
        except RuntimeError:
            pass  # No segment open

    def _shutdown(self) -> None:
        """Clean shutdown: flush agents and close sinks."""
        self.console.print("[yellow]Shutting down...[/yellow]")

        # Graceful stop sequence:
        # Emit an orchestrator-level event so the file log shows shutdown boundaries.
        try:
            now = datetime.now(UTC)
            agent_count = len(self.agent_manager.agents)
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
                self.file_sink.write_event(shutdown_event)
            except Exception:
                # Non-fatal - continue shutdown even if logging fails
                pass
            if self.config.monitor.console_verbosity in ("debug", "info"):
                self.console_sink.write_event(shutdown_event)
        except Exception:
            # Non-fatal; continue with shutdown
            pass

        # Graceful stop sequence using chained SEQUENCE command:
        # Send SEQUENCE([STOP, FLUSH, SHUTDOWN]) to all agents
        # Agent responds: ACK(stop) → ACK(flush) + summary → final heartbeat → exit
        # Orchestrator drains all messages and waits for responses

        # Initialize counters outside try block so they're available in except/finally
        summaries_count = 0
        logs_count = 0
        acks_count = 0

        try:
            from mimolo.core.protocol import CommandType, OrchestratorCommand

            # Send SEQUENCE command to all agents
            self.console.print(
                "[yellow]Sending shutdown sequence to Field-Agents...[/yellow]"
            )

            sequence_cmd = OrchestratorCommand(
                cmd=CommandType.SEQUENCE,
                sequence=[
                    CommandType.STOP,
                    CommandType.FLUSH,
                    CommandType.SHUTDOWN,
                ],
            )

            agents_in_shutdown = set(self.agent_manager.agents.keys())
            for label in list(agents_in_shutdown):
                handle = self.agent_manager.agents.get(label)
                if not handle:
                    continue
                try:
                    ok = handle.send_command(sequence_cmd)
                    if not ok:
                        self.console.print(
                            f"[red]Failed to send SEQUENCE to {label}[/red]"
                        )
                        agents_in_shutdown.discard(label)
                    elif self.config.monitor.console_verbosity == "debug":
                        self.console.print(
                            f"[cyan]Sent shutdown SEQUENCE to {label}[/cyan]"
                        )
                except Exception as e:
                    self.console.print(
                        f"[red]Exception sending SEQUENCE to {label}: {e}[/red]"
                    )
                    agents_in_shutdown.discard(label)

            # Track expected responses: stop ACK, flush ACK + summary
            pending_stop_ack = agents_in_shutdown.copy()
            pending_flush_response = agents_in_shutdown.copy()

            # Drain messages for up to 4 seconds total
            # Agents should respond: ACK(stop) → ACK(flush) + summary → final heartbeat → exit
            deadline = time.time() + 4.0
            while time.time() < deadline and (
                pending_stop_ack or pending_flush_response
            ):
                for label in list(agents_in_shutdown):
                    handle = self.agent_manager.agents.get(label)
                    if not handle:
                        continue

                    while (
                        msg := handle.read_message(timeout=0.01)
                    ) is not None:
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
                                    pending_stop_ack.discard(label)
                                    if (
                                        self.config.monitor.console_verbosity
                                        == "debug"
                                    ):
                                        self.console.print(
                                            f"[cyan]Agent {label} ACK(stop)[/cyan]"
                                        )
                                elif ack_cmd == "flush":
                                    # Flush ACK received, but still wait for summary
                                    if (
                                        self.config.monitor.console_verbosity
                                        == "debug"
                                    ):
                                        self.console.print(
                                            f"[cyan]Agent {label} ACK(flush)[/cyan]"
                                        )

                            elif t == "summary" or t.endswith("summary"):
                                try:
                                    self._handle_agent_summary(label, msg)
                                    summaries_count += 1
                                    pending_flush_response.discard(label)
                                    if (
                                        self.config.monitor.console_verbosity
                                        == "debug"
                                    ):
                                        self.console.print(
                                            f"[cyan]Agent {label} sent summary[/cyan]"
                                        )
                                except Exception:
                                    pass

                            elif t == "log" or t.endswith("log"):
                                try:
                                    self._handle_agent_log(label, msg)
                                    logs_count += 1
                                except Exception:
                                    pass

                            elif t == "heartbeat" or t.endswith("heartbeat"):
                                self._handle_heartbeat(label, msg)

                        except Exception:
                            pass

                time.sleep(0.01)

            # Log agents that didn't respond
            for label in pending_stop_ack:
                self.console.print(
                    f"[red]Agent {label} did not ACK STOP (timeout)[/red]"
                )
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
                    self.file_sink.write_event(stop_exception)
                except Exception:
                    pass

            for label in pending_flush_response:
                self.console.print(
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
                    self.file_sink.write_event(flush_exception)
                except Exception:
                    pass

            # Agents should have shut down by now; wait for processes to exit
            self.console.print(
                "[yellow]Waiting for Field-Agent processes to exit...[/yellow]"
            )
            handles = self.agent_manager.shutdown_all()

            # Drain any remaining messages produced during shutdown (short period)
            deadline = time.time() + 1.0
            while time.time() < deadline:
                got_any = False
                for handle in handles:
                    while (
                        msg := handle.read_message(timeout=0.01)
                    ) is not None:
                        got_any = True
                        try:
                            mtype = getattr(msg, "type", None)
                            if isinstance(mtype, str):
                                t = mtype
                            else:
                                t = str(mtype).lower()

                            if t == "summary" or t.endswith("summary"):
                                try:
                                    self._handle_agent_summary(
                                        handle.label, msg
                                    )
                                    summaries_count += 1
                                except Exception:
                                    pass
                            elif t == "log" or t.endswith("log"):
                                try:
                                    self._handle_agent_log(handle.label, msg)
                                    logs_count += 1
                                except Exception:
                                    pass
                            elif t == "heartbeat" or t.endswith("heartbeat"):
                                self._handle_heartbeat(handle.label, msg)
                        except Exception:
                            pass

                if not got_any:
                    break

            # Finally, remove references to the handles now we've drained them
            try:
                for h in handles:
                    if h.label in self.agent_manager.agents:
                        del self.agent_manager.agents[h.label]
            except Exception:
                pass

        except Exception as e:
            self.console.print(f"[red]Error shutting down agents: {e}[/red]")

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
                        "agent_count_final": len(self.agent_manager.agents),
                        "timestamp": now.isoformat(),
                        "note": "All agents shutdown and sinks closed",
                        "summaries_written_during_shutdown": summaries_count,
                        "logs_written_during_shutdown": logs_count,
                        "acks_received_during_shutdown": acks_count,
                    },
                )
                try:
                    self.file_sink.write_event(complete_event)
                except Exception:
                    # If writing the final event fails, continue to close sinks
                    pass
                if self.config.monitor.console_verbosity in ("debug", "info"):
                    self.console_sink.write_event(complete_event)
            except Exception:
                # Non-fatal - continue to closing sinks
                pass

            self.file_sink.flush()
            self.file_sink.close()
            self.console.print("[green]MiMoLo stopped.[/green]")
            # Final console-only confirmation after sinks are closed
            self.console.print("[green]Shutdown complete.[/green]")
        except Exception as e:
            self.console.print(f"[red]Error closing sinks: {e}[/red]")

    def stop(self) -> None:
        """Request graceful stop."""
        self._running = False
