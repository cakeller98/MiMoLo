"""Folder watch monitor plugin.

Monitors directories for file changes with specific extensions.
Demonstrates data_header with custom filter for unique sorted folders.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class FolderWatchMonitor(BaseMonitor):
    """Monitor that watches directories for file modifications.

    Emits events when files with matching extensions are modified.
    Aggregates unique parent folders during segments.
    """

    spec = PluginSpec(
        label="folderwatch",
        data_header="folders",
        resets_cooldown=True,
        infrequent=False,
        poll_interval_s=5.0,
    )

    def __init__(
        self,
        watch_dirs: list[str] | None = None,
        extensions: list[str] | None = None,
        emit_on_discovery: bool = False,
    ) -> None:
        """Initialize folder watch monitor.

        Args:
            watch_dirs: List of directory paths to watch.
            extensions: List of file extensions to monitor (without dots).
            emit_on_discovery: If True, emit an event the first time a file is seen.
        """
        self.watch_dirs = [Path(d) for d in (watch_dirs or [])]
        # Normalize extensions to be case-insensitive and dot-free
        self.extensions = {
            ext.lower().lstrip(".") for ext in (extensions or [])
        }
        self.emit_on_discovery = emit_on_discovery
        self._last_mtimes: dict[Path, float] = {}

    def emit_event(self) -> Event | None:
        """Check watched directories for file modifications.

        Returns:
            Event if a modified file is detected, None otherwise.
        """
        if not self.watch_dirs:
            return None

        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue

            # Scan directory for matching files
            try:
                for root, _dirs, files in os.walk(watch_dir):
                    root_path = Path(root)
                    for filename in files:
                        file_path = root_path / filename

                        # Check extension (case-insensitive)
                        if (
                            self.extensions
                            and file_path.suffix.lower().lstrip(".")
                            not in self.extensions
                        ):
                            continue

                        # Check modification time
                        try:
                            mtime = file_path.stat().st_mtime
                        except OSError:
                            continue

                        last_mtime = self._last_mtimes.get(file_path)

                        if last_mtime is None:
                            # First time seeing this file
                            self._last_mtimes[file_path] = mtime

                            # Optionally emit on discovery
                            if self.emit_on_discovery:
                                now = datetime.now(UTC)
                                folder = str(file_path.parent.resolve())
                                return Event(
                                    timestamp=now,
                                    label=self.spec.label,
                                    event="file_mod",
                                    data={
                                        "folders": [folder],
                                        "file": str(file_path),
                                    },
                                )
                            continue

                        if mtime > last_mtime:
                            # File was modified
                            self._last_mtimes[file_path] = mtime

                            # Emit event with parent folder
                            now = datetime.now(UTC)
                            folder = str(file_path.parent.resolve())

                            return Event(
                                timestamp=now,
                                label=self.spec.label,
                                event="file_mod",
                                data={
                                    "folders": [folder],
                                    "file": str(file_path),
                                },
                            )

            except OSError:
                # Skip directories that can't be accessed
                continue

        return None

    @staticmethod
    def filter_method(items: list[list[str]]) -> list[str]:
        """Aggregate folder paths by flattening, normalizing, and deduplicating.

        Args:
            items: List of lists of folder paths collected during segment.

        Returns:
            Sorted list of unique normalized folder paths.
        """
        # Flatten nested lists
        flat_folders = [folder for sublist in items for folder in sublist]

        # Normalize paths and deduplicate
        normalized = {str(Path(folder).resolve()) for folder in flat_folders}

        # Return sorted
        return sorted(normalized)
