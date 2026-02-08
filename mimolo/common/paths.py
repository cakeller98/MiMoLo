"""Shared path helpers for MiMoLo."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _env_path(name: str) -> Path | None:
    """Read and normalize a non-empty path env var."""
    raw = os.getenv(name)
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    return Path(text).expanduser()


def get_mimolo_data_dir() -> Path:
    """Return the OS-appropriate base data directory for MiMoLo.

    Windows: %APPDATA%/mimolo
    macOS: ~/Library/Application Support/mimolo
    Linux: $XDG_DATA_HOME/mimolo or ~/.local/share/mimolo
    """
    override = _env_path("MIMOLO_DATA_DIR")
    if override is not None:
        return override

    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mimolo"


def get_mimolo_bin_dir() -> Path:
    """Return executable root for portable/runtime tooling."""
    override = _env_path("MIMOLO_BIN_DIR")
    if override is not None:
        return override
    return get_mimolo_data_dir() / "bin"
