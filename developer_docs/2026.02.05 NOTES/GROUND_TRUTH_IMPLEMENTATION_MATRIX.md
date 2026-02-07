# Ground Truth Implementation Matrix (2026-02-05)

Date: 2026-02-07
Basis: current code + tests (`poetry run pytest -q` => 80 passed)
Interpretation rule: if code and notes conflict, code is ground truth.

## Current operational baseline
- Operations/orchestrator runtime is implemented and functioning in current form.
- Agent communication over Agent JLP (stdin/stdout JSON lines) is implemented.
- Agent lifecycle and shutdown sequence handling are implemented.
- Logging pipeline via Agent JLP log packets is implemented.
- Dashboard/Controller is not implemented beyond prototype stubs.

## Implemented (ground truth)
1. Agent runtime orchestration and message handling
- Status: Implemented
- Evidence:
  - `mimolo/core/runtime.py`
  - `mimolo/core/agent_process.py`
  - `mimolo/core/protocol.py`

2. Agent process spawning with context env vars
- Status: Implemented
- Notes:
  - Injects `MIMOLO_AGENT_LABEL`, `MIMOLO_AGENT_ID`, `MIMOLO_DATA_DIR`
- Evidence:
  - `mimolo/core/agent_process.py`
  - `mimolo/common/paths.py`

3. Agent flush/summary flow and shutdown sequence tracking
- Status: Implemented
- Evidence:
  - `mimolo/core/runtime.py`

4. JLP logging support and verbosity filtering
- Status: Implemented
- Evidence:
  - `mimolo/core/runtime.py`
  - `mimolo/core/agent_logging.py`
  - `tests/test_logging_integration.py`

5. Packaging utility for agent zips + manifest/hash generation
- Status: Implemented (tooling side)
- Evidence:
  - `mimolo/utils/src/pack-agent.ts`
  - `mimolo/agents/repository/README.md`

6. AF_UNIX IPC primitives
- Status: Implemented (library-level)
- Evidence:
  - `mimolo/core/ipc.py`
  - `tests/test_ipc_support.py`

## Planned or partial (preserve)
1. Dashboard/Controller implementation
- Status: Planned/partial
- Notes:
  - TS socket harness exists, Electron app is placeholder only.
- Evidence:
  - `mimolo/dashboard/src/index.ts`
  - `mimolo-dash/src/main.ts`

2. Orchestrator IPC command server contract (list/install/upgrade)
- Status: Planned/not implemented
- Notes:
  - IPC channel class exists; command server behavior is not wired in runtime/CLI.
- Evidence:
  - `mimolo/core/ipc.py`
  - `mimolo/core/runtime.py`

3. Install-folder scanning and installed-plugin registry lifecycle
- Status: Planned/not implemented in orchestrator runtime
- Notes:
  - Packaging outputs exist; install/upgrade/list operational path is not present.
- Evidence:
  - `mimolo/utils/src/pack-agent.ts`
  - `mimolo/core/runtime.py`

4. Integrity hardening with signed payload hash copy (HMAC)
- Status: Planned/not implemented
- Notes:
  - Hash generation exists, no orchestrator-side signed storage/verification path.
- Evidence:
  - `mimolo/utils/src/pack-agent.ts`

5. Interactive agent menu control handling
- Status: Partial
- Notes:
  - Rendering exists; input handling marked TODO.
- Evidence:
  - `mimolo/core/agent_menu.py`

## Reference-note discrepancies to treat as tactical drift
- Older docs still describe plugin layout and commands no longer aligned with current code.
- Dashboard specs include aspirational features not yet reflected in runtime.
- Historical status docs include agreed plans that remain valid but unimplemented.

## Actionable doc policy from this point
- Keep this matrix current and update status fields on implementation.
- Keep planned items explicitly listed instead of deleting them.
- Move superseded notes to archive with a small breadcrumb to canonical docs.
