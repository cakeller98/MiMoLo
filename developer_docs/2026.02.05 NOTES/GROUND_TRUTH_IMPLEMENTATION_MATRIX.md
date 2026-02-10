# Ground Truth Implementation Matrix (Canonical Active Backlog)

Date: 2026-02-10
Rule: code and tests are implementation truth when docs differ.

Verification snapshot:
- `poetry run pytest -q` => 132 passed
- `poetry run mypy mimolo` => clean
- `poetry run ruff check .` => clean
- `npm run build` in `mimolo/control_proto` => clean

Deep scan reference:
- `developer_docs/2026.02.10 CODE-MEGASCAN/` (repo-wide py/ts/sh + ps1-parity audit artifacts)

## 1) Implemented (Current Ground Truth)

1. Operations runtime and Agent JLP lifecycle
- Status: Implemented
- Includes:
  - agent spawn/monitor/flush/shutdown
  - Agent JLP message handling (`handshake`, `summary`, `heartbeat`, `log`, `error`, `ack`)
  - lifecycle state snapshots for Control
- Evidence:
  - `mimolo/core/runtime.py`
  - `mimolo/core/runtime_ipc_commands.py`
  - `mimolo/core/runtime_ipc_agent_commands.py`
  - `mimolo/core/runtime_ipc_plugin_commands.py`
  - `mimolo/core/runtime_ipc_widget_commands.py`
  - `mimolo/core/runtime_ipc_server.py`
  - `mimolo/core/runtime_control_actions.py`
  - `mimolo/core/runtime_agent_events.py`
  - `mimolo/core/runtime_agent_lifecycle.py`
  - `mimolo/core/runtime_agent_registry.py`
  - `mimolo/core/runtime_tick.py`
  - `mimolo/core/runtime_widget_support.py`
  - `mimolo/core/runtime_monitor_settings.py`
  - `mimolo/core/runtime_shutdown.py`
  - `mimolo/core/agent_process.py`
  - `mimolo/core/protocol.py`

2. Operations <-> Control IPC command server
- Status: Implemented
- Commands:
  - `ping`
  - `get_registered_plugins`
  - `list_agent_templates`
  - `get_agent_instances`
  - `get_agent_states`
  - `start_agent` / `stop_agent` / `restart_agent`
  - `add_agent_instance` / `duplicate_agent_instance` / `remove_agent_instance` / `update_agent_instance`
- Evidence:
  - `mimolo/core/runtime.py`

3. Control proto (Electron) operational testbed
- Status: Implemented (prototype scope)
- Includes:
  - operations log stream view
  - per-instance cards with start/stop/restart
  - per-instance duplicate/delete/configure
  - `+ Add` modal uses the live template registry as ground-truth source for instance creation
  - widget panel on each card with manual update + pause/play
  - persistent IPC channel with bounded queued requests and timeout handling
  - reconnect/poll/backoff timing policy loaded from `[control]` in `mimolo.toml` (no hard-coded cadence policy)
  - disconnected-state status throttling and reconnect backoff escalation
  - disconnected-state interactivity gating (instance controls, widget controls, and top-level add/config/install actions disabled while Operations is unavailable)
  - plugin zip install UI is disabled by default and enabled only in explicit developer mode (`MIMOLO_CONTROL_DEV_MODE=1`, for example via `mml.sh --dev`)
  - Evidence:
    - `mimolo/control_proto/src/main.ts`
    - `mimolo/control_proto/src/types.ts`
    - `mimolo/control_proto/src/control_timing.ts`
    - `mimolo/control_proto/src/control_proto_utils.ts`
    - `mimolo/control_proto/src/control_command_wrappers.ts`
    - `mimolo/control_proto/src/control_persistent_ipc.ts`
    - `mimolo/control_proto/src/control_operations.ts`
    - `mimolo/control_proto/src/control_operations_state.ts`
    - `mimolo/control_proto/src/control_env.ts`
    - `mimolo/control_proto/src/control_ops_log_writer.ts`
    - `mimolo/control_proto/src/control_timing_loader.ts`
    - `mimolo/control_proto/src/control_ipc_handlers.ts`
    - `mimolo/control_proto/src/control_snapshot_refresher.ts`
    - `mimolo/control_proto/src/control_window_publisher.ts`
    - `mimolo/control_proto/src/ui_html.ts`

