# mimolo/core/ipc_slowpoke.py
"""
SLOWPOKE IPC Module - File-based fallback for legacy platforms.

⚠️  WARNING: NOT RECOMMENDED FOR PRODUCTION USE ⚠️

This module provides a file-based IPC implementation for platforms that lack
Unix domain socket support (Windows 7/8, old macOS).

PERFORMANCE CHARACTERISTICS:
- Latency: 50-200ms (vs 0.1ms for native pipes)
- Throughput: 100-500 messages/sec (vs 100,000/sec for native)
- Disk writes: CONSTANT (wears out SSDs)
- CPU overhead: 10-100x higher than native pipes
- Max agents: ~50 before system becomes unusable

USE ONLY IF:
- You CANNOT upgrade your OS
- You accept severe performance degradation
- You have <50 agents running
- You don't care about SSD wear

Like running Crysis on a software renderer - it works, but why would you?

INSTALLATION:
This module is NOT included in default builds. To enable:
  pip install mimolo[slowpoke]

Or download separately and place in mimolo/core/
"""

import json
import time
import uuid
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SlowpokeWarning(UserWarning):
    """Warning issued when SLOWPOKE module is loaded."""


# Issue warning on import
warnings.warn(
    "\n"
    "════════════════════════════════════════════════════════════\n"
    "  ⚠️ SLOWPOKE IPC MODULE LOADED ⚠️                     \n"
    "                                                       \n"
    "  You are using the file-based fallback IPC.           \n"
    "  Performance will be SEVERELY DEGRADED.               \n"
    "                                                       \n"
    "  Expected impact:                                     \n"
    "    - 100-1000x slower than native pipes               \n"
    "    - Constant disk writes (SSD wear)                  \n"
    "    - Limited to ~50 agents maximum                    \n"
    "    - High CPU usage from polling                      \n"
    "                                                       \n"
    "  PLEASE UPGRADE YOUR OS:                              \n"
    "    - Windows 10 version 1803+                         \n"
    "    - macOS 10.13+                                     \n"
    "    - Modern Linux                                     \n"
    "════════════════════════════════════════════════════════════\n",
    SlowpokeWarning,
    stacklevel=2,
)


class SlowpokeChannel:
    """File-based IPC channel (SLOW, disk-intensive)."""

    # Performance limits
    MAX_AGENTS_WARNING = 50
    MAX_AGENTS_HARD = 100
    FILE_CLEANUP_INTERVAL = 60  # Cleanup old files every 60s
    POLL_INTERVAL = 0.1  # 100ms polling; high CPU usage comes from many agents polling, not the interval itself

    def __init__(self, read_dir: str, write_dir: str, create: bool = False):
        """Initialize SLOWPOKE channel.

        Args:
            read_dir: Directory to poll for incoming messages
            write_dir: Directory to write outgoing messages
            create: If True, create directories (server mode)
        """
        self.read_dir = Path(read_dir)
        self.write_dir = Path(write_dir)
        self.create = create
        self.buffer = ""
        self.last_cleanup = time.time()

        if create:
            self.read_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.write_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Write warning file
            warning_file = self.read_dir.parent / "SLOWPOKE_WARNING.txt"
            warning_file.write_text(
                "WARNING: This IPC directory is using SLOWPOKE mode.\n"
                "Performance is severely degraded. Please upgrade your OS.\n"
                f"Created: {datetime.now(UTC).isoformat()}\n"
            )

    def read_line(self) -> str | None:
        """Poll directory for message files (SLOW)."""
        # Cleanup old files periodically
        if time.time() - self.last_cleanup > self.FILE_CLEANUP_INTERVAL:
            self._cleanup_old_files()
            self.last_cleanup = time.time()

        # Poll for .json files (sorted by name = timestamp order)
        for msg_file in sorted(self.read_dir.glob("*.json")):
            try:
                # Read and delete atomically (ish)
                data = json.loads(msg_file.read_text())
                msg_file.unlink()
                return json.dumps(data)
            except (json.JSONDecodeError, FileNotFoundError):
                # Corrupted or already deleted, skip
                msg_file.unlink(missing_ok=True)
                continue

        # No messages, sleep to avoid busy-wait
        time.sleep(self.POLL_INTERVAL)
        return None

    def write_line(self, data: dict[str, Any]) -> None:
        """Write message as file (causes disk I/O)."""
        # Generate unique filename with timestamp + UUID
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        msg_id = str(uuid.uuid4())[:8]
        filename = f"{timestamp}_{msg_id}.json"

        msg_file = self.write_dir / filename

        # Add timestamp if not present
        if "timestamp" not in data:
            data["timestamp"] = datetime.now(UTC).isoformat()

        # Write atomically (write to temp, then rename)
        temp_file = msg_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data))
        temp_file.rename(msg_file)

    def _cleanup_old_files(self) -> None:
        """Delete message files older than 5 minutes."""
        cutoff = time.time() - 300
        for directory in [self.read_dir, self.write_dir]:
            for file in directory.glob("*.json"):
                try:
                    if file.stat().st_mtime < cutoff:
                        file.unlink()
                except (FileNotFoundError, OSError):
                    pass

    def close(self) -> None:
        """Cleanup message files."""
        for directory in [self.read_dir, self.write_dir]:
            for file in directory.glob("*.json"):
                file.unlink(missing_ok=True)


def check_agent_count_sanity(agent_count: int) -> None:
    """Warn or error if too many agents for SLOWPOKE mode."""
    if agent_count > SlowpokeChannel.MAX_AGENTS_HARD:
        raise RuntimeError(
            f"SLOWPOKE mode does not support more than {SlowpokeChannel.MAX_AGENTS_HARD} agents.\n"
            f"You are trying to run {agent_count} agents.\n"
            f"Please upgrade your OS to use native IPC."
        )
    elif agent_count > SlowpokeChannel.MAX_AGENTS_WARNING:
        warnings.warn(
            f"Running {agent_count} agents in SLOWPOKE mode will cause severe performance issues.\n"
            f"Recommended maximum: {SlowpokeChannel.MAX_AGENTS_WARNING} agents.\n"
            f"Please upgrade your OS.",
            SlowpokeWarning,
            stacklevel=2,
        )


def create_slowpoke_channel(
    read_dir: str, write_dir: str, create: bool = False
) -> SlowpokeChannel:
    """Create SLOWPOKE file-based IPC channel.

    Args:
        read_dir: Directory for incoming messages
        write_dir: Directory for outgoing messages
        create: If True, create directories (server mode)

    Returns:
        SlowpokeChannel instance

    Raises:
        RuntimeError: If platform actually supports native IPC (don't use SLOWPOKE!)
    """
    # Check if native IPC is actually available
    from mimolo.core.ipc import check_platform_support

    supported, reason = check_platform_support()

    if supported:
        raise RuntimeError(
            f"SLOWPOKE module should NOT be used on this platform!\n"
            f"Your system supports native Unix sockets: {reason}\n"
            f"Remove 'slowpoke' from imports and use normal IPC."
        )

    return SlowpokeChannel(read_dir, write_dir, create)
