"""Tests for plugin registry."""

import pytest

from mimolo.core.errors import PluginRegistrationError
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry


class TestMonitor(BaseMonitor):
    """Test monitor for registry tests."""

    spec = PluginSpec(label="test", data_header="test_data", resets_cooldown=True)

    def emit_event(self):
        return None


class AnotherMonitor(BaseMonitor):
    """Another test monitor."""

    spec = PluginSpec(label="another", resets_cooldown=False, infrequent=True)

    def emit_event(self):
        return None


def test_registry_initialization():
    """Test registry initialization."""
    registry = PluginRegistry()
    assert len(registry) == 0


def test_registry_add_plugin():
    """Test adding a plugin."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance = TestMonitor()

    registry.add(spec, instance)

    assert len(registry) == 1
    assert "test" in registry


def test_registry_duplicate_label():
    """Test that duplicate label raises error."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance1 = TestMonitor()
    instance2 = TestMonitor()

    registry.add(spec, instance1)

    with pytest.raises(PluginRegistrationError, match="already registered"):
        registry.add(spec, instance2)


def test_registry_get_plugin():
    """Test getting plugin by label."""
    registry = PluginRegistry()
    spec = TestMonitor.spec
    instance = TestMonitor()

    registry.add(spec, instance)
    result = registry.get("test")

    assert result is not None
    assert result[0] == spec
    assert result[1] == instance


def test_registry_get_nonexistent():
    """Test getting nonexistent plugin."""
    registry = PluginRegistry()
    result = registry.get("nonexistent")
    assert result is None


def test_registry_get_instance():
    """Test getting plugin instance."""
    registry = PluginRegistry()
    instance = TestMonitor()

    registry.add(TestMonitor.spec, instance)
    result = registry.get_instance("test")

    assert result == instance


def test_registry_get_spec():
    """Test getting plugin spec."""
    registry = PluginRegistry()
    instance = TestMonitor()

    registry.add(TestMonitor.spec, instance)
    result = registry.get_spec("test")

    assert result == TestMonitor.spec


def test_registry_list_all():
    """Test listing all plugins."""
    registry = PluginRegistry()
    instance1 = TestMonitor()
    instance2 = AnotherMonitor()

    registry.add(TestMonitor.spec, instance1)
    registry.add(AnotherMonitor.spec, instance2)

    all_plugins = registry.list_all()
    assert len(all_plugins) == 2


def test_registry_list_labels():
    """Test listing plugin labels."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    labels = registry.list_labels()
    assert "test" in labels
    assert "another" in labels
    assert len(labels) == 2


def test_registry_list_resetting():
    """Test listing resetting plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    resetting = registry.list_resetting()
    assert len(resetting) == 1
    assert resetting[0][0].label == "test"


def test_registry_list_infrequent():
    """Test listing infrequent plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    infrequent = registry.list_infrequent()
    assert len(infrequent) == 1
    assert infrequent[0][0].label == "another"


def test_registry_list_aggregating():
    """Test listing aggregating plugins."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    aggregating = registry.list_aggregating()
    assert len(aggregating) == 1
    assert aggregating[0][0].label == "test"


def test_registry_remove():
    """Test removing a plugin."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    assert len(registry) == 1

    removed = registry.remove("test")
    assert removed is True
    assert len(registry) == 0


def test_registry_remove_nonexistent():
    """Test removing nonexistent plugin."""
    registry = PluginRegistry()
    removed = registry.remove("nonexistent")
    assert removed is False


def test_registry_clear():
    """Test clearing registry."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())
    registry.add(AnotherMonitor.spec, AnotherMonitor())

    assert len(registry) == 2
    registry.clear()
    assert len(registry) == 0


def test_registry_to_dict():
    """Test exporting registry metadata."""
    registry = PluginRegistry()

    registry.add(TestMonitor.spec, TestMonitor())

    metadata = registry.to_dict()
    assert "test" in metadata
    assert metadata["test"]["label"] == "test"
    assert metadata["test"]["data_header"] == "test_data"
    assert metadata["test"]["resets_cooldown"] is True
