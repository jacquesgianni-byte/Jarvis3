"""
core/plugins
Plugin Ecosystem — Genesis-046

Public surface:
    PluginLoader    load and register plugin workers via enabled.json
    PluginRecord    immutable record of a plugin load attempt
    PluginStatus    LOADED / FAILED
    PluginMetadata  identity read from plugin.json
    PluginError     base exception
    PluginLoadError
    PluginConfigError
"""

from core.plugins.loader import PluginLoader
from core.plugins.models import PluginMetadata, PluginRecord, PluginStatus
from core.plugins.exceptions import PluginError, PluginLoadError, PluginConfigError

__all__ = [
    "PluginLoader",
    "PluginRecord",
    "PluginStatus",
    "PluginMetadata",
    "PluginError",
    "PluginLoadError",
    "PluginConfigError",
]
