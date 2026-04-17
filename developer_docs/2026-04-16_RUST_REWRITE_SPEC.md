# 2026-04-16 MiMoLo Rust Rewrite Specification

## Status

- Draft rewrite specification
- Intended as the primary handoff document for a full Rust-native MiMoLo implementation
- Supersedes ad hoc launcher / Electron / slowpoke direction as the target architecture

## Normative Scope

This document is intended to be normative for the rewrite target architecture.

It defines:

- product intent
- target behavior
- subsystem boundaries
- reliability expectations
- UI / CLI direction
- logging / evidence expectations

It does not define the rewrite packet composition by itself.

The handoff packet and exclusion rules belong in separate documents:

- `REWRITE_PACKET_MANIFEST.md`
- `LEGACY_ARTIFACTS_TO_IGNORE.md`

## Legacy Artifacts Out Of Scope

The following legacy implementation surfaces must not be treated as target architecture:

- PowerShell launchers
- shell launchers
- wrapper installers
- Electron / Node dashboard code
- ad hoc reporting scripts
- temporary compatibility shims

They may be consulted only as behavioral reference.

## Purpose

MiMoLo should become a Rust-first desktop system for:

- collecting activity evidence from lightweight local agents
- aggregating that evidence into durable local logs
- exposing a compact, dense operator-facing dashboard
- supporting later analyst-style reporting and derived summaries

This rewrite is intended to eliminate the current failure-prone mix of:

- PowerShell launcher semantics
- Python orchestration/runtime coupling
- Electron / Node / npm / npx dependency chains
- fragile Windows slowpoke IPC fallback as a primary control path

The Rust rewrite must preserve MiMoLo’s core intent while substantially improving:

- reliability
- startup / shutdown behavior
- cross-account usability on Windows
- packaging
- observability of failures
- long-term maintainability

---

## Product Definition

MiMoLo is a local-first workstation activity observability tool.

It is not a spyware product, not a cloud-first time tracker, and not a generalized enterprise device-management platform.

It exists to answer questions like:

- what was active today?
- which agents observed that activity?
- what files or application-specific signals support that conclusion?
- when was the system active vs quiet?
- what evidence was weak, noisy, or misleading?

The system must prefer preserved evidence over premature interpretation.

---

## Rewrite Goals

### Required

- One stable Rust codebase is the primary implementation surface.
- One stable Rust CLI / launcher becomes the public command face.
- One native Rust desktop app replaces Electron.
- Windows must be a first-class target.
- IPC must be reliable and explicitly observable on failure.
- Logs must remain local-first, inspectable, and durable.
- The system must preserve timestamp correctness:
  - timestamps stored as timezone-aware UTC
  - daily file boundaries based on local day
  - user-facing display rendered in local time
- Agents must remain lightweight and low-overhead.
- The analyst layer must remain possible without requiring agent explosion.

### Strongly Desired

- Slint-based desktop UI
- native Windows IPC
- native Unix domain sockets on platforms that support them
- first-party Rust agents for built-in functionality
- a stable external-agent protocol for optional future non-Rust plugins

### Explicitly Not Required for First Rust Release

- network sync
- multi-user shared server mode
- cloud services
- remote fleet management
- browser UI
- polished enterprise packaging

---

## Non-Goals

The Rust rewrite is not intended to:

- replicate the existing PowerShell / Python / Electron stack one-to-one
- preserve every internal implementation detail
- keep slowpoke as a polished long-term transport
- normalize all evidence at collection time
- overfit analyst logic into agents prematurely

---

## High-Level Architecture

The Rust system should be composed of four major layers:

1. Core Runtime
2. Agents
3. Analyst / Derived Views
4. Native UI + CLI

### 1. Core Runtime

Responsibilities:

- load configuration
- start and supervise agents
- accept control requests over IPC
- collect agent messages
- validate / normalize message envelopes
- write canonical event logs and diagnostics
- manage lifecycle and graceful shutdown

Proposed binary:

- `mimolo-ops`

### 2. Agents

Responsibilities:

- observe narrow local activity domains
- aggregate locally
- emit structured summaries and health
- remain low-overhead

Built-in agents should be implemented in Rust where practical.

### 3. Analyst / Derived Views

Responsibilities:

- consume canonical logs
- derive day charts, summaries, and per-file ledgers
- apply family-specific interpretation rules
- avoid corrupting source evidence

This may begin as a library plus CLI commands within the same Rust workspace.

### 4. Native UI + CLI

Responsibilities:

- dashboard / control surface
- command family
- agent and runtime visibility
- analyst views
- help / discovery / operator controls

Proposed GUI toolkit:

- Slint

Proposed public command family:

