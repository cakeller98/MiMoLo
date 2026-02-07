> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

# Trail Tracker Agent Spec

> Agent: trail_tracker
> Version: 0.1 (draft)
> Protocol: MiMoLo Agent Protocol v0.3 (see AGENT_PROTOCOL_SPEC.md)

## Purpose
Monitors the PTC Creo trail folder for activity and emits debounced activity pings with low-resolution screenshots. Trail file writes indicate user interaction with Creo.

## Inputs
- trail_folder: Directory containing trail.txt.# files (one per Creo session)
- screenshot_quality: JPEG quality (default: 35)
- screenshot_scale: 0.10 (10%)
- min_ping_interval_s: 30
- inactivity_threshold_s: 300 (5 minutes)

## Behavior
- Watch trail.txt.# files for write/append events.
- Treat any write as active interaction.
- Emit activity pings at most once per min_ping_interval_s.
- Consider the user inactive only after inactivity_threshold_s has passed since last write.
- Inactivity starts at the threshold time (not retroactive).

## Output Messages
All messages follow the v0.3 envelope. Payload goes in `data`.

### Summary (activity ping)
- type: summary
- data:
  - activity_state: "active" | "inactive"
  - activity_window:
    - start: ISO-8601
    - end: ISO-8601
  - source: "trail_write"
  - trail_file: filename (optional)
  - screenshots:
    - list of {timestamp, path, scale, quality, width, height}

### Heartbeat
- type: heartbeat
- data: {}
- metrics: include queue depth, last_write_age_s, pings_sent

## Screenshot Policy
- Capture at 10% scale of full screen or Creo window.
- Store as compressed JPEG.
- Include file path in summary data.

## Artifact Storage
Store artifacts in the per-user app data directory:
- Windows: `%AppData%\\mimolo\\trail_tracker\\...`
- macOS: `~/Library/Application Support/mimolo/trail_tracker/...`
- Linux: `~/.local/share/mimolo/trail_tracker/...`

## Debounce Rules (example)
- If writes occur continuously, emit at most 1 ping every 30s.
- If quiet for 5 minutes, emit inactivity ping at the 5 minute mark.
- Minimum 1 active ping covers a 5-minute window; max 10 pings per 5-minute window.

## Error Handling
- If trail folder is missing/unreadable, emit error status and continue retrying.
- Screenshot failures should not block activity pings; report error with message field.

## Config Example (mimolo.toml)
[plugins.trail_tracker]
enabled = true
plugin_type = "agent"
executable = "python"
args = ["trail_tracker.py", "--trail-folder", "C:/path/to/trail"]
heartbeat_interval_s = 15.0
agent_flush_interval_s = 60.0