4. Runtime widget IPC command names (stable stubs)
- Status: Implemented as non-breaking stubs
- Commands:
  - `get_widget_manifest`
  - `request_widget_render`
  - `dispatch_widget_action`
- Behavior:
  - returns structured `not_implemented_yet` responses for early Control integration
- Evidence:
  - `mimolo/core/runtime.py`
  - `tests/test_runtime_widget_ipc_stubs.py`

5. Agent template discovery and instance provisioning model
- Status: Implemented
- Behavior:
  - template discovery from `mimolo/agents/<agent_name>/`
  - instance-level config persisted by Operations
- Evidence:
  - `mimolo/core/runtime.py`
  - `mimolo/core/config.py`

6. Initial plugin scaffolds for planned real agents
- Status: Implemented (scaffold level)
- Added:
  - `client_folder_activity`
  - `screen_tracker`
- Evidence:
  - `mimolo/agents/client_folder_activity/client_folder_activity.py`
  - `mimolo/agents/screen_tracker/screen_tracker.py`

## 2) Planned / Partial (Keep Explicitly)

1. End-to-end widget render bridge
- Status: Planned / partial
- Gap:
  - runtime IPC names exist, but Operations does not yet request render payloads from agent instances and sanitize/render approved output end-to-end.

2. Install/upgrade lifecycle from packaged zips
- Status: Planned / partial
- Gap:
  - packaging exists, but full Operations-managed install registry, upgrade policy, and release-grade Control UX flow are not complete.
  - current default flow is distribution/build-time plugin seeding; runtime zip sideload is intentionally developer-mode-only.

3. Archive/restore/purge workflow with explicit permission gates
- Status: Planned / partial
- Gap:
  - contracts/specs exist; runtime + Control behavior is not yet fully implemented.

4. Production-grade agent implementations
- Status: Planned / partial
- Gap:
  - `client_folder_activity` and `screen_tracker` exist as runnable scaffolds, but still need full production behavior and expanded tests.

5. Commercial Control app parity
- Status: Planned / partial
- Gap:
  - `mimolo-control` exists but prototype-first work is currently concentrated in `mimolo/control_proto`.

## 3) Active Priority Backlog (Execution Order)

### Priority Index (Reprioritize Here, Keep Backlog Item Numbers Stable)

