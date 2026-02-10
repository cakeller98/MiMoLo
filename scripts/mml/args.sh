# Argument parsing helpers for mml launcher.

declare -a MML_FILTERED_ARGS=()

parse_global_flags() {
  MML_FILTERED_ARGS=()
  if [[ "$#" -eq 0 ]]; then
    return
  fi

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
    MML_FILTERED_ARGS+=("$arg")
  done
}
