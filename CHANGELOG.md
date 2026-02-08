# Changelog

All notable changes to this project will be documented in this file.
Documentation-only history is tracked separately in `developer_docs/CHANGELOG.md`.

## 2026-02-08

### Added
- Added Control proto widget bridge handlers (`mml:get-widget-manifest`, `mml:request-widget-render`) to forward widget requests from renderer to Operations IPC.
- Added per-agent widget canvas panel controls in Control proto cards:
  - manual `update` button for on-demand manifest/render requests
  - `pause`/`play` toggle for per-widget auto-refresh
- Added periodic widget polling in Control proto that requests:
  - `get_widget_manifest`
  - `request_widget_render`
  for each active instance.
- Added runnable plugin scaffolds under `mimolo/agents/` for:
  - `client_folder_activity` (folder metadata polling with bounded summary payloads)
  - `screen_tracker` (artifact-reference screenshot summaries)
- Added plugin build manifests for `client_folder_activity` and `screen_tracker`.
- Added these plugin entries to `mimolo/agents/sources.json` so local source inventory includes both.
- Added persistent IPC transport in `mimolo/control_proto`:
  - one long-lived AF_UNIX socket connection to Operations
  - bounded queued request dispatch with timeout handling and reconnect-safe teardown
  - request-id tagging on control requests for stable response correlation
- Added runtime IPC response request-id echo support in `mimolo/core/runtime.py` for persistent-client correlation.
- Added runtime IPC connection-serving threads so one long-lived client no longer blocks all other IPC clients.

### Changed
- Updated Control proto agent cards to display widget-manifest status and widget-render placeholder state from Operations responses.
- Kept widget canvas rendering security-first: renderer currently shows validated placeholder state text, not direct fragment injection.
- Reduced widget polling chatter by caching manifest fetches per instance and increasing auto-refresh interval.
- Removed redundant renderer-side `initial-state` polling loop; renderer now uses event-driven updates after initial hydrate.

## 2026-01-31

### Breaking
- Renamed agent paths and identifiers from `field_agents` to `agents`. The new codebase is incompatible with the old `field_agents` layout.

## 2026-02-03

### Added
- Added `--verify-existing` and `--force-pack` options to `pack-agent` for repo collision handling.
- Added `--help` output and CLI flag summary for `pack-agent`.

### Changed
- `pack-agent` now merges updates into `build-manifest.toml` instead of overwriting it.
- `pack-agent` now reports repo/version conflicts with explicit context and preserves non-conflicting builds.

## 2026-02-06

### Added
- Added canonical launcher scripts `mml.sh` and `mml.ps1` to standardize `MIMOLO_IPC_PATH` and launch Operations/Control/prototype targets.
- Added `mml.toml` for launcher defaults (no-verb command, default stack, IPC path, socket wait timeout).
- Added a minimal runtime IPC command server (AF_UNIX) that responds to `ping` and `get_registered_plugins`.
- Added Operations IPC commands `get_agent_states`, `start_agent`, `stop_agent`, and `restart_agent` for per-agent Control actions.
- Added runtime lifecycle state tracking for configured agents (`running`, `shutting-down`, `inactive`, `error`) with detail strings for UI instrumentation.
- Added queued control-action processing in runtime so IPC-triggered agent actions execute safely on the orchestrator loop.
- Added a right-side scrollable agent control panel in `mimolo/control_proto` with per-agent cards and `start/stop/restart` buttons.
- Added lifecycle indicator lights in `mimolo/control_proto` with state mapping: green `running`, yellow `shutting-down`, dark-gray `inactive`, red `error`.
- Added per-agent TX/RX indicator pulses in `mimolo/control_proto` (green on send, red on receive, dark-gray neutral idle).
- Added agent template discovery in Operations runtime to support instance creation from available agent plugins.
- Added Operations IPC commands for instance management: `list_agent_templates`, `get_agent_instances`, `add_agent_instance`, `duplicate_agent_instance`, `remove_agent_instance`, and `update_agent_instance`.
- Added persistent config-save support in core config utilities via `save_config(...)`.
- Added Control proto panel actions for agent-instance add, duplicate, remove, and configure workflows.
- Added per-card top-right icon controls in Control proto: duplicate (`⧉`), delete (`−`), configure (`⚙`).
- Added non-breaking widget IPC command stubs in Operations runtime for `get_widget_manifest`, `request_widget_render`, and `dispatch_widget_action` returning structured `not_implemented_yet` responses.
- Added runtime IPC stub tests in `tests/test_runtime_widget_ipc_stubs.py` to lock stable command names and response shape for early Control integration.

### Changed
- Archived legacy `start_*.sh` and `start_*.ps1` scripts under `archive/start_scripts/`.
- Improved launcher readiness checks to require an IPC `ping` response before launching proto, reducing startup `ECONNREFUSED` races.
- Converted `mimolo/control_proto` into an Electron prototype window that streams Operations output from `MIMOLO_OPS_LOG_PATH` and polls IPC status.
- Updated `mml.sh` / `mml.ps1` / `mml.toml` to manage `MIMOLO_OPS_LOG_PATH` and run Operations with log redirection for proto mode.
- Renamed the Electron Control app package path from `mimolo-dash` to `mimolo-control` and aligned package metadata.
- Renamed the TypeScript IPC prototype package path from `mimolo/dashboard` to `mimolo/control_proto`.
- Updated IPC prototype package metadata from `mimolo-dashboard-proto` to `mimolo-control-proto`.
- Added local TypeScript shim declarations in `mimolo-control` and `mimolo/control_proto` so early bootstrap builds pass before full runtime dependencies are installed.
- Removed deprecated `enableRemoteModule` BrowserWindow flag for Electron v40 compatibility.
- Updated `mimolo.toml` agent launch args to `poetry run python <agent_script>` ordering to avoid immediate exit-code `1` on startup.
- Updated `mimolo/control_proto` window layout from single-pane log view to split-pane log + control instrumentation panel.
- Updated `get_registered_plugins` IPC response to include `agent_states` snapshots for Control panel hydration.
- Updated control-proto Electron shim typings so IPC handlers/invokes accept payload arguments.
- Updated runtime startup to accept config path context so IPC-driven instance/config mutations persist to the active Operations config file.
- Updated Control proto to poll and render full agent instance snapshots (state/detail/config/template) instead of state-only data.
