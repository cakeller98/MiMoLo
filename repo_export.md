## mimolo.toml

``` toml
# MiMoLo Configuration
# See docs for full configuration reference

[monitor]
# Cooldown duration in seconds - segment closes after this period with no resetting events
cooldown_seconds = 600

# Polling tick interval in milliseconds
poll_tick_ms = 200

# Directory for log files (will be created if doesn't exist)
log_dir = "./logs"

# Log output format: jsonl (default), yaml, or md
log_format = "jsonl"

# Console verbosity: debug, info, warning, error
console_verbosity = "debug"

# Example Plugin Configuration (Legacy)
[plugins.example]
enabled = false
poll_interval_s = 3.0
resets_cooldown = true
infrequent = false

# Template Field-Agent Configuration (v0.3)
[plugins.agent_template]
enabled = true
plugin_type = "field_agent"
executable = "python"
args = ["agent_example.py"]
heartbeat_interval_s = 3.0
agent_flush_interval_s = 60.0

# Example Field-Agent Configuration (v0.3)
[plugins.agent_example]
enabled = true
plugin_type = "field_agent"
executable = "python"
args = ["agent_example.py"]
heartbeat_interval_s = 15.0
agent_flush_interval_s = 60.0

# Folder Watch Plugin Configuration
[plugins.folderwatch]
enabled = false
poll_interval_s = 5.0
resets_cooldown = true
infrequent = false

# Plugin-specific settings
watch_dirs = ["./demo", "./watched_folder"]
extensions = ["obj", "blend", "fbx", "py"]
```

## pyproject.toml

``` toml
[tool.poetry]
name = "mimolo"
version = "0.2.0"
description = "MiMoLo - Modular Monitor & Logger (Framework-First)"
authors = ["MiMoLo Contributors"]
readme = "README.md"
license = "MIT"
packages = [{include = "mimolo"}]

[tool.poetry.dependencies]
python = "^3.11"
typer = {extras = ["all"], version = "^0.20.0"}
pydantic = "^2.10.0"
pyyaml = "^6.0.1"
rich = "^14.2.0"

[tool.poetry.group.dev.dependencies]
pytest = "^8.4.0"
pytest-cov = "^7.0.0"
pytest-asyncio = "^1.2.0"
ruff = "^0.14.0"
mypy = "^1.14.0"
types-pyyaml = "^6.0.12"

[tool.poetry.scripts]
mimolo = "mimolo.cli:main"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
    "E",  # pycodestyle errors
    "W",  # pycodestyle warnings
    "F",  # pyflakes
    "I",  # isort
    "B",  # flake8-bugbear
    "C4", # flake8-comprehensions
    "UP", # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
strict_equality = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--showlocals",
]

[tool.coverage.run]
source = ["mimolo"]
omit = ["tests/*", "*/test_*.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "raise AssertionError",
    "raise NotImplementedError",
    "@abstractmethod",
]
```

## start_monitor.sh

``` sh
#!/usr/bin/env bash
# Launch MiMoLo monitor with Poetry environment
# Usage: ./start_monitor.sh [options]

set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate poetry environment and run monitor
poetry run python -m mimolo.cli monitor "$@"
```

## mimolo/__init__.py

``` py
"""MiMoLo - Modular Monitor & Logger Framework.

A lightweight, plugin-based framework for ingesting events from monitors,
applying aggregation filters, and emitting work segments.
"""

__version__ = "0.2.0"

from mimolo.core import (
    BaseMonitor,
    Config,
    Event,
    PluginRegistry,
    PluginSpec,
    Runtime,
    Segment,
)

__all__ = [
    "__version__",
    "BaseMonitor",
    "Config",
    "Event",
    "PluginRegistry",
    "PluginSpec",
    "Runtime",
    "Segment",
]
```

## mimolo/cli.py

``` py
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
```

## mimolo/agents/__init__.py

``` py
"""Field-Agent executables for MiMoLo v0.3."""
```

## mimolo/core/__init__.py

``` py
"""Core MiMoLo framework modules."""

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.config import Config, MonitorConfig, PluginConfig, load_config
from mimolo.core.cooldown import CooldownState, CooldownTimer, SegmentState
from mimolo.core.errors import (
    AggregationError,
    ConfigError,
    MiMoLoError,
    PluginEmitError,
    PluginRegistrationError,
    SinkError,
)
from mimolo.core.event import Event, EventRef, Segment
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry
from mimolo.core.runtime import Runtime
from mimolo.core.sink import BaseSink, ConsoleSink, JSONLSink, MarkdownSink, YAMLSink, create_sink

__all__ = [
    # Event primitives
    "Event",
    "EventRef",
    "Segment",
    # Errors
    "MiMoLoError",
    "ConfigError",
    "PluginRegistrationError",
    "PluginEmitError",
    "SinkError",
    "AggregationError",
    # Plugin system
    "BaseMonitor",
    "PluginSpec",
    "PluginRegistry",
    # Cooldown
    "CooldownTimer",
    "CooldownState",
    "SegmentState",
    # Aggregation
    "SegmentAggregator",
    # Config
    "Config",
    "MonitorConfig",
    "PluginConfig",
    "load_config",
    # Sinks
    "BaseSink",
    "JSONLSink",
    "YAMLSink",
    "MarkdownSink",
    "ConsoleSink",
    "create_sink",
    # Runtime
    "Runtime",
]
```

## mimolo/core/agent_process.py

``` py
"""Field-Agent subprocess management and communication."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from mimolo.core.protocol import AgentMessage, OrchestratorCommand, parse_agent_message


@dataclass
class AgentHandle:
    """Runtime handle for a Field-Agent subprocess."""

    label: str
    process: subprocess.Popen[str]
    config: Any  # PluginConfig

    # Communication queues
    outbound_queue: Queue[AgentMessage] = field(default_factory=lambda: Queue())

    # State tracking
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat: datetime | None = None
    agent_id: str | None = None
    health: str = "starting"

    # Threads
    _stdout_thread: threading.Thread | None = None
    _running: bool = True

    def start_reader(self) -> None:
        """Start stdout reader thread."""
        self._stdout_thread = threading.Thread(
            target=self._read_stdout_loop, daemon=True, name=f"agent-reader-{self.label}"
        )
        self._stdout_thread.start()

    def _read_stdout_loop(self) -> None:
        """Read JSON lines from agent stdout."""
        if self.process.stdout is None:
            return

        while self._running and self.process.poll() is None:
            try:
                line = self.process.stdout.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                # Parse and enqueue message
                msg = parse_agent_message(line)
                self.outbound_queue.put(msg)

                # Update heartbeat tracker
                if msg.type == "heartbeat":
                    self.last_heartbeat = msg.timestamp

            except Exception as e:
                # Log error but keep reading
                print(f"[{self.label}] Parse error: {e}")

    def send_command(self, cmd: OrchestratorCommand) -> None:
        """Write command to agent stdin."""
        if self.process.poll() is not None:
            return  # Process dead

        if self.process.stdin is None:
            return

        try:
            json_line = cmd.model_dump_json() + "\n"
            self.process.stdin.write(json_line)
            self.process.stdin.flush()
        except Exception as e:
            print(f"[{self.label}] Command send error: {e}")

    def read_message(self, timeout: float = 0.001) -> AgentMessage | None:
        """Non-blocking read from message queue."""
        try:
            return self.outbound_queue.get(timeout=timeout)
        except Empty:
            return None

    def is_alive(self) -> bool:
        """Check if process is running."""
        return self.process.poll() is None

    def shutdown(self) -> None:
        """Send shutdown command and wait."""
        from mimolo.core.protocol import CommandType

        self._running = False
        self.send_command(OrchestratorCommand(cmd=CommandType.SHUTDOWN))

        # Wait up to 3 seconds for clean exit
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


class AgentProcessManager:
    """Spawns and manages Field-Agent subprocesses."""

    def __init__(self, config: Any):  # Config type
        """Initialize manager.

        Args:
            config: Main configuration object
        """
        self.config = config
        self.agents: dict[str, AgentHandle] = {}

    def spawn_agent(self, label: str, plugin_config: Any) -> AgentHandle:
        """Spawn a Field-Agent subprocess.

        Args:
            label: Plugin label
            plugin_config: PluginConfig for this agent

        Returns:
            AgentHandle for managing the subprocess
        """
        # Resolve agent script path - only allow from user_plugins or plugins directories
        args_with_resolved_path: list[str] = []
        for arg in plugin_config.args:
            if arg.endswith(".py"):
                # Try user_plugins first, then plugins
                user_path = Path(__file__).parent.parent / "user_plugins" / arg
                plugins_path = Path(__file__).parent.parent / "plugins" / arg

                if user_path.exists():
                    args_with_resolved_path.append(str(user_path.resolve()))
                elif plugins_path.exists():
                    args_with_resolved_path.append(str(plugins_path.resolve()))
                else:
                    raise FileNotFoundError(
                        f"Field-Agent script not found: {arg} (searched user_plugins and plugins)"
                    )
            else:
                args_with_resolved_path.append(arg)

        # Build command
        cmd = [plugin_config.executable] + args_with_resolved_path

        # Spawn process
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

        # Create handle and start reader
        handle = AgentHandle(label=label, process=proc, config=plugin_config)
        handle.start_reader()

        self.agents[label] = handle
        return handle

    def shutdown_all(self) -> None:
        """Shutdown all managed agents."""
        for handle in self.agents.values():
            handle.shutdown()
        self.agents.clear()
```

## mimolo/core/aggregate.py

``` py
"""Segment aggregation builder and filter application.

The aggregator collects events during an open segment, groups data by
data_header, and applies plugin-specific filters when the segment closes.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from mimolo.core.cooldown import SegmentState
from mimolo.core.errors import AggregationError
from mimolo.core.event import Event, EventRef, Segment
from mimolo.core.registry import PluginRegistry


class SegmentAggregator:
    """Builds segments by collecting events and applying aggregation filters.

    The aggregator:
    - Buffers events during an open segment
    - Groups data by plugin data_header
    - Applies each plugin's filter_method on segment close
    - Constructs final Segment objects
    """

    def __init__(self, registry: PluginRegistry) -> None:
        """Initialize aggregator with plugin registry.

        Args:
            registry: Plugin registry for accessing filter methods.
        """
        self._registry = registry
        self._event_refs: list[EventRef] = []
        self._data_buffers: dict[str, list[Any]] = defaultdict(list)

    def add_event(self, event: Event) -> None:
        """Add an event to the current segment.

        Args:
            event: Event to add.
        """
        # Store lightweight event reference
        self._event_refs.append(EventRef.from_event(event))

        # If the plugin has a data_header and event.data contains it, buffer the value
        spec = self._registry.get_spec(event.label)
        if spec and spec.data_header and event.data:
            if spec.data_header in event.data:
                value = event.data[spec.data_header]
                self._data_buffers[spec.data_header].append(value)

    def build_segment(self, segment_state: SegmentState) -> Segment:
        """Build final segment by applying filters and constructing Segment object.

        Args:
            segment_state: State tracking from cooldown timer.

        Returns:
            Constructed Segment with aggregated data.

        Raises:
            AggregationError: If any filter fails.
        """
        # Apply filters to each data_header buffer
        aggregated: dict[str, Any] = {}

        for data_header, items in self._data_buffers.items():
            # Find the plugin that owns this data_header
            plugin_spec = None
            plugin_instance = None

            for spec, instance in self._registry.list_all():
                if spec.data_header == data_header:
                    plugin_spec = spec
                    plugin_instance = instance
                    break

            if plugin_instance is None:
                # No plugin found for this data_header - shouldn't happen
                # but we'll handle it gracefully
                aggregated[data_header] = items
                continue

            # Apply the plugin's filter method
            try:
                filtered = plugin_instance.filter_method(items)
                aggregated[data_header] = filtered
            except Exception as e:
                raise AggregationError(
                    plugin_label=plugin_spec.label
                    if plugin_spec
                    else "unknown",
                    data_header=data_header,
                    original_error=e,
                ) from e

        # Calculate duration
        duration_s = (segment_state.last_event_time - segment_state.start_time).total_seconds()

        # Build segment
        segment = Segment(
            start=segment_state.start_time,
            end=segment_state.last_event_time,
            duration_s=duration_s,
            events=self._event_refs.copy(),
            aggregated=aggregated,
            resets_count=segment_state.resets_count,
        )

        # Clear buffers for next segment
        self.clear()

        return segment

    def clear(self) -> None:
        """Clear all buffered data (for next segment or cleanup)."""
        self._event_refs.clear()
        self._data_buffers.clear()

    @property
    def event_count(self) -> int:
        """Number of events in current segment."""
        return len(self._event_refs)

    @property
    def has_events(self) -> bool:
        """Check if there are any buffered events."""
        return len(self._event_refs) > 0
```

## mimolo/core/config.py

