# Staged Runtime And Trail Tracker To-Do

Date: 2026-04-12

## Working Agreement

This plan is intentionally split into small operational checkpoints.

After each step:

- the repo should remain runnable,
- the expected behavior should be testable by hand,
- Codex stops,
- Codex provides a commit message relative to the last commit on the current
  branch,
- user tests,
- then either:
  - user commits and we move to the next step, or
  - user provides feedback and we fix issues before any commit.

Commit-message rule:

- If files are staged, the commit message must describe the staged delta versus
  the last commit.
- If nothing is staged, the commit message must describe the current repo delta
  versus the last commit.

## Priority Order

1. Fix orchestrator flush / shutdown correctness first.
2. Add per-instance sandbox roots.
3. Extend the generic base agent contract.
4. Only then bring `trail_tracker` into alignment.

## Current Checkpoint Status

### Completed / Mostly Completed

- Step 1 has been substantially advanced:
  - structured per-agent shutdown diagnostics were added
  - Windows-safe runtime console printing was hardened
  - launcher/runtime paths were moved out of `%TEMP%` into AppData roots
  - slowpoke IPC start/stop timing was improved in Control
  - monitor settings now apply live without backend restart
  - detached per-agent tail windows are now tracked and closed with agent lifecycle
  - Control now preserves explicit Operations phase transitions (`starting`,
    `stopping`, waiting-for-IPC / waiting-for-exit)
- Additional blocking runtime work was completed because it was required to make
  Step 1 testable on Windows:
  - Control stale-status start gating was hardened
  - launcher reuse of an already-running Operations instance was hardened
  - folder watcher startup/shutdown backlog behavior was reduced

### Not Yet Complete

- Step 1 is not fully closed until repeated restart/stop behavior is consistently
  clean under the current Windows slowpoke setup.
- Step 2 has not started yet.
- Step 3 has not started yet.
- `trail_tracker` widget/render support is still not implemented.

### Immediate Next Task After Current Commit

- Implement `trail_tracker` widget manifest/render support so the Control UI can
  show:
  - waiting / idle / active session state
  - latest trail file seen
  - last activity timestamp
  - clear indication that the agent is alive even when no trail activity has
    occurred yet

## Step 1: Fix Shutdown / Flush Contract

### Goal

Make clean shutdown reliable and diagnosable.

The orchestrator must preserve enough control-plane truth to know whether the
final flush-summary was actually delivered before agent exit.

### Scope

Touch only generic runtime/orchestrator shutdown and diagnostics paths.

Primary files likely involved:

- `mimolo/core/runtime_shutdown.py`
- `mimolo/core/runtime_tick.py`
- `mimolo/core/runtime_agent_events.py`
- tests covering shutdown / sequencing / diagnostics

### Required Changes

- Keep shutdown strict:
  - `STOP -> FLUSH -> summary -> SHUTDOWN -> exit`
- Record structured shutdown sequencing diagnostics:
  - stop sent
  - stop ack
  - flush sent
  - flush ack
  - final summary received
  - shutdown sent
  - shutdown ack
  - process exit
- Make unexpected agent exit after recent activity clearly reconstructable as a
  defect / ambiguity source.
- Do not loosen final-summary expectations for clean shutdown.

### Operational Expectation After Step

- normal startup still works
- normal agent ticking still works
- clean shutdown still works
- diagnostics now show whether shutdown was clean or defective

### Current Status

- Partially complete and currently usable.
- Diagnostics are in place.
- Control now surfaces more explicit startup / shutdown phases.
- Remaining concern:
  - restart/stop behavior on Windows slowpoke mode still needs continued manual
    confirmation to fully close this step.

### Manual Test Expectation

- start MiMoLo
- let one or more agents run
- trigger clean shutdown
- confirm final summary arrives before exit
- inspect diagnostics for explicit sequencing data

### If This Works

Next task:

- Step 2: add orchestrator-provided per-instance sandbox roots for agents

## Step 2: Add Per-Instance Agent Roots

### Goal

Move the generic agent runtime toward zero-trust storage boundaries.

### Scope

Touch only process spawn / environment grant paths and any supporting helpers.

Primary files likely involved:

- `mimolo/core/agent_process.py`
- path helper modules if needed
- tests covering spawned agent env / instance roots

### Required Changes

- Provide deterministic per-instance roots via environment:
  - `MIMOLO_AGENT_INSTANCE_ROOT`
  - `MIMOLO_AGENT_ARTIFACT_ROOT`
  - `MIMOLO_AGENT_JOURNAL_ROOT`
- Ensure directories are created safely by orchestrator before spawn.
- Preserve compatibility with existing `MIMOLO_DATA_DIR` during transition.

### Operational Expectation After Step

- existing agents still launch
- existing agents remain runnable
- new instance-specific roots are visible in agent environment

### Manual Test Expectation

- launch MiMoLo
- inspect agent environment using debug/logging or a temporary test hook
- confirm instance roots are unique, stable, and inside orchestrator-controlled
  storage

