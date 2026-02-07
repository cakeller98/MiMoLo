> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

## Core Concepts

### Orchestrator
The orchestrator is the supervisory process that spawns, tracks, and manages Agents. It coordinates communication, enforces resource policies, and aggregates data into time-based segments. It never executes agent code directly but interacts asynchronously with them through structured JSON messages.

**Capabilities**
- Spawn and terminate Agents as subprocesses  
- Send structured control commands (`flush`, `status`, `shutdown`)  
- Track agent status, heartbeat signals, and health metrics  
- Request live data (with or without flush) for dashboards or active monitoring  
- Enforce per-agent CPU and memory budgets  
- Aggregate agent summaries into segments for logging and analytics  
- Throttle, restart, or isolate agents that exceed limits or fail  
- Maintain a complete activity record of all orchestration actions  

---

### Agent
A Agent is an autonomous, ultra-lightweight process that performs an independent sensing or observation task while adhering to strict efficiency mandates. Each agent operates with **less than 0.1% instantaneous CPU utilization** and typically averages **below 0.01% CPU load over time**. Agents may sample data at high internal frequency but are required to aggregate locally and report infrequently—only when results are meaningful or requested. This design ensures that MiMoLo can run thousands of concurrent agents without measurable system impact.

**Capabilities**
- Perform any independent sensing or monitoring function in any language  
- Sample frequently but aggregate internally to minimize reporting overhead  
- Emit periodic heartbeats, health summaries, and status updates  
- Report warnings or recoverable errors through structured messages  
- Self-monitor and dynamically throttle sampling to remain within CPU and memory limits  
- Communicate asynchronously via Agent JLP (JSON Lines over stdin/stdout)  
- Respect orchestrator commands and exit cleanly on shutdown  

---

### Event
An event is a discrete, timestamped message representing a single unit of information or state change. It may originate from a Agent (observation, heartbeat, summary, warning, error) or from the orchestrator (command, acknowledgment). Events are the atomic communication layer of MiMoLo.

**Capabilities**
- Carry structured JSON data for reliable machine parsing  
- Represent any measurable change or control signal  
- Include metadata such as timestamp, type, and source label  
- Enable fully asynchronous, bidirectional communication between orchestrator and agents  

---

### Segment
A segment is a grouped record representing a continuous window of related activity. It condenses multiple events or summaries into a single, meaningful unit of time for review or analysis. Segments allow the orchestrator to present readable histories without requiring raw event streams.

**Capabilities**
- Aggregate and summarize sequences of related events  
- Capture duration, contributing agents, and accumulated data  
- Serve as durable records for logging, analytics, or visualization  
- Provide human-readable context for system or creative activity  

---

### Schema / Protocol
The schema defines the structure of all JSON messages exchanged between orchestrator and agents, and the protocol specifies how and when those messages flow. Together, they ensure interoperability, resilience, and predictability across languages and platforms.

**Capabilities**
- Define canonical message types (`heartbeat`, `summary`, `status`, `error`, `command`)  
- Maintain a stable, language-neutral Agent JLP format  
- Govern asynchronous bidirectional communication and timing rules  
- Enforce separation of responsibility: agents produce data; the orchestrator consumes and commands  
- Support large-scale monitoring where polling occurs every 5–15 seconds, minimizing total system overhead while still capturing meaningful workflow signals 

---

### Dashboard / Control Interface
The Dashboard is the human-facing companion to the orchestrator. It provides visualization, configuration, and reporting tools that translate the orchestrator’s aggregated data into interpretable context for users. The Dashboard never communicates directly with Agents—it interacts solely with the orchestrator through a control API or IPC channel.

**Capabilities**
- Query orchestrator state, agent health, and recent segment data in near-real time  
- Send configuration updates (e.g., modify plugin parameters, adjust monitored folders)  
- Trigger on-demand exports such as timecards or activity summaries  
- Render Jinja2 templates for formatted reports and allow live editing of those templates  
- Display health, performance, and activity dashboards without adding measurable system overhead  

---

### Hierarchy Note
The orchestrator remains the single point of authority for all communication:
- **Agents** report upward to the **Orchestrator**.  
- The **Dashboard** queries and commands through the **Orchestrator**, never bypassing it.  

---

### Glossary
**Agent JLP** — *Agent JSON Lines Protocol.* The newline-delimited JSON protocol over stdin/stdout used exclusively for Agent ↔ Orchestrator messaging (commands, heartbeats, summaries, logs).  

### ...next [[3_Architectural_Overview]]

