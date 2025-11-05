"""Log writers (sinks) for events and segments.

Supports:
- JSONL (default): One JSON object per line
- YAML: Human-readable YAML documents
- Markdown: Summary tables
- Daily file rotation
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from mimolo.core.errors import SinkError
from mimolo.core.event import Event, Segment


class BaseSink:
    """Abstract base for log sinks."""

    def write_segment(self, segment: Segment) -> None:
        """Write a completed segment.

        Args:
            segment: Segment to write.
        """
        raise NotImplementedError

    def write_event(self, event: Event) -> None:
        """Write an infrequent/standalone event.

        Args:
            event: Event to write.
        """
        raise NotImplementedError

    def flush(self) -> None:
        """Flush any buffered data."""
        pass

    def close(self) -> None:
        """Close resources."""
        pass


class JSONLSink(BaseSink):
    """JSONL (newline-delimited JSON) sink with daily rotation."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize JSONL sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._current_file: Path | None = None
        self._file_handle: Any = None

        # Create log directory with restricted permissions
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(f"Failed to create log directory {log_dir}: {e}")

    def _get_current_file(self, timestamp: datetime) -> Path:
        """Get the log file path for the given timestamp.

        Args:
            timestamp: Timestamp to determine date.

        Returns:
            Path to log file.
        """
        date_str = timestamp.strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.{self.name_prefix}.jsonl"

    def _ensure_file_open(self, timestamp: datetime) -> None:
        """Ensure the correct file is open for writing.

        Args:
            timestamp: Timestamp to determine which file to open.
        """
        target_file = self._get_current_file(timestamp)

        # If already open and correct, nothing to do
        if self._current_file == target_file and self._file_handle is not None:
            return

        # Close old file if open
        if self._file_handle is not None:
            self._file_handle.close()

        # Open new file
        try:
            self._file_handle = open(target_file, "a", encoding="utf-8")
            self._current_file = target_file
        except Exception as e:
            raise SinkError(f"Failed to open log file {target_file}: {e}")

    def write_segment(self, segment: Segment) -> None:
        """Write segment as JSONL record.

        Args:
            segment: Segment to write.
        """
        try:
            self._ensure_file_open(segment.end)
            record = segment.to_dict()
            json.dump(record, self._file_handle, separators=(",", ":"))
            self._file_handle.write("\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write segment: {e}")

    def write_event(self, event: Event) -> None:
        """Write standalone event as JSONL record.

        Args:
            event: Event to write.
        """
        try:
            self._ensure_file_open(event.timestamp)
            record = {"type": "event", **event.to_dict()}
            json.dump(record, self._file_handle, separators=(",", ":"))
            self._file_handle.write("\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write event: {e}")

    def flush(self) -> None:
        """Flush buffered data."""
        if self._file_handle is not None:
            self._file_handle.flush()

    def close(self) -> None:
        """Close file handle."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._current_file = None


class YAMLSink(BaseSink):
    """YAML sink with daily rotation."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize YAML sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._current_file: Path | None = None
        self._file_handle: Any = None

        # Create log directory
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(f"Failed to create log directory {log_dir}: {e}")

    def _get_current_file(self, timestamp: datetime) -> Path:
        """Get the log file path for the given timestamp."""
        date_str = timestamp.strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.{self.name_prefix}.yaml"

    def _ensure_file_open(self, timestamp: datetime) -> None:
        """Ensure the correct file is open for writing."""
        target_file = self._get_current_file(timestamp)

        if self._current_file == target_file and self._file_handle is not None:
            return

        if self._file_handle is not None:
            self._file_handle.close()

        try:
            self._file_handle = open(target_file, "a", encoding="utf-8")
            self._current_file = target_file
        except Exception as e:
            raise SinkError(f"Failed to open log file {target_file}: {e}")

    def write_segment(self, segment: Segment) -> None:
        """Write segment as YAML document."""
        try:
            self._ensure_file_open(segment.end)
            record = segment.to_dict()
            yaml.dump(record, self._file_handle, default_flow_style=False, sort_keys=False)
            self._file_handle.write("---\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write segment: {e}")

    def write_event(self, event: Event) -> None:
        """Write standalone event as YAML document."""
        try:
            self._ensure_file_open(event.timestamp)
            record = {"type": "event", **event.to_dict()}
            yaml.dump(record, self._file_handle, default_flow_style=False, sort_keys=False)
            self._file_handle.write("---\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write event: {e}")

    def flush(self) -> None:
        """Flush buffered data."""
        if self._file_handle is not None:
            self._file_handle.flush()

    def close(self) -> None:
        """Close file handle."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._current_file = None


class MarkdownSink(BaseSink):
    """Markdown sink for summary tables."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize Markdown sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._segments: list[Segment] = []
        self._events: list[Event] = []
        self._current_date: str | None = None

        # Create log directory
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(f"Failed to create log directory {log_dir}: {e}")

    def write_segment(self, segment: Segment) -> None:
        """Buffer segment for markdown table."""
        self._segments.append(segment)
        self._flush_if_new_day(segment.end)

    def write_event(self, event: Event) -> None:
        """Buffer event for markdown table."""
        self._events.append(event)
        self._flush_if_new_day(event.timestamp)

    def _flush_if_new_day(self, timestamp: datetime) -> None:
        """Flush to file if we've crossed into a new day."""
        date_str = timestamp.strftime("%Y-%m-%d")
        if self._current_date and self._current_date != date_str:
            self._write_markdown_file()
            self._segments.clear()
            self._events.clear()
        self._current_date = date_str

    def _write_markdown_file(self) -> None:
        """Write accumulated segments/events as markdown table."""
        if not self._current_date:
            return

        file_path = self.log_dir / f"{self._current_date}.{self.name_prefix}.md"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# MiMoLo Log - {self._current_date}\n\n")

                if self._segments:
                    f.write("## Segments\n\n")
                    f.write("| Start | End | Duration (s) | Labels | Resets | Events |\n")
                    f.write("|-------|-----|--------------|--------|--------|--------|\n")
                    for seg in self._segments:
                        labels = ", ".join(sorted({ref.label for ref in seg.events}))
                        f.write(
                            f"| {seg.start.strftime('%H:%M:%S')} | "
                            f"{seg.end.strftime('%H:%M:%S')} | "
                            f"{seg.duration_s:.1f} | "
                            f"{labels} | "
                            f"{seg.resets_count} | "
                            f"{len(seg.events)} |\n"
                        )
                    f.write("\n")

                if self._events:
                    f.write("## Standalone Events\n\n")
                    f.write("| Timestamp | Label | Event | Data |\n")
                    f.write("|-----------|-------|-------|------|\n")
                    for evt in self._events:
                        data_str = json.dumps(evt.data) if evt.data else ""
                        f.write(
                            f"| {evt.timestamp.strftime('%H:%M:%S')} | "
                            f"{evt.label} | "
                            f"{evt.event} | "
                            f"{data_str} |\n"
                        )
                    f.write("\n")

        except Exception as e:
            raise SinkError(f"Failed to write markdown file {file_path}: {e}")

    def flush(self) -> None:
        """Flush accumulated data to file."""
        if self._segments or self._events:
            self._write_markdown_file()

    def close(self) -> None:
        """Flush and close."""
        self.flush()


