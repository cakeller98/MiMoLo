"""Configuration management with validation.

Supports TOML and YAML configuration files with Pydantic validation.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

import tomlkit
import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator
from tomlkit.exceptions import TOMLKitError
from tomlkit.toml_document import TOMLDocument

from mimolo.core.errors import ConfigError


class MonitorConfig(BaseModel):
    """Monitor runtime configuration."""

    # NEW: Agent support
    journal_dir: str = "./journals"  # Event stream storage
    cache_dir: str = "./cache"  # Agent state cache
    main_system_max_cpu_per_plugin: float = 0.1  # CPU limit per agent
    agent_heartbeat_timeout_s: float = 30.0  # Miss threshold

    cooldown_seconds: float = Field(default=600.0, gt=0)
    poll_tick_s: float = Field(default=0.2, gt=0)
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


class ControlConfig(BaseModel):
    """Control-plane polling and IPC retry behavior."""

    status_poll_connected_s: float = Field(default=1.0, gt=0)
    status_poll_disconnected_s: float = Field(default=5.0, gt=0)
    instance_poll_connected_s: float = Field(default=1.0, gt=0)
    instance_poll_disconnected_s: float = Field(default=5.0, gt=0)
    log_poll_connected_s: float = Field(default=1.0, gt=0)
    log_poll_disconnected_s: float = Field(default=5.0, gt=0)
    ipc_connect_backoff_initial_s: float = Field(default=1.0, gt=0)
    ipc_connect_backoff_extended_s: float = Field(default=5.0, gt=0)
    ipc_connect_backoff_escalate_after: int = Field(default=5, ge=1)
    status_repeat_throttle_connected_s: float = Field(default=0.25, gt=0)
    status_repeat_throttle_disconnected_s: float = Field(default=3.0, gt=0)
    widget_auto_tick_s: float = Field(default=0.25, gt=0)
    widget_auto_refresh_default_s: float = Field(default=15.0, gt=0)
    ipc_request_timeout_s: float = Field(default=1.5, gt=0)
    template_cache_ttl_s: float = Field(default=3.0, gt=0)
    indicator_fade_step_s: float = Field(default=0.2, gt=0)
    toast_duration_s: float = Field(default=2.8, gt=0)
    stop_wait_disconnect_timeout_s: float = Field(default=5.0, gt=0)
    stop_wait_disconnect_poll_s: float = Field(default=0.15, gt=0)
    stop_wait_managed_exit_s: float = Field(default=1.0, gt=0)
    stop_wait_graceful_exit_s: float = Field(default=5.0, gt=0)
    stop_wait_forced_exit_s: float = Field(default=1.5, gt=0)


class PluginConfig(BaseModel):
    """Per-plugin configuration (Agent only)."""

    enabled: bool = Field(default=True)

    # Plugin-specific fields (stored as extra)
    model_config = {"extra": "allow"}

    # Agent specific
    plugin_type: Literal["agent"] = "agent"
    executable: str | None = None  # Python path or executable
    args: list[str] = Field(default_factory=list)  # CLI args for agent
    heartbeat_interval_s: float = Field(default=15.0)  # Expected heartbeat frequency
    agent_flush_interval_s: float = Field(default=60.0)  # How often to send flush command
    launch_in_separate_terminal: bool = Field(default=False)  # Launch in separate terminal window


class Config(BaseModel):
    """Root configuration model."""

    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
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
    except OSError as e:
        raise ConfigError(f"Failed to read configuration file {path}: {e}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Failed to parse TOML configuration {path}: {e}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML configuration {path}: {e}") from e

    try:
        return Config.model_validate(data)
    except ValidationError as e:
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
        content = _serialize_config(config, path)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except ConfigError:
        raise
    except OSError as e:
        raise ConfigError(f"Failed to write configuration file {path}: {e}") from e


def save_config(config: Config, path: Path | str) -> None:
    """Persist validated config to disk.

    Args:
        config: Config object to serialize.
        path: Destination config path (.toml/.yaml/.yml).

    Raises:
        ConfigError: If serialization or write fails.
    """
    path = Path(path)

    try:
        if path.suffix == ".toml":
            _save_toml_config_roundtrip(config, path)
            return

        content = _serialize_config(config, path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except ConfigError:
        raise
    except (OSError, TypeError, ValueError) as e:
        raise ConfigError(f"Failed to save configuration file {path}: {e}") from e


def _serialize_config(config: Config, path: Path) -> str:
    """Serialize config to text based on file extension."""
    if path.suffix == ".toml":
        return _config_to_toml(config)
    if path.suffix in (".yaml", ".yml"):
        return yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False)
    raise ConfigError(f"Unsupported config file extension: {path.suffix}")


def _config_to_toml(config: Config) -> str:
    """Convert Config to TOML string.

    Args:
        config: Config object to serialize.

    Returns:
        TOML-formatted string.
    """
    doc = tomlkit.document()
    _sync_toml_document_from_config(doc, config)
    return tomlkit.dumps(doc)


def _save_toml_config_roundtrip(config: Config, path: Path) -> None:
    """Save TOML config while preserving existing comments/format where possible."""
    try:
        with open(path, encoding="utf-8") as f:
            existing_text = f.read()
        doc = tomlkit.parse(existing_text)
    except FileNotFoundError:
        doc = tomlkit.document()
    except OSError as e:
        raise ConfigError(f"Failed to read existing TOML for save: {e}") from e
    except TOMLKitError as e:
        raise ConfigError(f"Failed to parse existing TOML for save: {e}") from e

    _sync_toml_document_from_config(doc, config)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))
    except OSError as e:
        raise ConfigError(f"Failed writing TOML config {path}: {e}") from e


def _sync_toml_document_from_config(doc: TOMLDocument, config: Config) -> None:
    """Mutate TOML document to match config model."""
    monitor_data = config.monitor.model_dump()
    control_data = config.control.model_dump()
    plugins_data = {
        label: plugin_cfg.model_dump() for label, plugin_cfg in config.plugins.items()
    }

    monitor_table = doc.get("monitor")
    if monitor_table is None or not isinstance(monitor_table, dict):
        monitor_table = tomlkit.table()
        doc["monitor"] = monitor_table
    _sync_mapping_table(
        monitor_table, monitor_data, remove_missing_keys=True  # Any: tomlkit dynamic mapping table.
    )

    control_table = doc.get("control")
    if control_table is None or not isinstance(control_table, dict):
        control_table = tomlkit.table()
        doc["control"] = control_table
    _sync_mapping_table(
        control_table, control_data, remove_missing_keys=True  # Any: tomlkit dynamic mapping table.
    )

    plugins_table = doc.get("plugins")
    if plugins_table is None or not isinstance(plugins_table, dict):
        plugins_table = tomlkit.table()
        doc["plugins"] = plugins_table

    existing_plugin_keys = {
        key for key in plugins_table.keys() if isinstance(key, str)
    }
    target_plugin_keys = set(plugins_data.keys())

    for plugin_key in existing_plugin_keys - target_plugin_keys:
        del plugins_table[plugin_key]

    for plugin_name, plugin_data in plugins_data.items():
        plugin_table = plugins_table.get(plugin_name)
        if plugin_table is None or not isinstance(plugin_table, dict):
            plugin_table = tomlkit.table()
            plugins_table[plugin_name] = plugin_table
        _sync_mapping_table(
            plugin_table, plugin_data, remove_missing_keys=True  # Any: tomlkit dynamic mapping table.
        )


def _sync_mapping_table(
    table: dict[str, Any], data: dict[str, Any], remove_missing_keys: bool
) -> None:
    """Sync key/value data into a TOML mapping table."""
    if remove_missing_keys:
        existing_keys = {key for key in table.keys() if isinstance(key, str)}
        for key in existing_keys - set(data.keys()):
            del table[key]

    for key, value in data.items():
        table[key] = tomlkit.item(value)