``` py
"""Configuration management with validation.

Supports TOML and YAML configuration files with Pydantic validation.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from mimolo.core.errors import ConfigError


class MonitorConfig(BaseModel):
    """Monitor runtime configuration."""

    # NEW: Field-Agent support
    journal_dir: str = "./journals"  # Event stream storage
    cache_dir: str = "./cache"  # Agent state cache
    main_system_max_cpu_per_plugin: float = 0.1  # CPU limit per agent
    agent_heartbeat_timeout_s: float = 30.0  # Miss threshold

    cooldown_seconds: float = Field(default=600.0, gt=0)
    poll_tick_ms: float = Field(default=200.0, gt=0)
    log_dir: str = Field(default="./logs")
    log_format: str = "jsonl"
    console_verbosity: Literal["debug", "info", "warning", "error"] = Field(default="info")

    @field_validator("log_dir")
    @classmethod
    def validate_log_dir(cls, v: str) -> str:
        """Validate log directory path."""
        path = Path(v)
        # Parent must exist or be creatable
        if not path.exists():
            parent = path.parent
            if not parent.exists():
                raise ValueError(f"Parent directory does not exist: {parent}")
        return v


class PluginConfig(BaseModel):
    """Per-plugin configuration."""

    enabled: bool = Field(default=True)
    poll_interval_s: float = Field(default=5.0, gt=0)
    resets_cooldown: bool = Field(default=True)
    infrequent: bool = Field(default=False)

    # Plugin-specific fields (stored as extra)
    model_config = {"extra": "allow"}

    # NEW: Field-Agent specific
    plugin_type: Literal["legacy", "field_agent"] = "legacy"  # Auto-detect
    executable: str | None = None  # For field agents: python path or script
    args: list[str] = Field(default_factory=list)  # CLI args for agent
    heartbeat_interval_s: float = Field(default=15.0)  # Expected heartbeat frequency
    agent_flush_interval_s: float = Field(default=60.0)  # How often to send flush command


class Config(BaseModel):
    """Root configuration model."""

    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    plugins: dict[str, PluginConfig] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


def load_config(path: Path | str) -> Config:
    """Load and validate configuration from file.

    Supports both TOML and YAML formats (detected by extension).

    Args:
        path: Path to configuration file.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If file cannot be read, parsed, or validated.
    """
    path = Path(path)

    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        if path.suffix in (".toml",):
            with open(path, "rb") as f:
                data = tomllib.load(f)
        elif path.suffix in (".yaml", ".yml"):
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        else:
            raise ConfigError(f"Unsupported config file extension: {path.suffix}")

    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"Failed to parse configuration file {path}: {e}") from e

    try:
        return Config.model_validate(data)
    except Exception as e:
        raise ConfigError(f"Configuration validation failed: {e}") from e


def load_config_or_default(path: Path | str | None = None) -> Config:
    """Load config from file, or return default if file doesn't exist.

    Args:
        path: Optional path to configuration file. If None, returns default.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If file exists but cannot be parsed or validated.
    """
    if path is None:
        return Config()

    path = Path(path)
    if not path.exists():
        return Config()

    return load_config(path)


def create_default_config(path: Path | str) -> None:
    """Create a default configuration file.

    Args:
        path: Path where to create the config file.

    Raises:
        ConfigError: If file already exists or cannot be written.
    """
    path = Path(path)

    if path.exists():
        raise ConfigError(f"Configuration file already exists: {path}")

    config = Config()

    try:
        if path.suffix == ".toml":
            # Generate TOML manually (tomli doesn't support writing)
            content = _config_to_toml(config)
        elif path.suffix in (".yaml", ".yml"):
            content = yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False)
        else:
            raise ConfigError(f"Unsupported config file extension: {path.suffix}")

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"Failed to write configuration file {path}: {e}") from e


def _config_to_toml(config: Config) -> str:
    """Convert Config to TOML string (simple implementation).

    Args:
        config: Config object to serialize.

    Returns:
        TOML-formatted string.
    """
    lines = ["[monitor]"]
    for key, value in config.monitor.model_dump().items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")

    lines.append("")

    for plugin_name, plugin_config in config.plugins.items():
        lines.append(f"[plugins.{plugin_name}]")
        for key, value in plugin_config.model_dump().items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, list):
                lines.append(f"{key} = {value}")
            else:
                lines.append(f"{key} = {value}")
        lines.append("")

    return "\n".join(lines)
```

## mimolo/core/cooldown.py

``` py
"""Cooldown timer and segment state machine.

The cooldown mechanism tracks activity and determines segment boundaries:

States:
- IDLE: No active segment, waiting for first resetting event
- ACTIVE: Segment open, cooldown timer running
- CLOSING: Cooldown expired, segment ready to close

Transitions:
- IDLE + resetting event → ACTIVE (open segment)
- ACTIVE + resetting event → ACTIVE (reset timer, increment resets_count)
- ACTIVE + non-resetting event → ACTIVE (no timer change)
- ACTIVE + cooldown expired → CLOSING
- CLOSING + segment closed → IDLE
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto


class CooldownState(Enum):
    """Cooldown state machine states."""

    IDLE = auto()
    ACTIVE = auto()
    CLOSING = auto()


@dataclass
class SegmentState:
    """Current segment tracking state.

    Attributes:
        start_time: When the segment opened (first event).
        last_event_time: Most recent event timestamp.
        resets_count: Number of times cooldown was reset.
    """

    start_time: datetime
    last_event_time: datetime
    resets_count: int = 0


class CooldownTimer:
    """Manages cooldown state and segment boundaries.

    The timer tracks when events occur and determines when to close segments
    based on a configurable cooldown period.
    """

    def __init__(self, cooldown_seconds: float) -> None:
        """Initialize cooldown timer.

        Args:
            cooldown_seconds: Duration in seconds after last resetting event
                             before segment closes.
        """
        if cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be positive: {cooldown_seconds}")

        self.cooldown_seconds = cooldown_seconds
        self._state = CooldownState.IDLE
        self._segment: SegmentState | None = None

    @property
    def state(self) -> CooldownState:
        """Current cooldown state."""
        return self._state

    @property
    def segment_state(self) -> SegmentState | None:
        """Current segment state (None if IDLE)."""
        return self._segment

    def on_resetting_event(self, timestamp: datetime) -> bool:
        """Process a resetting event (resets cooldown timer).

        Args:
            timestamp: Event timestamp.

        Returns:
            True if a new segment was opened, False if existing segment was reset.
        """
        if self._state == CooldownState.IDLE:
            # Open new segment
            self._segment = SegmentState(
                start_time=timestamp,
                last_event_time=timestamp,
                resets_count=0,
            )
            self._state = CooldownState.ACTIVE
            return True

        elif self._state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            # Reset timer and update tracking
            if self._segment is None:
                raise RuntimeError("Invalid state: ACTIVE/CLOSING without segment")

            self._segment.last_event_time = timestamp
            self._segment.resets_count += 1
            self._state = CooldownState.ACTIVE
            return False

        return False

    def on_non_resetting_event(self, timestamp: datetime) -> None:
        """Process a non-resetting event (does not reset timer).

        Args:
            timestamp: Event timestamp.
        """
        if self._state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            if self._segment is None:
                raise RuntimeError("Invalid state: ACTIVE/CLOSING without segment")

            # Update last event time but don't reset cooldown
            # Note: This doesn't affect the cooldown calculation which is based
            # on the last *resetting* event
            if timestamp > self._segment.last_event_time:
                self._segment.last_event_time = timestamp

    def check_expiration(self, current_time: datetime) -> bool:
        """Check if cooldown has expired.

        Args:
            current_time: Current time to check against.

        Returns:
            True if cooldown expired and segment should close.
        """
        if self._state != CooldownState.ACTIVE:
            return False

        if self._segment is None:
            raise RuntimeError("Invalid state: ACTIVE without segment")

        # Check if enough time has passed since last event
        elapsed = (current_time - self._segment.last_event_time).total_seconds()
        if elapsed >= self.cooldown_seconds:
            self._state = CooldownState.CLOSING
            return True

        return False

    def close_segment(self) -> SegmentState:
        """Close the current segment and return to IDLE.

        Returns:
            The closed segment state.

        Raises:
            RuntimeError: If no segment is open.
        """
        if self._segment is None:
            raise RuntimeError("Cannot close segment: no segment is open")

        segment = self._segment
        self._segment = None
        self._state = CooldownState.IDLE
        return segment

    def reset(self) -> None:
        """Reset timer to IDLE state (for testing/cleanup)."""
        self._state = CooldownState.IDLE
        self._segment = None

    def time_until_expiration(self, current_time: datetime) -> float | None:
        """Calculate seconds remaining until cooldown expires.

        Args:
            current_time: Current time.

        Returns:
            Seconds remaining, or None if not in ACTIVE state.
        """
        if self._state != CooldownState.ACTIVE or self._segment is None:
            return None

        elapsed = (current_time - self._segment.last_event_time).total_seconds()
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)
```

## mimolo/core/errors.py

``` py
"""Error taxonomy for MiMoLo framework."""

from __future__ import annotations


class MiMoLoError(Exception):
    """Base exception for all MiMoLo errors."""

    pass


class ConfigError(MiMoLoError):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class PluginRegistrationError(MiMoLoError):
    """Raised when plugin registration fails (e.g., duplicate label)."""

    pass


class PluginEmitError(MiMoLoError):
    """Raised when a plugin fails to emit an event."""

    def __init__(self, plugin_label: str, original_error: Exception) -> None:
        """Initialize plugin emit error.

        Args:
            plugin_label: Label of the plugin that failed.
            original_error: The original exception that was raised.
        """
        self.plugin_label = plugin_label
        self.original_error = original_error
        super().__init__(f"Plugin '{plugin_label}' failed to emit event: {original_error}")


class SinkError(MiMoLoError):
    """Raised when a sink fails to write output."""

    pass


class AggregationError(MiMoLoError):
    """Raised when aggregation filter fails."""

    def __init__(self, plugin_label: str, data_header: str, original_error: Exception) -> None:
        """Initialize aggregation error.

        Args:
            plugin_label: Label of the plugin whose filter failed.
            data_header: The data header being aggregated.
            original_error: The original exception that was raised.
        """
        self.plugin_label = plugin_label
        self.data_header = data_header
        self.original_error = original_error
        super().__init__(
            f"Aggregation failed for plugin '{plugin_label}', "
            f"data_header '{data_header}': {original_error}"
        )
```

## mimolo/core/event.py

``` py
"""Event primitives for MiMoLo framework."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    """Instantaneous event emitted by a monitor plugin.

    Attributes:
        timestamp: UTC timestamp when the event occurred.
        label: Plugin label that emitted this event (e.g., "folderwatch").
        event: Short event type identifier (e.g., "file_mod").
        data: Optional arbitrary event payload.
        id: Optional deterministic hash for deduplication.
    """

    timestamp: datetime
    label: str
    event: str
    data: dict[str, Any] | None = None
    id: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        """Validate event fields after initialization."""
        if not self.label:
            raise ValueError("Event label cannot be empty")
        if not self.event:
            raise ValueError("Event type cannot be empty")
        if self.timestamp.tzinfo is None:
            raise ValueError("Event timestamp must be timezone-aware (UTC)")

    @staticmethod
    def compute_id(timestamp: datetime, label: str, event: str, data: dict[str, Any] | None) -> str:
        """Compute deterministic hash ID for an event.

        Args:
            timestamp: Event timestamp.
            label: Plugin label.
            event: Event type.
            data: Event data payload.

        Returns:
            Hex digest of SHA256 hash.
        """
        content = {
            "timestamp": timestamp.isoformat(),
            "label": label,
            "event": event,
            "data": data,
        }
        json_str = json.dumps(content, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()[:16]

    def with_id(self) -> Event:
        """Return a copy of this event with computed ID.

        Returns:
            New Event instance with id field populated.
        """
        if self.id is not None:
            return self
        computed_id = self.compute_id(self.timestamp, self.label, self.event, self.data)
        # We need to use object.__setattr__ since the dataclass is frozen
        new_event = object.__new__(Event)
        object.__setattr__(new_event, "timestamp", self.timestamp)
        object.__setattr__(new_event, "label", self.label)
        object.__setattr__(new_event, "event", self.event)
        object.__setattr__(new_event, "data", self.data)
        object.__setattr__(new_event, "id", computed_id)
        return new_event

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary representation.

        Returns:
            Dictionary with all event fields.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "label": self.label,
            "event": self.event,
            "data": self.data,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create Event from dictionary representation.

        Args:
            data: Dictionary with event fields.

        Returns:
            New Event instance.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        timestamp_str = data.get("timestamp")
        if not timestamp_str:
            raise ValueError("Missing required field: timestamp")

        timestamp = datetime.fromisoformat(timestamp_str)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        return cls(
            timestamp=timestamp,
            label=data["label"],
            event=data["event"],
            data=data.get("data"),
            id=data.get("id"),
        )


@dataclass(frozen=True, slots=True)
class EventRef:
    """Lightweight reference to an event (for segment storage).

    Attributes:
        timestamp: Event timestamp.
        label: Plugin label.
        event: Event type.
    """

    timestamp: datetime
    label: str
    event: str

    @classmethod
    def from_event(cls, event: Event) -> EventRef:
        """Create EventRef from full Event.

        Args:
            event: Full event instance.

        Returns:
            Lightweight event reference.
        """
        return cls(timestamp=event.timestamp, label=event.label, event=event.event)

    def to_dict(self) -> dict[str, Any]:
        """Convert event reference to dictionary.

        Returns:
            Dictionary with timestamp (as 't'), label (as 'l'), event (as 'e').
        """
        return {
            "t": self.timestamp.isoformat(),
            "l": self.label,
            "e": self.event,
        }


@dataclass(slots=True)
class Segment:
    """A time segment containing aggregated events.

    Segments are opened by the first resetting event and closed
    when the cooldown timer expires.

    Attributes:
        start: Segment start timestamp (first event).
        end: Segment end timestamp (last event or last_event + epsilon).
        duration_s: Duration in seconds.
        events: Lightweight event references.
        aggregated: Mapping from data_header to filtered/aggregated result.
        resets_count: Number of cooldown resets during this segment.
    """

    start: datetime
    end: datetime
    duration_s: float
    events: list[EventRef]
    aggregated: dict[str, Any]
    resets_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert segment to dictionary representation.

        Returns:
            Dictionary suitable for JSON serialization.
        """
        # Extract unique labels from events
        labels = sorted({ref.label for ref in self.events})

        return {
            "type": "segment",
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "duration_s": self.duration_s,
            "labels": labels,
            "aggregated": self.aggregated,
            "resets_count": self.resets_count,
            "events": [ref.to_dict() for ref in self.events],
        }
```

## mimolo/core/plugin.py

