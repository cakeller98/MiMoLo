from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, Iterable

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel

CHUNKS_PER_DAY = 96
RENDER_WIDTH = 48
CHUNK_MINUTES = 15
LABEL_WIDTH_CAP = 24
BLOCK_EMPTY = " "
BLOCK_LEFT = "▌"
BLOCK_RIGHT = "▐"
BLOCK_FULL = "█"
BLOCK_FUTURE = "▒"
DEFAULT_EXCLUDED_LABELS: tuple[str, ...] = (
    "agent_template",
    "agent_example",
    "scheming_agent",
    "Floodgate",
    "Screen Shotter",
    "Agent Template",
    "Agent Example",
    "Agent Template Dup",
)
DEFAULT_LABEL_ALIASES: dict[str, str] = {
    "Watch Belker Dropbox Bedrock": "Watch Belker Dropbox",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_logs_dir() -> Path:
    return repo_root() / "logs"


@dataclass(frozen=True)
class DayActivityRecord:
    timestamp: datetime
    local_timestamp: datetime
    label: str
    event: str
    keep_alive: bool | None


@dataclass(frozen=True)
class DayBlipChart:
    target_date: date
    timezone_label: str
    time_axis: str
    all_activity_line: str
    agent_lines: list[tuple[str, str]]
    future_fill_start: int | None


def local_timezone() -> tzinfo:
    tz = datetime.now().astimezone().tzinfo
    if tz is None:
        raise RuntimeError("Local timezone is unavailable.")
    return tz


def ensure_utf8_output_streams() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except ValueError:
            continue


def format_timezone_label(reference: datetime, tz: tzinfo) -> str:
    local_reference = reference.astimezone(tz)
    tz_name = local_reference.tzname() or "local"
    offset = local_reference.strftime("%z")
    return f"{tz_name} (UTC{offset[:3]}:{offset[3:]})"


def parse_target_date(raw_value: str | None, tz: tzinfo) -> date:
    if raw_value is None:
        return datetime.now().astimezone(tz).date()
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --date value: {raw_value}") from exc


def resolve_log_paths(log_dir: Path, file_path: Path | None) -> list[Path]:
    if file_path is not None:
        resolved = file_path.expanduser().resolve()
        if not resolved.is_file():
            raise typer.BadParameter(f"Log file not found: {resolved}")
        return [resolved]

    resolved_log_dir = log_dir.expanduser().resolve()
    if not resolved_log_dir.is_dir():
        raise typer.BadParameter(f"Log directory not found: {resolved_log_dir}")

    candidates = sorted(resolved_log_dir.glob("*.mimolo.jsonl"))
    if not candidates:
        raise typer.BadParameter(f"No .mimolo.jsonl files found in: {resolved_log_dir}")
    return candidates


def parse_label_alias(alias_text: str) -> tuple[str, str]:
    if "=" not in alias_text:
        raise typer.BadParameter(f"Invalid --alias-label value: {alias_text}")
    source, target = alias_text.split("=", 1)
    source = source.strip()
    target = target.strip()
    if not source or not target:
        raise typer.BadParameter(f"Invalid --alias-label value: {alias_text}")
    return source, target


def normalize_label_filter(values: Iterable[str]) -> set[str]:
    return {value.strip() for value in values if value and value.strip()}


def build_label_aliases(alias_values: Iterable[str]) -> dict[str, str]:
    aliases = dict(DEFAULT_LABEL_ALIASES)
    for alias_value in alias_values:
        source, target = parse_label_alias(alias_value)
        aliases[source] = target
    return aliases


def clean_record_labels(
    records: Iterable[DayActivityRecord],
    *,
    aliases: dict[str, str],
    excluded_labels: set[str],
    included_labels: set[str],
) -> Iterable[DayActivityRecord]:
    for record in records:
        label = aliases.get(record.label, record.label)
        if label in excluded_labels:
            continue
        if included_labels and label not in included_labels:
            continue
        yield replace(record, label=label)


def is_lifecycle_event(event_name: str) -> bool:
    normalized = event_name.strip().lower()
    return (
        normalized.endswith("_session_open")
        or normalized.endswith("_session_close")
        or normalized.endswith("_open")
        or normalized.endswith("_close")
    )


def is_meaningful_record(record: DayActivityRecord) -> bool:
    if record.keep_alive is True or is_lifecycle_event(record.event):
        return True
    if record.keep_alive is False:
        return False
    return True


def quarter_hour_bucket(local_timestamp: datetime) -> int:
    return (local_timestamp.hour * 60 + local_timestamp.minute) // CHUNK_MINUTES


def next_quarter_hour_bucket(local_now: datetime) -> int:
    total_seconds = (
        local_now.hour * 3600 + local_now.minute * 60 + local_now.second
    )
    if local_now.microsecond:
        total_seconds += 1
    bucket = total_seconds // (CHUNK_MINUTES * 60)
    if total_seconds % (CHUNK_MINUTES * 60):
        bucket += 1
    return min(int(bucket), CHUNKS_PER_DAY - 1)


def render_bins(bins: list[bool]) -> str:
    if len(bins) != CHUNKS_PER_DAY:
        raise ValueError(f"Expected {CHUNKS_PER_DAY} bins, got {len(bins)}")

    chars: list[str] = []
    for index in range(0, CHUNKS_PER_DAY, 2):
        left = bins[index]
        right = bins[index + 1]
        if left and right:
            chars.append(BLOCK_FULL)
        elif left:
            chars.append(BLOCK_LEFT)
        elif right:
            chars.append(BLOCK_RIGHT)
        else:
            chars.append(BLOCK_EMPTY)
    return "".join(chars)


def apply_future_fill(line: str, start_index: int | None) -> str:
    if start_index is None or start_index >= len(line):
        return line

    chars = list(line)
    for index in range(max(0, start_index), len(chars)):
        if chars[index] == BLOCK_EMPTY:
            chars[index] = BLOCK_FUTURE
    return "".join(chars)


def build_time_axis() -> str:
    axis = [" "] * RENDER_WIDTH
    for hour in range(0, 24, 3):
        position = hour * 2
        label = f"{hour:02d}"
        if position + len(label) > len(axis):
            continue
        for offset, char in enumerate(label):
            axis[position + offset] = char
    return "".join(axis)


def _blank_bins() -> list[bool]:
    return [False] * CHUNKS_PER_DAY


def _coerce_keep_alive(raw_value: Any) -> bool | None:
    if isinstance(raw_value, bool):
        return raw_value
    return None


def iter_day_records(
    paths: Iterable[Path], target_date: date, tz: tzinfo
) -> Iterable[DayActivityRecord]:
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") != "event":
                    continue
                timestamp_value = payload.get("timestamp")
                if not isinstance(timestamp_value, str) or not timestamp_value.strip():
                    continue
                try:
                    timestamp = datetime.fromisoformat(timestamp_value)
                except ValueError:
                    continue
                if timestamp.tzinfo is None:
                    continue
                local_timestamp = timestamp.astimezone(tz)
                if local_timestamp.date() != target_date:
                    continue
                data = payload.get("data")
                if not isinstance(data, dict):
                    data = {}
                activity_signal = data.get("activity_signal")
                if not isinstance(activity_signal, dict):
                    activity_signal = {}
                label = payload.get("label")
                event = data.get("event") or payload.get("event") or ""
                if not isinstance(label, str):
                    label = ""
                if not isinstance(event, str):
                    event = str(event)
                yield DayActivityRecord(
                    timestamp=timestamp,
                    local_timestamp=local_timestamp,
                    label=label.strip() or "(unlabeled)",
                    event=event.strip(),
                    keep_alive=_coerce_keep_alive(activity_signal.get("keep_alive")),
                )


def build_day_blip_chart(
    records: Iterable[DayActivityRecord],
    target_date: date,
    tz: tzinfo,
    now_reference: datetime | None = None,
) -> DayBlipChart:
    agent_bins_by_label: dict[str, list[bool]] = {}

    for record in records:
        if not is_meaningful_record(record):
            continue
        bucket_index = quarter_hour_bucket(record.local_timestamp)
        bins = agent_bins_by_label.setdefault(record.label, _blank_bins())
        bins[bucket_index] = True

    all_activity_bins = _blank_bins()
    for bins in agent_bins_by_label.values():
        for index, active in enumerate(bins):
            if active:
                all_activity_bins[index] = True

    local_now = (now_reference or datetime.now().astimezone(tz)).astimezone(tz)
    future_fill_start: int | None = None
    if target_date == local_now.date():
        next_bucket = next_quarter_hour_bucket(local_now)
        future_fill_start = (next_bucket // 2) + 1

    return DayBlipChart(
        target_date=target_date,
        timezone_label=format_timezone_label(local_now, tz),
        time_axis=build_time_axis(),
        all_activity_line=render_bins(all_activity_bins),
        agent_lines=[(label, render_bins(bins)) for label, bins in agent_bins_by_label.items()],
        future_fill_start=future_fill_start,
    )


def format_chart_panel(chart: DayBlipChart) -> Panel:
    rows: list[tuple[str, str]] = [("time", chart.time_axis)]
    rows.append(
        ("all activity", apply_future_fill(chart.all_activity_line, chart.future_fill_start))
    )
    rows.extend(
        (
            label,
            apply_future_fill(line, chart.future_fill_start),
        )
        for label, line in chart.agent_lines
    )

    label_width = min(
        max(len(label) for label, _ in rows),
        LABEL_WIDTH_CAP,
    )

    def _format_label(label: str) -> str:
        if len(label) <= label_width:
            return label.ljust(label_width)
        if label_width <= 3:
            return label[:label_width]
        return (label[: label_width - 3] + "...").ljust(label_width)

    body = "\n".join(f"{_format_label(label)}  {line}" for label, line in rows)
    subtitle = "48 cols = 96 x 15m | summary = OR of visible agent rows | ▒ = future"
    return Panel.fit(
        body,
        title=f"MiMoLo Day Blips | {chart.target_date.isoformat()} | {chart.timezone_label}",
        subtitle=subtitle,
        border_style="cyan",
    )


def main(
    file: Path | None = typer.Option(None, "--file", help="Read a specific .mimolo.jsonl file."),
    date_text: str | None = typer.Option(
        None,
        "--date",
        help="Local day to render (YYYY-MM-DD). Defaults to today in local time.",
    ),
    log_dir: Path = typer.Option(
        default_logs_dir(),
        "--log-dir",
        help="Directory to scan for .mimolo.jsonl logs when --file is omitted.",
    ),
    include_label: list[str] = typer.Option(
        [],
        "--include-label",
        help="Repeat to show only specific display labels after alias/merge cleanup.",
    ),
    exclude_label: list[str] = typer.Option(
        [],
        "--exclude-label",
        help="Repeat to hide specific display labels after alias/merge cleanup.",
    ),
    alias_label: list[str] = typer.Option(
        [],
        "--alias-label",
        help="Repeat as Old Label=New Label to merge or rename labels.",
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help="Repaint the chart in place until interrupted with Ctrl+C.",
    ),
    refresh: int = typer.Option(
        300,
        "--refresh",
        min=1,
        help="Refresh interval in seconds (default 300). Only used with --live.",
    ),
) -> None:
    ensure_utf8_output_streams()
    tz = local_timezone()
    target_date = parse_target_date(date_text, tz)
    paths = resolve_log_paths(log_dir, file)
    aliases = build_label_aliases(alias_label)
    excluded_labels = set(DEFAULT_EXCLUDED_LABELS)
    excluded_labels.update(normalize_label_filter(exclude_label))
    included_labels = normalize_label_filter(include_label)

    def _render_panel() -> Panel:
        records = list(iter_day_records(paths, target_date, tz))
        records = list(
            clean_record_labels(
                records,
                aliases=aliases,
                excluded_labels=excluded_labels,
                included_labels=included_labels,
            )
        )
        chart = build_day_blip_chart(records, target_date, tz)
        return format_chart_panel(chart)

    console = Console()

    if not live:
        console.print(_render_panel())
        return

    with Live(console=console) as live_display:
        try:
            while True:
                now = datetime.now().astimezone(tz)
                timestamp = now.strftime("%H:%M:%S %Z")
                live_display.update(Group(
                    _render_panel(),
                    f"  [dim]refreshed {timestamp} · next in {refresh}s · Ctrl+C to quit[/dim]",
                ))
                time.sleep(refresh)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    typer.run(main)