- `mimolo`
- `mimolo dash`
- `mimolo ops start|stop|status`
- `mimolo report`
- `mimolo activity`
- `mimolo blips`
- `mimolo help`

Short wrappers may still exist, but the Rust CLI should be the canonical interface.

---

## Target Workspace Shape

Suggested Rust workspace layout:

- `crates/mimolo-core`
- `crates/mimolo-protocol`
- `crates/mimolo-ipc`
- `crates/mimolo-ops`
- `crates/mimolo-cli`
- `crates/mimolo-ui`
- `crates/mimolo-analyst`
- `crates/mimolo-agent-folder`
- `crates/mimolo-agent-trail`
- `crates/mimolo-agent-screen`
- `crates/mimolo-storage`
- `crates/mimolo-config`

This does not require one final executable per crate. It is a code-organization target.

---

## Core Design Principles

### Preserve Evidence First

Source evidence should be logged in a way that allows later reinterpretation.

Implications:

- avoid early truncation of changed-file evidence when feasible
- avoid hardcoding path-specific junk filtering in viewers when it belongs in collection config
- keep derived interpretations separate from raw canonical logs

### Low Overhead

Agents must remain lightweight.

Target posture:

- near-zero steady-state CPU when idle
- bounded periodic work
- no aggressive polling without reason
- no noisy per-event disk writes where batching works

### Explicit Failure Visibility

Critical system failures must become durable operator-visible events.

Examples:

- IPC server failure
- agent launch failure
- sink write failure
- config load failure
- plugin protocol mismatch

Console-only failure reporting is not sufficient.

### Windows Is Not Secondary

The design must not assume Unix semantics as the only good path.

Windows-native IPC and process control must be first-class, not a fallback embarrassment.

### Native, Dense, Practical UI

The UI should behave like a serious workstation tool, not a browser shell.

The design target is compact information density, not marketing polish.

---

## IPC Specification

## Requirements

- no primary dependence on file-polled slowpoke IPC
- reliable request/response control channel
- explicit request correlation
- explicit startup / liveness / shutdown semantics
- durable failure alert when control plane is unhealthy

## Transport

### Windows

Primary target:

- named pipes

### Unix-like systems

Primary target:

- Unix domain sockets

## Control Plane Semantics

The control plane must support at minimum:

- `ping`
- `status`
- `stop`
- `list_agents`
- `agent_status`
- `get_monitor_settings`
- future dashboard data requests

Every request must carry:

- request id
- command
- timestamp

Every response must carry:

- matching request id
- success / failure
- payload or explicit error

## Failure Contract

If IPC server startup fails:

- emit durable orchestrator event
- emit diagnostics event
- surface visible dashboard / CLI error if connected
- mark runtime control plane degraded

If IPC later dies while Ops remains alive:

- emit durable orchestrator event
- dashboard must show disconnected / degraded state
- CLI status should explain control-plane failure, not just “timed out”

---

## Agent Model

## Agent Philosophy

Agents collect narrow evidence.
They should not own all final interpretation.

Default rule:

- generic evidence collection in agents
- richer classification in analyst layer
- app-native custom emitters only where filesystem evidence is insufficient

## Agent Lifecycle

Every first-party agent must support:

- start
- register / handshake
- periodic heartbeat
- summary flush
- graceful stop
- graceful shutdown
- final summary on shutdown where relevant

## Agent Runtime Contract

Each agent must expose:

- agent id
- agent label
- agent kind
- version
- capabilities
- health
- current cadence / configuration summary

## Message Types

The Rust rewrite should preserve the conceptual message families already proven useful:

- `handshake`
- `heartbeat`
- `summary`
- `status`
- `error`
- `ack`
- `log`

The exact serialization can be Rust-native internally, but the conceptual model should remain stable.

## Activity Signal

Summary payloads should preserve the current activity-signal contract:

- `mode`
- `keep_alive`
- `reason`

This has proven useful for:

- tail reporting
- blip-chart generation
- future analyst filtering

---

## Built-In Agent Specifications

## 1. Folder Activity Agent

Purpose:

- observe file/folder activity under configured watch paths
- emit summary windows rather than raw event spam

Requirements:

- support multiple watch paths
- support default excludes
- support user excludes merged with defaults, not replacing them
- emit changed-file evidence suitable for later analyst filtering
- preserve counts and per-window activity signal

Important design direction:

- avoid “25 agents for 25 file types”
- keep watcher generic
- let analyst rules classify file families later

Required summary payload fields:

- watched paths
- changed files
- counts
- activity signal
- optional extension counts / directory counts

Desired future payload additions:

- full changed-file list when feasible
- extension histogram
- top directories
- duplicate-hit counts within window

