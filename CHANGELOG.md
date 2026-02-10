# Changelog

All notable changes to this project will be documented in this file.
Documentation-only history is tracked separately in `developer_docs/CHANGELOG.md`.

## 2026-02-10

### Changed
- Refactored Control proto maintainability boundaries without changing behavior:
  - extracted shared runtime/control type contracts into `mimolo/control_proto/src/types.ts`
  - extracted control timing TOML parsing/normalization into `mimolo/control_proto/src/control_timing.ts`
  - extracted IPC payload and monitor/loop utility functions into `mimolo/control_proto/src/control_proto_utils.ts`
  - extracted command wrapper helpers into `mimolo/control_proto/src/control_command_wrappers.ts`
  - extracted renderer HTML/template payload from `main.ts` into `mimolo/control_proto/src/ui_html.ts`
  - `mimolo/control_proto/src/main.ts` now acts as orchestration glue across these modules.
- Continued Control proto structural decomposition by moving additional concerns out of `main.ts`:
  - extracted persistent Operations socket transport, queueing, timeout, and reconnect backoff into `mimolo/control_proto/src/control_persistent_ipc.ts`
  - extracted Operations process lifecycle ownership (`start/stop/restart`, managed/unmanaged, graceful-stop/fallback-kill) into `mimolo/control_proto/src/control_operations.ts`
  - extracted all Electron IPC handler wiring/validation into `mimolo/control_proto/src/control_ipc_handlers.ts`
  - reduced `mimolo/control_proto/src/main.ts` from ~1700 lines to ~800 lines so it primarily composes state publishing, polling orchestration, and app bootstrap.
- Refactored Operations runtime maintainability boundaries without changing behavior:
  - extracted IPC command routing from `mimolo/core/runtime.py` into `mimolo/core/runtime_ipc_commands.py`
  - extracted IPC socket server plumbing from `mimolo/core/runtime.py` into `mimolo/core/runtime_ipc_server.py`
  - extracted agent summary/heartbeat/log event handling from `mimolo/core/runtime.py` into `mimolo/core/runtime_agent_events.py`
  - extracted screen-tracker widget rendering helpers from `mimolo/core/runtime.py` into `mimolo/core/runtime_widget_support.py`
  - extracted monitor settings update/persist helper from `mimolo/core/runtime.py` into `mimolo/core/runtime_monitor_settings.py`
  - extracted flush/segment/shutdown lifecycle orchestration from `mimolo/core/runtime.py` into `mimolo/core/runtime_shutdown.py`
  - `Runtime` methods now delegate to focused helper modules while preserving existing call sites and contracts.

## 2026-02-09

### Added
- Added a validated `[control]` timing configuration surface in `mimolo.toml` (via `ControlConfig`) for Control-proto cadence/retry behavior:
  - connected/disconnected status polling
  - connected/disconnected instance polling
  - connected/disconnected log polling
  - reconnect backoff (initial/extended/escalation threshold)
  - status repeat throttling
  - widget auto tick/default refresh
  - IPC request timeout and template cache TTL
  - indicator fade step + toast duration
  - operations stop/disconnect wait windows.
- Added runtime monitor settings IPC commands in Operations:
  - `get_monitor_settings`
  - `update_monitor_settings`
  with strict key validation, runtime rollback-on-failure semantics, and config persistence.
- Added Control proto monitor settings UX:
  - monitor summary row in header
  - `Monitor` button modal to edit global `poll_tick_s`, `cooldown_seconds`, and `console_verbosity`.
- Added runtime widget manifest/render support for `screen_tracker`:
  - real `get_widget_manifest` capabilities payload
  - real `request_widget_render` HTML payload for latest thumbnail or waiting-state text
  - `dispatch_widget_action` support for `refresh`.
- Added safe HTML fragment rendering in Control widget canvas using a strict allowlist sanitizer.
- Added screen tracker agent enhancements:
  - real macOS `app_window` capture path (`active_window` alias normalized)
  - `target_app` and `target_window_title_contains` targeting options
  - configurable `thumbnail_width_px` / `thumbnail_height_px`
  - deterministic SVG placeholder artifact when target window/app is unavailable.
- Added/expanded tests:
  - `tests/test_screen_tracker_agent.py`
  - `tests/test_runtime_monitor_settings_ipc.py`
  - `tests/test_runtime_widget_ipc_stubs.py` updated for live `screen_tracker` widget behavior.
- Added Operations singleton startup lock support to prevent duplicate runtime launches per data root.
- Added canonical `mimolo ops` command with backward-compatible hidden `monitor` alias.
- Added launcher process diagnostics commands:
  - `./mml.sh ps` / `./mml.sh processes`
  - `.\mml.ps1 ps` / `.\mml.ps1 processes`
- Added targeted lifecycle tests for operations singleton lock behavior:
  - `tests/test_ops_singleton.py`
  - plus orchestrator control IPC tests in `tests/test_runtime_orchestrator_control_ipc.py`.

