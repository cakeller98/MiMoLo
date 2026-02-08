from __future__ import annotations

from pathlib import Path

import pytest

from mimolo.common.paths import get_mimolo_bin_dir, get_mimolo_data_dir


def test_data_dir_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    override = "/tmp/mimolo-portable-test/data"
    monkeypatch.setenv("MIMOLO_DATA_DIR", override)
    assert get_mimolo_data_dir() == Path(override)


def test_bin_dir_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    data_override = "/tmp/mimolo-portable-test/data"
    bin_override = "/tmp/mimolo-portable-test/bin"
    monkeypatch.setenv("MIMOLO_DATA_DIR", data_override)
    monkeypatch.setenv("MIMOLO_BIN_DIR", bin_override)
    assert get_mimolo_bin_dir() == Path(bin_override)


def test_bin_dir_defaults_under_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    data_override = "/tmp/mimolo-portable-test/data"
    monkeypatch.setenv("MIMOLO_DATA_DIR", data_override)
    monkeypatch.delenv("MIMOLO_BIN_DIR", raising=False)
    assert get_mimolo_bin_dir() == Path(data_override) / "bin"
