# developer_docs Changelog

All notable documentation changes under `developer_docs/` are tracked in this file.

## 2026-02-10

### Added
- Added comprehensive code-health audit bundle at `developer_docs/2026.02.10 CODE-MEGASCAN/` with:
  - method/scope document
  - per-file metrics (`raw_line_count`, per-file function min/max/avg)
  - PS1-to-SH parity map (translated pair vs standalone)
  - duplicate-function cluster report
  - concern-boundary report and mixed-concern index
  - Python exception-policy audit and CSV findings
  - path portability and timing-literal candidate scans
  - API surface index (module/function inventory)
  - risk register and executive summary.

### Changed
- Updated architecture-truth documentation to reflect active maintainability refactor of orchestration files:
  - `runtime.py` responsibilities are now partially extracted into dedicated modules:
    - `mimolo/core/runtime_ipc_commands.py` (IPC command routing)
    - `mimolo/core/runtime_ipc_server.py` (IPC socket server plumbing)
    - `mimolo/core/runtime_agent_events.py` (agent summary/heartbeat/log handling)
    - `mimolo/core/runtime_widget_support.py` (screen-tracker widget thumbnail/data-uri/render helpers)
    - `mimolo/core/runtime_monitor_settings.py` (monitor settings update/persist helper)
    - `mimolo/core/runtime_shutdown.py` (shutdown/flush/segment lifecycle)
  - `mimolo/control_proto/src/main.ts` responsibilities are now partially extracted into:
    - `mimolo/control_proto/src/types.ts` (shared control/runtime types)
    - `mimolo/control_proto/src/control_timing.ts` (control timing parsing/normalization)
    - `mimolo/control_proto/src/control_proto_utils.ts` (IPC payload parsing + monitor/loop utility logic)
    - `mimolo/control_proto/src/control_command_wrappers.ts` (agent/widget/install IPC wrapper helpers)
    - `mimolo/control_proto/src/ui_html.ts` (renderer HTML template)
- Continued Control proto decomposition to enforce concern boundaries in live code:
  - `mimolo/control_proto/src/control_persistent_ipc.ts` now owns persistent socket transport + queue/backoff/timeout behavior.
  - `mimolo/control_proto/src/control_operations.ts` now owns Operations process lifecycle policy.
  - `mimolo/control_proto/src/control_ipc_handlers.ts` now owns Electron IPC handler registration and payload validation.
  - `mimolo/control_proto/src/main.ts` is now reduced to composition/wiring concerns rather than carrying transport/process/API implementation directly.
- Continued Control renderer maintainability decomposition:
  - `mimolo/control_proto/src/ui_html.ts` is now a thin composer for style, shell, and renderer script assembly.
  - moved CSS and DOM shell concerns into:
    - `mimolo/control_proto/src/ui_style.ts`
    - `mimolo/control_proto/src/ui_shell.ts`
  - moved renderer script into sectioned modules with stable execution order:
    - `mimolo/control_proto/src/ui_renderer_script.ts`
    - `mimolo/control_proto/src/ui_renderer_sections/state_and_ops.ts`
    - `mimolo/control_proto/src/ui_renderer_sections/modals.ts`
    - `mimolo/control_proto/src/ui_renderer_sections/indicators_and_widgets.ts`
    - `mimolo/control_proto/src/ui_renderer_sections/commands_and_install.ts`
    - `mimolo/control_proto/src/ui_renderer_sections/cards_and_bootstrap.ts`
- Continued Control main-process maintainability decomposition:
  - extracted Operations log tail/read/init concern into:
    - `mimolo/control_proto/src/control_ops_log_tailer.ts`
  - extracted template-list cache concern into:
    - `mimolo/control_proto/src/control_template_cache.ts`
  - extracted status/log/instance polling timer orchestration into:
    - `mimolo/control_proto/src/control_background_loops.ts`
  - extracted quit-policy and quit-prompt decision flow into:
    - `mimolo/control_proto/src/control_quit.ts`
  - extracted BrowserWindow construction and HTML load wiring into:
    - `mimolo/control_proto/src/control_window.ts`
  - `mimolo/control_proto/src/main.ts` now delegates those concerns instead of carrying inline implementations.
- Reduced duplicate loop-interval policy logic in `mimolo/control_proto/src/control_proto_utils.ts` by extracting a shared internal helper (`deriveLoopIntervalMs`) used by status/instance/log poll cadence derivations.
- Tightened runtime exception handling policy across core paths by replacing broad catches with explicit exception tuples and preserving plugin-boundary broad handling only where intentionally justified.
- Updated canonical backlog reality to note that Item 1 lifecycle hardening work now includes maintainability-oriented module boundary cleanup, not only behavior fixes.
- Refreshed verification snapshot context in active planning docs to stay aligned with latest strict checks and targeted IPC/runtime regression slices.

