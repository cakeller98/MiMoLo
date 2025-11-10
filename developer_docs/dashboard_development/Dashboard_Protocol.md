# Dashboard Specification

> **Document Version:** 0.3  
> **Target Framework:** MiMoLo v0.3+  
> **Last Updated:** November 2025  
> **Status:** Draft specification

---

## 1. Overview

The Dashboard is a **simple UI wrapper** around MiMoLo's Orchestrator and its JSONL log files.

**Three purposes only:**
1. **Launch/Kill Orchestrator** — Start/stop the monitor process
2. **Generate Reports** — Read daily rotating JSONL logs to create invoices/timecards
3. **Display Current Activity** — Show active segment from cached journal (last closed segment + today's partial data)

**No real-time monitoring. No subscriptions. No streaming. Just file reading and process management.**

---

## 2. Core Operations

### 2.1 Process Management

**Start Orchestrator:**
```python
import subprocess
orchestrator_proc = subprocess.Popen(
    ["mimolo", "monitor"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
```

**Stop Orchestrator:**
```python
orchestrator_proc.terminate()  # SIGTERM
orchestrator_proc.wait(timeout=10)
```

**Check if Running:**
```python
import psutil
def is_orchestrator_running():
    for proc in psutil.process_iter(['name', 'cmdline']):
        if 'mimolo' in proc.info['name'] and 'monitor' in proc.info['cmdline']:
            return True
    return False
```

---

## 3. Reading Log Files

### 3.1 Log File Structure

Daily rotating JSONL files in `~/.mimolo/logs/`:
```
mimolo_2025-11-09.jsonl
mimolo_2025-11-08.jsonl
mimolo_2025-11-07.jsonl
```

Each line is a complete segment JSON object:
```json
{"segment_id":"seg_045","start":"2025-11-09T09:45:00Z","end":"2025-11-09T10:15:00Z","duration_s":1800,"agents":{"folderwatch":{"folders":["/projects"]}}}
```

### 3.2 Reading Historical Data

```python
import json
from pathlib import Path

def read_segments(date):
    """Read all segments from a specific date's log."""
    log_path = Path.home() / ".mimolo" / "logs" / f"mimolo_{date}.jsonl"
    
    if not log_path.exists():
        return []
    
    segments = []
    with open(log_path) as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))
    
    return segments

# Get all November segments
from datetime import date, timedelta

nov_segments = []
current = date(2025, 11, 1)
while current.month == 11:
    nov_segments.extend(read_segments(current.isoformat()))
    current += timedelta(days=1)
```

### 3.3 Reading Current Activity

The Orchestrator writes a **cache file** with the last closed segment and current partial data:

```python
def read_current_activity():
    """Read cached current state (no orchestrator communication needed)."""
    cache_path = Path.home() / ".mimolo" / "cache" / "current.json"
    
    if not cache_path.exists():
        return None
    
    with open(cache_path) as f:
        return json.load(f)

# Returns:
# {
#   "last_closed": {...},  # Most recent completed segment
#   "active": {             # Current partial segment (if any)
#     "start": "2025-11-09T14:30:00Z",
#     "duration_s": 1234,
#     "agents": {...}
#   }
# }
```

---

## 4. Report Generation

### 4.1 Invoice

```python
def generate_invoice(start_date, end_date, hourly_rate=75.0):
    """Generate invoice from date range."""
    segments = []
    current = start_date
    while current <= end_date:
        segments.extend(read_segments(current.isoformat()))
        current += timedelta(days=1)
    
    total_hours = sum(s['duration_s'] for s in segments) / 3600
    total_amount = total_hours * hourly_rate
    
    return {
        'period': f"{start_date} to {end_date}",
        'total_hours': total_hours,
        'hourly_rate': hourly_rate,
        'total_amount': total_amount,
        'segments': len(segments)
    }
```

### 4.2 Timecard

```python
def generate_timecard(date):
    """Generate daily timecard."""
    segments = read_segments(date.isoformat())
    
    return {
        'date': date.isoformat(),
        'total_hours': sum(s['duration_s'] for s in segments) / 3600,
        'segments': len(segments),
        'timeline': [
            {
                'start': s['start'],
                'end': s['end'],
                'duration_h': s['duration_s'] / 3600,
                'agents': list(s['agents'].keys())
            }
            for s in segments
        ]
    }
```

---

## 5. Display Current Activity

```python
def display_dashboard():
    """Simple dashboard display."""
    current = read_current_activity()
    
    if not current:
        print("Monitors not running")
        return
    
    # Show last closed segment
    if current.get('last_closed'):
        last = current['last_closed']
        print(f"Last segment: {last['duration_s']/3600:.1f}h, ended {last['end']}")
    
    # Show active segment
    if current.get('active'):
        active = current['active']
        elapsed = active['duration_s'] / 3600
        agents = ', '.join(active['agents'].keys())
        print(f"Currently working: {elapsed:.1f}h, agents: {agents}")
    else:
        print("Currently idle")
```

---

## 6. That's It

**Dashboard = 3 things:**
1. `subprocess.Popen()` to launch orchestrator
2. `open("mimolo_YYYY-MM-DD.jsonl")` to read logs
3. `json.load("current.json")` to show activity

**No protocols. No messages. No subscriptions. Just files and processes.**