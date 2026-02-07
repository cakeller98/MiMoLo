> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.


---

TASK LIST CRIB SHEET

```
## Basic
- [ ] to-do
- [/] incomplete
- [x] done
- [-] canceled
- [>] forwarded
- [<] scheduling

## Extras
- [?] question
- [!] important
- [*] star
- ["] quote
- [l] location
- [b] bookmark
- [i] information
- [S] savings
- [I] idea
- [p] pros
- [c] cons
- [f] fire
- [k] key
- [w] win
- [u] up
- [d] down
- [D] draft pull request
- [P] open pull request
- [M] merged pull request
```

---

# 2026-01-29 Status Update (Combined)

This document merges `2026-01-29_status.md` and `2026-01-29_status_v2.md` so the originals can be deprecated.

## Packaging utilities
complete: 2026-01-31
- [x] `release-pack-agent` now supports release flags (mutually exclusive): --major | --minor | --patch
- [x] `release-pack-agent` now supports prerelease flags (mutually exclusive): --alpha | --beta | --rc
- [x] You can combine one release + one prerelease flag
- [x] Combined release+prerelease uses semver premajor/preminor/prepatch
- [x] Example: 1.0.1-beta.0 + --major --beta => 2.0.0-beta.0
- [x] Uses semver standard behavior for prereleases
- [x] alpha/beta/rc with dotted suffix (e.g., alpha.0, beta.0)

## Location & use
complete: 2026-01-31
- [x] Tool lives in `mimolo/utils/src/release-pack-agent.ts`
- [x] Recommended run: `npx tsx src/release-pack-agent.ts --source "../agents/agent_template" --beta`
- [x] `--out` resolves relative to `--source` when relative; default is `../repository`

## Packaging notes
complete: 2026-01-31
- [x] `build-manifest.toml` is the source manifest
- [x] `manifest.json` and `payload_hashes.json` are generated during packaging
- [x] Agent zip layout is documented in [[mimolo/agents/repository/README]]

## What we decided
- [x] Agents communicate with orchestrator over Agent JLP (stdin/stdout JSON lines)
- [i] AF_UNIX IPC is reserved for control <-> orchestrator (and report/exporters)
- [x] Storage is JSONL daily journals; no SQLite for now
- [x] Per-user data folder is the root for all artifacts (Windows/macOS/Linux)
- [/] Agent artifacts live in: <base>/<agent_name>/...
- [ ] Control artifacts live in: <base>/control/...

## Agent specs created
complete: 2026-01-31
- [x] trail_tracker_SPEC.md
- [x] blender_sonar_SPEC.md
- [x] client_folder_activity_SPEC.md
- [x] screen_tracker_SPEC.md
- [x] Specs include artifact storage rules per platform

## Architecture direction
- [x] Monorepo for now
- [/] Electron deferred
- [x] Current module layout target includes orchestrator (python)
- [x] Current module layout target includes agents/*
- [ ] Current module layout target includes reporter_exporters/*
- [x] Current module layout target includes control (TS IPC prototype only)
- [x] Current module layout target includes common (shared schemas/protocols)
- [/] Later: `mimolo-control` package for Electron UI
	- [x] Stub created
	- [ ] Next step - planning

## IPC prototype (TypeScript)
complete: 2026-01-31
- [x] Minimal TS IPC harness exists in `mimolo/control_proto/`
- [x] `src/index.ts` connects to AF_UNIX socket via MIMOLO_IPC_PATH and sends a placeholder command
- [x] package.json + tsconfig.json + README.md are set up

## Install & registry plan (agreed)
- [<] Agents are installed to per-user folder, not run from source module
- [<] Install = unzip into %AppData%/mimolo/agents/<plugin_id>/ (platform equivalents)
- [<] Orchestrator scans install folder to list available plugins
- [<] Installed plugins != running instances (instances are separate config/task list)
- [<] dash list-plugs
- [<] dash install <zip> (no overwrite)
- [<] dash upgrade <zip> (only if newer)
- [<] dash install --force <zip> (overwrite)

## Plugin manifest (minimal)
complete: 2026-01-31
- [x] manifest.json outside payload files; contains version + required params
- [x] payload_hashes.json included in zip but not itself hashed

## Integrity model (agreed)
- [x] Use SHA-256 for file hashes
- [ ] Orchestrator stores a signed copy of payload hashes using a local secret key (HMAC-SHA256)
- [ ] Validation compares current file hashes vs payload_hashes.json AND verifies HMAC signature
- [ ] Prevents tampering even if someone edits payload_hashes.json on disk

## Recent change summary
complete: 2026-01-31
- [x] Agents moved under `mimolo/agents/`
- [x] Added manifests and hash placeholders for agent_template and agent_example
- [x] Added shared `tsconfig.base.json` and stubbed `mimolo-control/` (Electron v40)
- [x] Added `mimolo/utils` for packaging scripts

## Recent run notes
complete: 2026-01-31
- [x] start_monitor.ps1 output is captured under developer_docs/2026.01.28 NOTES/
- [x] Logs show UTC timestamps (filenames YYYY-MM-DD.mimolo.jsonl; e.g., 2026-01-31.mimolo.jsonl)

## Next actions (when back)
- [<] Clarify IPC naming: IPC umbrella vs AF_UNIX IPC vs Agent JLP; update docs accordingly
- [<] Implement install folder + manifest schema + registry format + scan
- [<] Add IPC server in orchestrator to reply to list-plugs, install, upgrade
- [<] Wire TS control harness to actual IPC responses
- [<] Define instance config model separate from install list

## Codex environment note
- [i] In the Codex sandbox, Python `py_compile` cannot write `__pycache__` in-repo (permission denied)
- [i] Workaround: set `PYTHONPYCACHEPREFIX=$env:TEMP` (or run with no bytecode in temp)
