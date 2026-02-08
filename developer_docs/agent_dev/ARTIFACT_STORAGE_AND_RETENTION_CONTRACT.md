# Artifact Storage and Retention Contract

> Status: Canonical design contract for upcoming agent implementations.
> Scope: Operations <-> Agent data boundary, artifact storage, archive/restore, retention controls.

## 1. Intent

MiMoLo keeps the event stream lightweight while preserving rich evidence as user-controlled breadcrumbs.

Core idea:
- Protocol `data` carries structured metadata and references.
- Heavy payloads (images, large binaries, raw captures) live in per-agent instance storage.

## 2. Data Boundary Rules

1. Protocol and vault records must remain lightweight JSON metadata.
2. Heavy artifacts must never be embedded in protocol messages.
3. `summary` data should include references to artifacts, not artifact bytes.
4. Artifact references must be sufficient to verify and locate content later.

## 3. Required Artifact Reference Fields

When an event references an artifact, include:
- `artifact_id`: stable identifier inside the instance scope.
- `rel_path`: path relative to the instance root.
- `sha256`: content digest.
- `bytes`: file size.
- `mime`: media type.
- `captured_at`: ISO-8601 timestamp.
- `retention_class`: one of `ephemeral`, `retained`, `archived`.

## 4. Per-Instance Storage Layout

Base root is `MIMOLO_DATA_DIR` (injected into each agent process).

Recommended layout:
- `agents/<plugin_id>/<instance_id>/artifacts/`
- `agents/<plugin_id>/<instance_id>/index/`
- `agents/<plugin_id>/<instance_id>/archives/`

`instance_id` is the stable identity for a configured instance (not just display label).

## 5. Purge, Archive, Restore Rules

Hard rules:
1. Never purge without explicit user permission.
2. Always provide opportunity to archive before purge.
3. Archive format must support in-place restoration.
4. Restoration is plugin-owned so plugin-specific semantics are preserved.
5. Breadcrumb metadata remains after archive/purge (tombstone records).

## 6. Retention Policy

Default behavior:
- No automatic TTL purge.
- Size-based guardrails produce warnings only.
- User chooses manual actions: `pin`, `archive`, `purge`, `restore`.
- Optional quarterly/annual archive workflows are user-triggered.

## 7. Archive Manifest Requirements

Each archive unit must include a manifest with:
- `plugin_id`
- `instance_id`
- `instance_label` (display convenience)
- `created_at`
- list of archived entries:
  - original `rel_path`
  - hash and size
  - timestamp range
  - plugin-specific restore metadata
- restore target root (`MIMOLO_DATA_DIR`-relative)

## 8. Implementation Status

Implemented now:
- `MIMOLO_DATA_DIR` process env injection exists.
- Event `data` supports arbitrary lightweight JSON structures.

Planned (not yet fully implemented):
- Standardized artifact index format.
- Archive manifest writer/reader.
- Plugin restore API handshake.
- User-facing archive-before-purge workflow in Control.
