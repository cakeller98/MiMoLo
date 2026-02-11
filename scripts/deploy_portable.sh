#!/usr/bin/env bash
# Deploy portable runtime artifacts to a local bin/data root for dev testing.
# Default source list: mimolo/agents/sources.json
# Default seeded agents: all ids from selected source list

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PORTABLE_ROOT="${PORTABLE_ROOT:-$REPO_ROOT/temp_debug}"
DATA_DIR="${MIMOLO_DATA_DIR:-$PORTABLE_ROOT/user_home/mimolo}"
BIN_DIR="${MIMOLO_BIN_DIR:-$PORTABLE_ROOT/bin}"
RUNTIME_CONFIG_PATH="${MIMOLO_RUNTIME_CONFIG_PATH:-$DATA_DIR/operations/mimolo.portable.toml}"
CONFIG_SOURCE_PATH="${MIMOLO_CONFIG_SOURCE_PATH:-$REPO_ROOT/mimolo.toml}"
AGENTS_TO_SEED=""
SOURCE_LIST_PATH="${MIMOLO_RELEASE_AGENTS_PATH:-}"
NO_BUILD=0
FORCE_SYNC=0

resolve_portable_python_path() {
  if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* || "${OS:-}" == Windows_NT ]]; then
    printf "%s/.venv/Scripts/python.exe" "$BIN_DIR"
  else
    printf "%s/.venv/bin/python" "$BIN_DIR"
  fi
}

resolve_host_python() {
  if command -v poetry >/dev/null 2>&1; then
    poetry run python -c "import sys; print(sys.executable)"
    return
  fi
  printf ""
}

ensure_portable_runtime_venv() {
  local venv_python
  venv_python="$(resolve_portable_python_path)"
  if [[ ! -x "$venv_python" ]]; then
    local host_python
    host_python="$(resolve_host_python)"
    if [[ -z "$host_python" ]]; then
      echo "[deploy] missing python runtime; cannot create portable .venv" >&2
      exit 2
    fi
    echo "[deploy] creating portable runtime venv at $BIN_DIR/.venv"
    "$host_python" -m venv "$BIN_DIR/.venv"
  fi

  if [[ ! -x "$venv_python" ]]; then
    echo "[deploy] portable runtime python missing after venv creation: $venv_python" >&2
    exit 2
  fi

  if "$venv_python" - <<'PY' >/dev/null 2>&1
import mimolo  # noqa: F401
import pydantic  # noqa: F401
import rich  # noqa: F401
import tomlkit  # noqa: F401
import typer  # noqa: F401
import yaml  # noqa: F401
PY
  then
    echo "[deploy] portable runtime already ready: $venv_python"
    return
  fi

  if ! command -v poetry >/dev/null 2>&1; then
    echo "[deploy] poetry required to hydrate portable runtime from existing environment" >&2
    exit 2
  fi

  local source_site
  source_site="$(poetry run python -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" 2>/dev/null || true)"
  if [[ -z "$source_site" || ! -d "$source_site" ]]; then
    echo "[deploy] unable to resolve poetry site-packages source" >&2
    exit 2
  fi

  local target_site
  target_site="$("$venv_python" -c "import site; print(next(p for p in site.getsitepackages() if p.endswith('site-packages')))" 2>/dev/null || true)"
  if [[ -z "$target_site" || ! -d "$target_site" ]]; then
    echo "[deploy] unable to resolve portable venv site-packages target" >&2
    exit 2
  fi

  echo "[deploy] hydrating portable runtime from poetry environment..."
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$source_site"/ "$target_site"/
    rsync -a "$REPO_ROOT/mimolo/" "$target_site/mimolo/"
  else
    cp -R "$source_site"/. "$target_site"/
    rm -rf "$target_site/mimolo"
    cp -R "$REPO_ROOT/mimolo" "$target_site/mimolo"
  fi

  if ! "$venv_python" - <<'PY' >/dev/null 2>&1
import mimolo  # noqa: F401
import pydantic  # noqa: F401
import rich  # noqa: F401
import tomlkit  # noqa: F401
import typer  # noqa: F401
import yaml  # noqa: F401
PY
  then
    echo "[deploy] portable runtime hydration failed validation imports" >&2
    exit 2
  fi

  echo "[deploy] portable runtime ready: $venv_python"
}

