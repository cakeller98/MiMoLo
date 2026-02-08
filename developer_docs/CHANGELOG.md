# developer_docs Changelog

All notable documentation changes under `developer_docs/` are tracked in this file.

## 2026-02-08

### Added
- Added protocol reality map at `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md` to document implemented vs planned behavior for Agent JLP and Control IPC.
- Added canonical artifact lifecycle contract at `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`.
- Added minimal archive/restore IPC contract for Control <-> Operations at `developer_docs/control_dev/ARCHIVE_RESTORE_IPC_MIN_SPEC.md`.
- Added minimal widget render/action IPC contract for Control <-> Operations and Agent bridge at `developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md`.

### Changed
- Updated storage conventions in `developer_docs/agent_dev/DATA_STORAGE_CONVENTIONS.md` to enforce lightweight event payloads plus per-plugin/per-instance artifact layout.
- Updated `developer_docs/agent_dev/client_folder_activity/client_folder_activity_SPEC.md` from draft to implementation-ready v0.2 spec with bounded summary schema and command handling expectations.
- Updated `developer_docs/agent_dev/screen_tracker/screen_tracker_SPEC.md` from draft to implementation-ready v0.2 spec with artifact-reference summary schema and explicit archive-before-purge behavior.
- Formalized user-control retention policy in docs: no automatic purge by default, no purge without explicit permission, archive opportunity required before purge, and in-place restore requirement.

## 2026-02-06

### Added
- Added canonical workflow-intent consolidation at `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
- Added comprehensive documentation triage ledger at `developer_docs/2026.02.05 NOTES/DEVELOPER_DOCS_TRIAGE_2026-02-06.md`.
- Added centralized archive index at `developer_docs/archive/README.md`.

### Changed
- Updated canonical notes index and matrix to include unified workflow-intent and full docs triage references.
- Formalized documentation governance: code remains implementation truth; historical docs are reference-only unless merged into canonical 2026.02.05 notes.
- Centralized archived docs into `developer_docs/archive/` and removed scattered local archive folders.
- Added `Reference-History` banner notes to all `MERGE`-classified documents.
- Updated 2026.01.28 reference README and triage paths to point to centralized archive locations.
- Standardized active docs terminology to use `Control` as the canonical UI term (removed mixed Dashboard/Controller wording).
- Moved Control specification docs from `developer_docs/dashboard_dev/DASH_SPECIFICATION.md` to `developer_docs/control_dev/CONTROL_SPECIFICATION.md` and updated references.
- Updated preserved notes to current package paths: IPC prototype `mimolo/control_proto` and Electron app `mimolo-control`.
