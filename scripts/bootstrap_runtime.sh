#!/usr/bin/env bash
# Bootstrap MiMoLo portable runtime in-place (first-run rehydrate).
# Creates/rehydrates .venv, seeds runtime config, and rewrites agent executables
# to the portable runtime python interpreter.

set -euo pipefail

RUNTIME_ROOT=""
DATA_DIR=""
BIN_DIR=""
RUNTIME_CONFIG_PATH=""
CONFIG_SOURCE_PATH=""
OPS_LOG_PATH=""
MONITOR_LOG_DIR=""
MONITOR_JOURNAL_DIR=""
MONITOR_CACHE_DIR=""
SOURCE_SITE_PACKAGES="${MIMOLO_BOOTSTRAP_SOURCE_SITE_PACKAGES:-}"
SOURCE_PYTHON="${MIMOLO_BOOTSTRAP_SOURCE_PYTHON:-}"
RUNTIME_VENV_PATH="${MIMOLO_RUNTIME_VENV_PATH:-}"
REPO_ROOT="${MIMOLO_BOOTSTRAP_REPO_ROOT:-}"
BOOTSTRAP_LOCK_DIR=""

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf "%s" "$value"
}

usage() {
  cat <<'USAGE'
Bootstrap MiMoLo runtime (.venv + runtime config)

Usage:
  scripts/bootstrap_runtime.sh [options]

Options:
  --runtime-root <path>         Runtime root (contains .venv, user_home, bin)
  --data-dir <path>             MIMOLO data dir (default: <runtime-root>/user_home/mimolo)
  --bin-dir <path>              MIMOLO bin dir (default: <runtime-root>/bin)
  --runtime-config <path>       Runtime config path (default: <data-dir>/operations/mimolo.portable.toml)
  --config-source <path>        Source config path used when runtime config is missing
  --ops-log-path <path>         Operations log file path
  --monitor-log-dir <path>      Monitor log dir
  --monitor-journal-dir <path>  Monitor journal dir
  --monitor-cache-dir <path>    Monitor cache dir
  --source-site-packages <path> Source site-packages for hydration copy
  --source-python <path>        Source python executable (preferred for venv creation)
  --runtime-venv <path>         Runtime venv directory path (default: <bin-dir>/.venv)
  --repo-root <path>            Repo root containing ./mimolo package source
  -h, --help                    Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --runtime-root)
      RUNTIME_ROOT="$2"
      shift 2
      ;;
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="$2"
      shift 2
      ;;
    --runtime-config)
      RUNTIME_CONFIG_PATH="$2"
      shift 2
      ;;
    --config-source)
      CONFIG_SOURCE_PATH="$2"
      shift 2
      ;;
    --ops-log-path)
      OPS_LOG_PATH="$2"
      shift 2
      ;;
    --monitor-log-dir)
      MONITOR_LOG_DIR="$2"
      shift 2
      ;;
    --monitor-journal-dir)
      MONITOR_JOURNAL_DIR="$2"
      shift 2
      ;;
    --monitor-cache-dir)
      MONITOR_CACHE_DIR="$2"
      shift 2
      ;;
    --source-site-packages)
      SOURCE_SITE_PACKAGES="$2"
      shift 2
      ;;
    --source-python)
      SOURCE_PYTHON="$2"
      shift 2
      ;;
    --runtime-venv)
      RUNTIME_VENV_PATH="$2"
      shift 2
      ;;
    --repo-root)
      REPO_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[bootstrap] unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$RUNTIME_ROOT" ]]; then
  if [[ -n "$BIN_DIR" ]]; then
    RUNTIME_ROOT="$(dirname "$BIN_DIR")"
  elif [[ -n "$DATA_DIR" ]]; then
    RUNTIME_ROOT="$(dirname "$(dirname "$(dirname "$DATA_DIR")")")"
  else
    echo "[bootstrap] missing --runtime-root (or equivalent --data-dir/--bin-dir)." >&2
    exit 2
  fi
fi

if [[ -z "$DATA_DIR" ]]; then
  DATA_DIR="$RUNTIME_ROOT/user_home/mimolo"
fi
if [[ -z "$BIN_DIR" ]]; then
  BIN_DIR="$RUNTIME_ROOT/bin"
fi
if [[ -z "$RUNTIME_CONFIG_PATH" ]]; then
  RUNTIME_CONFIG_PATH="$DATA_DIR/operations/mimolo.portable.toml"
fi
if [[ -z "$OPS_LOG_PATH" ]]; then
  OPS_LOG_PATH="$DATA_DIR/runtime/operations.log"
fi
if [[ -z "$MONITOR_LOG_DIR" ]]; then
  MONITOR_LOG_DIR="$DATA_DIR/operations/logs"
