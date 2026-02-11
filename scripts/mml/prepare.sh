# Prepare/build/cleanup helpers for mml launcher.

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

run_pack_agents() {
  ensure_portable_layout

  if ! command -v node >/dev/null 2>&1; then
    echo "[dev-stack] missing node runtime; cannot run pack-agent" >&2
    return 2
  fi

  local utils_dir="$SCRIPT_DIR/mimolo/utils"
  local pack_dist="$utils_dir/dist/pack-agent.js"
  if [[ ! -f "$pack_dist" ]]; then
    echo "[dev-stack] building mimolo/utils pack tool..."
    (cd "$utils_dir" && npm run build)
  fi

  local source_list="${MIMOLO_RELEASE_AGENTS_PATH:-$SCRIPT_DIR/mimolo/agents/sources.json}"
  if [[ ! -f "$source_list" ]]; then
    echo "[dev-stack] source list missing: $source_list" >&2
    return 2
  fi

  for arg in "$@"; do
    case "$arg" in
      --source|--source=*|--source-list|--source-list=*|--create-source-list)
        echo "[dev-stack] pack_agents always uses --source-list \"$source_list\"." >&2
        echo "[dev-stack] remove source-selection flags and pass only pack options (e.g. --patch, --minor, --verify-existing)." >&2
        return 2
        ;;
    esac
  done

  echo "[dev-stack] pack_agents source list: $source_list"
  (
    cd "$utils_dir" &&
      node dist/pack-agent.js --source-list "$source_list" "$@"
  )
}
