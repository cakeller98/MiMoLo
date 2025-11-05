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
from typing import Any

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
        self.file_sink = create_sink(config.monitor.log_format, log_dir)
        self.console_sink = ConsoleSink(config.monitor.console_verbosity)

        # Runtime state
        self._running = False
        self._tick_count = 0

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

        # Poll plugins
        for spec, instance in self.registry.list_all():
            # Skip quarantined plugins
            if self.error_tracker.is_quarantined(spec.label):
                continue

            # Check if should poll
            if not self.scheduler.should_poll(spec.label, spec.poll_interval_s, current_time):
                continue

            # Emit event
            try:
                event = instance.emit_event()
                if event is not None:
                    self._handle_event(event, spec)
                    self.error_tracker.record_success(spec.label)
            except Exception as e:
                error = PluginEmitError(spec.label, e)
                self.console.print(f"[red]Plugin error: {error}[/red]")
                self.error_tracker.record_error(spec.label)

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
