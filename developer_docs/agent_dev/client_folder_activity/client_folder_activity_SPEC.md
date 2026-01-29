# Client Folder Activity Field-Agent Spec

> Agent: client_folder_activity
> Version: 0.1 (draft)
> Protocol: MiMoLo Field-Agent Protocol v0.3 (see AGENT_PROTOCOL_SPEC.md)

## Purpose
Tracks file activity within a client folder to attribute work to a client/project. Multiple instances can run concurrently, one per client.

## Inputs
- client_id: string (required)
- client_name: string (required)
- client_folder: path (required)
- ping_interval_s: 60 (default)
- debounce_window_s: 300 (optional)

## Behavior
- Monitor file changes in client_folder (create/modify/rename/delete).
- Emit low-frequency activity summaries; this is not a high-resolution activity sensor.
- Support multiple running instances with distinct client_id.

## Output Messages

### Summary (client activity)
- type: summary
- data:
  - client_id
  - client_name
  - client_folder
  - activity_window:
    - start: ISO-8601
    - end: ISO-8601
  - files_touched: optional list of filenames or counts
  - project_hint: optional (derived from paths)

## Artifact Storage
This agent does not create media artifacts by default. If it does in the future,
store them in the per-user app data directory:
- Windows: `%AppData%\\mimolo\\client_folder_activity\\...`
- macOS: `~/Library/Application Support/mimolo/client_folder_activity/...`
- Linux: `~/.local/share/mimolo/client_folder_activity/...`

### Heartbeat
- type: heartbeat
- metrics: include events_seen, last_event_age_s

## Error Handling
- If client_folder is missing/unreadable, emit status health=degraded and retry.

## Config Example (mimolo.toml)
[plugins.client_acme]
enabled = true
plugin_type = "field_agent"
executable = "python"
args = [
  "client_folder_activity.py",
  "--client-id", "acme",
  "--client-name", "Acme Corp",
  "--client-folder", "D:/clients/acme"
]
heartbeat_interval_s = 30.0
agent_flush_interval_s = 120.0