usage() {
  cat <<'EOF'
Portable deploy utility

Usage:
  scripts/deploy_portable.sh [options]

Options:
  --portable-root <path>   Portable root (default: ./temp_debug)
  --data-dir <path>        MIMOLO data dir override
  --bin-dir <path>         Portable bin dir override
  --runtime-config <path>  Runtime config destination
  --config-source <path>   Source config used to seed runtime config
  --agents <csv>           Agent ids to seed (default: all ids from selected source list)
  --source-list <path>     Agent source list JSON (default: \$MIMOLO_RELEASE_AGENTS_PATH or ./mimolo/agents/sources.json)
  --no-build               Skip control_proto npm build
  --force-sync             Force full file replacement when rsync is unavailable
  -h, --help               Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --portable-root)
      PORTABLE_ROOT="$2"
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
    --agents)
      AGENTS_TO_SEED="$2"
      shift 2
      ;;
    --source-list)
      SOURCE_LIST_PATH="$2"
      shift 2
      ;;
    --no-build)
      NO_BUILD=1
      shift
      ;;
    --force-sync)
      FORCE_SYNC=1
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

if [[ -z "$SOURCE_LIST_PATH" ]]; then
  SOURCE_LIST_PATH="$REPO_ROOT/mimolo/agents/sources.json"
