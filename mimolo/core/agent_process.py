"""Agent subprocess management and communication."""

from __future__ import annotations

import errno
import logging
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

from pydantic import ValidationError

from mimolo.common.paths import get_mimolo_data_dir
from mimolo.core.protocol import (
    AgentMessage,
    OrchestratorCommand,
    parse_agent_message,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentHandle:
    """Runtime handle for a Agent subprocess."""

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

                # Log raw line for diagnostics then parse and enqueue message
                logger.debug(f"[{self.label}] RECV: {line.rstrip()}")

                msg = parse_agent_message(line)
                self.outbound_queue.put(msg)

                # Update heartbeat tracker
                if msg.type == "heartbeat":
                    self.last_heartbeat = msg.timestamp

            except (OSError, ValueError, ValidationError) as e:
                # Log error but keep reading
                logger.error(f"[{self.label}] Parse error: {e}")

    def send_command(self, cmd: OrchestratorCommand) -> bool:
        """Write command to agent stdin.

        Returns:
            True if the command was written, False otherwise.
        """
        if self.process.poll() is not None:
            return False  # Process dead

        if self.process.stdin is None:
            return False

        try:
            json_line = cmd.model_dump_json() + "\n"
        except ValueError as e:
            pid = self.process.pid
            logger.error(
                f"Agent {self.label} (pid={pid}) command serialization error: {e}"
            )
            return False

        try:
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
            return True
        except OSError as e:
            pid = self.process.pid
            logger.error(
                f"Agent {self.label} (pid={pid}) command send error: {e}"
            )
            return False

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

        # Send shutdown command but keep the stdout reader running so we
        # can capture any final JSON lines the agent writes on shutdown.
        ok = self.send_command(OrchestratorCommand(cmd=CommandType.SHUTDOWN))
        if not ok:
            pid = self.process.pid
            logger.warning(
                f"Agent {self.label} (pid={pid}) failed to send shutdown command (stdin closed?)"
            )

        # Wait up to 3 seconds for clean exit while the reader thread
        # continues to consume stdout. If the process doesn't exit in
        # time, forcefully terminate it.
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            try:
                self.process.kill()
            except OSError as e:
                logger.warning(
                    f"[{self.label}] Failed to kill agent after timeout: {e}"
                )
            self.process.wait()

        # Now stop the reader loop and join the thread to ensure all
        # queued messages have been processed by the orchestrator.
        self._running = False
        if self._stdout_thread is not None and self._stdout_thread.is_alive():
            try:
                self._stdout_thread.join(timeout=1.0)
            except RuntimeError as e:
                logger.warning(
                    f"[{self.label}] Failed to join stdout reader thread: {e}"
                )


class AgentProcessManager:
    """Spawns and manages Agent subprocesses."""

    def __init__(self, config: Any):  # Config type
        """Initialize manager.

        Args:
            config: Main configuration object
        """
        self.config = config
        self.agents: dict[str, AgentHandle] = {}

    def _allowed_agent_roots(self) -> tuple[Path, Path]:
        """Return filesystem roots allowed for agent script execution."""
        workspace_agents_root = (Path(__file__).parent.parent / "agents").resolve()
        installed_agents_root = (
            get_mimolo_data_dir() / "operations" / "plugins" / "agents"
        ).resolve()
        return workspace_agents_root, installed_agents_root

    def _is_within_root(self, target: Path, root: Path) -> bool:
        """Check whether target is within root after path normalization."""
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_agent_script_arg(self, arg: str) -> str:
        """Resolve one python script arg inside allowed roots."""
        candidate = Path(arg)
        allowed_roots = self._allowed_agent_roots()

        probe_paths: list[Path]
        if candidate.is_absolute():
            probe_paths = [candidate]
        else:
            probe_paths = [root / candidate for root in allowed_roots]

        for probe in probe_paths:
            try:
                resolved = probe.resolve()
            except OSError:
                continue
            if not resolved.exists() or not resolved.is_file():
                continue
            if any(self._is_within_root(resolved, root) for root in allowed_roots):
                return str(resolved)

        allowed_text = ", ".join(str(root) for root in allowed_roots)
        raise FileNotFoundError(
            f"Agent script not found or outside allowed roots: {arg} (allowed_roots: {allowed_text})"
        )

    def spawn_agent(self, label: str, plugin_config: Any) -> AgentHandle:
        """Spawn a Agent subprocess.

        Args:
            label: Plugin label
            plugin_config: PluginConfig for this agent

        Returns:
            AgentHandle for managing the subprocess
        """
        # Resolve agent script path - only allow from trusted agent roots.
        args_with_resolved_path: list[str] = []
        for arg in plugin_config.args:
            if arg.endswith(".py"):
                args_with_resolved_path.append(self._resolve_agent_script_arg(arg))
            else:
                args_with_resolved_path.append(arg)

        # Build command
        cmd = [plugin_config.executable] + args_with_resolved_path

        # Spawn process. We capture stderr so we can forward it (with a
        # prefix) into the orchestrator console and optionally mirror it
        # into a separate terminal window for debugging.
        popen_kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,  # Line buffered
        }
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", None)
            if creationflags is None:
                raise RuntimeError(
                    "CREATE_NEW_PROCESS_GROUP flag unavailable on this Windows build."
                )
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True

        env = os.environ.copy()
        env["MIMOLO_AGENT_LABEL"] = label
        env["MIMOLO_AGENT_ID"] = f"{label}-{uuid.uuid4().hex[:8]}"
        env["MIMOLO_DATA_DIR"] = str(get_mimolo_data_dir())
        proc = subprocess.Popen(cmd, env=env, **popen_kwargs)

        # Create handle and start reader
        handle = AgentHandle(label=label, process=proc, config=plugin_config)
        handle.start_reader()

        # Start a thread to forward agent stderr to the orchestrator console
        # (prefixed) and optionally into a temp log file. If the plugin
        # requests a separate terminal, we will open one that tails the
        # temp log so the developer can see colorful rich output in its
        # own window while Agent JLP remains via pipes.
        launch_sep = bool(
            getattr(plugin_config, "launch_in_separate_terminal", False)
        )

        stderr_log_path = None
        if launch_sep:
            # Prepare a temp log file for tailing
            logs_dir = get_mimolo_data_dir() / "logs"
            try:
                logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            except OSError as e:
                if e.errno in {errno.EPERM, errno.EACCES}:
                    logs_dir = Path(tempfile.gettempdir()) / "mimolo" / "logs"
                    logs_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                    logger.warning(
                        f"[{label}] Data dir unavailable; using temp logs at {logs_dir}."
                    )
                else:
                    raise

            tmp = logs_dir / f"mimolo_agent_{label}_{uuid.uuid4().hex[:8]}.log"
            stderr_log_path = str(tmp)
            # Create the log file immediately so PowerShell can tail it.
            try:
                fd = os.open(stderr_log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(f"# MiMoLo Agent Log: {label}\n")
                    f.write(f"# Started at {datetime.now(UTC).isoformat()}\n\n")
            except OSError as e:
                logger.warning(
                    f"[{label}] Failed to initialize stderr log at {stderr_log_path}: {e}"
                )
                stderr_log_path = None

        def _stderr_forwarder(
            p: subprocess.Popen[str], lbl: str, log_path: str | None
        ) -> None:
            try:
                if p.stderr is None:
                    return
                for raw in p.stderr:
                    # Ensure we keep the original newlines.
                    line = raw.rstrip("\n")
                    logger.info(f"[{lbl}][STD_ERR] {line}")
                    if log_path:
                        try:
                            with open(
                                log_path,
                                "a",
                                encoding="utf-8",
                                errors="ignore",
                            ) as f:
                                f.write(raw)
                        except OSError as e:
                            logger.warning(
                                f"[{lbl}] Failed to append stderr log to {log_path}: {e}"
                            )
                            # Disable further log file attempts after first failure.
                            log_path = None
            except OSError as e:
                logger.warning(
                    f"[{lbl}] Stderr forwarder crashed: {e}"
                )

        _stderr_thread = threading.Thread(
            target=_stderr_forwarder,
            args=(proc, label, stderr_log_path),
            daemon=True,
            name=f"agent-stderr-{label}",
        )
        _stderr_thread.start()
        handle._stderr_thread = _stderr_thread
        handle.stderr_log = stderr_log_path

        self.agents[label] = handle
        return handle

    def shutdown_all(self) -> list[AgentHandle]:
        """Shutdown all managed agents and return their handles.

        Returns:
            List of `AgentHandle` objects for any callers that want to
            drain outstanding messages after the agents exit.
        """
        handles = list(self.agents.values())
        for handle in handles:
            if handle.is_alive():
                handle.shutdown()

        # Do not clear `self.agents` here — let the caller decide when to
        # discard handles after draining any outstanding messages.
        return handles
