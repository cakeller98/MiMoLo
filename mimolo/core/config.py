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

    # NEW: Agent support
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
