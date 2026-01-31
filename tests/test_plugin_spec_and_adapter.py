import pytest

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


def test_base_monitor_requires_spec() -> None:
    with pytest.raises(TypeError):
        class BadMonitor(BaseMonitor):
            def emit_event(self) -> Event | None:
                return None
