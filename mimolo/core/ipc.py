# mimolo/core/ipc.py
"""Generic IPC using Unix domain sockets (Windows 10+, macOS, Linux only)."""

import json
import logging
import os
import platform as _platform
import socket
from pathlib import Path
from typing import Any, cast

MIN_WINDOWS_VERSION = "10.0.17063"  # First Windows with AF_UNIX support
MIN_MACOS_VERSION = "10.13"  # High Sierra

# Resolve AF_UNIX in a mypy-friendly way: cast the getattr result to int.
# If AF_UNIX is missing at runtime, we'll detect and fail when creating sockets.
AF_UNIX: int = cast(int, getattr(socket, "AF_UNIX", -1))

# Re-export platform module for tests to monkeypatch (test_ipc_support).
platform = _platform

# Maximum socket path length (conservative for cross-platform compatibility)
MAX_SOCKET_PATH_LENGTH = 100  # Unix typically allows ~108, Windows ~256

logger = logging.getLogger(__name__)


def _check_af_unix_support() -> None:
    """Check if AF_UNIX is actually available at runtime.

    Raises:
        RuntimeError: If AF_UNIX not available
    """
    if AF_UNIX == -1:
        raise RuntimeError(
            "Unix domain sockets (AF_UNIX) not available.\n"
            "This usually means:\n"
            "  - Windows older than Windows 10 version 1803\n"
            "  - Python version older than 3.9 (on Windows)\n"
            "  - Unsupported platform\n"
            "\n"
            "Solutions:\n"
            "  1. Upgrade to Windows 10 version 1803+ (recommended)\n"
            "  2. Upgrade Python to 3.9+ (if on Windows)\n"
            "  3. Use SLOWPOKE fallback (not recommended)\n"
        )


