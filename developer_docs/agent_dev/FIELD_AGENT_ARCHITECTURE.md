# MiMoLo Agent Architecture Summary

> **Status:** Implemented in v0.3  
> **Last Updated:** November 10, 2025

## Overview

Agents are **self-contained, standalone executables** that monitor system activity and report to the MiMoLo orchestrator via Agent JLP (JSON Lines over stdin/stdout).

## Key Architectural Principles

### 1. **Agents Aggregate Their Own Data**

- Agents maintain internal accumulators in their Worker Loop
- When flushed, they create a snapshot, start fresh accumulation, and summarize the snapshot
- The orchestrator **never re-aggregates** Agent data

### 2. **Heartbeats Are Health Signals**

- Heartbeats contain health metrics (CPU, memory, queue size, flush latency)
- Orchestrator uses heartbeats for health tracking and optional console output
- Heartbeats are not aggregated into segments

### 3. **Summaries Are Pre-Aggregated**

- When an agent receives `flush` command, it:
  1. Takes a snapshot of accumulated data
  2. Starts a fresh accumulator
  3. Hands snapshot to Summarizer thread
  4. Summarizer packages data with start/end timestamps
  5. Emits `summary` message to stdout
- Orchestrator writes summaries **directly to file sink** without modification

### 4. **Flush Scheduling**

The orchestrator sends `flush` commands based on:
- `agent_flush_interval_s` config (default: 60s)
- Tracked per-agent (each agent has independent flush timing)
- Checked every tick, sent when interval elapsed

## Three-Thread Agent Architecture

Each Agent runs three cooperative threads:

```
┌─────────────────────────────────────────────┐
│  Agent Process                        │
│                                             │
│  ┌─────────────┐  ┌──────────────┐         │
│  │  Command    │  │  Worker Loop │         │
│  │  Listener   │  │              │         │
│  │  (stdin)    │  │  Accumulates │         │
│  └──────┬──────┘  │  data        │         │
│         │         └──────┬───────┘         │
│         │ flush          │                 │
│         └────────────────┤                 │
│                          │                 │
│                  ┌───────▼────────┐        │
│                  │  Summarizer    │        │
│                  │  Thread        │        │
│                  │  (stdout)      │        │
│                  └────────────────┘        │
└─────────────────────────────────────────────┘
```

## Message Flow

### Heartbeat Flow (Every ~15s)
```
Agent → {"type":"heartbeat","timestamp":"...","metrics":{...}}
Orchestrator → Writes to file immediately
```

### Flush/Summary Flow (Every ~60s)
```
Orchestrator → {"cmd":"flush"}
Agent → [Takes snapshot, starts fresh accumulator]
Agent → [Summarizer packages snapshot]
Agent → {"type":"summary","data":{start:"...",end:"...",items:[...]}}
Orchestrator → Writes to file immediately
```

### Sequence Flow (Ordered Commands)
```
Orchestrator → {"cmd":"sequence","sequence":["stop","flush","shutdown"]}
Agent → ACK(stop) → summary → ACK(flush) → shutdown
```

### Error Flow (As Needed)
```
Agent → {"type":"error","message":"..."}
Orchestrator → Logs error to console
```

## Configuration

### Agent Plugin Config

```toml
[plugins.my_agent]
enabled = true
plugin_type = "agent"           # Required
executable = "python"                 # Command to execute
args = ["agents/my_agent.py"]         # Arguments passed to executable
heartbeat_interval_s = 15.0           # How often agent sends heartbeat
agent_flush_interval_s = 60.0         # How often orchestrator sends flush
```

## Runtime Behavior

### Orchestrator Startup
1. Load config
2. For each plugin:
   - If `plugin_type == "agent"` → spawn subprocess via `agent_manager.spawn_agent()`
3. Start main event loop

### During Operation
Every tick (~100ms):
1. Check Agent flush intervals
   - Send `flush` commands when interval elapsed
2. Drain Agent message queues
   - Route by message type (heartbeat/summary/error)
   - Write summaries directly to file

### Shutdown
1. Send `sequence` commands to all Agents (stop → flush → shutdown)
2. Wait for agent processes to exit
3. Flush and close file sinks

## File Output Format

### Heartbeat Event (JSONL)
```json
{
  "timestamp": "2025-11-10T14:23:45.123Z",
  "label": "my_agent",
  "event": "heartbeat",
  "data": {
    "heartbeat": true,
    "metrics": {
      "cpu": 0.03,
      "mem": 42.1,
      "queue": 2,
      "latency_ms": 8.5
    }
  }
}
```

### Summary Event (JSONL)
```json
{
  "timestamp": "2025-11-10T14:24:00.456Z",
  "label": "my_agent",
  "event": "summary",
  "data": {
    "start_time": "2025-11-10T14:23:00Z",
    "end_time": "2025-11-10T14:24:00Z",
    "duration_s": 60,
    "items": [...],
    "count": 42
  }
}
```

## Implementation Status

### ✅ Completed
- Agent spawning on startup
- Message polling and routing
- Heartbeat logging to file
- Summary logging to file (without re-aggregation)
- Periodic flush command sending
- Agent shutdown on orchestrator exit
- Configuration schema with flush intervals

### 🚧 Next Steps
1. Create reference Agent implementations
   - Create template Agent with 3-thread architecture
2. Add agent health monitoring dashboard
3. Implement agent restart on failure
4. Add flush timeout handling

## References

- **Full Development Guide:** `developer_docs/agent_dev/AGENT_DEV_GUIDE.md`
- **Protocol Specification:** `developer_docs/agent_dev/AGENT_PROTOCOL_SPEC.md`
- **Configuration:** `mimolo/core/config.py` (PluginConfig)
- **Agent Management:** `mimolo/core/agent_process.py` (AgentProcessManager)
- **Orchestrator:** `mimolo/core/runtime.py` (MonitorRuntime)