fi
if [[ -z "$MONITOR_JOURNAL_DIR" ]]; then
  MONITOR_JOURNAL_DIR="$DATA_DIR/operations/journals"
fi
if [[ -z "$MONITOR_CACHE_DIR" ]]; then
  MONITOR_CACHE_DIR="$DATA_DIR/operations/cache"
fi

resolve_portable_python_path() {
  local venv_dir="$1"
  if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OS:-}" == Windows_NT ]]; then
    printf "%s/Scripts/python.exe" "$venv_dir"
  else
    printf "%s/bin/python" "$venv_dir"
  fi
}

resolve_source_python() {
  local source_python
  source_python="$(trim "$SOURCE_PYTHON")"
  if [[ -n "$source_python" && -x "$source_python" ]]; then
    printf "%s" "$source_python"
    return
  fi

  if command -v poetry >/dev/null 2>&1; then
    source_python="$(poetry run python -c "import sys; print(sys.executable)" 2>/dev/null || true)"
    source_python="$(trim "$source_python")"
    if [[ -n "$source_python" && -x "$source_python" ]]; then
      printf "%s" "$source_python"
      return
    fi
  fi

  printf ""
}

python_version_tag() {
  local python_path="$1"
  "$python_path" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true
}

prepare_bootstrap_lock() {
  BOOTSTRAP_LOCK_DIR="$RUNTIME_ROOT/.bootstrap.lock"
  local waited=0
  local wait_step=1
  local max_wait=180
  while ! mkdir "$BOOTSTRAP_LOCK_DIR" 2>/dev/null; do
    if (( waited >= max_wait )); then
      echo "[bootstrap] timeout waiting for existing bootstrap lock: $BOOTSTRAP_LOCK_DIR" >&2
      exit 2
    fi
    sleep "$wait_step"
    waited=$(( waited + wait_step ))
  done
  trap 'if [[ -n "$BOOTSTRAP_LOCK_DIR" ]]; then rmdir "$BOOTSTRAP_LOCK_DIR" 2>/dev/null || true; fi' EXIT
}

ensure_dirs() {
  mkdir -p "$RUNTIME_ROOT"
  mkdir -p "$BIN_DIR"
  mkdir -p "$(dirname "$RUNTIME_VENV_PATH")"
  mkdir -p "$DATA_DIR"
  mkdir -p "$(dirname "$RUNTIME_CONFIG_PATH")"
  mkdir -p "$(dirname "$OPS_LOG_PATH")"
  mkdir -p "$MONITOR_LOG_DIR"
  mkdir -p "$MONITOR_JOURNAL_DIR"
  mkdir -p "$MONITOR_CACHE_DIR"
}

ensure_venv() {
  local venv_python="$1"
  local source_python="$2"
  local venv_dir="$3"
  if [[ -z "$source_python" ]]; then
    echo "[bootstrap] missing source python; cannot create runtime .venv" >&2
    exit 2
  fi

  local source_version
  source_version="$(python_version_tag "$source_python")"
  if [[ -z "$source_version" ]]; then
    echo "[bootstrap] unable to resolve source python version: $source_python" >&2
    exit 2
  fi

  if [[ -x "$venv_python" ]]; then
    local existing_version
    existing_version="$(python_version_tag "$venv_python")"
    if [[ -n "$existing_version" && "$existing_version" == "$source_version" ]]; then
      return
    fi
    echo "[bootstrap] replacing runtime venv due to python version mismatch ($existing_version != $source_version)"
    rm -rf "$venv_dir"
  fi

  echo "[bootstrap] creating runtime venv at $venv_dir using $source_python"
  "$source_python" -m venv "$venv_dir"

  if [[ ! -x "$venv_python" ]]; then
    echo "[bootstrap] portable runtime python missing after venv creation: $venv_python" >&2
    exit 2
  fi
}

runtime_imports_ready() {
  local venv_python="$1"
  "$venv_python" - <<'PY' >/dev/null 2>&1
import mimolo  # noqa: F401
import pydantic  # noqa: F401
import rich  # noqa: F401
import tomlkit  # noqa: F401
import typer  # noqa: F401
import yaml  # noqa: F401
PY
}

resolve_source_site_packages() {
  local source_site="$(trim "$SOURCE_SITE_PACKAGES")"
  if [[ -n "$source_site" && -d "$source_site" ]]; then
    printf "%s" "$source_site"
    return
  fi

  local source_python
  source_python="$(resolve_source_python)"
  if [[ -n "$source_python" ]]; then
    source_site="$("$source_python" -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" 2>/dev/null || true)"
    source_site="$(trim "$source_site")"
    if [[ -n "$source_site" && -d "$source_site" ]]; then
      printf "%s" "$source_site"
      return
    fi
  fi

  if command -v poetry >/dev/null 2>&1; then
    source_site="$(poetry run python -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" 2>/dev/null || true)"
    source_site="$(trim "$source_site")"
    if [[ -n "$source_site" && -d "$source_site" ]]; then
      printf "%s" "$source_site"
      return
    fi
  fi

  printf ""
}