## 2026-02-09

### Changed
- Updated implementation matrix and changelog truth alignment for Control reconnect/cadence policy:
  - Control timing is now explicitly TOML-driven via `[control]` policy keys.
  - reconnect churn mitigation is now documented as config-first behavior (throttled status + escalating backoff).
  - disconnected interactivity policy is documented: instance/widget/top-level control actions are disabled while Operations is unavailable.
- Updated changelog alignment to reflect current implementation status:
  - Control proto now renders sanitized widget HTML fragments in-canvas.
  - Operations/runtime now exposes monitor settings IPC read/update commands and persists validated monitor updates.
  - `screen_tracker` now has real app-window/full-screen capture behavior with thumbnail controls and not-open placeholder artifacts.
- Recorded security posture correction for widget media rendering:
  - runtime delivers image payloads via safe `data:image/...` URIs for renderer compatibility under `data:` origin without weakening Electron security defaults.
- Updated canonical backlog status in `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md`:
  - promoted Operations lifecycle/process-ownership hardening as explicit highest-priority execution item.
  - documented partial completion progress (`mimolo ops` singleton guard, process diagnostics, external-stop IPC path) and remaining gaps.
  - refreshed verification snapshot from strict rerun:
    - `poetry run pytest -q` => 132 passed
    - `poetry run mypy mimolo` => clean
    - `poetry run ruff check .` => clean
    - `npm run build` in `mimolo/control_proto` => clean
  - added a `Priority Index` section so reprioritization can be done without renumbering backlog items.
  - converted active backlog entries to linkable `Item N` headings and updated the priority index to Obsidian-style section links with editable labels (`<highest item>`, `<next item>`).

## 2026-02-08

### Added
- Added protocol reality map at `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md` to document implemented vs planned behavior for Agent JLP and Control IPC.
- Added canonical artifact lifecycle contract at `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`.
- Added minimal archive/restore IPC contract for Control <-> Operations at `developer_docs/control_dev/ARCHIVE_RESTORE_IPC_MIN_SPEC.md`.
- Added minimal widget render/action IPC contract for Control <-> Operations and Agent bridge at `developer_docs/control_dev/WIDGET_RENDER_IPC_MIN_SPEC.md`.
- Added plugin distribution trust policy at `developer_docs/agent_dev/PLUGIN_TRUST_AND_SIGNING_POLICY.md` (signed+allowlisted release mode, explicit unsafe developer sideload mode).

### Changed
- Updated storage conventions in `developer_docs/agent_dev/DATA_STORAGE_CONVENTIONS.md` to enforce lightweight event payloads plus per-plugin/per-instance artifact layout.
- Updated `developer_docs/agent_dev/client_folder_activity/client_folder_activity_SPEC.md` from draft to implementation-ready v0.2 spec with bounded summary schema and command handling expectations.
- Updated `developer_docs/agent_dev/screen_tracker/screen_tracker_SPEC.md` from draft to implementation-ready v0.2 spec with artifact-reference summary schema and explicit archive-before-purge behavior.
- Formalized user-control retention policy in docs: no automatic purge by default, no purge without explicit permission, archive opportunity required before purge, and in-place restore requirement.
- Reworked `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md` into the canonical active backlog with updated implementation truth and prioritized execution order.
- Replaced `developer_docs/8_Future_Roadmap_and_Summary.md` with a strategic-only roadmap and explicit link to the canonical backlog.
- Updated `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md` to reflect current Control prototype capabilities and persistent IPC reliability intent.
- Updated `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md` to reflect persistent Control IPC transport, request-id correlation behavior, and current widget IPC stub reality.
- Updated `developer_docs/2026.02.05 NOTES/README.md` to point explicitly to canonical backlog and strategic roadmap locations.
- Updated plugin install posture documentation for Control:
  - release/default mode does not expose runtime zip sideload install UI.
  - runtime sideload remains developer-mode-only with explicit unsafe warning requirements.
  - backlog matrix now reflects `+ Add` template-list ground truth and `--dev`-gated sideload behavior.
- Updated indicator planning notes in canonical backlog:
  - documented strict transport-truth indicator direction (interactive tx/rx vs separate background activity signal).
  - added deferred optional “intent-dot” queue-lifecycle concept with explicit defer rationale.
- Updated active docs to clarify doctrine as capability-open but trust-closed distribution posture:
  - `developer_docs/agent_dev/AGENT_DEV_GUIDE.md`
  - `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md`
  - `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`
  - `developer_docs/TERMINOLOGY_MAP.md`
  - `developer_docs/security_agent.md`
  - `developer_docs/8_Future_Roadmap_and_Summary.md`
- Updated `developer_docs/6_Extensibility_and_Plugin_Development.md` historical reference wording to avoid contradictory "open ecosystem" interpretation against current trust policy.

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
