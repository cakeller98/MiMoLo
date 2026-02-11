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
#   ./mml.sh pack_agents [pack-agent args...]
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

source "$SCRIPT_DIR/scripts/mml/common.sh"
source "$SCRIPT_DIR/scripts/mml/prepare.sh"
source "$SCRIPT_DIR/scripts/mml/usage.sh"
source "$SCRIPT_DIR/scripts/mml/process.sh"
source "$SCRIPT_DIR/scripts/mml/launch.sh"
source "$SCRIPT_DIR/scripts/mml/args.sh"
source "$SCRIPT_DIR/scripts/mml/dispatch.sh"

load_launcher_config
apply_environment_defaults

parse_global_flags "$@"
set -- "${MML_FILTERED_ARGS[@]}"

apply_dev_mode_env

COMMAND=""
if [[ "$#" -gt 0 ]]; then
  COMMAND="$1"
  shift
else
  COMMAND="$DEFAULT_COMMAND"
fi
COMMAND="$(normalize_all_command "$COMMAND")"

execute_command "$COMMAND" "$@"
