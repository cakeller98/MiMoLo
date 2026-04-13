# Protocol Implementation Status

Date: 2026-04-12
Rule: pause on mismatch, discuss, and update docs/code together until aligned.

## 1. Agent <-> Operations (Agent JLP)

Transport:
- JSON lines over stdin/stdout.

Implemented message models:
- `handshake`, `summary`, `heartbeat`, `status`, `error`, `log`, `ack`
- Source: `mimolo/core/protocol.py`

Implemented runtime handling (normal loop):
- `heartbeat`, `summary`, `log`, `error`, `ack`, `status`
- Source:
  - `mimolo/core/runtime.py`
  - `mimolo/core/runtime_agent_events.py`

Implemented command handling in BaseAgent:
- `flush`, `stop`, `start`, `shutdown`, `sequence`, `status`
- ACK on `stop`, `flush`, and `shutdown`
- Source: `mimolo/agents/base_agent.py`

## 2. Operations <-> Control (IPC socket)

Transport:
- AF_UNIX socket with JSON-line request/response payloads when supported.
- Slowpoke file-backed fallback IPC on Windows/non-AF_UNIX builds.

Implemented commands:
- `ping`
- `get_registered_plugins`
- `list_agent_templates`
- `get_agent_instances`
- `get_agent_states`
- `start_agent`
- `stop_agent`
- `restart_agent`
- `add_agent_instance`
- `duplicate_agent_instance`
- `remove_agent_instance`
- `update_agent_instance`
- `get_widget_manifest` (stub)
- `request_widget_render` (stub)
- `dispatch_widget_action` (stub)
- Source: `mimolo/core/runtime.py`

Server behavior:
- Accept loop plus per-client serving threads for socket mode.
- File-backed request/response directory polling for slowpoke mode.
- Source:
  - `mimolo/core/runtime_ipc_server.py`
  - `mimolo/core/ipc.py`
  - `mimolo/core/ipc_slowpoke.py`

## 3. Control Proto IPC Behavior (Current)

Implemented in Control proto:
- One persistent AF_UNIX client connection to Operations.
- Bounded queued request dispatch.
- Request timeout handling and reconnect-safe teardown.
- Request-id tagging (`request_id`) on requests.
- Explicit Operations lifecycle ownership via Control main process:
  - managed/unmanaged state
  - start/stop/restart
  - transitional `starting` / `stopping` states
  - stale-status recovery before refusing start
  - slowpoke-specific stop/start timing hardening

Correlation behavior:
- Runtime echoes non-empty `request_id` in IPC responses.
- Sources:
  - `mimolo/core/runtime.py`
  - `tests/test_runtime_widget_ipc_stubs.py`

## 4. Known Gaps vs Spec Intent

1. Handshake negotiation:
- Handshake messages exist, but explicit runtime accept/reject negotiation flow is not enforced in orchestrator loop.

2. Schema file:
- `mimolo-agent-schema.json` is referenced in docs but is not present in repository.

3. Widget render bridge:
- Runtime widget manifest/render support exists for:
  - `screen_tracker`
  - `client_folder_activity`
- `trail_tracker` widget manifest/render support is not implemented yet.
- Design lock for continuing implementation:
  - agents emit evidence/state payloads,
  - Operations transports/caches and exposes widget render requests,
  - Control performs final render/sanitization before display.

4. Trust policy enforcement:
- Signed/allowlisted release policy is documented, but end-to-end enforcement coverage (install-time and launch-time) is still in progress.
- Source policy: `developer_docs/agent_dev/PLUGIN_TRUST_AND_SIGNING_POLICY.md`

## 5. Storage Contract Alignment

Implemented now:
- Agent processes receive `MIMOLO_DATA_DIR` environment variable.
- Operations log path and runtime IPC paths are now launcher-managed under
  AppData roots on Windows instead of `%TEMP%`.

Implemented now (runtime/control stability):
- Structured per-agent shutdown diagnostics are written during orchestrator
  shutdown sequencing.
- Runtime monitor settings can be changed live, including
  `console_verbosity`, without restarting Operations.
- Separate-terminal agent tail windows are now tracked and closed with agent
  lifecycle.
- Core runtime console writes now route through Unicode-safe printing logic to
  reduce Windows console crashes.

Planned:
- Standard artifact index schema.
- Archive manifest + restore protocol.
- Explicit user-driven archive/purge control flow in Control.
- Full widget render/action bridge (`request_widget_render` over IPC and render/action roundtrip with agent instances), including:
  - remaining `trail_tracker` widget support
  - operations-side transport/cache bounds enforcement
  - control-side sanitizer/allowlist policy
