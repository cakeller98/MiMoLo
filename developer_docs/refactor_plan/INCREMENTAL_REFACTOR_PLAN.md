# Incremental Refactor Plan: v0.2 → v0.3
> **Strategy:** File-by-file evolution with working code at every checkpoint  
> **Philosophy:** Adapt existing code, don't rebuild from scratch  
> **Timeline:** 3-4 weeks with continuous testing

---

## Core Principle: Dual-Mode Operation

The orchestrator will support **two plugin types simultaneously**:

| Type                   | Location               | Communication       | Heartbeats                           | Status             |
| ---------------------- | ---------------------- | ------------------- | ------------------------------------ | ------------------ |
| **Legacy Sync Plugin** | `mimolo/plugins/`      | Direct method calls | Synthetic (injected by orchestrator) | Silent (poll-only) |
| **Field-Agent Plugin** | `mimolo/user_plugins/` | stdin/stdout JSON   | Autonomous                           | Asynchronous       |

Both types participate in the same segment lifecycle. The orchestrator abstracts the differences.

---

## Phase 1: Foundation (Days 1-3)
**Goal:** Add Field-Agent protocol support without breaking existing plugins

### Step 1.1: Extend Configuration (`core/config.py`)
**Status:** Additive only - no breaking changes

```python
class MonitorConfig(BaseModel):
    cooldown_seconds: float = 600.0
    poll_tick_ms: float = 200.0
    log_dir: str = "./logs"
    log_format: str = "jsonl"
    console_verbosity: str = "info"
    
    # NEW: Field-Agent support
    journal_dir: str = "./journals"  # Event stream storage
    cache_dir: str = "./cache"  # Agent state cache
    main_system_max_cpu_per_plugin: float = 0.1  # CPU limit per agent
    agent_heartbeat_timeout_s: float = 30.0  # Miss threshold
    
class PluginConfig(BaseModel):
    enabled: bool = True
    poll_interval_s: float = 5.0
    resets_cooldown: bool = True
    
    # NEW: Field-Agent specific
    plugin_type: Literal["legacy", "field_agent"] = "legacy"  # Auto-detect
    executable: str | None = None  # For field agents: python path or script
    args: list[str] = Field(default_factory=list)  # CLI args for agent
    heartbeat_interval_s: float = 15.0  # Expected heartbeat frequency
```

**Testing:** Run existing tests - should pass with defaults.


- [x] step complete

---

### Step 1.2: Add Protocol Message Types (`core/protocol.py` - NEW FILE)
**Status:** New file, no existing code affected

```python
"""Field-Agent protocol message types and validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Agent → Orchestrator message types."""
    HANDSHAKE = "handshake"
    SUMMARY = "summary"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    ERROR = "error"


class CommandType(str, Enum):
    """Orchestrator → Agent command types."""
    ACK = "ack"
    REJECT = "reject"
    FLUSH = "flush"
    STATUS = "status"
    SHUTDOWN = "shutdown"


class AgentMessage(BaseModel):
    """Base message envelope for all agent → orchestrator messages."""
    type: MessageType
    timestamp: datetime
    agent_id: str
    agent_label: str
    protocol_version: str = "0.3"
    agent_version: str
    data: dict[str, Any] = Field(default_factory=dict)
    
    # Optional fields
    metrics: dict[str, Any] | None = None
    health: Literal["ok", "degraded", "overload", "failed"] | None = None
    message: str | None = None


class HandshakeMessage(AgentMessage):
    """Initial agent registration message."""
    type: Literal[MessageType.HANDSHAKE] = MessageType.HANDSHAKE
    min_app_version: str
    capabilities: list[str]


class SummaryMessage(AgentMessage):
    """Data flush from agent."""
    type: Literal[MessageType.SUMMARY] = MessageType.SUMMARY


class HeartbeatMessage(AgentMessage):
    """Health ping from agent."""
    type: Literal[MessageType.HEARTBEAT] = MessageType.HEARTBEAT
    metrics: dict[str, Any]  # Required for heartbeats


class OrchestratorCommand(BaseModel):
    """Base command envelope for orchestrator → agent commands."""
    cmd: CommandType
    args: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


def parse_agent_message(line: str) -> AgentMessage:
    """Parse JSON line into appropriate message type.
    
    Args:
        line: JSON string from agent stdout
        
    Returns:
        Parsed message object
        
    Raises:
        ValueError: If JSON invalid or type unknown
    """
    import json
    data = json.loads(line)
    msg_type = data.get("type")
    
    if msg_type == MessageType.HANDSHAKE:
        return HandshakeMessage(**data)
    elif msg_type == MessageType.SUMMARY:
        return SummaryMessage(**data)
    elif msg_type == MessageType.HEARTBEAT:
        return HeartbeatMessage(**data)
    else:
        return AgentMessage(**data)
```

