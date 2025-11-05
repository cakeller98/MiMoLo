"""Core MiMoLo framework modules."""

from mimolo.core.aggregate import SegmentAggregator
from mimolo.core.config import Config, MonitorConfig, PluginConfig, load_config
from mimolo.core.cooldown import CooldownState, CooldownTimer, SegmentState
from mimolo.core.errors import (
    AggregationError,
    ConfigError,
    MiMoLoError,
    PluginEmitError,
    PluginRegistrationError,
    SinkError,
)
from mimolo.core.event import Event, EventRef, Segment
from mimolo.core.plugin import BaseMonitor, PluginSpec
from mimolo.core.registry import PluginRegistry
from mimolo.core.runtime import Runtime
from mimolo.core.sink import BaseSink, ConsoleSink, JSONLSink, MarkdownSink, YAMLSink, create_sink

__all__ = [
    # Event primitives
    "Event",
    "EventRef",
    "Segment",
    # Errors
    "MiMoLoError",
    "ConfigError",
    "PluginRegistrationError",
    "PluginEmitError",
    "SinkError",
    "AggregationError",
    # Plugin system
    "BaseMonitor",
    "PluginSpec",
    "PluginRegistry",
    # Cooldown
    "CooldownTimer",
    "CooldownState",
    "SegmentState",
    # Aggregation
    "SegmentAggregator",
    # Config
    "Config",
    "MonitorConfig",
    "PluginConfig",
    "load_config",
    # Sinks
    "BaseSink",
    "JSONLSink",
    "YAMLSink",
    "MarkdownSink",
    "ConsoleSink",
    "create_sink",
    # Runtime
    "Runtime",
]