``` py
"""Plugin contracts and metadata for MiMoLo framework.

Plugins are the core extension point for MiMoLo. Each plugin:
- Registers itself with a unique label
- Emits events when polled
- Optionally declares a data_header for aggregation
- Optionally provides a filter_method for aggregating collected data

Invariants:
- Plugin labels must be unique across all registered plugins
- If data_header is provided, events must include that key in their data dict
- filter_method receives a list of values collected during a segment
- Plugins must be time-bounded (emit_event should not block indefinitely)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from mimolo.core.event import Event


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """Plugin registration specification.

    Attributes:
        label: Unique identifier for this plugin (e.g., "folderwatch").
        data_header: Optional key in event.data for aggregation (e.g., "folders").
        resets_cooldown: Whether events from this plugin reset the cooldown timer.
        infrequent: If True, bypass segment aggregation and flush immediately.
        poll_interval_s: How often to poll this plugin (seconds).
    """

    label: str
    data_header: str | None = None
    resets_cooldown: bool = True
    infrequent: bool = False
    poll_interval_s: float = 5.0

    def __post_init__(self) -> None:
        """Validate plugin spec fields."""
        if not self.label:
            raise ValueError("Plugin label cannot be empty")
        if not self.label.isidentifier():
            raise ValueError(f"Plugin label must be a valid identifier: {self.label}")
        if self.poll_interval_s <= 0:
            raise ValueError(f"poll_interval_s must be positive: {self.poll_interval_s}")


class BaseMonitor(ABC):
    """Abstract base class for monitor plugins.

    Subclasses must:
    1. Define a PluginSpec as a class attribute named 'spec'
    2. Implement emit_event() to return Event or None
    3. Optionally override filter_method() for data aggregation

    Example:
        class MyMonitor(BaseMonitor):
            spec = PluginSpec(
                label="mymonitor",
                data_header="items",
                resets_cooldown=True,
                poll_interval_s=3.0
            )

            def emit_event(self) -> Event | None:
                # Return event or None if nothing to report
                return Event(...)

            @staticmethod
            def filter_method(items: list[Any]) -> Any:
                # Aggregate collected items
                return list(set(items))
    """

    spec: PluginSpec

    @abstractmethod
    def emit_event(self) -> Event | None:
        """Emit an event or None if there is nothing to report.

        This method is called periodically based on spec.poll_interval_s.
        It should be non-blocking and time-bounded.

        Returns:
            Event instance if there is something to report, None otherwise.

        Raises:
            Exception: Any exception will be caught and wrapped in PluginEmitError.
        """
        ...

    @staticmethod
    def filter_method(items: list[Any]) -> Any:
        """Aggregate collected data for this plugin's data_header.

        Called when a segment closes to aggregate all collected values
        for this plugin's data_header.

        Default implementation returns the items list as-is.

        Args:
            items: List of values collected during the segment.

        Returns:
            Aggregated result (can be any JSON-serializable type).
        """
        return items

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate that subclasses define a spec attribute."""
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "spec"):
            raise TypeError(f"{cls.__name__} must define a 'spec' class attribute")
        if not isinstance(cls.spec, PluginSpec):
            raise TypeError(f"{cls.__name__}.spec must be a PluginSpec instance")
```

## mimolo/core/plugin_adapter.py

``` py
"""Adapter to make legacy plugins look like Field-Agents."""

from __future__ import annotations

from datetime import UTC, datetime

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor
from mimolo.core.protocol import HeartbeatMessage, SummaryMessage


class LegacyPluginAdapter:
    """Makes a legacy BaseMonitor plugin behave like a Field-Agent.

    This adapter:
    - Wraps emit_event() and converts to SummaryMessage
    - Generates synthetic heartbeats
    - Provides consistent interface for orchestrator
    """

    def __init__(self, plugin: BaseMonitor, label: str):
        """Initialize adapter.

        Args:
            plugin: Legacy plugin instance
            label: Plugin label
        """
        self.plugin = plugin
        self.label = label
        self.agent_id = f"legacy-{label}"
        self.last_heartbeat = datetime.now(UTC)

    def emit_event(self) -> Event | None:
        """Call wrapped plugin's emit_event."""
        return self.plugin.emit_event()

    def to_summary_message(self, event: Event) -> SummaryMessage:
        """Convert Event to SummaryMessage format.

        Args:
            event: Event from legacy plugin

        Returns:
            SummaryMessage compatible with Field-Agent protocol
        """
        return SummaryMessage(
            timestamp=event.timestamp,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            data=event.data or {},
        )

    def generate_heartbeat(self) -> HeartbeatMessage:
        """Generate synthetic heartbeat for legacy plugin."""
        self.last_heartbeat = datetime.now(UTC)
        return HeartbeatMessage(
            timestamp=self.last_heartbeat,
            agent_id=self.agent_id,
            agent_label=self.label,
            agent_version="legacy",
            metrics={"mode": "legacy", "synthetic": True},
        )
```

## mimolo/core/protocol.py

``` py
"""Field-Agent protocol message types and validation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    """Agent → Orchestrator message types."""

    HANDSHAKE = "handshake"
    SUMMARY = "summary"
    HEARTBEAT = "heartbeat"
    STATUS = "status"
    ERROR = "error"


class CommandType(str, Enum):
    """Orchestrator → Agent command types."""

    ACK = "ack"
    REJECT = "reject"
    FLUSH = "flush"
    STATUS = "status"
    SHUTDOWN = "shutdown"


class AgentMessage(BaseModel):
    """Base message envelope for all agent → orchestrator messages."""

    type: MessageType
    timestamp: datetime
    agent_id: str
    agent_label: str
    protocol_version: str = "0.3"
    agent_version: str
    data: dict[str, Any] = Field(default_factory=dict)

    # Optional fields
    metrics: dict[str, Any] = Field(default_factory=dict)
    health: Literal["ok", "degraded", "overload", "failed"] | None = None
    message: str | None = None


class HandshakeMessage(AgentMessage):
    """Initial agent registration message."""

    type: MessageType = MessageType.HANDSHAKE
    min_app_version: str
    capabilities: list[str]


class SummaryMessage(AgentMessage):
    """Data flush from agent."""

    type: MessageType = MessageType.SUMMARY


class HeartbeatMessage(AgentMessage):
    """Health ping from agent."""

    type: MessageType = MessageType.HEARTBEAT
    metrics: dict[str, Any] = Field(default_factory=dict, description="Required for heartbeats")


class OrchestratorCommand(BaseModel):
    """Base command envelope for orchestrator → agent commands."""

    cmd: CommandType
    args: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


def parse_agent_message(line: str) -> AgentMessage:
    """Parse JSON line into appropriate message type.

    Args:
        line: JSON string from agent stdout

    Returns:
        Parsed message object

    Raises:
        ValueError: If JSON invalid or type unknown
    """
    import json

    data = json.loads(line)
    msg_type = data.get("type")

    if msg_type == MessageType.HANDSHAKE:
        return HandshakeMessage(**data)
    elif msg_type == MessageType.SUMMARY:
        return SummaryMessage(**data)
    elif msg_type == MessageType.HEARTBEAT:
        return HeartbeatMessage(**data)
    else:
        return AgentMessage(**data)
```

## mimolo/core/registry.py

``` py
"""Plugin registry for managing monitor lifecycle and metadata."""

from __future__ import annotations

from typing import Any

from mimolo.core.errors import PluginRegistrationError
from mimolo.core.plugin import BaseMonitor, PluginSpec


class PluginRegistry:
    """Registry for managing plugin lifecycle and metadata.

    Maintains:
    - Mapping from label to (spec, instance)
    - Duplicate label protection
    - Query methods for enabled/resetting/data_header plugins
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._plugins: dict[str, tuple[PluginSpec, BaseMonitor]] = {}

    def add(self, spec: PluginSpec, instance: BaseMonitor) -> None:
        """Register a plugin with the given spec and instance.

        Args:
            spec: Plugin specification.
            instance: Plugin instance (must be a BaseMonitor).

        Raises:
            PluginRegistrationError: If label is already registered or invalid.
        """
        if spec.label in self._plugins:
            raise PluginRegistrationError(f"Plugin label '{spec.label}' is already registered")

        if not isinstance(instance, BaseMonitor):
            raise PluginRegistrationError(
                f"Plugin instance must be a BaseMonitor, got {type(instance)}"
            )

        # Verify the instance's spec matches the provided spec
        if instance.spec != spec:
            raise PluginRegistrationError(
                f"Plugin instance spec does not match provided spec for '{spec.label}'"
            )

        self._plugins[spec.label] = (spec, instance)

    def get(self, label: str) -> tuple[PluginSpec, BaseMonitor] | None:
        """Get plugin spec and instance by label.

        Args:
            label: Plugin label.

        Returns:
            Tuple of (spec, instance) or None if not found.
        """
        return self._plugins.get(label)

    def get_instance(self, label: str) -> BaseMonitor | None:
        """Get plugin instance by label.

        Args:
            label: Plugin label.

        Returns:
            Plugin instance or None if not found.
        """
        entry = self._plugins.get(label)
        return entry[1] if entry else None

    def get_spec(self, label: str) -> PluginSpec | None:
        """Get plugin spec by label.

        Args:
            label: Plugin label.

        Returns:
            Plugin spec or None if not found.
        """
        entry = self._plugins.get(label)
        return entry[0] if entry else None

    def list_all(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List all registered plugins.

        Returns:
            List of (spec, instance) tuples.
        """
        return list(self._plugins.values())

    def list_labels(self) -> list[str]:
        """List all registered plugin labels.

        Returns:
            List of plugin labels.
        """
        return list(self._plugins.keys())

    def list_resetting(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins that reset the cooldown timer.

        Returns:
            List of (spec, instance) tuples for plugins with resets_cooldown=True.
        """
        return [(spec, instance) for spec, instance in self._plugins.values() if spec.resets_cooldown]

    def list_infrequent(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins marked as infrequent.

        Returns:
            List of (spec, instance) tuples for plugins with infrequent=True.
        """
        return [(spec, instance) for spec, instance in self._plugins.values() if spec.infrequent]

    def list_aggregating(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins that participate in segment aggregation.

        Returns:
            List of (spec, instance) tuples for plugins with data_header set
            and infrequent=False.
        """
        return [
            (spec, instance)
            for spec, instance in self._plugins.values()
            if spec.data_header is not None and not spec.infrequent
        ]

    def remove(self, label: str) -> bool:
        """Remove a plugin from the registry.

        Args:
            label: Plugin label to remove.

        Returns:
            True if plugin was removed, False if not found.
        """
        if label in self._plugins:
            del self._plugins[label]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()

    def __len__(self) -> int:
        """Return number of registered plugins."""
        return len(self._plugins)

    def __contains__(self, label: str) -> bool:
        """Check if a plugin label is registered."""
        return label in self._plugins

    def to_dict(self) -> dict[str, Any]:
        """Export registry metadata to dictionary.

        Returns:
            Dictionary mapping labels to spec dictionaries.
        """
        return {
            label: {
                "label": spec.label,
                "data_header": spec.data_header,
                "resets_cooldown": spec.resets_cooldown,
                "infrequent": spec.infrequent,
                "poll_interval_s": spec.poll_interval_s,
            }
            for label, (spec, _) in self._plugins.items()
        }
```

## mimolo/core/runtime.py

