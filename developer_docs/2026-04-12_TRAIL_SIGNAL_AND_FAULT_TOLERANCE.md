# Trail Signal And Fault Tolerance

Date: 2026-04-12

## Purpose

This document captures the minimum contract changes required so MiMoLo can
reliably answer:

- `is_working = true`
- `is_working = false`
- `is_working = unknown`

for trail-based Creo activity, while remaining low-chatter and fault-tolerant.

The core problem is not only detecting activity. It is preserving enough
evidence so that after an agent crash, restart, or missing close, the system can
still say:

- what the last known state was,
- when that state was last known,
- whether a session closed cleanly,
- or whether the evidence is ambiguous and the user must estimate.

## Core Principles

1. `heartbeat` means agent liveness only.
2. `summary` means canonical evidence was emitted.
3. Absence of `summary` does not mean absence of work.
4. Absence of `heartbeat` does not mean inactivity. It means liveness is
   unknown.
5. Session closure must be a positive recorded signal.
6. Missing closure after prior activity is a defect, not a clean session end.
7. Agents are zero-trust. They may only read or write inside orchestrator-
   granted per-instance roots.
8. Trail tracking is metadata-only. Do not read trail contents.

## Required Derived Outputs

For posthumous evaluation, the analyzer must be able to derive at least:

- `is_working = true | false | unknown`
- `last_known_state_at`
- `last_positive_signal_at`
- `session_integrity = clean | ambiguous | defective`
- `monitor_state = not_running | running | stale | crashed | recovered`

These are derived outputs. They are not raw protocol fields.

## Minimal Truth Model

### Positive Work Signal

A positive work signal is a canonical `summary` from an active source proving
real monitored activity.

For `trail_tracker`, that means a trail metadata change was observed and emitted
as summary evidence.

### Negative / Closing Signal

A negative or closing signal is a positive summary that says the tracked Creo
session has ended.

Examples:

- `process_exit_confirmed`
- `dead_period_timeout`

### Ambiguous / Defect Signal

An ambiguous or defect signal is any combination showing that prior activity
existed but the session did not close cleanly.

Examples:

- agent exited unexpectedly after positive activity and before closure
- no heartbeat for a long period after recent activity and no close summary
- agent restart later detects missing closure

## Orchestrator-Side Truth Requirements

The orchestrator log must preserve enough data to reconstruct liveness,
evidence, and defects after the fact.

### Must Preserve

For each agent instance:

- `heartbeat`
  - `timestamp`
  - `agent_label`
  - `agent_id`
  - minimal metrics
- `summary`
  - `timestamp`
  - `agent_label`
  - `agent_id`
  - `data.event`
  - full `data`
- `ack`
  - `timestamp`
  - `ack_command`
  - `agent_label`
- orchestrator diagnostics
  - unexpected `agent_exit`
  - shutdown sequencing results
  - restart/recovery actions

### Must Be Inferable

The orchestrator log must let the analyzer answer:

1. When was the agent last known alive?
2. When was the last positive work signal?
3. Was there a positive close signal?
4. If not, did the agent disappear unexpectedly?
5. Did the agent later recover and report a missing-close gap?

If the logs can answer those five questions, the analyzer can safely output
`true`, `false`, or `unknown`.

## Clean Session State Model

The session state model should be kept small and explicit.

### Monitor Lifecycle State

- `not_running`
- `starting`
- `running`
- `shutting_down`
- `crashed`
- `recovered`

### Work Session State

- `inactive`
- `active`
- `expiring`
- `closed`
- `unknown`

### Integrity State

- `clean`
- `ambiguous`
- `defective`

The important rule is that `not_running` is a monitor lifecycle state, not a
work-state conclusion.

## Required Command / Flush Contract

The current orchestrator-agent sequence is correct in intent:

- `STOP`
- `FLUSH`
- final `summary`
- `SHUTDOWN`

This should remain strict for clean shutdown.

### Required Meaning

- `STOP` means stop collecting new samples immediately.
- `FLUSH` means package and send final pending evidence now.
- `SHUTDOWN` means exit only after the flush-summary obligation is complete.

### Why This Matters

Shutdown is the one path where the system must be able to guarantee that
pending evidence is not lost.

The real fault-tolerance problem is not clean shutdown. It is unexpected crash
or disappearance before positive closure.

## Minimal Changes Required In Orchestrator

### 1. Keep Shutdown Strict

No change in intent:

- keep `STOP -> FLUSH -> summary -> SHUTDOWN`
- ensure the final summary is persisted before shutdown completes

### 2. Record Shutdown Sequencing More Explicitly

The orchestrator should log:

- stop requested time
- stop ack time
- flush requested time
- flush ack time
- final summary received time
- shutdown requested time
- shutdown ack time
- process exit time

This creates a durable audit trail for whether shutdown was clean.

### 3. Treat Missing Close As Defect, Not Idle

If an agent had recent positive activity and then:

- exits unexpectedly, or
- stops heartbeating for too long, or
- never emits a close summary

then the orchestrator/analyzer must mark that period as:

- `is_working = unknown`
- `session_integrity = defective`

not `false`.

### 4. Provide Per-Instance Sandboxed Roots

The orchestrator must provide explicit per-instance roots, not just one global
data directory.

Suggested environment variables:

