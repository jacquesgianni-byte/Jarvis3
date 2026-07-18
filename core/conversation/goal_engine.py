"""
Jarvis Goal Engine (Genesis-020 Sprint-005)

Tracks active, completed, blocked, and cancelled goals.
Implements Projection — rebuilds entirely from Timeline replay.

Architecture position:
    Timeline  → "What happened?"       (source of truth)
    Decisions → "Why did we do that?"  (Sprint-004 Projection)
    Goals     → "What are we trying to accomplish?" (this Projection)

Design constraints:
    - No independent storage. Timeline is the source of truth.
    - Implements Projection: apply(event) + on_replay_complete().
    - Deterministic: same events → same state, always.
    - Immutable goals: status changes produce new instances.
    - Errors caught and logged — never crash the pipeline.

Integration:
    Agent creates one GoalEngine instance.
    Agent calls timeline.replay(goal_engine) on startup.
    Fact extractor publishes GOAL_* events to Timeline.
    GoalEngine.apply() processes those events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

from core.conversation.goal import Goal, GoalPriority, GoalStatus
from core.conversation.projection import Projection
from core.conversation.timeline_event import EventType, TimelineEvent

logger = logging.getLogger(__name__)

# Map EventType → GoalStatus for simple transitions
_EVENT_TO_STATUS: dict[EventType, GoalStatus] = {
    EventType.GOAL_STARTED:   GoalStatus.ACTIVE,
    EventType.GOAL_COMPLETED: GoalStatus.COMPLETED,
    EventType.GOAL_CANCELLED: GoalStatus.CANCELLED,
    EventType.GOAL_BLOCKED:   GoalStatus.BLOCKED,
    EventType.GOAL_UNBLOCKED: GoalStatus.ACTIVE,
}

_PRIORITY_MAP: dict[str, GoalPriority] = {
    "critical": GoalPriority.CRITICAL,
    "high":     GoalPriority.HIGH,
    "medium":   GoalPriority.MEDIUM,
    "low":      GoalPriority.LOW,
}


class GoalEngine(Projection):
    """
    Manages goals as a Projection over the Conversation Timeline.

    Public API:
        create(goal)               — add a new goal
        start(goal_id)             — mark ACTIVE
        complete(goal_id)          — mark COMPLETED
        cancel(goal_id, reason)    — mark CANCELLED
        block(goal_id, reason)     — mark BLOCKED
        unblock(goal_id)           — mark ACTIVE again
        update_priority(id, p)     — change priority
        get(goal_id)               — fetch by ID
        all_goals()                — all goals in turn order
        active()                   — ACTIVE goals
        planned()                  — PLANNED goals
        blocked()                  — BLOCKED goals
        completed()                — COMPLETED goals
        cancelled()                — CANCELLED goals
        open_goals()               — PLANNED + ACTIVE + BLOCKED
        search(query)              — full-text search
        latest(n)                  — most recent N goals
        by_priority(p)             — filter by priority
        on_date(date_str)          — goals created on date
        count(status)              — count with optional filter
        summary()                  — inspector-ready dict
    """

    def __init__(self) -> None:
        self._goals: dict[str, Goal] = {}
        self._order: list[str] = []

    # ------------------------------------------------------------------
    # Projection interface
    # ------------------------------------------------------------------

    def apply(self, event: TimelineEvent) -> None:
        """Process a single Timeline event."""
        try:
            self._apply_event(event)
        except Exception:
            logger.exception("[GOALS] Error applying event: %s", event)

    def on_replay_complete(self) -> None:
        logger.info(
            "[GOALS] Replay complete — %d goals loaded (%d active).",
            len(self._goals), len(self.active())
        )

    def _apply_event(self, event: TimelineEvent) -> None:
        """Map a GOAL_* timeline event to goal state."""
        et = event.event_type

        if et == EventType.GOAL_CREATED:
            goal = self._event_to_goal(event)
            if goal:
                self._store(goal)

        elif et in _EVENT_TO_STATUS:
            goal_id = event.payload.get("goal_id", "")
            if not goal_id or goal_id not in self._goals:
                return
            new_status = _EVENT_TO_STATUS[et]
            blocked_by = event.payload.get("blocked_by", "") if et == EventType.GOAL_BLOCKED else ""
            blocked_by_clear = "" if et == EventType.GOAL_UNBLOCKED else None
            updated = self._goals[goal_id].with_status(
                new_status,
                blocked_by=blocked_by if blocked_by_clear is None else "",
            )
            self._goals[goal_id] = updated

        elif et == EventType.GOAL_PRIORITY_CHANGED:
            goal_id = event.payload.get("goal_id", "")
            priority_str = event.payload.get("priority", "medium").lower()
            priority = _PRIORITY_MAP.get(priority_str, GoalPriority.MEDIUM)
            if goal_id in self._goals:
                self._goals[goal_id] = self._goals[goal_id].with_priority(priority)

    def _event_to_goal(self, event: TimelineEvent) -> Optional[Goal]:
        """Convert a GOAL_CREATED event to a Goal."""
        if not event.value or len(event.value.strip()) < 2:
            return None
        p = event.payload or {}
        priority_str = p.get("priority", "medium").lower()
        priority = _PRIORITY_MAP.get(priority_str, GoalPriority.MEDIUM)
        return Goal(
            id=p.get("goal_id", str(event.turn) + "_" + event.value[:8].replace(" ", "_")),
            title=p.get("title", event.value),
            description=p.get("description", event.notes or ""),
            status=GoalStatus.PLANNED,
            priority=priority,
            source_turn=event.turn,
            timestamp=event.timestamp,
            dependencies=tuple(p.get("dependencies", [])),
            parent_id=p.get("parent_id", ""),
            tags=tuple(p.get("tags", [])),
        )

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def create(self, goal: Goal) -> None:
        """Record a new goal."""
        try:
            self._store(goal)
            logger.info("[GOALS] Created: %s", goal.summary())
        except Exception:
            logger.exception("[GOALS] Failed to create goal.")

    def start(self, goal_id: str) -> None:
        """Mark a goal as ACTIVE."""
        self._transition(goal_id, GoalStatus.ACTIVE)

    def complete(self, goal_id: str) -> None:
        """Mark a goal as COMPLETED."""
        self._transition(goal_id, GoalStatus.COMPLETED, progress=100)

    def cancel(self, goal_id: str, reason: str = "") -> None:
        """Mark a goal as CANCELLED."""
        if goal_id not in self._goals:
            return
        updated = self._goals[goal_id].with_status(GoalStatus.CANCELLED)
        self._goals[goal_id] = updated
        logger.info("[GOALS] Cancelled: %s", self._goals[goal_id].title)

    def block(self, goal_id: str, reason: str = "") -> None:
        """Mark a goal as BLOCKED."""
        if goal_id not in self._goals:
            return
        updated = self._goals[goal_id].with_status(GoalStatus.BLOCKED, blocked_by=reason)
        self._goals[goal_id] = updated
        logger.info("[GOALS] Blocked: %s — %s", self._goals[goal_id].title, reason)

    def unblock(self, goal_id: str) -> None:
        """Remove block and mark ACTIVE."""
        if goal_id not in self._goals:
            return
        updated = self._goals[goal_id].with_status(GoalStatus.ACTIVE, blocked_by="")
        self._goals[goal_id] = updated
        logger.info("[GOALS] Unblocked: %s", self._goals[goal_id].title)

    def update_priority(self, goal_id: str, priority: GoalPriority) -> None:
        """Update a goal's priority."""
        if goal_id not in self._goals:
            return
        self._goals[goal_id] = self._goals[goal_id].with_priority(priority)
        logger.info("[GOALS] Priority updated: %s → %s",
                    self._goals[goal_id].title, priority.label())

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get(self, goal_id: str) -> Optional[Goal]:
        return self._goals.get(goal_id)

    def all_goals(self) -> list[Goal]:
        return [self._goals[id_] for id_ in self._order if id_ in self._goals]

    def active(self) -> list[Goal]:
        return [g for g in self.all_goals() if g.status == GoalStatus.ACTIVE]

    def planned(self) -> list[Goal]:
        return [g for g in self.all_goals() if g.status == GoalStatus.PLANNED]

    def blocked(self) -> list[Goal]:
        return [g for g in self.all_goals() if g.status == GoalStatus.BLOCKED]

    def completed(self) -> list[Goal]:
        return [g for g in self.all_goals() if g.status == GoalStatus.COMPLETED]

    def cancelled(self) -> list[Goal]:
        return [g for g in self.all_goals() if g.status == GoalStatus.CANCELLED]

    def open_goals(self) -> list[Goal]:
        """All goals not yet in a terminal state."""
        return [g for g in self.all_goals() if g.status.is_open]

    def by_priority(self, priority: GoalPriority) -> list[Goal]:
        return [g for g in self.all_goals() if g.priority == priority]

    def search(self, query: str) -> list[Goal]:
        """Full-text search across title, description, and tags."""
        q = query.lower().strip()
        results = []
        for g in self.all_goals():
            searchable = " ".join([
                g.title, g.description, " ".join(g.tags)
            ]).lower()
            if q in searchable:
                results.append(g)
        return results

    def latest(self, n: int = 5) -> list[Goal]:
        return self.all_goals()[-n:]

    def on_date(self, date_str: str) -> list[Goal]:
        return [g for g in self.all_goals() if g.date_str() == date_str]

    def today(self) -> list[Goal]:
        return self.on_date(datetime.now(UTC).strftime("%Y-%m-%d"))

    def count(self, status: Optional[GoalStatus] = None) -> int:
        if status is None:
            return len(self._goals)
        return len([g for g in self._goals.values() if g.status == status])

    def current_goal(self) -> Optional[Goal]:
        """Return the highest-priority active goal."""
        active = self.active()
        if not active:
            return None
        return sorted(active, key=lambda g: g.priority.value)[0]

    def next_goal(self) -> Optional[Goal]:
        """Return the highest-priority planned goal."""
        planned = self.planned()
        if not planned:
            return None
        return sorted(planned, key=lambda g: g.priority.value)[0]

    def summary(self) -> dict:
        active = self.active()
        return {
            "total":     len(self._goals),
            "active":    len(active),
            "planned":   self.count(GoalStatus.PLANNED),
            "blocked":   self.count(GoalStatus.BLOCKED),
            "completed": self.count(GoalStatus.COMPLETED),
            "cancelled": self.count(GoalStatus.CANCELLED),
            "current":   self.current_goal().title if self.current_goal() else None,
            "priorities": [g.title for g in
                           sorted(active, key=lambda g: g.priority.value)[:3]],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _store(self, goal: Goal) -> None:
        if goal.id not in self._goals:
            self._order.append(goal.id)
        self._goals[goal.id] = goal

    def _transition(
        self, goal_id: str, status: GoalStatus, progress: int = -1
    ) -> None:
        if goal_id not in self._goals:
            return
        updated = self._goals[goal_id].with_status(
            status, progress=progress
        )
        self._goals[goal_id] = updated
        logger.info("[GOALS] %s → %s", self._goals[goal_id].title, status.label())