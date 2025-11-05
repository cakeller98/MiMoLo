"""Plugin contracts and metadata for MiMoLo framework.

Plugins are the core extension point for MiMoLo. Each plugin:
- Registers itself with a unique label
- Emits events when polled
- Optionally declares a data_header for aggregation
- Optionally provides a filter_method for aggregating collected data

Invariants:
- Plugin labels must be unique across all registered plugins
- If data_header is provided, events must include that key in their data dict
- filter_method receives a list of values collected during a segment
- Plugins must be time-bounded (emit_event should not block indefinitely)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from mimolo.core.event import Event


@dataclass(frozen=True, slots=True)
class PluginSpec:
    """Plugin registration specification.

    Attributes:
        label: Unique identifier for this plugin (e.g., "folderwatch").
        data_header: Optional key in event.data for aggregation (e.g., "folders").
        resets_cooldown: Whether events from this plugin reset the cooldown timer.
        infrequent: If True, bypass segment aggregation and flush immediately.
        poll_interval_s: How often to poll this plugin (seconds).
    """

    label: str
    data_header: str | None = None
    resets_cooldown: bool = True
    infrequent: bool = False
    poll_interval_s: float = 5.0

    def __post_init__(self) -> None:
        """Validate plugin spec fields."""
        if not self.label:
            raise ValueError("Plugin label cannot be empty")
        if not self.label.isidentifier():
            raise ValueError(f"Plugin label must be a valid identifier: {self.label}")
        if self.poll_interval_s <= 0:
            raise ValueError(f"poll_interval_s must be positive: {self.poll_interval_s}")


class BaseMonitor(ABC):
    """Abstract base class for monitor plugins.

    Subclasses must:
    1. Define a PluginSpec as a class attribute named 'spec'
    2. Implement emit_event() to return Event or None
    3. Optionally override filter_method() for data aggregation

    Example:
        class MyMonitor(BaseMonitor):
            spec = PluginSpec(
                label="mymonitor",
                data_header="items",
                resets_cooldown=True,
                poll_interval_s=3.0
            )

            def emit_event(self) -> Event | None:
                # Return event or None if nothing to report
                return Event(...)

            @staticmethod
            def filter_method(items: list[Any]) -> Any:
                # Aggregate collected items
                return list(set(items))
    """

    spec: PluginSpec

    @abstractmethod
    def emit_event(self) -> Event | None:
        """Emit an event or None if there is nothing to report.

        This method is called periodically based on spec.poll_interval_s.
        It should be non-blocking and time-bounded.

        Returns:
            Event instance if there is something to report, None otherwise.

        Raises:
            Exception: Any exception will be caught and wrapped in PluginEmitError.
        """
        ...

    @staticmethod
    def filter_method(items: list[Any]) -> Any:
        """Aggregate collected data for this plugin's data_header.

        Called when a segment closes to aggregate all collected values
        for this plugin's data_header.

        Default implementation returns the items list as-is.

        Args:
            items: List of values collected during the segment.

        Returns:
            Aggregated result (can be any JSON-serializable type).
        """
        return items

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate that subclasses define a spec attribute."""
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "spec"):
            raise TypeError(f"{cls.__name__} must define a 'spec' class attribute")
        if not isinstance(cls.spec, PluginSpec):
            raise TypeError(f"{cls.__name__}.spec must be a PluginSpec instance")
