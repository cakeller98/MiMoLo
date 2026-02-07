> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

## Data Schema and Message Types

All MiMoLo communication occurs through **newline-delimited JSON objects** transmitted over each Agent’s standard input and output streams.  
Every message includes a `"type"` or `"cmd"` field that identifies its semantic role. These structures define the canonical vocabulary used between Agents, the Orchestrator, and—indirectly—the Control.

---

### Heartbeat
Periodic signal from a Agent indicating it is alive and within resource limits.

```json
{
  "type": "heartbeat",
  "timestamp": "2025-11-07T09:00:00Z",
  "metrics": {"cpu": 0.008, "mem_mb": 7.2, "queue": 1}
}
```

**Purpose:** Maintain continuous visibility into agent health, latency, and load.  
**Frequency:** Regular interval (typically every 5–15 seconds).  

---

### Summary
Aggregated result emitted by a Agent representing condensed observations since the last flush or time window.

```json
{
  "type": "summary",
  "timestamp": "2025-11-07T09:00:15Z",
  "data": {"folders": ["/projects/demo", "/assets/scenes"]},
  "metrics": {"samples": 152, "interval_s": 15.0}
}
```

**Purpose:** Transmit meaningful, low-frequency summaries instead of raw samples.  
**Frequency:** Event-driven or on orchestrator `flush` command.  

---

### Status
Describes the agent’s current operating state and environment health.

```json
{
  "type": "status",
  "health": "healthy",
  "uptime_s": 86400,
  "details": {"threads": 2, "mode": "normal", "poll_interval_s": 15.0}
}
```

**Purpose:** Provide current configuration and state snapshot during handshake or on request.  
**Frequency:** On startup, on demand, or when state changes materially.  

---

### Error
Reports a recoverable or fatal agent-side failure.  
Agents must use this instead of printing diagnostic text.

```json
{
  "type": "error",
  "message": "permission denied while reading /projects/demo",
  "severity": "recoverable",
  "context": {"path": "/projects/demo"}
}
```

**Purpose:** Notify orchestrator of operational faults without terminating the agent.  
**Frequency:** As needed when internal exceptions occur.  

---

### Command
Instruction sent from the Orchestrator to a Agent via Agent JLP (stdin).  
Commands control lifecycle, flushing, and health checks.

```json
{
  "cmd": "flush",
  "params": {"reason": "control_request"}
}
```

**Purpose:** Direct agent actions while maintaining full isolation.  
**Frequency:** On demand or at lifecycle transitions.  

---

### Message Type Summary

| Message Type | Direction | Required Fields | Optional Fields | Purpose |
|---------------|------------|----------------|-----------------|----------|
| `heartbeat` | Agent → Orchestrator | `type`, `timestamp` | `metrics` | Health ping / keep-alive |
| `summary` | Agent → Orchestrator | `type`, `data` | `timestamp`, `metrics` | Aggregated data flush |
| `status` | Agent → Orchestrator | `type`, `health` | `details`, `uptime_s` | Configuration and runtime state |
| `error` | Agent → Orchestrator | `type`, `message` | `severity`, `context` | Report recoverable failures |
| `command` | Orchestrator → Agent | `cmd` | `params` | Control or shutdown request |

---

**Extensibility**
- Additional message types (`metric`, `log`, `custom`, etc.) may be defined as long as they include either `"type"` or `"cmd"`.  
- All new types must remain valid JSON objects terminated by a newline (`\n`).  
- Unknown types are ignored by the Orchestrator but logged for traceability.  
- This schema is versioned at the protocol level; backward-compatible fields should use additive expansion rather than mutation.

### ...next [[5_Lifecycle_and_Control_Flow]]