``` py
"""Runtime orchestrator for MiMoLo.

The orchestrator:
- Loads configuration
- Registers plugins
- Runs main event loop
- Handles plugin polling and scheduling
- Manages cooldown and segment lifecycle
- Writes output via sinks
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from rich.console import Console

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.config import Config
from mimolo.core.cooldown import CooldownState, CooldownTimer
from mimolo.core.errors import AggregationError, PluginEmitError, SinkError
from mimolo.core.event import Event
from mimolo.core.registry import PluginRegistry
from mimolo.core.sink import ConsoleSink, create_sink


class PluginScheduler:
    """Schedules plugin polling based on poll_interval_s."""

    def __init__(self) -> None:
        """Initialize scheduler."""
        self._last_poll: dict[str, float] = {}

    def should_poll(self, label: str, interval_s: float, current_time: float) -> bool:
        """Check if plugin should be polled.

        Args:
            label: Plugin label.
            interval_s: Poll interval in seconds.
            current_time: Current time (from time.time()).

        Returns:
            True if enough time has elapsed since last poll.
        """
        last = self._last_poll.get(label, 0.0)
        if current_time - last >= interval_s:
            self._last_poll[label] = current_time
            return True
        return False

    def reset(self, label: str) -> None:
        """Reset poll timer for a plugin."""
        self._last_poll.pop(label, None)


class PluginErrorTracker:
    """Tracks plugin errors and implements exponential backoff."""

    def __init__(self, base_backoff_s: float = 1.0, max_backoff_s: float = 300.0) -> None:
        """Initialize error tracker.

        Args:
            base_backoff_s: Base backoff duration.
            max_backoff_s: Maximum backoff duration.
        """
        self.base_backoff_s = base_backoff_s
        self.max_backoff_s = max_backoff_s
        self._error_counts: dict[str, int] = defaultdict(int)
        self._backoff_until: dict[str, float] = {}

    def record_error(self, label: str) -> None:
        """Record an error for a plugin.

        Args:
            label: Plugin label.
        """
        self._error_counts[label] += 1
        count = self._error_counts[label]
        backoff = min(self.base_backoff_s * (2 ** (count - 1)), self.max_backoff_s)
        self._backoff_until[label] = time.time() + backoff

    def record_success(self, label: str) -> None:
        """Record successful operation for a plugin.

        Args:
            label: Plugin label.
        """
        self._error_counts[label] = 0
        self._backoff_until.pop(label, None)

    def is_quarantined(self, label: str) -> bool:
        """Check if plugin is in backoff period.

        Args:
            label: Plugin label.

        Returns:
            True if plugin should not be polled yet.
        """
        until = self._backoff_until.get(label)
        if until is None:
            return False
        return time.time() < until


class Runtime:
    """Main orchestrator for MiMoLo framework."""

    def __init__(
        self,
        config: Config,
        registry: PluginRegistry,
        console: Console | None = None,
    ) -> None:
        """Initialize runtime.

        Args:
            config: Configuration object.
            registry: Plugin registry with registered plugins.
            console: Optional rich console for output.
        """
        self.config = config
        self.registry = registry
        self.console = console or Console()

        # Core components
        self.cooldown = CooldownTimer(config.monitor.cooldown_seconds)
        self.aggregator = SegmentAggregator(registry)
        self.scheduler = PluginScheduler()
        self.error_tracker = PluginErrorTracker()

        # Sinks
        log_dir = Path(config.monitor.log_dir)
        log_format = cast(Literal["jsonl", "yaml", "md"], config.monitor.log_format)
        self.file_sink = create_sink(log_format, log_dir)
        self.console_sink = ConsoleSink(config.monitor.console_verbosity)

        # Runtime state
        self._running = False
        self._tick_count = 0
        # Field-Agent support (added incrementally; imports are deferred so
        # runtime can operate without the new modules present)
        try:
            from mimolo.core.agent_process import AgentProcessManager
            from mimolo.core.plugin_adapter import LegacyPluginAdapter

            self.agent_manager: AgentProcessManager | None = AgentProcessManager(config)
            self.legacy_adapters: dict[str, LegacyPluginAdapter] = {}
            self.agent_last_flush: dict[str, datetime] = {}  # Track last flush time per agent

            # First, spawn Field-Agent plugins directly from config
            for label, plugin_config in config.plugins.items():
                if not plugin_config.enabled:
                    continue

                if plugin_config.plugin_type == "field_agent":
                    if plugin_config.executable:
                        try:
                            self.agent_manager.spawn_agent(label, plugin_config)
                            self.console.print(f"[green]Spawned Field-Agent: {label}[/green]")
                        except Exception as e:
                            self.console.print(f"[red]Failed to spawn agent {label}: {e}[/red]")
                            import traceback

                            self.console.print(f"[red]{traceback.format_exc()}[/red]")

            # Then, wrap legacy plugins from registry
            for spec, instance in registry.list_all():
                # Only wrap if not configured as field_agent
                legacy_config = config.plugins.get(spec.label)
                if not legacy_config or legacy_config.plugin_type != "field_agent":
                    try:
                        adapter = LegacyPluginAdapter(instance, spec.label)
                        self.legacy_adapters[spec.label] = adapter
                    except Exception:
                        # If adapter construction fails, skip wrapping but
                        # keep existing behavior; error will surface when polled.
                        pass
        except Exception as e:
            # If the new modules don't exist yet, keep runtime working.
            self.console.print(f"[yellow]Field-Agent support unavailable: {e}[/yellow]")
            self.agent_manager = None
            self.legacy_adapters = {}

    def run(self, max_iterations: int | None = None) -> None:
        """Run the main event loop.

        Args:
            max_iterations: Optional maximum iterations (for testing/dry-run).
        """
        self._running = True
        self.console.print("[bold green]MiMoLo starting...[/bold green]")
        self.console.print(f"Cooldown: {self.config.monitor.cooldown_seconds}s")
        self.console.print(f"Poll tick: {self.config.monitor.poll_tick_ms}ms")

        # Count both legacy plugins and Field-Agents
        agent_count = 0
        if self.agent_manager:
            agent_count = len(self.agent_manager.agents)
        total_plugins = len(self.registry) + agent_count

        self.console.print(f"Registered plugins: {len(self.registry)}")
        if agent_count > 0:
            self.console.print(f"Field-Agents: {agent_count}")
        self.console.print()

        if total_plugins == 0:
            self.console.print("[yellow]No plugins registered. Nothing to monitor.[/yellow]")
            return

        try:
            while self._running:
                self._tick()

                if max_iterations is not None:
                    max_iterations -= 1
                    if max_iterations <= 0:
                        break

                # Sleep for poll tick duration
                time.sleep(self.config.monitor.poll_tick_ms / 1000.0)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Shutting down...[/yellow]")
        finally:
            self._shutdown()

    def _tick(self) -> None:
        """Execute one tick of the event loop."""
        self._tick_count += 1
        current_time = time.time()
        now = datetime.now(UTC)

        # Check for cooldown expiration
        if self.cooldown.check_expiration(now):
            self._close_segment()
        # Poll plugins (legacy adapters if available)
        for spec, instance in self.registry.list_all():
            # Skip quarantined plugins
            if self.error_tracker.is_quarantined(spec.label):
                continue

            # Check if should poll
            if not self.scheduler.should_poll(spec.label, spec.poll_interval_s, current_time):
                continue

            try:
                adapter = (
                    self.legacy_adapters.get(spec.label)
                    if getattr(self, "legacy_adapters", None) is not None
                    else None
                )
                if adapter is not None:
                    # Use adapter that exposes a Field-Agent-like interface
                    event = adapter.emit_event()
                    if event is not None:
                        # Convert legacy Event to a summary message and route through
                        # the agent message handlers so both plugin types share logic.
                        msg = adapter.to_summary_message(event)
                        try:
                            self._handle_agent_message(msg, spec)
                            self.error_tracker.record_success(spec.label)
                        except Exception:
                            # Fall back to original behavior if routing fails
                            self._handle_event(event, spec)
                            self.error_tracker.record_success(spec.label)
                    continue

                # Fallback: direct legacy plugin polling (existing behavior)
                event = instance.emit_event()
                if event is not None:
                    self._handle_event(event, spec)
                    self.error_tracker.record_success(spec.label)
            except Exception as e:
                error = PluginEmitError(spec.label, e)
                self.console.print(f"[red]Plugin error: {error}[/red]")
                self.error_tracker.record_error(spec.label)

        # Poll Field-Agent messages (if agent manager is present)
        agm = getattr(self, "agent_manager", None)
        if agm is not None:
            from mimolo.core.protocol import CommandType, OrchestratorCommand

            now = datetime.now(UTC)

            for label, handle in list(agm.agents.items()):
                # Check if it's time to send flush command
                plugin_config = self.config.plugins.get(label)
                if plugin_config and plugin_config.plugin_type == "field_agent":
                    last_flush = self.agent_last_flush.get(label)
                    flush_interval = plugin_config.agent_flush_interval_s

                    # Send flush if interval elapsed or never flushed
                    if last_flush is None or (now - last_flush).total_seconds() >= flush_interval:
                        try:
                            flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
                            handle.send_command(flush_cmd)
                            self.agent_last_flush[label] = now
                            if self.config.monitor.console_verbosity == "debug":
                                self.console.print(f"[cyan]Sent flush to {label}[/cyan]")
                        except Exception as e:
                            self.console.print(f"[red]Error sending flush to {label}: {e}[/red]")

                # Drain all available messages from this agent
                while (msg := handle.read_message(timeout=0.001)) is not None:
                    try:
                        # Message routing by type (msg.type may be str or Enum)
                        mtype = getattr(msg, "type", None)
                        if isinstance(mtype, str):
                            t = mtype
                        else:
                            t = str(mtype).lower()

                        if t == "heartbeat" or t.endswith("heartbeat"):
                            self._handle_heartbeat(label, msg)
                        elif t == "summary" or t.endswith("summary"):
                            self._handle_agent_summary(label, msg)
                        elif t == "error" or t.endswith("error"):
                            # Log agent-reported error
                            try:
                                message = getattr(msg, "message", None) or getattr(msg, "data", None)
                                self.console.print(f"[red]Agent {label} error: {message}[/red]")
                            except Exception:
                                self.console.print(f"[red]Agent {label} reported an error[/red]")
                    except Exception as e:
                        self.console.print(f"[red]Error handling agent message from {label}: {e}[/red]")

    def _handle_event(self, event: Event, spec: Any) -> None:
        """Handle an event from a plugin.

        Args:
            event: Event emitted by plugin.
            spec: Plugin spec.
        """
        # Write to console sink
        if self.config.monitor.console_verbosity in ("debug", "info"):
            self.console_sink.write_event(event)

        # Handle infrequent events separately
        if spec.infrequent:
            try:
                self.file_sink.write_event(event)
            except SinkError as e:
                self.console.print(f"[red]Sink error: {e}[/red]")
            return

        # Regular event: participate in segment aggregation
        if spec.resets_cooldown:
            opened = self.cooldown.on_resetting_event(event.timestamp)
            if opened and self.config.monitor.console_verbosity == "debug":
                self.console.print(f"[green]Segment opened at {event.timestamp}[/green]")
        else:
            self.cooldown.on_non_resetting_event(event.timestamp)

        # Add to aggregator if segment is active
        if self.cooldown.state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            self.aggregator.add_event(event)

    def _coerce_timestamp(self, ts: object) -> datetime:
        """Coerce a timestamp value (str or datetime) into timezone-aware datetime."""
        if isinstance(ts, datetime):
            timestamp = ts
        else:
            # Try parsing ISO format string
            try:
                timestamp = datetime.fromisoformat(str(ts))
            except Exception:
                timestamp = datetime.now(UTC)

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp

    def _handle_agent_summary(self, label: str, msg: object) -> None:
        """Write Field-Agent summary directly to file.

        Field-Agents pre-aggregate their own data, so we don't re-aggregate.
        Just log the summary event directly.

        Args:
            label: agent label
            msg: parsed message object with attributes `timestamp`, `agent_label`, `data`.
        """
        try:
            ts = getattr(msg, "timestamp", None)
            timestamp = self._coerce_timestamp(ts)
            agent_label = getattr(msg, "agent_label", label)
            raw_data: Any = getattr(msg, "data", None)
            # Ensure data is always a dict
            if not isinstance(raw_data, dict):
                data: dict[str, Any] = {}
            else:
                data = cast(dict[str, Any], raw_data)

            # Determine event type if provided, else default to 'summary'
            event_type: str = "summary"
            evt = data.get("event")
            typ = data.get("type")
            if evt:
                event_type = str(evt)
            elif typ:
                event_type = str(typ)

            event = Event(timestamp=timestamp, label=agent_label, event=event_type, data=data)

            # Write summary directly to file (agent already aggregated the data)
            try:
                self.file_sink.write_event(event)
            except SinkError as e:
                self.console.print(f"[red]Sink error writing agent summary: {e}[/red]")

            # Also log to console if verbose
            if self.config.monitor.console_verbosity in ("debug", "info"):
                self.console_sink.write_event(event)

        except Exception as e:
            self.console.print(f"[red]Error handling agent summary {label}: {e}[/red]")

    def _handle_heartbeat(self, label: str, msg: object) -> None:
        """Handle a heartbeat message from a Field-Agent.

        Updates agent health state and optionally logs to console.
        Heartbeats are NOT written to file - they're for health monitoring only.
        """
        try:
            ts = getattr(msg, "timestamp", None)
            timestamp = self._coerce_timestamp(ts)

            # Update AgentProcessManager handle state if present
            agm = getattr(self, "agent_manager", None)
            if agm is not None:
                try:
                    handle = agm.agents.get(label)
                    if handle is not None:
                        handle.last_heartbeat = timestamp
                except Exception:
                    pass

            # Log to console in debug mode
            if self.config.monitor.console_verbosity == "debug":
                metrics = getattr(msg, "metrics", {})
                metrics_str = f" | {metrics}" if metrics else ""
                self.console.print(f"[cyan]❤️  {label}{metrics_str}[/cyan]")
        except Exception as e:
            self.console.print(f"[red]Error handling heartbeat from {label}: {e}[/red]")

    def _flush_all_agents(self) -> None:
        """Send flush command to all active Field-Agents."""
        agm = getattr(self, "agent_manager", None)
        if agm is not None:
            from mimolo.core.protocol import CommandType, OrchestratorCommand

            flush_cmd = OrchestratorCommand(cmd=CommandType.FLUSH)
            for label, handle in agm.agents.items():
                try:
                    handle.send_command(flush_cmd)
                    if self.config.monitor.console_verbosity == "debug":
                        self.console.print(f"[cyan]Sent flush to {label}[/cyan]")
                except Exception as e:
                    self.console.print(f"[red]Error sending flush to {label}: {e}[/red]")

    def _handle_agent_message(self, msg: object, spec: Any | None = None) -> None:
        """Generic entry point for handling agent-style messages.

        This will dispatch to the appropriate specific handler based on message type.
        """
        mtype = getattr(msg, "type", None)
        try:
            if isinstance(mtype, str):
                t = mtype
            else:
                t = str(mtype).lower()

            if t == "heartbeat" or t.endswith("heartbeat"):
                self._handle_heartbeat(getattr(msg, "agent_label", "unknown"), msg)
            elif t == "summary" or t.endswith("summary"):
                self._handle_agent_summary(getattr(msg, "agent_label", "unknown"), msg)
            elif t == "error" or t.endswith("error"):
                # Log error
                self.console.print(f"[red]Agent error: {getattr(msg, 'message', None)}[/red]")
            else:
                # Unknown type: try treating as summary
                self._handle_agent_summary(getattr(msg, "agent_label", "unknown"), msg)
        except Exception as e:
            self.console.print(f"[red]Error handling agent message: {e}[/red]")

    def _close_segment(self) -> None:
        """Close current segment and write to sinks."""
        # Send flush command to all Field-Agents before closing segment
        self._flush_all_agents()

        if not self.aggregator.has_events:
            # Empty segment, just close cooldown
            try:
                self.cooldown.close_segment()
            except RuntimeError:
                pass  # No segment open
            return

        try:
            segment_state = self.cooldown.close_segment()
            segment = self.aggregator.build_segment(segment_state)

            # Write to sinks
            self.console_sink.write_segment(segment)
            self.file_sink.write_segment(segment)

            if self.config.monitor.console_verbosity in ("debug", "info"):
                self.console.print(f"[blue]Segment closed: {segment.duration_s:.1f}s[/blue]")

        except AggregationError as e:
            self.console.print(f"[red]Aggregation error: {e}[/red]")
            self.aggregator.clear()
        except SinkError as e:
            self.console.print(f"[red]Sink error: {e}[/red]")
        except Exception as e:
            self.console.print(f"[red]Unexpected error closing segment: {e}[/red]")
            self.aggregator.clear()

    def _shutdown(self) -> None:
        """Clean shutdown: close any open segment and flush sinks."""
        self.console.print("[yellow]Shutting down...[/yellow]")

        # Close any open segment
        if self.cooldown.state in (CooldownState.ACTIVE, CooldownState.CLOSING):
            try:
                self._close_segment()
            except Exception as e:
                self.console.print(f"[red]Error during shutdown: {e}[/red]")

        # Shutdown all Field-Agents
        agm = getattr(self, "agent_manager", None)
        if agm is not None:
            try:
                self.console.print("[yellow]Shutting down Field-Agents...[/yellow]")
                agm.shutdown_all()
            except Exception as e:
                self.console.print(f"[red]Error shutting down agents: {e}[/red]")

        # Flush and close sinks
        try:
            self.file_sink.flush()
            self.file_sink.close()
            self.console.print("[green]MiMoLo stopped.[/green]")
        except Exception as e:
            self.console.print(f"[red]Error closing sinks: {e}[/red]")

    def stop(self) -> None:
        """Request graceful stop."""
        self._running = False
```

