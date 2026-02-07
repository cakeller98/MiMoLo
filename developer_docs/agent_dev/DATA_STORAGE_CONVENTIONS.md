> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

# Data Storage Conventions

All components store data under the per-user application data directory.

## Base Paths
- Windows: %AppData%\\mimolo
- macOS: ~/Library/Application Support/mimolo
- Linux: ~/.local/share/mimolo

## Agent Artifacts
Each agent writes only to its own subtree:
- <base>/Agent-name/...

Examples:
- %AppData%\\mimolo\\trail_tracker\\...
- ~/Library/Application Support/mimolo/blender_sonar/...
- ~/.local/share/mimolo/screen_tracker/...

## Control Data
Control artifacts live under:
- <base>/control/...

Example report layout:
- mimolo/control/reports/report_20260128_<client>_1/
  - report_20260128_<client>.md
  - assets/ (mp4, wav, jpg, png, svg)

