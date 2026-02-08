# Data Storage Conventions

All components store data under the per-user application data directory.

## Base Paths
- Windows: %AppData%\\mimolo
- macOS: ~/Library/Application Support/mimolo
- Linux: ~/.local/share/mimolo

## Agent and Instance Storage

Agents should write only under their own plugin + instance subtree:
- `<base>/agents/<plugin_id>/<instance_id>/artifacts/...`
- `<base>/agents/<plugin_id>/<instance_id>/index/...`
- `<base>/agents/<plugin_id>/<instance_id>/archives/...`

Notes:
- Use `MIMOLO_DATA_DIR` from the runtime environment as the base root.
- Keep protocol/vault records lightweight; store heavy binaries in artifact paths.

## Control Data
Control artifacts live under:
- <base>/control/...

Example report layout:
- mimolo/control/reports/report_20260128_<client>_1/
  - report_20260128_<client>.md
  - assets/ (mp4, wav, jpg, png, svg)

## Retention and Purge Policy

1. Never purge automatically by default.
2. Never purge without explicit user permission.
3. Always offer archive before purge.
4. Archive must be restorable in place.
5. Keep breadcrumb metadata even when content is archived or purged.

For complete rules, see:
- `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`
