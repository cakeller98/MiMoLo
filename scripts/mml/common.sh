# Shared mml shell helpers (config/env/runtime command wiring).
# This file is sourced by mml.sh in Phase 1 shell concern decomposition.

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
