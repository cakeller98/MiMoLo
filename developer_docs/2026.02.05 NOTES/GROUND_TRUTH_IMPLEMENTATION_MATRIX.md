# Ground Truth Implementation Matrix (Canonical Active Backlog)

Date: 2026-02-09
Rule: code and tests are implementation truth when docs differ.

Verification snapshot:
- `poetry run pytest -q` => 131 passed
- `poetry run mypy mimolo` => clean
- `poetry run ruff check .` => clean
- `npm run build` in `mimolo/control_proto` => clean

## 1) Implemented (Current Ground Truth)

1. Operations runtime and Agent JLP lifecycle
- Status: Implemented
- Includes:
  - agent spawn/monitor/flush/shutdown
  - Agent JLP message handling (`handshake`, `summary`, `heartbeat`, `log`, `error`, `ack`)
  - lifecycle state snapshots for Control
- Evidence:
  - `mimolo/core/runtime.py`
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
  - plugin zip install UI is disabled by default and enabled only in explicit developer mode (`MIMOLO_CONTROL_DEV_MODE=1`, for example via `mml.sh --dev`)
- Evidence:
  - `mimolo/control_proto/src/main.ts`

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

1. Operations lifecycle ownership + orphan-process elimination (highest priority)
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
  - remaining:
    - explicit Control quit prompt (`leave running` vs `shutdown operations+agents`)
    - comprehensive lifecycle regression coverage for repeated start/stop/restart/quit cycles
    - residual orphan-process scenarios still under active investigation and hardening

2. Implement true widget render pipeline through Operations
- Done when:
  - `get_widget_manifest` and `request_widget_render` return implemented data for at least one real agent instance.
  - Control renders validated output and handles refresh/action round-trips without transport errors.

3. Finish agent package install/upgrade lifecycle
- Done when:
  - Operations can list/install/upgrade installed agent packages from repository artifacts with clear policy outcomes.
  - Control can trigger the flow via stable commands.

4. Complete archive-before-purge workflow
- Done when:
  - no artifact purge can occur without explicit user confirmation and archive option.
  - restore path can rehydrate data in-place by plugin-controlled logic.

5. Hardening pass for `client_folder_activity` and `screen_tracker`
- Done when:
  - behavior matches spec contracts for bounded payloads/artifact references.
  - plugin-level tests cover key edge and failure paths.

6. Promote control_proto patterns into commercial Control app
- Done when:
  - `mimolo-control` reaches functional parity for core runtime controls and stable IPC integration.

7. Repository-wide path handling normalization audit (Python + TypeScript)
- Done when:
  - Python path handling is standardized on `pathlib`-safe semantics for composition and validation.
  - TypeScript/Electron path handling is standardized on `path` module semantics with no brittle separator assumptions.
  - Existing brittle path-separator/string path joins are cataloged, remediated, and regression-tested cross-platform.

8. Plugin trust boundary and capability-gated isolation model
- Done when:
  - Plugin architecture is documented as contract-first and self-contained: plugin interoperability occurs only via the Operations communication contract.
  - Shared code with Operations/Control is optional SDK/base-class convenience only, not a compatibility requirement.
  - Operations owns access mediation: plugins request capabilities (for example folder access) and receive only approved, scoped paths/tokens.
  - Plugin runtime model is explicit about isolation baseline (separate process) and additional sandbox controls for untrusted plugins.

9. Optional indicator intent-dot for request lifecycle diagnostics (deferred)
- Done when:
  - request lifecycle states (`queued`, `dispatching`, `timeout`, `completed`) are exposed as explicit telemetry events.
  - Control can render a distinct intent/queue signal that does not overlap with transport truth indicators.
- Deferred reason:
  - current priority is strict semantic honesty for transport indicators (`tx/rx` for actual transport events, plus separate background activity signal).
  - adding an intent dot before queue telemetry exists would create ambiguous UI semantics.

## 4) Canonical Planning Rules

- This file is the canonical active backlog/todo for implementation tracking.
- `developer_docs/8_Future_Roadmap_and_Summary.md` remains strategic direction.
- `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md` remains protocol reality map.
- Keep planned items explicit; do not delete them when incomplete.
