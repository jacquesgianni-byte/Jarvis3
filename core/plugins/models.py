"""
Plugin models — Genesis-046 Sprint-002

PluginRecord: identity + load state for one plugin.
PluginStatus: two-value load lifecycle (LOADED / FAILED).
PluginMetadata: read from plugin.json (identity only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class PluginStatus(Enum):
    """Load-time state of a plugin. Runtime behaviour is tracked by WorkerManager."""
    LOADED = auto()   # imported, get_workers() succeeded, workers registered
    FAILED = auto()   # any error during load; workers NOT registered

    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class PluginMetadata:
    """
    Identity information read from plugins/<name>/plugin.json.

    All fields are optional in the file — defaults are used when absent.
    Jarvis Core never interprets the semantic meaning of these fields.
    """
    name:        str = "unknown"
    version:     str = "unknown"
    description: str = ""


@dataclass(frozen=True)
class PluginRecord:
    """
    Immutable record of a plugin load attempt.

    Created by PluginLoader after each load attempt (success or failure).
    Queryable at runtime via PluginLoader.loaded_plugins() / failed_plugins().
    """
    plugin_name:  str
    status:       PluginStatus
    metadata:     PluginMetadata          = field(default_factory=PluginMetadata)
    worker_names: tuple[str, ...]         = field(default_factory=tuple)
    error:        str                     = ""

    @property
    def loaded(self) -> bool:
        return self.status == PluginStatus.LOADED

    @property
    def failed(self) -> bool:
        return self.status == PluginStatus.FAILED

    def __str__(self) -> str:
        if self.loaded:
            return (
                f"PluginRecord({self.plugin_name!r} LOADED "
                f"v{self.metadata.version} workers={list(self.worker_names)})"
            )
        return f"PluginRecord({self.plugin_name!r} FAILED: {self.error})"