### Changed
- Updated Control proto reconnect behavior to be policy-driven from `[control]` settings instead of hard-coded constants.
- Updated Control proto disconnected UX semantics:
  - repeated identical disconnected status updates are throttled.
  - reconnect attempts back off and escalate per config policy.
  - disconnected `ipc_connect_backoff` status is normalized to waiting semantics.
- Updated Control proto interactivity gating:
  - per-agent action buttons and widget controls are disabled when Operations is unavailable.
  - top-level Add/Monitor/Install buttons are disabled when Operations is unavailable.
  - disconnected card lifecycle indicators normalize to inactive instead of stale `shutting-down`.
- Updated runtime monitor-settings snapshot payload to include `control` timing settings for Control consumption.
- Updated runtime IPC socket startup robustness so a socket chmod failure no longer aborts the IPC server startup path.
- Updated Control background refresh loops to derive cadence from runtime monitor settings (`poll_tick_s`) instead of hardcoded intervals.
- Updated widget auto-refresh interval resolution to respect effective heartbeat cadence plus global monitor floor.
- Updated `screen_tracker` artifact semantics to include both full and thumbnail references with lightweight metadata payloads.
- Updated `screen_tracker` plugin metadata version to `0.2.0`:
  - `mimolo/agents/screen_tracker/build-manifest.toml`
  - `mimolo/agents/sources.json`.
- Updated screen widget image delivery to use embedded `data:image/...;base64,...` URIs instead of `file://` links, fixing renderer local-resource blocking under `data:` page origin.

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
- Added filesystem-ground-truth plugin installation store support in `mimolo/core/plugin_store.py` under:
  - `<MIMOLO_DATA_DIR>/operations/plugins/agents/<plugin_id>/<version>/`
  - `<MIMOLO_DATA_DIR>/operations/plugins/reporters/<plugin_id>/<version>/`
  - `<MIMOLO_DATA_DIR>/operations/plugins/widgets/<plugin_id>/<version>/`
- Added Operations IPC commands for plugin deployment lifecycle:
  - `list_installed_plugins`
  - `inspect_plugin_archive`
  - `install_plugin`
  - `upgrade_plugin`
- Added Control proto plugin-install UX:
  - `Install` button modal with archive inspection + class/action selection
  - drag-and-drop `.zip` archive support
  - native file picker integration for archive selection
- Added plugin install/upgrade tests and runtime IPC tests:
  - `tests/test_plugin_store.py`
  - `tests/test_runtime_plugin_install_ipc.py`
  - `tests/test_runtime_template_discovery.py`
- Added portable runtime path helpers in `mimolo/common/paths.py`:
  - `MIMOLO_DATA_DIR` override support
  - `MIMOLO_BIN_DIR` override support (`get_mimolo_bin_dir`)
- Added portable deployment utility `scripts/deploy_portable.sh` that:
  - incrementally syncs runtime artifacts into portable `bin/`
  - writes `deploy-manifest.json`
  - seeds default agents into portable plugin storage
- Added cross-platform PowerShell deploy utility `scripts/deploy_portable.ps1`:
  - compatible with `pwsh` on macOS/Windows/Linux
  - same incremental sync + default agent seeding behavior as shell deploy script
- Added launcher cache/reset controls in both `mml.sh` and `mml.ps1`:
  - global `--no-cache` preflight (cleanup + prepare)
  - alias `--rebuild-dist`
  - explicit `cleanup` command
  - explicit `prepare` command in PowerShell launcher
- Added macOS bundle utility scripts for dev packaging:
  - `scripts/bundle_app.sh` (primary implementation)
  - `scripts/bundle_app.ps1` (PowerShell wrapper)
- Added `bundle-app` launcher verb in `mml.sh` and `mml.ps1` to dispatch to bundle utility scripts.
- Added `mml.toml` bundle defaults for bundle generation:
  - `bundle_target_default`
  - `bundle_out_dir`
  - `bundle_version_default`
  - `bundle_app_name_proto`
  - `bundle_app_name_control`
  - `bundle_bundle_id_proto`
  - `bundle_bundle_id_control`
  - `bundle_dev_mode_default`
- Added launcher self-repair behavior for Electron startup:
  - auto-install Electron runtime via `npm ci` in `mimolo-control` when missing
  - auto-build missing `dist/main.js` for `mimolo-control` and `mimolo/control_proto`

### Changed
- Updated Control proto agent cards to display widget-manifest status and widget-render placeholder state from Operations responses.
- Kept widget canvas rendering security-first: renderer currently shows validated placeholder state text, not direct fragment injection.
- Reduced widget polling chatter by caching manifest fetches per instance and increasing auto-refresh interval.
- Removed redundant renderer-side `initial-state` polling loop; renderer now uses event-driven updates after initial hydrate.
- Clarified runtime plugin deployment semantics in responses: filesystem is ground truth and registry is cache-only metadata.
- Updated runtime agent template discovery to include installed agent plugins from app-data storage.
- Updated agent process script-path resolution to allow only trusted roots:
  - workspace `mimolo/agents`
  - installed plugins under `<MIMOLO_DATA_DIR>/operations/plugins/agents`
