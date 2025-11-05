"""Error taxonomy for MiMoLo framework."""

from __future__ import annotations


class MiMoLoError(Exception):
    """Base exception for all MiMoLo errors."""

    pass


class ConfigError(MiMoLoError):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class PluginRegistrationError(MiMoLoError):
    """Raised when plugin registration fails (e.g., duplicate label)."""

    pass


class PluginEmitError(MiMoLoError):
    """Raised when a plugin fails to emit an event."""

    def __init__(self, plugin_label: str, original_error: Exception) -> None:
        """Initialize plugin emit error.

        Args:
            plugin_label: Label of the plugin that failed.
            original_error: The original exception that was raised.
        """
        self.plugin_label = plugin_label
        self.original_error = original_error
        super().__init__(f"Plugin '{plugin_label}' failed to emit event: {original_error}")


class SinkError(MiMoLoError):
    """Raised when a sink fails to write output."""

    pass


class AggregationError(MiMoLoError):
    """Raised when aggregation filter fails."""

    def __init__(self, plugin_label: str, data_header: str, original_error: Exception) -> None:
        """Initialize aggregation error.

        Args:
            plugin_label: Label of the plugin whose filter failed.
            data_header: The data header being aggregated.
            original_error: The original exception that was raised.
        """
        self.plugin_label = plugin_label
        self.data_header = data_header
        self.original_error = original_error
        super().__init__(
            f"Aggregation failed for plugin '{plugin_label}', "
            f"data_header '{data_header}': {original_error}"
        )
