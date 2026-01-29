# Code Review & Migration Strategy for MiMoLo v0.2 → v0.3

> **Note (v0.3+ reality):** Legacy synchronous plugins are removed. Agents are the only supported plugin type.  
> Any sections below that mention legacy adapters or `mimolo/plugins/` are historical and should not be implemented.

## Executive Summary

**Recommendation: HYBRID APPROACH**

- **~40% salvageable** - Core utilities, config, error taxonomy, event primitives
- **~60% needs rebuilding** - Plugin architecture, orchestrator, communication layer

**Verdict:** Refactor and extend. The bones are solid, but the architecture fundamentally changed.

---

## ✅ What's Excellent and Salvageable (Keep & Extend)

### 1. **Configuration System** (`core/config.py`) - 95% Reusable
- Pydantic validation ✅
- TOML/YAML support ✅
- MonitorConfig, PluginConfig structure ✅
- **Minor changes needed:**
  - Add `main_system_max_cpu_per_plugin` to MonitorConfig
  - Add `heartbeat_interval_s` to PluginConfig
  - Add journal output directory config
  - Remove or deprecate `infrequent` flag (no longer in v0.3 spec)

### 2. **Error Taxonomy** (`core/errors.py`) - 100% Reusable
- Clean hierarchy ✅
- Good error context ✅
- **No changes needed** - this is perfect

### 3. **Event Primitives** (`core/event.py`) - 90% Reusable
- Event, EventRef, Segment dataclasses ✅
- ID computation ✅
- Validation ✅
- **Minor changes needed:**
  - Segment structure needs adjustment for v0.3 journal format (event stream vs. complete objects)
  - Add support for new message types (handshake, heartbeat, status, error)

### 4. **Build System** (`pyproject.toml`) - 100% Reusable
- Poetry setup ✅
- Dependencies look good ✅
- Ruff/mypy config ✅
- **No changes needed**

### 5. **CLI Structure** (`cli.py`) - 70% Reusable
- Typer framework ✅
- Command structure (monitor, test) ✅
- **Changes needed:**
  - Remove synchronous plugin discovery
  - Add Agent subprocess spawning
  - Add dashboard launch command

---

## ❌ What's Broken and Needs Rebuilding

### 1. **Plugin Architecture** - FUNDAMENTAL BREAKING CHANGE

**v0.2 Pattern (Synchronous):**
```python
class BaseMonitor(ABC):
    spec = PluginSpec(...)
    
    def emit_event(self) -> Event | None:
        # Called by orchestrator in same process
        return Event(...)
```

**v0.3 Pattern (Asynchronous Agent):**
```python
# Separate subprocess communicating via Agent JLP
# Three cooperative loops: Command Listener, Worker Loop, Summarizer
# No shared memory, no direct method calls
```

**Impact:** Every plugin must be rewritten as a Agent subprocess.

**Migration Path:**
1. Create `BaseFieldAgent` class with Agent JLP
2. Create legacy adapter that wraps v0.2 plugins in Agent interface
3. Rewrite plugins one-by-one as true Agents

---

### 2. **Orchestrator/Runtime** (`core/runtime.py`) - 80% Needs Rewriting

**v0.2 Issues:**
- In-process polling loop ❌
- Direct method calls to plugins ❌
- No subprocess management ❌
- No Agent JLP communication ❌
- No protocol validation ❌

**v0.3 Requirements:**
- Spawn Agents as subprocesses ✅ (new)
- Read/parse Agent JLP stdout lines ✅ (new)
- Write commands to Agent JLP stdin ✅ (new)
- Validate against `mimolo-agent-schema.json` ✅ (new)
- Track agent health via heartbeats ✅ (new)
- Enforce CPU/memory limits ✅ (new)

**Salvageable Parts:**
- `PluginScheduler` (polling logic) ✅
- `PluginErrorTracker` (backoff logic) ✅
- Tick-based main loop structure ✅

**Needs Rebuilding:**
- Plugin emission (becomes: read Agent JLP stdout lines, parse JSON)
- Event handling (becomes: validate, route by message type)
- Segment lifecycle (becomes: write to daily journal JSONL on segment_close)

---

### 3. **Aggregation Layer** (`core/aggregate.py`) - ARCHITECTURAL MISMATCH

