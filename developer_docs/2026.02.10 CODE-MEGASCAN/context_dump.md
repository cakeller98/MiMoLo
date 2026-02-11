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
1. **Item 10 is active priority again**: maintainability-first decomposition and concern-boundary compliance.
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
  - use repo-local temp paths for ad-hoc validation work (`temp_debug/tmp/...`) instead of system `/tmp` paths.
- Collaboration preference:
  - one decision site at a time when adjusting exception behavior;
  - always provide suggested `git add` + commit message after completion.
  - commit messages must use `Performed verification with:` and list each check with explicit status (`PASS` / `FAIL` + brief failure note when applicable).
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
  - `pack_agent_core.ts` (compat export barrel),
  - `pack_agent_types.ts` (pack-agent type contracts),
  - `pack_agent_contracts.ts` (manifest/source schema + semver validation contracts),
  - `pack_agent_repository.ts` (repository scan/path/dir policies),
  - `pack_agent_manifest_io.ts` (manifest + build-manifest TOML mutation I/O),
  - `pack_agent_archive.ts` (hashing/archive/verification I/O),
  - `pack_agent_cli_helpers.ts` (CLI support),
  - `pack_agent_errors.ts` (shared helpers).
- Recent hardening removed expected-validation throws in source-list mode and replaced with deterministic conditional accounting + explicit mode results.
- MML Phase 1 shell decomposition is now active and materially progressed:
  - `mml.sh` reduced to coordinator-only entrypoint (74 LOC).
  - concern modules now live in `scripts/mml/`:
    - `common.sh`, `prepare.sh`, `launch.sh`, `process.sh`, `usage.sh`, `args.sh`, `dispatch.sh`.
  - smoke checks passing:
    - `bash -n mml.sh && bash -n scripts/mml/*.sh`
    - `./mml.sh help`
    - `./mml.sh env`
- Portable runtime startup hardening:
  - Ops launch paths now support a Poetry-free runtime startup path via explicit `MIMOLO_OPERATIONS_PYTHON`.
  - deploy now provisions `temp_debug/bin/.venv` and hydrates it from the existing Poetry environment (network-independent in constrained environments).
  - bundle app now exports `MIMOLO_OPERATIONS_PYTHON` into bundled runtime defaults so Control can start Operations without requiring `poetry` on runtime PATH.
  - runtime bootstrap now enforces managed-source Python only:
    - no fallback to `python3`/`python` command discovery.
    - source interpreter is explicit via `MIMOLO_BOOTSTRAP_SOURCE_PYTHON` (or Poetry-resolved interpreter).
    - bootstrap creates/replaces runtime `.venv` when Python major/minor mismatches source interpreter.
  - runtime bootstrap is now lock-serialized (`<runtime_root>/.bootstrap.lock`) to prevent concurrent hydration races.
  - bundle runtime location policy is now mml-configurable:
    - `bundle_runtime_mode = auto|portable|user_data`
    - `bundle_runtime_path = ./.venv` (portable mode path, relative to app parent when non-absolute)
  - bootstrap/runtime path alignment hardened:
    - bootstrap now accepts explicit runtime venv path (`MIMOLO_RUNTIME_VENV_PATH` / `--runtime-venv`),
    - control runtime-prep passes that value through,
    - bundle exports the same runtime venv path into process env so bootstrap target and operations python target cannot drift.
  - bootstrap UX visibility in Control proto is now active:
    - startup overlay captures real bootstrap stage lines and paths,
    - progress bar advances from actual bootstrap events (not fake timers),
    - explicit `OK` acknowledgement is required after runtime-ready before overlay dismissal.

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
Item 11 pack-agent verification blocker is now resolved and re-validated.
Resume planned order:
1. Phase 1 MML shell concern decomposition (`mml.sh` -> `scripts/mml/<concern>.sh`, no TS yet),
2. then Phase 2 MML TypeScript migration (`mml.sh`/`mml.ps1` thin wrappers -> compiled `mml.js` -> concern modules),
3. then continue remaining maintainability slices in matrix order.

## Confirmed Execution Order (User-Directed, Updated)
Work in this exact order, one commit-ready slice at a time (not together):
1. Pack-agent maintainability completion first:
  - `mimolo/utils/src/pack_agent_core.ts` final concern split and dedup pass.
2. Phase 1 MML shell decomposition (no TypeScript yet):
  - `mml.sh` delegates to `scripts/mml/<concern>.sh` modules by concern.
  - preserve behavior exactly while splitting concerns.
3. Phase 2 MML TypeScript migration:
  - move concern logic to `mimolo/utils/src/mml/<concern>.ts`.
  - wrappers become thin launchers:
    - `mml.sh` -> compiled `mml.js` -> concern modules
    - `mml.ps1` -> compiled `mml.js` -> concern modules
4. Then continue maintainability slices in order:
  - `mimolo/control_proto/src/ui_renderer_sections/commands_and_install.ts`
  - `mimolo/agents/screen_tracker/screen_tracker.py`

## Scripts Refactor Direction (Design Intent, Updated)
- Phase 1 explicitly avoids introducing TS; decompose shell concerns first for safety.
- Phase 2 introduces TS only after concerns are isolated and behavior is stable.
- Runtime choice for wrappers is compiled JS (`mml.js`) only; no `tsx`, no `ts-node`.
- `mml.ps1` is not hand-maintained during transition; treat it as a generated/thin mirror target.
- `mml.sh` and `mml.ps1` remain backward-compatible entrypoints after migration.
- Shared cross-cutting policy modules (for example semver/version semantics) should live in reusable `mimolo/utils/src/common/` modules, not duplicated inside `mml` concerns.
