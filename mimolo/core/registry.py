"""Plugin registry for managing monitor lifecycle and metadata."""

from __future__ import annotations

from typing import Any

from mimolo.core.errors import PluginRegistrationError
from mimolo.core.plugin import BaseMonitor, PluginSpec


class PluginRegistry:
    """Registry for managing plugin lifecycle and metadata.

    Maintains:
    - Mapping from label to (spec, instance)
    - Duplicate label protection
    - Query methods for enabled/resetting/data_header plugins
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._plugins: dict[str, tuple[PluginSpec, BaseMonitor]] = {}

    def add(self, spec: PluginSpec, instance: BaseMonitor) -> None:
        """Register a plugin with the given spec and instance.

        Args:
            spec: Plugin specification.
            instance: Plugin instance (must be a BaseMonitor).

        Raises:
            PluginRegistrationError: If label is already registered or invalid.
        """
        if spec.label in self._plugins:
            raise PluginRegistrationError(f"Plugin label '{spec.label}' is already registered")

        if not isinstance(instance, BaseMonitor):
            raise PluginRegistrationError(
                f"Plugin instance must be a BaseMonitor, got {type(instance)}"
            )

        # Verify the instance's spec matches the provided spec
        if instance.spec != spec:
            raise PluginRegistrationError(
                f"Plugin instance spec does not match provided spec for '{spec.label}'"
            )

        self._plugins[spec.label] = (spec, instance)

    def get(self, label: str) -> tuple[PluginSpec, BaseMonitor] | None:
        """Get plugin spec and instance by label.

        Args:
            label: Plugin label.

        Returns:
            Tuple of (spec, instance) or None if not found.
        """
        return self._plugins.get(label)

    def get_instance(self, label: str) -> BaseMonitor | None:
        """Get plugin instance by label.

        Args:
            label: Plugin label.

        Returns:
            Plugin instance or None if not found.
        """
        entry = self._plugins.get(label)
        return entry[1] if entry else None

    def get_spec(self, label: str) -> PluginSpec | None:
        """Get plugin spec by label.

        Args:
            label: Plugin label.

        Returns:
            Plugin spec or None if not found.
        """
        entry = self._plugins.get(label)
        return entry[0] if entry else None

    def list_all(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List all registered plugins.

        Returns:
            List of (spec, instance) tuples.
        """
        return list(self._plugins.values())

    def list_labels(self) -> list[str]:
        """List all registered plugin labels.

        Returns:
            List of plugin labels.
        """
        return list(self._plugins.keys())

    def list_resetting(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins that reset the cooldown timer.

        Returns:
            List of (spec, instance) tuples for plugins with resets_cooldown=True.
        """
        return [(spec, instance) for spec, instance in self._plugins.values() if spec.resets_cooldown]

    def list_infrequent(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins marked as infrequent.

        Returns:
            List of (spec, instance) tuples for plugins with infrequent=True.
        """
        return [(spec, instance) for spec, instance in self._plugins.values() if spec.infrequent]

    def list_aggregating(self) -> list[tuple[PluginSpec, BaseMonitor]]:
        """List plugins that participate in segment aggregation.

        Returns:
            List of (spec, instance) tuples for plugins with data_header set
            and infrequent=False.
        """
        return [
            (spec, instance)
            for spec, instance in self._plugins.values()
            if spec.data_header is not None and not spec.infrequent
        ]

    def remove(self, label: str) -> bool:
        """Remove a plugin from the registry.

        Args:
            label: Plugin label to remove.

        Returns:
            True if plugin was removed, False if not found.
        """
        if label in self._plugins:
            del self._plugins[label]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()

    def __len__(self) -> int:
        """Return number of registered plugins."""
        return len(self._plugins)

    def __contains__(self, label: str) -> bool:
        """Check if a plugin label is registered."""
        return label in self._plugins

    def to_dict(self) -> dict[str, Any]:
        """Export registry metadata to dictionary.

        Returns:
            Dictionary mapping labels to spec dictionaries.
        """
        return {
            label: {
                "label": spec.label,
                "data_header": spec.data_header,
                "resets_cooldown": spec.resets_cooldown,
                "infrequent": spec.infrequent,
                "poll_interval_s": spec.poll_interval_s,
            }
            for label, (spec, _) in self._plugins.items()
        }
