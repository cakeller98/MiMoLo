# Context Dump (Working Session Snapshot)
Date: 2026-02-11 as of current working session
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
1. **Item 13 is now active highest priority**: agent-owned `widget_frame` end-to-end contract completion.
2. **Item 14 is next**: Control JSONL evidence viewer with derived segment filtering (read-only projection).
3. **Item 15 follows**: stable dummy evidence datasets + deterministic generator tooling.
4. Item 12 (CPU budgeting policy envelope) remains active and resumes after Items 13-15 unless safety/regression forces immediate behavior work.

## Session Decision Lock (2026-02-11)
- Folder watcher warning semantics are locked:
  - missing watch path => warn once per path per session on first missing transition,
  - restored path => log once on restore transition,
  - no interval-spam warnings for repeatedly missing paths.
- Manual widget `update` behavior is locked:
  - it must execute the same pipeline as the scheduled poll tick path (no separate/manual-only logic).
- Startup/restart scan burst is currently acceptable:
  - short transient CPU spikes during initial listing are tolerated for now.
- Watch-root policy is locked:
  - users are not restricted from watching broad roots,
  - but Control/agent diagnostics must clearly warn when runtime/log/journal/cache paths overlap a watched root because that can create self-amplifying churn.
- Portable config drift gotcha is now explicitly tracked:
  - `mimolo.portable.toml` can retain stale watch paths after source config changes; this must be visible and handled deliberately.

## Architecture Lock: Evidence + Rendering Planes (2026-02-11)
- Agents are autonomous and plugin-aware; Operations and Control are not plugin-aware renderers.
- Agent -> Operations JSON-lines remains the only runtime transport channel; protocol is extended by schema/message type, not transport replacement.
- `SUMMARY` packets are evidence/telemetry payloads that land in Operations logs as raw canonical records.
- Canonical evidence ledger scope is now locked to `summary` records only.
- Operational telemetry (`heartbeat`, `status`, `error`, `ack`, `log`) is persisted to diagnostics logs with retention and is not canonical work evidence.
- `activity_signal` semantics must be carried in `summary.data` packets so activity inference is data-driven and auditable.
- `activity_signal` contract lock:
  - `mode`: `active|passive`
  - `keep_alive`: `true|false|null`
  - `reason`: optional text
  - `summary` is the only activity-signal carrier (not heartbeat).
- Operations is the canonical ledger/vault:
  - stores raw JSONL records as-is (ground truth),
  - stores indices/pointers/hashes for agent-produced artifacts/bundles,
  - does not hard-code plugin rendering logic.
- Active/not-active timeline is a post-processing projection over raw records:
  - rounding/granularity decisions are report-time policy, not ingestion-time mutation.
- `WIDGET_FRAME` is the rendering plane:
  - agent produces `html_fragment_v1` (plus metadata like `state_token`, `ttl_ms`),
  - Operations transports/caches frame data,
  - Control sanitizes and renders generically.
- Shutdown completion contract is locked for clean exits:
  - `ACK(stop)` -> `ACK(flush)` + final `summary` -> `ACK(shutdown)` -> process exit.
- Daily evidence bundle producer is the agent (not Operations), with vault naming convention:
  - `<yyyymmdd>_<plugin>_<instance>.zip`
  - Operations stores for safekeeping with hash/index metadata.

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
  - bootstrap trigger behavior now matches first-run expectations:
    - runtime prepare is invoked automatically during initial renderer startup (no Start Ops click required),
    - bootstrap script output is streamed over a dedicated IPC event (`ops:bootstrap-line`) so overlay updates are immediate even when disconnected poll loops are slow.
- runtime performance instrumentation is now wired end-to-end for diagnostics:
  - Operations records per-tick wall-time, stage breakdown, per-agent drain/flush/message counters.
  - Operations exposes telemetry over IPC (`get_runtime_perf`).
  - Control subscribes and renders a live `Perf` line with CPU/tick/memory/top-agent hotspot summary.
  - Runtime perf now also samples per-agent OS process CPU/RSS, so parent runtime vs child-agent CPU mismatches are visible directly in UI (`top_agent_cpu`).
- folder watcher + widget refresh hardening now includes:
  - transition-only watch-path missing/restored logs (no interval warning spam),
  - one-time overlap warning when watch roots include runtime-managed directories,
  - manual widget update dispatch (`refresh`) before render,
  - runtime dispatch action translates `refresh` into immediate agent `flush`,
  - folder watcher snapshots run the same accumulation pipeline used by scheduled polling.

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
- `poetry run python scripts/qc_exception_scan.py --scope modified`
- `poetry run python scripts/qc_exception_scan.py --scope all`

Exception scan behavior:
- scanner now detects `py_try`, `py_except`, `ts_try`, `ts_catch`, and `ts_throw`.
- `--scope` supports `modified` and `all`.
- optional strict gate: `--fail-on-findings`.

Last known snapshot in matrix/changelog: clean, `132 passed`.

## Next Recommended Action
Item 12 phase-1 implementation is the immediate next action:
1. BaseAgent one-time CPU self-monitoring and heartbeat budget telemetry.
2. Operations budget policy wiring (default/override/max + envelope auto-scale).
3. Control/runtime visibility updates and strict QC rerun.

Policy lock (approved):
- missing per-agent override => info only (normal), not warning.
- warning only when override exceeds global default, and when clamped above global max.
- enforce envelope with proportional auto-scale:
  - `sum(effective_plugin_budgets) + ops_budget <= global_total_cpu_budget_percent`.

## Confirmed Execution Order (User-Directed, Updated)
Work in this exact order, one commit-ready slice at a time (not together):
1. Item 13: complete `widget_frame` end-to-end (agent -> operations transport/cache -> control sanitize/render).
2. Item 14: implement JSONL evidence viewer in Control with derived (not canonical) segment filtering.
3. Item 15: add deterministic fixture datasets + generator tooling to prevent rebuild wipeout of reference data.
4. Resume Item 12 CPU-budgeting policy envelope implementation.
5. Resume maintainability slices (Item 10) as queued in matrix.

## Scripts Refactor Direction (Design Intent, Updated)
- Phase 1 explicitly avoids introducing TS; decompose shell concerns first for safety.
- Phase 2 introduces TS only after concerns are isolated and behavior is stable.
- Runtime choice for wrappers is compiled JS (`mml.js`) only; no `tsx`, no `ts-node`.
- `mml.ps1` is not hand-maintained during transition; treat it as a generated/thin mirror target.
- `mml.sh` and `mml.ps1` remain backward-compatible entrypoints after migration.
- Shared cross-cutting policy modules (for example semver/version semantics) should live in reusable `mimolo/utils/src/common/` modules, not duplicated inside `mml` concerns.
