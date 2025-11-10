# Data Access Patterns

> **Document Version:** 0.3  
> **Target Framework:** MiMoLo v0.3+  
> **Last Updated:** November 2025  
> **Status:** Draft specification

---

## 1. Overview

Dashboard data access is **dead simple**:

1. **Read Log Files** — Parse daily JSONL files from `~/.mimolo/logs/`
2. **Read Cache File** — Load current activity from `~/.mimolo/cache/current.json`
3. **Spawn/Kill Process** — Use `subprocess.Popen()` to control orchestrator

**No subscriptions. No streaming. No protocols. Just files and processes.**

---

## 2. Reading Historical Segments

### 2.1 Read Single Day

```python
import json
from pathlib import Path

def read_segments_for_date(date_str):
    """Read all segments from a specific date's JSONL log."""
    log_path = Path.home() / ".mimolo" / "logs" / f"mimolo_{date_str}.jsonl"
    
    if not log_path.exists():
        return []
    
    segments = []
    with open(log_path) as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))
    
    return segments

# Usage
segments = read_segments_for_date("2025-11-09")
print(f"Found {len(segments)} segments")
```

### 2.2 Read Date Range

```python
from datetime import date, timedelta

def read_segments_for_range(start_date, end_date):
    """Read all segments within a date range."""
    segments = []
    current = start_date
    
    while current <= end_date:
        date_str = current.isoformat()
        segments.extend(read_segments_for_date(date_str))
        current += timedelta(days=1)
    
    return segments

# Usage - get all November segments
segments = read_segments_for_range(
    date(2025, 11, 1),
    date(2025, 11, 30)
)
print(f"Total hours: {sum(s['duration_s'] for s in segments) / 3600:.1f}")
```

### 2.3 Iterate Through Log Directory

```python
def find_all_log_files():
    """Find all JSONL log files."""
    log_dir = Path.home() / ".mimolo" / "logs"
    return sorted(log_dir.glob("mimolo_*.jsonl"))

def read_all_segments():
    """Read every segment from all log files."""
    segments = []
    for log_file in find_all_log_files():
        with open(log_file) as f:
            for line in f:
                if line.strip():
                    segments.append(json.loads(line))
    return segments
```

---

## 3. Reading Current Activity

### 3.1 Cache File Structure

The Orchestrator maintains a cache at `~/.mimolo/cache/current.json`:

```json
{
  "last_closed": {
    "segment_id": "seg_044",
    "start": "2025-11-09T13:00:00Z",
    "end": "2025-11-09T14:15:00Z",
    "duration_s": 4500,
    "agents": {...}
  },
  "active": {
    "start": "2025-11-09T14:30:00Z",
    "duration_s": 1234,
    "agents": {...}
  }
}
```

### 3.2 Read Cache File

```python
def read_current_activity():
    """Read cached current state."""
    cache_path = Path.home() / ".mimolo" / "cache" / "current.json"
    
    if not cache_path.exists():
        return None
    
    with open(cache_path) as f:
        return json.load(f)

# Usage
current = read_current_activity()
if current:
    if current.get('active'):
        active = current['active']
        elapsed_h = active['duration_s'] / 3600
        print(f"Currently working: {elapsed_h:.1f} hours")
    else:
        print("Currently idle")
```

### 3.3 Display Current Dashboard State

```python
def display_dashboard():
    """Simple dashboard display."""
    current = read_current_activity()
    
    if not current:
        print("Orchestrator not running")
        return
    
    # Show last completed segment
    if current.get('last_closed'):
        last = current['last_closed']
        duration_h = last['duration_s'] / 3600
        print(f"Last segment: {duration_h:.1f}h, ended {last['end']}")
    
    # Show current activity
    if current.get('active'):
        active = current['active']
        elapsed_h = active['duration_s'] / 3600
        agents = ', '.join(active['agents'].keys())
        print(f"Active: {elapsed_h:.1f}h, agents: {agents}")
    else:
        print("Status: Idle")
```

---

## 4. Process Management

### 4.1 Start Orchestrator

```python
import subprocess

def start_orchestrator():
    """Launch orchestrator as subprocess."""
    proc = subprocess.Popen(
        ["mimolo", "monitor"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"Orchestrator started (PID: {proc.pid})")
    return proc
```

### 4.2 Stop Orchestrator

```python
def stop_orchestrator(proc, timeout=10):
    """Gracefully stop orchestrator."""
    proc.terminate()  # Send SIGTERM
    try:
        proc.wait(timeout=timeout)
        print("Orchestrator stopped")
    except subprocess.TimeoutExpired:
        proc.kill()  # Force kill if timeout
        print("Orchestrator killed (timeout)")
```

### 4.3 Check if Running

```python
import psutil

def is_orchestrator_running():
    """Check if orchestrator process exists."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if 'mimolo' in proc.info['name']:
                cmdline = proc.info.get('cmdline', [])
                if 'monitor' in cmdline:
                    return True, proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False, None

# Usage
running, pid = is_orchestrator_running()
if running:
    print(f"Orchestrator running (PID: {pid})")
else:
    print("Orchestrator not running")
```

---

## 5. Combined Example: Full Dashboard State

```python
class SimpleDashboard:
    def __init__(self):
        self.orchestrator_proc = None
    
    def start(self):
        """Launch orchestrator."""
        self.orchestrator_proc = start_orchestrator()
    
    def stop(self):
        """Stop orchestrator."""
        if self.orchestrator_proc:
            stop_orchestrator(self.orchestrator_proc)
            self.orchestrator_proc = None
    
    def get_status(self):
        """Get current status."""
        running, pid = is_orchestrator_running()
        current = read_current_activity()
        
        return {
            'orchestrator_running': running,
            'orchestrator_pid': pid,
            'current_activity': current
        }
    
    def generate_invoice(self, start_date, end_date, rate=75.0):
        """Generate invoice from logs."""
        segments = read_segments_for_range(start_date, end_date)
        total_hours = sum(s['duration_s'] for s in segments) / 3600
        return {
            'period': f"{start_date} to {end_date}",
            'total_hours': round(total_hours, 2),
            'rate': rate,
            'amount': round(total_hours * rate, 2)
        }
```

---

## Summary

Dashboard data access = **3 simple operations**:

1. **`open("mimolo_YYYY-MM-DD.jsonl")`** — Read historical segments
2. **`json.load("current.json")`** — Read current activity
3. **`subprocess.Popen(["mimolo", "monitor"])`** — Control orchestrator

**No protocols. No subscriptions. No streaming. Just files and processes.**