- `MIMOLO_AGENT_INSTANCE_ROOT`
- `MIMOLO_AGENT_ARTIFACT_ROOT`
- `MIMOLO_AGENT_JOURNAL_ROOT`

Agents should only write inside those granted roots.

### 5. Preserve Enough Diagnostics For Posthumous Reconstruction

At minimum, keep:

- heartbeats
- summaries
- acks
- agent exit diagnostics
- restart/recovery diagnostics

These are sufficient to reconstruct ambiguity even when canonical evidence is
incomplete.

## Minimal Changes Required In Base Agent Contract

The base agent transport and command handling are already useful, but they do
not fully express the evidence semantics needed here.

### 1. Add First-Class Local Journal Support

Base agent should provide a helper for append-only per-instance JSONL journaling
inside the orchestrator-provided journal root.

This is needed for:

- restart recovery
- missing-close detection
- duplicate suppression
- post-crash agent self-diagnosis

### 2. Add Explicit Status / State Reporting Hook

`status` is effectively unused today.

Base agent should support a structured status snapshot that can say:

- monitor lifecycle state
- open session id if any
- last known activity timestamp
- current internal session state

This is not canonical work evidence, but it improves diagnosis and recovery.

### 3. Clarify Flush Obligation

Base agent behavior should document:

- normal flush may produce no new evidence if nothing is pending
- shutdown flush must produce the final pending summary if pending evidence
  exists
- agent-specific logic may suppress meaningless idle summaries during normal
  running

The base contract should explicitly distinguish:

- liveness
- evidence
- shutdown delivery

## Minimal Changes Required In All Agents

These rules should apply to every real agent, not only trail tracking.

### 1. Journal Their Own Critical State Locally

Every agent should write a small recovery journal in its granted journal root.

At minimum:

- start
- heartbeat checkpoints
- observed positive signal
- summary emitted
- session close decision
- restart recovery gap detected
- clean stop

### 2. Emit Positive Closure Signals

If an agent opens a session-like state, it must also emit a positive closure
record when that state ends.

Without this, the analyzer cannot distinguish inactivity from missing data.

### 3. Distill Their Own Errors

Agents should gracefully handle their own faults and emit:

- low-noise diagnostics
- recovery-aware local journal entries
- explicit anomaly markers when evidence integrity is compromised

The orchestrator should not need to infer everything from silence.

### 4. Respect Zero Trust

Agents must not read or write outside orchestrator-provided roots.

## Minimal Changes Required In Trail Tracker

### 1. Trail Tracker Must Remain Metadata-Only

Track only:

- trail file name
- modified timestamp
- size
- size delta if useful

Do not read trail contents.

### 2. Trail Tracker Must Keep A Local Recovery Journal

This is mandatory.

Without a local journal, the agent cannot know on restart whether:

- a session was open,
- a close was missing,
- a summary should have already been emitted,
- or the prior segment is defective.

### 3. Trail Tracker Must Distinguish These Local Journal Events

At minimum:

- `agent_started`
- `agent_heartbeat_checkpoint`
- `trail_activity_observed`
- `session_opened`
- `session_active_checkpoint`
- `no_trail_activity`
- `session_expiring`
- `session_closed_dead_period`
- `session_closed_process_exit`
- `summary_emitted`
- `recovery_gap_detected`
- `agent_stopped_cleanly`

### 4. Trail Tracker Must Emit Canonical Summaries Sparingly

Canonical summaries should be emitted for:

- session open
- periodic active checkpoint
- session close
- recovery gap / missing-close warning

Canonical summaries should not be emitted on every idle flush.

### 5. Trail Tracker Should Detect Creo Process Presence If Cheap

If lightweight process detection is reliable, use it to improve certainty:

- `creo_not_detected_no_trail_activity`
- `creo_detected_no_trail_activity`
- `process_exit_confirmed`

This improves close semantics without overstating authority.

### 6. Trail Tracker Must Preserve Ambiguity

If trail activity was observed but no valid closure occurred before crash or
restart, the next recovery cycle must emit a warning summary marking the prior
interval as defective or ambiguous.

Example meaning:

- last known activity existed
- close signal missing
- user must estimate this interval manually

## Required Canonical Summary Semantics For Trail Tracker

The summary payload must stay small and factual.

The minimum useful fields are:

- `schema`
- `event`
- `session_id`
- `last_activity_at`
- `file`
  - `name`
  - `modified_at`
  - `size_bytes`
  - optional `size_delta_bytes`
- `closure_reason` when relevant
- `integrity`

This is enough for:

- work detection
- posthumous reconstruction
- defect signaling

without bloating the evidence ledger.

## Posthumous Evaluation Rules

The analyzer should apply these rules.

### `is_working = true`

When there is a recent positive summary from trail tracker.

### `is_working = false`

Only when there is a positive close signal or positive inactive condition.

Lack of data alone is not enough.

### `is_working = unknown`

When there was prior activity but:

- no close signal,
- heartbeat/liveness became stale,
- or recovery later detected a missing-close gap.

## Bottom Line

The system only becomes trustworthy if it can say both:

- "there is positive evidence of work"
- and "there is positive evidence that the session ended cleanly"

If the second part is missing, the correct conclusion is not `false`.
It is `unknown`, and the defect must be surfaced clearly to the user.
