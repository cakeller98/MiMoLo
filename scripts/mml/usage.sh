# Help/usage/env output helpers for mml launcher.

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

print_env() {
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
}
