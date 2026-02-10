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
    - `mimolo/core/runtime_ipc_plugin_commands.py` (plugin package IPC list/inspect/install/upgrade routing)
    - `mimolo/core/runtime_ipc_widget_commands.py` (widget IPC command routing and payload assembly)
    - `mimolo/core/runtime_ipc_agent_commands.py` (agent start/stop/restart and instance add/duplicate/remove/update routing)
    - `mimolo/core/runtime_control_actions.py` (queued control-action processing and agent instance mutation/persistence helpers)
    - `mimolo/core/runtime_agent_events.py` (agent summary/heartbeat/log handling)
    - `mimolo/core/runtime_agent_lifecycle.py` (agent start/spawn/stop/restart orchestration)
    - `mimolo/core/runtime_agent_registry.py` (agent state snapshots, template discovery, instance snapshot/cadence helpers)
    - `mimolo/core/runtime_tick.py` (event-loop tick execution: control-action drain, exit reaping, flush cadence, message routing)
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
  - extracted Control snapshot/status synchronization concern into:
    - `mimolo/control_proto/src/control_snapshot_refresher.ts`
      - status refresh + throttled publish
      - monitor settings refresh/update + timing policy apply/restart
      - agent instance/template refresh + initial snapshot bootstrap
  - extracted UI publish/event fanout concern into:
    - `mimolo/control_proto/src/control_window_publisher.ts`
      - canonical emitter for `ops:line`, `ops:traffic`, `ops:status`, `ops:instances`, `ops:monitor-settings`, and `ops:process`
      - `main.ts` now delegates all BrowserWindow publish paths through a single class instead of carrying duplicate helper methods
  - extracted Operations process-state store concern into:
    - `mimolo/control_proto/src/control_operations_state.ts`
      - canonical state holder for Operations managed/unmanaged lifecycle snapshot updates
      - `main.ts` now delegates process-state change/publish logic through the store instead of inline state mutation
  - extracted Control bootstrap/environment and local file-IO concerns into:
    - `mimolo/control_proto/src/control_env.ts` (environment flag/path resolution)
    - `mimolo/control_proto/src/control_ops_log_writer.ts` (queued append-only ops-log writer)
    - `mimolo/control_proto/src/control_timing_loader.ts` (timing config candidate load/parse)
  - `main.ts` now delegates these concerns and remains focused on orchestration composition.
  - `mimolo/control_proto/src/main.ts` now delegates those concerns instead of carrying inline implementations.
- Reduced duplicate loop-interval policy logic in `mimolo/control_proto/src/control_proto_utils.ts` by extracting a shared internal helper (`deriveLoopIntervalMs`) used by status/instance/log poll cadence derivations.
- Continued Runtime IPC maintainability decomposition:
  - extracted agent lifecycle/instance control command handling branch from `mimolo/core/runtime_ipc_commands.py` into:
    - `mimolo/core/runtime_ipc_agent_commands.py`
  - `build_ipc_response(...)` now delegates agent lifecycle/instance control handling through `maybe_handle_agent_control_command(...)`.
  - extracted plugin package command handling branch from `mimolo/core/runtime_ipc_commands.py` into:
    - `mimolo/core/runtime_ipc_plugin_commands.py`
  - `build_ipc_response(...)` now delegates plugin package command handling through `maybe_handle_plugin_store_command(...)`.
  - extracted widget command handling branch from `mimolo/core/runtime_ipc_commands.py` into:
    - `mimolo/core/runtime_ipc_widget_commands.py`
  - `build_ipc_response(...)` now delegates widget command handling through `maybe_handle_widget_command(...)` to keep command routing file focused.
- Continued Runtime maintainability decomposition (non-IPC):
  - extracted tick-loop execution concern from `runtime.py` into:
    - `mimolo/core/runtime_tick.py`
  - `Runtime._tick()` now delegates event-loop body to `execute_tick(...)`, keeping `runtime.py` focused on orchestration composition.
  - extracted agent state/template/instance registry concerns from `runtime.py` into:
    - `mimolo/core/runtime_agent_registry.py`
  - `Runtime` now delegates:
    - `_snapshot_running_agents` / `_set_agent_state` / `_snapshot_agent_states`
    - `_infer_template_id` / `_discover_agent_templates` / `_snapshot_agent_instances`
    - `_effective_interval_s` / `_effective_heartbeat_interval_s` / `_effective_agent_flush_interval_s`
  - extracted agent lifecycle operations from `runtime.py` into:
    - `mimolo/core/runtime_agent_lifecycle.py`
  - `Runtime` now delegates:
    - `_start_agents`
    - `_spawn_agent_for_label`
    - `_stop_agent_for_label`
    - `_restart_agent_for_label`
  - extracted queued control-action execution and agent-instance mutation/persistence helpers from `runtime.py` into:
    - `mimolo/core/runtime_control_actions.py`
  - `Runtime` now delegates:
    - `_queue_control_action` / `_drain_control_actions` / `_process_control_actions`
    - `_add_agent_instance` / `_duplicate_agent_instance` / `_remove_agent_instance` / `_update_agent_instance`
    - `_next_available_label` / `_persist_runtime_config`
- Continued tooling maintainability decomposition for pack-agent utility:
  - extracted core artifact/manifest/hash/archive functions from:
    - `mimolo/utils/src/pack-agent.ts`
  - into:
    - `mimolo/utils/src/pack_agent_core.ts`
  - `pack-agent.ts` now focuses more on CLI flow/control logic while archive/manifest primitives are isolated for reuse and further modularization.
