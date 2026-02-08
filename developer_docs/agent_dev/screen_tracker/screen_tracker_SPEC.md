# Screen Tracker Agent Spec

> Agent: `screen_tracker`
> Version: 0.2 (implementation-ready spec)
> Protocol: MiMoLo Agent Protocol v0.3 (see `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md`)
> Storage contract: `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`

## 1. Purpose

Capture periodic visual breadcrumbs for workflow context.
The agent writes image artifacts to per-instance storage and emits only lightweight references in protocol `data`.

## 2. Inputs

Required:
- `capture_interval_s: float`
- `mode: "active_window" | "full_screen"`

Optional:
- `image_format: "jpg" | "png"` (default `jpg`)
- `jpeg_quality: int` (default `35`)
- `scale: float` (default `0.10`)
- `letterbox: bool` (default `false`)
- `max_dimension_px: int` (default `1920`)
- `redact_regions: list[rect]` (optional privacy masks)
- `capture_on_user_idle: bool` (default `false`)

## 3. Runtime Behavior

1. Capture at configured interval while sampling is enabled.
2. Save artifact to per-instance artifact storage.
3. Record artifact metadata entry in local index.
4. On orchestrator `flush`, emit summary referencing captures in the flush window.
5. Continue running on recoverable capture failures, emitting `error` details.

## 4. Summary Payload Schema (`type = "summary"`)

`data` fields:
- `schema`: `"screen_tracker.summary.v1"`
- `capture_mode`
- `window`:
  - `start`
  - `end`
  - `duration_s`
- `capture_count`
- `captures`: list (bounded) of:
  - `artifact_id`
  - `rel_path`
  - `sha256`
  - `bytes`
  - `mime`
  - `captured_at`
  - `width`
  - `height`
  - `scale`
  - `quality` (for jpeg)
  - `retention_class`
- `active_app_samples` (optional bounded list)
- `dropped_capture_count` (if bounded list truncated)

Rules:
- No raw image bytes in `data`.
- `captures` list must be bounded by config to keep event payloads lightweight.

## 5. Heartbeat Payload (`type = "heartbeat"`)

`metrics` fields:
- `captures_total`
- `captures_pending_flush`
- `last_capture_age_s`
- `capture_failures_total`
- `artifact_store_bytes`

## 6. Error and Status Semantics

Use `status` for degradations:
- screen capture backend unavailable
- permission not granted (screen recording entitlement)

Use `error` for failed capture attempts and write failures.

Agent should continue unless failure is non-recoverable.

## 7. Artifact and Storage Policy

Storage root:
- `MIMOLO_DATA_DIR/agents/screen_tracker/<instance_id>/artifacts/...`
- `MIMOLO_DATA_DIR/agents/screen_tracker/<instance_id>/index/...`
- `MIMOLO_DATA_DIR/agents/screen_tracker/<instance_id>/archives/...`

Retention rules:
1. No automatic purge by default.
2. Purge only with explicit user permission.
3. Always offer archive before purge.
4. Archives must support plugin-controlled in-place restore.
5. Keep breadcrumb metadata (tombstones) after archive/purge.

## 8. Command Handling Expectations

Must honor:
- `flush`: emit summary with artifact references
- `stop`: pause capture and ACK
- `start`: resume capture
- `shutdown`: graceful exit
- `sequence`: execute ordered steps with required ACKs

## 9. Config Example (`mimolo.toml`)

```toml
[plugins.screen_tracker_design]
enabled = true
plugin_type = "agent"
executable = "poetry"
args = [
  "run", "python", "screen_tracker/screen_tracker.py",
  "--capture-interval-s", "60",
  "--mode", "active_window",
  "--image-format", "jpg",
  "--jpeg-quality", "35",
  "--scale", "0.10"
]
heartbeat_interval_s = 15.0
agent_flush_interval_s = 60.0
launch_in_separate_terminal = false
```

## 10. Implementation Notes

Implemented now in platform:
- protocol transport, summary routing, and per-instance lifecycle control

To implement this plugin:
- add cross-platform capture backend adapter
- add artifact index writer with hash + metadata
- add archive/restore hooks matching storage contract