fi
if [[ "$SOURCE_LIST_PATH" != /* ]]; then
  SOURCE_LIST_PATH="$REPO_ROOT/$SOURCE_LIST_PATH"
fi

mkdir -p "$PORTABLE_ROOT" "$DATA_DIR" "$BIN_DIR"
mkdir -p "$(dirname "$RUNTIME_CONFIG_PATH")"

if [[ ! -f "$CONFIG_SOURCE_PATH" ]]; then
  echo "[deploy] missing config source: $CONFIG_SOURCE_PATH" >&2
  exit 2
fi

if [[ ! -f "$RUNTIME_CONFIG_PATH" ]]; then
  cp "$CONFIG_SOURCE_PATH" "$RUNTIME_CONFIG_PATH"
  echo "[deploy] seeded runtime config: $RUNTIME_CONFIG_PATH"
fi

sync_dir() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then
    rsync \
      -a \
      --delete \
      --exclude "__pycache__/" \
      --exclude "*.pyc" \
      --exclude ".mypy_cache/" \
      --exclude ".pytest_cache/" \
      --exclude ".DS_Store" \
      "$src" "$dst"
    return
  fi

  if [[ "$FORCE_SYNC" -eq 1 ]]; then
    rm -rf "$dst"
    mkdir -p "$dst"
  fi
  cp -R "$src"/* "$dst"/
}

sync_file() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst"
}

ensure_pack_agent_archives() {
  local utils_dir="$REPO_ROOT/mimolo/utils"
  local pack_dist="$utils_dir/dist/pack-agent.js"
  if [[ ! -d "$utils_dir" ]]; then
    echo "[deploy] missing utils dir: $utils_dir" >&2
    exit 2
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo "[deploy] missing node runtime; cannot run pack-agent" >&2
    exit 2
  fi

  if [[ ! -d "$utils_dir/node_modules" ]]; then
    echo "[deploy] installing mimolo/utils npm deps..."
    (cd "$utils_dir" && npm ci >/dev/null)
  fi
  if [[ ! -f "$pack_dist" ]]; then
    echo "[deploy] building mimolo/utils pack tool..."
    (cd "$utils_dir" && npm run build >/dev/null)
  fi

  echo "[deploy] ensuring plugin archives from source list..."
  (cd "$utils_dir" && node dist/pack-agent.js --source-list "$SOURCE_LIST_PATH")
}

if [[ "$NO_BUILD" -eq 0 ]]; then
  echo "[deploy] building control_proto..."
  (cd "$REPO_ROOT/mimolo/control_proto" && npm run build >/dev/null)
fi

echo "[deploy] syncing runtime artifacts..."
sync_file "$REPO_ROOT/mml.sh" "$BIN_DIR/mml.sh"
sync_file "$REPO_ROOT/scripts/bundle_app.sh" "$BIN_DIR/scripts/bundle_app.sh"
sync_file "$REPO_ROOT/scripts/bundle_app.ps1" "$BIN_DIR/scripts/bundle_app.ps1"
sync_file "$REPO_ROOT/mml.toml" "$BIN_DIR/mml.toml"
sync_file "$REPO_ROOT/pyproject.toml" "$BIN_DIR/pyproject.toml"
if [[ -f "$REPO_ROOT/poetry.lock" ]]; then
  sync_file "$REPO_ROOT/poetry.lock" "$BIN_DIR/poetry.lock"
fi
sync_file "$REPO_ROOT/mimolo.toml" "$BIN_DIR/mimolo.default.toml"
sync_dir "$REPO_ROOT/mimolo/control_proto/dist/" "$BIN_DIR/control_proto/dist/"
sync_dir "$REPO_ROOT/mimolo/" "$BIN_DIR/runtime/mimolo/"

chmod +x "$BIN_DIR/mml.sh" || true
chmod +x "$BIN_DIR/scripts/bundle_app.sh" || true

ensure_portable_runtime_venv

if [[ ! -f "$SOURCE_LIST_PATH" ]]; then
  echo "[deploy] missing source list: $SOURCE_LIST_PATH" >&2
  exit 2
fi
echo "[deploy] source list: $SOURCE_LIST_PATH"
ensure_pack_agent_archives
if [[ -n "$AGENTS_TO_SEED" ]]; then
  echo "[deploy] seeding agents: $AGENTS_TO_SEED"
else
  echo "[deploy] seeding agents: <all from source list>"
fi
poetry run python - <<'PY' "$REPO_ROOT" "$DATA_DIR" "$AGENTS_TO_SEED" "$SOURCE_LIST_PATH"
from __future__ import annotations

import json
import sys
from pathlib import Path

from mimolo.core.plugin_store import PluginStore

repo_root = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
agents_csv = sys.argv[3]
source_list_path = Path(sys.argv[4])

repo_dir = repo_root / "mimolo" / "agents" / "repository"
if not source_list_path.exists():
    raise SystemExit(f"[deploy] missing source list: {source_list_path}")
if not repo_dir.exists():
    raise SystemExit(f"[deploy] missing repository dir: {repo_dir}")

sources_doc = json.loads(source_list_path.read_text(encoding="utf-8"))
source_rows = sources_doc.get("sources", [])
if not isinstance(source_rows, list):
    raise SystemExit(f"[deploy] source list has invalid shape: {source_list_path}")
source_versions: dict[str, str] = {}
source_order: list[str] = []
for row in source_rows:
    if isinstance(row, dict):
        plugin_id = str(row.get("id", "")).strip()
        version = str(row.get("ver", "")).strip()
        if plugin_id and version:
            source_versions[plugin_id] = version
            source_order.append(plugin_id)

agent_ids = [x.strip() for x in agents_csv.split(",") if x.strip()]
if not agent_ids:
    agent_ids = source_order
if not agent_ids:
    raise SystemExit("[deploy] no agent ids resolved from source list")

store = PluginStore(data_dir)
for agent_id in agent_ids:
    version = source_versions.get(agent_id)
    if not version:
        raise SystemExit(
            f"[deploy] source list does not define a version for agent id: {agent_id}"
        )
    zip_path = repo_dir / f"{agent_id}_v{version}.zip"
    if not zip_path.exists():
        raise SystemExit(f"[deploy] missing archive for {agent_id}")

    ok, detail, payload = store.install_plugin_archive(
        zip_path,
        "agents",
        require_newer=True,
    )
    if ok:
        print(
            f"[deploy] installed {payload.get('plugin_id')}@{payload.get('version')} -> {payload.get('path')}"
        )
        continue
    if detail in {"version_already_installed", "not_newer_than_installed"}:
        print(f"[deploy] unchanged {agent_id}: {detail}")
        continue
    raise SystemExit(f"[deploy] failed {agent_id}: {detail}")

store.write_registry_cache()
PY

poetry run python - <<'PY' "$BIN_DIR" "$DATA_DIR" "$RUNTIME_CONFIG_PATH" "$AGENTS_TO_SEED" "$SOURCE_LIST_PATH"
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import sys

bin_dir = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
runtime_config = Path(sys.argv[3])
agents = [x.strip() for x in sys.argv[4].split(",") if x.strip()]
source_list_path = Path(sys.argv[5])

manifest_path = bin_dir / "deploy-manifest.json"
manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "bin_dir": str(bin_dir.resolve()),
    "data_dir": str(data_dir.resolve()),
    "runtime_config_path": str(runtime_config.resolve()),
    "seeded_agents_default": agents if agents else ["*"],
    "source_list_path": str(source_list_path.resolve()),
    "deployment_model": "portable",
}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"[deploy] wrote {manifest_path}")
PY

echo "[deploy] done."
