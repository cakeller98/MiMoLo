# Command dispatch helpers for mml launcher.

execute_command() {
  local command="$1"
  shift

  case "$command" in
    help|-h|--help)
      print_usage
      ;;
    env)
      print_env
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
      echo "Unknown command: $command" >&2
      print_usage >&2
      exit 2
      ;;
  esac
}
