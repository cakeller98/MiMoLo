# MiMoLo Agent Protocol Specification (formerly Agent)

> **Protocol Version:** 0.3  
> **Status:** Current (since MiMoLo v0.3.0)  
> **Last Updated:** November 2025  
> **Schema:** `mimolo-agent-schema.json`

---

## 1. Overview

**MiMoLo-LSP-lite** defines the lightweight, language-agnostic communication protocol between the **MiMoLo Orchestrator** (collector) and its **Agent** subprocesses (formerly Agent).

It provides:

- A **single, versioned message envelope** shared by all agents.  
- A **handshake phase** for version and capability negotiation.  
- A **minimal schema** for structured JSON validation.  
- A **stable foundation** for cross-language plugin development and future protocol evolution.

Agents communicate via **Agent JLP**: JSON Lines over stdin/stdout.  
Each line is a complete, self-contained JSON object.

---

## 2. Transport Rules

| Rule                       | Description                                                                      |
| -------------------------- | -------------------------------------------------------------------------------- |
| **Transport**              | UTF-8 text, JSON object per line (`\n` delimited).                               |
| **Direction**              | Bidirectional: Orchestrator ⇄ Agent.                                             |
| **Initiation**             | Collector starts each agent as a subprocess and waits for a `handshake` message. |
| **Validation**             | Collector validates messages against `mimolo-agent-schema.json`.                 |
| **Compression / Encoding** | None (raw text).                                                                 |
| **Termination**            | Agent exits on `{"cmd":"shutdown"}` or end-of-input.                             |

---

## 3. Message Envelope (Agent → Collector)

All outbound messages share a common envelope.

### 3.1 Core Required Fields

| Field              | Type                  | Description                                                                |
| ------------------ | --------------------- | -------------------------------------------------------------------------- |
| `type`             | string                | Message category (`handshake`, `summary`, `heartbeat`, `status`, `error`). |
| `timestamp`        | string (ISO-8601 UTC) | When this message was emitted.                                             |
| `agent_id`         | string                | Unique runtime identifier for this instance.                               |
| `agent_label`      | string                | Logical plugin name (registered label).                                    |
| `protocol_version` | string                | Protocol version used (checked only at handshake).                         |
| `agent_version`    | string                | Agent implementation version.                                              |
| `data`             | object                | Plugin-defined payload. Structure varies per agent.                        |

### 3.2 Optional Common Fields

| Field     | Type   | Applies To        | Description                                             |
| --------- | ------ | ----------------- | ------------------------------------------------------- |
| `metrics` | object | `heartbeat`       | Lightweight runtime metrics (CPU, mem, queue, latency). |
| `health`  | string | `status`          | `"ok"`, `"degraded"`, `"overload"`, or `"failed"`.      |
| `message` | string | `status`, `error` | Human-readable diagnostic text.                         |

### 3.3 Example Envelopes

**Summary**
```json
{
  "type": "summary",
  "timestamp": "2025-11-07T10:12:05Z",
  "agent_id": "folderwatch-001",
  "agent_label": "folderwatch",
  "protocol_version": "0.3",
  "agent_version": "1.2.1",
  "data": {"folders": ["/tmp", "/home/user/projects"]}
}
```

**Heartbeat**
```json
{
  "type": "heartbeat",
  "timestamp": "2025-11-07T10:12:10Z",
  "agent_id": "folderwatch-001",
  "agent_label": "folderwatch",
  "protocol_version": "0.3",
  "agent_version": "1.2.1",
  "data": {},
  "metrics": {"cpu": 0.03, "mem": 42.1, "latency_ms": 9.2}
}
```

**Error**
```json
{
  "type": "error",
  "timestamp": "2025-11-07T10:15:03Z",
  "agent_id": "folderwatch-001",
  "agent_label": "folderwatch",
  "protocol_version": "0.3",
  "agent_version": "1.2.1",
  "data": {},
  "message": "Permission denied while scanning /root"
}
```

---

## 4. Handshake (Initialization)

### 4.1 Purpose

Executed once immediately after the agent process starts.  
Used to verify compatibility and record version metadata.

### 4.2 Handshake Message

```json
{
  "type": "handshake",
  "timestamp": "2025-11-07T10:00:00Z",
  "agent_id": "folderwatch-001",
  "agent_label": "folderwatch",
  "protocol_version": "0.3",
  "agent_version": "1.2.1",
  "min_app_version": "0.3.0",
  "capabilities": ["summary", "heartbeat", "status", "error"],
  "data": {}
}
```

### 4.3 Collector Response

```json
{
  "cmd": "ack",
  "app_version": "0.3.5",
  "protocol_version": "0.3",
  "accepted": true,
  "message": "Registration complete"
}
```

If versions are incompatible, the collector responds with:

```json
{"cmd": "reject", "reason": "protocol_version_mismatch"}
```

After a successful handshake, no further version negotiation occurs during runtime.

---

## 5. Command Envelope (Collector → Agent)

