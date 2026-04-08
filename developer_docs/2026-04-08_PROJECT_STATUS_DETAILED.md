# MiMoLo Project Status: Detailed Review And 24-Hour Push Plan

Date: 2026-04-08

## Scope And Method

This review was based on the current repository state in:

- `mimolo/`
- `developer_docs/`
- launcher/config files
- tests

Code was treated as ground truth when docs disagreed, which matches the repo's own documentation discipline.

Local validation notes:

- `ruff check .` passed in the current environment.
- `pytest -q` did not run to behavioral completion because the active Python environment is currently missing `tomlkit`, so test collection fails early.
- I therefore treated the code and the test suite contents as the review baseline, but not the local runtime environment as a trustworthy pass/fail signal.

## Short Answer

MiMoLo is not close to "finished product" status, but it is close enough that rewriting from scratch would be a net loss.

My recommendation:

- Do not rewrite the system architecture.
- Do perform a spec reset around the 3 real evidence goals.
- Treat everything outside those goals as deferred.

## Ground-Truth State

### What is real and valuable already

1. Runtime and agent lifecycle

- The orchestrator/runtime is real and modular enough to continue with.
- Agent spawning, messaging, shutdown sequencing, IPC command handling, template discovery, and plugin install/archive inspection all exist in code.
- Relevant files:
  - `mimolo/core/runtime.py`
  - `mimolo/core/runtime_tick.py`
  - `mimolo/core/runtime_shutdown.py`
  - `mimolo/core/runtime_ipc_commands.py`
  - `mimolo/core/runtime_ipc_widget_commands.py`
  - `mimolo/core/agent_process.py`
  - `mimolo/core/plugin_store.py`

2. Folder activity tracking

- `client_folder_activity` is already a meaningful implementation.
- It supports:
  - multiple watch paths
  - include/exclude globs
  - watchfiles backend with polling fallback
  - bounded created/modified/deleted samples
  - health/status transition logging
  - widget-facing recent rows
  - activity signal emission
- Relevant file:
  - `mimolo/agents/client_folder_activity/client_folder_activity.py`

3. Screenshot tracking

- `screen_tracker` is also real enough to build on.
- It supports:
  - full-screen and app-window modes
  - artifact creation for full images and thumbnails
  - file hashing and reference emission
  - placeholder output when target windows are unavailable
  - widget rendering of the latest image
- Relevant files:
  - `mimolo/agents/screen_tracker/screen_tracker.py`
  - `mimolo/core/runtime_widget_support.py`
  - `mimolo/core/runtime_ipc_widget_commands.py`

4. Control prototype

- `mimolo/control_proto` is a legitimate prototype control plane, not just scaffolding.
- It appears good enough for in-house runtime management while the broader product remains unfinished.

### What is not real enough yet

1. Trail tracking

- `trail_tracker` is only specified, not implemented.
- Evidence:
  - spec exists: `developer_docs/agent_dev/trail_tracker/trail_tracker_SPEC.md`
  - no matching implementation exists under `mimolo/agents/`

2. Activity session logic

- The repo talks a lot about cooldown/segment logic.
- The core problem is that the real agent summaries are not currently driving that logic.

Evidence:

- `client_folder_activity` emits an `activity_signal.keep_alive` decision.
- BaseAgent automatically inserts `activity_signal` into summaries.
- Runtime summary handling writes the event and caches `agent_last_summary`, but does not apply `activity_signal` to `CooldownTimer`.
- The runtime tick checks cooldown expiration, but there is no corresponding real summary-driven open/reset path.

Relevant files:

- `mimolo/agents/base_agent.py`
- `mimolo/agents/client_folder_activity/client_folder_activity.py`
- `mimolo/core/runtime_agent_events.py`
- `mimolo/core/runtime_tick.py`
- `mimolo/core/cooldown.py`

This is the single most important architectural gap for your stated goal.

3. Artifact history/index model

- The screenshot agent creates `index/` and `archives/` folders but does not yet write the durable artifact history/index that the docs promise.
- The archive-before-purge model is still mostly design intent, not a completed workflow.

Evidence:

- `screen_tracker` creates storage roots for `index` and `archives`.
- There is no real index writer or restore/archive implementation in the agent.
- The artifact contract explicitly marks those pieces as planned.

Relevant files:

- `mimolo/agents/screen_tracker/screen_tracker.py`
- `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`

4. Instance identity consistency

- The docs describe per-plugin, per-instance storage using stable instance ids.
- Current runtime/agent behavior is not fully aligned with that.

Evidence:

- Agents receive `MIMOLO_AGENT_LABEL` and `MIMOLO_AGENT_ID`.
- `MIMOLO_AGENT_ID` is generated per process launch, not a stable configured instance id.
- `screen_tracker` stores under `.../screen_tracker/<agent_label>/...`, which means storage is keyed by label, not by a stable instance identifier.

Relevant files:

- `mimolo/core/agent_process.py`
- `mimolo/agents/screen_tracker/screen_tracker.py`
- `developer_docs/agent_dev/DATA_STORAGE_CONVENTIONS.md`
- `developer_docs/agent_dev/ARTIFACT_STORAGE_AND_RETENTION_CONTRACT.md`

For an in-house tool this is fixable, but it should be fixed before you treat the evidence layout as durable.

5. Operator-facing defaults and docs

- The top-level docs are stale.
- The default runtime config is not clean for first-use.

Evidence:

