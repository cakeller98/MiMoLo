"""Interactive agent selection menu for MiMoLo orchestrator.

Provides a keyboard-driven menu to view and interact with Agents:
- Ctrl+A or 'a' command: Show agent list
- Number keys (1-9): Select agent from current page
- 'n'/'>': Next page
- 'p'/'<': Previous page
- 'q'/Esc: Close menu
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from mimolo.core.agent_process import AgentHandle


class AgentMenu:
    """Interactive menu for viewing and selecting Agents."""

    def __init__(self, console: Console | None = None):
        """Initialize agent menu.

        Args:
            console: Rich console for output (creates new if None)
        """
        self.console = console or Console()
        self.page_size = 9  # Show 9 agents per page (1-9 keys)
        self.current_page = 0

    def show_agent_list(
        self, agents: dict[str, AgentHandle], interactive: bool = False
    ) -> str | None:
        """Display list of agents with pagination.

        Args:
            agents: Dictionary of agent labels to AgentHandle instances
            interactive: If True, wait for user input for selection

        Returns:
            Selected agent label if interactive=True, None otherwise
        """
        if not agents:
            self.console.print("[yellow]No agents currently running.[/yellow]")
            return None

        total_agents = len(agents)
        total_pages = math.ceil(total_agents / self.page_size)

        # Ensure current page is valid
        self.current_page = max(0, min(self.current_page, total_pages - 1))

        # Get agents for current page
        agent_list = list(agents.items())
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, total_agents)
        page_agents = agent_list[start_idx:end_idx]

        # Build table
        table = Table(title=f"Agents (Page {self.current_page + 1}/{total_pages})")
        table.add_column("#", style="cyan", justify="right", width=3)
        table.add_column("Label", style="green", width=20)
        table.add_column("Status", style="yellow", width=10)
        table.add_column("Uptime", style="blue", width=12)
        table.add_column("Heartbeat", style="magenta", width=12)

        for idx, (label, handle) in enumerate(page_agents, start=1):
            # Calculate uptime
            from datetime import UTC, datetime

            uptime = datetime.now(UTC) - handle.started_at
            uptime_str = self._format_duration(uptime.total_seconds())

            # Last heartbeat
            if handle.last_heartbeat:
                hb_ago = datetime.now(UTC) - handle.last_heartbeat
                hb_str = f"{hb_ago.total_seconds():.0f}s ago"
            else:
                hb_str = "None"

            # Status color
            status = handle.health
            if handle.process.poll() is not None:
                status = "dead"
                status_color = "red"
            elif handle.health == "ok":
                status_color = "green"
            elif handle.health == "starting":
                status_color = "yellow"
            else:
                status_color = "orange"

            table.add_row(
                str(idx),
                label,
                f"[{status_color}]{status}[/{status_color}]",
                uptime_str,
                hb_str,
            )

        # Add navigation help
        nav_text = Text()
        if interactive:
            nav_text.append("Keys: ", style="bold")
            nav_text.append("1-9", style="cyan")
            nav_text.append(" = Select | ", style="dim")
            nav_text.append("n/>", style="cyan")
            nav_text.append(" = Next | ", style="dim")
            nav_text.append("p/<", style="cyan")
            nav_text.append(" = Prev | ", style="dim")
            nav_text.append("q/Esc", style="cyan")
            nav_text.append(" = Close", style="dim")
        else:
            nav_text.append(f"Showing {start_idx + 1}-{end_idx} of {total_agents} agents", style="dim")

        panel = Panel(table, subtitle=nav_text, border_style="blue")
        self.console.print(panel)

        if interactive:
            # TODO: Implement keyboard input handling
            # For now, just display the menu
            return None

        return None

    def next_page(self, agents: dict[str, AgentHandle]) -> None:
        """Navigate to next page (wraps to first page after last)."""
        total_pages = math.ceil(len(agents) / self.page_size)
        self.current_page = (self.current_page + 1) % total_pages

    def prev_page(self, agents: dict[str, AgentHandle]) -> None:
        """Navigate to previous page (wraps to last page before first)."""
        total_pages = math.ceil(len(agents) / self.page_size)
        self.current_page = (self.current_page - 1) % total_pages

    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to human-readable string.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted string (e.g., "1h 23m", "45s")
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"


def format_agent_list_compact(agents: dict[str, AgentHandle]) -> str:
    """Format agent list as compact string for status display.

    Args:
        agents: Dictionary of agent labels to AgentHandle instances

    Returns:
        Compact string like "agent1(ok), agent2(starting), ..."
    """
    if not agents:
        return "No agents"

    parts = []
    for label, handle in agents.items():
        status = handle.health
        if handle.process.poll() is not None:
            status = "dead"
        parts.append(f"{label}({status})")

    return ", ".join(parts)
