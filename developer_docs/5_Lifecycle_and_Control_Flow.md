## Lifecycle and Control Flow

MiMoLo operates as a continuous cooperative loop between the Orchestrator, its Agents, and the optional Dashboard.  
Each component participates in a predictable lifecycle: initialization, active monitoring, cooldown or idle periods, and graceful shutdown.  
The system is designed to remain resilient under partial failures, maintaining data integrity and stability at all times.

---

### 1. Startup
1. The Orchestrator loads configuration and initializes sinks.  
2. Agents are spawned as subprocesses with Agent JLP (stdin/stdout) communication channels.  
3. Each Agent performs self-checks, loads its configuration, and sends an initial `status` or `heartbeat` message to confirm readiness.  
4. The Orchestrator validates these messages, records agent identities, and begins the main monitoring loop.

```text
Orchestrator → (spawn agent)
Agent → {"type":"status","health":"initializing","details":{"pid":21345}}
Orchestrator → {"ack":"agent_registered","label":"folderwatch"}
```

---

### 2. Active Operation
1. Agents independently collect and aggregate local observations while consuming <0.1% instantaneous CPU and <0.01% sustained CPU over time.  
2. At defined intervals (typically 5–15 seconds), each Agent emits a `heartbeat` message reporting operational metrics and, when relevant, a `summary` containing condensed data.  
3. The Orchestrator continuously listens, validates message structure, and appends events to active segments.  
4. The Dashboard may query aggregated data or trigger orchestrator commands such as `flush` or `status`.  
5. When a `flush` command is issued, the Orchestrator relays it to the targeted agent, which emits a `summary` immediately.

```text
Agent → {"type":"heartbeat","timestamp":"2025-11-07T09:00:00Z"}
Agent → {"type":"summary","data":{"folders":["/project/demo"]}}
Dashboard → {"action":"flush","target":"folderwatch"}
Orchestrator → {"cmd":"flush"}
Agent → {"type":"summary","data":{"folders":["/project/demo"],"flush_reason":"manual"}}
```

---

### 3. Idle / Cooldown
When no resetting events or summaries are received within the configured cooldown window,  
the Orchestrator assumes activity has paused and finalizes the current segment.

1. The cooldown timer expires (e.g., 600 seconds).  
2. The Orchestrator aggregates buffered events into a segment record.  
3. The finalized segment is written to the configured sinks (JSONL, YAML, or Markdown).  
4. The system reverts to the IDLE state, awaiting new activity.

```text
Orchestrator → Segment close → Log sink (2025-11-07T09:10:00Z)
```

---

### 4. Error Handling
1. Agents encountering recoverable issues emit `error` messages describing context and severity.  
2. The Orchestrator logs the error and may issue diagnostic `status` requests or apply exponential backoff before resuming polling.  
3. Severe or repeated failures trigger isolation or restart of the affected agent.

```text
Agent → {"type":"error","message":"permission denied","severity":"recoverable"}
Orchestrator → {"cmd":"status"}
Agent → {"type":"status","health":"degraded","details":{"missing_paths":3}}
Orchestrator → logs event and applies backoff (30s → 60s → 120s)
```

---

### 5. Shutdown
1. The Orchestrator initiates a global stop sequence or receives a termination signal.  
2. It sends a `{"cmd":"shutdown"}` command to all active agents.  
3. Each Agent performs cleanup, emits a final `summary`, and exits cleanly.  
4. The Orchestrator collects any remaining data, closes all segments, and flushes all sinks.

```text
Orchestrator → {"cmd":"shutdown"}
Agent → {"type":"summary","data":{"folders":["/project/demo"],"state":"final"}}
Agent → (process exit)
Orchestrator → closes sinks, writes final logs
```

---

### Resilience and Recovery
- **Missed Heartbeats:** If an Agent fails to send heartbeats for more than twice its expected interval, the Orchestrator marks it *degraded* and may query or restart it.  
- **Back-Pressure Handling:** Incoming message queues are throttled; Agents can self-tune emission frequency to reduce load.  
- **Error Recovery:** Consecutive failures trigger exponential backoff; successful heartbeats reset the error count.  
- **Graceful Termination:** Even under partial failure, the Orchestrator ensures all buffered data are flushed to disk and that segments close cleanly.  
- **Dashboard Continuity:** If the Dashboard disconnects, the Orchestrator continues normal operation; data remain accessible upon reconnection.

---

**Operational Summary**

MiMoLo’s full loop can be represented as:

`Startup → Sampling → Event → Aggregation → Segment → Dashboard → User → (Flush / Shutdown)`

This continuous feedback cycle ensures each Agent operates independently yet contributes to a unified, low-overhead timeline of creative or system activity.

### ...next [[6_Extensibility_and_Plugin_Development]]

