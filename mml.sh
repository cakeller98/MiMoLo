#!/usr/bin/env bash
# Launch MiMoLo Control/Operations dev targets in portable-test mode by default.
# Usage:
#   ./mml.sh [command]
#   ./mml.sh --no-cache [command]
#   ./mml.sh --rebuild-dist [command]
#   ./mml.sh --dev [command]
#   ./mml.sh operations [monitor args...]
#   ./mml.sh all-proto [monitor args...]
#   ./mml.sh all-control [monitor args...]
#   ./mml.sh bundle-app [bundle args...]

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
CONFIG_RELEASE_AGENTS_PATH=""
CONFIG_BUNDLE_TARGET_DEFAULT=""
CONFIG_BUNDLE_OUT_DIR=""
CONFIG_BUNDLE_VERSION_DEFAULT=""
CONFIG_BUNDLE_APP_NAME_PROTO=""
CONFIG_BUNDLE_APP_NAME_CONTROL=""
CONFIG_BUNDLE_BUNDLE_ID_PROTO=""
CONFIG_BUNDLE_BUNDLE_ID_CONTROL=""
CONFIG_BUNDLE_DEV_MODE_DEFAULT=""
EFFECTIVE_PORTABLE_ROOT=""
NO_CACHE=0
DEV_MODE=0
IPC_SOCKET_MAX_LENGTH=100

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
  CONFIG_RELEASE_AGENTS_PATH="$(get_toml_value "release_agents_path" "")"
  CONFIG_BUNDLE_TARGET_DEFAULT="$(get_toml_value "bundle_target_default" "")"
  CONFIG_BUNDLE_OUT_DIR="$(get_toml_value "bundle_out_dir" "")"
  CONFIG_BUNDLE_VERSION_DEFAULT="$(get_toml_value "bundle_version_default" "")"
  CONFIG_BUNDLE_APP_NAME_PROTO="$(get_toml_value "bundle_app_name_proto" "")"
  CONFIG_BUNDLE_APP_NAME_CONTROL="$(get_toml_value "bundle_app_name_control" "")"
  CONFIG_BUNDLE_BUNDLE_ID_PROTO="$(get_toml_value "bundle_bundle_id_proto" "")"
  CONFIG_BUNDLE_BUNDLE_ID_CONTROL="$(get_toml_value "bundle_bundle_id_control" "")"
  CONFIG_BUNDLE_DEV_MODE_DEFAULT="$(get_toml_value "bundle_dev_mode_default" "")"
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

to_abs_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf "%s" "$path"
  else
    printf "%s/%s" "$SCRIPT_DIR" "$path"
  fi
}

