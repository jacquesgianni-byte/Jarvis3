"""
Plugin exceptions — Genesis-046

All plugin failures are non-fatal: Jarvis starts normally even if a plugin
fails to load.  These exceptions are caught and logged by PluginLoader.
"""


class PluginError(Exception):
    """Base class for all plugin errors."""


class PluginLoadError(PluginError):
    """Raised when a plugin module cannot be imported or instantiated."""


class PluginConfigError(PluginError):
    """Raised when enabled.json is missing, malformed, or references an unknown plugin."""
