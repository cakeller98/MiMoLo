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
from mimolo.core.errors import ConfigError, PluginRegistrationError
from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry
from mimolo.core.runtime import Runtime
from mimolo.plugins import ExampleMonitor, FolderWatchMonitor

app = typer.Typer(
    name="mimolo",
    help="MiMoLo - Modular Monitor & Logger Framework",
    add_completion=False,
)

console = Console()

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


def _discover_and_register_plugins(config: Config, registry: PluginRegistry) -> None:
    """Discover and register plugins based on configuration.

    Args:
        config: Configuration object.
        registry: Plugin registry.

    Raises:
        PluginRegistrationError: If plugin registration fails.
    """
    # Explicit plugin list for v0.2 (entry points later)
    available_plugins: dict[str, type[BaseMonitor]] = {
        "example": ExampleMonitor,
        "folderwatch": FolderWatchMonitor,
    }

    for plugin_name, plugin_class in available_plugins.items():
        plugin_config = config.plugins.get(plugin_name)

        if plugin_config is None or not plugin_config.enabled:
            console.print(f"[dim]Plugin '{plugin_name}' disabled or not configured[/dim]")
            continue

        # Create spec from plugin class default and override with config
        default_spec = plugin_class.spec
        spec = PluginSpec(
            label=default_spec.label,
            data_header=default_spec.data_header,
            resets_cooldown=plugin_config.resets_cooldown,
            infrequent=plugin_config.infrequent,
            poll_interval_s=plugin_config.poll_interval_s,
        )

        # Instantiate plugin with config
        if plugin_name == "example":
            instance = plugin_class()
        elif plugin_name == "folderwatch":
            extras: dict[str, Any] = plugin_config.model_extra or {}
            watch_dirs = extras.get("watch_dirs", [])
            extensions = extras.get("extensions", [])
            emit_on_discovery = extras.get("emit_on_discovery", False)
            fw_class = cast(type[FolderWatchMonitor], plugin_class)
            instance = fw_class(
                watch_dirs=watch_dirs,
                extensions=extensions,
                emit_on_discovery=emit_on_discovery,
            )
        else:
            instance = plugin_class()

        # Register
        registry.add(spec, instance)
        console.print(f"[green]Registered plugin: {spec.label}[/green]")


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

        # Register plugins
        registry = PluginRegistry()
        _discover_and_register_plugins(config, registry)

        # Check for Field-Agent plugins in config (they don't need registry)
        field_agent_count = sum(1 for pc in config.plugins.values() if pc.enabled and pc.plugin_type == "field_agent")

        if len(registry) == 0 and field_agent_count == 0:
            console.print("[red]No plugins registered. Nothing to monitor.[/red]")
            sys.exit(1)

        # Create and run runtime
        runtime = Runtime(config, registry, console)
        runtime.run(max_iterations=1 if once else None)

    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(2)
    except PluginRegistrationError as e:
        console.print(f"[red]Plugin registration error: {e}[/red]")
        sys.exit(3)
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


@app.command()
def register() -> None:
    """Print plugin registration metadata (stub for future IPC).

    Displays available plugins and their specifications.
    """
    console.print("[cyan]Available Plugins:[/cyan]\n")

    plugins: list[type[BaseMonitor]] = [
        ExampleMonitor,
        FolderWatchMonitor,
    ]

    for plugin_class in plugins:
        spec = plugin_class.spec
        spec_dict: dict[str, Any] = {
            "label": spec.label,
            "data_header": spec.data_header,
            "resets_cooldown": spec.resets_cooldown,
            "infrequent": spec.infrequent,
            "poll_interval_s": spec.poll_interval_s,
        }
        console.print(f"[bold]{spec.label}[/bold]")
        console.print(json.dumps(spec_dict, indent=2))
        console.print()


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