## mimolo/core/sink.py

``` py
"""Log writers (sinks) for events and segments.

Supports:
- JSONL (default): One JSON object per line
- YAML: Human-readable YAML documents
- Markdown: Summary tables
- Daily file rotation
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from mimolo.core.errors import SinkError
from mimolo.core.event import Event, Segment


class BaseSink:
    """Abstract base for log sinks."""

    def write_segment(self, segment: Segment) -> None:
        """Write a completed segment.

        Args:
            segment: Segment to write.
        """
        raise NotImplementedError

    def write_event(self, event: Event) -> None:
        """Write an infrequent/standalone event.

        Args:
            event: Event to write.
        """
        raise NotImplementedError

    def flush(self) -> None:
        """Flush any buffered data."""
        pass

    def close(self) -> None:
        """Close resources."""
        pass


class JSONLSink(BaseSink):
    """JSONL (newline-delimited JSON) sink with daily rotation."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize JSONL sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._current_file: Path | None = None
        self._file_handle: Any = None

        # Create log directory with restricted permissions
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(
                f"Failed to create log directory {log_dir}: {e}"
            ) from e

    def _get_current_file(self, timestamp: datetime) -> Path:
        """Get the log file path for the given timestamp.

        Args:
            timestamp: Timestamp to determine date.

        Returns:
            Path to log file.
        """
        date_str = timestamp.strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.{self.name_prefix}.jsonl"

    def _ensure_file_open(self, timestamp: datetime) -> None:
        """Ensure the correct file is open for writing.

        Args:
            timestamp: Timestamp to determine which file to open.
        """
        target_file = self._get_current_file(timestamp)

        # If already open and correct, nothing to do
        if self._current_file == target_file and self._file_handle is not None:
            return

        # Close old file if open
        if self._file_handle is not None:
            self._file_handle.close()

        # Open new file
        try:
            self._file_handle = open(target_file, "a", encoding="utf-8")
            self._current_file = target_file
        except Exception as e:
            raise SinkError(
                f"Failed to open log file {target_file}: {e}"
            ) from e

    def write_segment(self, segment: Segment) -> None:
        """Write segment as JSONL record.

        Args:
            segment: Segment to write.
        """
        try:
            self._ensure_file_open(segment.end)
            record = segment.to_dict()
            json.dump(record, self._file_handle, separators=(",", ":"))
            self._file_handle.write("\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write segment: {e}") from e

    def write_event(self, event: Event) -> None:
        """Write standalone event as JSONL record.

        Args:
            event: Event to write.
        """
        try:
            self._ensure_file_open(event.timestamp)
            record = {"type": "event", **event.to_dict()}
            json.dump(record, self._file_handle, separators=(",", ":"))
            self._file_handle.write("\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write event: {e}") from e

    def flush(self) -> None:
        """Flush buffered data."""
        if self._file_handle is not None:
            self._file_handle.flush()

    def close(self) -> None:
        """Close file handle."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._current_file = None


class YAMLSink(BaseSink):
    """YAML sink with daily rotation."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize YAML sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._current_file: Path | None = None
        self._file_handle: Any = None

        # Create log directory
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(
                f"Failed to create log directory {log_dir}: {e}"
            ) from e

    def _get_current_file(self, timestamp: datetime) -> Path:
        """Get the log file path for the given timestamp."""
        date_str = timestamp.strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.{self.name_prefix}.yaml"

    def _ensure_file_open(self, timestamp: datetime) -> None:
        """Ensure the correct file is open for writing."""
        target_file = self._get_current_file(timestamp)

        if self._current_file == target_file and self._file_handle is not None:
            return

        if self._file_handle is not None:
            self._file_handle.close()

        try:
            self._file_handle = open(target_file, "a", encoding="utf-8")
            self._current_file = target_file
        except Exception as e:
            raise SinkError(
                f"Failed to open log file {target_file}: {e}"
            ) from e

    def write_segment(self, segment: Segment) -> None:
        """Write segment as YAML document."""
        try:
            self._ensure_file_open(segment.end)
            record = segment.to_dict()
            yaml.dump(record, self._file_handle, default_flow_style=False, sort_keys=False)
            self._file_handle.write("---\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write segment: {e}") from e

    def write_event(self, event: Event) -> None:
        """Write standalone event as YAML document."""
        try:
            self._ensure_file_open(event.timestamp)
            record = {"type": "event", **event.to_dict()}
            yaml.dump(record, self._file_handle, default_flow_style=False, sort_keys=False)
            self._file_handle.write("---\n")
            self._file_handle.flush()
        except Exception as e:
            if isinstance(e, SinkError):
                raise
            raise SinkError(f"Failed to write event: {e}") from e

    def flush(self) -> None:
        """Flush buffered data."""
        if self._file_handle is not None:
            self._file_handle.flush()

    def close(self) -> None:
        """Close file handle."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None
            self._current_file = None


class MarkdownSink(BaseSink):
    """Markdown sink for summary tables."""

    def __init__(self, log_dir: Path, name_prefix: str = "mimolo") -> None:
        """Initialize Markdown sink.

        Args:
            log_dir: Directory for log files.
            name_prefix: Prefix for log filenames.
        """
        self.log_dir = Path(log_dir)
        self.name_prefix = name_prefix
        self._segments: list[Segment] = []
        self._events: list[Event] = []
        self._current_date: str | None = None

        # Create log directory
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        except Exception as e:
            raise SinkError(
                f"Failed to create log directory {log_dir}: {e}"
            ) from e

    def write_segment(self, segment: Segment) -> None:
        """Buffer segment for markdown table."""
        self._segments.append(segment)
        self._flush_if_new_day(segment.end)

    def write_event(self, event: Event) -> None:
        """Buffer event for markdown table."""
        self._events.append(event)
        self._flush_if_new_day(event.timestamp)

    def _flush_if_new_day(self, timestamp: datetime) -> None:
        """Flush to file if we've crossed into a new day."""
        date_str = timestamp.strftime("%Y-%m-%d")
        if self._current_date and self._current_date != date_str:
            self._write_markdown_file()
            self._segments.clear()
            self._events.clear()
        self._current_date = date_str

    def _write_markdown_file(self) -> None:
        """Write accumulated segments/events as markdown table."""
        if not self._current_date:
            return

        file_path = self.log_dir / f"{self._current_date}.{self.name_prefix}.md"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# MiMoLo Log - {self._current_date}\n\n")

                if self._segments:
                    f.write("## Segments\n\n")
                    f.write("| Start | End | Duration (s) | Labels | Resets | Events |\n")
                    f.write("|-------|-----|--------------|--------|--------|--------|\n")
                    for seg in self._segments:
                        labels = ", ".join(sorted({ref.label for ref in seg.events}))
                        f.write(
                            f"| {seg.start.strftime('%H:%M:%S')} | "
                            f"{seg.end.strftime('%H:%M:%S')} | "
                            f"{seg.duration_s:.1f} | "
                            f"{labels} | "
                            f"{seg.resets_count} | "
                            f"{len(seg.events)} |\n"
                        )
                    f.write("\n")

                if self._events:
                    f.write("## Standalone Events\n\n")
                    f.write("| Timestamp | Label | Event | Data |\n")
                    f.write("|-----------|-------|-------|------|\n")
                    for evt in self._events:
                        data_str = json.dumps(evt.data) if evt.data else ""
                        f.write(
                            f"| {evt.timestamp.strftime('%H:%M:%S')} | "
                            f"{evt.label} | "
                            f"{evt.event} | "
                            f"{data_str} |\n"
                        )
                    f.write("\n")

        except Exception as e:
            raise SinkError(
                f"Failed to write markdown file {file_path}: {e}"
            ) from e

    def flush(self) -> None:
        """Flush accumulated data to file."""
        if self._segments or self._events:
            self._write_markdown_file()

    def close(self) -> None:
        """Flush and close."""
        self.flush()


class ConsoleSink(BaseSink):
    """Console output sink (for debugging/monitoring)."""

    def __init__(self, verbosity: Literal["debug", "info", "warning", "error"] = "info") -> None:
        """Initialize console sink.

        Args:
            verbosity: Console verbosity level.
        """
        self.verbosity = verbosity

    def write_segment(self, segment: Segment) -> None:
        """Print segment summary to console."""
        labels = sorted({ref.label for ref in segment.events})
        print(
            f"[SEGMENT] {segment.start.strftime('%H:%M:%S')} -> "
            f"{segment.end.strftime('%H:%M:%S')} "
            f"({segment.duration_s:.1f}s) | "
            f"Labels: {', '.join(labels)} | "
            f"Events: {len(segment.events)} | "
            f"Resets: {segment.resets_count}"
        )

    def write_event(self, event: Event) -> None:
        """Print event to console."""
        print(
            f"[EVENT] {event.timestamp.strftime('%H:%M:%S')} | "
            f"{event.label}.{event.event} | "
            f"Data: {event.data if event.data else 'None'}"
        )


def create_sink(
    format_type: Literal["jsonl", "yaml", "md"],
    log_dir: Path,
    name_prefix: str = "mimolo",
) -> BaseSink:
    """Factory function to create appropriate sink.

    Args:
        format_type: Type of sink to create.
        log_dir: Directory for log files.
        name_prefix: Prefix for log filenames.

    Returns:
        Configured sink instance.

    Raises:
        ValueError: If format_type is unknown.
    """
    if format_type == "jsonl":
        return JSONLSink(log_dir, name_prefix)
    elif format_type == "yaml":
        return YAMLSink(log_dir, name_prefix)
    elif format_type == "md":
        return MarkdownSink(log_dir, name_prefix)
    else:
        raise ValueError(f"Unknown sink format: {format_type}")
```

## mimolo/plugins/__init__.py

``` py
"""MiMoLo plugin modules."""

from mimolo.plugins.folderwatch import FolderWatchMonitor
from mimolo.user_plugins.example import ExampleMonitor

__all__ = [
    "ExampleMonitor",
    "FolderWatchMonitor",
]
```

## mimolo/plugins/folderwatch.py

