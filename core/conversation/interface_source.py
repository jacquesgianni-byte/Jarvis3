"""
InterfaceSource — Genesis-047 Sprint-002

Enum identifying which interface submitted a request to Agent.process().

Wired call sites (Sprint-002):
    HTTP    — apps/server/routes.py (/chat and /upload fallback)

Reserved (defined but not yet wired — inject at real call sites only):
    DESKTOP — apps/desktop/ entry point (not yet calling Agent.process())
    VOICE   — no voice entry point exists yet
    ANDROID — Android connects via HTTP; reserved for future direct channel

UNKNOWN is the safe default when no source is injected.

Design notes:
    - Runtime code uses the strongly typed InterfaceSource enum.
    - Conversion to/from string occurs only at the persistence boundary
      (PersistedTimelineEvent stores the .value string).
    - Never infer ANDROID from HTTP — they are distinct channels.
"""
from __future__ import annotations

from enum import Enum


class InterfaceSource(Enum):
    """Identifies the interface that originated a request to Agent.process()."""

    ANDROID = "android"   # Reserved — future direct Android channel
    DESKTOP = "desktop"   # Reserved — Desktop app not yet wired
    HTTP    = "http"      # Wired — apps/server/routes.py
    VOICE   = "voice"     # Reserved — no voice entry point yet
    UNKNOWN = "unknown"   # Default — no source injected
