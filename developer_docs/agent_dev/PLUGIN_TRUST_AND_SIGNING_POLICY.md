# MiMoLo Plugin Trust and Signing Policy

Date: 2026-02-08
Status: Policy (active)
Scope: Agents, Reporters, Widgets, and future plugin classes.

## 1. Policy Summary

MiMoLo uses a closed-by-default plugin model in release mode:
- Plugins must be signed by MiMoLo and allowlisted to install or run.
- Protocol compatibility alone does not grant install or execution permission.
- Control remains the install UX surface, but Operations is the enforcement authority.

## 2. Distribution Modes

### 2.1 Release Mode (Default)
- No arbitrary plugin sideloading.
- Install and launch require:
  - trusted signature validation,
  - allowlist match for `plugin_id` + `version` + package hash,
  - policy checks for declared capabilities.

### 2.2 Developer Mode (Unsafe)
- Sideloading is allowed only when explicit unsafe mode is enabled.
- Unsafe mode must show a warning every launch/session.
- Unsafe plugins remain isolated subprocesses and still must obey protocol contracts.
- Unsafe mode is for local development/testing only, not default end-user operation.

## 3. Submission and Inclusion Workflow

1. Plugin developer submits candidate plugin to MiMoLo maintainers.
2. MiMoLo reviews code, behavior, and test coverage.
3. If accepted, plugin is signed and added to allowlist policy.
4. Plugin tests become part of the main project test suite.
5. Plugin is included in distribution channels.

If a trusted plugin regresses or violates safety constraints:
- distribution can ship a disabled placeholder/stub entry,
- user-facing message must explain temporary disablement and recovery path,
- maintainers request corrective changes from plugin owner.

## 4. Install and Launch Enforcement

Install-time gate (Operations):
- validate package structure and manifest,
- validate signature and allowlist status,
- validate capability declaration and policy compliance.

Launch-time gate (Operations):
- re-check signature/allowlist status before process start,
- deny execution if package trust state is invalid.

## 5. Runtime Trust Boundary

- Plugins run in separate processes with independent memory space.
- Operations and Control do not assume plugin internals are trusted.
- Plugin-to-system interaction should be capability-gated and mediated by Operations.
- Shared SDK/base classes are optional convenience, not compatibility requirements.

## 6. UX Intent for Control

- Drag/drop and file-picker install UX remain supported for user ergonomics.
- In release mode, install attempts for unsigned/unallowlisted plugins are rejected with clear diagnostics.
- In unsafe developer mode, install can proceed after explicit warning/acknowledgment.

## 7. Relationship to Other Docs

- Communication contract: `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md`
- Active backlog and execution status:
  `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md`
- Workflow intent:
  `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`

