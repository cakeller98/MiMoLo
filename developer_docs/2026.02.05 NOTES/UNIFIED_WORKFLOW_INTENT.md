# Unified Workflow Intent (Reference-History Consolidation)

Date: 2026-02-08
Status: Canonical workflow-intent document

## 1. Purpose
This document captures product and UX workflow intent extracted from historical `developer_docs` material.

Interpretation rules:
- Code remains implementation truth.
- This document preserves UX/workflow intent even when implementation is incomplete.
- Historical docs are references, not direct coding plans.

## 2. Current Reality vs Intent
Current reality (implemented):
- Operations runtime, Agent JLP lifecycle, and logging pipeline are functioning.
- Control exists as a working prototype (`mimolo/control_proto`) with:
  - lifecycle controls (start/stop/restart),
  - instance actions (add/duplicate/remove/configure),
  - a widget panel/testbed path,
  - persistent IPC transport to reduce connection churn and overhead.

Intent to preserve:
- Control should be the user-facing control plane.
- Operations should remain the execution and state authority.

## 3. Core Workflow Model
1. Control handles user interaction.
2. Operations validates, installs, configures, and runs Agents.
3. Agents run as isolated subprocesses and communicate with Operations via Agent JLP.
4. Control does not communicate directly with Agent processes.

## 4. Plugin Install UX Intent (Preserve)
Primary UX pattern to preserve:
- Install and upgrade flow should feel similar to Blender extensions:
  - drag-and-drop zip into control, or
  - select zip via extension/agent manager UI.

Behavioral flow:
1. User provides an agent package zip via Control.
2. Control passes install/upgrade request to Operations.
3. Operations validates package metadata/integrity and applies install policy.
4. Operations returns result/status to Control.
5. Control updates UI state and available actions.

Trust and policy posture:
- Capability openness: protocol-compatible plugins can be developed in any language.
- Release distribution trust is closed-by-default:
  - install/run requires signed + allowlisted packages.
- Developer unsafe sideloading is explicit opt-in and should display warning each launch/session.

Operational policy intent:
- Install and upgrade logic belongs to Operations.
- Control should not unpack/deploy payloads directly.
- Preserve planned command semantics from notes:
  - list installed plugins
  - install (no overwrite)
  - upgrade (version-aware)
  - install with force overwrite

## 5. Provisioning and Multi-Instance Intent (Preserve)
Core distinction to preserve:
- Installed agent packages are not the same as running/provisioned instances.

Desired workflow:
1. User installs an agent package once.
2. User provisions one or more instances from that package.
3. Each instance has independent parameters and enable/disable state.
4. Operations persists and enforces instance configuration.

## 6. Configuration Ownership and Location Intent
Ownership rule:
- Operations owns writable runtime configuration for agents and instances.
- Control requests changes through control commands; Operations writes canonical files.

Canonical path intent:
- `agent_config.toml` should be owned by Operations under OS-appropriate data root.
- Target shape:
  - `<mimolo_data_root>/operations/agent_config.toml`

OS examples aligned with current data-root model:
- Windows: `%AppData%/mimolo/operations/agent_config.toml`
- macOS: `~/Library/Application Support/mimolo/operations/agent_config.toml`
- Linux: `~/.local/share/mimolo/operations/agent_config.toml`

Note:
- If product direction later requires a different Linux base path (for example `~/.mimolo`), keep the same `operations/agent_config.toml` subpath contract.

## 7. Data/Control Separation Intent
Preserve this separation:
- Control reads durable activity data from files (journals/cache views).
- Control uses command bridge only for control and runtime state.
- Operations remains system-of-record for lifecycle, health, and config authority.

## 8. Reporter Workflow Intent
Preserve reporter concept:
- Report generation remains a Control-driven UX path.
- Control can synthesize segment views from journals/cache and pass prepared data to reporter subprocesses.
- Reporter plugins are presentation/export tools, not runtime control owners.

## 9. Security and Reliability Intent
Cross-cutting behavior to preserve:
- Owner-only permissions for socket/config/log artifacts where possible.
- No shell command construction from untrusted strings.
- Operations-side validation for package/install actions.
- Clear diagnostics for failures and policy rejections.
- Prefer persistent, bounded IPC flows over connection-spam polling patterns.
- Favor architectural fixes over retry/noise masking.

## 10. Non-Goals
This document is intentionally not:
- a sprint-by-sprint implementation checklist,
- a direct migration script from old docs,
- a commitment that every historical idea must be implemented.

## 11. Change Tracking Discipline (Required Going Forward)
When implementation changes land:
1. Update root `CHANGELOG.md` for code/runtime behavior changes.
2. Update `developer_docs/CHANGELOG.md` for documentation-only changes.
3. Keep entries on the same day as the change.
4. Classify entries under `Added`, `Changed`, `Fixed`, or `Breaking`.
5. When a planned workflow item is implemented, update:
  - `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md`
6. Keep `developer_docs/8_Future_Roadmap_and_Summary.md` strategic-only.
7. Keep this unified workflow document stable unless workflow intent itself changes.

## 12. Source Inputs Merged Into This Document
Primary reference sources:
- `developer_docs/control_dev/CONTROL_SPECIFICATION.md`
- `developer_docs/TERMINOLOGY_MAP.md`
- `developer_docs/agent_dev/DATA_STORAGE_CONVENTIONS.md`
- `developer_docs/2026.01.28 NOTES/1-29-2026_context.md`
- `developer_docs/2026.01.28 NOTES/2026-01-29_status_combined.md`
- `developer_docs/monitor_ux_dev/AGENT_MENU_FEATURE.md`
- `developer_docs/security_agent.md`
- `developer_docs/agent_dev/client_folder_activity/client_folder_activity_SPEC.md`
