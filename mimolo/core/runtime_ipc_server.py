"""IPC server helpers for Runtime."""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from mimolo.core.errors import SinkError
from mimolo.core.event import Event
from mimolo.core.ipc import (
    AF_UNIX,
    MAX_SOCKET_PATH_LENGTH,
    derive_slowpoke_dirs,
    effective_ipc_mode,
)

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
    try:
        response = runtime._build_ipc_response(request)
        if request_id:
            response["request_id"] = request_id
        return response
    except Exception as exc:
        runtime._console_print_safe(
            f"[red]IPC request handling failed: {type(exc).__name__}: {exc}[/red]"
        )
        runtime._write_diagnostic_event(
            label="orchestrator",
            event="ipc_request_error",
            timestamp=datetime.now(UTC),
            data={
                "request": request,
                "request_id": request_id or None,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return {
            "ok": False,
            "timestamp": now,
            "error": "ipc_request_exception",
            "data": {
                "request_id": request_id or None,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        }

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

    mode = effective_ipc_mode(getattr(runtime, "_ipc_mode", "auto"))
    if mode == "slowpoke":
        _ipc_server_loop_slowpoke(runtime)
        return

    if AF_UNIX == -1:
        runtime._console_print_safe(
            "[red]IPC disabled: this Python build does not provide AF_UNIX sockets.[/red]"
        )
        return

    socket_path = runtime._ipc_socket_path
    if len(socket_path) > MAX_SOCKET_PATH_LENGTH:
        runtime._console_print_safe(
            f"[red]IPC socket path too long ({len(socket_path)} > {MAX_SOCKET_PATH_LENGTH}).[/red]"
        )
        return

    socket_dir = Path(socket_path).parent
    socket_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime._cleanup_ipc_socket_file()

    server_sock: socket.socket | None = None
    try:
        server_sock = socket.socket(AF_UNIX, socket.SOCK_STREAM)
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
        runtime._console_print_safe(f"[red]IPC server failed to start: {e}[/red]")
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


def _cleanup_slowpoke_json(directory: Path) -> None:
    """Remove stale slowpoke message files from a directory."""
    if not directory.exists():
        return
    for file in directory.glob("*.json"):
        try:
            file.unlink(missing_ok=True)
        except OSError:
            continue
    for file in directory.glob("*.tmp"):
        try:
            file.unlink(missing_ok=True)
        except OSError:
            continue


def _emit_ipc_failure_alert(
    runtime: Runtime,
    *,
    event: str,
    error: Exception,
    mode: str,
    root_dir: str | None = None,
) -> None:
    """Emit a visible orchestrator event for IPC failure conditions."""
    timestamp = datetime.now(UTC)
    data: dict[str, Any] = {
        "error_type": type(error).__name__,
        "error": str(error),
        "ipc_mode": mode,
        "ipc_socket_path": runtime._ipc_socket_path,
        "ipc_slowpoke_root": root_dir,
        "user_action": "restart_ops_required",
        "severity": "critical",
    }
    runtime._write_diagnostic_event(
        label="orchestrator",
        event=event,
        timestamp=timestamp,
        data=data,
    )
    try:
        runtime.file_sink.write_event(
            Event(
                timestamp=timestamp,
                label="orchestrator",
                event=event,
                data=data,
            )
        )
    except SinkError:
        runtime._debug("[yellow]Failed writing IPC failure alert to file sink.[/yellow]")


def _ipc_server_loop_slowpoke(runtime: Runtime) -> None:
    """Serve IPC requests through the file-backed slowpoke transport."""
    from mimolo.core.ipc_slowpoke import SlowpokeChannel

    socket_path = runtime._ipc_socket_path or ""
    root_dir, control_to_ops_dir, ops_to_control_dir = derive_slowpoke_dirs(
        socket_path,
        getattr(runtime, "_ipc_slowpoke_root", None),
    )
    control_to_ops_path = Path(control_to_ops_dir)
    ops_to_control_path = Path(ops_to_control_dir)
    root_path = Path(root_dir)
    root_path.mkdir(parents=True, exist_ok=True)
    _cleanup_slowpoke_json(control_to_ops_path)
    _cleanup_slowpoke_json(ops_to_control_path)

    channel: SlowpokeChannel | None = None
    try:
        channel = SlowpokeChannel(
            read_dir=control_to_ops_dir,
            write_dir=ops_to_control_dir,
            create=True,
        )
        runtime._ipc_slowpoke_channel = channel
        runtime._debug(f"[dim]IPC server listening in slowpoke mode at {root_dir}[/dim]")
        while not runtime._ipc_stop_event.is_set():
            try:
                line = channel.read_line()
            except OSError as exc:
                runtime._console_print_safe(
                    f"[red]IPC slowpoke read failed: {type(exc).__name__}: {exc}[/red]"
                )
                _emit_ipc_failure_alert(
                    runtime,
                    event="ipc_slowpoke_read_error",
                    error=exc,
                    mode="slowpoke",
                    root_dir=root_dir,
                )
                continue
            if not line:
                continue
            try:
                response = handle_ipc_line(runtime, line)
                channel.write_line(response)
            except Exception as exc:
                runtime._console_print_safe(
                    f"[red]IPC slowpoke loop failed: {type(exc).__name__}: {exc}[/red]"
                )
                runtime._write_diagnostic_event(
                    label="orchestrator",
                    event="ipc_slowpoke_loop_error",
                    timestamp=datetime.now(UTC),
                    data={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
    except OSError as e:
        runtime._console_print_safe(
            f"[red]IPC slowpoke server failed to start: {e}[/red]"
        )
        _emit_ipc_failure_alert(
            runtime,
            event="ipc_slowpoke_server_failure",
            error=e,
            mode="slowpoke",
            root_dir=root_dir,
        )
    finally:
        if channel is not None:
            channel.close()
        runtime._ipc_slowpoke_channel = None
