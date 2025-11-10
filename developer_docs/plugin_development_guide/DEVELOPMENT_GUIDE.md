# MiMoLo Plugin Development Guide

> **Document Version:** 0.3  
> **Target Framework:** MiMoLo v0.3+  
> **Last Updated:** November 2025  
> **Status:** Living document

---

> **⚠️ Architectural Notice**  
> Beginning with **MiMoLo v0.3**, the canonical plugin model is the **asynchronous Field-Agent architecture**.  
> The older `BaseMonitor` synchronous model remains supported for backward compatibility but is **deprecated** and will be retired in a future release.  
> All new development must target **Field-Agent** standards.

---

## 1  Overview — What MiMoLo Is

**MiMoLo** (Mini Modular Monitor & Logger) is a lightweight, cooperative monitoring framework.  
It runs small, polite *agents* that observe aspects of the system or creative workflow and report structured events.  
The orchestrator (the “collector”) aggregates these events into human-readable logs and time segments.

**Design goals**

- Modular: each plugin is isolated and replaceable  
- Predictable: all agents communicate via JSON lines  
- Minimal overhead: hundreds – thousands of agents can coexist without noticeable impact on system **headroom**  
- Cross-language: any executable that speaks the JSON protocol can be a valid MiMoLo agent  

---

## 2  Plugin Types and Compatibility

| Plugin Type                  | Base Class                                | Launch Mode                       | Communication                | Status       |
| ---------------------------- | ----------------------------------------- | --------------------------------- | ---------------------------- | ------------ |
| **Synchronous Monitor**      | `BaseMonitor`                             | In-process (thread)               | Direct method calls          | *Deprecated* |
| **Asynchronous Field-Agent** | `BaseFieldAgent` (→ `AdaptiveFieldAgent`) | Sub-process / external executable | JSON lines over stdin/stdout | **Default**  |

Legacy monitors still work but are wrapped as “silent” agents inside the orchestrator.  
They only *speak when spoken to*.  
Field-Agents, by contrast, are autonomous: they send heartbeats, summaries, and status updates asynchronously.

---

## 3  Synchronous Model (Deprecated but Supported)

### 3.1 Definition
A `BaseMonitor` subclass implements:
```python
def emit_event(self) -> Event | None
```
and optionally a `filter_method()` for aggregation.

### 3.2 Runtime Behavior
- The orchestrator polls the plugin on its configured `poll_interval_s`.  
- Returned events are aggregated into segments.  
- If no event is returned, nothing is emitted.

### 3.3 Asynchronous Compatibility
Legacy plugins are now managed through a *Legacy Monitor Adapter* which:
- Wraps each synchronous plugin in an asynchronous facade  
- Emits synthetic JSON messages identical to Field-Agent output  
- Injects periodic heartbeats for health visibility  

**Best practice:** keep legacy monitors simple, fast, and stateless.  
They should defer heavy work to new Field-Agents whenever possible.

---

## 4  Field-Agent Architecture (v0.3+)

### 4.1 Philosophy
Field-Agents are **self-contained executables**.  
They may be written in Python, Node.js, Go, Rust — any language — as long as they:

- Read **commands** from **stdin**  
- Write **structured JSON messages** to **stdout**  
- Never block indefinitely  
- Respect global resource limits (`main_system_max_cpu_per_plugin`)  

### 4.2 Lifecycle
Each agent runs **three cooperative loops**:

| Component            | Responsibility                                         |
| -------------------- | ------------------------------------------------------ |
| **Command Listener** | Reads `{ "cmd": "flush"                                | "shutdown" | "status" }` from stdin |
| **Worker Loop**      | Samples or monitors, accumulates data continuously     |
| **Summarizer**       | Packages shunted data, writes JSON summaries to stdout |

**Flow example**

```
Collector → {"cmd": "flush"}  
Agent     → {"type": "summary", "data": {...}}  
Agent     → {"type": "heartbeat", "timestamp": "..."}
```

### 4.3 Required Message Types

| Type        | Description                     | Example                                                |
| ----------- | ------------------------------- | ------------------------------------------------------ |
| `summary`   | Data flush payload              | `{"type":"summary","data":{"folders":["/tmp"]}}`       |
| `heartbeat` | Regular health ping             | `{"type":"heartbeat","timestamp":"2025-11-07T09:00Z"}` |
| `status`    | Informational or degraded state | `{"type":"status","health":"degraded"}`                |
| `error`     | Recoverable agent-side failure  | `{"type":"error","message":"permission denied"}`       |

Agents must emit at least one `heartbeat` every `heartbeat_interval` seconds.