``` py
"""Folder watch monitor plugin.

Monitors directories for file changes with specific extensions.
Demonstrates data_header with custom filter for unique sorted folders.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class FolderWatchMonitor(BaseMonitor):
    """Monitor that watches directories for file modifications.

    Emits events when files with matching extensions are modified.
    Aggregates unique parent folders during segments.
    """

    spec = PluginSpec(
        label="folderwatch",
        data_header="folders",
        resets_cooldown=True,
        infrequent=False,
        poll_interval_s=5.0,
    )

    def __init__(
        self,
        watch_dirs: list[str] | None = None,
        extensions: list[str] | None = None,
        emit_on_discovery: bool = False,
    ) -> None:
        """Initialize folder watch monitor.

        Args:
            watch_dirs: List of directory paths to watch.
            extensions: List of file extensions to monitor (without dots).
            emit_on_discovery: If True, emit an event the first time a file is seen.
        """
        self.watch_dirs = [Path(d) for d in (watch_dirs or [])]
        # Normalize extensions to be case-insensitive and dot-free
        self.extensions = {
            ext.lower().lstrip(".") for ext in (extensions or [])
        }
        self.emit_on_discovery = emit_on_discovery
        self._last_mtimes: dict[Path, float] = {}
        self._validated: bool = False
        self._ack_emitted: bool = False
        self._warn_emitted: bool = False

    def _validate_and_filter(self) -> tuple[list[Path], list[str], list[str]]:
        """Validate configured watch directories and normalize them without raising.

        Returns:
            (valid_dirs, missing, not_dirs)
        """
        if self._validated:
            return self.watch_dirs, [], []

        resolved_valid: list[Path] = []
        missing: list[str] = []
        not_dirs: list[str] = []

        for d in self.watch_dirs:
            try:
                p = d.resolve()
            except OSError:
                p = d
            if not p.exists():
                missing.append(str(p))
                continue
            if not p.is_dir():
                not_dirs.append(str(p))
                continue
            resolved_valid.append(p)

        # Deduplicate and store only valid, normalized paths
        self.watch_dirs = sorted(set(resolved_valid))
        self._validated = True
        return self.watch_dirs, missing, not_dirs

    def emit_event(self) -> Event | None:
        """Check watched directories for file modifications.

        Returns:
            Event if a modified file is detected, None otherwise.
        """
        # Validate configuration on first tick without raising
        if not self._validated:
            valid_dirs, missing, not_dirs = self._validate_and_filter()

            # If there are invalid entries, emit a one-time warning event
            if (missing or not_dirs) and not self._warn_emitted:
                self._warn_emitted = True
                now = datetime.now(UTC)
                return Event(
                    timestamp=now,
                    label=self.spec.label,
                    event="watch_warning",
                    data={
                        "folders": [str(p) for p in valid_dirs],
                        "invalid": {
                            "missing": missing,
                            "not_dirs": not_dirs,
                        },
                        "message": (
                            "Some configured folders are invalid. Please fix your config."
                        ),
                        "extensions": sorted(self.extensions)
                        if self.extensions
                        else [],
                    },
                )

            # If there are valid entries, emit a one-time ack that lists them
            if valid_dirs and not self._ack_emitted:
                self._ack_emitted = True
                now = datetime.now(UTC)
                return Event(
                    timestamp=now,
                    label=self.spec.label,
                    event="watch_started",
                    data={
                        "folders": [str(p) for p in valid_dirs],
                        "extensions": sorted(self.extensions)
                        if self.extensions
                        else [],
                    },
                )

            # If none are valid and no invalid lists (i.e., nothing configured), warn once
            if not valid_dirs and not self._warn_emitted:
                self._warn_emitted = True
                now = datetime.now(UTC)
                return Event(
                    timestamp=now,
                    label=self.spec.label,
                    event="watch_warning",
                    data={
                        "folders": [],
                        "invalid": {"missing": [], "not_dirs": []},
                        "message": (
                            "No watch_dirs configured for FolderWatchMonitor. Set plugins.folderwatch.watch_dirs."
                        ),
                        "extensions": sorted(self.extensions)
                        if self.extensions
                        else [],
                    },
                )

        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue

            # Scan directory for matching files
            try:
                for root, _dirs, files in os.walk(watch_dir):
                    root_path = Path(root)
                    for filename in files:
                        file_path = root_path / filename

                        # Check extension (case-insensitive)
                        if (
                            self.extensions
                            and file_path.suffix.lower().lstrip(".")
                            not in self.extensions
                        ):
                            continue

                        # Check modification time
                        try:
                            mtime = file_path.stat().st_mtime
                        except OSError:
                            continue

                        last_mtime = self._last_mtimes.get(file_path)

                        if last_mtime is None:
                            # First time seeing this file
                            self._last_mtimes[file_path] = mtime

                            # Optionally emit on discovery
                            if self.emit_on_discovery:
                                now = datetime.now(UTC)
                                folder = str(file_path.parent.resolve())
                                return Event(
                                    timestamp=now,
                                    label=self.spec.label,
                                    event="file_mod",
                                    data={
                                        "folders": [folder],
                                        "file": str(file_path),
                                    },
                                )
                            continue

                        if mtime > last_mtime:
                            # File was modified
                            self._last_mtimes[file_path] = mtime

                            # Emit event with parent folder
                            now = datetime.now(UTC)
                            folder = str(file_path.parent.resolve())

                            return Event(
                                timestamp=now,
                                label=self.spec.label,
                                event="file_mod",
                                data={
                                    "folders": [folder],
                                    "file": str(file_path),
                                },
                            )

            except OSError:
                # Skip directories that can't be accessed
                continue

        return None

    @staticmethod
    def filter_method(items: list[list[str]]) -> list[str]:
        """Aggregate folder paths by flattening, normalizing, and deduplicating.

        Args:
            items: List of lists of folder paths collected during segment.

        Returns:
            Sorted list of unique normalized folder paths.
        """
        # Flatten nested lists
        flat_folders = [folder for sublist in items for folder in sublist]

        # Normalize paths and deduplicate
        normalized = {str(Path(folder).resolve()) for folder in flat_folders}

        # Return sorted
        return sorted(normalized)
```

## mimolo/user_plugins/__init__.py

``` py
"""MiMoLo user plugin modules."""

from mimolo.plugins.folderwatch import FolderWatchMonitor
from mimolo.user_plugins.example import ExampleMonitor

__all__ = [
    "ExampleMonitor",
    "FolderWatchMonitor",
]
```

## mimolo/user_plugins/agent_example.py

``` py
#!/usr/bin/env python3
"""Example Field-Agent demonstrating the v0.3 protocol.

This agent generates synthetic events with fake items and aggregates them internally.
When flushed, it returns a summary with item counts.

Three-thread architecture:
- Command Listener: reads flush/shutdown commands from stdin
- Worker Loop: generates fake items continuously
- Summarizer: packages accumulated data on flush
"""

from __future__ import annotations

import json
import sys
import threading
import time
from collections import Counter
from datetime import UTC, datetime
from queue import Empty, Queue
from random import randint
from typing import Any


class AgentExample:
    """Field-Agent that generates synthetic monitoring events."""

    def __init__(
        self,
        agent_id: str = "agent_example-001",
        agent_label: str = "agent_example",
        item_count: int = 5,
        sample_interval: float = 3.0,
        heartbeat_interval: float = 15.0,
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique runtime identifier
            agent_label: Logical plugin name
            item_count: Number of unique fake items to generate
            sample_interval: Seconds between generating fake items
            heartbeat_interval: Seconds between heartbeat emissions
        """
        self.agent_id = agent_id
        self.agent_label = agent_label
        self.item_count = item_count
        self.sample_interval = sample_interval
        self.heartbeat_interval = heartbeat_interval

        # Accumulator for current segment
        self.item_counts: Counter[str] = Counter()
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Command queue for flush/shutdown
        self.command_queue: Queue[dict[str, Any]] = Queue()

        # Flush queue for summarizer
        self.flush_queue: Queue[tuple[datetime, datetime, Counter[str]]] = Queue()

        # Control flags
        self.running = True
        self.shutdown_event = threading.Event()

    def send_message(self, msg: dict[str, Any]) -> None:
        """Write a JSON message to stdout.

        Args:
            msg: Message dictionary to serialize
        """
        try:
            print(json.dumps(msg), flush=True)
        except Exception as e:
            print(json.dumps({"type": "error", "message": f"Failed to send message: {e}"}), file=sys.stderr, flush=True)

    def command_listener(self) -> None:
        """Read commands from stdin (blocking thread)."""
        try:
            while not self.shutdown_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        break

                    line = line.strip()
                    if not line:
                        continue

                    cmd = json.loads(line)
                    self.command_queue.put(cmd)
                except json.JSONDecodeError as e:
                    self.send_message({
                        "type": "error",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": "0.3",
                        "agent_version": "1.0.0",
                        "data": {},
                        "message": f"Invalid JSON command: {e}",
                    })
                except EOFError:
                    break
        except Exception:
            # stdin closed or other error
            pass
        finally:
            # Trigger shutdown when stdin closes
            self.shutdown_event.set()
            self.running = False

    def worker_loop(self) -> None:
        """Generate fake items continuously and accumulate them."""
        last_heartbeat = time.time()

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)

            # Initialize segment start if needed
            with self.data_lock:
                if self.segment_start is None:
                    self.segment_start = now

                # Generate a fake item
                item = f"fake_item_{randint(1, self.item_count)}"
                self.item_counts[item] += 1

            # Send heartbeat if interval elapsed
            if time.time() - last_heartbeat >= self.heartbeat_interval:
                self.send_message({
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": "0.3",
                    "agent_version": "1.0.0",
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "items_accumulated": sum(self.item_counts.values()),
                    },
                })
                last_heartbeat = time.time()

            # Check for commands (non-blocking)
            try:
                cmd = self.command_queue.get_nowait()
                cmd_type = cmd.get("cmd", "").lower()

                if cmd_type == "flush":
                    # Take snapshot and reset accumulator
                    with self.data_lock:
                        snapshot_counts = self.item_counts.copy()
                        snapshot_start = self.segment_start or now
                        snapshot_end = now

                        # Reset for next segment
                        self.item_counts.clear()
                        self.segment_start = now

                    # Queue for summarizer
                    self.flush_queue.put((snapshot_start, snapshot_end, snapshot_counts))

                elif cmd_type == "shutdown":
                    self.running = False
                    self.shutdown_event.set()

            except Empty:
                pass

            # Sleep to avoid busy-wait
            time.sleep(self.sample_interval)

    def summarizer(self) -> None:
        """Package snapshots and emit summaries."""
        while self.running or not self.flush_queue.empty():
            try:
                # Wait for flush data (blocking with timeout)
                start, end, counts = self.flush_queue.get(timeout=1.0)

                # Calculate duration
                duration = (end - start).total_seconds()

                # Format data as list of {item, count}
                items_list: list[dict[str, Any]] = [
                    {"item": item, "count": count}
                    for item, count in sorted(counts.items())
                ]

                # Emit summary
                self.send_message({
                    "type": "summary",
                    "timestamp": end.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": "0.3",
                    "agent_version": "1.0.0",
                    "data": {
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "length": duration,
                        "items": items_list,
                        "total_events": sum(counts.values()),
                        "unique_items": len(counts),
                    },
                })

            except Empty:
                if not self.running:
                    break

    def run(self) -> None:
        """Main entry point - starts all threads and sends handshake."""
        # Send handshake
        self.send_message({
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": "0.3",
            "agent_version": "1.0.0",
            "min_app_version": "0.3.0",
            "capabilities": ["summary", "heartbeat", "status", "error"],
            "data": {},
        })

        # Start threads
        listener_thread = threading.Thread(target=self.command_listener, daemon=True)
        worker_thread = threading.Thread(target=self.worker_loop, daemon=False)
        summarizer_thread = threading.Thread(target=self.summarizer, daemon=False)

        listener_thread.start()
        worker_thread.start()
        summarizer_thread.start()

        # Wait for shutdown (with timeout to allow Ctrl+C)
        try:
            while worker_thread.is_alive():
                worker_thread.join(timeout=0.5)
            while summarizer_thread.is_alive():
                summarizer_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self.running = False
            self.shutdown_event.set()


def main() -> None:
    """Entry point."""
    agent = AgentExample(
        agent_id="agent_example-001",
        agent_label="agent_example",
        item_count=5,
        sample_interval=3.0,
        heartbeat_interval=15.0,
    )
    agent.run()


if __name__ == "__main__":
    main()
```

## mimolo/user_plugins/agent_template.py

