#!/usr/bin/env bash
# Launch MiMoLo Control/Operations dev targets in portable-test mode by default.
# Usage:
#   ./mml.sh [command]
#   ./mml.sh operations [monitor args...]
#   ./mml.sh all-proto [monitor args...]
#   ./mml.sh all-control [monitor args...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE="${SCRIPT_DIR}/mml.toml"
DEFAULT_COMMAND="all-proto"
DEFAULT_STACK="proto"
SOCKET_WAIT_SECONDS="8"

PORTABLE_ROOT_DEFAULT="${SCRIPT_DIR}/temp_debug"
CONFIG_PORTABLE_ROOT=""
CONFIG_DATA_DIR=""
CONFIG_BIN_DIR=""
CONFIG_RUNTIME_CONFIG_PATH=""
CONFIG_CONFIG_SOURCE_PATH=""
CONFIG_IPC_PATH=""
CONFIG_OPS_LOG_PATH=""
CONFIG_MONITOR_LOG_DIR=""
CONFIG_MONITOR_JOURNAL_DIR=""
CONFIG_MONITOR_CACHE_DIR=""
CONFIG_DEPLOY_AGENTS_DEFAULT=""

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

  CONFIG_PORTABLE_ROOT="$(get_toml_value "portable_root" "")"
  CONFIG_DATA_DIR="$(get_toml_value "data_dir" "")"
  CONFIG_BIN_DIR="$(get_toml_value "bin_dir" "")"
  CONFIG_RUNTIME_CONFIG_PATH="$(get_toml_value "runtime_config_path" "")"
  CONFIG_CONFIG_SOURCE_PATH="$(get_toml_value "config_source_path" "")"
  CONFIG_IPC_PATH="$(get_toml_value "ipc_path" "")"
  CONFIG_OPS_LOG_PATH="$(get_toml_value "operations_log_path" "")"
  CONFIG_MONITOR_LOG_DIR="$(get_toml_value "monitor_log_dir" "")"
  CONFIG_MONITOR_JOURNAL_DIR="$(get_toml_value "monitor_journal_dir" "")"
  CONFIG_MONITOR_CACHE_DIR="$(get_toml_value "monitor_cache_dir" "")"
  CONFIG_DEPLOY_AGENTS_DEFAULT="$(get_toml_value "deploy_agents_default" "")"
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

apply_environment_defaults() {
  local portable_root="${CONFIG_PORTABLE_ROOT:-$PORTABLE_ROOT_DEFAULT}"
  local derived_data_dir="${portable_root}/user_home/mimolo"
  local derived_bin_dir="${portable_root}/bin"

  export MIMOLO_DATA_DIR="${MIMOLO_DATA_DIR:-${CONFIG_DATA_DIR:-$derived_data_dir}}"
  export MIMOLO_BIN_DIR="${MIMOLO_BIN_DIR:-${CONFIG_BIN_DIR:-$derived_bin_dir}}"
  export PATH="${MIMOLO_BIN_DIR}:${PATH}"

  local derived_runtime_config="${MIMOLO_DATA_DIR}/operations/mimolo.portable.toml"
  local derived_config_source="${SCRIPT_DIR}/mimolo.toml"
  export MIMOLO_RUNTIME_CONFIG_PATH="${MIMOLO_RUNTIME_CONFIG_PATH:-${CONFIG_RUNTIME_CONFIG_PATH:-$derived_runtime_config}}"
  export MIMOLO_CONFIG_SOURCE_PATH="${MIMOLO_CONFIG_SOURCE_PATH:-${CONFIG_CONFIG_SOURCE_PATH:-$derived_config_source}}"

  local derived_ipc_path="${MIMOLO_DATA_DIR}/runtime/operations.sock"
  local derived_ops_log_path="${MIMOLO_DATA_DIR}/runtime/operations.log"
  export MIMOLO_IPC_PATH="${MIMOLO_IPC_PATH:-${CONFIG_IPC_PATH:-$derived_ipc_path}}"
  export MIMOLO_OPS_LOG_PATH="${MIMOLO_OPS_LOG_PATH:-${CONFIG_OPS_LOG_PATH:-$derived_ops_log_path}}"

  local derived_monitor_log_dir="${MIMOLO_DATA_DIR}/operations/logs"
  local derived_monitor_journal_dir="${MIMOLO_DATA_DIR}/operations/journals"
  local derived_monitor_cache_dir="${MIMOLO_DATA_DIR}/operations/cache"
  export MIMOLO_MONITOR_LOG_DIR="${MIMOLO_MONITOR_LOG_DIR:-${CONFIG_MONITOR_LOG_DIR:-$derived_monitor_log_dir}}"
  export MIMOLO_MONITOR_JOURNAL_DIR="${MIMOLO_MONITOR_JOURNAL_DIR:-${CONFIG_MONITOR_JOURNAL_DIR:-$derived_monitor_journal_dir}}"
  export MIMOLO_MONITOR_CACHE_DIR="${MIMOLO_MONITOR_CACHE_DIR:-${CONFIG_MONITOR_CACHE_DIR:-$derived_monitor_cache_dir}}"
}