- Updated CLI monitor command to honor env overrides for monitor paths:
  - `MIMOLO_MONITOR_LOG_DIR`
  - `MIMOLO_MONITOR_JOURNAL_DIR`
  - `MIMOLO_MONITOR_CACHE_DIR`
- Updated `mml.sh` portable launcher behavior:
  - always sets `MIMOLO_DATA_DIR` and `MIMOLO_BIN_DIR`
  - seeds and uses `MIMOLO_RUNTIME_CONFIG_PATH` unless `--config` is passed explicitly
  - routes IPC path, operations stream log, and monitor log/journal/cache directories into portable data root
  - adds `prepare` command and one-time auto-prepare when portable deploy manifest is missing
- Updated portable deploy defaults to seed only baseline agents:
  - `agent_template`
  - `agent_example`
- Updated Control proto with non-blocking installer status toasts for passive drag/drop install flow.
- Updated launcher cleanup logic to avoid deleting `node_modules/**` artifacts while still clearing repo build caches.
- Updated default non-Windows IPC socket behavior to use short `/tmp/mimolo/operations.sock` paths with length-guard fallback to avoid AF_UNIX path-length failures in portable mode.
- Updated Control proto install UX policy enforcement:
  - `+ Add` remains the default instance-management flow driven by template registry ground truth.
  - plugin zip install UI/drag-drop path is now disabled by default and gated behind developer mode (`MIMOLO_CONTROL_DEV_MODE=1`).
  - added explicit developer-mode warning that signature allowlist enforcement is not yet implemented for sideload flow.
- Updated launchers `mml.sh` and `mml.ps1` with global `--dev` flag to propagate Control dev-install mode without changing default `all-proto` startup behavior.
- Updated portable deploy utilities to sync bundle scripts into portable bin (`temp_debug/bin/scripts/`) so `bundle-app` remains available from portable launchers.
- Updated launcher `help` output to include a final `Defaults from mml.toml` section for fast visibility of active launcher/bundle defaults.
- Updated `scripts/bundle_app.sh` to read bundle defaults from `mml.toml` when corresponding CLI options are not provided.
- Updated Control proto status handling so missing/uninitialized ops log files no longer force transport status to `disconnected`; IPC connectivity remains the source of truth.
- Updated Control proto startup to initialize the configured ops log path directory/file when possible, and report log-read issues in the stream instead of masking IPC status.
- Updated `bundle-app` output to print a shell-safe quoted `open "<path>.app"` launch command for app names that include spaces/parentheses.
- Updated Control proto header with global Operations controls:
  - `Start Ops`
  - `Stop Ops`
  - `Restart Ops`
  with process-state display (`running/stopped/starting/stopping/error`) and managed/unmanaged ownership detail.
- Updated Control proto to support app-owned Operations process lifecycle:
  - start/stop/restart handlers in Electron main process (`mml:ops-control`)
  - managed process stdout/stderr append into configured ops log path for stream viewer continuity
  - safe refusal to kill externally managed Operations instances.
- Updated Control proto IPC indicator semantics to be transport-truthful and role-separated:
  - interactive transport indicators are split into separate `tx` and `rx` lights (global and per-instance)
  - `tx`/`rx` lights now pulse only from actual Operations socket write/response events
  - `bg` is now a static communication-state indicator (not an activity pulse):
    - green-outline = online
    - red solid = offline/error
    - dark gray = shutdown/not managed
  - renderer-side pre/post invoke flashing was removed to avoid non-transport “fake” pulses
  - indicator pulses now use a fixed 4-step fade (`0.9 -> 0.6 -> 0.3 -> 0.1`, 200ms per step) with non-blocking retrigger semantics (no queued blink backlog).
  - widget auto-refresh is now state-aware and interval-aware:
    - automatic widget requests run only for `running` instances
    - cadence derives from each instance `heartbeat_interval_s` (fallback: 15s)
    - stopped/inactive/error instances no longer generate label-scoped auto-refresh traffic.
- Updated launcher/bundle environment propagation to include `MIMOLO_REPO_ROOT`, improving in-app Operations start reliability from bundled app launches.
- Updated monitor timing units to seconds-only with immediate hard cut:
  - renamed config key `monitor.poll_tick_ms` -> `monitor.poll_tick_s`
  - runtime loop now sleeps on `poll_tick_s` directly
  - default project config and getting-started examples now use seconds
  - removed test references to millisecond poll-tick naming.
- Updated launcher default Operations invocations from `mimolo.cli monitor` to `mimolo.cli ops` for clearer process identity.
- Updated Control proto Operations control behavior:
  - stop/restart now attempts orchestrator stop over IPC when connected to an external/unmanaged Operations instance.
  - status transitions preserve explicit `external_stop_requested` -> `stopped_via_ipc` semantics instead of misleading unmanaged dead-end states.

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