``` py
#!/usr/bin/env python3
"""Field-Agent Template for MiMoLo v0.3+

This template demonstrates the complete 3-thread Field-Agent architecture.
Copy this file, rename it, and customize the worker logic for your use case.

Key sections to modify:
1. Agent metadata (agent_id, agent_label, version)
2. __init__ parameters for your specific monitoring needs
3. worker_loop() - your actual monitoring/sampling logic
4. _format_summary_data() - how you package accumulated data

The template includes rich console debugging to help you understand:
- Message flow (handshake, heartbeat, summary, errors)
- Command reception (flush, shutdown, status)
- Thread coordination and data flow
- Internal state and accumulation

To use:
1. Copy to a new file: cp agent_template.py my_agent.py
2. Update AGENT_LABEL and AGENT_ID
3. Implement your monitoring logic in worker_loop()
4. Configure in mimolo.toml:
   [plugins.my_agent]
   enabled = true
   plugin_type = "field_agent"
   executable = "python"
   args = ["my_agent.py"]
   heartbeat_interval_s = 15.0
   agent_flush_interval_s = 60.0

Architecture:
- Command Listener: Reads stdin for flush/shutdown/status commands
- Worker Loop: Samples/monitors continuously, accumulates data
- Summarizer: Packages snapshots and emits summaries on flush
"""

from __future__ import annotations

import json
import sys
import threading
import time

# Note: Counter imported for use in template examples (see _format_summary_data)
from collections import Counter  # noqa: F401
from datetime import UTC, datetime
from queue import Empty, Queue
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

# =============================================================================
# CUSTOMIZE THESE VALUES FOR YOUR AGENT
# =============================================================================

AGENT_LABEL = "template_agent"  # TODO: Change to your agent name
AGENT_ID = "template_agent-001"  # TODO: Change to unique ID
AGENT_VERSION = "1.0.0"  # TODO: Update as you develop
PROTOCOL_VERSION = "0.3"
MIN_APP_VERSION = "0.3.0"

# Debug output (set to False in production)
DEBUG_MODE = True  # Shows rich debugging output to stderr

# =============================================================================
# Field-Agent Implementation
# =============================================================================


class FieldAgentTemplate:
    """Template Field-Agent with full 3-thread architecture and debugging."""

    def __init__(
        self,
        agent_id: str = AGENT_ID,
        agent_label: str = AGENT_LABEL,
        sample_interval: float = 5.0,
        heartbeat_interval: float = 15.0,
        # TODO: Add your custom parameters here
        # example_param: str = "default_value",
    ) -> None:
        """Initialize the agent.

        Args:
            agent_id: Unique runtime identifier
            agent_label: Logical plugin name
            sample_interval: Seconds between samples in worker loop
            heartbeat_interval: Seconds between heartbeat emissions
            # TODO: Document your custom parameters
        """
        self.agent_id = agent_id
        self.agent_label = agent_label
        self.sample_interval = sample_interval
        self.heartbeat_interval = heartbeat_interval

        # TODO: Store your custom parameters
        # self.example_param = example_param

        # Accumulator for current segment
        self.data_accumulator: list[Any] = []  # TODO: Use appropriate data structure
        self.segment_start: datetime | None = None
        self.data_lock = threading.Lock()

        # Command queue for flush/shutdown/status
        self.command_queue: Queue[dict[str, Any]] = Queue()

        # Flush queue for summarizer
        self.flush_queue: Queue[tuple[datetime, datetime, list[Any]]] = Queue()

        # Control flags
        self.running = True
        self.shutdown_event = threading.Event()

        # Debug console (writes to stderr)
        self.debug = Console(stderr=True, force_terminal=True) if DEBUG_MODE else None

    def _debug_log(self, message: str, style: str = "cyan") -> None:
        """Log debug message to stderr if debugging enabled."""
        if self.debug:
            self.debug.print(f"[{style}][DEBUG {self.agent_label}][/{style}] {message}")

    def _debug_panel(self, content: Any, title: str, style: str = "blue") -> None:
        """Display debug panel to stderr if debugging enabled."""
        if self.debug:
            self.debug.print(Panel(content, title=f"[{style}]{title}[/{style}]", border_style=style))

    def send_message(self, msg: dict[str, Any]) -> None:
        """Write a JSON message to stdout.

        Args:
            msg: Message dictionary to serialize
        """
        try:
            json_str = json.dumps(msg)
            print(json_str, flush=True)

            # Debug output
            if self.debug:
                msg_type = msg.get("type", "unknown")
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                self._debug_panel(syntax, f"📤 Sent: {msg_type}", "green")

        except Exception as e:
            error_msg = {"type": "error", "message": f"Failed to send message: {e}"}
            print(json.dumps(error_msg), file=sys.stderr, flush=True)

    def command_listener(self) -> None:
        """Read commands from stdin (blocking thread)."""
        self._debug_log("🎧 Command listener thread started", "magenta")

        try:
            while not self.shutdown_event.is_set():
                try:
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        self._debug_log("📭 stdin closed (EOF)", "yellow")
                        break

                    line = line.strip()
                    if not line:
                        continue

                    cmd = json.loads(line)
                    cmd_type = cmd.get("cmd", "unknown")

                    # Debug: show received command
                    if self.debug:
                        syntax = Syntax(json.dumps(cmd, indent=2), "json", theme="monokai")
                        self._debug_panel(syntax, f"📥 Received command: {cmd_type}", "yellow")

                    self.command_queue.put(cmd)

                except json.JSONDecodeError as e:
                    self._debug_log(f"❌ Invalid JSON: {e}", "red")
                    self.send_message({
                        "type": "error",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "agent_id": self.agent_id,
                        "agent_label": self.agent_label,
                        "protocol_version": PROTOCOL_VERSION,
                        "agent_version": AGENT_VERSION,
                        "data": {},
                        "message": f"Invalid JSON command: {e}",
                    })
                except EOFError:
                    self._debug_log("📭 stdin EOF", "yellow")
                    break
        except Exception as e:
            self._debug_log(f"❌ Command listener error: {e}", "red")
        finally:
            self._debug_log("🛑 Command listener shutting down", "magenta")
            self.shutdown_event.set()
            self.running = False

    def worker_loop(self) -> None:
        """Main work loop: sample/monitor continuously and accumulate data."""
        self._debug_log("⚙️  Worker thread started", "blue")

        last_heartbeat = time.time()
        sample_count = 0

        while self.running and not self.shutdown_event.is_set():
            now = datetime.now(UTC)

            # Initialize segment start if needed
            with self.data_lock:
                if self.segment_start is None:
                    self.segment_start = now
                    self._debug_log(f"📅 Segment started at {now.isoformat()}", "cyan")

                # =============================================================
                # TODO: IMPLEMENT YOUR MONITORING LOGIC HERE
                # =============================================================
                # Example: Sample something and accumulate
                sample_count += 1
                sample_data: dict[str, Any] = {
                    "timestamp": now.isoformat(),
                    "sample_id": sample_count,
                    "value": f"sample_{sample_count}",
                    # TODO: Add your actual sampled data
                }
                self.data_accumulator.append(sample_data)

                self._debug_log(
                    f"📊 Sample #{sample_count} accumulated (total: {len(self.data_accumulator)})",
                    "cyan"
                )
                # =============================================================

            # Send heartbeat if interval elapsed
            if time.time() - last_heartbeat >= self.heartbeat_interval:
                with self.data_lock:
                    accumulated_count = len(self.data_accumulator)

                self.send_message({
                    "type": "heartbeat",
                    "timestamp": now.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "data": {},
                    "metrics": {
                        "queue": self.flush_queue.qsize(),
                        "accumulated_count": accumulated_count,
                        "sample_count": sample_count,
                    },
                })
                last_heartbeat = time.time()

            # Check for commands (non-blocking)
            try:
                cmd = self.command_queue.get_nowait()
                cmd_type = cmd.get("cmd", "").lower()

                if cmd_type == "flush":
                    self._debug_log("💾 FLUSH command received - taking snapshot", "yellow")

                    # Take snapshot and reset accumulator
                    with self.data_lock:
                        snapshot = self.data_accumulator.copy()
                        snapshot_start = self.segment_start or now
                        snapshot_end = now

                        # Reset for next segment
                        self.data_accumulator.clear()
                        self.segment_start = now

                    self._debug_log(
                        f"📸 Snapshot taken: {len(snapshot)} items from {snapshot_start.isoformat()} "
                        f"to {snapshot_end.isoformat()}",
                        "green"
                    )

                    # Queue for summarizer
                    self.flush_queue.put((snapshot_start, snapshot_end, snapshot))

                elif cmd_type == "shutdown":
                    self._debug_log("🛑 SHUTDOWN command received", "red")
                    self.running = False
                    self.shutdown_event.set()

                elif cmd_type == "status":
                    self._debug_log("📊 STATUS command received", "yellow")
                    # TODO: Send status message if needed

            except Empty:
                pass

            # Sleep to avoid busy-wait
            time.sleep(self.sample_interval)

        self._debug_log("🛑 Worker thread shutting down", "blue")

    def _format_summary_data(
        self,
        snapshot: list[Any],
        start: datetime,
        end: datetime
    ) -> dict[str, Any]:
        """Format accumulated data into summary payload.

        TODO: Customize this to aggregate/summarize your data appropriately.

        Args:
            snapshot: Copy of accumulated data from segment
            start: Segment start time
            end: Segment end time

        Returns:
            Dictionary to include in summary message data field
        """
        duration = (end - start).total_seconds()

        # =================================================================
        # TODO: IMPLEMENT YOUR SUMMARIZATION LOGIC HERE
        # =================================================================
        # Example: Just pass through the raw samples
        summary_data: dict[str, Any] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration_s": duration,
            "sample_count": len(snapshot),
            "samples": snapshot,  # TODO: Aggregate/summarize instead of raw dump
        }

        # Example: Count occurrences
        # if snapshot:
        #     counter = Counter(item["value"] for item in snapshot)
        #     summary_data["value_counts"] = dict(counter)

        return summary_data
        # =================================================================

    def summarizer(self) -> None:
        """Package snapshots and emit summaries."""
        self._debug_log("📦 Summarizer thread started", "green")

        while self.running or not self.flush_queue.empty():
            try:
                # Wait for flush data (blocking with timeout)
                start, end, snapshot = self.flush_queue.get(timeout=1.0)

                self._debug_log(
                    f"🔄 Summarizing {len(snapshot)} items...",
                    "yellow"
                )

                # Format summary data
                summary_data = self._format_summary_data(snapshot, start, end)

                # Emit summary
                self.send_message({
                    "type": "summary",
                    "timestamp": end.isoformat(),
                    "agent_id": self.agent_id,
                    "agent_label": self.agent_label,
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "data": summary_data,
                })

            except Empty:
                if not self.running:
                    break

        self._debug_log("🛑 Summarizer thread shutting down", "green")

    def run(self) -> None:
        """Main entry point - starts all threads and sends handshake."""
        if self.debug:
            self.debug.print(Panel.fit(
                f"[bold cyan]{self.agent_label}[/bold cyan]\n"
                f"ID: {self.agent_id}\n"
                f"Version: {AGENT_VERSION}\n"
                f"Protocol: {PROTOCOL_VERSION}\n"
                f"Sample Interval: {self.sample_interval}s\n"
                f"Heartbeat Interval: {self.heartbeat_interval}s",
                title="[bold green]🚀 Field-Agent Starting[/bold green]",
                border_style="green"
            ))

        # Send handshake
        self.send_message({
            "type": "handshake",
            "timestamp": datetime.now(UTC).isoformat(),
            "agent_id": self.agent_id,
            "agent_label": self.agent_label,
            "protocol_version": PROTOCOL_VERSION,
            "agent_version": AGENT_VERSION,
            "min_app_version": MIN_APP_VERSION,
            "capabilities": ["summary", "heartbeat", "status", "error"],
            "data": {},
        })

        # Start threads
        listener_thread = threading.Thread(target=self.command_listener, daemon=True, name="CommandListener")
        worker_thread = threading.Thread(target=self.worker_loop, daemon=False, name="Worker")
        summarizer_thread = threading.Thread(target=self.summarizer, daemon=False, name="Summarizer")

        listener_thread.start()
        worker_thread.start()
        summarizer_thread.start()

        self._debug_log("🎯 All threads started", "green")

        # Wait for shutdown (with timeout to allow Ctrl+C)
        try:
            while worker_thread.is_alive():
                worker_thread.join(timeout=0.5)
            while summarizer_thread.is_alive():
                summarizer_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self._debug_log("⚠️  KeyboardInterrupt - shutting down", "yellow")
            self.running = False
            self.shutdown_event.set()

        if self.debug:
            self.debug.print(Panel.fit(
                "[bold yellow]Agent stopped cleanly[/bold yellow]",
                border_style="yellow"
            ))


def main() -> None:
    """Entry point."""
    # TODO: Parse command-line arguments if needed
    # import argparse
    # parser = argparse.ArgumentParser()
    # parser.add_argument("--sample-interval", type=float, default=5.0)
    # args = parser.parse_args()

    agent = FieldAgentTemplate(
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        sample_interval=5.0,
        heartbeat_interval=15.0,
        # TODO: Pass your custom parameters
    )
    agent.run()


if __name__ == "__main__":
    main()
```

## mimolo/user_plugins/example.py

``` py
"""Example monitor plugin demonstrating the plugin API.

This plugin emits synthetic events for testing and demonstration purposes.

    For a full development guide, see:
    developer_docs/agent_dev/AGENT_DEV_GUIDE.md

    For the full Field-Agent protocol specification, see:

This example demonstrates:
- Basic event emission
- data_header usage
- Custom filter_method for aggregation
"""

from __future__ import annotations

from datetime import UTC, datetime
from random import randint

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class ExampleMonitor(BaseMonitor):
    """Example monitor that emits synthetic demo events.

    Demonstrates:
    - Basic event emission
    - data_header usage
    - Custom filter_method for aggregation
    """

    spec = PluginSpec(
        label="example",
        data_header="examples",
        resets_cooldown=True,
        infrequent=False,
        poll_interval_s=3.0,
    )

    def __init__(self, item_count: int = 5) -> None:
        """Initialize example monitor.

        Args:
            item_count: Number of unique items to generate.
        """
        self.item_count = item_count

    def emit_event(self) -> Event | None:
        """Emit a synthetic demo event.

        Returns:
            Event with random item from pool.
        """
        now = datetime.now(UTC)
        item = f"fake_item_{randint(1, self.item_count)}"
        payload = {"examples": [item]}

        return Event(
            timestamp=now,
            label=self.spec.label,
            event="demo",
            data=payload,
        )

    @staticmethod
    def filter_method(items: list[list[str]]) -> list[str]:
        """Aggregate example items by flattening and deduplicating.

        Args:
            items: List of lists of example items collected during segment.

        Returns:
            Sorted list of unique items.
        """
        # Flatten nested lists
        flat_items = [item for sublist in items for item in sublist]
        # Deduplicate and sort
        return sorted(set(flat_items))
```

## mimolo/user_plugins/template.py

``` py
"""Template for creating new MiMoLo plugins.

Copy this file, rename it, and fill in your monitoring logic.
See developer_docs/agent_dev/AGENT_DEV_GUIDE.md for detailed instructions.
"""

from __future__ import annotations

from typing import Any

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


class TemplateMonitor(BaseMonitor):
    """TODO: Brief description of what this plugin monitors."""

    spec = PluginSpec(
        label="template",              # TODO: Change to unique identifier
        data_header=None,              # TODO: Set to key name for aggregation, or leave None
        resets_cooldown=True,          # TODO: False if events shouldn't reset segment timer
        infrequent=False,              # TODO: True to bypass aggregation and write immediately
        poll_interval_s=5.0,           # TODO: Adjust polling frequency
    )

    def __init__(self) -> None:
        """Initialize the monitor.

        TODO: Add any parameters you need from config.
        Example: def __init__(self, paths: list[str]) -> None:
        """
        pass  # TODO: Initialize any state here

    def emit_event(self) -> Event | None:
        """Check for events and emit if detected.

        Returns:
            Event if something detected, None otherwise.
        """
        # TODO: Add your detection logic here
        # Example:
        # if self._something_changed():
        #     return Event(
        #         timestamp=datetime.now(UTC),
        #         label=self.spec.label,
        #         event="event_type",
        #         data={"items": ["detected_value"]} if self.spec.data_header else None,
        #     )

    @staticmethod
    def filter_method(items: list[Any]) -> list[Any]:
        """Aggregate collected data when segment closes.

        Only called if data_header is set in spec.
        Default implementation returns items unchanged.

        Args:
            items: List of values collected during segment.

        Returns:
            Aggregated result (must be JSON-serializable).
        """
        # TODO: Add custom aggregation logic
        # Examples:
        # - Deduplicate: return list(set(items))
        # - Sort: return sorted(items)
        # - Count: return {"count": len(items), "items": items}

        # Return a copy to avoid "unchanged" linting warnings
        return list(items)
```

## tests/__init__.py

``` py
"""Tests for MiMoLo framework."""
```

## tests/test_aggregate.py

