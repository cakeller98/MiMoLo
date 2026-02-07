#!/usr/bin/env bash
# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   ./start_control_dev.sh [command]
#   ./start_control_dev.sh operations [monitor args...]
#   ./start_control_dev.sh all-proto [monitor args...]
#   ./start_control_dev.sh all-control [monitor args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"
DEFAULT_IPC_PATH="${TMP_BASE}/mimolo/operations.sock"
CONFIG_FILE="${SCRIPT_DIR}/control_dev.toml"
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
  [no command] Use default_command from control_dev.toml
  env         Show current MIMOLO_IPC_PATH and launch commands
  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor
  control     Launch Electron Control app (mimolo-control)
  proto       Launch Control IPC prototype (mimolo/control_proto)
  all         Alias to all-proto or all-control (default_stack in control_dev.toml)
  all-proto   Launch Operations in background, wait for IPC socket, then launch proto
  all-control Launch Operations in background, then launch Control app
  help        Show this message

Examples:
  ./start_control_dev.sh
  ./start_control_dev.sh env
  ./start_control_dev.sh operations --once
  ./start_control_dev.sh control
  ./start_control_dev.sh proto
  ./start_control_dev.sh all-proto
  MIMOLO_IPC_PATH=/tmp/mimolo/dev.sock ./start_control_dev.sh all-control
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
  local deadline=$((SECONDS + SOCKET_WAIT_SECONDS))

  while ((SECONDS < deadline)); do
    if [[ -S "$MIMOLO_IPC_PATH" ]]; then
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
    echo "  ./start_control_dev.sh"
    echo "  ./start_control_dev.sh operations"
    echo "  ./start_control_dev.sh control"
    echo "  ./start_control_dev.sh proto"
    echo "  ./start_control_dev.sh all-proto"
    echo "  ./start_control_dev.sh all-control"
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
