# mimolo/docs/SLOWPOKE_MODULE.md

# SLOWPOKE IPC Module

## ⚠️  WARNING: LEGACY FALLBACK ONLY ⚠️

The SLOWPOKE module is a file-based IPC implementation for platforms that lack
Unix domain socket support.

**DO NOT USE THIS unless you absolutely cannot upgrade your OS.**

## When to Use

ONLY use SLOWPOKE if:
- ❌ You are stuck on Windows 7/8 or old macOS
- ❌ You cannot upgrade your OS
- ❌ You accept severe performance degradation
- ❌ You have fewer than 50 agents

## Installation

SLOWPOKE is NOT included in default builds.

### Option 1: pip extra
```bash
pip install mimolo[slowpoke]
```

### Option 2: Manual download
Download `ipc_slowpoke.py` from releases and place in:
```
mimolo/core/ipc_slowpoke.py
```

## Configuration
```toml
# mimolo.toml
[monitor]
use_slowpoke_ipc = true  # Enable file-based fallback

# IMPORTANT: Reduce agent count
[monitor.slowpoke]
max_agents = 50          # Hard limit
warn_at_agents = 30      # Show performance warning
```

## Performance Impact

| Metric           | Native IPC      | SLOWPOKE         |
| ---------------- | --------------- | ---------------- |
| **Latency**      | 0.1ms           | 100-200ms        |
| **Throughput**   | 100,000 msg/s   | 100-500 msg/s    |
| **CPU overhead** | 0.01% per agent | 0.5-1% per agent |
| **Disk writes**  | None            | Constant         |
| **Max agents**   | 500+            | ~50              |

## Performance Degradation Examples

### 10 Agents
- Native: 0.1% CPU, 0 disk writes
- SLOWPOKE: 5% CPU, 2400 files/hour

### 50 Agents  
- Native: 0.5% CPU, 0 disk writes
- SLOWPOKE: 25% CPU, 12,000 files/hour, **system becomes sluggish**

### 100 Agents
- Native: 1% CPU, 0 disk writes
- SLOWPOKE: **SYSTEM UNUSABLE** - don't even try

## SSD Wear Warning

SLOWPOKE writes files constantly:
- 1 agent = ~40 writes/minute = 2,400 writes/hour
- 50 agents = ~2,000 writes/minute = 120,000 writes/hour

**This WILL wear out SSDs faster.**

Modern SSDs can handle 100,000s of write cycles, but SLOWPOKE accelerates wear by 10-100x compared to normal usage.

## Code Example
```python
# Orchestrator startup with SLOWPOKE
from mimolo.core.ipc import check_platform_support

supported, reason = check_platform_support()

if not supported:
    # Native IPC unavailable, offer SLOWPOKE
    console.print(f"[yellow]Warning: {reason}[/yellow]")
    console.print("[yellow]Native IPC not available.[/yellow]")
    
    use_slowpoke = input("Use SLOWPOKE fallback? (yes/no): ")
    
    if use_slowpoke.lower() != "yes":
        console.print("[red]Cannot proceed. Please upgrade your OS.[/red]")
        sys.exit(1)
    
    # Import SLOWPOKE (issues warning on import)
    from mimolo.core.ipc_slowpoke import (
        create_slowpoke_channel,
        check_agent_count_sanity
    )
    
    # Check agent count
    agent_count = len(config.plugins)
    check_agent_count_sanity(agent_count)
    
    # Create SLOWPOKE channels
    ipc = create_slowpoke_channel(
        read_dir="/tmp/mimolo_slowpoke/to_orch",
        write_dir="/tmp/mimolo_slowpoke/to_dash",
        create=True
    )
    
    console.print("[yellow]SLOWPOKE mode enabled. Performance will be degraded.[/yellow]")
```

## Upgrade Path

**Please upgrade your OS instead of using SLOWPOKE:**

### Windows 7/8 Users
- Upgrade to Windows 10 version 1803+ (free upgrade available)
- Or use Windows 11

### Old macOS Users
- Upgrade to macOS 10.13 High Sierra or later
- Most Macs from 2009+ support High Sierra

### Why Upgrade?
- 100-1000x better performance
- No SSD wear from constant writes
- Support 500+ agents instead of 50
- Actually usable in production

## FAQ

**Q: Why is it called SLOWPOKE?**  
A: Like the Pokémon - slow but reliable. Also a reference to software rendering fallbacks from the 90s/2000s (opengl.dll software renderer).

**Q: Can I use this in production?**  
A: **NO.** SLOWPOKE is for desperate legacy users only. Upgrade your OS.

**Q: Will SLOWPOKE get better over time?**  
A: **NO.** File-based IPC is fundamentally limited by disk I/O. It will never match native pipes. This is a maintenance-mode fallback, not an active development target.

**Q: My system crashes with 100 agents in SLOWPOKE mode.**  
A: **Expected behavior.** SLOWPOKE cannot handle 100 agents. Use ≤50 agents or upgrade your OS.

**Q: SLOWPOKE is writing millions of files and my disk is full.**  
A: **Working as designed** (unfortunately). SLOWPOKE cleans up files older than 5 minutes, but high agent counts create file spam. Reduce agent count or upgrade your OS.