``` py
"""Tests for segment aggregation."""

from datetime import UTC, datetime

import pytest

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.cooldown import SegmentState
from mimolo.core.errors import AggregationError
from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry


class TestMonitor(BaseMonitor):
    """Test monitor for aggregation tests."""

    spec = PluginSpec(label="test", data_header="items", resets_cooldown=True)

    def emit_event(self):
        return None

    @staticmethod
    def filter_method(items):
        """Deduplicate and sort."""
        return sorted(set(items))


def test_aggregator_initialization():
    """Test aggregator initialization."""
    registry = PluginRegistry()
    aggregator = SegmentAggregator(registry)

    assert aggregator.event_count == 0
    assert not aggregator.has_events


def test_aggregator_add_event():
    """Test adding events to aggregator."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"items": "item1"},
    )

    aggregator.add_event(event)

    assert aggregator.event_count == 1
    assert aggregator.has_events


def test_aggregator_build_segment():
    """Test building segment with aggregation."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    start = datetime.now(UTC)

    # Add events
    for _i, item in enumerate(["item1", "item2", "item1", "item3"]):
        event = Event(
            timestamp=start,
            label="test",
            event="test_event",
            data={"items": item},
        )
        aggregator.add_event(event)

    # Build segment
    segment_state = SegmentState(
        start_time=start,
        last_event_time=start,
        resets_count=3,
    )

    segment = aggregator.build_segment(segment_state)

    assert segment.start == start
    assert len(segment.events) == 4
    assert segment.aggregated["items"] == ["item1", "item2", "item3"]  # Deduplicated and sorted
    assert segment.resets_count == 3


def test_aggregator_clear():
    """Test clearing aggregator buffers."""
    registry = PluginRegistry()
    registry.add(TestMonitor.spec, TestMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(timestamp=now, label="test", event="test_event", data={"items": "item1"})
    aggregator.add_event(event)

    assert aggregator.has_events

    aggregator.clear()

    assert not aggregator.has_events
    assert aggregator.event_count == 0


def test_aggregator_filter_error():
    """Test aggregation error handling."""

    class BrokenMonitor(BaseMonitor):
        spec = PluginSpec(label="broken", data_header="items")

        def emit_event(self):
            return None

        @staticmethod
        def filter_method(items):
            raise ValueError("Filter failed!")

    registry = PluginRegistry()
    registry.add(BrokenMonitor.spec, BrokenMonitor())

    aggregator = SegmentAggregator(registry)
    now = datetime.now(UTC)

    event = Event(timestamp=now, label="broken", event="test", data={"items": "item1"})
    aggregator.add_event(event)

    segment_state = SegmentState(start_time=now, last_event_time=now, resets_count=0)

    with pytest.raises(AggregationError, match="Filter failed"):
        aggregator.build_segment(segment_state)
```

## tests/test_cooldown.py

``` py
"""Tests for cooldown timer."""

from datetime import UTC, datetime, timedelta

import pytest

from mimolo.core.cooldown import CooldownState, CooldownTimer


def test_cooldown_initialization():
    """Test cooldown timer initialization."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    assert timer.cooldown_seconds == 10.0
    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None


def test_cooldown_invalid_duration():
    """Test that invalid duration raises ValueError."""
    with pytest.raises(ValueError, match="must be positive"):
        CooldownTimer(cooldown_seconds=-1.0)

    with pytest.raises(ValueError, match="must be positive"):
        CooldownTimer(cooldown_seconds=0.0)


def test_cooldown_resetting_event_opens_segment():
    """Test that resetting event opens segment from IDLE."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    opened = timer.on_resetting_event(now)

    assert opened is True
    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.start_time == now
    assert timer.segment_state.last_event_time == now
    assert timer.segment_state.resets_count == 0


def test_cooldown_resetting_event_resets_timer():
    """Test that resetting event resets timer in ACTIVE state."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    later = now + timedelta(seconds=5)
    opened = timer.on_resetting_event(later)

    assert opened is False
    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.last_event_time == later
    assert timer.segment_state.resets_count == 1


def test_cooldown_non_resetting_event():
    """Test that non-resetting event updates timestamp but doesn't reset timer."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    # Open segment
    timer.on_resetting_event(start)

    # Non-resetting event
    later = start + timedelta(seconds=3)
    timer.on_non_resetting_event(later)

    assert timer.state == CooldownState.ACTIVE
    assert timer.segment_state is not None
    assert timer.segment_state.last_event_time == later
    assert timer.segment_state.resets_count == 0


def test_cooldown_expiration():
    """Test cooldown expiration detection."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    timer.on_resetting_event(start)

    # Check before expiration
    check_time = start + timedelta(seconds=5)
    expired = timer.check_expiration(check_time)
    assert expired is False
    assert timer.state == CooldownState.ACTIVE

    # Check after expiration
    check_time = start + timedelta(seconds=11)
    expired = timer.check_expiration(check_time)
    assert expired is True
    assert timer.state == CooldownState.CLOSING


def test_cooldown_close_segment():
    """Test segment closing."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    segment = timer.close_segment()

    assert segment is not None
    assert segment.start_time == now
    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None


def test_cooldown_close_segment_no_segment():
    """Test that closing without segment raises RuntimeError."""
    timer = CooldownTimer(cooldown_seconds=10.0)

    with pytest.raises(RuntimeError, match="no segment is open"):
        timer.close_segment()


def test_cooldown_time_until_expiration():
    """Test time until expiration calculation."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    start = datetime.now(UTC)

    # No segment
    assert timer.time_until_expiration(start) is None

    # Active segment
    timer.on_resetting_event(start)
    check_time = start + timedelta(seconds=3)
    remaining = timer.time_until_expiration(check_time)

    assert remaining is not None
    assert 6.9 < remaining < 7.1  # Should be ~7 seconds


def test_cooldown_reset():
    """Test timer reset."""
    timer = CooldownTimer(cooldown_seconds=10.0)
    now = datetime.now(UTC)

    timer.on_resetting_event(now)
    timer.reset()

    assert timer.state == CooldownState.IDLE
    assert timer.segment_state is None
```

## tests/test_event.py

``` py
"""Tests for event primitives."""

from datetime import UTC, datetime

import pytest

from mimolo.core.event import Event, EventRef, Segment


def test_event_creation():
    """Test basic event creation."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    )

    assert event.timestamp == now
    assert event.label == "test"
    assert event.event == "test_event"
    assert event.data == {"key": "value"}
    assert event.id is None


def test_event_with_id():
    """Test event ID computation."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    )

    event_with_id = event.with_id()
    assert event_with_id.id is not None
    assert len(event_with_id.id) == 16


def test_event_compute_id_deterministic():
    """Test that event ID computation is deterministic."""
    now = datetime.now(UTC)
    data = {"key": "value"}

    id1 = Event.compute_id(now, "test", "event", data)
    id2 = Event.compute_id(now, "test", "event", data)

    assert id1 == id2


def test_event_validation_empty_label():
    """Test that empty label raises ValueError."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="label cannot be empty"):
        Event(timestamp=now, label="", event="test")


def test_event_validation_empty_event():
    """Test that empty event type raises ValueError."""
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="Event type cannot be empty"):
        Event(timestamp=now, label="test", event="")


def test_event_validation_naive_timestamp():
    """Test that naive timestamp raises ValueError."""
    now = datetime.now()  # No timezone
    with pytest.raises(ValueError, match="must be timezone-aware"):
        Event(timestamp=now, label="test", event="test")


def test_event_to_dict():
    """Test event to dictionary conversion."""
    now = datetime.now(UTC)
    event = Event(
        timestamp=now,
        label="test",
        event="test_event",
        data={"key": "value"},
    ).with_id()

    d = event.to_dict()
    assert d["timestamp"] == now.isoformat()
    assert d["label"] == "test"
    assert d["event"] == "test_event"
    assert d["data"] == {"key": "value"}
    assert d["id"] is not None


def test_event_from_dict():
    """Test event from dictionary conversion."""
    now = datetime.now(UTC)
    d = {
        "timestamp": now.isoformat(),
        "label": "test",
        "event": "test_event",
        "data": {"key": "value"},
        "id": "abc123",
    }

    event = Event.from_dict(d)
    assert event.label == "test"
    assert event.event == "test_event"
    assert event.data == {"key": "value"}
    assert event.id == "abc123"


def test_event_ref_from_event():
    """Test EventRef creation from Event."""
    now = datetime.now(UTC)
    event = Event(timestamp=now, label="test", event="test_event")
    ref = EventRef.from_event(event)

    assert ref.timestamp == event.timestamp
    assert ref.label == event.label
    assert ref.event == event.event


def test_event_ref_to_dict():
    """Test EventRef to dictionary conversion."""
    now = datetime.now(UTC)
    ref = EventRef(timestamp=now, label="test", event="test_event")

    d = ref.to_dict()
    assert d["t"] == now.isoformat()
    assert d["l"] == "test"
    assert d["e"] == "test_event"


def test_segment_creation():
    """Test Segment creation."""
    start = datetime.now(UTC)
    end = start
    refs = [EventRef(timestamp=start, label="test", event="test_event")]

    segment = Segment(
        start=start,
        end=end,
        duration_s=0.0,
        events=refs,
        aggregated={"test_header": [1, 2, 3]},
        resets_count=5,
    )

    assert segment.start == start
    assert segment.end == end
    assert segment.duration_s == 0.0
    assert len(segment.events) == 1
    assert segment.aggregated == {"test_header": [1, 2, 3]}
    assert segment.resets_count == 5


def test_segment_to_dict():
    """Test Segment to dictionary conversion."""
    start = datetime.now(UTC)
    end = start
    refs = [EventRef(timestamp=start, label="test", event="test_event")]

    segment = Segment(
        start=start,
        end=end,
        duration_s=10.5,
        events=refs,
        aggregated={"test": [1, 2]},
        resets_count=3,
    )

    d = segment.to_dict()
    assert d["type"] == "segment"
    assert d["start"] == start.isoformat()
    assert d["end"] == end.isoformat()
    assert d["duration_s"] == 10.5
    assert d["labels"] == ["test"]
    assert d["aggregated"] == {"test": [1, 2]}
    assert d["resets_count"] == 3
    assert len(d["events"]) == 1
```

## tests/test_plugins_example.py

``` py
"""Tests for example plugin."""

from mimolo.plugins.example import ExampleMonitor


def test_example_monitor_spec():
    """Test ExampleMonitor spec."""
    spec = ExampleMonitor.spec

    assert spec.label == "example"
    assert spec.data_header == "examples"
    assert spec.resets_cooldown is True
    assert spec.infrequent is False
    assert spec.poll_interval_s == 3.0


def test_example_monitor_emit_event():
    """Test ExampleMonitor event emission."""
    monitor = ExampleMonitor(item_count=3)
    event = monitor.emit_event()

    assert event is not None
    assert event.label == "example"
    assert event.event == "demo"
    assert "examples" in event.data
    assert isinstance(event.data["examples"], list)
    assert len(event.data["examples"]) == 1


def test_example_monitor_filter_method():
    """Test ExampleMonitor filter method."""
    items = [
        ["item1", "item2"],
        ["item2", "item3"],
        ["item1", "item4"],
    ]

    result = ExampleMonitor.filter_method(items)

    assert isinstance(result, list)
    assert result == ["item1", "item2", "item3", "item4"]
    assert len(result) == 4  # Unique items
```

## tests/test_registry.py

``` py
"""Tests for plugin registry."""

import pytest

from mimolo.core.errors import PluginRegistrationError
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry


class TestMonitor(BaseMonitor):
    """Test monitor for registry tests."""

    spec = PluginSpec(label="test", data_header="test_data", resets_cooldown=True)

    def emit_event(self):
        return None


class AnotherMonitor(BaseMonitor):
    """Another test monitor."""

    spec = PluginSpec(label="another", resets_cooldown=False, infrequent=True)

    def emit_event(self):
        return None


def test_registry_initialization():
    """Test registry initialization."""
    registry = PluginRegistry()
    assert len(registry) == 0


def test_registry_add_plugin():
    """Test adding a plugin."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance = TestMonitor()

    registry.add(spec, instance)

    assert len(registry) == 1
    assert "test" in registry


def test_registry_duplicate_label():
    """Test that duplicate label raises error."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance1 = TestMonitor()
    instance2 = TestMonitor()

    registry.add(spec, instance1)

    with pytest.raises(PluginRegistrationError, match="already registered"):
        registry.add(spec, instance2)


def test_registry_get_plugin():
    """Test getting plugin by label."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance = TestMonitor()

    registry.add(spec, instance)
    result = registry.get("test")

    assert result is not None
    assert result[0] == spec
    assert result[1] == instance


def test_registry_get_nonexistent():
    """Test getting nonexistent plugin."""
    registry = PluginRegistry()
    result = registry.get("nonexistent")
    assert result is None


def test_registry_get_instance():
    """Test getting plugin instance."""
    registry = PluginRegistry()
    instance = TestMonitor()

    registry.add(TestMonitor.spec, instance)
    result = registry.get_instance("test")

    assert result == instance


def test_registry_get_spec():
    """Test getting plugin spec."""
    registry = PluginRegistry()
    instance = TestMonitor()

    registry.add(TestMonitor.spec, instance)
    result = registry.get_spec("test")

    assert result == TestMonitor.spec


def test_registry_list_all():
    """Test listing all plugins."""
    registry = PluginRegistry()
    instance1 = TestMonitor()
    instance2 = AnotherMonitor()

    registry.add(TestMonitor.spec, instance1)
    registry.add(AnotherMonitor.spec, instance2)

    all_plugins = registry.list_all()
    assert len(all_plugins) == 2


def test_registry_list_labels():
    """Test listing plugin labels."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    labels = registry.list_labels()
    assert "test" in labels
    assert "another" in labels
    assert len(labels) == 2


def test_registry_list_resetting():
    """Test listing resetting plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    resetting = registry.list_resetting()
    assert len(resetting) == 1
    assert resetting[0][0].label == "test"


def test_registry_list_infrequent():
    """Test listing infrequent plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    infrequent = registry.list_infrequent()
    assert len(infrequent) == 1
    assert infrequent[0][0].label == "another"


def test_registry_list_aggregating():
    """Test listing aggregating plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    aggregating = registry.list_aggregating()
    assert len(aggregating) == 1
    assert aggregating[0][0].label == "test"


def test_registry_remove():
    """Test removing a plugin."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    assert len(registry) == 1

    removed = registry.remove("test")
    assert removed is True
    assert len(registry) == 0


def test_registry_remove_nonexistent():
    """Test removing nonexistent plugin."""
    registry = PluginRegistry()
    removed = registry.remove("nonexistent")
    assert removed is False


def test_registry_clear():
    """Test clearing registry."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    assert len(registry) == 2
    registry.clear()
    assert len(registry) == 0


def test_registry_to_dict():
    """Test exporting registry metadata."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())

    metadata = registry.to_dict()
    assert "test" in metadata
    assert metadata["test"]["label"] == "test"
    assert metadata["test"]["data_header"] == "test_data"
    assert metadata["test"]["resets_cooldown"] is True
```