## 2. Trail Tracker Agent

Purpose:

- watch app-generated trail-style files that imply active work

Current conceptual examples:

- Creo trail tracking
- future Blender or other tool-specific lightweight trail emitters

Requirements:

- detect active trail growth
- emit lifecycle boundaries:
  - session open
  - session close
- emit summary windows with:
  - changed files
  - size deltas
  - activity signal

The trail tracker concept is valid because some application domains expose good evidence through append-only or incrementing work artifacts.

## 3. Screen / Screenshot Agent

Purpose:

- optional screen-context or screenshot support

Current direction:

- do not treat screenshot activity as meaningful work evidence by default
- it may remain telemetry-only until a better semantic model exists

## 4. App-Native Activity Agents

These should exist only where filesystem evidence is insufficient.

Examples:

- Blender activity trail addon
- Modo/LXO activity addon
- other app-native emitters where real work occurs without reliable file writes

Requirements:

- ultralight emission
- bounded disk writes
- explicit lifecycle markers where possible
- never spam raw per-command events if coarser breadcrumbs work

---

## Analyst Layer Specification

The analyst layer is a first-class subsystem, not an afterthought.

Its job is to derive useful interpretations from canonical logs without rewriting history.

## Required Analyst Capabilities

- local-day blip charts
- last-activity queries
- filtered activity reports
- per-agent occupancy views
- derived daily summaries

## Derived Evidence Model

Analyst outputs must be derived from source logs, not replace them.

Important derived concepts:

- occupancy
- intensity
- file-family classification
- logical work file identity
- daily work ledger

## Occupancy vs Intensity

Occupancy:

- was this agent active in this bucket?

Intensity:

- how strongly did evidence suggest concentrated work in this bucket?

Intensity should be additive and clipped, not heavily normalized by default.

Rationale:

- hand-wavy evidence should not be overfitted into fake precision
- clipped additive scoring is more honest than over-normalized weighting

## File-Family Rules Registry

The analyst layer should own a family-rules registry for path interpretation.

Example classes:

- raw-preserved families
- canonicalized families
- app-assisted families

### Creo

Creo work files likely need analyst-side canonicalization.

Candidate filename regex:

```regex
^(.+?)\.(prt|asm)\.(\d+)$
```

Interpretation:

- `widget.prt.17` and `widget.prt.18` map to logical file `widget.prt`
- `assembly.asm.4` maps to `assembly.asm`

### Plasticity

Plasticity autosaves/backups should remain distinct raw files by default.

Rationale:

- autosave hits are meaningful activity evidence
- explicit parent-folder saves are a separate stronger signal
- these should not be collapsed away prematurely

### Blender

Blender should use:

- autosave/temp-file evidence first
- app-native trail addon only if needed

## Daily Work Ledger

The analyst layer should eventually produce a per-day derived ledger containing:

- file family
- canonical file identity when applicable
- raw paths seen
- hit counts
- hit timestamps
- active bucket counts
- supporting agent labels

This is the likely path to answering:

- “what file did I work on most today?”

---

## Logging and Storage Specification

## Canonical Logs

Canonical event logs must remain:

- local files
- human-inspectable
- append-oriented
- durable

Preferred canonical format:

- JSONL

Optional additional human-readable sinks may exist, but JSONL is the ground truth.

## Time Handling

Must preserve the current corrected model:

- event timestamps stored in UTC with timezone
- daily files bucketed by local day
- displayed times rendered in local timezone

This requirement is non-negotiable.

## Log Rotation

Daily rotation by local day.

Diagnostics logs should use the same local-day boundary logic.

## Evidence Retention

Three categories:

- canonical event logs
- diagnostics logs
- derived analyst artifacts

Retention policy should be configurable independently for each.

---

## Diagnostics and Failure Visibility

This is one of the most important parts of the rewrite.

## Required Durable Failure Events

At minimum:

- `ipc_server_failure`
- `ipc_disconnected`
- `agent_spawn_failure`
- `agent_protocol_error`
- `sink_write_failure`
- `config_error`
- `shutdown_exception`

If the runtime remains alive after a critical subsystem failure, the failure must still be preserved in logs.

## Dashboard Failure Visibility

The native UI must have a clear runtime health area showing:

- ops running / stopped
- control connected / disconnected
- IPC healthy / degraded / failed
- per-agent degraded / failed status

The operator should not need to tail a log file to learn that the control plane is dead.

---

## Native UI Specification

Toolkit target:

- Slint

## UI Goals

- dense
- compact
- fast
- workstation-appropriate
- non-browser feel

## Required Screens / Panels

### Dashboard