apply_environment_defaults() {
  local portable_root_raw="${CONFIG_PORTABLE_ROOT:-$PORTABLE_ROOT_DEFAULT}"
  local portable_root
  portable_root="$(to_abs_path "$portable_root_raw")"
  EFFECTIVE_PORTABLE_ROOT="$portable_root"
  local derived_data_dir="${portable_root}/user_home/mimolo"
  local derived_bin_dir="${portable_root}/bin"

  export MIMOLO_DATA_DIR="${MIMOLO_DATA_DIR:-${CONFIG_DATA_DIR:-$derived_data_dir}}"
  export MIMOLO_BIN_DIR="${MIMOLO_BIN_DIR:-${CONFIG_BIN_DIR:-$derived_bin_dir}}"
  export MIMOLO_REPO_ROOT="${MIMOLO_REPO_ROOT:-$SCRIPT_DIR}"
  export PATH="${MIMOLO_BIN_DIR}:${PATH}"

  local derived_runtime_config="${MIMOLO_DATA_DIR}/operations/mimolo.portable.toml"
  local derived_config_source="${SCRIPT_DIR}/mimolo.toml"
  export MIMOLO_RUNTIME_CONFIG_PATH="${MIMOLO_RUNTIME_CONFIG_PATH:-${CONFIG_RUNTIME_CONFIG_PATH:-$derived_runtime_config}}"
  export MIMOLO_CONFIG_SOURCE_PATH="${MIMOLO_CONFIG_SOURCE_PATH:-${CONFIG_CONFIG_SOURCE_PATH:-$derived_config_source}}"

  local tmp_root="${TMPDIR:-/tmp}"
  local derived_ipc_path="${tmp_root%/}/mimolo/operations.sock"
  local derived_ops_log_path="${MIMOLO_DATA_DIR}/runtime/operations.log"
  export MIMOLO_IPC_PATH="${MIMOLO_IPC_PATH:-${CONFIG_IPC_PATH:-$derived_ipc_path}}"
  export MIMOLO_OPS_LOG_PATH="${MIMOLO_OPS_LOG_PATH:-${CONFIG_OPS_LOG_PATH:-$derived_ops_log_path}}"

  # AF_UNIX socket paths are length-limited on macOS/Linux; keep socket path in temp.
  if ((${#MIMOLO_IPC_PATH} > IPC_SOCKET_MAX_LENGTH)); then
    echo "[dev-stack] IPC path too long (${#MIMOLO_IPC_PATH} > ${IPC_SOCKET_MAX_LENGTH}); falling back to ${derived_ipc_path}"
    export MIMOLO_IPC_PATH="$derived_ipc_path"
  fi

  local derived_monitor_log_dir="${MIMOLO_DATA_DIR}/operations/logs"
  local derived_monitor_journal_dir="${MIMOLO_DATA_DIR}/operations/journals"
  local derived_monitor_cache_dir="${MIMOLO_DATA_DIR}/operations/cache"
  export MIMOLO_MONITOR_LOG_DIR="${MIMOLO_MONITOR_LOG_DIR:-${CONFIG_MONITOR_LOG_DIR:-$derived_monitor_log_dir}}"
  export MIMOLO_MONITOR_JOURNAL_DIR="${MIMOLO_MONITOR_JOURNAL_DIR:-${CONFIG_MONITOR_JOURNAL_DIR:-$derived_monitor_journal_dir}}"
  export MIMOLO_MONITOR_CACHE_DIR="${MIMOLO_MONITOR_CACHE_DIR:-${CONFIG_MONITOR_CACHE_DIR:-$derived_monitor_cache_dir}}"

  local derived_source_list_path="${SCRIPT_DIR}/mimolo/agents/sources.json"
  if [[ -n "${MIMOLO_RELEASE_AGENTS_PATH:-}" ]]; then
    :
  elif [[ -n "$CONFIG_RELEASE_AGENTS_PATH" ]]; then
    export MIMOLO_RELEASE_AGENTS_PATH="$(to_abs_path "$CONFIG_RELEASE_AGENTS_PATH")"
  else
    export MIMOLO_RELEASE_AGENTS_PATH="$derived_source_list_path"
  fi
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

run_ops_command() {
  local -a ops_args=("$@")
  local -a cmd=(poetry run python -m mimolo.cli ops)
  if ! has_config_arg "$@"; then
    cmd+=(--config "$MIMOLO_RUNTIME_CONFIG_PATH")
  fi
  if ((${#ops_args[@]} > 0)); then
    cmd+=("${ops_args[@]}")
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
    --source-list "$MIMOLO_RELEASE_AGENTS_PATH"
  )
  if [[ -n "$CONFIG_DEPLOY_AGENTS_DEFAULT" ]]; then
    prepare_cmd+=(--agents "$CONFIG_DEPLOY_AGENTS_DEFAULT")
  fi
  if ((${#@} > 0)); then
    prepare_cmd+=("$@")
  fi
  "${prepare_cmd[@]}"
}

cleanup_artifacts() {
  local removed_portable=0
  local removed_dist=0
  local removed_pycache=0

  echo "[dev-stack] Cleaning development artifacts..."

  if [[ -n "$EFFECTIVE_PORTABLE_ROOT" ]]; then
    if [[ "$EFFECTIVE_PORTABLE_ROOT" == "$SCRIPT_DIR" || "$EFFECTIVE_PORTABLE_ROOT" == "$SCRIPT_DIR/"* ]]; then
      if [[ -d "$EFFECTIVE_PORTABLE_ROOT" ]]; then
        rm -rf "$EFFECTIVE_PORTABLE_ROOT"
        removed_portable=1
      fi
    else
      echo "[dev-stack] Skipping portable root outside repo: $EFFECTIVE_PORTABLE_ROOT"
    fi
  fi

  while IFS= read -r dir; do
    [[ -z "$dir" ]] && continue
    if [[ "$dir" == */node_modules/* ]]; then
      continue
    fi
    rm -rf "$dir"
    removed_dist=$((removed_dist + 1))
  done < <(find "$SCRIPT_DIR" -type d -name dist -prune -print)

  while IFS= read -r dir; do
    [[ -z "$dir" ]] && continue
    rm -rf "$dir"
    removed_pycache=$((removed_pycache + 1))
  done < <(find "$SCRIPT_DIR" -type d -name __pycache__ -prune -print)

  echo "[dev-stack] Cleanup done: portable_root_removed=$removed_portable dist_removed=$removed_dist pycache_removed=$removed_pycache"
}

maybe_reset_and_prepare() {
  if [[ "$NO_CACHE" -ne 1 ]]; then
    return
  fi
  echo "[dev-stack] --no-cache requested: cleaning and rebuilding portable artifacts..."
  cleanup_artifacts
  run_prepare
}

apply_dev_mode_env() {
  if [[ "$DEV_MODE" -eq 1 ]]; then
    export MIMOLO_CONTROL_DEV_MODE="1"
    return
  fi
  if [[ -z "${MIMOLO_CONTROL_DEV_MODE:-}" ]]; then
    export MIMOLO_CONTROL_DEV_MODE="0"
  fi
}

ensure_control_build() {
  if ! (cd "$SCRIPT_DIR/mimolo-control" && npx --no-install electron --version >/dev/null 2>&1); then
    echo "[dev-stack] Electron runtime missing for mimolo-control; running npm ci..."
    (cd "$SCRIPT_DIR/mimolo-control" && npm ci)
  fi
  local control_main="$SCRIPT_DIR/mimolo-control/dist/main.js"
  if [[ -f "$control_main" ]]; then
    return
  fi
  echo "[dev-stack] Building mimolo-control (dist missing)..."
  (cd "$SCRIPT_DIR/mimolo-control" && npm run build)
}

ensure_proto_build() {
  if ! (cd "$SCRIPT_DIR/mimolo-control" && npx --no-install electron --version >/dev/null 2>&1); then
    echo "[dev-stack] Electron runtime missing for control_proto launch; running npm ci in mimolo-control..."
    (cd "$SCRIPT_DIR/mimolo-control" && npm ci)
  fi
  local proto_main="$SCRIPT_DIR/mimolo/control_proto/dist/main.js"
  if [[ -f "$proto_main" ]]; then
    return
  fi
  echo "[dev-stack] Building control_proto (dist missing)..."
  (cd "$SCRIPT_DIR/mimolo/control_proto" && npm run build)
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
  local display_portable_root="${CONFIG_PORTABLE_ROOT:-./temp_debug}"
  local display_seed_agents="${CONFIG_DEPLOY_AGENTS_DEFAULT:-<all from source list>}"
  local display_release_agents_path="${CONFIG_RELEASE_AGENTS_PATH:-./mimolo/agents/sources.json}"
  local display_bundle_target="${CONFIG_BUNDLE_TARGET_DEFAULT:-proto}"
  local display_bundle_out_dir="${CONFIG_BUNDLE_OUT_DIR:-./temp_debug/bundles/macos}"
  local display_bundle_version="${CONFIG_BUNDLE_VERSION_DEFAULT:-<package version>}"
  local display_bundle_name_proto="${CONFIG_BUNDLE_APP_NAME_PROTO:-mimolo-proto (v<package_version>).app}"
  local display_bundle_name_control="${CONFIG_BUNDLE_APP_NAME_CONTROL:-MiMoLo.app}"
  local display_bundle_id_proto="${CONFIG_BUNDLE_BUNDLE_ID_PROTO:-com.mimolo.control.proto.dev}"
  local display_bundle_id_control="${CONFIG_BUNDLE_BUNDLE_ID_CONTROL:-com.mimolo.control.dev}"
  local display_bundle_dev_mode="${CONFIG_BUNDLE_DEV_MODE_DEFAULT:-<inherit launcher env/--dev>}"
  cat <<EOF
MiMoLo Portable Dev Launcher

Commands:
  [no command] Use default_command from mml.toml
  --no-cache  Global flag: cleanup and rebuild portable artifacts before launch
  --rebuild-dist Alias for --no-cache
  --dev       Global flag: enable developer-mode plugin zip install in Control/proto
  prepare     Build/sync portable bin artifacts and seed default agents
  cleanup     Remove temp_debug, all dist folders, and all __pycache__ folders
  bundle-app  Build macOS .app bundle for proto/control via scripts/bundle_app.sh
  ps          List running MiMoLo-related processes (dev diagnostics)
  env         Show effective environment and launch commands
  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli ops
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
  ./mml.sh --no-cache
  ./mml.sh --rebuild-dist
  ./mml.sh --dev all-proto
  ./mml.sh --no-cache all-proto
  ./mml.sh bundle-app
  ./mml.sh --dev bundle-app --target proto
  ./mml.sh prepare
  ./mml.sh cleanup
  ./mml.sh env
  ./mml.sh operations --once
  ./mml.sh proto
  ./mml.sh all-proto

Defaults from mml.toml:
  default_command=$DEFAULT_COMMAND
  default_stack=$DEFAULT_STACK
  socket_wait_seconds=$SOCKET_WAIT_SECONDS
  portable_root=$display_portable_root
  deploy_agents_default=$display_seed_agents
  release_agents_path=$display_release_agents_path
  bundle_target_default=$display_bundle_target
  bundle_out_dir=$display_bundle_out_dir
  bundle_version_default=$display_bundle_version
  bundle_app_name_proto=$display_bundle_name_proto
  bundle_app_name_control=$display_bundle_name_control
  bundle_bundle_id_proto=$display_bundle_id_proto
  bundle_bundle_id_control=$display_bundle_id_control
  bundle_dev_mode_default=$display_bundle_dev_mode
EOF
}

list_mimolo_processes() {
  if ! command -v ps >/dev/null 2>&1; then
    echo "[dev-stack] ps command not available on PATH."
    return 1
  fi

  local pattern="$SCRIPT_DIR|mimolo\\.cli (ops|monitor)|mimolo-control|control_proto|mml\\.(sh|ps1)|MiMoLo"
  echo "[dev-stack] MiMoLo-related processes:"
  local ps_output=""
  if ! ps_output="$(ps -axo pid,ppid,stat,etime,command 2>/dev/null)"; then
    echo "[dev-stack] unable to query process table (permission denied or unsupported environment)."
    return 0
  fi
  if command -v rg >/dev/null 2>&1; then
    printf "%s\n" "$ps_output" | rg -N -i "$pattern" || true
  else
    printf "%s\n" "$ps_output" | grep -Ei "$pattern" || true
  fi
}

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

load_launcher_config
apply_environment_defaults

# Global flag parse (can appear anywhere before command args).
if [[ "$#" -gt 0 ]]; then
  filtered_args=()
  for arg in "$@"; do
    case "$arg" in
      --no-cache|--rebuild-dist)
        NO_CACHE=1
        continue
        ;;
      --dev)
        DEV_MODE=1
        continue
        ;;
    esac
    filtered_args+=("$arg")
  done
  set -- "${filtered_args[@]}"
fi

apply_dev_mode_env

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
    echo "MIMOLO_REPO_ROOT=$MIMOLO_REPO_ROOT"
    echo "MIMOLO_RUNTIME_CONFIG_PATH=$MIMOLO_RUNTIME_CONFIG_PATH"
    echo "MIMOLO_CONFIG_SOURCE_PATH=$MIMOLO_CONFIG_SOURCE_PATH"
    echo "MIMOLO_IPC_PATH=$MIMOLO_IPC_PATH"
    echo "MIMOLO_OPS_LOG_PATH=$MIMOLO_OPS_LOG_PATH"
    echo "MIMOLO_MONITOR_LOG_DIR=$MIMOLO_MONITOR_LOG_DIR"
    echo "MIMOLO_MONITOR_JOURNAL_DIR=$MIMOLO_MONITOR_JOURNAL_DIR"
    echo "MIMOLO_MONITOR_CACHE_DIR=$MIMOLO_MONITOR_CACHE_DIR"
    echo "MIMOLO_RELEASE_AGENTS_PATH=$MIMOLO_RELEASE_AGENTS_PATH"
    echo "default_command=$DEFAULT_COMMAND"
    echo "default_stack=$DEFAULT_STACK"
    echo "socket_wait_seconds=$SOCKET_WAIT_SECONDS"
    echo "control_dev_mode=$MIMOLO_CONTROL_DEV_MODE"
    echo "deploy_agents_default=${CONFIG_DEPLOY_AGENTS_DEFAULT:-<all from source list>}"
    echo "release_agents_path=${CONFIG_RELEASE_AGENTS_PATH:-./mimolo/agents/sources.json}"
    echo "bundle_target_default=${CONFIG_BUNDLE_TARGET_DEFAULT:-proto}"
    echo "bundle_out_dir=${CONFIG_BUNDLE_OUT_DIR:-./temp_debug/bundles/macos}"
    echo "bundle_version_default=${CONFIG_BUNDLE_VERSION_DEFAULT:-}"
    echo "bundle_app_name_proto=${CONFIG_BUNDLE_APP_NAME_PROTO:-}"
    echo "bundle_app_name_control=${CONFIG_BUNDLE_APP_NAME_CONTROL:-}"
    echo "bundle_bundle_id_proto=${CONFIG_BUNDLE_BUNDLE_ID_PROTO:-com.mimolo.control.proto.dev}"
    echo "bundle_bundle_id_control=${CONFIG_BUNDLE_BUNDLE_ID_CONTROL:-com.mimolo.control.dev}"
    echo "bundle_dev_mode_default=${CONFIG_BUNDLE_DEV_MODE_DEFAULT:-}"
    echo "no_cache_supported=true"
    echo
    echo "Launch commands:"
    echo "  ./mml.sh"
    echo "  ./mml.sh prepare"
    echo "  ./mml.sh cleanup"
    echo "  ./mml.sh --no-cache [command]"
    echo "  ./mml.sh --rebuild-dist [command]"
    echo "  ./mml.sh --dev [command]"
    echo "  ./mml.sh operations"
    echo "  ./mml.sh ps"
    echo "  ./mml.sh control"
    echo "  ./mml.sh proto"
    echo "  ./mml.sh all-proto"
    echo "  ./mml.sh all-control"
    echo "  ./mml.sh bundle-app [bundle args]"
    ;;
  operations)
    maybe_reset_and_prepare
    launch_operations "$@"
    ;;
  ps|processes)
    list_mimolo_processes
    ;;
  prepare)
    if [[ "$NO_CACHE" -eq 1 ]]; then
      echo "[dev-stack] --no-cache requested: cleaning before prepare..."
      cleanup_artifacts
    fi
    run_prepare "$@"
    ;;
  cleanup)
    cleanup_artifacts
    ;;
  bundle-app)
    maybe_reset_and_prepare
    launch_bundle_app "$@"
    ;;
  control)
    maybe_reset_and_prepare
    launch_control
    ;;
  proto)
    maybe_reset_and_prepare
    launch_proto
    ;;
  all)
    maybe_reset_and_prepare
    run_all_target "$DEFAULT_STACK" "$@"
    ;;
  all-proto)
    maybe_reset_and_prepare
    run_all_target "proto" "$@"
    ;;
  all-control)
    maybe_reset_and_prepare
    run_all_target "control" "$@"
    ;;
  *)
    echo "Unknown command: $COMMAND" >&2
    print_usage >&2
    exit 2
    ;;
esac
