# Developer Docs Triage (Comprehensive)

Date: 2026-02-07
Scope: all markdown files under `developer_docs/`
Policy labels:
- `KEEP`: keep as active reference (or canonical source).
- `MERGE`: keep file as historical reference but treat its workflow intent as merged into canonical notes.
- `ARCHIVE`: historical implementation logs/transcripts/plans not used as active direction.

## Canonical and Current Notes
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/2026.02.05 NOTES/README.md` | KEEP | Canonical notes index. |
| `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md` | KEEP | Implementation-truth tracker. |
| `developer_docs/2026.02.05 NOTES/NOTES_TRIAGE_2026-02-05.md` | KEEP | January-notes triage log. |
| `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md` | KEEP | Canonical workflow-intent consolidation. |
| `developer_docs/2026.02.05 NOTES/DEVELOPER_DOCS_TRIAGE_2026-02-07.md` | KEEP | Full docs triage ledger. |

## 2026.01.28 Notes
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/2026.01.28 NOTES/README.md` | KEEP | Declares reference-only status and archive pointer. |
| `developer_docs/2026.01.28 NOTES/1-29-2026_context.md` | MERGE | Context intent merged into unified workflow doc. |
| `developer_docs/2026.01.28 NOTES/2026-01-29_status_combined.md` | MERGE | Install/registry and control-flow intent merged into unified workflow doc. |
| `developer_docs/2026.01.28 NOTES/archive/2026-01-29_status.md` | ARCHIVE | Superseded status snapshot. |
| `developer_docs/2026.01.28 NOTES/archive/2026-01-29_status_v2.md` | ARCHIVE | Superseded status snapshot. |
| `developer_docs/2026.01.28 NOTES/archive/another run.md` | ARCHIVE | Raw runtime transcript. |
| `developer_docs/2026.01.28 NOTES/archive/current_test_run.md` | ARCHIVE | Raw runtime transcript. |

## Core Architecture Narrative Docs
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/1_Core_Overview.md` | KEEP | High-level product framing. |
| `developer_docs/2_Core_Concepts.md` | MERGE | Useful conceptual intent; some details stale vs code. |
| `developer_docs/3_Architectural_Overview.md` | MERGE | Conceptual flow remains useful; implementation details partly stale. |
| `developer_docs/4_Data_Schema_and_Message_Types.md` | MERGE | Message intent useful; canonical protocol now in code/spec docs. |
| `developer_docs/5_Lifecycle_and_Control_Flow.md` | MERGE | Lifecycle intent useful; exact runtime behavior must defer to code. |
| `developer_docs/6_Extensibility_and_Plugin_Development.md` | MERGE | Agent behavior principles preserved as workflow intent. |
| `developer_docs/7_Constraints_and_Performance_Etiquette.md` | MERGE | Performance etiquette remains directional intent. |
| `developer_docs/8_Future_Roadmap_and_Summary.md` | MERGE | Future themes retained as non-binding direction. |
| `developer_docs/ASM_Development_Documentation.md` | ARCHIVE | Obsidian index wrapper, no independent canonical content. |

## Dashboard / UX / Terminology
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/dashboard_dev/DASH_SPECIFICATION.md` | MERGE | Primary source for control/data separation and dashboard UX intent. |
| `developer_docs/monitor_ux_dev/AGENT_MENU_FEATURE.md` | MERGE | Useful operational UX ideas, partially implemented. |
| `developer_docs/TERMINOLOGY_MAP.md` | MERGE | Role mapping and naming intent consolidated. |

## Agent Developer and Spec Docs
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/agent_dev/AGENT_DEV_GUIDE.md` | KEEP | Ongoing developer reference for agent model. |
| `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md` | KEEP | Core protocol reference intent (alongside code). |
| `developer_docs/agent_dev/FIELD_AGENT_ARCHITECTURE.md` | MERGE | Architectural intent mostly represented elsewhere; some status claims stale. |
| `developer_docs/agent_dev/DATA_STORAGE_CONVENTIONS.md` | MERGE | Storage placement intent merged into unified workflow doc. |
| `developer_docs/agent_dev/trail_tracker/trail_tracker_SPEC.md` | MERGE | Workflow-level agent behavior examples preserved as references. |
| `developer_docs/agent_dev/blender_sonar/blender_sonar_SPEC.md` | MERGE | Workflow-level agent behavior examples preserved as references. |
| `developer_docs/agent_dev/client_folder_activity/client_folder_activity_SPEC.md` | MERGE | Multi-instance intent source preserved. |
| `developer_docs/agent_dev/screen_tracker/screen_tracker_SPEC.md` | MERGE | Workflow-level behavior reference. |

## Logging and Migration History
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/logging_spec/LOGGING_IMPLEMENTATION_SUMMARY.md` | ARCHIVE | Legacy celebratory summary, overlaps with structured logging docs. |
| `developer_docs/LOGGING_FIXES/LOGGING_IMPLEMENTATION_SUMMARY.md` | ARCHIVE | Implementation-historical detail, not forward workflow intent. |
| `developer_docs/LOGGING_FIXES/LOGGING_FIXES_APPLIED.md` | ARCHIVE | Fix diary/history, not active planning doc. |
| `developer_docs/LOGGING_FIXES/LEGACY_PLUGIN_REMOVAL.md` | ARCHIVE | Migration completion history. |
| `developer_docs/refactor_plan/refactor_plan_v0.2-to-v0.3.md` | ARCHIVE | Pre-implementation migration plan (historical). |
| `developer_docs/refactor_plan/INCREMENTAL_REFACTOR_PLAN.md` | ARCHIVE | Pre-implementation migration plan (historical). |

## Platform / Security / Operations Setup
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/ipc_comms/ipc_PLATFORM_ARCHITECTURE.md` | KEEP | Platform support and IPC rationale reference. |
| `developer_docs/ipc_comms/SLOWPOKE_MODULE.md` | KEEP | Explicit fallback policy reference for unsupported platforms. |
| `developer_docs/security_agent.md` | KEEP | Security baseline for future implementation decisions. |
| `developer_docs/REMOTE_SSH_SETUP.md` | KEEP | Contributor environment operations guide. |

## Conversation Artifacts
| Path | Decision | Rationale |
|---|---|---|
| `developer_docs/copilot-conversations/20251113_180129__what_can_you_infer_from_what_you_can_see_within.md` | ARCHIVE | AI conversation artifact; not product source-of-truth. |
| `developer_docs/copilot-conversations/20251113_200540__write_me_a_small_python_class_that_does_the_following.md` | ARCHIVE | AI conversation artifact; not product source-of-truth. |

## Practical Use Rule
When implementing new work:
1. Read code truth first.
2. Read `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md` for preserved UX/workflow intent.
3. Use `MERGE` docs as historical context only.
4. Treat `ARCHIVE` docs as non-authoritative history.
