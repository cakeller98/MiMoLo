"""Field-Agent subprocess management and communication."""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from mimolo.core.protocol import (
    AgentMessage,
    OrchestratorCommand,
    parse_agent_message,
)


@dataclass
class AgentHandle:
    """Runtime handle for a Field-Agent subprocess."""

    label: str
    process: subprocess.Popen[str]
    config: Any  # PluginConfig

    # Communication queues
    outbound_queue: Queue[AgentMessage] = field(default_factory=lambda: Queue())

    # State tracking
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None
    agent_id: str | None = None
    health: str = "starting"

    # Threads
    _stdout_thread: threading.Thread | None = None
    _stderr_thread: threading.Thread | None = None
    stderr_log: str | None = None
    _running: bool = True

    def start_reader(self) -> None:
        """Start stdout reader thread."""
        self._stdout_thread = threading.Thread(
            target=self._read_stdout_loop, daemon=True, name=f"agent-reader-{self.label}"
        )
        self._stdout_thread.start()

    def _read_stdout_loop(self) -> None:
        """Read JSON lines from agent stdout."""
        if self.process.stdout is None:
            return

        while self._running and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Parse and enqueue message
                msg = parse_agent_message(line)
                self.outbound_queue.put(msg)

                # Update heartbeat tracker
                if msg.type == "heartbeat":
                    self.last_heartbeat = msg.timestamp

            except Exception as e:
                # Log error but keep reading
                print(f"[{self.label}] Parse error: {e}")

    def send_command(self, cmd: OrchestratorCommand) -> None:
        """Write command to agent stdin."""
        if self.process.poll() is not None:
            return  # Process dead

        if self.process.stdin is None:
            return

        try:
            json_line = cmd.model_dump_json() + "\n"
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
        except Exception as e:
            print(f"[{self.label}] Command send error: {e}")

    def read_message(self, timeout: float = 0.001) -> AgentMessage | None:
        """Non-blocking read from message queue."""
        try:
            return self.outbound_queue.get(timeout=timeout)
        except Empty:
            return None

    def is_alive(self) -> bool:
        """Check if process is running."""
        return self.process.poll() is None

    def shutdown(self) -> None:
        """Send shutdown command and wait."""
        from mimolo.core.protocol import CommandType

        self._running = False
        self.send_command(OrchestratorCommand(cmd=CommandType.SHUTDOWN))

        # Wait up to 3 seconds for clean exit
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


class AgentProcessManager:
    """Spawns and manages Field-Agent subprocesses."""

    def __init__(self, config: Any):  # Config type
        """Initialize manager.

        Args:
            config: Main configuration object
        """
        self.config = config
        self.agents: dict[str, AgentHandle] = {}

    def spawn_agent(self, label: str, plugin_config: Any) -> AgentHandle:
        """Spawn a Field-Agent subprocess.

        Args:
            label: Plugin label
            plugin_config: PluginConfig for this agent

        Returns:
            AgentHandle for managing the subprocess
        """
        # Resolve agent script path - only allow from user_plugins or plugins directories
        args_with_resolved_path: list[str] = []
        for arg in plugin_config.args:
            if arg.endswith(".py"):
                # Try user_plugins first, then plugins
                user_path = Path(__file__).parent.parent / "user_plugins" / arg
                plugins_path = Path(__file__).parent.parent / "plugins" / arg

                if user_path.exists():
                    args_with_resolved_path.append(str(user_path.resolve()))
                elif plugins_path.exists():
                    args_with_resolved_path.append(str(plugins_path.resolve()))
                else:
                    raise FileNotFoundError(
                        f"Field-Agent script not found: {arg} (searched user_plugins and plugins)"
                    )
            else:
                args_with_resolved_path.append(arg)

        # Build command
        cmd = [plugin_config.executable] + args_with_resolved_path

        # Spawn process. We capture stderr so we can forward it (with a
        # prefix) into the orchestrator console and optionally mirror it
        # into a separate terminal window for debugging.
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Create handle and start reader
        handle = AgentHandle(label=label, process=proc, config=plugin_config)
        handle.start_reader()

        # Start a thread to forward agent stderr to the orchestrator console
        # (prefixed) and optionally into a temp log file. If the plugin
        # requests a separate terminal, we will open one that tails the
        # temp log so the developer can see colorful rich output in its
        # own window while IPC remains via pipes.
        launch_sep = bool(
            getattr(plugin_config, "launch_in_separate_terminal", False)
        )

        stderr_log_path = None
        if launch_sep:
            # Prepare a temp log file for tailing
            tmp = (
                Path(tempfile.gettempdir())
                / f"mimolo_agent_{label}_{uuid.uuid4().hex[:8]}.log"
            )
            stderr_log_path = str(tmp)

        def _stderr_forwarder(
            p: subprocess.Popen[str], lbl: str, log_path: str | None
        ) -> None:
            try:
                if p.stderr is None:
                    return
                for raw in p.stderr:
                    # Ensure we keep the original newlines.
                    line = raw.rstrip("\n")
                    print(f"[{lbl}][ERR] {line}")
                    if log_path:
                        try:
                            with open(
                                log_path,
                                "a",
                                encoding="utf-8",
                                errors="ignore",
                            ) as f:
                                f.write(raw)
                        except Exception:
                            pass
            except Exception:
                pass

        _stderr_thread = threading.Thread(
            target=_stderr_forwarder,
            args=(proc, label, stderr_log_path),
            daemon=True,
            name=f"agent-stderr-{label}",
        )
        _stderr_thread.start()
        handle._stderr_thread = _stderr_thread
        handle.stderr_log = stderr_log_path

        # If requested, open a separate terminal that tails the log file
        if launch_sep and stderr_log_path:
            try:
                if os.name == "nt":
                    # Use PowerShell to tail the file and keep the window open
                    tail_cmd = [
                        "cmd",
                        "/c",
                        "start",
                        "",
                        "powershell",
                        "-NoProfile",
                        "-NoExit",
                        "-Command",
                        "Get-Content -Path @args[0] -Wait",
                        stderr_log_path,
                    ]
                    subprocess.Popen(tail_cmd)
                else:
                    # Try common terminals on *nix
                    try:
                        subprocess.Popen(
                            ["xterm", "-e", f"tail -f {stderr_log_path}"]
                        )
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
                            # Last resort: background `tail -f` (no window)
                            subprocess.Popen(
                                ["sh", "-c", f"tail -f {stderr_log_path} &"]
                            )
            except Exception:
                # Non-fatal — just don't open the separate window
                pass

        self.agents[label] = handle
        return handle

    def shutdown_all(self) -> None:
        """Shutdown all managed agents."""
        for handle in self.agents.values():
            handle.shutdown()
        self.agents.clear()
