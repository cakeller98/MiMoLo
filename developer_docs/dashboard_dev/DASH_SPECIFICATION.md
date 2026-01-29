# Dashboard Specification

> **Document Version:** 0.3  
> **Target Framework:** MiMoLo v0.3+  
> **Last Updated:** November 2025  
> **Status:** Specification

---

## 1. Overview

The Dashboard is MiMoLo's human-facing interface for monitoring, reporting, and controlling the Orchestrator and its Agents.

### Core Principle: Separation of Concerns

**Dashboard reads data directly from files.**  
**Dashboard sends commands via bi-directional bridge.**  
**No redundant data transport.**

```
Dashboard Responsibilities:
├── Read daily_journal_YYYYMMDD.jsonl (historic data)
├── Read current_segment.json cache (TODAY's partial data)
├── Query Orchestrator status (agent health, config, runtime info)
├── Send control commands (start/stop monitors, restart agents, modify config)
└── Launch report plugins (subprocess with segment data via stdin)

Orchestrator Responsibilities:
├── Write daily_journal_YYYYMMDD.jsonl (every flush from agents)
├── Write current_segment.json cache (partial segment before final write)
├── Respond to status queries (agent health, registered plugins, runtime metrics)
├── Accept control commands (lifecycle, config changes)
└── Manage Agents (spawn, monitor, throttle, restart)
```

**Key Insight:**  
The Dashboard never asks the Orchestrator to "send segment data" because the Dashboard can read the journal files directly. The Orchestrator only provides information it uniquely knows: runtime state, agent health, and in-flight partial segments.

---

## 2. Data Access Patterns

### 2.1 Historical Data (Read from Journal Files)

**File Location:** `~/.mimolo/journals/daily_journal_YYYYMMDD.jsonl`

**Format:** Newline-delimited JSON (JSONL), one event per line

**Event Types:**
```jsonl
{"type":"segment_start","timestamp":"2025-11-09T08:00:00Z","segment_id":"seg_001"}
{"type":"summary","agent":"creo_trail_watcher","data":{"active_files":["trail.txt.1"]},"timestamp":"2025-11-09T08:05:00Z"}
{"type":"summary","agent":"folder_watcher","data":{"folders":{"C:/Projects/ClientA":3}},"timestamp":"2025-11-09T08:05:00Z"}
{"type":"summary","agent":"creo_trail_watcher","data":{"active_files":["trail.txt.1","trail.txt.2"]},"timestamp":"2025-11-09T08:10:00Z"}
{"type":"segment_close","timestamp":"2025-11-09T08:30:00Z","segment_id":"seg_001","duration_s":1800}
{"type":"idle_start","timestamp":"2025-11-09T08:30:00Z"}
{"type":"segment_start","timestamp":"2025-11-09T09:45:00Z","segment_id":"seg_002"}
```

**Reading Historical Segments:**

```python
import json
from pathlib import Path
from datetime import date, timedelta

def read_journal_events(date_str):
    """Read all events from a specific date's journal file."""
    journal_path = Path.home() / ".mimolo" / "journals" / f"daily_journal_{date_str.replace('-', '')}.jsonl"
    
    if not journal_path.exists():
        return []
    
    events = []
    with open(journal_path) as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    
    return events

def synthesize_segments_from_events(events):
    """Convert event stream into complete segments.
    
    Report plugins will do this synthesis to reconstruct work periods.
    """
    segments = []
    current_segment = None
    
    for event in events:
        if event['type'] == 'segment_start':
            current_segment = {
                'segment_id': event['segment_id'],
                'start': event['timestamp'],
                'summaries': []
            }
        
        elif event['type'] == 'summary' and current_segment:
            current_segment['summaries'].append(event)
        
        elif event['type'] == 'segment_close' and current_segment:
            current_segment['end'] = event['timestamp']
            current_segment['duration_s'] = event['duration_s']
            segments.append(current_segment)
            current_segment = None
    
    return segments

# Usage
events = read_journal_events("2025-11-09")
segments = synthesize_segments_from_events(events)
print(f"Found {len(segments)} complete segments")
```

