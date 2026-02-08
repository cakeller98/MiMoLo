# Control <-> Operations Archive/Restore IPC (Minimal Spec)

Date: 2026-02-08
Status: Planned contract (not fully implemented yet)

## 1. Scope

This spec defines the minimal IPC commands needed to support:
- artifact inventory visibility
- user-driven archive creation
- plugin-owned in-place restore
- explicit-permission purge with archive opportunity

This spec does not change Agent JLP. It is Control <-> Operations IPC only.

## 2. Envelope

Use the current Operations IPC response shape:

Request:
```json
{"cmd":"<command_name>", "...":"..."}
```

Response:
```json
{"ok":true,"cmd":"<command_name>","timestamp":"...","data":{...}}
```

Error response:
```json
{"ok":false,"cmd":"<command_name>","timestamp":"...","error":"<error_code>"}
```

## 3. Identity Model

All archive/restore operations are scoped by:
- `plugin_id` (agent plugin type)
- `instance_id` (stable configured instance identity)

Optional display field:
- `instance_label`

## 4. Minimal Command Set

## 4.1 `get_artifact_inventory`

Purpose:
- return lightweight storage stats and retention warnings per plugin/instance.

Request:
```json
{"cmd":"get_artifact_inventory"}
```

Success `data`:
- `instances`: list of
  - `plugin_id`
  - `instance_id`
  - `instance_label`
  - `artifact_bytes`
  - `artifact_count`
  - `archive_bytes`
  - `archive_count`
  - `warnings` (size thresholds, index issues)

## 4.2 `list_instance_archives`

Purpose:
- list archives available for one plugin instance.

Request:
```json
{"cmd":"list_instance_archives","plugin_id":"screen_tracker","instance_id":"inst_abc123"}
```

Success `data`:
- `archives`: list of
  - `archive_id`
  - `created_at`
  - `entry_count`
  - `total_bytes`
  - `manifest_version`
  - `restore_capable` (bool)

## 4.3 `archive_instance_artifacts`

Purpose:
- create an archive from selected artifacts for one instance.

Request:
```json
{
  "cmd":"archive_instance_artifacts",
  "plugin_id":"screen_tracker",
  "instance_id":"inst_abc123",
  "selection":{"artifact_ids":["a1","a2","a3"]},
  "reason":"user_archive_before_cleanup"
}
```

Success `data`:
- `accepted` (bool)
- `archive_id`
- `entry_count`
- `total_bytes`
- `plugin_restore_metadata` (plugin-defined)

Notes:
- archive creation is plugin-owned for format details.
- Operations records audit breadcrumb event.

## 4.4 `restore_instance_archive`

Purpose:
- restore archived artifacts in place for one instance.

Request:
```json
{
  "cmd":"restore_instance_archive",
  "plugin_id":"screen_tracker",
  "instance_id":"inst_abc123",
  "archive_id":"arc_2026_001",
  "mode":"in_place"
}
```

Success `data`:
- `accepted` (bool)
- `restored_count`
- `restored_bytes`
- `restore_root`
- `plugin_restore_report`

Rules:
- restore path resolution is plugin-owned.
- restore must target original instance subtree.

## 4.5 `plan_instance_purge`

Purpose:
- produce a purge plan token; no deletion happens here.

Request:
```json
{
  "cmd":"plan_instance_purge",
  "plugin_id":"screen_tracker",
  "instance_id":"inst_abc123",
  "selection":{"artifact_ids":["a1","a2","a3"]}
}
```

Success `data`:
- `plan_id`
- `entry_count`
- `total_bytes`
- `archive_options`:
  - `can_create_archive` (bool)
  - `existing_archives` (list of `archive_id`)
- `expires_at`

Hard rule:
- plan response must always include archive options before purge can execute.

## 4.6 `execute_instance_purge`

Purpose:
- perform deletion only after explicit confirmation.

Request:
```json
{
  "cmd":"execute_instance_purge",
  "plan_id":"purge_plan_001",
  "confirm":true,
  "archive_decision":{
    "action":"create_archive"
  }
}
```

Allowed `archive_decision.action`:
- `create_archive`
- `use_existing_archive` (requires `archive_id`)
- `decline_archive`

Success `data`:
- `purged_count`
- `purged_bytes`
- `archive_id` (if created/used)
- `tombstones_written` (bool)

Rules:
1. `confirm` must be true.
2. If no valid archive decision provided, reject.
3. Archive opportunity is mandatory; archive itself is user choice.
4. Purge action must emit audit breadcrumb event.

## 5. Error Codes (Initial)

- `missing_plugin_id`
- `missing_instance_id`
- `unknown_instance`
- `missing_plan_id`
- `invalid_plan_id`
- `plan_expired`
- `missing_confirmation`
- `missing_archive_decision`
- `archive_create_failed`
- `restore_failed`
- `plugin_not_restore_capable`
- `plugin_operation_failed`

## 6. Audit/Breadcrumb Events

Operations should write lightweight events for:
- `artifact_archive_created`
- `artifact_archive_restored`
- `artifact_purge_planned`
- `artifact_purged`

Each event should include:
- `plugin_id`, `instance_id`, `user_action`, `counts`, `bytes`, `archive_id` (if any)

## 7. Implementation Notes

Implemented today:
- base IPC transport and command routing shape.

Planned:
- these archive/restore commands in runtime IPC handler
- plugin archive/restore adapters
- Control UI flows for archive-before-purge confirmation