**v0.2 Approach:**
- Buffer events in-memory during segment
- Apply filter_method on segment close
- Build complete Segment object

**v0.3 Approach:**
- Write every flush as a `summary` event to daily journal
- No in-memory aggregation in orchestrator
- Report plugins synthesize segments from event stream

**Verdict:** Delete `SegmentAggregator` entirely. Orchestrator just writes events to journal.

---

### 4. **Cooldown Timer** (`core/cooldown.py`) - 60% Salvageable

**Salvageable:**
- State machine (IDLE, ACTIVE, CLOSING) ✅
- Expiration logic ✅
- SegmentState tracking ✅

**Needs Changes:**
- Add idle_period tracking
- Change segment close to write event stream (not aggregated Segment)

---

### 5. **Sinks** (`core/sink.py`) - 50% Salvageable

**v0.2 Sinks:**
- JSONLSink, YAMLSink, MarkdownSink
- Daily rotation ✅
- Write complete Segment objects

**v0.3 Requirements:**
- Write event stream (segment_start, summary, segment_close, idle_start)
- JSONL is primary format
- YAML/Markdown become dashboard report plugins

**Migration:**
- Keep JSONLSink, adapt to event stream format
- Delete YAMLSink, MarkdownSink (move to dashboard report plugins)
- Rename to `daily_journal_YYYYMMDD.jsonl`

---

### 6. **Registry** (`core/registry.py`) - 40% Salvageable

**Salvageable:**
- Label uniqueness enforcement ✅
- Lookup methods ✅

**Needs Changes:**
- Store Agent subprocess handles (not instances)
- Track PIDs, health status, last heartbeat
- Remove filter_method references (no in-memory aggregation)

---

## 📋 Detailed Refactor Roadmap

### **Phase 1: Preserve Core Utilities (1-2 days)**

**Goal:** Extract and extend the good parts

1. **Keep as-is:**
   - `core/errors.py` ✅
   - `core/event.py` ✅ (minor tweaks)
   - `pyproject.toml` ✅

2. **Extend:**
   - `core/config.py`:
     ```python
     class MonitorConfig(BaseModel):
         cooldown_seconds: float = 600.0
         poll_tick_ms: float = 200.0
         journal_dir: str = "./journals"  # NEW
         cache_dir: str = "./cache"  # NEW
         main_system_max_cpu_per_plugin: float = 0.1  # NEW
         # ... rest
     
     class PluginConfig(BaseModel):
         enabled: bool = True
         poll_interval_s: float = 5.0
         heartbeat_interval_s: float = 15.0  # NEW
         resets_cooldown: bool = True
         # Remove: infrequent (deprecated)
     ```

3. **Adapt:**
   - `core/event.py` - Add new message types:
     ```python
     @dataclass
     class HandshakeMessage:
         type: Literal["handshake"]
         timestamp: datetime
         agent_id: str
         agent_label: str
         protocol_version: str
         agent_version: str
         min_app_version: str
         capabilities: list[str]
         data: dict[str, Any]
     
     # Similar for HeartbeatMessage, StatusMessage, ErrorMessage
     ```

---

### **Phase 2: Build Agent Protocol Layer (3-5 days)**

**Goal:** New Agent JLP communication infrastructure

1. **Create `core/protocol.py`:**
   ```python
   class FieldAgentProtocol:
       """Handles Agent JLP communication with Agents."""
       
       def __init__(self, process: subprocess.Popen):
           self.process = process
           self.stdout_reader = LineReader(process.stdout)
           self.stdin_writer = LineWriter(process.stdin)
       
       def read_message(self) -> dict | None:
           """Non-blocking read of JSON line from stdout."""
           line = self.stdout_reader.read_line()
           if line:
               return json.loads(line)
           return None
       
       def send_command(self, cmd: dict) -> None:
           """Write command as JSON line to stdin."""
           self.stdin_writer.write_line(json.dumps(cmd))
       
       def validate_message(self, msg: dict) -> bool:
           """Validate against mimolo-agent-schema.json."""
           # Use jsonschema library
           ...
   ```