**Key Points:**
- Dashboard reads raw event stream from journal files
- Report plugins synthesize segments from events (not Dashboard's job)
- Every flush is logged as a separate summary event
- Minimal time between flushes prevents spam (configured per-agent)
- Heartbeats are NOT recorded in journal (too noisy, only for runtime health)

---

### 2.2 Current Activity (Read from Cache File)

**File Location:** `~/.mimolo/cache/current_segment.json`

**Purpose:** Provides TODAY's in-progress segment before it's written to journal

**Format:**
```json
{
  "last_closed": {
    "segment_id": "seg_044",
    "start": "2025-11-09T13:00:00Z",
    "end": "2025-11-09T14:15:00Z",
    "duration_s": 4500,
    "summaries": [
      {"agent":"creo_trail_watcher","data":{...},"timestamp":"2025-11-09T13:05:00Z"},
      {"agent":"folder_watcher","data":{...},"timestamp":"2025-11-09T13:05:00Z"}
    ]
  },
  "active": {
    "segment_id": "seg_045",
    "start": "2025-11-09T14:30:00Z",
    "elapsed_s": 1234,
    "summaries": [
      {"agent":"creo_trail_watcher","data":{...},"timestamp":"2025-11-09T14:35:00Z"}
    ]
  },
  "last_updated": "2025-11-09T14:50:23Z"
}
```

**Reading Current Activity:**

```python
def read_current_segment():
    """Read cached current segment (TODAY's partial data)."""
    cache_path = Path.home() / ".mimolo" / "cache" / "current_segment.json"
    
    if not cache_path.exists():
        return None
    
    with open(cache_path) as f:
        return json.load(f)

# Usage
current = read_current_segment()
if current and current.get('active'):
    elapsed_h = current['active']['elapsed_s'] / 3600
    summary_count = len(current['active']['summaries'])
    print(f"Currently working: {elapsed_h:.1f}h, {summary_count} summaries")
else:
    print("Currently idle")
```

**Key Points:**
- Cache updated by Orchestrator on every flush
- Contains last closed segment + current partial segment
- Dashboard reads this file directly (no Orchestrator query needed)
- File updated frequently but not written to journal until segment closes

---

## 3. Dashboard-Orchestrator Bridge Protocol

### 3.1 Communication Pattern

**Transport:** IPC socket, HTTP, or WebSocket (implementation choice)  
**Direction:** Bi-directional  
**Purpose:** Commands and status queries ONLY (not data transport)

**What the Dashboard Queries:**
- Agent health and registered plugins
- Configuration values
- Runtime metrics (CPU, memory usage)
- Process IDs and lifecycle state

**What the Dashboard Commands:**
- Start/stop "the monitors" (all Agents)
- Restart individual agents
- Modify configuration (poll intervals, watch folders, etc.)
- Trigger forced flush

**What the Dashboard Does NOT Query:**
- Segment data (reads journals directly)
- Historical summaries (reads journals directly)
- Current partial segment (reads cache file directly)

---

### 3.2 Command Messages (Dashboard → Orchestrator)

#### Start All Monitors
```json
{"cmd":"start_monitors"}
```

**Response:**
```json
{"type":"ack","result":"monitors_started","agents_started":["creo_trail_watcher","folder_watcher","designated_screenshot"],"timestamp":"2025-11-09T15:00:00Z"}
```

---

#### Stop All Monitors
```json
{"cmd":"stop_monitors"}
```

**Response:**
```json
{"type":"ack","result":"monitors_stopped","timestamp":"2025-11-09T15:05:00Z"}
```

---

#### Restart Specific Agent
```json
{"cmd":"restart_agent","agent":"creo_trail_watcher"}
```

**Response:**
```json
{"type":"ack","result":"agent_restarted","agent":"creo_trail_watcher","new_pid":12345,"timestamp":"2025-11-09T15:10:00Z"}
```

---

#### Get Agent Status
```json
{"cmd":"get_agent_status"}
```

**Response:**
```json
{
  "type":"agent_status",
  "timestamp":"2025-11-09T15:15:00Z",
  "agents":[
    {
      "label":"creo_trail_watcher",
      "health":"ok",
      "pid":12345,
      "uptime_s":3600,
      "cpu_percent":0.002,
      "mem_mb":4.5,
      "last_heartbeat":"2025-11-09T15:15:00Z"
    },
    {
      "label":"folder_watcher",
      "health":"degraded",
      "pid":12346,
      "uptime_s":3600,
      "cpu_percent":0.008,
      "mem_mb":15.2,
      "last_heartbeat":"2025-11-09T15:14:45Z"
    }
  ]
}
```

---

#### Get Registered Plugins
```json
{"cmd":"get_registered_plugins"}
```

**Response:**
```json
{
  "type":"registered_plugins",
  "plugins":[
    {
      "label":"creo_trail_watcher",
      "enabled":true,
      "executable":"mimolo_creo_trail.exe",
      "poll_interval_s":15.0
    },
    {
      "label":"folder_watcher",
      "enabled":true,
      "executable":"python",
      "args":["-m","mimolo.plugins.folder_watcher"],
      "poll_interval_s":10.0
    }
  ]
}
```

---

#### Update Configuration
```json
{
  "cmd":"update_config",
  "plugin":"folder_watcher",
  "params":{
    "watch_dirs":["C:/Projects/ClientWork","D:/Backup/ClientWork"],
    "extensions":[".prt",".asm",".drw"]
  }
}
```

**Response:**
```json
{"type":"ack","result":"config_updated","plugin":"folder_watcher","restart_required":true}
```

---

#### Force Flush
```json
{"cmd":"force_flush","agent":"creo_trail_watcher"}
```

**Response:**
```json
{"type":"ack","result":"flush_sent","agent":"creo_trail_watcher"}
```

---

### 3.3 Error Responses

```json
{
  "type":"error",
  "message":"agent not found",
  "agent":"invalid_agent_name",
  "timestamp":"2025-11-09T15:20:00Z"
}
```

---

## 4. Dashboard Report Plugins

### 4.1 Plugin Architecture

**Report plugins are subprocesses** spawned by the Dashboard to generate outputs (PDF, CSV, video, etc.).

**Communication:** stdin (command + segment data) → stdout (progress + result)

**Key Principle:**  
Dashboard reads journal files, synthesizes segments, then feeds segment data to report plugins. Plugins never read journals directly (Dashboard does the I/O).

---

### 4.2 Report Plugin Protocol

#### Dashboard → Plugin (stdin)

```json
{
  "cmd":"generate",
  "output_type":"invoice",
  "params":{
    "start_date":"2025-11-01",
    "end_date":"2025-11-30",
    "hourly_rate":75.0,
    "output_path":"/tmp/invoice_nov2025.pdf"
  },
  "segments":[
    {
      "segment_id":"seg_001",
      "start":"2025-11-09T08:00:00Z",
      "end":"2025-11-09T08:30:00Z",
      "duration_s":1800,
      "summaries":[...]
    }
  ]
}
```

#### Plugin → Dashboard (stdout)

**Progress Updates:**
```json
{"type":"progress","percent":25,"message":"Rendering page 2 of 8"}
{"type":"progress","percent":75,"message":"Rendering page 6 of 8"}
```

**Final Result:**
```json
{
  "type":"result",
  "success":true,
  "output_path":"/tmp/invoice_nov2025.pdf",
  "metadata":{
    "total_hours":152.5,
    "total_amount":11437.50,
    "segment_count":45
  }
}
```

**Error:**
```json
{
  "type":"error",
  "message":"Failed to render PDF: missing font",
  "recoverable":false
}
```

---

### 4.3 Built-In Report Plugins

#### Invoice Generator
- **Input:** Date range, hourly rate, segments
- **Output:** PDF invoice with total hours and amount due
- **Template:** Jinja2 template (user-editable)

#### Timecard Generator
- **Input:** Date range, segments
- **Output:** PDF/Markdown timecard with daily breakdown
- **Template:** Jinja2 template (user-editable)

#### CSV Exporter
- **Input:** Segments
- **Output:** CSV file with columns: date, start, end, duration_h, agents
- **No template** (raw data export)

#### Timelapse Video Generator
- **Input:** Segments + screenshot paths (from designated_screenshot agent)
- **Output:** MP4 video stitching screenshots with timestamps
- **Dependencies:** ffmpeg, PIL
- **Resource limit:** Higher CPU budget (video encoding is intensive)

---

### 4.4 Report Plugin Example Implementation

```python
#!/usr/bin/env python3
"""
Invoice generator report plugin.
Reads segment data from stdin, generates PDF invoice, writes result to stdout.
"""
import json
import sys
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

def generate_invoice_pdf(segments, hourly_rate, output_path):
    """Generate PDF invoice from segments."""
    total_seconds = sum(seg['duration_s'] for seg in segments)
    total_hours = total_seconds / 3600
    total_amount = total_hours * hourly_rate
    
    # Create PDF
    c = canvas.Canvas(output_path, pagesize=letter)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "Invoice")
    
    c.setFont("Helvetica", 12)
    c.drawString(100, 700, f"Period: {segments[0]['start'][:10]} to {segments[-1]['end'][:10]}")
    c.drawString(100, 680, f"Total Hours: {total_hours:.2f}")
    c.drawString(100, 660, f"Hourly Rate: ${hourly_rate:.2f}")
    c.drawString(100, 640, f"Total Amount: ${total_amount:.2f}")
    
    c.save()
    
    return {
        'total_hours': total_hours,
        'total_amount': total_amount,
        'segment_count': len(segments)
    }

def main():
    # Read command from stdin
    command = json.loads(sys.stdin.readline())
    
    if command['cmd'] != 'generate':
        sys.stdout.write(json.dumps({
            'type': 'error',
            'message': 'Invalid command'
        }) + '\n')
        sys.exit(1)
    
    segments = command['segments']
    hourly_rate = command['params']['hourly_rate']
    output_path = command['params']['output_path']
    
    # Emit progress
    sys.stdout.write(json.dumps({
        'type': 'progress',
        'percent': 0,
        'message': 'Starting PDF generation'
    }) + '\n')
    sys.stdout.flush()
    
    # Generate invoice
    metadata = generate_invoice_pdf(segments, hourly_rate, output_path)
    
    # Emit progress
    sys.stdout.write(json.dumps({
        'type': 'progress',
        'percent': 100,
        'message': 'PDF generation complete'
    }) + '\n')
    sys.stdout.flush()
    
    # Emit result
    sys.stdout.write(json.dumps({
        'type': 'result',
        'success': True,
        'output_path': output_path,
        'metadata': metadata
    }) + '\n')
    sys.stdout.flush()

if __name__ == '__main__':
    main()
```

---

## 5. Dashboard Process Management

### 5.1 Start Orchestrator

```python
import subprocess

def start_orchestrator():
    """Launch orchestrator as subprocess."""
    proc = subprocess.Popen(
        ["mimolo", "orchestrator"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"Orchestrator started (PID: {proc.pid})")
    return proc
```

---

### 5.2 Stop Orchestrator

```python
def stop_orchestrator(proc, timeout=10):
    """Gracefully stop orchestrator."""
    proc.terminate()  # Send SIGTERM
    try:
        proc.wait(timeout=timeout)
        print("Orchestrator stopped gracefully")
    except subprocess.TimeoutExpired:
        proc.kill()  # Force kill if timeout
        print("Orchestrator killed (timeout)")
```

---

### 5.3 Check if Running

```python
import psutil

def is_orchestrator_running():
    """Check if orchestrator process exists."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'mimolo' in proc.info['name']:
                cmdline = proc.info.get('cmdline', [])
                if 'orchestrator' in cmdline:
                    return True, proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, None
```

---

## 6. Complete Dashboard Example

```python
class MiMoLoDashboard:
    """Simple dashboard implementation."""
    
    def __init__(self):
        self.orchestrator_proc = None
        self.bridge = None  # IPC/HTTP/WebSocket connection
    
    def start_monitoring(self):
        """Start orchestrator and all monitors."""
        # Launch orchestrator process
        self.orchestrator_proc = start_orchestrator()
        
        # Connect to bridge
        self.bridge = connect_to_orchestrator()  # Implementation-specific
        
        # Start all Agents
        response = self.bridge.send_command({"cmd":"start_monitors"})
        print(f"Monitors started: {response['agents_started']}")
    
    def stop_monitoring(self):
        """Stop all monitors and orchestrator."""
        if self.bridge:
            self.bridge.send_command({"cmd":"stop_monitors"})
        
        if self.orchestrator_proc:
            stop_orchestrator(self.orchestrator_proc)
    
    def get_current_activity(self):
        """Read current activity from cache file."""
        return read_current_segment()
    
    def get_agent_health(self):
        """Query orchestrator for agent health."""
        if not self.bridge:
            return None
        
        response = self.bridge.send_command({"cmd":"get_agent_status"})
        return response['agents']
    
    def generate_invoice(self, start_date, end_date, hourly_rate=75.0):
        """Generate invoice by reading journals and spawning plugin."""
        # Read journal files directly
        events = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y%m%d")
            events.extend(read_journal_events(date_str))
            current += timedelta(days=1)
        
        # Synthesize segments
        segments = synthesize_segments_from_events(events)
        
        # Spawn invoice plugin
        plugin_proc = subprocess.Popen(
            ["mimolo-plugin-invoice"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        
        # Send command
        command = {
            'cmd': 'generate',
            'output_type': 'invoice',
            'params': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'hourly_rate': hourly_rate,
                'output_path': f'/tmp/invoice_{start_date}_{end_date}.pdf'
            },
            'segments': segments
        }
        
        plugin_proc.stdin.write(json.dumps(command) + '\n')
        plugin_proc.stdin.flush()
        
        # Read progress and result
        for line in plugin_proc.stdout:
            message = json.loads(line)
            if message['type'] == 'progress':
                print(f"Progress: {message['percent']}% - {message['message']}")
            elif message['type'] == 'result':
                print(f"Invoice generated: {message['output_path']}")
                return message
        
        plugin_proc.wait()
```

---

## 7. Summary

### Dashboard Data Flow

```
Historical Data:
  Dashboard → read daily_journal_YYYYMMDD.jsonl → synthesize segments → feed to report plugins

Current Activity:
  Dashboard → read current_segment.json cache → display in UI

Agent Status:
  Dashboard → query Orchestrator via bridge → display health/metrics

Control:
  Dashboard → send commands via bridge → Orchestrator executes → Dashboard receives ack
```

### Key Principles

1. **No Redundant Data Transport**  
   Dashboard reads journal files directly. Orchestrator never sends segment data over the bridge.

2. **Bi-Directional Bridge for Commands Only**  
   Dashboard queries runtime state (agent health, config) and sends control commands (start/stop, restart, config changes).

3. **Report Plugins as Subprocesses**  
   Dashboard handles I/O (reading journals), plugins handle rendering (PDF, video, CSV).

4. **Cache File for Current Segment**  
   Orchestrator maintains `current_segment.json` with in-progress data. Dashboard reads it directly.

5. **Event-Based Journal Format**  
   Journal contains raw events (segment_start, summary, segment_close, idle_start). Report plugins synthesize complete segments from event streams.

---

## 8. Implementation Checklist

- [ ] Journal reader: parse JSONL events from `daily_journal_YYYYMMDD.jsonl`
- [ ] Segment synthesizer: convert event stream to complete segments
- [ ] Cache reader: parse `current_segment.json` for TODAY's partial data
- [ ] Bridge client: connect to Orchestrator (IPC/HTTP/WebSocket)
- [ ] Command sender: start/stop monitors, restart agents, update config
- [ ] Status display: show agent health, current activity, elapsed time
- [ ] Report plugin spawner: launch subprocess, send segment data via stdin
- [ ] Progress handler: read plugin stdout for progress updates
- [ ] Process manager: start/stop Orchestrator subprocess
- [ ] Configuration editor: modify TOML, trigger Orchestrator reload

---

**Dashboard = File Reader + Command Sender + Plugin Spawner**  
**No redundant data transport. No over-engineering. Just the essentials.**
