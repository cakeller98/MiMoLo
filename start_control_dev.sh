#!/usr/bin/env bash
# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   ./start_control_dev.sh env
#   ./start_control_dev.sh operations [monitor args...]
#   ./start_control_dev.sh control
#   ./start_control_dev.sh proto
#   ./start_control_dev.sh all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"
DEFAULT_IPC_PATH="${TMP_BASE}/mimolo/operations.sock"
export MIMOLO_IPC_PATH="${MIMOLO_IPC_PATH:-$DEFAULT_IPC_PATH}"

print_usage() {
  cat <<'EOF'
MiMoLo Control Dev Launcher

Commands:
  env         Show current MIMOLO_IPC_PATH and launch commands
  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor
  control     Launch Electron Control app (mimolo-control)
  proto       Launch Control IPC prototype (mimolo/control_proto)
  all         Launch Operations in background, then launch Control app
  help        Show this message

Examples:
  ./start_control_dev.sh env
  ./start_control_dev.sh operations --once
  ./start_control_dev.sh control
  ./start_control_dev.sh proto
  MIMOLO_IPC_PATH=/tmp/mimolo/dev.sock ./start_control_dev.sh all
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

COMMAND="${1:-help}"
if [[ "$#" -gt 0 ]]; then
  shift
fi

case "$COMMAND" in
  help|-h|--help)
    print_usage
    ;;
  env)
    ensure_ipc_dir
    echo "MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
    echo "export MIMOLO_IPC_PATH=\"$MIMOLO_IPC_PATH\""
    echo
    echo "Launch commands:"
    echo "  ./start_control_dev.sh operations"
    echo "  ./start_control_dev.sh control"
    echo "  ./start_control_dev.sh proto"
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
    echo "[dev-stack] Launching Control app..."
    launch_control
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    print_usage >&2
    exit 2
    ;;
esac