2. **Create `core/agent_manager.py`:**
   ```python
   class FieldAgentManager:
       """Manages Agent subprocess lifecycle."""
       
       def spawn_agent(self, config: PluginConfig) -> FieldAgentHandle:
           """Spawn agent as subprocess."""
           proc = subprocess.Popen(
               [config.executable, *config.args],
               stdin=subprocess.PIPE,
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE,
               text=True,
               bufsize=1  # Line-buffered
           )
           return FieldAgentHandle(proc, config)
       
       def perform_handshake(self, handle: FieldAgentHandle) -> bool:
           """Execute handshake protocol."""
           # Read handshake message, send ack/reject
           ...
       
       def monitor_health(self, handle: FieldAgentHandle) -> AgentHealth:
           """Check heartbeat freshness."""
           ...
   ```

---

### **Phase 3: Rebuild Orchestrator Core (5-7 days)**

**Goal:** New orchestrator that spawns Agents and writes daily journals

1. **Create `core/orchestrator.py`:**
   ```python
   class Orchestrator:
       def __init__(self, config: Config):
           self.config = config
           self.agent_manager = FieldAgentManager()
           self.agents: dict[str, FieldAgentHandle] = {}
           self.journal_writer = DailyJournalWriter(config.journal_dir)
           self.cooldown = CooldownTimer(config.cooldown_seconds)
       
       def start(self):
           """Spawn all configured Agents."""
           for plugin_name, plugin_config in self.config.plugins.items():
               if plugin_config.enabled:
                   handle = self.agent_manager.spawn_agent(plugin_config)
                   self.agents[plugin_name] = handle
       
       def tick(self):
           """Main event loop tick."""
           # Read messages from all agent stdout
           for label, handle in self.agents.items():
               while True:
                   msg = handle.protocol.read_message()
                   if msg is None:
                       break
                   self._handle_message(label, msg)
           
           # Check cooldown expiration
           if self.cooldown.check_expiration(datetime.now(UTC)):
               self._close_segment()
       
       def _handle_message(self, label: str, msg: dict):
           """Route message by type."""
           msg_type = msg.get("type")
           
           if msg_type == "heartbeat":
               self._handle_heartbeat(label, msg)
           elif msg_type == "summary":
               self._handle_summary(label, msg)
           elif msg_type == "status":
               self._handle_status(label, msg)
           elif msg_type == "error":
               self._handle_error(label, msg)
       
       def _handle_summary(self, label: str, msg: dict):
           """Write summary to journal, update cooldown."""
           # Check if this agent resets cooldown
           plugin_config = self.config.plugins[label]
           if plugin_config.resets_cooldown:
               self.cooldown.on_resetting_event(parse_timestamp(msg["timestamp"]))
           
           # Write summary event to journal
           self.journal_writer.write_event({
               "type": "summary",
               "agent": label,
               **msg
           })
       
       def _close_segment(self):
           """Write segment_close event to journal."""
           segment_state = self.cooldown.close_segment()
           self.journal_writer.write_event({
               "type": "segment_close",
               "timestamp": segment_state.last_event_time.isoformat(),
               "segment_id": self._generate_segment_id(),
               "duration_s": (segment_state.last_event_time - segment_state.start_time).total_seconds()
           })
           self.journal_writer.write_event({
               "type": "idle_start",
               "timestamp": datetime.now(UTC).isoformat()
           })
   ```

2. **Create `core/journal.py`:**
   ```python
   class DailyJournalWriter:
       """Writes event stream to daily_journal_YYYYMMDD.jsonl."""
       
       def write_event(self, event: dict):
           """Write event as JSON line to current day's journal."""
           date_str = datetime.now(UTC).strftime("%Y%m%d")
           journal_path = self.journal_dir / f"daily_journal_{date_str}.jsonl"
           
           with open(journal_path, "a") as f:
               f.write(json.dumps(event) + "\n")
               f.flush()
   ```

---

### **Phase 4: Migrate Plugins to Agents (3-5 days)**

**Goal:** Convert existing plugins to Agent architecture