- `GETTING_STARTED.md` still references old plugin paths and old test counts.
- `developer_docs/control_dev/CONTROL_SPECIFICATION.md` is mostly historical intent, not current behavior.
- `mimolo.toml` currently enables scaffold/dev agents and contains a hardcoded absolute macOS watch path.
- The launcher seeds the portable runtime config from that root config by default.

Relevant files:

- `GETTING_STARTED.md`
- `mimolo.toml`
- `scripts/mml/common.sh`

This is why the repo feels less usable than the codebase actually is.

## Readiness Against Your 3 Real Tracking Goals

### 1. Working screenshots per time-frequency

Status: partially implemented, close

What exists:

- periodic screenshot capture
- artifact emission
- thumbnail support
- latest-image widget rendering

What is missing for your real use:

- stable artifact index/history
- better linkage to activity/session state
- true use of the configured scaling intent
- cross-platform capture strategy, if needed

Assessment:

- likely 65% complete for your in-house use

### 2. Creo trail file tracking

Status: not implemented

What exists:

- only the spec

What is missing:

- actual agent
- debounced write monitoring
- active/inactive state emission
- optional screenshot pairing
- artifact and summary schema implementation

Assessment:

- roughly 10% complete, almost entirely at the spec level

### 3. Artifact/file tracking history in selected folders

Status: meaningfully implemented, but not yet "finished"

What exists:

- file create/modify/delete monitoring
- bounded evidence payloads
- watch-path health reporting
- relative path sampling
- recent rows for UI

What is missing:

- stronger history/index presentation layer
- tighter config defaults for actual monitored folders
- a finalized session/activity interpretation path

Assessment:

- roughly 70% complete for your in-house use

## The Most Important Technical Finding

The repo already knows how to collect evidence.

What it does not yet reliably know how to do is answer:

"When was I actively working, and when was I merely idle between meaningful signals?"

That is the heart of your actual use case.

Right now:

- file changes can be detected
- screenshots can be captured
- summaries can be emitted

But the runtime does not yet convert those summary-level activity signals into a trustworthy working-session model.

Until that is fixed, the system is a breadcrumb logger, not yet a convincing work-activity tracker.

## Rewrite Vs Continue

### Full rewrite

I do not recommend it.

Reasons:

- you would be throwing away real working infrastructure
- the missing pieces are feature-completion gaps, not proof that the architecture is fundamentally wrong
- the current design is already close to the right shape for isolated evidence agents plus an operations/control layer

### What should be rewritten or reset

I do recommend a limited rewrite of intent and defaults:

1. Rewrite the active spec into a single compact breadcrumb contract.
2. Rewrite the default config for your actual in-house workflow.
3. Rewrite the top-level "how to use this" docs so they match reality.

That is a spec/defaults reset, not a platform rewrite.

## 24-Hour Push Plan

This is feasible if you define "usable" as:

- can run locally
- captures the 3 evidence streams
- persists raw evidence cleanly
- has a minimal way to inspect the results

This is not feasible in 24 hours if you also demand:

- polished Control UX
- full archive/restore lifecycle
- signing/trust hardening
- commercial app parity
- broad plugin ecosystem polish

### Suggested execution sequence

1. Freeze the target spec for the 3 required evidence streams.
   - Time: 1 hour
   - Deliverable:
     - one concise doc defining:
       - screenshot cadence evidence
       - trail-write evidence
       - selected-folder artifact/file history evidence
       - one shared activity/debounce rule

2. Make runtime activity real.
   - Time: 3 to 4 hours
   - Change:
     - on each summary, inspect `data.activity_signal.keep_alive`
     - `True` should open/reset cooldown
     - `False` should be recorded as non-resetting evidence
   - Deliverable:
     - actual active/idle session behavior tied to agent evidence

3. Implement `trail_tracker`.
   - Time: 4 to 6 hours
   - Reuse:
     - folder watch/debounce structure from `client_folder_activity`
     - screenshot/artifact reference patterns from `screen_tracker`
   - Deliverable:
     - watch trail writes
     - debounce writes into activity windows
     - emit active/inactive summaries
     - optionally attach low-res screenshot references

4. Add minimal artifact index/history output.
   - Time: 2 to 3 hours
   - Scope:
     - append-only JSONL index per agent instance is enough
     - do not build full archive/restore yet
   - Deliverable:
     - artifact creation history for screenshots
     - trail/file evidence lookup path

5. Normalize instance identity and storage keys.
   - Time: 1 to 2 hours
   - Change:
     - introduce stable configured instance id
     - pass it explicitly to agents
     - use it for storage roots

6. Clean the launch path.
   - Time: 1 hour
   - Change:
     - replace scaffold-heavy defaults in `mimolo.toml`
     - seed only the 3 agents you actually want
     - remove hardcoded personal watch paths from the default config

7. Add a minimal evidence viewer or summary script.
   - Time: 2 hours
   - Scope:
     - could be a simple CLI report, not a polished UI
   - Deliverable:
     - one command to summarize "today's evidence" by time window and source

### What to defer

Defer these until after the system is already useful:

- full archive/restore/purge UX
- trust/signing enforcement
- commercial `mimolo-control` parity
- generalized plugin packaging polish beyond what is needed for local use
- deeper widget/render contract cleanup

## Final Recommendation

The current codebase is worth continuing, but only if you stop treating it like a generic future product and start treating it like a focused in-house evidence tool.

If you narrow scope to:

- screenshots
- trail writes
- selected-folder file history
- summary-level activity debounce

then MiMoLo looks finishable.

If you keep trying to mature the whole ecosystem at once, it will continue to feel perpetually "almost there."
