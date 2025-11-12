"""Command-line interface for MiMoLo using Typer.

Commands:
- monitor: Run the orchestrator
- test: Emit synthetic test events
- register: Print plugin registration info (stub)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console

from mimolo.core.config import Config, load_config_or_default
from mimolo.core.errors import ConfigError
from mimolo.core.event import Event
from mimolo.core.ipc import check_platform_support
from mimolo.core.logging_setup import init_orchestrator_logging
from mimolo.core.runtime import Runtime

console = Console()
# Check platform support on module import
_supported, _reason = check_platform_support()
if not _supported:
    console.print(f"[red]ERROR: {_reason}[/red]")
    console.print("\n[yellow]MiMoLo requires:[/yellow]")
    console.print("  - Windows 10 version 1803+ (April 2018 or later)")
    console.print("  - macOS 10.13 High Sierra or later")
    console.print("  - Modern Linux (kernel 2.6+)")
    console.print("\n[dim]Your platform is not supported.[/dim]")
    sys.exit(1)

console.print(f"[dim]Platform check: {_reason}[/dim]")

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


@app.command()
def monitor(
    config_path: Annotated[Path | None, CONFIG_OPTION] = Path("mimolo.toml"),
    once: Annotated[bool, ONCE_OPTION] = False,
    dry_run: Annotated[bool, DRY_RUN_OPTION] = False,
    log_format: Annotated[str | None, LOG_FORMAT_OPTION] = None,
    cooldown: Annotated[float | None, COOLDOWN_OPTION] = None,
) -> None:
    """Run the MiMoLo monitor orchestrator.

    Loads configuration, registers plugins, and runs the main event loop.
    """
    try:
        # Load config
        config = load_config_or_default(config_path)

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

        # Check for Field-Agent plugins in config
        field_agent_count = sum(1 for pc in config.plugins.values() if pc.enabled and pc.plugin_type == "field_agent")

        if field_agent_count == 0:
            console.print("[red]No Field-Agents configured. Nothing to monitor.[/red]")
            sys.exit(1)

        # Create and run runtime
        runtime = Runtime(config, console)
        runtime.run(max_iterations=1 if once else None)

    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(2)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


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