class ConsoleSink(BaseSink):
    """Console output sink (for debugging/monitoring)."""

    def __init__(self, verbosity: Literal["debug", "info", "warning", "error"] = "info") -> None:
        """Initialize console sink.

        Args:
            verbosity: Console verbosity level.
        """
        self.verbosity = verbosity

    def write_segment(self, segment: Segment) -> None:
        """Print segment summary to console."""
        labels = sorted({ref.label for ref in segment.events})
        print(
            f"[SEGMENT] {segment.start.strftime('%H:%M:%S')} -> "
            f"{segment.end.strftime('%H:%M:%S')} "
            f"({segment.duration_s:.1f}s) | "
            f"Labels: {', '.join(labels)} | "
            f"Events: {len(segment.events)} | "
            f"Resets: {segment.resets_count}"
        )

    def write_event(self, event: Event) -> None:
        """Print event to console."""
        print(
            f"[EVENT] {event.timestamp.strftime('%H:%M:%S')} | "
            f"{event.label}.{event.event} | "
            f"Data: {event.data if event.data else 'None'}"
        )


def create_sink(
    format_type: Literal["jsonl", "yaml", "md"],
    log_dir: Path,
    name_prefix: str = "mimolo",
) -> BaseSink:
    """Factory function to create appropriate sink.

    Args:
        format_type: Type of sink to create.
        log_dir: Directory for log files.
        name_prefix: Prefix for log filenames.

    Returns:
        Configured sink instance.

    Raises:
        ValueError: If format_type is unknown.
    """
    if format_type == "jsonl":
        return JSONLSink(log_dir, name_prefix)
    elif format_type == "yaml":
        return YAMLSink(log_dir, name_prefix)
    elif format_type == "md":
        return MarkdownSink(log_dir, name_prefix)
    else:
        raise ValueError(f"Unknown sink format: {format_type}")