### If This Works

Next task:

- Step 3: extend the generic base agent contract with journal and flush/status
  semantics

## Step 3: Extend Base Agent Contract

### Goal

Give all agents the generic capabilities needed for recovery-aware low-chatter
 evidence emission.

### Scope

Touch only the generic base agent behavior and shared tests.

Primary files likely involved:

- `mimolo/agents/base_agent.py`
- protocol-related tests
- any generic agent test scaffolds

### Required Changes

- Add base helper for append-only local journal events inside
  `MIMOLO_AGENT_JOURNAL_ROOT`.
- Implement a real `status` response path instead of a no-op.
- Clarify `flush` behavior:
  - normal running may have no pending evidence
  - shutdown flush must still guarantee final pending evidence delivery
- If needed, enrich `ACK(flush)` so the orchestrator can tell whether a summary
  was emitted.

### Operational Expectation After Step

- existing agents still run under the base class
- existing heartbeats still work
- status requests return useful data
- journal helper is available without forcing every agent to fully adopt it yet

### Manual Test Expectation

- launch MiMoLo
- inspect heartbeats and status behavior
- trigger flush on an idle/simple agent
- confirm semantics are explicit and non-ambiguous

### If This Works

Next task:

- Step 4: adapt orchestrator runtime to consume the improved base-agent flush
  semantics during normal operation

## Step 4: Align Runtime With Improved Base-Agent Semantics

### Goal

Ensure periodic orchestrator flushes and posthumous reconstruction work with the
new agent contract.

### Scope

Touch only generic runtime behavior, not trail-specific logic yet.

Primary files likely involved:

- `mimolo/core/runtime_tick.py`
- `mimolo/core/runtime_agent_events.py`
- `mimolo/core/runtime_shutdown.py`
- tests for runtime message handling

### Required Changes

- Consume the improved flush/status/journal-related semantics.
- Preserve low chatter during normal operation.
- Preserve strict final-flush behavior during clean shutdown.
- Improve defect detection for:
  - agent exit without close
  - stale heartbeat after prior activity
  - missing close / missing final summary

### Operational Expectation After Step

- runtime remains operational
- periodic flushes do not create false confidence
- crash/exit paths preserve enough information for later ambiguity marking

### Manual Test Expectation

- clean run/shutdown
- forced agent failure during run
- confirm diagnostics distinguish clean closure vs defect

### If This Works

Next task:

- Step 5: update `trail_tracker` spec and implementation against the new generic
  contract

## Step 5: Update Trail Tracker Spec

### Goal

Bring the spec in line with the actual intended behavior.

### Scope

Documentation only.

Primary files likely involved:

- `developer_docs/agent_dev/trail_tracker/trail_tracker_SPEC.md`
- related design docs if needed

### Required Changes

- remove screenshot responsibilities from `trail_tracker`
- state explicitly that trail tracking is metadata-only
- add per-instance journal / recovery requirements
- add positive closure and missing-close defect semantics
- align payload expectations with orchestrator/runtime contract

### Operational Expectation After Step

- repo behavior unchanged
- docs now match intended architecture

### If This Works

Next task:

- Step 6: implement `trail_tracker` against the corrected contract

## Step 6: Fix Trail Tracker Implementation

### Goal

Make `trail_tracker` conform to the corrected spec and generic runtime
contract.

### Scope

Trail tracker only, plus any integration config/widget/test updates required to
make it runnable.

Primary files likely involved:

- `mimolo/agents/trail_tracker/trail_tracker.py`
- `mimolo/core/runtime_widget_support.py`
- `mimolo/core/runtime_ipc_widget_commands.py`
- `mimolo.toml`
- `mimolo/agents/sources.json`
- trail tracker tests

### Required Changes

- use orchestrator-provided per-instance journal/artifact roots
- keep a local recovery journal
- emit sparse canonical summaries only when meaningful
- emit positive close signals
- emit recovery-gap warning signals after restart when closure is missing
- wire widget rendering
- add default config entry

### Operational Expectation After Step

- `trail_tracker` is runnable and testable from MiMoLo
- widget render works
- config entry exists
- recovery and ambiguity semantics are observable

### Manual Test Expectation

- run with real or simulated trail folder
- observe session open / continue / close behavior
- simulate restart/crash and verify recovery-gap handling

### If This Works

Next task:

- Step 7: verify end-to-end posthumous reconstruction behavior

## Step 7: Verify Posthumous Reconstruction

### Goal

Prove that orchestrator logs contain enough truth to derive:

- working
- not working
- unknown

for trail-driven sessions.

### Scope

Tests, fixtures, and manual verification.

### Required Changes

- add focused reconstruction fixtures
- validate clean session
- validate clean idle state
- validate crash before close
- validate restart with recovery-gap summary

### Operational Expectation After Step

- system is still runnable
- we have evidence the contract supports posthumous truth evaluation

## Immediate Next Step

Start with Step 1 only.
