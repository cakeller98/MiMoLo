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
