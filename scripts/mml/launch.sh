# Launch and IPC wait helpers for mml launcher.

launch_operations() {
  ensure_prepared
  ensure_portable_layout
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_RUNTIME_CONFIG_PATH=$MIMOLO_RUNTIME_CONFIG_PATH"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  echo "[dev-stack] MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
  run_ops_command "$@"
}

launch_control() {
  ensure_prepared
  ensure_portable_layout
  ensure_control_build
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  echo "[dev-stack] MIMOLO_CONTROL_DEV_MODE=$MIMOLO_CONTROL_DEV_MODE"
  (cd "$SCRIPT_DIR/mimolo-control" && env -u ELECTRON_RUN_AS_NODE npm run start)
}

launch_proto() {
  ensure_prepared
  ensure_portable_layout
  ensure_proto_build
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  echo "[dev-stack] MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
  echo "[dev-stack] MIMOLO_CONTROL_DEV_MODE=$MIMOLO_CONTROL_DEV_MODE"
  (cd "$SCRIPT_DIR/mimolo/control_proto" && env -u ELECTRON_RUN_AS_NODE npm run start)
}

launch_bundle_app() {
  if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    if [[ ! -f "$SCRIPT_DIR/scripts/bundle_app.sh" ]]; then
      echo "[dev-stack] missing bundle script: $SCRIPT_DIR/scripts/bundle_app.sh" >&2
      exit 2
    fi
    "$SCRIPT_DIR/scripts/bundle_app.sh" "$@"
    return
  fi
  ensure_portable_layout
  ensure_prepared
  if [[ ! -x "$SCRIPT_DIR/scripts/bundle_app.sh" ]]; then
    echo "[dev-stack] missing or non-executable bundle script: $SCRIPT_DIR/scripts/bundle_app.sh" >&2
    exit 2
  fi
  "$SCRIPT_DIR/scripts/bundle_app.sh" "$@"
}

wait_for_ipc_socket() {
  local python_cmd=""
  if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
  elif command -v python >/dev/null 2>&1; then
    python_cmd="python"
  fi

  ipc_ping() {
    if [[ -z "$python_cmd" ]]; then
      return 0
    fi

    "$python_cmd" -c 'import socket,sys
p=sys.argv[1]
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(0.25)
s.connect(p)
s.sendall(b"{\"cmd\":\"ping\"}\n")
data=s.recv(4096).decode("utf-8","ignore")
s.close()
sys.exit(0 if "\"ok\": true" in data or "\"ok\":true" in data else 1)' "$MIMOLO_IPC_PATH" >/dev/null 2>&1
  }

  local deadline=$((SECONDS + SOCKET_WAIT_SECONDS))
  while ((SECONDS < deadline)); do
    if [[ -S "$MIMOLO_IPC_PATH" ]] && ipc_ping; then
      return 0
    fi
    if ! kill -0 "$operations_pid" 2>/dev/null; then
      echo "[dev-stack] Operations exited before socket became ready."
      return 1
    fi
    sleep 0.2
  done

  if [[ -S "$MIMOLO_IPC_PATH" ]]; then
    return 0
  fi

  echo "[dev-stack] IPC socket not ready after ${SOCKET_WAIT_SECONDS}s: $MIMOLO_IPC_PATH"
  echo "[dev-stack] Operations may not expose IPC yet in current runtime."
  return 1
}

run_all_target() {
  local target="$1"
  shift

  ensure_prepared
  ensure_portable_layout
  echo "[dev-stack] Starting Operations in background..."
  echo "[dev-stack] Portable runtime config: $MIMOLO_RUNTIME_CONFIG_PATH"

  if [[ "$target" == "proto" ]]; then
    : > "$MIMOLO_OPS_LOG_PATH"
    echo "[dev-stack] Operations log file: $MIMOLO_OPS_LOG_PATH"
    run_ops_command "$@" >"$MIMOLO_OPS_LOG_PATH" 2>&1 &
  else
    run_ops_command "$@" &
  fi
  operations_pid=$!

  echo "[dev-stack] Operations started (pid=$operations_pid)"
  if [[ "${MML_AUTOSTOP_ON_EXIT:-0}" == "1" ]]; then
    cleanup() {
      if kill -0 "$operations_pid" 2>/dev/null; then
        echo "[dev-stack] MML_AUTOSTOP_ON_EXIT=1 -> stopping Operations (pid=$operations_pid)..."
        kill "$operations_pid" 2>/dev/null || true
      fi
    }
    trap cleanup EXIT INT TERM
  else
    echo "[dev-stack] Operations will remain running after Control exits (set MML_AUTOSTOP_ON_EXIT=1 to restore auto-stop)."
  fi

  if [[ "$target" == "proto" ]]; then
    echo "[dev-stack] Waiting for IPC socket..."
    wait_for_ipc_socket || return 1
    echo "[dev-stack] IPC socket ready."
    echo "[dev-stack] Launching proto..."
    launch_proto
    return
  fi

  echo "[dev-stack] Launching Control app..."
  launch_control
}
