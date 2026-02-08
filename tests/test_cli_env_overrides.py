from __future__ import annotations

import pytest

from mimolo.cli import _apply_monitor_env_overrides
from mimolo.core.config import Config


def test_apply_monitor_env_overrides_sets_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIMOLO_MONITOR_LOG_DIR", "/tmp/mimolo-test/logs")
    monkeypatch.setenv("MIMOLO_MONITOR_JOURNAL_DIR", "/tmp/mimolo-test/journals")
    monkeypatch.setenv("MIMOLO_MONITOR_CACHE_DIR", "/tmp/mimolo-test/cache")

    config = Config()
    _apply_monitor_env_overrides(config)

    assert config.monitor.log_dir == "/tmp/mimolo-test/logs"
    assert config.monitor.journal_dir == "/tmp/mimolo-test/journals"
    assert config.monitor.cache_dir == "/tmp/mimolo-test/cache"