1. [[#Item 10 — Maintainability-first decomposition and concern-boundary compliance]]
2. [[#Item 1 — Operations lifecycle ownership + orphan-process elimination]]
3. [[#Item 2 — Implement true widget render pipeline through Operations]]
4. [[#Item 3 — Finish agent package install/upgrade lifecycle]]
5. [[#Item 4 — Complete archive-before-purge workflow]]
6. [[#Item 5 — Hardening pass for `client_folder_activity` and `screen_tracker`]]
7. [[#Item 6 — Promote control_proto patterns into commercial Control app]]
8. [[#Item 7 — Repository-wide path handling normalization audit (Python + TypeScript)]]
9. [[#Item 8 — Plugin trust boundary and capability-gated isolation model]]
10. [[#Item 9 — Optional indicator intent-dot for request lifecycle diagnostics (deferred)]]

Priority-index rule:
- Reprioritize by editing this index only.
- Do not renumber backlog items below unless adding/removing items.

### Item 1 — Operations lifecycle ownership + orphan-process elimination
- Done when:
  - Operations is singleton-correct: exactly one active `mimolo ops` runtime per data root.
  - `stop operations` always performs full subordinate shutdown (all agents stop, then Operations exits, lock released).
  - Control quit flow prompts user: leave Operations running vs shutdown Operations+Agents.
  - Choosing shutdown from Control reliably stops Operations and all agents with no orphan processes.
  - `mml.sh ps` / `mml.ps1 ps` confirms clean state after repeated start/stop/restart/quit cycles.
  - Lifecycle behavior is validated by regression tests (stop/restart/quit paths).
- Progress update (2026-02-09):
  - implemented:
    - `mimolo ops` canonical command (with `monitor` compatibility alias)
    - operations singleton lock guard in runtime startup path
    - Control stop path can request external/unmanaged Operations shutdown via IPC
    - launcher process diagnostics (`mml.sh ps`, `mml.ps1 ps`)
    - Control disconnect policy hardening:
      - transport status chatter reduced via configurable throttling/backoff
      - control actions are disabled while Operations is unavailable
  - remaining:
    - explicit Control quit prompt (`leave running` vs `shutdown operations+agents`)
    - comprehensive lifecycle regression coverage for repeated start/stop/restart/quit cycles
    - residual orphan-process scenarios still under active investigation and hardening
- Progress update (2026-02-10):
  - implemented:
    - maintainability refactor in-progress for lifecycle-critical orchestrators:
      - Runtime IPC command routing extracted from `runtime.py` into `runtime_ipc_commands.py`
      - Runtime IPC server plumbing extracted into `runtime_ipc_server.py`
      - Runtime shutdown/flush/segment lifecycle extracted into `runtime_shutdown.py`
      - Control proto `main.ts` split into focused modules (`types.ts`, `control_timing.ts`, `ui_html.ts`, `control_persistent_ipc.ts`, `control_operations.ts`, `control_ipc_handlers.ts`)
      - Control proto additional main-process concern extraction:
        - `control_env.ts` (runtime environment/path/flag resolution)
        - `control_ops_log_tailer.ts` (ops log init/tail/read cursor lifecycle)
        - `control_ops_log_writer.ts` (queued append-only runtime log writer)
        - `control_timing_loader.ts` (timing config candidate load/parse bootstrap)
        - `control_template_cache.ts` (template refresh cache + in-flight de-dup)
        - `control_background_loops.ts` (status/log/instance loop timer orchestration)
        - `control_quit.ts` (quit policy + prompt-driven shutdown decision flow)
        - `control_window.ts` (BrowserWindow creation + HTML load composition)
        - `control_operations_state.ts` (Operations lifecycle state store + publish)
        - `control_snapshot_refresher.ts` (status/monitor/instance/template refresh orchestration + initial snapshot bootstrap)
        - `control_window_publisher.ts` (all BrowserWindow publish/event fanout in one place)
      - Runtime widget IPC command routing extraction:
        - `runtime_ipc_widget_commands.py` (widget command branch decoupled from main IPC router)
      - Runtime plugin package command routing extraction:
        - `runtime_ipc_plugin_commands.py` (install/list/inspect/upgrade branch decoupled from main IPC router)
      - Runtime agent lifecycle/instance command routing extraction:
        - `runtime_ipc_agent_commands.py` (start/stop/restart and add/duplicate/remove/update branch decoupled from main IPC router)
      - Runtime queued-control and config-mutation extraction:
        - `runtime_control_actions.py` (queue/drain/process control actions + instance mutation/persist helpers decoupled from runtime loop coordinator)
      - Runtime lifecycle extraction:
        - `runtime_agent_lifecycle.py` (start/spawn/stop/restart operations decoupled from runtime loop coordinator)
      - Runtime agent-registry extraction:
        - `runtime_agent_registry.py` (state snapshots, template discovery, instance/cadence helper branch decoupled from runtime loop coordinator)
      - Runtime tick-loop extraction:
        - `runtime_tick.py` (control-action drain + flush/message routing + exit-reap branch decoupled from runtime loop coordinator)
  - remaining:
    - continue decomposition until orchestration files are coordinator-only and easier to audit under Item 1 hardening goals

### Item 2 — Implement true widget render pipeline through Operations
- Done when:
  - `get_widget_manifest` and `request_widget_render` return implemented data for at least one real agent instance.
  - Control renders validated output and handles refresh/action round-trips without transport errors.

### Item 3 — Finish agent package install/upgrade lifecycle
- Done when:
  - Operations can list/install/upgrade installed agent packages from repository artifacts with clear policy outcomes.
  - Control can trigger the flow via stable commands.
- Progress update (2026-02-10):
  - packaging utility decomposition + hardening completed:
    - `mimolo/utils/src/pack-agent.ts` reduced to CLI orchestration/dispatch
    - packaging mode flows extracted to `mimolo/utils/src/pack_agent_modes.ts`
    - core archive/manifest/hash/repo helpers live in `mimolo/utils/src/pack_agent_core.ts`
    - CLI formatting/default-source helpers live in `mimolo/utils/src/pack_agent_cli_helpers.ts`
    - shared error handling helpers added in `mimolo/utils/src/pack_agent_errors.ts`
  - exception policy hardening applied in packaging toolchain:
    - expected missing-path cases are errno-gated
    - unexpected filesystem failures are rethrown (not silently swallowed)
    - repository scan, source-list fallback, and source-list creation paths now follow explicit failure semantics
  - exception/throw hardening checklist (pack-agent utility module):
    - [x] Replace `processSourceList` expected validation throws with explicit conditional error accounting:
      - `mimolo/utils/src/pack_agent_modes.ts`:
        - missing source path
        - source path not a directory
        - missing `build-manifest.toml`
    - [x] Keep core contract/invariant throws only (schema + strict semver + repo-dir invariant) and document them in code comments where needed.
    - [x] Keep cleanup-only `try/finally` blocks (tmp directories/readline close), no catch-and-continue behavior.
    - [x] Keep boundary catch sites only (`main().catch`, `archive.finalize().catch(reject)`), with explicit diagnostics.
    - [x] Re-run strict QC (`npm --prefix mimolo/utils run build`, `poetry run ruff check .`, `poetry run mypy mimolo scripts/qc_exception_scan.py`, `poetry run pytest -q`) and record results in changelog on check-in.

### Item 4 — Complete archive-before-purge workflow
- Done when:
  - no artifact purge can occur without explicit user confirmation and archive option.
  - restore path can rehydrate data in-place by plugin-controlled logic.

### Item 5 — Hardening pass for `client_folder_activity` and `screen_tracker`
- Done when:
  - behavior matches spec contracts for bounded payloads/artifact references.
  - plugin-level tests cover key edge and failure paths.

### Item 6 — Promote control_proto patterns into commercial Control app
- Done when:
  - `mimolo-control` reaches functional parity for core runtime controls and stable IPC integration.

### Item 7 — Repository-wide path handling normalization audit (Python + TypeScript)
- Done when:
  - Python path handling is standardized on `pathlib`-safe semantics for composition and validation.
  - TypeScript/Electron path handling is standardized on `path` module semantics with no brittle separator assumptions.
  - Existing brittle path-separator/string path joins are cataloged, remediated, and regression-tested cross-platform.

### Item 8 — Plugin trust boundary and capability-gated isolation model
- Done when:
  - Plugin architecture is documented as contract-first and self-contained: plugin interoperability occurs only via the Operations communication contract.
  - Shared code with Operations/Control is optional SDK/base-class convenience only, not a compatibility requirement.
  - Operations owns access mediation: plugins request capabilities (for example folder access) and receive only approved, scoped paths/tokens.
  - Plugin runtime model is explicit about isolation baseline (separate process) and additional sandbox controls for untrusted plugins.

### Item 9 — Optional indicator intent-dot for request lifecycle diagnostics (deferred)
- Done when:
  - request lifecycle states (`queued`, `dispatching`, `timeout`, `completed`) are exposed as explicit telemetry events.
  - Control can render a distinct intent/queue signal that does not overlap with transport truth indicators.
- Deferred reason:
  - current priority is strict semantic honesty for transport indicators (`tx/rx` for actual transport events, plus separate background activity signal).
  - adding an intent dot before queue telemetry exists would create ambiguous UI semantics.

### Item 10 — Maintainability-first decomposition and concern-boundary compliance
- Done when:
  - active orchestrator files are coordinator-only and remain below the tactical cap (`<1000 LOC`) until further decomposition can continue toward smaller modules.
  - modules expose one primary concern with clear boundaries and minimal cross-cutting leakage.
  - duplicate logic is consolidated into shared helpers/modules where behavior is genuinely common.
  - exception usage remains boundary/cleanup/contract-only; no catch-and-continue for deterministic expected states.
  - each maintainability slice includes strict QC verification and synchronized docs/changelog updates.
- Scope note:
  - this item is now the top execution priority and supersedes behavior-feature sequencing when there is a tradeoff.

## 4) Canonical Planning Rules

- This file is the canonical active backlog/todo for implementation tracking.
- `developer_docs/8_Future_Roadmap_and_Summary.md` remains strategic direction.
- `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md` remains protocol reality map.
- Keep planned items explicit; do not delete them when incomplete.
