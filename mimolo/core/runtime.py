"""Runtime orchestrator for MiMoLo.

The orchestrator:
- Loads configuration
- Registers plugins
- Runs main event loop
- Handles plugin polling and scheduling
- Manages cooldown and segment lifecycle
- Writes output via sinks
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, cast

from rich.console import Console

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.config import Config
from mimolo.core.cooldown import CooldownState, CooldownTimer
from mimolo.core.errors import AggregationError, PluginEmitError, SinkError
from mimolo.core.event import Event
from mimolo.core.registry import PluginRegistry
from mimolo.core.sink import ConsoleSink, create_sink


class PluginScheduler:
    """Schedules plugin polling based on poll_interval_s."""

    def __init__(self) -> None:
        """Initialize scheduler."""
        self._last_poll: dict[str, float] = {}

    def should_poll(self, label: str, interval_s: float, current_time: float) -> bool:
        """Check if plugin should be polled.

        Args:
            label: Plugin label.
            interval_s: Poll interval in seconds.
            current_time: Current time (from time.time()).

        Returns:
            True if enough time has elapsed since last poll.
        """
        last = self._last_poll.get(label, 0.0)
        if current_time - last >= interval_s:
            self._last_poll[label] = current_time
            return True
        return False

    def reset(self, label: str) -> None:
        """Reset poll timer for a plugin."""
        self._last_poll.pop(label, None)


class PluginErrorTracker:
    """Tracks plugin errors and implements exponential backoff."""

    def __init__(self, base_backoff_s: float = 1.0, max_backoff_s: float = 300.0) -> None:
        """Initialize error tracker.

        Args:
            base_backoff_s: Base backoff duration.
            max_backoff_s: Maximum backoff duration.
        """
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._error_counts: dict[str, int] = defaultdict(int)
        self._backoff_until: dict[str, float] = {}

    def record_error(self, label: str) -> None:
        """Record an error for a plugin.

        Args:
            label: Plugin label.
        """
        self._error_counts[label] += 1
        count = self._error_counts[label]
        backoff = min(self.base_backoff_s * (2 ** (count - 1)), self.max_backoff_s)
        self._backoff_until[label] = time.time() + backoff

    def record_success(self, label: str) -> None:
        """Record successful operation for a plugin.

        Args:
            label: Plugin label.
        """
        self._error_counts[label] = 0
        self._backoff_until.pop(label, None)

    def is_quarantined(self, label: str) -> bool:
        """Check if plugin is in backoff period.

        Args:
            label: Plugin label.

        Returns:
            True if plugin should not be polled yet.
        """
        until = self._backoff_until.get(label)
        if until is None:
            return False
        return time.time() < until


class Runtime:
    """Main orchestrator for MiMoLo framework."""

    def __init__(
        self,
        config: Config,
        registry: PluginRegistry,
        console: Console | None = None,
    ) -> None:
        """Initialize runtime.

        Args:
            config: Configuration object.
            registry: Plugin registry with registered plugins.
            console: Optional rich console for output.
        """
        self.config = config
        self.registry = registry
        self.console = console or Console()

        # Core components
        self.cooldown = CooldownTimer(config.monitor.cooldown_seconds)
        self.aggregator = SegmentAggregator(registry)
        self.scheduler = PluginScheduler()
        self.error_tracker = PluginErrorTracker()

        # Sinks
        log_dir = Path(config.monitor.log_dir)
        log_format = cast(Literal["jsonl", "yaml", "md"], config.monitor.log_format)
        self.file_sink = create_sink(log_format, log_dir)
        self.console_sink = ConsoleSink(config.monitor.console_verbosity)

        # Runtime state
        self._running = False
        self._tick_count = 0
        # Field-Agent support (added incrementally; imports are deferred so
        # runtime can operate without the new modules present)
        try:
            from mimolo.core.agent_process import AgentProcessManager
            from mimolo.core.plugin_adapter import LegacyPluginAdapter

            self.agent_manager: AgentProcessManager | None = AgentProcessManager(config)
            self.legacy_adapters: dict[str, LegacyPluginAdapter] = {}

            # Wrap legacy plugins so they can be routed through the same
            # message handling pipeline as Field-Agents.
            for spec, instance in registry.list_all():
                try:
                    adapter = LegacyPluginAdapter(instance, spec.label)
                    self.legacy_adapters[spec.label] = adapter
                except Exception:
                    # If adapter construction fails, skip wrapping but
                    # keep existing behavior; error will surface when polled.
                    pass
        except Exception:
            # If the new modules don't exist yet, keep runtime working.
            self.agent_manager = None
            self.legacy_adapters = {}

    def run(self, max_iterations: int | None = None) -> None:
        """Run the main event loop.

        Args:
            max_iterations: Optional maximum iterations (for testing/dry-run).
        """
        self._running = True
        self.console.print("[bold green]MiMoLo starting...[/bold green]")
        self.console.print(f"Cooldown: {self.config.monitor.cooldown_seconds}s")
        self.console.print(f"Poll tick: {self.config.monitor.poll_tick_ms}ms")
        self.console.print(f"Registered plugins: {len(self.registry)}")
        self.console.print()

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
        current_time = time.time()
        now = datetime.now(UTC)

        # Check for cooldown expiration
        if self.cooldown.check_expiration(now):
            self._close_segment()
        # Poll plugins (legacy adapters if available)
        for spec, instance in self.registry.list_all():
            # Skip quarantined plugins
            if self.error_tracker.is_quarantined(spec.label):
                continue

            # Check if should poll
            if not self.scheduler.should_poll(spec.label, spec.poll_interval_s, current_time):
                continue

            try:
                adapter = (
                    self.legacy_adapters.get(spec.label)
                    if getattr(self, "legacy_adapters", None) is not None
                    else None
                )
                if adapter is not None:
                    # Use adapter that exposes a Field-Agent-like interface
                    event = adapter.emit_event()
                    if event is not None:
                        # Convert legacy Event to a summary message and route through
                        # the agent message handlers so both plugin types share logic.
                        msg = adapter.to_summary_message(event)
                        try:
                            self._handle_agent_message(msg, spec)
                            self.error_tracker.record_success(spec.label)
                        except Exception:
                            # Fall back to original behavior if routing fails
                            self._handle_event(event, spec)
                            self.error_tracker.record_success(spec.label)
                    continue

                # Fallback: direct legacy plugin polling (existing behavior)
                event = instance.emit_event()
                if event is not None:
                    self._handle_event(event, spec)
                    self.error_tracker.record_success(spec.label)
            except Exception as e:
                error = PluginEmitError(spec.label, e)
                self.console.print(f"[red]Plugin error: {error}[/red]")
                self.error_tracker.record_error(spec.label)

        # Poll Field-Agent messages (if agent manager is present)
        agm = getattr(self, "agent_manager", None)
        if agm is not None:
            for label, handle in list(agm.agents.items()):
                msg = handle.read_message(timeout=0.001)
                if msg is not None:
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
                        elif t == "error" or t.endswith("error"):
                            # Log agent-reported error
                            try:
                                message = getattr(msg, "message", None) or getattr(msg, "data", None)
                                self.console.print(f"[red]Agent {label} error: {message}[/red]")
                            except Exception:
                                self.console.print(f"[red]Agent {label} reported an error[/red]")
                    except Exception as e:
                        self.console.print(f"[red]Error handling agent message from {label}: {e}[/red]")

    def _handle_event(self, event: Event, spec: Any) -> None:
        """Handle an event from a plugin.

        Args:
            event: Event emitted by plugin.
            spec: Plugin spec.
        """
        # Write to console sink
        if self.config.monitor.console_verbosity in ("debug", "info"):
            self.console_sink.write_event(event)

        # Handle infrequent events separately
        if spec.infrequent:
            try:
                self.file_sink.write_event(event)
            except SinkError as e:
                self.console.print(f"[red]Sink error: {e}[/red]")
            return

        # Regular event: participate in segment aggregation
        if spec.resets_cooldown:
            opened = self.cooldown.on_resetting_event(event.timestamp)
            if opened and self.config.monitor.console_verbosity == "debug":
                self.console.print(f"[green]Segment opened at {event.timestamp}[/green]")
        else:
            self.cooldown.on_non_resetting_event(event.timestamp)

        # Add to aggregator if segment is active
        if self.cooldown.state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            self.aggregator.add_event(event)

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
        """Convert a Field-Agent summary message into an Event and handle it.

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

            # Create a lightweight spec-like object: Field-Agents reset cooldown by default
            spec_obj = SimpleNamespace(label=agent_label, infrequent=False, resets_cooldown=True)
            self._handle_event(event, spec_obj)
        except Exception as e:
            self.console.print(f"[red]Error handling agent summary {label}: {e}[/red]")

    def _handle_heartbeat(self, label: str, msg: object) -> None:
        """Handle a heartbeat message from a Field-Agent.

        Update agent state and optionally surface debug output.
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

            if self.config.monitor.console_verbosity == "debug":
                self.console.print(f"[cyan]Heartbeat from {label} at {timestamp.isoformat()}[/cyan]")
        except Exception as e:
            self.console.print(f"[red]Error handling heartbeat from {label}: {e}[/red]")

    def _handle_agent_message(self, msg: object, spec: Any | None = None) -> None:
        """Generic entry point for handling agent-style messages.

        This will dispatch to the appropriate specific handler based on message type.
        """
        mtype = getattr(msg, "type", None)
        try:
            if isinstance(mtype, str):
                t = mtype
            else:
                t = str(mtype).lower()

            if t == "heartbeat" or t.endswith("heartbeat"):
                self._handle_heartbeat(getattr(msg, "agent_label", "unknown"), msg)
            elif t == "summary" or t.endswith("summary"):
                self._handle_agent_summary(getattr(msg, "agent_label", "unknown"), msg)
            elif t == "error" or t.endswith("error"):
                # Log error
                self.console.print(f"[red]Agent error: {getattr(msg, 'message', None)}[/red]")
            else:
                # Unknown type: try treating as summary
                self._handle_agent_summary(getattr(msg, "agent_label", "unknown"), msg)
        except Exception as e:
            self.console.print(f"[red]Error handling agent message: {e}[/red]")

    def _close_segment(self) -> None:
        """Close current segment and write to sinks."""
        if not self.aggregator.has_events:
            # Empty segment, just close cooldown
            try:
                self.cooldown.close_segment()
            except RuntimeError:
                pass  # No segment open
            return

        try:
            segment_state = self.cooldown.close_segment()
            segment = self.aggregator.build_segment(segment_state)

            # Write to sinks
            self.console_sink.write_segment(segment)
            self.file_sink.write_segment(segment)

            if self.config.monitor.console_verbosity in ("debug", "info"):
                self.console.print(f"[blue]Segment closed: {segment.duration_s:.1f}s[/blue]")

        except AggregationError as e:
            self.console.print(f"[red]Aggregation error: {e}[/red]")
            self.aggregator.clear()
        except SinkError as e:
            self.console.print(f"[red]Sink error: {e}[/red]")
        except Exception as e:
            self.console.print(f"[red]Unexpected error closing segment: {e}[/red]")
            self.aggregator.clear()

    def _shutdown(self) -> None:
        """Clean shutdown: close any open segment and flush sinks."""
        self.console.print("[yellow]Closing open segments...[/yellow]")

        # Close any open segment
        if self.cooldown.state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            try:
                self._close_segment()
            except Exception as e:
                self.console.print(f"[red]Error during shutdown: {e}[/red]")

        # Flush and close sinks
        try:
            self.file_sink.flush()
            self.file_sink.close()
            self.console.print("[green]MiMoLo stopped.[/green]")
        except Exception as e:
            self.console.print(f"[red]Error closing sinks: {e}[/red]")

    def stop(self) -> None:
        """Request graceful stop."""
        self._running = False