**Testing:** Unit tests for message parsing and validation.

---

### Step 1.3: Create Agent Process Manager (`core/agent_process.py` - NEW FILE)
**Status:** New file, handles subprocess lifecycle

```python
"""Field-Agent subprocess management and communication."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any

from mimolo.core.protocol import AgentMessage, OrchestratorCommand, parse_agent_message


@dataclass
class AgentHandle:
    """Runtime handle for a Field-Agent subprocess."""
    
    label: str
    process: subprocess.Popen
    config: Any  # PluginConfig
    
    # Communication queues
    outbound_queue: Queue[AgentMessage] = field(default_factory=Queue)
    
    # State tracking
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None
    agent_id: str | None = None
    health: str = "starting"
    
    # Threads
    _stdout_thread: threading.Thread | None = None
    _running: bool = True
    
    def start_reader(self) -> None:
        """Start stdout reader thread."""
        self._stdout_thread = threading.Thread(
            target=self._read_stdout_loop,
            daemon=True,
            name=f"agent-reader-{self.label}"
        )
        self._stdout_thread.start()
    
    def _read_stdout_loop(self) -> None:
        """Read JSON lines from agent stdout."""
        while self._running and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                # Parse and enqueue message
                msg = parse_agent_message(line)
                self.outbound_queue.put(msg)
                
                # Update heartbeat tracker
                if msg.type == "heartbeat":
                    self.last_heartbeat = msg.timestamp
                    
            except Exception as e:
                # Log error but keep reading
                print(f"[{self.label}] Parse error: {e}")
    
    def send_command(self, cmd: OrchestratorCommand) -> None:
        """Write command to agent stdin."""
        if self.process.poll() is not None:
            return  # Process dead
        
        try:
            json_line = cmd.model_dump_json() + "\n"
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
        except Exception as e:
            print(f"[{self.label}] Command send error: {e}")
    
    def read_message(self, timeout: float = 0.001) -> AgentMessage | None:
        """Non-blocking read from message queue."""
        try:
            return self.outbound_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def is_alive(self) -> bool:
        """Check if process is running."""
        return self.process.poll() is None
    
    def shutdown(self) -> None:
        """Send shutdown command and wait."""
        self._running = False
        self.send_command(OrchestratorCommand(cmd="shutdown"))
        
        # Wait up to 3 seconds for clean exit
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


class AgentProcessManager:
    """Spawns and manages Field-Agent subprocesses."""
    
    def __init__(self, config: Any):  # Config type
        """Initialize manager.
        
        Args:
            config: Main configuration object
        """
        self.config = config
        self.agents: dict[str, AgentHandle] = {}
    
    def spawn_agent(self, label: str, plugin_config: Any) -> AgentHandle:
        """Spawn a Field-Agent subprocess.
        
        Args:
            label: Plugin label
            plugin_config: PluginConfig for this agent
            
        Returns:
            AgentHandle for managing the subprocess
        """
        # Build command
        cmd = [plugin_config.executable] + plugin_config.args
        
        # Spawn process
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )
        
        # Create handle and start reader
        handle = AgentHandle(
            label=label,
            process=proc,
            config=plugin_config
        )
        handle.start_reader()
        
        self.agents[label] = handle
        return handle
    
    def shutdown_all(self) -> None:
        """Shutdown all managed agents."""
        for handle in self.agents.values():
            handle.shutdown()
        self.agents.clear()
```

**Testing:** Create mock agent script that echoes JSON, test spawn/communicate/shutdown.

---

## Phase 2: Dual-Mode Orchestrator (Days 4-7)
**Goal:** Runtime supports both legacy and Field-Agent plugins

### Step 2.1: Create Plugin Adapter (`core/plugin_adapter.py` - NEW FILE)
**Status:** Wraps legacy plugins with Field-Agent interface

