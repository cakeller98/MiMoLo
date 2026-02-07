> [!NOTE]
> Reference-History Document: workflow intent from this file is merged into `developer_docs/2026.02.05 NOTES/UNIFIED_WORKFLOW_INTENT.md`.
> Use that file for current workflow direction; keep this file for historical context.

# Agent Selection Menu - Feature Design

## Overview

Interactive menu system for viewing and managing Agents in the MiMoLo orchestrator with keyboard-driven navigation and pagination.

## Requirements

### User Story
As a user running the MiMoLo orchestrator with multiple Agents, I want to:
- Press `Ctrl+A` to show a list of running agents
- See agents in pages of 9 (numbered 1-9 for easy selection)
- Navigate pages with `n/p` or `>/<` keys
- Select an agent with number keys (1-9)
- Have pagination wrap correctly (mod-divided, not continuously rolling)

### Key Constraint
> "We don't want a non-multiple of 9 to have the second item shifting to 5th because the last bank of 9 was only 5"

This means: **Fixed page structure** - if there are 14 agents, show:
- Page 1: Agents 1-9
- Page 2: Agents 10-14 (only 5 items, but numbers stay 10-14, not reset to 1-5)

## Implementation Status

### ✅ Completed
1. **[mimolo/core/agent_menu.py](mimolo/core/agent_menu.py)** - Created
   - `AgentMenu` class for rendering agent lists
   - Pagination logic (9 agents per page)
   - Mod-division paging (fixed page structure)
   - Rich table display with status, uptime, heartbeat

### 🚧 Pending
2. **Keyboard Input Handling** - Not yet implemented
   - Challenge: Runtime runs in blocking event loop
   - Need non-blocking keyboard input
   - Options: threading, async, or signal-based

3. **Integration with Runtime** - Not yet implemented
   - Add `AgentMenu` instance to `Runtime` class
   - Hook up keyboard listener
   - Display menu on `Ctrl+A`

## Architecture

### Current Agent Storage
```python
# In Runtime class
self.agent_manager = AgentProcessManager(config)  # Manages agents
self.agent_manager.agents: dict[str, AgentHandle]  # Label → Handle mapping
```

### Agent Information Available
```python
class AgentHandle:
    label: str                    # Agent name
    process: subprocess.Popen     # Process object
    started_at: datetime          # Start time
    last_heartbeat: datetime | None  # Last heartbeat
    health: str                   # "ok" | "starting" | "degraded" | "failed"
    agent_id: str | None          # Unique ID
```

## Implementation Options

### Option 1: Command-Based (Recommended for v1)
**Pros:** Simple, reliable, no threading complexity
**Cons:** Not real-time, must type command

```python
# User types 'agents' or 'a' in orchestrator console
# OR: Use a CLI command in separate terminal
$ mimolo agents  # Shows live agent status
```

**Implementation:**
- Add `agents` command to CLI
- Read agent state from shared file/socket
- Display menu with AgentMenu class

### Option 2: Keyboard Listener Thread
**Pros:** True `Ctrl+A` support, real-time
**Cons:** Complex, potential race conditions

```python
import threading
import sys
import select  # Unix only
# or
import msvcrt  # Windows only

# Background thread listening for keyboard
def keyboard_listener():
    while running:
        if kbhit():  # Non-blocking check
            ch = getch()
            if ch == '\x01':  # Ctrl+A
                show_agent_menu()
```

**Issues:**
- Platform-specific (different for Windows/Unix)
- Stdin conflicts with agent JLP reading
- Thread safety with Rich console

### Option 3: Signal-Based (Unix/POSIX)
**Pros:** Clean, event-driven
**Cons:** Platform-specific, limited to Unix

```python
import signal

def show_agents_handler(signum, frame):
    menu.show_agent_list(agents)

signal.signal(signal.SIGUSR1, show_agents_handler)
# User sends: kill -SIGUSR1 <orchestrator_pid>
```

### Option 4: Rich Live Display (Recommended for v2)
**Pros:** Professional UI, builtin to Rich
**Cons:** Major refactor of runtime loop