Commands from the collector are simple one-object JSON messages.

| Field  | Type              | Description                                                    |
| ------ | ----------------- | -------------------------------------------------------------- |
| `cmd`  | string            | Command verb (`flush`, `stop`, `shutdown`, `status`, `sequence`, `ack`, `reject`). |
| `args` | object (optional) | Additional command parameters.                                 |
| `id`   | string (optional) | For correlation if acknowledgments are used.                   |

### 5.1 Examples

```json
{"cmd":"flush"}
{"cmd":"stop"}
{"cmd":"shutdown"}
{"cmd":"status"}
{"cmd":"sequence","sequence":["stop","flush","shutdown"]}
```

Agents must respond to `flush` by emitting a `summary` message, and must exit gracefully on `shutdown`.
Agents must honor `sequence` commands by executing the listed commands in-order.
When `stop` or `flush` appears in a sequence, agents must ACK those commands in-order.

---

## 6. Validation Schema (`mimolo-agent-schema.json`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://mimolo.io/schema/mimolo-agent-schema.json",
  "title": "MiMoLo Agent Protocol (v0.3)",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "type",
    "timestamp",
    "agent_id",
    "agent_label",
    "protocol_version",
    "agent_version",
    "data"
  ],
  "properties": {
    "type": {
      "type": "string",
      "enum": ["handshake", "summary", "heartbeat", "status", "error"]
    },
    "timestamp": {"type": "string", "format": "date-time"},
    "agent_id": {"type": "string"},
    "agent_label": {"type": "string"},
    "protocol_version": {"type": "string"},
    "agent_version": {"type": "string"},
    "data": {"type": "object", "additionalProperties": true},
    "metrics": {
      "type": "object",
      "properties": {
        "cpu": {"type": "number", "minimum": 0},
        "mem": {"type": "number", "minimum": 0},
        "queue": {"type": "integer", "minimum": 0},
        "latency_ms": {"type": "number", "minimum": 0}
      },
      "additionalProperties": true
    },
    "health": {
      "type": "string",
      "enum": ["ok", "degraded", "overload", "failed"]
    },
    "message": {"type": "string"},
    "min_app_version": {"type": "string"},
    "capabilities": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "allOf": [
    {
      "if": {"properties": {"type": {"const": "handshake"}}},
      "then": {
        "required": ["min_app_version", "capabilities"]
      }
    },
    {
      "if": {"properties": {"type": {"const": "error"}}},
      "then": {"required": ["message"]}
    }
  ]
}
```

---

## 7. Versioning & Evolution Policy

- The protocol version (`protocol_version`) changes **only** when message shapes change.  
- Minor additions to optional fields do **not** increment major version.  
- The orchestrator validates protocol version only once (during handshake).  
- Every message still carries `protocol_version` and `agent_version` for offline audit and compatibility checking.

Example version timeline:

| Version | Change                                  | Backward Compatibility |
| ------- | --------------------------------------- | ---------------------- |
| `0.3`   | Initial asynchronous Agent schema | —                      |
| `0.4`   | Adds `trace_id` optional field          | backward-compatible    |
| `1.0`   | Structural change to message envelope   | breaking change        |

---

## 8. Minimal Runtime Behavior Summary

| Phase                 | Agent Action                                          | Collector Expectation         |
| --------------------- | ----------------------------------------------------- | ----------------------------- |
| Startup               | Send `handshake`                                      | Validate and `ack`            |
| Normal                | Emit `summary` and `heartbeat` messages as configured | Log and segment data          |
| Warning / Degradation | Send `status` or `error` messages                     | Record + optional alert       |
| Shutdown              | Clean exit on `{"cmd":"shutdown"}`                    | Flush logs and remove process |

---

## 9. Schema Usage in Toolchains

| Purpose                    | Integration                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| **Runtime validation**     | `jsonschema` (Python), `ajv` (Node.js), or `quicktype` (Go/Rust).                          |
| **Typed model generation** | Generate Pydantic models for validation and serialization.                                 |
| **Offline analysis**       | Tools can read historical logs, inspect `protocol_version`, and skip unsupported versions. |

---

## 10. Summary

The **MiMoLo-LSP-lite Protocol v0.3** provides:

- A stable, minimal JSON envelope for agent communication.  
- Strict top-level validation with freedom inside each plugin’s `data` payload.  
- Clean version negotiation and extensibility.  
- Guaranteed compatibility across languages and future MiMoLo releases.

This schema is the authoritative reference for all Agent implementations.

## Plugin UUID Migration Rule (Future)

If `plugin_uuid` is introduced later, older logs will not be rewritten.
Instead, the orchestrator/dashboard will apply this mapping at read time:

- Maintain a persistent mapping: `plugin_id -> plugin_uuid`
- If a log entry is missing `plugin_uuid`, inject from the mapping
- If no mapping exists for the `plugin_id`, generate a UUID once and persist it

This keeps old logs compatible while ensuring stable UUIDs going forward.

