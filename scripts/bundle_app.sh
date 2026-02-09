#!/usr/bin/env bash
# Build a macOS .app bundle for MiMoLo dev targets from local built artifacts.
# Default target: control proto.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
CONFIG_FILE="$REPO_ROOT/mml.toml"

TARGET=""
OUT_DIR=""
APP_NAME=""
APP_VERSION=""
BUNDLE_ID=""
DEV_MODE_OVERRIDE=""
SKIP_PREPARE=0
NO_BUILD=0

PORTABLE_ROOT="${PORTABLE_ROOT:-$REPO_ROOT/temp_debug}"
DATA_DIR="${MIMOLO_DATA_DIR:-$PORTABLE_ROOT/user_home/mimolo}"
BIN_DIR="${MIMOLO_BIN_DIR:-$PORTABLE_ROOT/bin}"
RUNTIME_CONFIG_PATH="${MIMOLO_RUNTIME_CONFIG_PATH:-$DATA_DIR/operations/mimolo.portable.toml}"
CONFIG_SOURCE_PATH="${MIMOLO_CONFIG_SOURCE_PATH:-$REPO_ROOT/mimolo.toml}"
IPC_PATH="${MIMOLO_IPC_PATH:-/tmp/mimolo/operations.sock}"
OPS_LOG_PATH="${MIMOLO_OPS_LOG_PATH:-$DATA_DIR/runtime/operations.log}"
MONITOR_LOG_DIR="${MIMOLO_MONITOR_LOG_DIR:-$DATA_DIR/operations/logs}"
MONITOR_JOURNAL_DIR="${MIMOLO_MONITOR_JOURNAL_DIR:-$DATA_DIR/operations/journals}"
MONITOR_CACHE_DIR="${MIMOLO_MONITOR_CACHE_DIR:-$DATA_DIR/operations/cache}"

CONFIG_BUNDLE_TARGET_DEFAULT=""
CONFIG_BUNDLE_OUT_DIR=""
CONFIG_BUNDLE_VERSION_DEFAULT=""
CONFIG_BUNDLE_APP_NAME_PROTO=""
CONFIG_BUNDLE_APP_NAME_CONTROL=""
CONFIG_BUNDLE_BUNDLE_ID_PROTO=""
CONFIG_BUNDLE_BUNDLE_ID_CONTROL=""
CONFIG_BUNDLE_DEV_MODE_DEFAULT=""

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

load_bundle_defaults() {
  CONFIG_BUNDLE_TARGET_DEFAULT="$(get_toml_value "bundle_target_default" "")"
  CONFIG_BUNDLE_OUT_DIR="$(get_toml_value "bundle_out_dir" "")"
  CONFIG_BUNDLE_VERSION_DEFAULT="$(get_toml_value "bundle_version_default" "")"
  CONFIG_BUNDLE_APP_NAME_PROTO="$(get_toml_value "bundle_app_name_proto" "")"
  CONFIG_BUNDLE_APP_NAME_CONTROL="$(get_toml_value "bundle_app_name_control" "")"
  CONFIG_BUNDLE_BUNDLE_ID_PROTO="$(get_toml_value "bundle_bundle_id_proto" "")"
  CONFIG_BUNDLE_BUNDLE_ID_CONTROL="$(get_toml_value "bundle_bundle_id_control" "")"
  CONFIG_BUNDLE_DEV_MODE_DEFAULT="$(get_toml_value "bundle_dev_mode_default" "")"
}

to_abs_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf "%s" "$path"
  else
    printf "%s/%s" "$REPO_ROOT" "$path"
  fi
}

usage() {
  cat <<'EOF'
MiMoLo macOS bundle utility

Usage:
  scripts/bundle_app.sh [options]

Options:
  --target <proto|control>    Bundle target (default: proto)
  --out-dir <path>            Output directory (default: temp_debug/bundles/macos)
  --name <bundle-name>        Bundle filename (.app suffix optional)
  --version <x.y.z>           Override app version metadata
  --bundle-id <id>            Override CFBundleIdentifier
  --dev-mode <0|1>            Override MIMOLO_CONTROL_DEV_MODE inside bundle
  --skip-prepare              Skip deploy_portable preflight
  --no-build                  Skip npm build for selected target
  -h, --help                  Show this help

Examples:
  scripts/bundle_app.sh
  scripts/bundle_app.sh --target proto
  scripts/bundle_app.sh --target control --name MiMoLo.app
  scripts/bundle_app.sh --dev-mode 1 --name "mimolo-proto (v0.0.1).app"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --name)
      APP_NAME="$2"
      shift 2
      ;;
    --version)
      APP_VERSION="$2"
      shift 2
      ;;
    --bundle-id)
      BUNDLE_ID="$2"
      shift 2
      ;;
    --dev-mode)
      DEV_MODE_OVERRIDE="$2"
      shift 2
      ;;
    --skip-prepare)
      SKIP_PREPARE=1
      shift
      ;;
    --no-build)
      NO_BUILD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

load_bundle_defaults

if [[ -z "$TARGET" ]]; then
  TARGET="${CONFIG_BUNDLE_TARGET_DEFAULT:-proto}"