### 4.4 Freedom of Implementation
Beyond those basics, you’re free to be creative.  
Your agent could:
- Count files,
- Track GPU load,
- Paint spiderwebs on the desktop and measure the spider’s travel time.  

**As long as it stays polite** — within configured CPU and memory budgets — it’s a valid MiMoLo agent.

### 4.5 Resource Etiquette
- Respect `main_system_max_cpu_per_plugin` (default ≈ 0.1 %).  
- Yield often; sleep between samples.  
- Never spin-lock or busy-wait.  
- If you must exceed limits temporarily (e.g. heavy render analysis), clearly declare `"mode":"intensive"` in your status payload so the collector can throttle or isolate you.  

---

## 5  Adaptive and Self-Healing Agents

A professional-grade Field-Agent is **self-monitoring**:

### 5.1 Dynamic Self-Tuning
- Track queue size, flush latency, CPU usage.  
- If lag or load rises:  
  → reduce sampling rate or complexity.  
- When recovered:  
  → gradually restore normal rate.  
- Log each adjustment via `{"type":"status","tuned":{...}}`.

### 5.2 Graceful Notification
If self-tuning fails, emit:
```json
{"type":"status","health":"overload","metrics":{...}}
```
The collector may log, alert, or restart the agent.  
Agent may enter a minimal “safe mode” that sends only heartbeats until cleared.

### 5.3 Quality Control (QC)
Include health metrics in heartbeat or summary:
```json
{"type":"heartbeat",
 "metrics":{"cpu":0.03,"queue":2,"flush_latency_ms":8}}
```
The collector aggregates these and can classify agents as *slowpoke*, *degraded*, or *healthy*.

---

## 6  Collector Responsibilities (Orchestrator Side)

1. **Spawn** agents (sub-processes).  
2. **Parse** stdout → JSON events.  
3. **Enforce** CPU and memory budgets.  
4. **Record** metrics and segment data.  
5. **Intervene** when agents misbehave (log, restart, back-off).  
6. **Always log** every action for transparency.

---

## 7  Developer Freedom and Compliance Checklist

✅ You *must*  
- Use stdin/stdout JSON lines.  
- Send periodic heartbeats.  
- Respect resource budgets.  
- Handle `flush`, `status`, `shutdown` commands.  
- Exit cleanly on shutdown.  

✅ You *may*  
- Use any language or framework.  
- Perform any computation or creative experiment.  
- Implement custom self-tuning logic.  
- Emit additional message types (`log`, `metric`, `custom`).  

🚫 You *must not*  
- Consume excessive CPU or RAM.  
- Write to user output (console, UI) unless explicitly configured.  
- Hang on blocking operations.  
- Modify files outside your configured watch scope.

---

## 8  Examples of Compliance

### Example A — Folder Watcher Agent (Py)
A simple agent that monitors folders and flushes modified paths.  
Runs < 0.05 % CPU and emits one heartbeat per 5 s.

### Example B — Creative Spider Simulator (JS)
Draws procedural spiderwebs, measures traversal latency, and reports average node-time.  
Even this whimsical plugin is valid *if* it:
- Emits summaries in JSON,  
- Obeys CPU budget,  
- Yields gracefully between frames.

---

## 9  Future Roadmap

- Formal schema registration (`mimolo-agent-schema.json`)  
- Secure sandboxing / namespaces  
- Plugin capabilities advertisement (`metadata` messages)  
- Network-distributed collectors  

---

## 10  Summary

MiMoLo v0.3+ defines a **polite, asynchronous, self-aware ecosystem** of modular monitors.  
Each Field-Agent is expected to:

> *Observe lightly, report cleanly, adapt gracefully, and never steal headroom.*

Legacy synchronous monitors may coexist for now, but the path forward is clear:
**all new MiMoLo development belongs in the Field-Agent ecosystem.**

## 11  Documentation Map

For implementation details, see:

- **Protocol Reference**: `PROTOCOL_SPECIFICATION.md`  
  Complete technical specification for message formats, schemas, and validation.

- **Architectural Deep-Dive**: `developer_docs/1_Core_Overview.md` through `8_Future_Roadmap_and_Summary.md`  
  Comprehensive conceptual framework covering design philosophy, data flow, and constraints.

- **Working Examples**: `mimolo/plugins/`  
  Reference implementations including `folderwatch.py` (file monitoring) and `template.py` (starter scaffold).

---

**Legacy Note**: Existing `BaseMonitor` plugins continue to function via compatibility adapters,  
but development guidance for that synchronous model has been retired as of v0.3.