```python
"""Adapter to make legacy plugins look like Field-Agents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor
from mimolo.core.protocol import AgentMessage, HeartbeatMessage, SummaryMessage


class LegacyPluginAdapter:
    """Makes a legacy BaseMonitor plugin behave like a Field-Agent.
    
    This adapter:
    - Wraps emit_event() and converts to SummaryMessage
    - Generates synthetic heartbeats
    - Provides consistent interface for orchestrator
    """
    
    def __init__(self, plugin: BaseMonitor, label: str):
        """Initialize adapter.
        
        Args:
            plugin: Legacy plugin instance
            label: Plugin label
        """
        self.plugin = plugin
        self.label = label
        self.agent_id = f"legacy-{label}"
        self.last_heartbeat = datetime.now(UTC)
    
    def emit_event(self) -> Event | None:
        """Call wrapped plugin's emit_event."""
        return self.plugin.emit_event()
    
    def to_summary_message(self, event: Event) -> SummaryMessage:
        """Convert Event to SummaryMessage format.
        
        Args:
            event: Event from legacy plugin
            
        Returns:
            SummaryMessage compatible with Field-Agent protocol
        """
        return SummaryMessage(
            timestamp=event.timestamp,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            data=event.data or {}
        )
    
    def generate_heartbeat(self) -> HeartbeatMessage:
        """Generate synthetic heartbeat for legacy plugin."""
        self.last_heartbeat = datetime.now(UTC)
        return HeartbeatMessage(
            timestamp=self.last_heartbeat,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            metrics={"mode": "legacy", "synthetic": True}
        )
```

**Testing:** Wrap existing FolderWatchMonitor, verify message conversion.

---

### Step 2.2: Extend Runtime to Support Both Types (`core/runtime.py`)
**Status:** Modify existing file incrementally

**Changes needed:**
1. Add `AgentProcessManager` instance
2. During startup, detect plugin type and route accordingly
3. In `_tick()`, poll both legacy plugins AND read Field-Agent queues
4. Convert legacy Events to SummaryMessages internally

**Key modification to `Runtime.__init__`:**
```python
def __init__(self, config: Config, registry: PluginRegistry, console: Console | None = None):
    # ... existing code ...
    
    # NEW: Add Field-Agent support
    from mimolo.core.agent_process import AgentProcessManager
    from mimolo.core.plugin_adapter import LegacyPluginAdapter
    
    self.agent_manager = AgentProcessManager(config)
    self.legacy_adapters: dict[str, LegacyPluginAdapter] = {}
    
    # Wrap legacy plugins
    for spec, instance in registry.list_all():
        adapter = LegacyPluginAdapter(instance, spec.label)
        self.legacy_adapters[spec.label] = adapter
```

**Key modification to `_tick()`:**
```python
def _tick(self) -> None:
    self._tick_count += 1
    current_time = time.time()
    now = datetime.now(UTC)
    
    # Check cooldown
    if self.cooldown.check_expiration(now):
        self._close_segment()
    
    # Poll LEGACY plugins (existing code, adapted)
    for spec, instance in self.registry.list_all():
        if self.error_tracker.is_quarantined(spec.label):
            continue
        
        if not self.scheduler.should_poll(spec.label, spec.poll_interval_s, current_time):
            continue
        
        try:
            adapter = self.legacy_adapters[spec.label]
            event = adapter.emit_event()
            
            if event is not None:
                # Convert to SummaryMessage
                msg = adapter.to_summary_message(event)
                self._handle_agent_message(msg, spec)
                self.error_tracker.record_success(spec.label)
                
        except Exception as e:
            error = PluginEmitError(spec.label, e)
            self.console.print(f"[red]Plugin error: {error}[/red]")
            self.error_tracker.record_error(spec.label)
    
    # Poll FIELD-AGENT messages (NEW)
    for label, handle in self.agent_manager.agents.items():
        while True:
            msg = handle.read_message(timeout=0.001)
            if msg is None:
                break
            
            # Route by message type
            if msg.type == "heartbeat":
                self._handle_heartbeat(label, msg)
            elif msg.type == "summary":
                # Look up spec (need to extend registry or maintain separate dict)
                self._handle_agent_summary(label, msg)
            elif msg.type == "error":
                self.console.print(f"[red]Agent {label} error: {msg.message}[/red]")
```

**Testing:** Run with only legacy plugins - should behave identically to v0.2.

---

### Step 2.3: Discover and Load user_plugins (`core/registry.py`)
**Status:** Extend existing plugin discovery

