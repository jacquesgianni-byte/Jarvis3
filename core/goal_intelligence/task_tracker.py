"""
Goal & Task Intelligence — Task Tracker
Genesis-033 Sprint-002

Stores and recalls WorkTasks using KnowledgeEngine.
Tasks live under Projects in the hierarchy.

Storage convention:
  subject:   "work_tasks"
  category:  "projects"
  attribute: "task_{id}"
  value:     task title
  tags:      ["work_task", "active"|"completed"|"paused",
               "task_{id}", "project_{project_id}", "goal_{goal_id}"]
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from core.goal_intelligence.models import WorkTask, WorkStatus

logger = logging.getLogger(__name__)

_SUBJECT  = "work_tasks"
_CATEGORY = "projects"
_TAG_TYPE = "work_task"


def _task_attribute(task_id: str) -> str:
    return f"task_{task_id}"


def _id_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower().strip()).strip("_")
    return slug[:40]


class TaskTracker:
    """
    Stores and retrieves WorkTasks via KnowledgeEngine.
    One responsibility: Task persistence and recall.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def set_active_task(
        self,
        title: str,
        project_id: str = "",
        goal_id: str = "",
    ) -> WorkTask:
        """
        Create or activate a task. Deactivates previous active task.
        Links to project_id and goal_id if provided.
        """
        task_id = _id_from_title(title)
        today   = date.today().isoformat()

        self._deactivate_all()

        tags = [_TAG_TYPE, WorkStatus.ACTIVE.value, f"task_{task_id}"]
        if project_id:
            tags.append(f"project_{project_id}")
        if goal_id:
            tags.append(f"goal_{goal_id}")

        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_task_attribute(task_id),
            value=title,
            tags=tags,
        )

        logger.info("[TASK] Active task set: %r (id=%s)", title, task_id)
        return WorkTask(
            id=task_id,
            title=title,
            project_id=project_id,
            goal_id=goal_id,
            status=WorkStatus.ACTIVE,
            created_at=today,
        )

    def complete_task(self, task_id: str) -> bool:
        return self._set_status(task_id, WorkStatus.COMPLETED)

    # ── Read ───────────────────────────────────────────────────────────────────

    def active_task(self) -> Optional[WorkTask]:
        for record in self._all_task_records():
            if WorkStatus.ACTIVE.value in record.tags:
                return self._record_to_task(record)
        return None

    def all_tasks(self) -> list[WorkTask]:
        return [self._record_to_task(r) for r in self._all_task_records()]

    def active_tasks(self) -> list[WorkTask]:
        return [t for t in self.all_tasks() if t.status == WorkStatus.ACTIVE]

    def tasks_for_project(self, project_id: str) -> list[WorkTask]:
        tag = f"project_{project_id}"
        return [t for t in self.all_tasks() if tag in self._tags_for(t.id)]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _all_task_records(self):
        return [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=200)
            if _TAG_TYPE in r.tags
        ]

    def _deactivate_all(self) -> None:
        for record in self._all_task_records():
            if WorkStatus.ACTIVE.value in record.tags:
                new_tags = [t for t in record.tags if t != WorkStatus.ACTIVE.value]
                new_tags.append(WorkStatus.COMPLETED.value)
                self._ke.store_memory(
                    subject=_SUBJECT,
                    category=_CATEGORY,
                    attribute=record.attribute,
                    value=record.value,
                    tags=new_tags,
                )

    def _set_status(self, task_id: str, status: WorkStatus) -> bool:
        attr   = _task_attribute(task_id)
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

    def _record_to_task(self, record) -> WorkTask:
        task_id    = record.attribute[len("task_"):] if record.attribute.startswith("task_") else record.attribute
        project_id = ""
        goal_id    = ""
        for tag in record.tags:
            if tag.startswith("project_"):
                project_id = tag[len("project_"):]
            elif tag.startswith("goal_"):
                goal_id = tag[len("goal_"):]
        status = self._status_from_tags(record.tags)
        return WorkTask(
            id=task_id,
            title=record.value,
            project_id=project_id,
            goal_id=goal_id,
            status=status,
            created_at=record.created_at.date().isoformat(),
        )

    def _tags_for(self, task_id: str) -> list[str]:
        record = self._ke.recall_memory(_SUBJECT, _task_attribute(task_id))
        return record.tags if record else []

    def _status_from_tags(self, tags: list[str]) -> WorkStatus:
        if WorkStatus.COMPLETED.value in tags:
            return WorkStatus.COMPLETED
        if WorkStatus.PAUSED.value in tags:
            return WorkStatus.PAUSED
        return WorkStatus.ACTIVE
