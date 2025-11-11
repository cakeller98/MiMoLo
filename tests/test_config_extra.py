from pathlib import Path

import pytest

from mimolo.core.config import (
    Config,
    MonitorConfig,
    create_default_config,
    load_config,
    load_config_or_default,
)
from mimolo.core.errors import ConfigError


def test_load_config_or_default_missing_returns_default(tmp_path: Path) -> None:
    cfg = load_config_or_default(tmp_path / "does_not_exist.toml")
    assert isinstance(cfg, Config)


def test_create_default_config_toml_and_load(tmp_path: Path) -> None:
    path = tmp_path / "mimolo.toml"
    create_default_config(path)
    assert path.exists()
    cfg = load_config(path)
    # Basic sanity
    assert cfg.monitor.cooldown_seconds > 0


def test_create_default_config_yaml_and_load(tmp_path: Path) -> None:
    path = tmp_path / "mimolo.yaml"
    create_default_config(path)
    assert path.exists()
    cfg = load_config(path)
    assert cfg.monitor.poll_tick_ms > 0


def test_invalid_log_dir_parent_raises() -> None:
    # Parent does not exist -> validator should raise
    with pytest.raises(ValueError):
        MonitorConfig(log_dir="this_parent_does_not_exist/sub")


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.ini"
    path.write_text("[section]\nkey=value\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
