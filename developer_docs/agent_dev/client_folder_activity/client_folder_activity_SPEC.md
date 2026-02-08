# Client Folder Activity Agent Spec

> Agent: `client_folder_activity`
> Version: 0.2 (implementation-ready spec)
> Protocol: MiMoLo Agent Protocol v0.3 (see `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md`)
> Storage contract: `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`

## 1. Purpose

Track folder-level file activity for client/project attribution.
Multiple instances may run concurrently, one per client or workspace scope.

This agent is a metadata monitor, not a heavy artifact producer by default.

## 2. Inputs

Required:
- `client_id: str`
- `client_name: str`
- `watch_paths: list[path]` (one or more directories)

Optional:
- `include_globs: list[str]` (default `["**/*"]`)
- `exclude_globs: list[str]` (default system/temp ignores)
- `follow_symlinks: bool` (default `false`)
- `coalesce_window_s: float` (default `2.0`)
- `poll_interval_s: float` (fallback polling cadence when native watch unavailable)
- `emit_path_samples_limit: int` (default `50`)

## 3. Runtime Behavior

1. Watch configured paths for create/modify/delete/rename events.
2. Coalesce noisy bursts into windows (`coalesce_window_s`).
3. Accumulate counts and bounded path samples until orchestrator `flush`.
4. Emit `summary` with lightweight metadata only.
5. Emit `heartbeat` for liveness and queue metrics.
6. On recoverable failures (permission, missing path), emit `status`/`error` and continue.

## 4. Summary Payload Schema (`type = "summary"`)

`data` fields:
- `schema`: `"client_folder_activity.summary.v1"`
- `client_id`
- `client_name`
- `watch_paths`
- `window`:
  - `start`
  - `end`
  - `duration_s`
- `counts`:
  - `created`
  - `modified`
  - `deleted`
  - `renamed`
  - `total`
- `top_extensions`: list of `{ext, count}`
- `path_samples`: bounded list of relative paths (size-limited)
- `dropped_events`: integer count dropped due to backpressure/coalescing limits

Rules:
- Keep payload small and bounded.
- No file contents in payload.
- No binary blobs in payload.

## 5. Heartbeat Payload (`type = "heartbeat"`)

`metrics` fields:
- `events_seen_total`
- `events_buffered`
- `last_event_age_s`
- `watch_path_count`
- `degraded_path_count`

## 6. Status and Error Semantics

Use `status` for degraded but running state:
- `health = "degraded"` when one or more watch paths fail.

Use `error` for actionable failures:
- invalid watch configuration
- repeated OS watch backend failures
- serialization failures

The agent should keep running whenever safe to do so.

## 7. Artifact and Storage Policy

Default behavior:
- no heavy artifacts produced.

If optional evidence snapshots are added later:
- write under `MIMOLO_DATA_DIR/agents/client_folder_activity/<instance_id>/artifacts/...`
- emit only references in `data` (`artifact_id`, `rel_path`, `sha256`, `bytes`, `mime`)
- follow explicit archive-before-purge rules from storage contract.

## 8. Command Handling Expectations

Must honor:
- `flush`: emit summary
- `stop`: stop sampling and ACK
- `start`: resume sampling
- `shutdown`: graceful exit
- `sequence`: execute in order and ACK `stop` and `flush`

## 9. Config Example (`mimolo.toml`)

```toml
[plugins.client_acme]
enabled = true
plugin_type = "agent"
executable = "poetry"
args = [
  "run", "python", "client_folder_activity/client_folder_activity.py",
  "--client-id", "acme",
  "--client-name", "Acme Corp",
  "--watch-path", "/Users/me/work/acme",
  "--watch-path", "/Users/me/work/acme-assets",
  "--coalesce-window-s", "2.0"
]
heartbeat_interval_s = 15.0
agent_flush_interval_s = 60.0
launch_in_separate_terminal = false
```

## 10. Implementation Notes

Implemented now in platform:
- protocol envelope and orchestrator routing for summary/heartbeat/error
- per-instance configuration lifecycle in Operations IPC

To implement this plugin:
- add concrete watcher backend + fallback polling
- enforce bounded payload limits
- emit schema-tagged summaries (`schema = ...v1`)
