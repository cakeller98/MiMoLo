"""Helpers for optional agent debug UX (separate terminal tail)."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys

logger = logging.getLogger(__name__)


def _open_tail_window_windows(stderr_log_path: str) -> None:
    # Use PowerShell 7+ (pwsh) to tail the file and keep the window open.
    try:
        tail_cmd = [
            "cmd",
            "/c",
            "start",
            "",
            "pwsh",
            "-NoProfile",
            "-NoExit",
            "-Command",
            f"Get-Content -Path '{stderr_log_path}' -Wait",
        ]
        subprocess.Popen(tail_cmd)
    except FileNotFoundError:
        # Fallback to Windows PowerShell if pwsh is unavailable.
        tail_cmd = [
            "cmd",
            "/c",
            "start",
            "",
            "powershell",
            "-NoProfile",
            "-NoExit",
            "-Command",
            f"Get-Content -Path '{stderr_log_path}' -Wait",
        ]
        subprocess.Popen(tail_cmd)


def _open_tail_window_macos(stderr_log_path: str) -> None:
    # Use Terminal.app to open a new window and tail the log file.
    try:
        # Quote the file path for shell safety (spaces, special chars).
        tail_command = f"tail -f {shlex.quote(stderr_log_path)}"
        escaped_command = tail_command.replace("\\", "\\\\").replace(
            '"', '\\"'
        )
        script = (
            f'tell application "Terminal" to do script "{escaped_command}"'
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "unknown error"
            logger.warning(
                "Failed to open macOS tail window (osascript error): %s",
                detail,
            )
    except FileNotFoundError:
        # osascript missing on PATH; cannot launch Terminal on macOS.
        logger.warning("Failed to open macOS tail window (osascript not found).")


def _open_tail_window_linux(stderr_log_path: str) -> None:
    try:
        subprocess.Popen(["xterm", "-e", "tail", "-f", stderr_log_path])
        return
    except FileNotFoundError:
        # xterm not available; try gnome-terminal.
        pass

    try:
        subprocess.Popen(
            [
                "gnome-terminal",
                "--",
                "tail",
                "-f",
                stderr_log_path,
            ]
        )
    except FileNotFoundError:
        # Neither xterm nor gnome-terminal available on this host.
        logger.warning(
            "Failed to open Linux tail window (xterm/gnome-terminal not found)."
        )


def open_tail_window(stderr_log_path: str) -> None:
    """Open a separate terminal window to tail a log file."""
    if os.name == "nt":
        _open_tail_window_windows(stderr_log_path)
        return

    elif sys.platform == "darwin":
        _open_tail_window_macos(stderr_log_path)
        return

    else:
        # Assume Linux/Unix if not Windows or macOS.
        _open_tail_window_linux(stderr_log_path)
        return
