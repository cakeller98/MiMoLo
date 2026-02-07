#!/usr/bin/env bash
# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   ./mml.sh [command]
#   ./mml.sh operations [monitor args...]
#   ./mml.sh all-proto [monitor args...]
#   ./mml.sh all-control [monitor args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"
DEFAULT_IPC_PATH="${TMP_BASE}/mimolo/operations.sock"
CONFIG_FILE="${SCRIPT_DIR}/mml.toml"
DEFAULT_COMMAND="all"
DEFAULT_STACK="proto"
SOCKET_WAIT_SECONDS="8"

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf "%s" "$value"
}

get_toml_value() {
  local key="$1"
  local fallback="$2"
  local raw=""
  if [[ -f "$CONFIG_FILE" ]]; then
    raw="$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$CONFIG_FILE" | head -n 1 | cut -d'=' -f2- || true)"
    raw="$(trim "$raw")"
    raw="${raw%\"}"
    raw="${raw#\"}"
  fi
  if [[ -z "$raw" ]]; then
    printf "%s" "$fallback"
  else
    printf "%s" "$raw"
  fi
}

load_launcher_config() {
  DEFAULT_COMMAND="$(get_toml_value "default_command" "$DEFAULT_COMMAND")"
  DEFAULT_STACK="$(get_toml_value "default_stack" "$DEFAULT_STACK")"
  SOCKET_WAIT_SECONDS="$(get_toml_value "socket_wait_seconds" "$SOCKET_WAIT_SECONDS")"

  local config_ipc_path
  config_ipc_path="$(get_toml_value "ipc_path" "")"
  if [[ -n "$config_ipc_path" ]]; then
    DEFAULT_IPC_PATH="$config_ipc_path"
  fi
}

normalize_all_command() {
  local command="$1"
  if [[ "$command" != "all" ]]; then
    printf "%s" "$command"
    return
  fi

  if [[ "$DEFAULT_STACK" == "control" ]]; then
    printf "all-control"
  else
    printf "all-proto"
  fi
}

load_launcher_config
export MIMOLO_IPC_PATH="${MIMOLO_IPC_PATH:-$DEFAULT_IPC_PATH}"

print_usage() {
  cat <<'EOF'
MiMoLo Control Dev Launcher

Commands:
  [no command] Use default_command from mml.toml
  env         Show current MIMOLO_IPC_PATH and launch commands
  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor
  control     Launch Electron Control app (mimolo-control)
  proto       Launch Control IPC prototype (mimolo/control_proto)
  all         Alias to all-proto or all-control (default_stack in mml.toml)
  all-proto   Launch Operations in background, wait for IPC socket, then launch proto
  all-control Launch Operations in background, then launch Control app
  help        Show this message

Examples:
  ./mml.sh
  ./mml.sh env
  ./mml.sh operations --once
  ./mml.sh control
  ./mml.sh proto
  ./mml.sh all-proto
  MIMOLO_IPC_PATH=/tmp/mimolo/dev.sock ./mml.sh all-control
EOF
}

ensure_ipc_dir() {
  local ipc_dir
  ipc_dir="$(dirname "$MIMOLO_IPC_PATH")"
  mkdir -p "$ipc_dir"
}

launch_operations() {
  ensure_ipc_dir
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  poetry run python -m mimolo.cli monitor "$@"
}

launch_control() {
  ensure_ipc_dir
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  (cd "$SCRIPT_DIR/mimolo-control" && npm run start)
}

launch_proto() {
  ensure_ipc_dir
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  (cd "$SCRIPT_DIR/mimolo/control_proto" && npm run start)
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
      # If Python is unavailable, fall back to socket-file existence only.
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

  ensure_ipc_dir
  echo "[dev-stack] Starting Operations in background..."
  poetry run python -m mimolo.cli monitor "$@" &
  operations_pid=$!

  cleanup() {
    if kill -0 "$operations_pid" 2>/dev/null; then
      echo "[dev-stack] Stopping Operations (pid=$operations_pid)..."
      kill "$operations_pid" 2>/dev/null || true
    fi
  }
  trap cleanup EXIT INT TERM

  echo "[dev-stack] Operations started (pid=$operations_pid)"

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

COMMAND=""
if [[ "$#" -gt 0 ]]; then
  COMMAND="$1"
  shift
else
  COMMAND="$DEFAULT_COMMAND"
fi
COMMAND="$(normalize_all_command "$COMMAND")"

case "$COMMAND" in
  help|-h|--help)
    print_usage
    ;;
  env)
    ensure_ipc_dir
    echo "MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
    echo "export MIMOLO_IPC_PATH=\"$MIMOLO_IPC_PATH\""
    echo "default_command=$DEFAULT_COMMAND"
    echo "default_stack=$DEFAULT_STACK"
    echo "socket_wait_seconds=$SOCKET_WAIT_SECONDS"
    echo
    echo "Launch commands:"
    echo "  ./mml.sh"
    echo "  ./mml.sh operations"
    echo "  ./mml.sh control"
    echo "  ./mml.sh proto"
    echo "  ./mml.sh all-proto"
    echo "  ./mml.sh all-control"
    ;;
  operations)
    launch_operations "$@"
    ;;
  control)
    launch_control
    ;;
  proto)
    launch_proto
    ;;
  all)
    run_all_target "$DEFAULT_STACK" "$@"
    ;;
  all-proto)
    run_all_target "proto" "$@"
    ;;
  all-control)
    run_all_target "control" "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    print_usage >&2
    exit 2
    ;;
esac
