"""
Goal & Task Intelligence — Goal Tracker
Genesis-033 Sprint-002

Stores and recalls WorkGoals using KnowledgeEngine as the persistence layer.
No separate storage. Goals are stored as MemoryRecords in the 'projects' category.

Storage convention:
  subject:   "work_goals"
  category:  "projects"
  attribute: "goal_{id}"
  value:     goal title
  tags:      ["work_goal", "active"|"completed"|"paused", "goal_{id}"]
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from core.goal_intelligence.models import WorkGoal, WorkStatus

logger = logging.getLogger(__name__)

_SUBJECT   = "work_goals"
_CATEGORY  = "projects"
_TAG_TYPE  = "work_goal"


def _goal_attribute(goal_id: str) -> str:
    return f"goal_{goal_id}"


def _id_from_title(title: str) -> str:
    """Produce a short stable id from a title."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower().strip()).strip("_")
    return slug[:40]


class GoalTracker:
    """
    Stores and retrieves WorkGoals via KnowledgeEngine.
    One responsibility: Goal persistence and recall.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def set_active_goal(self, title: str) -> WorkGoal:
        """
        Create or activate a goal with the given title.
        If a goal with this title already exists, activate it.
        Returns the WorkGoal.
        """
        goal_id = _id_from_title(title)
        today   = date.today().isoformat()

        # Deactivate all current active goals first
        self._deactivate_all()

        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_goal_attribute(goal_id),
            value=title,
            tags=[_TAG_TYPE, WorkStatus.ACTIVE.value, f"goal_{goal_id}"],
        )

        logger.info("[GOAL] Active goal set: %r (id=%s)", title, goal_id)
        return WorkGoal(id=goal_id, title=title, status=WorkStatus.ACTIVE, created_at=today)

    def complete_goal(self, goal_id: str) -> bool:
        """Mark a goal as completed."""
        return self._set_status(goal_id, WorkStatus.COMPLETED)

    def pause_goal(self, goal_id: str) -> bool:
        """Mark a goal as paused."""
        return self._set_status(goal_id, WorkStatus.PAUSED)

    # ── Read ───────────────────────────────────────────────────────────────────

    def active_goal(self) -> Optional[WorkGoal]:
        """Return the currently active goal, or None."""
        for record in self._all_goal_records():
            if WorkStatus.ACTIVE.value in record.tags:
                goal_id = self._extract_id(record)
                return WorkGoal(
                    id=goal_id,
                    title=record.value,
                    status=WorkStatus.ACTIVE,
                    created_at=record.created_at.date().isoformat(),
                )
        return None

    def all_goals(self) -> list[WorkGoal]:
        """Return all goals (any status)."""
        goals: list[WorkGoal] = []
        for record in self._all_goal_records():
            status = self._status_from_tags(record.tags)
            goal_id = self._extract_id(record)
            goals.append(WorkGoal(
                id=goal_id,
                title=record.value,
                status=status,
                created_at=record.created_at.date().isoformat(),
            ))
        return goals

    def active_goals(self) -> list[WorkGoal]:
        return [g for g in self.all_goals() if g.status == WorkStatus.ACTIVE]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _all_goal_records(self):
        return [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=200)
            if _TAG_TYPE in r.tags
        ]

    def _deactivate_all(self) -> None:
        """Remove 'active' tag from all currently active goals."""
        for record in self._all_goal_records():
            if WorkStatus.ACTIVE.value in record.tags:
                new_tags = [t for t in record.tags if t != WorkStatus.ACTIVE.value]
                new_tags.append(WorkStatus.PAUSED.value)
                self._ke.update_memory(
                    subject=_SUBJECT,
                    attribute=record.attribute,
                    value=record.value,
                )
                # Re-store with updated tags
                self._ke.store_memory(
                    subject=_SUBJECT,
                    category=_CATEGORY,
                    attribute=record.attribute,
                    value=record.value,
                    tags=new_tags,
                )

    def _set_status(self, goal_id: str, status: WorkStatus) -> bool:
        attr = _goal_attribute(goal_id)
        record = self._ke.recall_memory(_SUBJECT, attr)
        if record is None:
            return False
        new_tags = [t for t in record.tags
                    if t not in (WorkStatus.ACTIVE.value, WorkStatus.COMPLETED.value, WorkStatus.PAUSED.value)]
        new_tags.append(status.value)
        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=attr,
            value=record.value,
            tags=new_tags,
        )
        return True

    def _extract_id(self, record) -> str:
        """Extract goal_id from attribute name 'goal_{id}'."""
        attr = record.attribute
        if attr.startswith("goal_"):
            return attr[len("goal_"):]
        return attr

    def _status_from_tags(self, tags: list[str]) -> WorkStatus:
        if WorkStatus.COMPLETED.value in tags:
            return WorkStatus.COMPLETED
        if WorkStatus.PAUSED.value in tags:
            return WorkStatus.PAUSED
        return WorkStatus.ACTIVE