ensure_portable_layout() {
  mkdir -p "$MIMOLO_DATA_DIR"
  mkdir -p "$MIMOLO_BIN_DIR"
  mkdir -p "$(dirname "$MIMOLO_IPC_PATH")"
  mkdir -p "$(dirname "$MIMOLO_OPS_LOG_PATH")"
  mkdir -p "$MIMOLO_MONITOR_LOG_DIR"
  mkdir -p "$MIMOLO_MONITOR_JOURNAL_DIR"
  mkdir -p "$MIMOLO_MONITOR_CACHE_DIR"
  mkdir -p "$(dirname "$MIMOLO_RUNTIME_CONFIG_PATH")"

  if [[ ! -f "$MIMOLO_RUNTIME_CONFIG_PATH" ]]; then
    if [[ ! -f "$MIMOLO_CONFIG_SOURCE_PATH" ]]; then
      echo "[dev-stack] Missing config source: $MIMOLO_CONFIG_SOURCE_PATH" >&2
      exit 2
    fi
    cp "$MIMOLO_CONFIG_SOURCE_PATH" "$MIMOLO_RUNTIME_CONFIG_PATH"
    echo "[dev-stack] Seeded runtime config: $MIMOLO_RUNTIME_CONFIG_PATH"
  fi
}

has_config_arg() {
  for arg in "$@"; do
    case "$arg" in
      -c|--config|--config=*)
        return 0
        ;;
    esac
  done
  return 1
}

