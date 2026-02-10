"""IPC server helpers for Runtime."""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mimolo.core.ipc import MAX_SOCKET_PATH_LENGTH

if TYPE_CHECKING:
    from mimolo.core.runtime import Runtime

def handle_ipc_line(runtime: Runtime, line: str) -> dict[str, Any]:
    """Parse one JSON-line request and produce a response."""
    now = datetime.now(UTC).isoformat()
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return {"ok": False, "timestamp": now, "error": "invalid_json"}

    if not isinstance(payload, dict):
        return {"ok": False, "timestamp": now, "error": "invalid_payload"}
    request = cast(dict[str, Any], payload)
    response = runtime._build_ipc_response(request)
    request_id_raw = request.get("request_id")
    request_id = (
        str(request_id_raw).strip()
        if request_id_raw is not None and str(request_id_raw).strip()
        else ""
    )
    if request_id:
        response["request_id"] = request_id
    return response

def send_ipc_response(conn: socket.socket, payload: dict[str, Any]) -> bool:
    """Send a single JSON-line response to an IPC client."""
    try:
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        return True
    except OSError:
        # OSError: client may disconnect while response is being written.
        return False

def serve_ipc_connection(runtime: Runtime, conn: socket.socket) -> None:
    """Serve one IPC client connection until disconnect/stop."""
    conn.settimeout(0.2)
    buffer = ""

    while not runtime._ipc_stop_event.is_set():
        try:
            chunk = conn.recv(4096)
        except TimeoutError:
            continue
        except OSError:
            # OSError: client socket may close/reset unexpectedly.
            return

        if not chunk:
            return

        try:
            buffer += chunk.decode("utf-8")
        except UnicodeDecodeError:
            response = {
                "ok": False,
                "timestamp": datetime.now(UTC).isoformat(),
                "error": "invalid_utf8",
            }
            send_ipc_response(conn, response)
            return

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            response = handle_ipc_line(runtime, line)
            if not send_ipc_response(conn, response):
                return

def ipc_server_loop(runtime: Runtime) -> None:
    """Accept IPC connections and process control commands."""
    if not runtime._ipc_socket_path:
        return

    socket_path = runtime._ipc_socket_path
    if len(socket_path) > MAX_SOCKET_PATH_LENGTH:
        runtime.console.print(
            f"[red]IPC socket path too long ({len(socket_path)} > {MAX_SOCKET_PATH_LENGTH}).[/red]"
        )
        return

    socket_dir = Path(socket_path).parent
    socket_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime._cleanup_ipc_socket_file()

    server_sock: socket.socket | None = None
    try:
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(socket_path)
        try:
            os.chmod(socket_path, 0o600)
        except OSError as e:
            # OSError: chmod can fail on some filesystems; keep IPC alive with existing perms.
            runtime._debug(f"[yellow]IPC socket chmod failed: {e}[/yellow]")
        server_sock.listen(4)
        server_sock.settimeout(0.2)
        runtime._ipc_server_socket = server_sock
        runtime._debug(f"[dim]IPC server listening at {socket_path}[/dim]")

        while not runtime._ipc_stop_event.is_set():
            try:
                conn, _ = server_sock.accept()
            except TimeoutError:
                continue
            except OSError:
                # OSError: listener may be closed during shutdown.
                if runtime._ipc_stop_event.is_set():
                    break
                continue
            ipc_conn_thread = threading.Thread(
                target=serve_ipc_client_thread,
                args=(runtime, conn),
                name="mimolo-ipc-client",
                daemon=True,
            )
            ipc_conn_thread.start()
    except OSError as e:
        # OSError: bind/listen can fail due path/permission conflicts.
        runtime.console.print(f"[red]IPC server failed to start: {e}[/red]")
    finally:
        if server_sock is not None:
            try:
                server_sock.close()
            except OSError:
                # OSError: best-effort close on shutdown path.
                pass
        runtime._ipc_server_socket = None
        runtime._cleanup_ipc_socket_file()

def serve_ipc_client_thread(runtime: Runtime, conn: socket.socket) -> None:
    """Serve one IPC client connection on its own thread."""
    with conn:
        serve_ipc_connection(runtime, conn)
