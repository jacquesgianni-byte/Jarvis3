"""
Jarvis Session Summary Engine (Genesis-020 Sprint-006)

Builds a deterministic SessionSummary by replaying Timeline events.
Implements Projection — no independent storage, fully replayable.

Architecture position:
    Timeline   → "What happened?"           (source of truth)
    Decisions  → "Why did we do that?"      (Sprint-004 Projection)
    Goals      → "What are we trying to do?" (Sprint-005 Projection)
    Summary    → "What happened this session?" (this Projection)

Design constraints:
    - No independent storage. Timeline is the source of truth.
    - Deterministic: same events → same summary, always.
    - No AI. No generated prose. Pure event counting and extraction.
    - Implements Projection: apply(event) + on_replay_complete().
    - Errors caught and logged — never crash the pipeline.

The Summary Engine accumulates state as events flow through apply().
current_summary() produces an immutable SessionSummary snapshot
from that accumulated state at any point in time.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

from core.conversation.projection import Projection
from core.conversation.session_summary import SessionSummary
from core.conversation.timeline_event import EventType, TimelineEvent

logger = logging.getLogger(__name__)

# Event types that count as "important" and appear in Key Events
_IMPORTANT_TYPES = {
    EventType.START_PROJECT,
    EventType.FINISH_SPRINT,
    EventType.FREEZE,
    EventType.DECISION_ACCEPTED,
    EventType.GOAL_COMPLETED,
    EventType.ACHIEVEMENT,
}


class SessionSummaryEngine(Projection):
    """
    Builds a deterministic session summary from Timeline events.

    Implements Projection so it rebuilds from Timeline.replay().
    Accumulates counters and lists as events are applied.
    Produces immutable SessionSummary snapshots on demand.

    Public API:
        current_summary()       — snapshot of current session state
        session_statistics()    — dict of key stats
        important_events()      — list of key event descriptions
        summary_lines()         — bullet-point summary strings
        conversation_length()   — turn count
        export_summary()        — formatted string for display
    """

    def __init__(self, session_id: Optional[str] = None) -> None:
        self._session_id = session_id or str(uuid.uuid4())
        self._reset()

    def _reset(self) -> None:
        """Reset all accumulated state."""
        self._started_at: Optional[datetime] = None
        self._ended_at:   Optional[datetime] = None
        self._turn_count:           int = 0
        self._goals_created:        int = 0
        self._goals_completed:      int = 0
        self._goals_blocked:        int = 0
        self._goals_cancelled:      int = 0
        self._decisions_made:       int = 0
        self._decisions_superseded: int = 0
        self._decisions_rejected:   int = 0
        self._memories_created:     int = 0
        self._projects:       list[str] = []
        self._milestones:     list[str] = []
        self._people:         list[str] = []
        self._important:      list[str] = []
        self._max_turn:             int = 0

    # ------------------------------------------------------------------
    # Projection interface
    # ------------------------------------------------------------------

    def apply(self, event: TimelineEvent) -> None:
        """Process a single Timeline event."""
        try:
            self._apply_event(event)
        except Exception:
            logger.exception("[SUMMARY] Error applying event: %s", event)

    def on_replay_complete(self) -> None:
        logger.info(
            "[SUMMARY] Replay complete — %d turns, %d goals, %d decisions.",
            self._turn_count, self._goals_created, self._decisions_made,
        )

    def _apply_event(self, event: TimelineEvent) -> None:
        """Accumulate state from a single event."""
        # Track session boundaries
        if self._started_at is None:
            self._started_at = event.timestamp
        self._ended_at = event.timestamp

        # Track max turn
        if event.turn > self._max_turn:
            self._max_turn = event.turn
            self._turn_count = event.turn

        et = event.event_type

        # Goals
        if et == EventType.GOAL_CREATED:
            self._goals_created += 1
        elif et == EventType.GOAL_COMPLETED:
            self._goals_completed += 1
        elif et == EventType.GOAL_BLOCKED:
            self._goals_blocked += 1
        elif et == EventType.GOAL_CANCELLED:
            self._goals_cancelled += 1

        # Decisions
        elif et in (EventType.DECISION, EventType.DECISION_ACCEPTED,
                    EventType.DECISION_PROPOSED):
            self._decisions_made += 1
        elif et == EventType.DECISION_SUPERSEDED:
            self._decisions_superseded += 1
        elif et == EventType.DECISION_REJECTED:
            self._decisions_rejected += 1

        # Memory / facts
        elif et in (EventType.TASK, EventType.ACHIEVEMENT):
            self._memories_created += 1

        # Named entities
        if et == EventType.START_PROJECT:
            if event.value and event.value not in self._projects:
                self._projects.append(event.value)

        if et in (EventType.FINISH_SPRINT, EventType.FREEZE):
            if event.value and event.value not in self._milestones:
                self._milestones.append(event.value)

        if et == EventType.PERSON:
            if event.value and event.value not in self._people:
                self._people.append(event.value)

        # Important events — key moments worth surfacing
        if et in _IMPORTANT_TYPES and event.value:
            description = f"{et.label()}: {event.value}"
            if description not in self._important:
                self._important.append(description)

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def current_summary(self) -> SessionSummary:
        """
        Produce an immutable snapshot of the current session state.

        Returns a SessionSummary frozen dataclass built from all
        events applied so far. Calling this twice produces identical
        results (deterministic).
        """
        now = datetime.now(UTC)
        started = self._started_at or now
        ended   = self._ended_at   or now

        return SessionSummary(
            session_id=self._session_id,
            started_at=started,
            ended_at=ended,
            turn_count=self._turn_count,
            goals_created=self._goals_created,
            goals_completed=self._goals_completed,
            goals_blocked=self._goals_blocked,
            goals_cancelled=self._goals_cancelled,
            decisions_made=self._decisions_made,
            decisions_superseded=self._decisions_superseded,
            decisions_rejected=self._decisions_rejected,
            memories_created=self._memories_created,
            projects_mentioned=tuple(self._projects),
            milestones_reached=tuple(self._milestones),
            people_mentioned=tuple(self._people),
            important_events=tuple(self._important),
            summary_lines=tuple(self.summary_lines()),
        )

    def session_statistics(self) -> dict:
        """Return key session statistics as a dict."""
        return {
            "session_id":    self._session_id,
            "turn_count":    self._turn_count,
            "goals_created": self._goals_created,
            "goals_completed": self._goals_completed,
            "goals_blocked": self._goals_blocked,
            "decisions_made": self._decisions_made,
            "decisions_superseded": self._decisions_superseded,
            "memories_created": self._memories_created,
            "projects":  list(self._projects),
            "milestones": list(self._milestones),
            "people":    list(self._people),
        }

    def important_events(self) -> list[str]:
        """Return key event descriptions in turn order."""
        return list(self._important)

    def summary_lines(self) -> list[str]:
        """
        Generate deterministic summary bullet points.
        No AI. Pure event-driven facts.
        """
        lines = []

        if self._turn_count:
            lines.append(f"{self._turn_count} conversation turns")

        if self._goals_created:
            lines.append(
                f"{self._goals_created} goal{'s' if self._goals_created != 1 else ''} created"
            )
        if self._goals_completed:
            lines.append(
                f"{self._goals_completed} goal{'s' if self._goals_completed != 1 else ''} completed"
            )
        if self._goals_blocked:
            lines.append(
                f"{self._goals_blocked} goal{'s' if self._goals_blocked != 1 else ''} blocked"
            )
        if self._decisions_made:
            lines.append(
                f"{self._decisions_made} architectural decision{'s' if self._decisions_made != 1 else ''} recorded"
            )
        if self._memories_created:
            lines.append(
                f"{self._memories_created} fact{'s' if self._memories_created != 1 else ''} added to memory"
            )
        if self._projects:
            lines.append(f"Projects: {', '.join(self._projects)}")
        if self._milestones:
            lines.append(f"Milestones: {', '.join(self._milestones)}")
        if self._people:
            lines.append(f"People: {', '.join(self._people)}")

        return lines

    def conversation_length(self) -> int:
        """Return the current turn count."""
        return self._turn_count

    def export_summary(self) -> str:
        """Return the full formatted summary string."""
        return self.current_summary().format()

    def is_empty(self) -> bool:
        """True if no events have been applied yet."""
        return self._started_at is None