from datetime import UTC, datetime
from typing import Any

import pytest
from mimolo.core.plugin_adapter import LegacyPluginAdapter

from mimolo.core.event import Event
from mimolo.core.plugin import BaseMonitor, PluginSpec


def test_plugin_spec_validation() -> None:
    # Valid
    PluginSpec(label="valid_label", poll_interval_s=1.0)

    # Empty label
    with pytest.raises(ValueError):
        PluginSpec(label="", poll_interval_s=1.0)

    # Invalid identifier
    with pytest.raises(ValueError):
        PluginSpec(label="not-valid", poll_interval_s=1.0)

    # Non-positive interval
    with pytest.raises(ValueError):
        PluginSpec(label="ok", poll_interval_s=0)


class DummyPlugin(BaseMonitor):
    spec = PluginSpec(label="dummy", data_header="items", poll_interval_s=0.1)

    def __init__(self, to_emit: Event | None) -> None:
        self._evt = to_emit

    def emit_event(self) -> Event | None:
        return self._evt

    @staticmethod
    def filter_method(items: list[Any]) -> Any:  # pragma: no cover
        return items


def test_legacy_plugin_adapter_summary_and_heartbeat() -> None:
    ts = datetime.now(UTC)
    evt = Event(timestamp=ts, label="dummy", event="tick", data={"x": 1})
    plug = DummyPlugin(to_emit=evt)

    adapter = LegacyPluginAdapter(plug, label="dummy")

    out_evt = adapter.emit_event()
    assert out_evt is evt

    msg = adapter.to_summary_message(evt)
    assert msg.agent_label == "dummy"
    assert msg.agent_version == "legacy"
    assert msg.data == {"x": 1}

    hb = adapter.generate_heartbeat()
    assert hb.agent_label == "dummy"
    assert hb.agent_version == "legacy"
    assert "synthetic" in hb.metrics
