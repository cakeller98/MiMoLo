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
