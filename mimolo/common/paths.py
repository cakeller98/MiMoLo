"""Shared path helpers for MiMoLo."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def get_mimolo_data_dir() -> Path:
    """Return the OS-appropriate base data directory for MiMoLo.

    Windows: %APPDATA%/mimolo
    macOS: ~/Library/Application Support/mimolo
    Linux: $XDG_DATA_HOME/mimolo or ~/.local/share/mimolo
    """
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "mimolo"
