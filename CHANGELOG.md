# Changelog

All notable changes to this project will be documented in this file.
Documentation-only history is tracked separately in `developer_docs/CHANGELOG.md`.

## 2026-01-31

### Breaking
- Renamed agent paths and identifiers from `field_agents` to `agents`. The new codebase is incompatible with the old `field_agents` layout.

## 2026-02-03

### Added
- Added `--verify-existing` and `--force-pack` options to `pack-agent` for repo collision handling.
- Added `--help` output and CLI flag summary for `pack-agent`.

### Changed
- `pack-agent` now merges updates into `build-manifest.toml` instead of overwriting it.
- `pack-agent` now reports repo/version conflicts with explicit context and preserves non-conflicting builds.

## 2026-02-06

### Added
- Added canonical launcher scripts `mml.sh` and `mml.ps1` to standardize `MIMOLO_IPC_PATH` and launch Operations/Control/prototype targets.
- Added `mml.toml` for launcher defaults (no-verb command, default stack, IPC path, socket wait timeout).
- Added a minimal runtime IPC command server (AF_UNIX) that responds to `ping` and `get_registered_plugins`.

### Changed
- Archived legacy `start_*.sh` and `start_*.ps1` scripts under `archive/start_scripts/`.
- Improved launcher readiness checks to require an IPC `ping` response before launching proto, reducing startup `ECONNREFUSED` races.
- Renamed the Electron Control app package path from `mimolo-dash` to `mimolo-control` and aligned package metadata.
- Renamed the TypeScript IPC prototype package path from `mimolo/dashboard` to `mimolo/control_proto`.
- Updated IPC prototype package metadata from `mimolo-dashboard-proto` to `mimolo-control-proto`.
- Added local TypeScript shim declarations in `mimolo-control` and `mimolo/control_proto` so early bootstrap builds pass before full runtime dependencies are installed.
- Removed deprecated `enableRemoteModule` BrowserWindow flag for Electron v40 compatibility.
