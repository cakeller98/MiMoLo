"""Logging helper for Agents that sends structured log packets via Agent JLP.

This module provides AgentLogger, which allows Agents to emit structured
log messages that are routed through the orchestrator and rendered with Rich
formatting on the orchestrator console.

Key features:
- Logs flow through stdout Agent JLP (not stderr)
- Preserves Rich markup for colorful, styled output
- Orchestrator controls verbosity filtering
- Works across process boundaries and in separate terminals
- Simple, familiar logging API

Example usage in a Agent:
    from mimolo.core.agent_logging import AgentLogger

    logger = AgentLogger(agent_id="my_agent-001", agent_label="my_agent")

    logger.debug("[cyan]Worker thread started[/cyan]")
    logger.info("[green]✓[/green] Processing complete")
    logger.warning("[yellow]⚠[/yellow] Cache near capacity: [bold]85%[/bold]")
    logger.error("[red]✗[/red] Connection failed: [dim]timeout after 30s[/dim]")
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any


class AgentLogger:
    """Logger for Agents that sends structured log packets via stdout protocol.

    This logger emits JSON log messages on stdout that are parsed by the orchestrator
    and rendered with Rich console formatting. Log messages can contain Rich markup
    (e.g., [cyan], [bold], [red]) which will be preserved and rendered correctly.

    Attributes:
        agent_id: Unique runtime identifier for the agent
        agent_label: Logical plugin name
        protocol_version: Agent JLP protocol version
        agent_version: Agent implementation version
    """

    def __init__(
        self,
        agent_id: str,
        agent_label: str,
        protocol_version: str = "0.3",
        agent_version: str = "1.0.0",
    ) -> None:
        """Initialize the agent logger.

        Args:
            agent_id: Unique runtime identifier (e.g., "my_agent-001")
            agent_label: Logical plugin name (e.g., "my_agent")
            protocol_version: Agent JLP protocol version (default: "0.3")
            agent_version: Agent implementation version (default: "1.0.0")
        """
        self.agent_id = agent_id
        self.agent_label = agent_label
        self.protocol_version = protocol_version
        self.agent_version = agent_version

    def _send_log(
        self,
        level: str,
        message: str,
        markup: bool = True,
        **extra: Any,
    ) -> None:
        """Send a structured log packet via stdout.

        This is an internal method that constructs and emits a log packet
        in the Agent JLP format. The orchestrator will parse this packet
        and route it to the appropriate output handler based on verbosity
        settings.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message text (may contain Rich markup)
            markup: Whether the message contains Rich markup (default: True)
            **extra: Additional context data to include in the log packet
        """
        packet = {
            "type": "log",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": self.protocol_version,
            "agent_version": self.agent_version,
            "level": level,
            "message": message,
            "markup": markup,
            "data": {},  # Required by AgentMessage schema
            "extra": extra,
        }
        try:
            print(json.dumps(packet), flush=True)
        except (OSError, TypeError, ValueError) as e:
            # Fallback to stderr if stdout logging fails
            error_msg = f"[AgentLogger] Failed to send log: {e}"
            print(error_msg, file=sys.stderr, flush=True)

    def debug(self, message: str, markup: bool = True, **extra: Any) -> None:
        """Log a debug message.

        Debug messages are typically used for detailed diagnostic information
        useful during development and troubleshooting.

        Args:
            message: Log message text (may contain Rich markup)
            markup: Whether the message contains Rich markup (default: True)
            **extra: Additional context data

        Example:
            logger.debug("[cyan]⚙️  Worker thread started[/cyan]")
            logger.debug("Processing item", item_id=42, status="pending")
        """
        self._send_log("debug", message, markup=markup, **extra)

    def info(self, message: str, markup: bool = True, **extra: Any) -> None:
        """Log an info message.

        Info messages are used for general informational messages that highlight
        the progress of the agent.

        Args:
            message: Log message text (may contain Rich markup)
            markup: bool = True: Whether the message contains Rich markup (default: True)
            **extra: Additional context data

        Example:
            logger.info("[green]✓[/green] Processing complete")
            logger.info("Processed batch", count=100, duration=1.23)
        """
        self._send_log("info", message, markup=markup, **extra)

    def warning(self, message: str, markup: bool = True, **extra: Any) -> None:
        """Log a warning message.

        Warning messages are used to indicate something unexpected happened,
        but the agent is still working as expected.

        Args:
            message: Log message text (may contain Rich markup)
            markup: Whether the message contains Rich markup (default: True)
            **extra: Additional context data

        Example:
            logger.warning("[yellow]⚠[/yellow] Cache near capacity: [bold]85%[/bold]")
            logger.warning("Retry attempt failed", attempt=2, max_retries=3)
        """
        self._send_log("warning", message, markup=markup, **extra)

    def error(self, message: str, markup: bool = True, **extra: Any) -> None:
        """Log an error message.

        Error messages are used to indicate a serious problem that prevented
        the agent from performing some function.

        Args:
            message: Log message text (may contain Rich markup)
            markup: Whether the message contains Rich markup (default: True)
            **extra: Additional context data

        Example:
            logger.error("[red]✗[/red] Connection failed: [dim]timeout after 30s[/dim]")
            logger.error("Database error", exception=str(e), table="users")
        """
        self._send_log("error", message, markup=markup, **extra)

    # Convenience aliases for common patterns

    def rich_debug(self, message: str, **extra: Any) -> None:
        """Log a debug message with Rich markup enabled.

        This is a convenience method that is equivalent to calling
        debug(message, markup=True).

        Args:
            message: Log message with Rich markup
            **extra: Additional context data
        """
        self.debug(message, markup=True, **extra)

    def rich_info(self, message: str, **extra: Any) -> None:
        """Log an info message with Rich markup enabled.

        Args:
            message: Log message with Rich markup
            **extra: Additional context data
        """
        self.info(message, markup=True, **extra)

    def rich_warning(self, message: str, **extra: Any) -> None:
        """Log a warning message with Rich markup enabled.

        Args:
            message: Log message with Rich markup
            **extra: Additional context data
        """
        self.warning(message, markup=True, **extra)

    def rich_error(self, message: str, **extra: Any) -> None:
        """Log an error message with Rich markup enabled.

        Args:
            message: Log message with Rich markup
            **extra: Additional context data
        """
        self.error(message, markup=True, **extra)
