# Export and Reporting

> **Document Version:** 0.3  
> **Target Framework:** MiMoLo v0.3+  
> **Last Updated:** November 2025  
> **Status:** Draft specification

---

## 1. Overview

The Dashboard generates reports by **reading JSONL log files directly** from `~/.mimolo/logs/`. No Orchestrator communication required.

**Key capabilities:**
- Generate invoices for billable work periods
- Create timecards for personal tracking
- Export raw data to CSV for external analysis
- Produce formatted reports grouped by day/week/agent

---

## 2. Reading Historical Data

### 2.1 Read Segments from Log Files

```python
import json
from pathlib import Path
from datetime import date, timedelta

def read_segments_for_date(date_str):
    """Read all segments from a specific date's log file."""
    log_dir = Path.home() / ".mimolo" / "logs"
    log_file = log_dir / f"mimolo_{date_str}.jsonl"
    
    if not log_file.exists():
        return []
    
    segments = []
    with open(log_file) as f:
        for line in f:
            if line.strip():
                segments.append(json.loads(line))
    
    return segments

def read_segments_for_range(start_date, end_date):
    """Read all segments within a date range."""
    segments = []
    current = start_date
    
    while current <= end_date:
        date_str = current.isoformat()
        segments.extend(read_segments_for_date(date_str))
        current += timedelta(days=1)
    
    return segments
```

---

## 3. Invoice Generation

### 3.1 Calculate Billable Hours

```python
def generate_invoice(start_date, end_date, hourly_rate=75.0):
    """Generate invoice from date range."""
    segments = read_segments_for_range(start_date, end_date)
    
    # Calculate total hours
    total_seconds = sum(s['duration_s'] for s in segments)
    total_hours = total_seconds / 3600
    total_amount = total_hours * hourly_rate
    
    return {
        'period': f"{start_date} to {end_date}",
        'total_hours': round(total_hours, 2),
        'hourly_rate': hourly_rate,
        'total_amount': round(total_amount, 2),
        'segment_count': len(segments)
    }
```

### 3.2 Format Invoice Output

```python
def format_invoice_markdown(invoice_data):
    """Format invoice as markdown."""
    return f"""# Invoice

**Period:** {invoice_data['period']}  
**Total Hours:** {invoice_data['total_hours']}  
**Rate:** ${invoice_data['hourly_rate']}/hr  
**Segments:** {invoice_data['segment_count']}

---

**Total Amount Due:** ${invoice_data['total_amount']:.2f}
"""

# Usage
invoice = generate_invoice(date(2025, 11, 1), date(2025, 11, 30))
print(format_invoice_markdown(invoice))
```

---

## 4. Timecard Generation

### 4.1 Daily Timecard

```python
def generate_timecard(target_date):
    """Generate daily timecard."""
    date_str = target_date.isoformat()
    segments = read_segments_for_date(date_str)
    
    total_seconds = sum(s['duration_s'] for s in segments)
    total_hours = total_seconds / 3600
    
    timeline = []
    for seg in segments:
        timeline.append({
            'start': seg['start'],
            'end': seg['end'],
            'duration_h': round(seg['duration_s'] / 3600, 2),
            'agents': list(seg['agents'].keys())
        })
    
    return {
        'date': date_str,
        'total_hours': round(total_hours, 2),
        'segment_count': len(segments),
        'timeline': timeline
    }
```

### 4.2 Format Timecard Output

```python
def format_timecard_markdown(timecard):
    """Format timecard as markdown."""
    md = f"# Timecard: {timecard['date']}\n\n"
    md += f"**Total:** {timecard['total_hours']} hours  \n"
    md += f"**Segments:** {timecard['segment_count']}\n\n"
    md += "## Timeline\n\n"
    
    for entry in timecard['timeline']:
        agents = ', '.join(entry['agents'])
        md += f"- **{entry['start']}** to **{entry['end']}** "
        md += f"({entry['duration_h']}h) — {agents}\n"
    
    return md
```

---

## 5. CSV Export

### 5.1 Basic CSV Export

```python
import csv

def export_to_csv(segments, output_path):
    """Export segments to CSV."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow(['segment_id', 'start', 'end', 'duration_h', 'agents'])
        
        # Rows
        for seg in segments:
            writer.writerow([
                seg.get('segment_id', ''),
                seg['start'],
                seg['end'],
                round(seg['duration_s'] / 3600, 2),
                ','.join(seg['agents'].keys())
            ])

# Usage
segments = read_segments_for_range(date(2025, 11, 1), date(2025, 11, 30))
export_to_csv(segments, 'november_2025.csv')
```

---

## 6. Filtering Segments

### 6.1 Filter by Agent

```python
def filter_by_agent(segments, agent_name):
    """Filter segments that include specific agent."""
    return [s for s in segments if agent_name in s['agents']]
```

### 6.2 Filter by Duration

```python
def filter_by_min_duration(segments, min_seconds=300):
    """Filter out segments shorter than threshold."""
    return [s for s in segments if s['duration_s'] >= min_seconds]
```

---

## 7. Aggregation

### 7.1 Group by Day

```python
from collections import defaultdict

def group_by_day(segments):
    """Group segments by date."""
    by_day = defaultdict(list)
    
    for seg in segments:
        # Extract date from ISO timestamp (e.g., "2025-11-09T10:00:00Z")
        date_str = seg['start'].split('T')[0]
        by_day[date_str].append(seg)
    
    return dict(by_day)
```

### 7.2 Calculate Per-Agent Hours

```python
def calculate_agent_hours(segments):
    """Calculate total hours per agent."""
    agent_seconds = defaultdict(int)
    
    for seg in segments:
        for agent in seg['agents'].keys():
            agent_seconds[agent] += seg['duration_s']
    
    # Convert to hours
    return {agent: round(secs / 3600, 2) 
            for agent, secs in agent_seconds.items()}
```

---

## Summary

Dashboard report generation = **reading JSONL files and processing them**:

1. Read `~/.mimolo/logs/mimolo_YYYY-MM-DD.jsonl` files
2. Parse segments (one JSON object per line)
3. Filter/aggregate as needed
4. Format output (markdown/CSV/JSON)

**No Orchestrator communication. Just file reading.**