- runtime health
- agent list with status
- current day summary
- control buttons

### Agent Health View

- per-agent state
- heartbeat age
- last summary age
- warning / degraded signals

### Activity View

- current day blip chart
- local-day labels
- summary row
- per-agent rows

### Logs / Diagnostics View

- recent runtime alerts
- IPC failure alerts
- agent errors

### Reports / Analyst View

- last active
- tail report
- day charts
- future derived daily ledger

## Interaction Requirements

- keyboard-friendly
- safe stop/start controls
- no blind process-kill semantics as the default control path

---

## CLI and Command Surface

The Rust CLI should become the canonical face of MiMoLo.

## Required Commands

- `mimolo --help`
- `mimolo dash`
- `mimolo ops start`
- `mimolo ops stop`
- `mimolo ops status`
- `mimolo ops list-active`
- `mimolo report`
- `mimolo activity`
- `mimolo blips`
- `mimolo blips --live --refresh <s>`

Short aliases may still be installed, but they should be simple veneers over the Rust CLI.

## CLI Error Behavior

- bad flags fail fast
- help is explicit
- dependency or runtime issues produce actionable output
- IPC failures should explain whether Ops is down, IPC is dead, or control path is degraded

---

## Configuration Specification

Config should remain local-file based.

Desired characteristics:

- one clear primary config file
- typed parsing
- explicit defaults
- no ambiguous split between launcher config and runtime config unless there is a very strong reason

Suggested direction:

- unify launch/runtime config semantics where practical
- reduce the need to reason about both `mml.toml` and `mimolo.toml` separately

---

## Reliability Requirements

## Startup

- detect already-running Ops instance cleanly
- connect dashboard to existing instance when appropriate
- avoid duplicate orchestrators

## Shutdown

- graceful stop first
- explicit agent sequencing
- bounded wait
- durable shutdown result logging

## Crash Survivability

- if UI dies, Ops may continue
- if control channel dies, Ops must log it
- if Ops dies, restart attempts must detect that accurately

## Process Identity

Process metadata may be logged for diagnostics.

But routine control should prefer IPC, not PID-guessing.

---

## Performance Requirements

## Runtime

- low idle CPU
- bounded memory
- no pathological disk churn in normal operation

## Agents

- low steady-state cost
- throttled summaries
- avoid raw event floods unless explicitly debug-enabled

## UI

- smooth dashboard refresh
- no browser overhead
- no dependency on npm/node/electron at runtime

---

## Migration Requirements

The Rust rewrite should migrate behavior, not blindly mirror implementation.

## Preserve

- event concepts
- activity-signal semantics
- local-day log bucketing
- canonical JSONL evidence
- blip-chart mental model
- short-command user experience

## Retire

- PowerShell as primary launcher logic
- Electron dashboard
- Node/npm/npx as runtime dependency for the dashboard
- slowpoke as a respectable long-term IPC strategy

## Transitional Possibility

It is acceptable for the first Rust milestone to:

- keep reading legacy JSONL logs
- preserve compatible log schema where practical
- coexist temporarily with some legacy agent outputs during migration

---

## Suggested Delivery Phases

## Phase 1: Rust Core and CLI

- Rust config loading
- Rust ops runtime
- Rust IPC
- Rust command family
- stable status/stop/start

## Phase 2: Rust Built-In Agents

- folder activity agent
- trail tracker agent
- basic diagnostics and failure surfacing

## Phase 3: Native UI

- Slint dashboard
- agent health
- control actions
- diagnostics view

## Phase 4: Analyst Views

- local-day blips
- activity reports
- last-active view
- derived daily ledger foundations

## Phase 5: App-Native Extensions

- Blender activity support if needed
- other app-native emitters only where justified by evidence gaps

---

## Open Decisions

- exact IPC transport library and abstraction choice for Windows named pipes
- whether first-party agents run in-process, out-of-process, or mixed
- whether external non-Rust agent support remains a long-term first-class feature
- whether the analyst subsystem ships in the same binary or separate subcommand crate
- exact config unification strategy
- exact public log schema versioning strategy for the Rust rewrite

---

## Bottom Line

The Rust rewrite should produce:

- one trustworthy runtime
- one trustworthy command surface
- one native UI
- one durable evidence model
- one analyst-friendly log pipeline

It should not be a “Rust port of today’s mess.”

It should be a cleaner system that keeps the good ideas:

- local-first evidence
- lightweight agents
- durable structured logs
- analyst-friendly summaries
- compact operator visibility

while removing the obvious liabilities:

- shell glue as core runtime behavior
- JS runtime dependency for the dashboard
- fragile fallback IPC as a normal operating mode

That is the target architecture.