**Add to `PluginRegistry`:**
```python
def discover_user_plugins(self, user_plugins_dir: Path) -> None:
    """Discover Field-Agent plugins in user_plugins directory.
    
    Args:
        user_plugins_dir: Path to user_plugins directory
    """
    # Scan for agent_*.py files
    for agent_file in user_plugins_dir.glob("agent_*.py"):
        if agent_file.name.startswith("agent_"):
            # Extract label from filename: agent_folderwatch.py → folderwatch
            label = agent_file.stem.replace("agent_", "")
            
            # Register as Field-Agent type (store differently or flag in registry)
            # This will be expanded in Phase 3
            pass
```

**Testing:** Create dummy `agent_test.py`, verify discovery.

---

## Phase 3: First Field-Agent Plugins (Days 8-12)
**Goal:** Create three working Field-Agent examples

### Step 3.1: Create BaseFieldAgent Template (`user_plugins/base_agent.py`)

```python
"""Base class for Field-Agent plugins."""

import json
import sys
import threading
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any


class BaseFieldAgent(ABC):
    """Base class for MiMoLo Field-Agent plugins.
    
    Subclasses must implement:
    - sample() → returns data to accumulate
    - summarize(accumulated_data) → returns summary dict for flush
    """
    
    def __init__(
        self,
        label: str,
        agent_version: str = "1.0.0",
        poll_interval_s: float = 5.0,
        heartbeat_interval_s: float = 15.0
    ):
        """Initialize Field-Agent.
        
        Args:
            label: Plugin label
            agent_version: Version string
            poll_interval_s: How often to sample
            heartbeat_interval_s: How often to send heartbeat
        """
        self.label = label
        self.agent_version = agent_version
        self.agent_id = f"{label}-{int(time.time())}"
        self.poll_interval_s = poll_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s
        
        # State
        self.running = True
        self.accumulated_data: list[Any] = []
        self.data_lock = threading.Lock()
        self.flush_event = threading.Event()
        
        # Threads
        self.cmd_thread = threading.Thread(target=self._command_listener, daemon=True)
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
    
    def run(self) -> None:
        """Start all three cooperative loops."""
        # Send handshake
        self._send_handshake()
        
        # Start threads
        self.cmd_thread.start()
        self.worker_thread.start()
        self.heartbeat_thread.start()
        
        # Wait for shutdown
        self.cmd_thread.join()
        self.worker_thread.join()
        self.heartbeat_thread.join()
    
    def _send_handshake(self) -> None:
        """Send initial handshake message."""
        msg = {
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.label,
            "protocol_version": "0.3",
            "agent_version": self.agent_version,
            "min_app_version": "0.3.0",
            "capabilities": ["summary", "heartbeat", "status"],
            "data": {}
        }
        self._write_stdout(msg)
    
    def _command_listener(self) -> None:
        """Read commands from stdin."""
        for line in sys.stdin:
            try:
                cmd = json.loads(line.strip())
                cmd_type = cmd.get("cmd")
                
                if cmd_type == "flush":
                    self.flush_event.set()
                elif cmd_type == "shutdown":
                    self.running = False
                    break
                    
            except Exception:
                pass  # Ignore invalid commands
    
    def _worker_loop(self) -> None:
        """Sample data periodically."""
        while self.running:
            try:
                data = self.sample()
                if data is not None:
                    with self.data_lock:
                        self.accumulated_data.append(data)
            except Exception:
                pass  # Log or emit error message
            
            time.sleep(self.poll_interval_s)
    
    def _heartbeat_loop(self) -> None:
        """Send heartbeats and handle flush."""
        while self.running:
            # Send heartbeat
            self._send_heartbeat()
            
            # Check for flush request
            if self.flush_event.wait(timeout=self.heartbeat_interval_s):
                self._emit_summary()
                self.flush_event.clear()
    
    def _send_heartbeat(self) -> None:
        """Emit heartbeat message."""
        msg = {
            "type": "heartbeat",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.label,
            "protocol_version": "0.3",
            "agent_version": self.agent_version,
            "data": {},
            "metrics": {"queue": len(self.accumulated_data)}
        }
        self._write_stdout(msg)
    
    def _emit_summary(self) -> None:
        """Emit summary message."""
        with self.data_lock:
            data_copy = self.accumulated_data.copy()
            self.accumulated_data.clear()
        
        summary_data = self.summarize(data_copy)
        
        msg = {
            "type": "summary",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.label,
            "protocol_version": "0.3",
            "agent_version": self.agent_version,
            "data": summary_data
        }
        self._write_stdout(msg)
    
    def _write_stdout(self, msg: dict) -> None:
        """Write JSON message to stdout."""
        print(json.dumps(msg), flush=True)
    
    @abstractmethod
    def sample(self) -> Any:
        """Sample/observe and return data.
        
        Called every poll_interval_s.
        Return None if nothing to report.
        
        Returns:
            Data to accumulate (any type)
        """
        ...
    
    @abstractmethod
    def summarize(self, accumulated_data: list[Any]) -> dict[str, Any]:
        """Aggregate accumulated data into summary.
        
        Called on flush.
        
        Args:
            accumulated_data: List of samples collected since last flush
            
        Returns:
            Dictionary for summary message data field
        """
        ...
```

