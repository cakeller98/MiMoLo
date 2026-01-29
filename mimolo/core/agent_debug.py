"""Helpers for optional agent debug UX (separate terminal tail)."""

from __future__ import annotations

import os
import subprocess


def open_tail_window(stderr_log_path: str) -> None:
    """Open a separate terminal window to tail a log file."""
    try:
        if os.name == "nt":
            # Use PowerShell 7+ (pwsh) to tail the file and keep the window open
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
        else:
            try:
                subprocess.Popen(["xterm", "-e", f"tail -f {stderr_log_path}"])
            except Exception:
                try:
                    subprocess.Popen(
                        [
                            "gnome-terminal",
                            "--",
                            "bash",
                            "-c",
                            f"tail -f {stderr_log_path}; exec bash",
                        ]
                    )
                except Exception:
                    subprocess.Popen(["sh", "-c", f"tail -f {stderr_log_path} &"])
    except Exception:
        pass
