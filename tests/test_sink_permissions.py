from __future__ import annotations

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mimolo.core.event import Event
from mimolo.core.sink import JSONLSink, YAMLSink


@pytest.mark.skipif(os.name == "nt", reason="File mode checks are unreliable on Windows")
def test_jsonl_log_permissions(tmp_path: Path) -> None:
    log_dir = tmp_path
    sink = JSONLSink(log_dir)
    event = Event(timestamp=datetime.now(UTC), label="test", event="evt", data={})

    sink.write_event(event)
    sink.close()

    files = list(log_dir.iterdir())
    assert len(files) == 1

    mode = stat.S_IMODE(files[0].stat().st_mode)
    assert mode == 0o600


@pytest.mark.skipif(os.name == "nt", reason="File mode checks are unreliable on Windows")
def test_yaml_log_permissions(tmp_path: Path) -> None:
    log_dir = tmp_path
    sink = YAMLSink(log_dir)
    event = Event(timestamp=datetime.now(UTC), label="test", event="evt", data={})

    sink.write_event(event)
    sink.close()

    files = list(log_dir.iterdir())
    assert len(files) == 1

    mode = stat.S_IMODE(files[0].stat().st_mode)
    assert mode == 0o600
