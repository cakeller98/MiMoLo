"""MiMoLo plugin modules."""

from mimolo.plugins.folderwatch import FolderWatchMonitor
from mimolo.user_plugins.example import ExampleMonitor

__all__ = [
    "ExampleMonitor",
    "FolderWatchMonitor",
]
