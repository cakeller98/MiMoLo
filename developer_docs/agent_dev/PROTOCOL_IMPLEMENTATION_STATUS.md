# Protocol Implementation Status

Date: 2026-02-08
Rule: code is ground truth when docs and code differ.

## 1. Agent <-> Operations (Agent JLP)

Transport:
- JSON lines over stdin/stdout.

Implemented message models:
- `handshake`, `summary`, `heartbeat`, `status`, `error`, `log`, `ack`
- Source: `mimolo/core/protocol.py`

Implemented runtime handling (normal loop):
- `heartbeat`, `summary`, `log`, `error`
- Source: `mimolo/core/runtime.py`

Implemented command handling in BaseAgent:
- `flush`, `stop`, `start`, `shutdown`, `sequence`
- ACK on `stop` and `flush`
- Source: `mimolo/agents/base_agent.py`

## 2. Operations <-> Control (IPC socket)

Transport:
- AF_UNIX socket with JSON-line request/response payloads.

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
- Accept loop plus per-client serving threads.
- Source: `mimolo/core/runtime.py`

## 3. Control Proto IPC Behavior (Current)

Implemented in `mimolo/control_proto/src/main.ts`:
- One persistent AF_UNIX client connection to Operations.
- Bounded queued request dispatch.
- Request timeout handling and reconnect-safe teardown.
- Request-id tagging (`request_id`) on requests.

Correlation behavior:
- Runtime echoes non-empty `request_id` in IPC responses.
- Sources:
  - `mimolo/core/runtime.py`
  - `tests/test_runtime_widget_ipc_stubs.py`

## 4. Known Gaps vs Spec Intent

1. Handshake negotiation:
- Handshake messages exist, but explicit runtime accept/reject negotiation flow is not enforced in orchestrator loop.

2. Status handling:
- `status` type exists in protocol model, but normal runtime routing does not currently process it as a first-class state update path.

3. Schema file:
- `mimolo-agent-schema.json` is referenced in docs but is not present in repository.

4. Widget render bridge:
- IPC widget command names and response shapes exist, but Operations does not yet complete the full agent-render bridge.

5. Trust policy enforcement:
- Signed/allowlisted release policy is documented, but end-to-end enforcement coverage (install-time and launch-time) is still in progress.
- Source policy: `developer_docs/agent_dev/PLUGIN_TRUST_AND_SIGNING_POLICY.md`

## 5. Storage Contract Alignment

Implemented now:
- Agent processes receive `MIMOLO_DATA_DIR` environment variable.

Planned:
- Standard artifact index schema.
- Archive manifest + restore protocol.
- Explicit user-driven archive/purge control flow in Control.
- Full widget render/action bridge (`request_widget_render` over IPC and render/action roundtrip with agent instances), including sanitization/allowlist policy.
