"""Logging configuration for the MiMoLo orchestrator process.

This module provides logging setup for the orchestrator (runtime) process
itself, NOT for Field-Agents. Field-Agents use the AgentLogger which sends
structured log packets via Agent JLP.

The orchestrator logging is used for:
- Internal orchestrator diagnostics
- Agent process management errors
- Configuration and plugin loading errors
- Sink/file I/O errors

All orchestrator logs are written to stderr with Rich formatting.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

from rich.logging import RichHandler


def setup_logging(
    verbosity: Literal["debug", "info", "warning", "error"] = "info",
    log_to_file: bool = False,
    log_file_path: str | None = None,
) -> logging.Logger:
    """Configure logging for the orchestrator process.

    Sets up logging with Rich handler for colorful stderr output. The verbosity
    level controls what orchestrator-internal logs are displayed.

    Note: This does NOT affect Field-Agent logging, which flows through the
    Agent JLP via AgentLogger.

    Args:
        verbosity: Console verbosity level (debug, info, warning, error)
        log_to_file: Whether to also log to a file (default: False)
        log_file_path: Path for file logging (if log_to_file=True)

    Returns:
        Configured root logger instance

    Example:
        from mimolo.core.logging_setup import setup_logging

        logger = setup_logging(verbosity="debug")
        logger.info("Orchestrator started")
        logger.error("Configuration error", exc_info=True)
    """
    # Map verbosity string to logging level
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    log_level = level_map.get(verbosity, logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything at root level

    # Clear existing handlers (avoid duplicates on re-initialization)
    root_logger.handlers.clear()

    # Rich handler for stderr (colorful console output)
    rich_handler = RichHandler(
        console=None,  # Creates its own console instance
        show_time=True,
        show_level=True,
        show_path=False,  # Don't show file paths (too verbose)
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    rich_handler.setLevel(log_level)

    # Format: just the message (Rich handles the rest)
    rich_formatter = logging.Formatter("%(message)s", datefmt="[%X]")
    rich_handler.setFormatter(rich_formatter)

    root_logger.addHandler(rich_handler)

    # Optional file handler
    if log_to_file and log_file_path:
        try:
            file_handler = logging.FileHandler(log_file_path, mode="a", encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)  # Log everything to file

            # File format: timestamp, level, logger name, message
            file_formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(file_formatter)

            root_logger.addHandler(file_handler)
        except Exception as e:
            # Fallback: warn but don't crash
            root_logger.warning(f"Failed to setup file logging: {e}")

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a named logger for a specific module.

    This is a convenience wrapper around logging.getLogger() that ensures
    logging is configured before use.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Logger instance

    Example:
        from mimolo.core.logging_setup import get_logger

        logger = get_logger(__name__)
        logger.debug("Processing event...")
    """
    return logging.getLogger(name)


# Convenience function for quick setup
def init_orchestrator_logging(verbosity: str = "info") -> None:
    """Initialize orchestrator logging with minimal configuration.

    This is a convenience function that sets up logging for the orchestrator
    with default settings. Should be called early in cli.py.

    Args:
        verbosity: Console verbosity level (debug, info, warning, error)
    """
    setup_logging(verbosity=verbosity)  # type: ignore[arg-type]
