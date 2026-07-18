"""
Jarvis Timeline Event Model (Genesis-020 Sprint-003)

Defines the immutable event types that make up the Conversation Timeline.

Design constraints:
    - Frozen dataclasses only — events are never mutated after creation.
    - Every event carries a turn number and UTC timestamp.
    - Append-only: events are never deleted or edited.
    - Stable ordering: events are naturally ordered by turn, then timestamp.
    - Zero AI — all event creation is deterministic.

Polish pass additions (backwards compatible):
    - version:  schema version for future replay compatibility.
                Defaults to 1. Increment when payload schema changes.
    - payload:  structured dict of additional data. Defaults to empty.
                All existing fields remain the primary API; payload is
                supplementary and optional.
    - source field was already present — no change needed.

Backwards compatibility:
    All existing code constructing TimelineEvent(event_type, value, turn)
    continues to work unchanged. version and payload have defaults.

Event types:
    START_PROJECT   — "We're building Jarvis OS"
    START_SPRINT    — "We're starting Sprint-002"
    FINISH_SPRINT   — "Sprint-001 is complete"
    FREEZE          — "Genesis-019 is frozen"
    DECISION        — "We decided to use Flask"
    TASK            — "Claude is implementing Sprint-002"
    PERSON          — "Claude is my senior engineer"
    ACHIEVEMENT     — "We completed 529 tests"
    QUESTION        — user asked a question
    GENERAL         — any other noteworthy turn
    DECISION_*      — architectural decision lifecycle events (Genesis-020 S4)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    """The type of a timeline event."""
    START_PROJECT = auto()
    START_SPRINT  = auto()
    FINISH_SPRINT = auto()
    FREEZE        = auto()
    DECISION      = auto()
    TASK          = auto()
    PERSON        = auto()
    ACHIEVEMENT   = auto()
    QUESTION              = auto()
    GENERAL               = auto()
    DECISION_PROPOSED     = auto()   # Genesis-020 S4: decision under consideration
    DECISION_ACCEPTED     = auto()   # Genesis-020 S4: decision adopted
    DECISION_SUPERSEDED   = auto()   # Genesis-020 S4: decision replaced
    DECISION_REJECTED     = auto()   # Genesis-020 S4: decision rejected
    GOAL_CREATED          = auto()   # Genesis-020 S5: goal added to plan
    GOAL_STARTED          = auto()   # Genesis-020 S5: goal moved to active
    GOAL_COMPLETED        = auto()   # Genesis-020 S5: goal achieved
    GOAL_CANCELLED        = auto()   # Genesis-020 S5: goal abandoned
    GOAL_BLOCKED          = auto()   # Genesis-020 S5: goal cannot proceed
    GOAL_UNBLOCKED        = auto()   # Genesis-020 S5: blocker removed
    GOAL_PRIORITY_CHANGED = auto()   # Genesis-020 S5: priority updated


    def label(self) -> str:
        """Human-readable label for the inspector."""
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class TimelineEvent:
    """
    A single immutable event in the conversation timeline.

    Primary fields (original API — unchanged):
        event_type: The type of event that occurred.
        value:      The primary value ("Jarvis OS", "Sprint-001", etc.)
        turn:       Conversation turn number when this event occurred.
        timestamp:  UTC datetime when this event was recorded.
        source:     Producer of this event ("user", "auto", "system").
        raw:        The original user message that triggered this event.
        notes:      Optional human-readable context.

    Polish pass additions (all have defaults — backwards compatible):
        version:    Integer schema version. Increment when payload
                    schema changes to enable future migration.
                    Default: 1.
        payload:    Structured dict of supplementary data. Use for
                    machine-readable fields that don't belong in value.
                    Example: {"confidence": 0.85, "sprint_number": 2}
                    Default: empty dict (via field factory).

    Replay contract:
        Any Projection that reconstructs state from events should treat
        (event_type, value, turn, timestamp) as the canonical identity.
        payload provides enrichment; version signals schema compatibility.
    """
    event_type: EventType
    value:      str
    turn:       int
    timestamp:  datetime       = field(default_factory=lambda: datetime.now(UTC))
    source:     str            = "user"
    raw:        str            = ""
    notes:      str            = ""
    version:    int            = 1
    payload:    dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[Turn {self.turn}] {self.event_type.label()}: {self.value}"

    def date_str(self) -> str:
        """Return the event date as YYYY-MM-DD in UTC."""
        return self.timestamp.strftime("%Y-%m-%d")

    def time_str(self) -> str:
        """Return the event time as HH:MM in UTC."""
        return self.timestamp.strftime("%H:%M")

    def with_payload(self, **kwargs: Any) -> "TimelineEvent":
        """
        Return a new event with additional payload fields.

        Because TimelineEvent is frozen, this creates a new instance
        with the merged payload. Use during event construction when
        supplementary data is available.

        Example:
            event = TimelineEvent(...).with_payload(confidence=0.85)
        """
        merged = {**self.payload, **kwargs}
        return TimelineEvent(
            event_type=self.event_type,
            value=self.value,
            turn=self.turn,
            timestamp=self.timestamp,
            source=self.source,
            raw=self.raw,
            notes=self.notes,
            version=self.version,
            payload=merged,
        )