> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

# Screen Tracker Agent Spec

> Agent: screen_tracker
> Version: 0.1 (draft)
> Protocol: MiMoLo Agent Protocol v0.3 (see AGENT_PROTOCOL_SPEC.md)

## Purpose
Captures periodic screenshots (full screen or active window) for broad activity context.

## Inputs
- capture_interval_s: 30 or 60
- mode: "active_window" | "full_screen"
- screenshot_quality: JPEG quality (default: 35)
- screenshot_scale: 0.10 (10%)
- letterbox: true | false

## Behavior
- Capture on schedule and emit thumbnail metadata.
- If capture fails, emit error and continue.

## Output Messages

### Summary (screen capture)
- type: summary
- data:
  - capture_mode
  - active_app: optional
  - window_title: optional
  - screenshot:
    - {timestamp, path, scale, quality, width, height, letterbox}

## Artifact Storage
Store artifacts in the per-user app data directory:
- Windows: `%AppData%\\mimolo\\screen_tracker\\...`
- macOS: `~/Library/Application Support/mimolo/screen_tracker/...`
- Linux: `~/.local/share/mimolo/screen_tracker/...`

### Heartbeat
- type: heartbeat
- metrics: include captures_sent, last_capture_age_s

## Config Example (mimolo.toml)
[plugins.screen_tracker]
enabled = true
plugin_type = "agent"
executable = "python"
args = ["screen_tracker.py", "--interval", "60"]
heartbeat_interval_s = 30.0
agent_flush_interval_s = 120.0

