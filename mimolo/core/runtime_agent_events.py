"""Agent event handling helpers for Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from mimolo.core.errors import SinkError
from mimolo.core.event import Event

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime

def coerce_timestamp(runtime: Runtime, ts: object) -> datetime:
    """Coerce a timestamp value (str or datetime) into timezone-aware datetime."""
    if isinstance(ts, datetime):
        timestamp = ts
    else:
        # Try parsing ISO format string
        try:
            timestamp = datetime.fromisoformat(str(ts))
        except (TypeError, ValueError):
            timestamp = datetime.now(UTC)

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp


def handle_agent_summary(runtime: Runtime, label: str, msg: object) -> None:
    """Write agent summary directly to file."""
    try:
        ts = getattr(msg, "timestamp", None)
        timestamp = coerce_timestamp(runtime, ts)
        agent_label = getattr(msg, "agent_label", label)
        raw_data: Any = getattr(msg, "data", None)
        if not isinstance(raw_data, dict):
            data: dict[str, Any] = {}
        else:
            data = cast(dict[str, Any], raw_data)

        event_type: str = "summary"
        summary_event = data.get("summary_event")
        evt = data.get("event")
        if summary_event:
            event_type = str(summary_event)
        elif evt:
            event_type = str(evt)

        event = Event(timestamp=timestamp, label=agent_label, event=event_type, data=data)
        runtime.agent_last_summary[label] = data

        try:
            runtime.file_sink.write_event(event)
        except SinkError as e:
            runtime.console.print(f"[red]Sink error writing agent summary: {e}[/red]")

        if runtime.config.monitor.console_verbosity in ("debug", "info"):
            runtime.console_sink.write_event(event)

    except (AttributeError, TypeError, ValueError, RuntimeError) as e:
        runtime.console.print(f"[red]Error handling agent summary {label}: {e}[/red]")


def handle_heartbeat(runtime: Runtime, label: str, msg: object) -> None:
    """Handle a heartbeat message from an agent."""
    try:
        ts = getattr(msg, "timestamp", None)
        timestamp = coerce_timestamp(runtime, ts)

        agm = getattr(runtime, "agent_manager", None)
        if agm is not None:
            try:
                handle = agm.agents.get(label)
                if handle is not None:
                    handle.last_heartbeat = timestamp
            except (AttributeError, RuntimeError, TypeError, ValueError) as e:
                runtime._debug(
                    f"[yellow]Failed to update heartbeat for {label}: {e}[/yellow]"
                )

        if runtime.config.monitor.console_verbosity == "debug":
            metrics = getattr(msg, "metrics", {})
            metrics_str = f" | {metrics}" if metrics else ""
            runtime.console.print(f"[cyan]❤️  {label}{metrics_str}[/cyan]")
        raw_metrics = getattr(msg, "metrics", {})
        metrics_payload: dict[str, Any]
        if isinstance(raw_metrics, dict):
            metrics_payload = cast(dict[str, Any], raw_metrics)
        else:
            metrics_payload = {}
        runtime._write_diagnostic_event(
            label=label,
            event="heartbeat",
            timestamp=timestamp,
            data={"metrics": metrics_payload},
        )
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        runtime.console.print(f"[red]Error handling heartbeat from {label}: {e}[/red]")


def handle_agent_log(runtime: Runtime, label: str, msg: object) -> None:
    """Handle a structured log message from an agent."""
    level_raw = getattr(msg, "level", "info")
    if isinstance(level_raw, str):
        level = level_raw.lower()
    else:
        level = str(level_raw).lower()

    verbosity_map = {
        "debug": ["debug", "info", "warning", "error"],
        "info": ["info", "warning", "error"],
        "warning": ["warning", "error"],
        "error": ["error"],
    }

    allowed_levels = verbosity_map.get(
        runtime.config.monitor.console_verbosity,
        ["info", "warning", "error"],
    )

    if level not in allowed_levels:
        return

    message_text = getattr(msg, "message", "")
    markup = getattr(msg, "markup", True)

    try:
        message_text.encode(runtime.console.encoding or "utf-8")
    except (UnicodeEncodeError, AttributeError) as e:
        runtime._debug(
            f"[yellow]Log message encoding mismatch for {label}: {e}[/yellow]"
        )
        message_text = message_text.encode(
            "ascii", errors="replace"
        ).decode("ascii")

    prefix = f"[grey70][{label}][/grey70] "

    try:
        if "\n" in message_text:
            lines = message_text.split("\n")
            for line in lines:
                if markup:
                    runtime.console.print(prefix + line)
                else:
                    runtime.console.print(prefix + line, markup=False)
        else:
            if markup:
                runtime.console.print(prefix + message_text)
            else:
                runtime.console.print(prefix + message_text, markup=False)
    except (AttributeError, RuntimeError, TypeError, ValueError) as e:
        runtime.console.print(
            f"[red]Error rendering log from {label} (markup={markup}): {e}[/red]"
        )
    runtime._write_diagnostic_event(
        label=label,
        event="log",
        timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
        data={
            "level": level,
            "message": message_text,
            "markup": bool(markup),
        },
    )


def handle_agent_error(runtime: Runtime, label: str, msg: object) -> None:
    """Handle an error message from an agent."""
    error_message = getattr(msg, "message", None) or getattr(msg, "data", None)
    runtime.console.print(f"[red]Agent {label} error: {error_message}[/red]")
    runtime._write_diagnostic_event(
        label=label,
        event="error",
        timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
        data={"message": str(error_message)},
    )


def handle_agent_ack(runtime: Runtime, label: str, msg: object) -> None:
    """Handle an ack message from an agent."""
    ack_command_raw = getattr(msg, "ack_command", None)
    ack_command = (
        str(ack_command_raw).strip()
        if ack_command_raw is not None and str(ack_command_raw).strip()
        else "unknown"
    )
    runtime._write_diagnostic_event(
        label=label,
        event="ack",
        timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
        data={
            "ack_command": ack_command,
            "message": str(getattr(msg, "message", "")),
        },
    )


def handle_status(runtime: Runtime, label: str, msg: object) -> None:
    """Handle a status message from an agent."""
    runtime._write_diagnostic_event(
        label=label,
        event="status",
        timestamp=coerce_timestamp(runtime, getattr(msg, "timestamp", None)),
        data={"data": getattr(msg, "data", {})},
    )
