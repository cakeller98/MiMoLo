# Protocol Implementation Status

Date: 2026-02-08
Rule: Code is ground truth when docs and code differ.

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
- AF_UNIX socket, JSON lines request/response.

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
- Source: `mimolo/core/runtime.py`

Control proto client usage:
- Implemented in `mimolo/control_proto/src/main.ts`

## 3. Known Gaps vs Spec Intent

1. Handshake negotiation:
- Handshake messages exist, but explicit runtime accept/reject negotiation flow is not enforced in orchestrator loop.

2. Status handling:
- `status` type exists in protocol model, but normal runtime routing does not currently process it beyond shutdown path timing updates.

3. Schema file:
- `mimolo-agent-schema.json` is referenced in docs but is not present in repository.

4. Unknown custom message types:
- Parser currently validates `type` against known enum, so arbitrary new message types are not accepted by default.

## 4. Storage Contract Alignment

Implemented now:
- Agent processes receive `MIMOLO_DATA_DIR` environment variable.

Planned:
- Standard artifact index schema.
- Archive manifest + restore protocol.
- Explicit user-driven archive/purge control flow in Control.
- Widget render/action bridge (`request_widget_render` over IPC and `widget_render` over Agent JLP), with Operations-side sanitization and class allowlist enforcement.