hydrate_runtime_packages() {
  local venv_python="$1"
  local source_site
  source_site="$(resolve_source_site_packages)"
  if [[ -z "$source_site" ]]; then
    echo "[bootstrap] unable to resolve source site-packages for runtime hydration" >&2
    exit 2
  fi

  local target_site
  target_site="$($venv_python -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" 2>/dev/null || true)"
  target_site="$(trim "$target_site")"
  if [[ -z "$target_site" || ! -d "$target_site" ]]; then
    echo "[bootstrap] unable to resolve target site-packages: $target_site" >&2
    exit 2
  fi

  echo "[bootstrap] hydrating runtime packages from $source_site"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$source_site"/ "$target_site"/
  else
    cp -R "$source_site"/. "$target_site"/
  fi

  if [[ -n "$REPO_ROOT" && -d "$REPO_ROOT/mimolo" ]]; then
    echo "[bootstrap] syncing mimolo package source from $REPO_ROOT/mimolo"
    rm -rf "$target_site/mimolo"
    cp -R "$REPO_ROOT/mimolo" "$target_site/mimolo"
  fi

  if ! runtime_imports_ready "$venv_python"; then
    echo "[bootstrap] runtime hydration failed import validation" >&2
    exit 2
  fi
}

seed_runtime_config_if_missing() {
  if [[ -f "$RUNTIME_CONFIG_PATH" ]]; then
    return
  fi
  if [[ -z "$CONFIG_SOURCE_PATH" || ! -f "$CONFIG_SOURCE_PATH" ]]; then
    echo "[bootstrap] missing config source for initial seed: $CONFIG_SOURCE_PATH" >&2
    exit 2
  fi
  cp "$CONFIG_SOURCE_PATH" "$RUNTIME_CONFIG_PATH"
  echo "[bootstrap] seeded runtime config: $RUNTIME_CONFIG_PATH"
}

rewrite_runtime_config_executables() {
  local venv_python="$1"
  "$venv_python" - <<'PY' "$RUNTIME_CONFIG_PATH" "$venv_python"
from __future__ import annotations

from pathlib import Path
import sys

import tomlkit

config_path = Path(sys.argv[1])
runtime_python = sys.argv[2]

if not config_path.exists():
    raise SystemExit(f"[bootstrap] runtime config missing: {config_path}")

raw = config_path.read_text(encoding="utf-8")
doc = tomlkit.parse(raw)
plugins = doc.get("plugins")
if not isinstance(plugins, dict):
    config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
    raise SystemExit(0)

for _label, plugin_doc in plugins.items():
    if not isinstance(plugin_doc, dict):
        continue
    executable = str(plugin_doc.get("executable", "")).strip()
    args_raw = plugin_doc.get("args", [])
    args: list[str] = []
    if isinstance(args_raw, list):
        args = [str(item) for item in args_raw]

    if executable == "poetry":
        if len(args) >= 2 and args[0] == "run" and args[1] in {"python", "python3"}:
            args = args[2:]
        elif len(args) >= 1 and args[0] in {"python", "python3"}:
            args = args[1:]
        plugin_doc["executable"] = runtime_python
        plugin_doc["args"] = args
        continue

    if executable in {"python", "python3"}:
        plugin_doc["executable"] = runtime_python

config_path.write_text(tomlkit.dumps(doc), encoding="utf-8")
PY
}

if [[ -z "$RUNTIME_VENV_PATH" ]]; then
  RUNTIME_VENV_PATH="$BIN_DIR/.venv"
elif [[ "$RUNTIME_VENV_PATH" != /* ]]; then
  RUNTIME_VENV_PATH="$RUNTIME_ROOT/$RUNTIME_VENV_PATH"
fi

ensure_dirs
prepare_bootstrap_lock

source_python="$(resolve_source_python)"
if [[ -z "$source_python" ]]; then
  echo "[bootstrap] no managed source python found (set --source-python or ensure poetry runtime is available)" >&2
  exit 2
fi

portable_python="$(resolve_portable_python_path "$RUNTIME_VENV_PATH")"
ensure_venv "$portable_python" "$source_python" "$RUNTIME_VENV_PATH"
if ! runtime_imports_ready "$portable_python"; then
  hydrate_runtime_packages "$portable_python"
fi
seed_runtime_config_if_missing
rewrite_runtime_config_executables "$portable_python"

echo "[bootstrap] runtime ready: $portable_python"
echo "[bootstrap] runtime config: $RUNTIME_CONFIG_PATH"
