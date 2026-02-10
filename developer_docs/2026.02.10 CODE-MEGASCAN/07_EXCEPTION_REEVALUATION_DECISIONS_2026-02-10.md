# Exception Handling Re-Evaluation (Strict Policy)

Date: 2026-02-10  
Scope: current candidate list from recent refactor files

## Policy used for this review

- Expected conditions must be handled by explicit logic/conditionals, not by exception flow.
- `try/catch` is reserved for true external boundary failures (OS/fs/network/subprocess/plugin boundary).
- In build mode (`--source-list`), broken sources should fail the build (not continue quietly).
- In discovery mode (`--create-source-list`), folders without `build-manifest.toml` are expected skips.

## Decision Ledger (Keep vs Change)

### 1) `mimolo/utils/src/pack_agent_core.ts:101` (`findHighestRepoVersion`)
- Current: `readdir` wrapped in catch; `ENOENT` returns `null`.
- Decision: `CHANGE`.
- Why:
  - Missing repo directory on first run is common/expected.
  - Expected first-run state should be handled deterministically (`ensure_repo_dir`) rather than using exception path.
- Better result:
  - Ensure/create repo directory in caller before querying versions.
  - `findHighestRepoVersion` should not encode first-run setup behavior.
  - If directory cannot be created/read, fail with explicit write/read error.

### 2) `mimolo/utils/src/pack_agent_cli_helpers.ts:32` (`readPackageVersion` read)
- Current: catches `ENOENT` and returns `"unknown"`.
- Decision: `CHANGE`.
- Why:
  - Missing `package.json` can be checked explicitly before read.
  - This is not a hard runtime boundary for core packaging logic.
- Better result:
  - Use explicit file presence logic for expected missing case.
  - Let unexpected fs failures surface.

### 3) `mimolo/utils/src/pack_agent_cli_helpers.ts:41` (`readPackageVersion` JSON parse)
- Current: catches `SyntaxError`, returns `"unknown"`.
- Decision: `CHANGE` (preferred strict mode).
- Why:
  - Malformed `package.json` is a real repo integrity issue, not normal.
- Better result:
  - Fail with actionable error, or gate fallback behind explicit non-strict/dev flag.

### 4) `mimolo/utils/src/pack_agent_cli_helpers.ts:54` (`fileExists`)
- Current: catch on `access`; `ENOENT => false`.
- Decision: `KEEP` (boundary helper), with caution.
- Why:
  - Node fs API surface for existence checks is exception-based.
  - This helper centralizes that pattern and prevents ad-hoc spread.
- Constraint:
  - Keep this pattern isolated to helper-level boundary code only.

### 5) `mimolo/utils/src/pack_agent_cli_helpers.ts:81` (`resolveDefaultAgentsDir`)
- Current: catch `ENOENT => null`.
- Decision: `KEEP` (acceptable boundary probe).
- Why:
  - Optional default dir probe at runtime.
  - Explicitly bounded/typed handling.

### 6) `mimolo/utils/src/pack_agent_modes.ts:96` (stat source-list entry path)
- Current: catch/log/continue.
- Decision: `CHANGE`.
- Why:
  - In source-list build mode, missing/non-dir path means broken configuration.
  - Should fail build, not continue.
- Better result:
  - Raise/fail-fast with explicit entry id/path error.

### 7) `mimolo/utils/src/pack_agent_modes.ts:113` (read build manifest in source-list mode)
- Current: catch/log/continue.
- Decision: `CHANGE`.
- Why:
  - Listed agent without valid manifest is a real build error.
- Better result:
  - Fail-fast with entry + manifest path diagnostics.

### 8) `mimolo/utils/src/pack_agent_modes.ts:126` (normalize semver)
- Current: catch/log/continue.
- Decision: `CHANGE`.
- Why:
  - Invalid version metadata in listed source is a hard build error.
- Better result:
  - Fail-fast.

### 9) `mimolo/utils/src/pack_agent_modes.ts:141` (repo read in source-list mode)
- Current: catch/log/continue.
- Decision: `CHANGE`.
- Why:
  - Repo read/write errors are environment failures requiring intervention.
- Better result:
  - Fail-fast with specific repo path and error.

### 10) `mimolo/utils/src/pack_agent_modes.ts:355` (discovery mode catch+rethrow)
- Current: catch and rethrow with context.
- Decision: `KEEP`.
- Why:
  - Discovery mode intentionally filters folders by manifest presence first.
  - If manifest exists but parsing/validation fails, failing fast is correct.
  - catch+rethrow adds entry context without silently continuing.

### 11) `mimolo/utils/src/pack_agent_modes.ts:388` (single-agent repo read catch)
- Current: catch, print, `process.exit(1)`.
- Decision: `CHANGE`.
- Why:
  - Prefer raising explicit error upward instead of direct process exit in lower-level function.
  - Keeps control flow testable and composition-friendly.

### 12) `mimolo/control_proto/src/ui_renderer_sections/state_and_ops.ts:255` (`.catch`)
- Current: non-blocking IPC reset warning path.
- Decision: `KEEP`.
- Why:
  - Fire-and-forget UX helper call; failure should not block operator action.
  - Now logs explicit warning (not silent swallow).

### 13) `mimolo/control_proto/src/ui_renderer_sections/state_and_ops.ts:273` (`try/catch` around invoke)
- Current: catches IPC invocation failure and reports to user.
- Decision: `KEEP`.
- Why:
  - True runtime IPC boundary in interactive UI flow.

## Summary

- Keep: 5
- Change: 8

The biggest correctness issue is not existence of `try/catch` itself; it is **where continuation behavior is allowed**.  
For source-list build mode, current `catch + continue` sites should be converted to fail-fast behavior.

## Required next code changes

1. Add deterministic repository directory preparation before version scan/pack.
2. Remove first-run repo-dir exception handling from `findHighestRepoVersion`.
3. Convert source-list mode early catches (`:96`, `:113`, `:126`, `:141`) to fail-fast.
4. Replace low-level `process.exit(1)` in mode helpers with raised errors handled at CLI entrypoint.
5. Tighten package-version helper behavior (presence check conditional; malformed JSON policy explicit).

## Applied Follow-Up (this pass)

- Replaced `parseArgs` throw-based validation with explicit parse-result contract in `mimolo/utils/src/pack-agent.ts`.
- Replaced `createSourceListFromDir` existing-sources throw with explicit result payload (`created=false` + message) in `mimolo/utils/src/pack_agent_modes.ts`.
- Replaced low-level `process.exitCode` control in `packSingleAgent` with explicit `SinglePackResult` return values, and moved CLI failure signaling to `mimolo/utils/src/pack-agent.ts`.
