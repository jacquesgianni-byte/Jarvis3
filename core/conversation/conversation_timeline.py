"""
Jarvis Conversation Timeline (Genesis-020 Sprint-003)

Append-only, in-memory record of significant conversation events.

Architecture position:
    Memory    → "What do I know?"    (persisted knowledge store)
    Context   → "What now?"          (SessionContext — session RAM)
    Timeline  → "How did we get here?" (ConversationTimeline — session RAM)

Design constraints:
    - Append-only: events are never deleted or mutated.
    - Immutable events: TimelineEvent is a frozen dataclass.
    - Stable ordering: events always sorted by (turn, timestamp).
    - Zero AI: all queries are deterministic.
    - Fully independent of SessionContext and Memory subsystems.
    - Errors are swallowed and logged — never crash the pipeline.

Integration:
    ConversationObserver calls timeline.record_from_facts(facts, turn)
    after extracting facts each turn. The Timeline is purely additive —
    it never reads from or writes to any persistence layer.

Future:
    Workers will read from the Timeline to understand conversation history
    without needing to re-parse raw messages.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Optional

from core.conversation.fact_extractor import ExtractedFact, FactType
from core.conversation.timeline_event import EventType, TimelineEvent
from core.conversation.projection import Projection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fact type → Event type mapping
# ---------------------------------------------------------------------------

_FACT_TO_EVENT: dict[FactType, EventType] = {
    FactType.PROJECT:     EventType.START_PROJECT,
    FactType.TASK:        EventType.START_SPRINT,
    FactType.DECISION:    EventType.DECISION,
    FactType.PERSON:      EventType.PERSON,
    FactType.ACHIEVEMENT: EventType.ACHIEVEMENT,
    FactType.PREFERENCE:  EventType.GENERAL,
    FactType.UNKNOWN:     EventType.GENERAL,
}

# Milestone sub-classification: frozen/freeze → FREEZE, else FINISH_SPRINT
_FREEZE_PATTERN = re.compile(r"\bfrozen?|freeze|locked|lock\b", re.IGNORECASE)
_SPRINT_PATTERN = re.compile(r"\bsprint[- ]?\d+\b", re.IGNORECASE)


def _milestone_event_type(value: str, raw: str) -> EventType:
    """Classify a milestone fact as FREEZE or FINISH_SPRINT."""
    if _FREEZE_PATTERN.search(raw) or _FREEZE_PATTERN.search(value):
        return EventType.FREEZE
    if _SPRINT_PATTERN.search(value):
        return EventType.FINISH_SPRINT
    return EventType.FREEZE


def _task_event_type(value: str) -> EventType:
    """Classify a task fact as START_SPRINT or TASK."""
    if _SPRINT_PATTERN.search(value):
        return EventType.START_SPRINT
    return EventType.TASK


class ConversationTimeline:
    """
    Append-only in-memory timeline of significant conversation events.

    Owned by the Agent alongside SessionContext. Independent of all
    other subsystems — it only knows about TimelineEvent.

    Public API:
        record(event)                    — append a single event
        record_from_facts(facts, turn)   — convert extracted facts to events
        record_turn(message, turn)       — record a raw turn as GENERAL
        query(...)                       — filter events by type/date/turn
        latest(event_type)               — most recent event of a given type
        events_on_date(date_str)         — all events on YYYY-MM-DD
        events_since_turn(turn)          — all events from turn onwards
        all_events()                     — full ordered list (copy)
        summary()                        — human-readable dict
    """

    def __init__(self) -> None:
        self._events: list[TimelineEvent] = []

    # ------------------------------------------------------------------
    # Write API — append only
    # ------------------------------------------------------------------

    def record(self, event: TimelineEvent) -> None:
        """
        Append a single event to the timeline.

        Events are stored in insertion order. Because turns are
        monotonically increasing and each turn appends in order,
        the list is naturally sorted.
        """
        try:
            self._events.append(event)
            logger.info("[TIMELINE] %s", event)
        except Exception:
            logger.exception("[TIMELINE] Failed to record event.")

    def record_from_facts(
        self,
        facts: list[ExtractedFact],
        turn: int,
    ) -> None:
        """
        Convert a list of ExtractedFacts into timeline events and record them.

        Called by ConversationObserver after fact extraction. Only facts
        with meaningful event types are recorded (GENERAL facts are skipped
        unless they carry a specific value).

        Args:
            facts: Extracted facts from the current turn.
            turn:  Current conversation turn number.
        """
        for fact in facts:
            try:
                event = self._fact_to_event(fact, turn)
                if event is not None:
                    self.record(event)
            except Exception:
                logger.exception("[TIMELINE] Error converting fact to event.")

    def record_turn(
        self,
        message: str,
        turn: int,
        event_type: EventType = EventType.GENERAL,
        notes: str = "",
    ) -> None:
        """
        Record a raw conversation turn as a timeline event.

        Used for turns that don't produce extracted facts but are
        still worth recording (e.g. questions, greetings, key replies).
        """
        if not message or not message.strip():
            return
        value = message.strip()
        if len(value) > 100:
            value = value[:97] + "..."
        event = TimelineEvent(
            event_type=event_type,
            value=value,
            turn=turn,
            source="user",
            raw=message,
            notes=notes,
        )
        self.record(event)

    # ------------------------------------------------------------------
    # Read API — deterministic queries
    # ------------------------------------------------------------------

    def all_events(self) -> list[TimelineEvent]:
        """Return a copy of all events in turn order."""
        return list(self._events)

    def query(
        self,
        event_type: Optional[EventType] = None,
        since_turn: Optional[int] = None,
        until_turn: Optional[int] = None,
        date_str: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[TimelineEvent]:
        """
        Filter timeline events by one or more criteria.

        All criteria are applied as AND filters. Returns a list in
        turn order (oldest first). Results are copies.

        Args:
            event_type:  Filter to only this event type.
            since_turn:  Only events at or after this turn.
            until_turn:  Only events at or before this turn.
            date_str:    Only events on this date (YYYY-MM-DD, UTC).
            limit:       Maximum number of results (most recent N).

        Returns:
            Filtered list of TimelineEvent objects.
        """
        results = list(self._events)

        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]

        if since_turn is not None:
            results = [e for e in results if e.turn >= since_turn]

        if until_turn is not None:
            results = [e for e in results if e.turn <= until_turn]

        if date_str is not None:
            results = [e for e in results if e.date_str() == date_str]

        if limit is not None:
            results = results[-limit:]

        return results

    def latest(self, event_type: Optional[EventType] = None) -> Optional[TimelineEvent]:
        """
        Return the most recent event, optionally filtered by type.

        Returns None if no matching event exists.
        """
        results = self.query(event_type=event_type)
        return results[-1] if results else None

    def events_on_date(self, date_str: str) -> list[TimelineEvent]:
        """Return all events on a given date (YYYY-MM-DD, UTC)."""
        return self.query(date_str=date_str)

    def events_since_turn(self, turn: int) -> list[TimelineEvent]:
        """Return all events from a given turn onwards."""
        return self.query(since_turn=turn)

    def events_of_type(self, event_type: EventType) -> list[TimelineEvent]:
        """Return all events of a given type, oldest first."""
        return self.query(event_type=event_type)

    def today_events(self) -> list[TimelineEvent]:
        """Return all events from today (UTC)."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return self.events_on_date(today)

    def yesterday_events(self) -> list[TimelineEvent]:
        """Return all events from yesterday (UTC)."""
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        return self.events_on_date(yesterday)

    def count(self, event_type: Optional[EventType] = None) -> int:
        """Return the number of events, optionally filtered by type."""
        return len(self.query(event_type=event_type))

    def summary(self) -> dict:
        """Return a human-readable summary dict for the Inspector."""
        by_type: dict[str, int] = {}
        for event in self._events:
            key = event.event_type.label()
            by_type[key] = by_type.get(key, 0) + 1

        latest_project = self.latest(EventType.START_PROJECT)
        latest_sprint  = self.latest(EventType.START_SPRINT)
        latest_freeze  = self.latest(EventType.FREEZE)

        return {
            "total_events": len(self._events),
            "by_type": by_type,
            "latest_project": latest_project.value if latest_project else None,
            "latest_sprint":  latest_sprint.value  if latest_sprint  else None,
            "latest_freeze":  latest_freeze.value   if latest_freeze   else None,
        }

    # ------------------------------------------------------------------
    # Replay API — event sourcing foundation
    # ------------------------------------------------------------------

    def replay(self, projection: Projection) -> None:
        """
        Replay all timeline events into a Projection in turn order.

        This is the event-sourcing contract: any read model that
        implements Projection can reconstruct its state by calling
        replay() on the Timeline.

        The Timeline is the source of truth. Projections are derived
        views. replay() is deterministic — the same event sequence
        always produces the same projection state.

        Args:
            projection: Any Projection implementation. Called with
                        every event in insertion (turn) order.

        Future (Genesis-021):
            Workers will call replay() to bootstrap their world view
            without needing parameter passing or shared mutable state.
        """
        try:
            for event in self._events:
                projection.apply(event)
            projection.on_replay_complete()
        except Exception:
            logger.exception("[TIMELINE] replay() error — projection may be incomplete.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fact_to_event(
        self, fact: ExtractedFact, turn: int
    ) -> Optional[TimelineEvent]:
        """Convert an ExtractedFact to a TimelineEvent, or None to skip."""
        if not fact.value or len(fact.value.strip()) < 2:
            return None

        if fact.fact_type == FactType.MILESTONE:
            event_type = _milestone_event_type(fact.value, fact.raw)
        elif fact.fact_type == FactType.TASK:
            event_type = _task_event_type(fact.value)
        else:
            event_type = _FACT_TO_EVENT.get(fact.fact_type, EventType.GENERAL)

        # Skip GENERAL events with very short or generic values
        if event_type == EventType.GENERAL and len(fact.value) < 4:
            return None

        # Skip duplicate person events at the same turn
        if event_type == EventType.PERSON:
            existing = self.query(
                event_type=EventType.PERSON,
                since_turn=turn,
                until_turn=turn,
            )
            if any(e.value.lower() == fact.value.lower() for e in existing):
                return None

        return TimelineEvent(
            event_type=event_type,
            value=fact.value,
            turn=turn,
            source="auto",
            raw=fact.raw,
        )