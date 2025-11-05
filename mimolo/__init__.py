"""MiMoLo - Modular Monitor & Logger Framework.

A lightweight, plugin-based framework for ingesting events from monitors,
applying aggregation filters, and emitting work segments.
"""

__version__ = "0.2.0"

from mimolo.core import (
    BaseMonitor,
    Config,
    Event,
    PluginRegistry,
    PluginSpec,
    Runtime,
    Segment,
)

__all__ = [
    "__version__",
    "BaseMonitor",
    "Config",
    "Event",
    "PluginRegistry",
    "PluginSpec",
    "Runtime",
    "Segment",
]