run_monitor_command() {
  local -a monitor_args=("$@")
  local -a cmd=(poetry run python -m mimolo.cli monitor)
  if ! has_config_arg "$@"; then
    cmd+=(--config "$MIMOLO_RUNTIME_CONFIG_PATH")
  fi
  if ((${#monitor_args[@]} > 0)); then
    cmd+=("${monitor_args[@]}")
  fi
  "${cmd[@]}"
}

run_prepare() {
  ensure_portable_layout
  local -a prepare_cmd=(
    "$SCRIPT_DIR/scripts/deploy_portable.sh"
    --data-dir "$MIMOLO_DATA_DIR"
    --bin-dir "$MIMOLO_BIN_DIR"
    --runtime-config "$MIMOLO_RUNTIME_CONFIG_PATH"
    --config-source "$MIMOLO_CONFIG_SOURCE_PATH"
  )
  if [[ -n "$CONFIG_DEPLOY_AGENTS_DEFAULT" ]]; then
    prepare_cmd+=(--agents "$CONFIG_DEPLOY_AGENTS_DEFAULT")
  fi
  if ((${#@} > 0)); then
    prepare_cmd+=("$@")
  fi
  "${prepare_cmd[@]}"
}

ensure_prepared() {
  local manifest="$MIMOLO_BIN_DIR/deploy-manifest.json"
  if [[ -f "$manifest" ]]; then
    return
  fi
  echo "[dev-stack] Portable bin not prepared; running deploy once..."
  run_prepare
}

print_usage() {
  cat <<'EOF'
MiMoLo Portable Dev Launcher

Commands:
  [no command] Use default_command from mml.toml
  prepare     Build/sync portable bin artifacts and seed default agents
  env         Show effective environment and launch commands
  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor
  control     Launch Electron Control app (mimolo-control)
  proto       Launch Control IPC prototype (mimolo/control_proto)
  all         Alias to all-proto or all-control (default_stack in mml.toml)
  all-proto   Launch Operations in background, wait for IPC socket, then launch proto
  all-control Launch Operations in background, then launch Control app
  help        Show this message

Notes:
  - Portable mode is default: MIMOLO_DATA_DIR and MIMOLO_BIN_DIR are always set.
  - Operations uses a runtime config at MIMOLO_RUNTIME_CONFIG_PATH unless --config is passed explicitly.

Examples:
  ./mml.sh
  ./mml.sh prepare
  ./mml.sh env
  ./mml.sh operations --once
  ./mml.sh proto
  ./mml.sh all-proto
EOF
}

launch_operations() {
  ensure_prepared
  ensure_portable_layout
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_RUNTIME_CONFIG_PATH=$MIMOLO_RUNTIME_CONFIG_PATH"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  echo "[dev-stack] MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
  run_monitor_command "$@"
}

launch_control() {
  ensure_prepared
  ensure_portable_layout
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  (cd "$SCRIPT_DIR/mimolo-control" && env -u ELECTRON_RUN_AS_NODE npm run start)
}

launch_proto() {
  ensure_prepared
  ensure_portable_layout
  echo "[dev-stack] MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
  echo "[dev-stack] MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
  echo "[dev-stack] MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
  echo "[dev-stack] MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
  (cd "$SCRIPT_DIR/mimolo/control_proto" && env -u ELECTRON_RUN_AS_NODE npm run start)
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
    run_monitor_command "$@" >"$MIMOLO_OPS_LOG_PATH" 2>&1 &
  else
    run_monitor_command "$@" &
  fi
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

load_launcher_config
apply_environment_defaults

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
    ensure_portable_layout
    echo "MIMOLO_DATA_DIR=$MIMOLO_DATA_DIR"
    echo "MIMOLO_BIN_DIR=$MIMOLO_BIN_DIR"
    echo "MIMOLO_RUNTIME_CONFIG_PATH=$MIMOLO_RUNTIME_CONFIG_PATH"
    echo "MIMOLO_CONFIG_SOURCE_PATH=$MIMOLO_CONFIG_SOURCE_PATH"
    echo "MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
    echo "MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
    echo "MIMOLO_MONITOR_LOG_DIR=$MIMOLO_MONITOR_LOG_DIR"
    echo "MIMOLO_MONITOR_JOURNAL_DIR=$MIMOLO_MONITOR_JOURNAL_DIR"
    echo "MIMOLO_MONITOR_CACHE_DIR=$MIMOLO_MONITOR_CACHE_DIR"
    echo "default_command=$DEFAULT_COMMAND"
    echo "default_stack=$DEFAULT_STACK"
    echo "socket_wait_seconds=$SOCKET_WAIT_SECONDS"
    echo
    echo "Launch commands:"
    echo "  ./mml.sh"
    echo "  ./mml.sh prepare"
    echo "  ./mml.sh operations"
    echo "  ./mml.sh control"
    echo "  ./mml.sh proto"
    echo "  ./mml.sh all-proto"
    echo "  ./mml.sh all-control"
    ;;
  operations)
    launch_operations "$@"
    ;;
  prepare)
    run_prepare "$@"
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