```python
from rich.live import Live
from rich.layout import Layout

with Live(layout, refresh_per_second=4) as live:
    while running:
        # Update layout
        layout["agents"].update(agent_table)
        # F1 key: expand agent panel
```

## Recommended Implementation Path

### Phase 1: CLI Command (Immediate)
```bash
# In separate terminal while orchestrator runs
$ mimolo agents
```
- Simple, no runtime changes
- Reads agent PID files from temp directory
- Uses `AgentMenu` class to display

### Phase 2: In-Runtime Display (Future)
- Add periodic agent status to orchestrator console output
- Every N seconds, print compact agent list
- Example: `[16:05:32] Agents: template(ok), example(ok)`

### Phase 3: Interactive Mode (Advanced)
- Full Rich Live display with keyboard navigation
- Requires refactoring runtime loop
- Best UX, most complex

## Current Implementation

### AgentMenu Class
```python
from mimolo.core.agent_menu import AgentMenu

menu = AgentMenu(console)
menu.show_agent_list(agents)  # Displays page 1

# Navigate
menu.next_page(agents)  # Page 2
menu.prev_page(agents)  # Back to page 1 (wraps around)

# Pagination logic ensures fixed structure
# 14 agents = Page 1 (1-9), Page 2 (10-14)
# Not: Page 1 (1-9), Page 2 (1-5) ✗
```

### Display Format
```
┌─ Agents (Page 1/2) ─────────────────────────┐
│ #  Label            Status    Uptime      Heartbeat│
│ 1  template_agent   ok        5m 23s      2s ago   │
│ 2  example_agent    ok        5m 23s      15s ago  │
│ 3  monitor_agent    starting  12s         None     │
│ ...                                                 │
│ 9  data_collector   ok        1h 15m      1s ago   │
├────────────────────────────────────────────────────┤
│ Showing 1-9 of 14 agents                          │
└────────────────────────────────────────────────────┘
```

## Future Enhancements

1. **Agent Actions**
   - Select agent → show detailed stats
   - Send flush command to specific agent
   - Restart failed agent
   - View agent logs

2. **Filtering**
   - Show only failed agents
   - Filter by label pattern
   - Sort by uptime/status

3. **Real-Time Updates**
   - Auto-refresh every N seconds
   - Highlight status changes
   - Show heartbeat indicator (pulsing)

## Usage Examples

### Example 1: View All Agents
```python
# In runtime code
menu = AgentMenu(self.console)
menu.show_agent_list(self.agent_manager.agents)
```

### Example 2: Paginated Navigation
```python
# User presses 'n' for next page
menu.next_page(agents)
menu.show_agent_list(agents)  # Shows page 2

# User presses 'p' for previous
menu.prev_page(agents)
menu.show_agent_list(agents)  # Back to page 1
```

### Example 3: Compact Status
```python
from mimolo.core.agent_menu import format_agent_list_compact

status = format_agent_list_compact(agents)
console.print(f"[dim]Agents: {status}[/dim]")
# Output: Agents: template(ok), example(ok), monitor(starting)
```

## Testing

### Test Pagination Logic
```python
# 5 agents (1 page)
assert menu.current_page == 0
menu.next_page(agents)  # Wraps to 0
assert menu.current_page == 0

# 14 agents (2 pages)
menu.current_page = 0
menu.next_page(agents)
assert menu.current_page == 1  # Page 2
menu.next_page(agents)
assert menu.current_page == 0  # Wraps back to page 1

# 27 agents (3 pages)
# Page 1: 1-9, Page 2: 10-18, Page 3: 19-27
```

## Files

- **Created:** `mimolo/core/agent_menu.py` - Menu implementation
- **TODO:** CLI command integration
- **TODO:** Runtime keyboard listener (optional)
- **TODO:** Rich Live display (future)

## Status

**Phase 1 (CLI Command):** Ready for implementation
**Phase 2 (Runtime Display):** Design complete, awaiting implementation
**Phase 3 (Interactive):** Future enhancement

---

**Date:** 2025-01-11
**Status:** Infrastructure ready, awaiting integration decision

