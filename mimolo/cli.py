"""Command-line interface for MiMoLo using Typer.

Commands:
- ops: Run the operations orchestrator (singleton)
- monitor: Backward-compatible alias for ops
- test: Emit synthetic test events
- register: Print plugin registration info (stub)
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from mimolo.common.paths import get_mimolo_data_dir
from mimolo.core.config import Config, load_config_or_default
from mimolo.core.errors import ConfigError
from mimolo.core.event import Event
from mimolo.core.ipc import check_platform_support
from mimolo.core.logging_setup import init_orchestrator_logging
from mimolo.core.ops_singleton import OperationsSingletonLock
from mimolo.core.runtime import Runtime

console = Console()


def _check_platform_or_exit() -> None:
    supported, reason = check_platform_support()
    if not supported:
        console.print(f"[red]ERROR: {reason}[/red]")
        console.print("\n[yellow]MiMoLo requires:[/yellow]")
        console.print("  - Windows 10 version 1803+ (April 2018 or later)")
        console.print("  - macOS 10.13 High Sierra or later")
        console.print("  - Modern Linux (kernel 2.6+)")
        console.print("\n[dim]Your platform is not supported.[/dim]")
        sys.exit(1)
    console.print(f"[dim]Platform check: {reason}[/dim]")


def _apply_monitor_env_overrides(config: Config) -> None:
    """Apply optional monitor path overrides from environment."""
    log_dir = os.getenv("MIMOLO_MONITOR_LOG_DIR")
    if log_dir is not None and log_dir.strip():
        config.monitor.log_dir = log_dir.strip()

    journal_dir = os.getenv("MIMOLO_MONITOR_JOURNAL_DIR")
    if journal_dir is not None and journal_dir.strip():
        config.monitor.journal_dir = journal_dir.strip()

    cache_dir = os.getenv("MIMOLO_MONITOR_CACHE_DIR")
    if cache_dir is not None and cache_dir.strip():
        config.monitor.cache_dir = cache_dir.strip()


def _install_graceful_sigterm_handler(runtime: Runtime) -> None:
    """Handle SIGTERM as a graceful orchestrator stop request."""

    def _on_sigterm(signum: int, _frame: object | None) -> None:
        if signum == signal.SIGTERM:
            runtime._running = False

    signal.signal(signal.SIGTERM, _on_sigterm)

app = typer.Typer(
    name="mimolo",
    help="MiMoLo - Modular Monitor & Logger Framework",
    add_completion=False,
)

# Typer option metadata constants to avoid function calls in annotations/defaults
CONFIG_OPTION = typer.Option(
    "--config",
    "-c",
    help="Path to configuration file",
)
ONCE_OPTION = typer.Option(
    "--once",
    help="Exit after first segment closes",
)
DRY_RUN_OPTION = typer.Option(
    "--dry-run",
    help="Validate config and exit",
)
LOG_FORMAT_OPTION = typer.Option(
    "--log-format",
    help="Override log format (jsonl|yaml|md)",
)
COOLDOWN_OPTION = typer.Option(
    "--cooldown",
    help="Override cooldown seconds",
)


def _run_ops_command(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Run the MiMoLo operations orchestrator.

    Loads configuration, registers plugins, and runs the main event loop.
    """
    try:
        _check_platform_or_exit()

        # Load config
        config = load_config_or_default(config_path)
        _apply_monitor_env_overrides(config)

        # Initialize orchestrator logging (for internal diagnostics)
        init_orchestrator_logging(verbosity=config.monitor.console_verbosity)

        # Apply CLI overrides
        if log_format:
            config.monitor.log_format = log_format
        if cooldown is not None:
            config.monitor.cooldown_seconds = cooldown

        console.print(f"[cyan]Configuration loaded from: {config_path or 'defaults'}[/cyan]")

        if dry_run:
            console.print("[yellow]Dry-run mode: validating only[/yellow]")
            console.print(json.dumps(config.model_dump(), indent=2))
            return

        # Check for Agent plugins in config
        agent_count = sum(1 for pc in config.plugins.values() if pc.enabled and pc.plugin_type == "agent")

        if agent_count == 0:
            console.print("[red]No Agents configured. Nothing to monitor.[/red]")
            sys.exit(1)

        lock = OperationsSingletonLock(get_mimolo_data_dir())
        lock_status = lock.acquire()
        if not lock_status.acquired:
            pid_text = (
                f" (pid={lock_status.existing_pid})"
                if lock_status.existing_pid is not None
                else ""
            )
            console.print(
                "[red]Operations singleton already running"
                f"{pid_text}. Attach Control to existing instance.[/red]"
            )
            sys.exit(3)

        # Create and run runtime
        runtime = Runtime(config, console, config_path=config_path)
        _install_graceful_sigterm_handler(runtime)
        try:
            runtime.run(max_iterations=1 if once else None)
        finally:
            lock.release()

    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(2)
    except (OSError, RuntimeError, TypeError, ValueError) as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@app.command(name="ops")
def ops(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Run the MiMoLo operations orchestrator."""
    _run_ops_command(config_path, once, dry_run, log_format, cooldown)


@app.command(name="monitor", hidden=True)
def monitor_alias(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Backward-compatible alias for `mimolo ops`."""
    _run_ops_command(config_path, once, dry_run, log_format, cooldown)


@app.command()
def test(
    rate: float = 1.0,
    count: int = 10,
) -> None:
    """Emit synthetic test events.

    Useful for testing event schema and validating sink configuration.
    """
    console.print(f"[cyan]Emitting {count} test events at {rate} EPS[/cyan]")

    interval = 1.0 / rate if rate > 0 else 0

    for i in range(count):
        now = datetime.now(UTC)
        event = Event(
            timestamp=now,
            label="test",
            event=f"synthetic_{i}",
            data={"iteration": i, "message": "Hello from MiMoLo test"},
        ).with_id()

        print(json.dumps(event.to_dict(), separators=(",", ":")))

        if i < count - 1:
            time.sleep(interval)

    console.print("[green]Test complete[/green]")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