class MessageChannel:
    """Bidirectional JSON-line channel over Unix domain socket."""

    def __init__(self, socket_path: str, server: bool = False) -> None:
        """Initialize channel.

        Args:
            socket_path: Filesystem path for Unix socket
            server: If True, bind and listen. If False, connect.

        Raises:
            ValueError: If socket_path is too long
            RuntimeError: If AF_UNIX not supported
        """
        # Validate socket path length
        if len(socket_path) > MAX_SOCKET_PATH_LENGTH:
            raise ValueError(
                f"Socket path too long ({len(socket_path)} chars, max {MAX_SOCKET_PATH_LENGTH}).\n"
                f"Unix sockets limit path length to ~108 characters.\n"
                f"Path: {socket_path}\n"
                f"Consider using a shorter path or /tmp directory."
            )

        self.socket_path: str = socket_path
        self.server: bool = server
        self.sock: socket.socket | None = None
        self.conn: socket.socket | None = None
        self.buffer: str = ""

        if server:
            self._create_server()
        else:
            self._connect_client()

    def _create_server(self) -> None:
        """Create server socket and wait for connection.

        Raises:
            RuntimeError: If socket creation fails
        """
        # Ensure parent directory exists
        Path(self.socket_path).parent.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )

        # Remove stale socket file
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            # Socket file already absent; nothing to clean.
            logger.debug(
                f"IPC socket file already absent before bind: {self.socket_path}"
            )

        try:
            # Create and bind socket
            server_sock = socket.socket(AF_UNIX, socket.SOCK_STREAM)
            server_sock.bind(self.socket_path)
            self.sock = server_sock

            # Set permissions (owner-only)
            os.chmod(self.socket_path, 0o600)

            # Listen and accept one connection
            assert self.sock is not None
            self.sock.listen(1)
            conn, _ = self.sock.accept()
            conn.setblocking(False)  # Non-blocking reads
            self.conn = conn

        except OSError as e:
            raise RuntimeError(
                f"Failed to create server socket: {e}\n"
                f"Socket path: {self.socket_path}"
            ) from e

    def _connect_client(self) -> None:
        """Connect to existing server socket.

        Raises:
            RuntimeError: If connection fails with helpful error message
        """
        try:
            client_sock = socket.socket(AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(self.socket_path)
            client_sock.setblocking(False)
            self.conn = client_sock

        except FileNotFoundError as e:
            raise RuntimeError(
                f"Orchestrator not running (socket not found).\n"
                f"Socket path: {self.socket_path}\n"
                f"Start the orchestrator first."
            ) from e

        except ConnectionRefusedError as e:
            raise RuntimeError(
                f"Orchestrator not accepting connections.\n"
                f"Socket exists but connection refused.\n"
                f"Socket path: {self.socket_path}\n"
                f"The orchestrator may be shutting down or crashed."
            ) from e

        except PermissionError as e:
            raise RuntimeError(
                f"Permission denied accessing socket.\n"
                f"Socket path: {self.socket_path}\n"
                f"Check file permissions (should be 0600, owner-only)."
            ) from e

        except OSError as e:
            raise RuntimeError(
                f"Failed to connect to socket: {e}\n"
                f"Socket path: {self.socket_path}"
            ) from e

    def read_line(self) -> str | None:
        """Read one JSON line. Returns None if no data available."""
        import select

        if self.conn is None:
            return None

        # Check if data available (non-blocking)
        ready, _, _ = select.select([self.conn], [], [], 0.01)
        if not ready:
            return None

        # Read available data
        try:
            chunk = self.conn.recv(4096)
            if not chunk:  # Connection closed
                return None
            self.buffer += chunk.decode("utf-8")
        except BlockingIOError:
            return None
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Socket read failed for {self.socket_path}: {e}")
            return None

        # Extract one line if available
        if "\n" not in self.buffer:
            return None

        line, self.buffer = self.buffer.split("\n", 1)
        return line.strip()

    def write_line(self, data: dict[str, Any]) -> None:
        """Write one JSON line.

        Raises:
            RuntimeError: If not connected
        """
        if self.conn is None:
            raise RuntimeError(
                "Not connected. Cannot write to closed channel."
            )

        msg = json.dumps(data) + "\n"
        try:
            self.conn.sendall(msg.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError) as e:
            raise RuntimeError(f"Connection lost while writing: {e}") from e

    def close(self) -> None:
        """Close connection and cleanup."""
        if self.conn is not None:
            try:
                self.conn.close()
            except OSError as e:
                logger.warning(
                    f"Failed to close IPC connection {self.socket_path}: {e}"
                )
            self.conn = None

        if self.sock is not None:
            try:
                self.sock.close()
            except OSError as e:
                logger.warning(
                    f"Failed to close IPC server socket {self.socket_path}: {e}"
                )
            self.sock = None

        if self.server:
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                # Cleanup is idempotent; missing socket on close is expected.
                logger.debug(
                    f"IPC socket file already removed at close: {self.socket_path}"
                )
            except OSError as e:
                logger.warning(
                    f"Failed to remove IPC socket file {self.socket_path}: {e}"
                )


def check_platform_support() -> tuple[bool, str]:
    """Check if platform supports Unix domain sockets.

    Returns:
        (supported: bool, reason: str)
    """
    import sys

    plat = platform  # use module-level platform (monkeypatch-friendly)

    if sys.platform == "win32":
        # Windows 10 build 17063+ required
        version = plat.version()
        try:
            build = int(version.split(".")[-1]) if "." in version else 0
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Failed to parse Windows build from version '{version}': {e}"
            )
            build = 0
        if build < 17063:
            return (
                False,
                f"Windows build {build} < 17063 (requires Windows 10 version 1803+)",
            )
        return True, "Windows 10+ with Unix socket support"

    elif sys.platform == "darwin":
        # macOS 10.13+ recommended
        version = (plat.mac_ver()[0] if hasattr(plat, "mac_ver") else "0.0")
        parts = version.split(".")
        try:
            major = int(parts[0]) if len(parts) > 0 and parts[0] else 0
            minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Failed to parse macOS version '{version}': {e}"
            )
            major, minor = 0, 0
        if major < 10 or (major == 10 and minor < 13):
            return False, f"macOS {version} < 10.13"
        return True, f"macOS {version}"

    elif sys.platform.startswith("linux"):
        # All modern Linux supports AF_UNIX
        rel = plat.release() if hasattr(plat, "release") else "unknown"
        return True, f"Linux {rel}"

    else:
        return False, f"Unsupported platform: {sys.platform}"


def create_ipc_channel(
    socket_path: str, server: bool = False
) -> MessageChannel:
    """Create IPC channel.

    Args:
        socket_path: Path to Unix domain socket
        server: True = create and listen, False = connect

    Returns:
        MessageChannel instance

    Raises:
        RuntimeError: If platform doesn't support Unix sockets or AF_UNIX unavailable
        ValueError: If socket_path is too long
    """
    # Check AF_UNIX availability first
    _check_af_unix_support()

    # Check platform support
    supported, reason = check_platform_support()
    if not supported:
        raise RuntimeError(
            f"Platform not supported: {reason}\n"
            f"\n"
            f"MiMoLo requires:\n"
            f"  - Windows 10 version 1803+ (build 17063+)\n"
            f"  - macOS 10.13+\n"
            f"  - Linux kernel 2.6+\n"
            f"\n"
            f"Consider:\n"
            f"  1. Upgrading your OS (recommended)\n"
            f"  2. Using SLOWPOKE fallback (pip install mimolo[slowpoke])"
        )

    return MessageChannel(socket_path, server)