- Continued pack-agent core concern split with compatibility preservation:
  - `mimolo/utils/src/pack_agent_core.ts` converted into a compatibility export barrel.
  - concrete concerns extracted into focused modules:
    - `mimolo/utils/src/pack_agent_types.ts`
    - `mimolo/utils/src/pack_agent_contracts.ts`
    - `mimolo/utils/src/pack_agent_repository.ts`
    - `mimolo/utils/src/pack_agent_manifest_io.ts`
    - `mimolo/utils/src/pack_agent_archive.ts`
  - call sites remained stable via `pack_agent_core.ts` re-exports while reducing core-module complexity.
- Continued tooling maintainability decomposition for pack-agent utility:
  - extracted mode-specific flows from `mimolo/utils/src/pack-agent.ts` into:
    - `mimolo/utils/src/pack_agent_modes.ts`
      - source-list processing mode
      - source-list generation mode
      - single-agent pack mode
  - reduced `pack-agent.ts` to CLI orchestration/dispatch only (no embedded package/repository mode logic).
- Continued pack-agent concern-boundary decomposition and deduplication:
  - converted `mimolo/utils/src/pack_agent_modes.ts` into a compatibility export barrel and moved concrete mode implementations into:
    - `mimolo/utils/src/pack_agent_source_list_mode.ts`
    - `mimolo/utils/src/pack_agent_single_mode.ts`
    - `mimolo/utils/src/pack_agent_versioning.ts`
  - extracted shared behavior that had been duplicated across source-list and single-agent flows into:
    - `mimolo/utils/src/pack_agent_packing_helpers.ts`
      - shared temporary pack workspace orchestration (`packAgentToRepo`)
      - shared repository-skip guidance output (`logRepoSkipNote`)
  - result: mode modules now focus on decision/control flow, while shared pack mechanics and repeated operator messaging are centralized.
- Continued pack-agent exception-flow hardening to align with explicit-control policy:
  - replaced `processSourceList` expected validation throws (missing source path / non-directory source path / missing `build-manifest.toml`) with deterministic conditional error accounting + final failure status.
  - replaced throw-based argument validation in `pack-agent.ts` with explicit parse-result contracts.
  - replaced mode-internal process-exit signaling in `pack_agent_modes.ts` with typed mode results consumed at CLI boundary.
  - annotated remaining invariant/cleanup/boundary exception sites with explicit rationale comments.
- Fixed pack-agent `--verify-existing` deterministic verification blocker:
  - replaced non-deterministic full-archive hash comparison with payload-integrity verification using
    `${plugin_id}/payload_hashes.json` from the existing archive.
  - `verifyExistingArchive(...)` now compares stable file-hash payload content for current sources vs repository artifact.
  - validated with strict QC and targeted runtime checks (built-in agents + clean repo-local `temp_debug/tmp/packtest` pack/verify cycle).
- Added utility error-hardening helpers at:
  - `mimolo/utils/src/pack_agent_errors.ts`
  - standardized errno-aware handling (`ENOENT` expected-path cases) in pack-agent helper/mode/core modules with explicit rethrow on unexpected failures.
- Continued maintainability decomposition for launcher shell orchestration:
  - split `mml.sh` concerns into focused modules under `scripts/mml/`:
    - `common.sh` (config/env/runtime command wiring)
    - `prepare.sh` (prepare/cleanup/build guards)
    - `launch.sh` (operations/control/proto launch + IPC wait)
    - `process.sh` (process inspection)
    - `usage.sh` (help/env output)
    - `args.sh` (global flag parsing)
    - `dispatch.sh` (command routing)
  - reduced `mml.sh` from 518 LOC to 74 LOC so it now acts as a coordinator-only entrypoint.
  - validated launcher behavior parity with syntax + smoke checks:
    - `bash -n mml.sh && bash -n scripts/mml/*.sh`
    - `./mml.sh help`
    - `./mml.sh env`
    - `./mml.sh --no-cache help`
- Hardened portable runtime startup to remove runtime Poetry launcher dependency:
  - `scripts/deploy_portable.sh` now provisions portable Python runtime at `temp_debug/bin/.venv` and hydrates it from the local Poetry environment site-packages.
  - `scripts/mml/common.sh` `run_ops_command` now prefers `MIMOLO_OPERATIONS_PYTHON` (or portable `.venv` python path) before falling back to `poetry run`.
  - `mimolo/control_proto/src/control_operations.ts` now supports direct interpreter startup when `MIMOLO_OPERATIONS_PYTHON` is present.
  - `scripts/bundle_app.sh` now writes `MIMOLO_OPERATIONS_PYTHON` into bundle defaults so bundled app operations controls do not require poetry launcher on runtime PATH.
- Hardened Control renderer non-critical promise handling:
  - replaced silent swallow on reconnect-backoff reset invocation in
    `mimolo/control_proto/src/ui_renderer_sections/state_and_ops.ts`
  - now emits explicit warning line when reset command fails.
- Tightened runtime exception handling policy across core paths by replacing broad catches with explicit exception tuples and preserving plugin-boundary broad handling only where intentionally justified.
- Updated canonical backlog reality to note that Item 1 lifecycle hardening work now includes maintainability-oriented module boundary cleanup, not only behavior fixes.
- Refreshed verification snapshot context in active planning docs to stay aligned with latest strict checks and targeted IPC/runtime regression slices.
- Verified strict QC for this hardening pass:
  - `npm --prefix mimolo/utils run build` => clean
  - `poetry run ruff check .` => clean
  - `poetry run mypy mimolo scripts/qc_exception_scan.py` => clean
  - `poetry run pytest -q` => 132 passed
- Updated canonical backlog prioritization:
  - maintainability decomposition and concern-boundary compliance is now explicit top priority in
    `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md` (`Item 10`).

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
