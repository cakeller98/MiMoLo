# Future Roadmap and Summary

Date: 2026-02-08
Purpose: strategic direction, not sprint-by-sprint task tracking.

Canonical execution tracker:
- `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md`

Protocol reality tracker:
- `developer_docs/agent_dev/PROTOCOL_IMPLEMENTATION_STATUS.md`

## Strategic Priorities

1. Control as the durable user-facing plane
- Mature from prototype instrumentation to production workflows:
  - agent install/upgrade management
  - instance provisioning/configuration at scale
  - stable widget-based monitoring experiences

2. Operations as strict execution authority
- Keep all runtime control, lifecycle, and config persistence centralized in Operations.
- Maintain a narrow, explicit IPC contract with clear validation and diagnostics.

3. Artifact-first breadcrumb model
- Keep vault/journal payloads lightweight.
- Store heavy artifacts in plugin-owned instance storage under `MIMOLO_DATA_DIR`.
- Enforce archive-before-purge and explicit user permission before destructive actions.

4. Plugin ecosystem hardening
- Move scaffold agents to production-grade behavior and tests.
- Strengthen package install/upgrade lifecycle and integrity policy.
- Keep release distribution trust closed-by-default (signed + allowlisted).
- Preserve cross-platform behavior expectations for both runtime and plugin tooling.

5. Security and resilience defaults
- Keep owner-scoped permissions, validated payloads, and bounded queues.
- Keep low-overhead runtime behavior with measurable backpressure and reconnect behavior.
- Prefer design-level fixes over retries/noise masking.

## Roadmap Horizons

Near term:
- complete end-to-end widget render/action bridge
- complete install/upgrade lifecycle through Operations
- complete archive/restore/purge workflow gates

Mid term:
- commercial Control app parity with proto runtime features
- richer instance-level monitoring UIs and widget contracts
- expanded protocol conformance tests and plugin contract tests

Long term:
- distributed Operations/collector topology
- deeper analytics/reporting workflows
- schema/version negotiation and compatibility automation

## Guiding Principle

Measure twice, cut once:
- favor simple, durable architecture decisions,
- avoid throwaway intermediate layers unless there is measurable necessity.
