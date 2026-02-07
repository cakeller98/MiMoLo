from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mimolo.core.event import Event, EventRef, Segment
from mimolo.core.sink import (
    ConsoleSink,
    JSONLSink,
    MarkdownSink,
    YAMLSink,
    create_sink,
)


def make_segment(now: datetime) -> Segment:
    e1 = Event(timestamp=now, label="a", event="e1").with_id()
    e2 = Event(timestamp=now + timedelta(seconds=1), label="b", event="e2").with_id()
    seg = Segment(
        start=e1.timestamp,
        end=e2.timestamp,
        duration_s=1.0,
        events=[EventRef.from_event(e1), EventRef.from_event(e2)],
        aggregated={"items": [1, 2]},
        resets_count=2,
    )
    return seg


def test_jsonl_sink_segment_and_event(tmp_path: Path) -> None:
    sink = JSONLSink(tmp_path)
    now = datetime.now(UTC)
    seg = make_segment(now)
    sink.write_segment(seg)
    evt = Event(timestamp=now, label="x", event="y", data={"k": "v"}).with_id()
    sink.write_event(evt)
    sink.flush()
    sink.close()
    files = list(tmp_path.glob("*.jsonl"))
    assert files, "jsonl file not created"
    content = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert any('"type":"segment"' in line for line in content)
    assert any('"type":"event"' in line for line in content)


def test_yaml_sink(tmp_path: Path) -> None:
    sink = YAMLSink(tmp_path)
    now = datetime.now(UTC)
    seg = make_segment(now)
    sink.write_segment(seg)
    evt = Event(timestamp=now, label="x", event="y").with_id()
    sink.write_event(evt)
    sink.close()
    files = list(tmp_path.glob("*.yaml"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert "segment" in text
    assert "event" in text


def test_markdown_sink(tmp_path: Path) -> None:
    sink = MarkdownSink(tmp_path)
    now = datetime.now(UTC)
    seg = make_segment(now)
    sink.write_segment(seg)
    evt = Event(timestamp=now, label="x", event="y").with_id()
    sink.write_event(evt)
    sink.flush()
    sink.close()
    files = list(tmp_path.glob("*.md"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert "Segments" in text
    assert "Standalone Events" in text


def test_console_sink(caplog: pytest.LogCaptureFixture) -> None:
    sink = ConsoleSink("debug")
    now = datetime.now(UTC)
    seg = make_segment(now)
    evt = Event(timestamp=now, label="x", event="y", data=None).with_id()

    with caplog.at_level("INFO"):
        sink.write_segment(seg)
        sink.write_event(evt)

    text = caplog.text
    assert "[SEGMENT]" in text
    assert "[EVENT]" in text

    caplog.clear()
    quiet_sink = ConsoleSink("warning")
    with caplog.at_level("INFO"):
        quiet_sink.write_segment(seg)
        quiet_sink.write_event(evt)
    assert "[SEGMENT]" not in caplog.text
    assert "[EVENT]" not in caplog.text


def test_create_sink_factory(tmp_path: Path) -> None:
    assert isinstance(create_sink("jsonl", tmp_path), JSONLSink)
    assert isinstance(create_sink("yaml", tmp_path), YAMLSink)
    assert isinstance(create_sink("md", tmp_path), MarkdownSink)
