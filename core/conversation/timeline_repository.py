"""
Timeline Repository — Genesis-047 Sprint-001

Persistence contract for ConversationTimeline events.

Two public components:
    PersistedTimelineEvent  — serialisable form of a timeline event
    TimelineRepository      — ABC that all storage implementations satisfy

Privacy guarantee (structural, not advisory):
    raw   hard-capped at 200 chars in __post_init__
    value hard-capped at 500 chars in __post_init__
    No full message text may ever be stored here.

Intentionally absent (deferred):
    load_sessions() — Sprint-004 will request this formally
    interface_source — Sprint-002
    time_of_day      — Sprint-003
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PersistedTimelineEvent:
    """
    Serialisable record of a single timeline event.

    Privacy hard caps enforced in __post_init__ — structural, not advisory.
    schema_version enables future migration without breaking readers.
    """
    event_id:       str
    session_id:     str
    event_type:     str    # EventType.label() — e.g. "Decision"
    value:          str
    turn:           int
    timestamp:      str    # ISO 8601 UTC — e.g. "2026-08-13T07:23:41Z"
    source:         str    # "auto" | "manual" | "system"
    raw:            str    = ""
    schema_version: int    = 1

    def __post_init__(self) -> None:
        # Hard privacy caps — structural enforcement.
        # object.__setattr__ required because the dataclass is frozen.
        object.__setattr__(self, "raw",   self.raw[:200])
        object.__setattr__(self, "value", self.value[:500])

    def to_dict(self) -> dict:
        """Serialise to a plain dict for JSON storage."""
        return {
            "event_id":       self.event_id,
            "session_id":     self.session_id,
            "event_type":     self.event_type,
            "value":          self.value,
            "turn":           self.turn,
            "timestamp":      self.timestamp,
            "source":         self.source,
            "raw":            self.raw,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PersistedTimelineEvent":
        """
        Deserialise from a plain dict.
        Missing fields default gracefully. Unknown extra keys are ignored.
        """
        return cls(
            event_id=       str(d.get("event_id",       str(uuid.uuid4()))),
            session_id=     str(d.get("session_id",     "")),
            event_type=     str(d.get("event_type",     "General")),
            value=          str(d.get("value",          "")),
            turn=           int(d.get("turn",           0)),
            timestamp=      str(d.get("timestamp",      "")),
            source=         str(d.get("source",         "auto")),
            raw=            str(d.get("raw",            "")),
            schema_version= int(d.get("schema_version", 1)),
        )


class TimelineRepository(ABC):
    """
    Persistence contract for timeline events.

    All implementations must satisfy:
        - save() is idempotent on event_id.
        - load_by_session() returns events sorted by (turn, timestamp).
        - All other load methods return events sorted by timestamp ascending.
        - purge_before() permanently deletes events older than cutoff_date.
        - Failure raises — ConversationTimeline is responsible for catching.

    load_sessions(since_date) is intentionally absent.
    Sprint-004 will request it formally when EI cross-session design is reviewed.
    """

    @abstractmethod
    def save(self, event: PersistedTimelineEvent) -> None:
        """Persist a single event. Idempotent on event_id. Raises on failure."""

    @abstractmethod
    def load_by_session(self, session_id: str) -> list[PersistedTimelineEvent]:
        """Return all events for a session, sorted by (turn, timestamp)."""

    @abstractmethod
    def load_by_date(self, date_str: str) -> list[PersistedTimelineEvent]:
        """Return all events for YYYY-MM-DD, sorted by timestamp ascending."""

    @abstractmethod
    def load_by_type(
        self, event_type: str, limit: int = 100,
    ) -> list[PersistedTimelineEvent]:
        """Return events matching event_type, newest first, up to limit."""

    @abstractmethod
    def load_recent(
        self, days: int = 7, limit: int = 500,
    ) -> list[PersistedTimelineEvent]:
        """Return events from the last `days` days, timestamp ascending."""

    @abstractmethod
    def purge_before(self, cutoff_date: str) -> int:
        """Delete all events with timestamp < cutoff_date. Returns count deleted."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of persisted events."""