1. **Create `BaseFieldAgent` wrapper:**
   ```python
   class BaseFieldAgent(ABC):
       """Base class for Agent implementations."""
       
       def __init__(self):
           self.stdin = sys.stdin
           self.stdout = sys.stdout
           self.running = True
           
           # Three cooperative loops (threads)
           self.command_thread = threading.Thread(target=self._command_listener)
           self.worker_thread = threading.Thread(target=self._worker_loop)
           self.summarizer_thread = threading.Thread(target=self._summarizer_loop)
           
           self.flush_event = threading.Event()
           self.data_lock = threading.Lock()
           self.accumulated_data = []
       
       def run(self):
           """Start all three loops."""
           self.command_thread.start()
           self.worker_thread.start()
           self.summarizer_thread.start()
           
           self.command_thread.join()
           self.worker_thread.join()
           self.summarizer_thread.join()
       
       def _command_listener(self):
           """Read commands from stdin."""
           for line in self.stdin:
               cmd = json.loads(line)
               if cmd["cmd"] == "flush":
                   self.flush_event.set()
               elif cmd["cmd"] == "shutdown":
                   self.running = False
                   break
       
       def _worker_loop(self):
           """Sample and accumulate data."""
           while self.running:
               data = self.sample()  # Abstract method
               if data:
                   with self.data_lock:
                       self.accumulated_data.append(data)
               time.sleep(self.poll_interval_s)
       
       def _summarizer_loop(self):
           """Emit heartbeats and summaries."""
           while self.running:
               # Emit heartbeat
               self._emit_heartbeat()
               
               # Check for flush
               if self.flush_event.is_set():
                   self._emit_summary()
                   self.flush_event.clear()
               
               time.sleep(self.heartbeat_interval_s)
       
       @abstractmethod
       def sample(self) -> Any:
           """Sample data (implemented by subclass)."""
           ...
   ```

2. **Convert existing plugins:**
   ```python
   # Example: FolderWatchMonitor → FolderWatchAgent
   class FolderWatchAgent(BaseFieldAgent):
       def __init__(self, watch_dirs, extensions):
           super().__init__()
           self.watch_dirs = watch_dirs
           self.extensions = extensions
           self._last_mtimes = {}
       
       def sample(self) -> list[str] | None:
           """Check for file modifications."""
           # Same logic as v0.2, but return folders instead of Event
           for watch_dir in self.watch_dirs:
               # ... existing logic ...
               if mtime > last_mtime:
                   return [str(file_path.parent.resolve())]
           return None
   ```

---

### **Phase 5: Dashboard & Bridge (5-7 days)**

**Goal:** Build Dashboard-Orchestrator bridge and report plugins

1. **Create `dashboard/bridge.py`:**
   ```python
   class OrchestratorBridge:
       """IPC/HTTP bridge to Orchestrator."""
       
       def get_agent_status(self) -> dict:
           """Query agent health."""
           ...
       
       def start_monitors(self) -> dict:
           """Command: start all agents."""
           ...
   ```

2. **Create report plugins** (PDF, CSV, timelapse, etc.)

---

## 🎯 Migration Checklist

### Immediate (Week 1)
- [ ] Extend `core/config.py` with v0.3 fields
- [ ] Add new message types to `core/event.py`
- [ ] Create `core/protocol.py` (Agent JLP)
- [ ] Create `core/agent_manager.py` (subprocess lifecycle)

### Core Rebuild (Week 2-3)
- [ ] Build new `core/orchestrator.py`
- [ ] Create `core/journal.py` (daily JSONL writer)
- [ ] Adapt `core/cooldown.py` for event stream
- [ ] Delete `core/aggregate.py` (obsolete)

### Plugin Migration (Week 3-4)
- [ ] Create `BaseFieldAgent` class
- [ ] Convert FolderWatchMonitor → FolderWatchAgent
- [ ] Convert ExampleMonitor → ExampleAgent
- [ ] Build Creo Trail Watcher, Screenshot plugins (new)

### Dashboard (Week 4-5)
- [ ] Build Dashboard-Orchestrator bridge
- [ ] Implement journal reader
- [ ] Create report plugins (invoice, timecard, CSV)

---

## Final Recommendation

**REFACTOR AND EXTEND** - Don't start from scratch. About 40% of the code is solid and reusable. The plugin architecture and orchestrator need rebuilding, but you have excellent foundations in config, errors, events, and build system.

**Estimated Timeline:** 4-5 weeks for full v0.3 implementation with the roadmap above.

Ready to dive in? Want me to help write any of these new components?


