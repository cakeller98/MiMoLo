## Extensibility and Plugin Development

MiMoLo’s plugin ecosystem is intentionally open and language-agnostic.  
Any executable that communicates via Agent JLP (JSON Lines over stdin/stdout) and adheres to the defined message schema can operate as a Agent.  
This allows developers to extend the system without modifying core code—each agent is independently testable, replaceable, and sandboxed within its own process space.

---

### Agent Implementation
Developers can implement Agents in any language capable of reading from **stdin** and writing to **stdout** (Agent JLP).  
Agents must remain compliant with the MiMoLo communication schema and follow lightweight, cooperative behavior rules.

**Requirements**
- Communicate exclusively over Agent JLP using the canonical JSON line format.  
- Implement handlers for the core commands: `flush`, `status`, and `shutdown`.  
- Emit periodic `heartbeat` messages containing minimal health metrics.  
- Aggregate locally and emit concise `summary` messages instead of raw event streams.  
- Maintain efficiency targets: **<0.1% instantaneous CPU**, **<0.01% sustained average CPU**.  
- Include self-monitoring for health, queue depth, and sampling latency.  
- Exit gracefully and idempotently when the orchestrator issues a shutdown command.  

**Optional Enhancements**
- Implement `status` fields for custom health metrics (e.g., cache size, latency).  
- Add `error` messages for recoverable conditions to improve resilience.  
- Provide version and metadata tags for orchestrator and dashboard visibility.  

---

### Registration and Configuration
The orchestrator discovers and supervises agents based on configuration entries within `mimolo.toml`.  
Each agent is represented under `[plugins.<name>]`, where it may include both standard and plugin-specific parameters.

**Workflow**
1. Developer implements an agent and ensures JSON compliance.  
2. User adds configuration under `[plugins.<agent_name>]`, enabling and defining polling parameters.  
3. The orchestrator spawns the executable or Python class listed in configuration.  
4. Agents register themselves on launch via `status` or `heartbeat` messages.  
5. The Dashboard can modify these settings interactively and trigger a reload or restart.  
6. The orchestrator maintains versioning and runtime control (enable, disable, isolate).  

**Configuration Example**
```toml
[plugins.folderwatch]
enabled = true
poll_interval_s = 15.0
resets_cooldown = true
watch_dirs = ["./projects", "./assets"]
extensions = ["blend", "fbx", "obj"]
```

---

### Developer Compliance Checklist
✅ Communicates using Agent JLP (`"type"` or `"cmd"` required).  
✅ Emits a `heartbeat` within the configured interval.  
✅ Responds deterministically to `flush`, `status`, and `shutdown`.  
✅ Aggregates locally—no raw or verbose output flooding.  
✅ Maintains CPU and memory budgets automatically.  
✅ Emits recoverable `error` messages instead of stack traces.  
✅ Terminates cleanly and reproducibly across restarts.  
✅ Documents all configuration keys and their expected effects.  
✅ Tested independently using standard input/output without the orchestrator.  

---

**Summary**
Extensibility in MiMoLo centers on **protocol compliance**, not code coupling.  
By adhering to a simple, schema-driven interface, developers can introduce new Agents or integrate creative sensors—all without modifying the orchestrator core.  
This modular independence is the foundation of MiMoLo’s scalability and long-term maintainability.

### ...next [[7_Constraints_and_Performance_Etiquette]]

