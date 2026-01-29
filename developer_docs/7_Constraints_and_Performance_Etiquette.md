## Constraints and Performance Etiquette

MiMoLo enforces lightweight, predictable behavior across all components to guarantee scalability, stability, and zero interference with user workloads.  
Its agents are designed to be *polite citizens*—able to observe and report continuously without ever consuming noticeable resources.  
These limits ensure the system remains deterministic and safe even when hundreds or thousands of Agents operate concurrently.

---

### Resource Limits

| Resource               | Target                     | Hard Cap            | Enforcement                          |
| ---------------------- | -------------------------- | ------------------- | ------------------------------------ |
| **CPU (per agent)**    | < 0.01 % sustained average | 0.1 % instantaneous | Self-monitor + orchestrator throttle |
| **Memory (per agent)** | < 32 MB typical            | 64 MB absolute      | Self-report + orchestrator isolation |
| **Message rate**       | ≤ 1 msg / 3 s average      | Burst ≤ 10 msg / s  | Orchestrator back-pressure           |
| **Startup latency**    | < 1 s normal               | 3 s timeout         | Process watchdog / forced restart    |
| **Heartbeat interval** | 5–15 s typical             | 30 s maximum        | Orchestrator degradation flag        |
| **File I/O rate**      | < 100 KB / s per agent     | 1 MB / s burst      | Internal throttling + delayed flush  |

---

### Behavioral Guidelines

- **Self-Throttling:**  
  Agents must continuously monitor their CPU and queue usage. When resource metrics rise, sampling intervals lengthen or analysis complexity decreases automatically.

- **Dynamic Rate Adjustment:**  
  Sampling frequency adapts to system headroom—agents slow down under pressure and resume normal cadence once stable.

- **Graceful Degradation:**  
  During overload, agents pause summary generation but continue sending minimal `heartbeat` messages to maintain visibility.

- **No Busy-Waiting:**  
  All sampling loops must include blocking waits or explicit `sleep()` intervals. Continuous polling or spin-locks are forbidden.

- **Bounded Queues:**  
  Any in-memory buffer must be finite; when approaching capacity, the agent emits a `status: degraded` message and temporarily reduces output.

- **Silent Recovery:**  
  Agents recover automatically from transient I/O or permission errors, resuming normal operation without requiring user intervention.

---

### Orchestrator Enforcement

- **Monitoring and Classification:**  
  The orchestrator tracks all agent metrics and classifies each as *healthy*, *degraded*, or *quarantined* based on CPU, memory, and heartbeat timing.

- **Back-Pressure and Isolation:**  
  If an agent exceeds its allowed output rate or resource limit, the orchestrator applies back-pressure, pauses reads, or temporarily suspends polling.

- **Exponential Back-Off:**  
  Repeated `error` messages trigger exponentially increasing delays before the next poll cycle, reducing system load while maintaining supervision.

- **Restart and Recovery:**  
  Agents that fail or hang beyond timeout thresholds are gracefully restarted with their last known configuration.

- **Telemetry Aggregation:**  
  Performance and health data are logged to sinks and visualized in the Dashboard for long-term trend analysis.

---

### Measurement and Verification

- Benchmark new agents for **5-minute sustained CPU and memory averages** before deployment.  
- Verify each `heartbeat` includes `metrics.cpu` and `metrics.mem_mb`.  
- Review orchestrator diagnostic logs and Dashboard telemetry for compliance across multi-hour sessions.  
- Use controlled load tests to confirm that throttling and recovery logic behave deterministically under pressure.

---

**Principle:** *Every agent must remain polite.*  
MiMoLo’s cooperative etiquette guarantees that observation never competes with creation—ensuring persistent insight with negligible cost.

### ...next [[8_Future_Roadmap_and_Summary]]