---

### Step 3.2: Port FolderWatch to Field-Agent (`user_plugins/agent_folderwatch.py`)

```python
#!/usr/bin/env python
"""Field-Agent: Folder modification watcher."""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mimolo.user_plugins.base_agent import BaseFieldAgent


class FolderWatchAgent(BaseFieldAgent):
    """Watches folders for file modifications."""
    
    def __init__(self, watch_dirs: list[str], extensions: list[str]):
        super().__init__(
            label="folderwatch",
            agent_version="1.0.0",
            poll_interval_s=5.0,
            heartbeat_interval_s=15.0
        )
        self.watch_dirs = [Path(d) for d in watch_dirs]
        self.extensions = set(extensions)
        self._last_mtimes: dict[Path, float] = {}
    
    def sample(self) -> list[str] | None:
        """Check for modified files."""
        modified_folders = set()
        
        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue
            
            for file_path in watch_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                
                if file_path.suffix not in self.extensions:
                    continue
                
                try:
                    mtime = file_path.stat().st_mtime
                    last_mtime = self._last_mtimes.get(file_path, 0.0)
                    
                    if mtime > last_mtime:
                        modified_folders.add(str(file_path.parent.resolve()))
                        self._last_mtimes[file_path] = mtime
                        
                except OSError:
                    pass
        
        return list(modified_folders) if modified_folders else None
    
    def summarize(self, accumulated_data: list[Any]) -> dict[str, Any]:
        """Flatten and deduplicate folder list."""
        all_folders = set()
        for item in accumulated_data:
            if isinstance(item, list):
                all_folders.update(item)
        
        return {"folders": sorted(all_folders)}


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch-dirs", nargs="+", required=True)
    parser.add_argument("--extensions", nargs="+", default=[".blend", ".py"])
    args = parser.parse_args()
    
    agent = FolderWatchAgent(args.watch_dirs, args.extensions)
    agent.run()
```

---

### Step 3.3: Create agent_example.py and agent_template.py

Similar structure - I can provide these if needed.

---

## Phase 4: Testing & Refinement (Days 13-15)

### Checkpoint Tests:
1. ✅ Legacy plugins still work exactly as before
2. ✅ Field-Agent plugins spawn, handshake, and emit messages
3. ✅ Both types participate in segment aggregation
4. ✅ Cooldown timer works with both types
5. ✅ Graceful shutdown works for both

### Configuration example (mimolo.toml):
```toml
[monitor]
cooldown_seconds = 600
journal_dir = "./journals"

[plugins.folderwatch]
enabled = true
plugin_type = "field_agent"
executable = "python"
args = ["-m", "mimolo.user_plugins.agent_folderwatch", "--watch-dirs", "/projects"]
resets_cooldown = true
```

---

## Success Criteria for Phase 1-3:

- [ ] `mimolo monitor` starts successfully
- [ ] Legacy plugins in `mimolo/plugins/` still work
- [ ] Field-Agent plugins in `mimolo/user_plugins/` spawn as subprocesses
- [ ] Both types emit events that appear in segments
- [ ] Shutdown is clean for all plugin types
- [ ] Tests pass for both legacy and Field-Agent paths

---

## Future Phases (Weeks 3-4+):

**Phase 5:** Journal event stream writer  
**Phase 6:** Dashboard bridge  
**Phase 7:** Advanced agent features (self-tuning, metrics)  
**Phase 8:** Deprecate legacy plugins, migrate all to Field-Agents

---

## Why This Approach Works:

✅ **No "big bang" rewrite** - working code at every step  
✅ **Incremental testing** - can validate each change  
✅ **Backward compatible** - legacy plugins never break  
✅ **Forward looking** - Field-Agents are the future, but coexist during transition  
✅ **Risk mitigation** - can pause or rollback at any checkpoint  

This is a **production-grade migration strategy** rather than a research prototype approach.
