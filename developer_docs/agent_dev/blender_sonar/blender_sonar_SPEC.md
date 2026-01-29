# Blender Sonar Agent Spec

> Agent: blender_sonar
> Version: 0.1 (draft)
> Protocol: MiMoLo Agent Protocol v0.3 (see AGENT_PROTOCOL_SPEC.md)

## Purpose
Runs inside Blender and emits periodic activity pings with viewport thumbnails.

## Inputs
- ping_interval_s: 30
- screenshot_quality: JPEG quality (default: 40)
- screenshot_scale: 0.10 (10%)

## Behavior
- Use Blender timer/event loop to emit a ping every ping_interval_s.
- Capture a thumbnail of the viewport.
- Never block Blender UI; any capture work should be async or lightweight.

## Output Messages

### Summary (sonar ping)
- type: summary
- data:
  - app: "blender"
  - activity_state: "active"
  - viewport_thumbnail:
    - {timestamp, path, scale, quality, width, height}
  - scene_id: optional
  - file_path: optional (current .blend)

## Artifact Storage
Store artifacts in the per-user app data directory:
- Windows: `%AppData%\\mimolo\\blender_sonar\\...`
- macOS: `~/Library/Application Support/mimolo/blender_sonar/...`
- Linux: `~/.local/share/mimolo/blender_sonar/...`

### Heartbeat
- type: heartbeat
- metrics: include pings_sent, capture_ms

## Error Handling
- If capture fails, emit error message and keep running.
- If Blender context is invalid, emit status health=degraded.

## Config Example (mimolo.toml)
[plugins.blender_sonar]
enabled = true
plugin_type = "field_agent"
executable = "blender"
args = ["--background", "--python", "blender_sonar.py"]
heartbeat_interval_s = 15.0
agent_flush_interval_s = 60.0