fi

if [[ -z "$OUT_DIR" ]]; then
  if [[ -n "$CONFIG_BUNDLE_OUT_DIR" ]]; then
    OUT_DIR="$(to_abs_path "$CONFIG_BUNDLE_OUT_DIR")"
  fi
fi

if [[ -z "$APP_VERSION" ]]; then
  APP_VERSION="${CONFIG_BUNDLE_VERSION_DEFAULT:-}"
fi

if [[ -z "$DEV_MODE_OVERRIDE" ]]; then
  DEV_MODE_OVERRIDE="${CONFIG_BUNDLE_DEV_MODE_DEFAULT:-}"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[bundle] macOS required (bundle_app.sh is macOS-only)." >&2
  exit 2
fi

if [[ "$TARGET" != "proto" && "$TARGET" != "control" ]]; then
  echo "[bundle] invalid target: $TARGET (expected proto|control)" >&2
  exit 2
fi

extract_package_version() {
  local pkg="$1"
  local version
  version="$(grep -E '"version"[[:space:]]*:' "$pkg" | head -n1 | sed -E 's/.*"version"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/')"
  if [[ -z "$version" ]]; then
    echo "0.0.0"
    return
  fi
  echo "$version"
}

js_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  printf '"%s"' "$value"
}

ensure_npm_deps() {
  local dir="$1"
  if [[ -d "$dir/node_modules" ]]; then
    return
  fi
  echo "[bundle] installing npm deps in $(basename "$dir")..."
  (cd "$dir" && npm ci)
}

if [[ "$SKIP_PREPARE" -eq 0 ]]; then
  echo "[bundle] running portable prepare preflight..."
  preflight_cmd=(
    "$REPO_ROOT/scripts/deploy_portable.sh"
    --portable-root "$PORTABLE_ROOT"
    --data-dir "$DATA_DIR"
    --bin-dir "$BIN_DIR"
    --runtime-config "$RUNTIME_CONFIG_PATH"
    --config-source "$CONFIG_SOURCE_PATH"
    --no-build
  )
  if [[ -n "${MIMOLO_RELEASE_AGENTS_PATH:-}" ]]; then
    preflight_cmd+=(--source-list "$MIMOLO_RELEASE_AGENTS_PATH")
  fi
  "${preflight_cmd[@]}"
fi

ensure_npm_deps "$REPO_ROOT/mimolo-control"

if [[ "$TARGET" == "proto" ]]; then
  TARGET_DIR="$REPO_ROOT/mimolo/control_proto"
  TARGET_PKG="$TARGET_DIR/package.json"
  TARGET_DISPLAY_NAME="MiMoLo Proto"
  DEFAULT_BUNDLE_ID="com.mimolo.control.proto.dev"
  if [[ -z "$APP_NAME" && -n "$CONFIG_BUNDLE_APP_NAME_PROTO" ]]; then
    APP_NAME="$CONFIG_BUNDLE_APP_NAME_PROTO"
  fi
  if [[ -z "$BUNDLE_ID" && -n "$CONFIG_BUNDLE_BUNDLE_ID_PROTO" ]]; then
    BUNDLE_ID="$CONFIG_BUNDLE_BUNDLE_ID_PROTO"
  fi
else
  TARGET_DIR="$REPO_ROOT/mimolo-control"
  TARGET_PKG="$TARGET_DIR/package.json"
  TARGET_DISPLAY_NAME="MiMoLo"
  DEFAULT_BUNDLE_ID="com.mimolo.control.dev"
  if [[ -z "$APP_NAME" && -n "$CONFIG_BUNDLE_APP_NAME_CONTROL" ]]; then
    APP_NAME="$CONFIG_BUNDLE_APP_NAME_CONTROL"
  fi
  if [[ -z "$BUNDLE_ID" && -n "$CONFIG_BUNDLE_BUNDLE_ID_CONTROL" ]]; then
    BUNDLE_ID="$CONFIG_BUNDLE_BUNDLE_ID_CONTROL"
  fi
fi

if [[ -z "$APP_VERSION" ]]; then
  APP_VERSION="$(extract_package_version "$TARGET_PKG")"
fi

if [[ -z "$APP_NAME" ]]; then
  if [[ "$TARGET" == "proto" ]]; then
    APP_NAME="mimolo-proto (v${APP_VERSION}).app"
  else
    APP_NAME="MiMoLo.app"
  fi
fi

if [[ "$APP_NAME" != *.app ]]; then
  APP_NAME="${APP_NAME}.app"
fi

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="$PORTABLE_ROOT/bundles/macos"
fi
mkdir -p "$OUT_DIR"

if [[ -z "$BUNDLE_ID" ]]; then
  BUNDLE_ID="$DEFAULT_BUNDLE_ID"
fi

if [[ -n "$DEV_MODE_OVERRIDE" ]]; then
  export MIMOLO_CONTROL_DEV_MODE="$DEV_MODE_OVERRIDE"
elif [[ -z "${MIMOLO_CONTROL_DEV_MODE:-}" ]]; then
  export MIMOLO_CONTROL_DEV_MODE="0"
fi

