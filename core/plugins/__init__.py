"""
core/plugins
Plugin Ecosystem — Genesis-046

Public surface:
    PluginLoader   load and register plugin workers via enabled.json
    PluginError    base exception for plugin failures
"""

from core.plugins.loader import PluginLoader
from core.plugins.exceptions import PluginError, PluginLoadError, PluginConfigError

__all__ = ["PluginLoader", "PluginError", "PluginLoadError", "PluginConfigError"]
