## Architectural Overview

MiMoLo operates as a distributed monitoring loop connecting Field-Agents, the Orchestrator, and an optional Dashboard.  
Each Field-Agent performs localized sampling with near-zero overhead, reports summarized observations as structured JSON, and the Orchestrator aggregates these into time-based segments for persistence and visualization.  
The Dashboard observes the Orchestrator’s state, queries aggregated data, and provides human interaction for configuration and reporting.

---

### Operational Flow
1. **Launch** – The Orchestrator starts and loads configuration, then spawns each Field-Agent as a subprocess.  
2. **Initialization** – Each Field-Agent registers itself by sending a `status` or `heartbeat` message confirming readiness.  
3. **Sampling Loop** – Agents collect local data at their own cadence (<0.1% instantaneous CPU, <0.01% sustained) and internally aggregate results.  
4. **Event Emission** – Agents emit newline-delimited JSON messages (`heartbeat`, `summary`, `status`, `error`) through stdout.  
5. **Aggregation** – The Orchestrator receives these events, validates structure, and groups them into segments representing continuous work periods.  
6. **Persistence** – Segments and events are written to configured sinks (JSONL, YAML, Markdown).  
7. **Dashboard Interaction** – The Dashboard queries the Orchestrator over its control channel for near-real-time summaries, agent health, and accumulated statistics.  
8. **User Interaction** – The user views current activity, modifies monitored paths or settings, and can trigger on-demand reports or exports.  
9. **Shutdown** – The Orchestrator issues a `shutdown` command to all Field-Agents, collects any final data, and closes sinks cleanly.

---

### Message Flow Overview

User  
↑  
│ (configuration / reports)  
│  
Dashboard ⇄ Orchestrator ⇄ Field-Agents  
│             │  
│             └──> Logs / Sinks → Persistent storage  
│  
└──> Displays timecards, activity, agent health  

---

### Communication Channels

| Direction | Medium | Content | Frequency / Nature |
|------------|---------|----------|--------------------|
| **Orchestrator → Agent** | `stdin` | Command messages (`flush`, `status`, `shutdown`) | On demand |
| **Agent → Orchestrator** | `stdout` | Structured JSON (`heartbeat`, `summary`, `status`, `error`) | Periodic / event-driven |
| **Orchestrator → Dashboard** | IPC / HTTP / WebSocket | Aggregated data, agent health, configuration API | Near-real-time |
| **Dashboard → Orchestrator** | IPC / HTTP / WebSocket | User actions, configuration updates, export requests | Event-driven |
| **Orchestrator → Sinks** | File I/O (JSONL, YAML, Markdown) | Persistent segment and event logs | Continuous |
| **Orchestrator → Console** | stdout / rich console | Status updates, debug output, lifecycle messages | Optional / interactive |

---

**System Summary**  
MiMoLo’s architecture forms a closed feedback loop:  
`Field-Agent → Event → Orchestrator → Segment → Sink → Dashboard → User`  
Each component communicates asynchronously using well-defined, low-overhead channels, ensuring accurate time and activity tracking without measurable impact on system performance.

### ...next [[4_Data_Schema_and_Message_Types]]