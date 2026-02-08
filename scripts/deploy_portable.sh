#!/usr/bin/env bash
# Deploy portable runtime artifacts to a local bin/data root for dev testing.
# Default seeded agents: agent_template, agent_example

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PORTABLE_ROOT="${PORTABLE_ROOT:-$REPO_ROOT/temp_debug}"
DATA_DIR="${MIMOLO_DATA_DIR:-$PORTABLE_ROOT/user_home/mimolo}"
BIN_DIR="${MIMOLO_BIN_DIR:-$PORTABLE_ROOT/bin}"
RUNTIME_CONFIG_PATH="${MIMOLO_RUNTIME_CONFIG_PATH:-$DATA_DIR/operations/mimolo.portable.toml}"
CONFIG_SOURCE_PATH="${MIMOLO_CONFIG_SOURCE_PATH:-$REPO_ROOT/mimolo.toml}"
AGENTS_TO_SEED="agent_template,agent_example"
NO_BUILD=0
FORCE_SYNC=0

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
  --agents <csv>           Agent ids to seed (default: agent_template,agent_example)
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

echo "[deploy] seeding agents: $AGENTS_TO_SEED"
poetry run python - <<'PY' "$REPO_ROOT" "$DATA_DIR" "$AGENTS_TO_SEED"
from __future__ import annotations

import json
import sys
from pathlib import Path

from mimolo.core.plugin_store import PluginStore

repo_root = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
agents_csv = sys.argv[3]
agent_ids = [x.strip() for x in agents_csv.split(",") if x.strip()]
if not agent_ids:
    raise SystemExit("[deploy] no agent ids provided")

sources_path = repo_root / "mimolo" / "agents" / "sources.json"
repo_dir = repo_root / "mimolo" / "agents" / "repository"
if not sources_path.exists():
    raise SystemExit(f"[deploy] missing sources file: {sources_path}")
if not repo_dir.exists():
    raise SystemExit(f"[deploy] missing repository dir: {repo_dir}")

sources_doc = json.loads(sources_path.read_text(encoding="utf-8"))
source_rows = sources_doc.get("sources", [])
source_versions: dict[str, str] = {}
for row in source_rows:
    if isinstance(row, dict):
        plugin_id = str(row.get("id", "")).strip()
        version = str(row.get("ver", "")).strip()
        if plugin_id and version:
            source_versions[plugin_id] = version

store = PluginStore(data_dir)
for agent_id in agent_ids:
    zip_path: Path | None = None
    version = source_versions.get(agent_id)
    if version:
        candidate = repo_dir / f"{agent_id}_v{version}.zip"
        if candidate.exists():
            zip_path = candidate
    if zip_path is None:
        candidates = sorted(repo_dir.glob(f"{agent_id}_v*.zip"))
        if candidates:
            zip_path = candidates[-1]
    if zip_path is None:
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

poetry run python - <<'PY' "$BIN_DIR" "$DATA_DIR" "$RUNTIME_CONFIG_PATH" "$AGENTS_TO_SEED"
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import sys

bin_dir = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
runtime_config = Path(sys.argv[3])
agents = [x.strip() for x in sys.argv[4].split(",") if x.strip()]

manifest_path = bin_dir / "deploy-manifest.json"
manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "bin_dir": str(bin_dir.resolve()),
    "data_dir": str(data_dir.resolve()),
    "runtime_config_path": str(runtime_config.resolve()),
    "seeded_agents_default": agents,
    "deployment_model": "portable",
}
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"[deploy] wrote {manifest_path}")
PY

echo "[deploy] done."
