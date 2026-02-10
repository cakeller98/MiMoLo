# Context Dump (Working Session Snapshot)
Date: 2026-02-10 as of 10:45am PT
Purpose: compact carry-forward context without duplicating canonical docs.

## Canonical Sources (read first)
- Backlog + execution truth: `developer_docs/2026.02.05 NOTES/GROUND_TRUTH_IMPLEMENTATION_MATRIX.md`
- Docs history: `developer_docs/CHANGELOG.md`
- Exception policy decisions: `developer_docs/2026.02.10 CODE-MEGASCAN/07_EXCEPTION_REEVALUATION_DECISIONS_2026-02-10.md`
- Exception scan task + policy:
  - `.vscode/settings.json` (`mimolo.quality.exceptionPolicy`)
  - `.vscode/tasks.json` (`qc:exceptions`)
- Full code-health audit bundle: `developer_docs/2026.02.10 CODE-MEGASCAN/`

## Current Priority
1. **Item 10 is now top priority**: maintainability-first decomposition and concern-boundary compliance.
2. Item 1 (ops lifecycle/orphan elimination) remains critical, but is currently secondary to maintainability unless safety/regression forces immediate behavior work.

## Rule-Set Sensibilities (non-negotiable)
- **Code/tests are implementation truth** when docs differ.
- Maintainability first:
  - coordinator files should keep shrinking;
  - one primary concern per module;
  - remove duplication with deliberate shared helpers.
- Exception posture:
  - treat `try/catch` / `try/except` / generic `throw` as hostile by default;
  - allowed only for:
    - boundary failures (OS/fs/network/subprocess/plugin IPC),
    - cleanup guarantees (`try/finally`),
    - strict contract/invariant validation.
  - no catch-and-continue for deterministic expected states.
- Error flow:
  - expected outcomes use explicit conditionals/result objects;
  - CLI boundary owns exit signaling and user-facing diagnostics.
- Work style:
  - committable/reversible slices;
  - strict QC after each meaningful slice;
  - docs/changelog updated as part of each completed slice.
- Collaboration preference:
  - one decision site at a time when adjusting exception behavior;
  - always provide suggested `git add` + commit message after completion.
  - always consult this `context_dump.md` at the start of each new work slice and update it when rules/priorities change.
  - if ambiguity or inconsistency is detected, do not assume:
    - propose 1–3 concrete options (with a recommended default),
    - include a final `Other:` option for user-defined input,
    - wait for user clarification before implementing ambiguous decisions.

## Current Implementation Snapshot (high level)
- Runtime and Control proto have ongoing decomposition into focused modules.
- `pack-agent` decomposition complete across:
  - `pack-agent.ts` (CLI orchestration),
  - `pack_agent_modes.ts` (compat export barrel),
  - `pack_agent_source_list_mode.ts` (source-list processing + source-list creation flows),
  - `pack_agent_single_mode.ts` (single-agent pack flow),
  - `pack_agent_versioning.ts` (semver bump policy),
  - `pack_agent_packing_helpers.ts` (shared pack workspace + shared skip-note helpers),
  - `pack_agent_core.ts` (core manifest/hash/repo/archive),
  - `pack_agent_cli_helpers.ts` (CLI support),
  - `pack_agent_errors.ts` (shared helpers).
- Recent hardening removed expected-validation throws in source-list mode and replaced with deterministic conditional accounting + explicit mode results.

## Remaining Exception Patterns in pack-agent module (intentional)
- Core invariant throws (schema/semver/repo-dir contract): keep.
- Cleanup `try/finally` for temp dirs/readline: keep.
- Boundary catches (`main().catch`, archive finalize promise rejection path): keep.
- No known catch-and-continue control-flow remains in `mimolo/utils` pack-agent paths.

## QC Baseline
Run as standard gate:
- `npm --prefix mimolo/utils run build`
- `poetry run ruff check .`
- `poetry run mypy mimolo scripts/qc_exception_scan.py`
- `poetry run pytest -q`
- `poetry run python scripts/qc_exception_scan.py`

Last known snapshot in matrix/changelog: clean, `132 passed`.

## Next Recommended Action
Continue Item 10 by selecting next largest orchestrator slice and applying the same pattern:
1. isolate concern boundary,
2. remove implicit/exception-driven control flow,
3. run strict QC,
4. update matrix + changelog.

## Confirmed Execution Order (User-Directed)
Work these maintainability slices in this exact order, one commit-ready slice at a time (not together):
1. `mimolo/utils/src/pack_agent_core.ts`
2. `mimolo/control_proto/src/ui_renderer_sections/commands_and_install.ts`
3. `mimolo/agents/screen_tracker/screen_tracker.py`

Rationale captured from user direction:
- Do `pack_agent_core.ts` first to complete the current pack-agent maintainability arc to a high standard.
- Do `commands_and_install.ts` next because it opens high-value reuse opportunities for installer/deployment flows.
- Do `screen_tracker.py` third after infrastructure concerns are cleaner.

## Scripts Refactor Direction (Design Intent)
- After the current refactor slices, migrate automation logic from `./scripts` into reusable TypeScript modules under `mimolo/utils`.
- Prefer reusable shared modules for concerns like semver/version policy, packaging/deployment orchestration, and common command flows.
- Keep `mml.sh`, `mml.ps1`, and `mml.toml` backward compatible, but progressively thin them into wrappers over reusable utilities.
- Preserve behavior compatibility while reducing duplicated shell/PowerShell logic.
