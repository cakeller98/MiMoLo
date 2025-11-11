"""Compatibility shim for ExampleMonitor import path.

This module re-exports ExampleMonitor from mimolo.user_plugins.example so that
existing imports like `from mimolo.plugins.example import ExampleMonitor` work.
"""

from mimolo.user_plugins.example import ExampleMonitor

__all__ = ["ExampleMonitor"]