ensure_npm_deps "$TARGET_DIR"

if [[ "$NO_BUILD" -eq 0 ]]; then
  echo "[bundle] building target: $TARGET..."
  (cd "$TARGET_DIR" && npm run build)
fi

TARGET_MAIN="$TARGET_DIR/dist/main.js"
if [[ ! -f "$TARGET_MAIN" ]]; then
  echo "[bundle] missing build artifact: $TARGET_MAIN" >&2
  exit 2
fi

ELECTRON_TEMPLATE="$REPO_ROOT/mimolo-control/node_modules/electron/dist/Electron.app"
if [[ ! -d "$ELECTRON_TEMPLATE" ]]; then
  echo "[bundle] missing Electron template app: $ELECTRON_TEMPLATE" >&2
  exit 2
fi

BUNDLE_PATH="$OUT_DIR/$APP_NAME"
rm -rf "$BUNDLE_PATH"
cp -R "$ELECTRON_TEMPLATE" "$BUNDLE_PATH"

APP_RESOURCES="$BUNDLE_PATH/Contents/Resources/app"
rm -rf "$APP_RESOURCES"
mkdir -p "$APP_RESOURCES/dist"
cp -R "$TARGET_DIR/dist/." "$APP_RESOURCES/dist/"

cat > "$APP_RESOURCES/package.json" <<EOF
{
  "name": "mimolo-${TARGET}-bundle",
  "private": true,
  "version": "${APP_VERSION}",
  "type": "module",
  "main": "bundle_main.mjs"
}
EOF

JS_DATA_DIR="$(js_quote "$DATA_DIR")"
JS_BIN_DIR="$(js_quote "$BIN_DIR")"
JS_REPO_ROOT="$(js_quote "$REPO_ROOT")"
JS_RUNTIME_CONFIG_PATH="$(js_quote "$RUNTIME_CONFIG_PATH")"
JS_CONFIG_SOURCE_PATH="$(js_quote "$CONFIG_SOURCE_PATH")"
JS_IPC_PATH="$(js_quote "$IPC_PATH")"
JS_OPS_LOG_PATH="$(js_quote "$OPS_LOG_PATH")"
JS_MONITOR_LOG_DIR="$(js_quote "$MONITOR_LOG_DIR")"
JS_MONITOR_JOURNAL_DIR="$(js_quote "$MONITOR_JOURNAL_DIR")"
JS_MONITOR_CACHE_DIR="$(js_quote "$MONITOR_CACHE_DIR")"
JS_CONTROL_DEV_MODE="$(js_quote "${MIMOLO_CONTROL_DEV_MODE:-0}")"

cat > "$APP_RESOURCES/bundle_main.mjs" <<EOF
const defaults = {
  MIMOLO_DATA_DIR: ${JS_DATA_DIR},
  MIMOLO_BIN_DIR: ${JS_BIN_DIR},
  MIMOLO_REPO_ROOT: ${JS_REPO_ROOT},
  MIMOLO_RUNTIME_CONFIG_PATH: ${JS_RUNTIME_CONFIG_PATH},
  MIMOLO_CONFIG_SOURCE_PATH: ${JS_CONFIG_SOURCE_PATH},
  MIMOLO_IPC_PATH: ${JS_IPC_PATH},
  MIMOLO_OPS_LOG_PATH: ${JS_OPS_LOG_PATH},
  MIMOLO_MONITOR_LOG_DIR: ${JS_MONITOR_LOG_DIR},
  MIMOLO_MONITOR_JOURNAL_DIR: ${JS_MONITOR_JOURNAL_DIR},
  MIMOLO_MONITOR_CACHE_DIR: ${JS_MONITOR_CACHE_DIR},
  MIMOLO_CONTROL_DEV_MODE: ${JS_CONTROL_DEV_MODE}
};

for (const [key, value] of Object.entries(defaults)) {
  if (!process.env[key] || process.env[key].trim().length === 0) {
    process.env[key] = value;
  }
}

await import("./dist/main.js");
EOF

PLIST_PATH="$BUNDLE_PATH/Contents/Info.plist"
if [[ ! -f "$PLIST_PATH" ]]; then
  echo "[bundle] missing plist: $PLIST_PATH" >&2
  exit 2
fi

plutil -replace CFBundleName -string "$TARGET_DISPLAY_NAME" "$PLIST_PATH" 2>/dev/null || true
plutil -replace CFBundleDisplayName -string "$TARGET_DISPLAY_NAME" "$PLIST_PATH" 2>/dev/null || true
plutil -replace CFBundleIdentifier -string "$BUNDLE_ID" "$PLIST_PATH" 2>/dev/null || true
plutil -replace CFBundleShortVersionString -string "$APP_VERSION" "$PLIST_PATH" 2>/dev/null || true
plutil -replace CFBundleVersion -string "$APP_VERSION" "$PLIST_PATH" 2>/dev/null || true

echo "[bundle] created: $BUNDLE_PATH"
echo "[bundle] target=$TARGET version=$APP_VERSION dev_mode=${MIMOLO_CONTROL_DEV_MODE:-0}"
echo "[bundle] launch: open \"$BUNDLE_PATH\""
