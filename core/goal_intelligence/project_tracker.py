"""
Goal & Task Intelligence — Project Tracker
Genesis-033 Sprint-002

Stores and recalls WorkProjects using KnowledgeEngine.
Projects live under Goals in the hierarchy.

Storage convention:
  subject:   "work_projects"
  category:  "projects"
  attribute: "project_{id}"
  value:     project title
  tags:      ["work_project", "active"|"completed"|"paused",
               "project_{id}", "goal_{goal_id}"]
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from core.goal_intelligence.models import WorkProject, WorkStatus

logger = logging.getLogger(__name__)

_SUBJECT  = "work_projects"
_CATEGORY = "projects"
_TAG_TYPE = "work_project"


def _project_attribute(project_id: str) -> str:
    return f"project_{project_id}"


def _id_from_title(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower().strip()).strip("_")
    return slug[:40]


class ProjectTracker:
    """
    Stores and retrieves WorkProjects via KnowledgeEngine.
    One responsibility: Project persistence and recall.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def set_active_project(self, title: str, goal_id: str = "") -> WorkProject:
        """
        Create or activate a project with the given title.
        Links to goal_id if provided. Deactivates previous active project.
        """
        project_id = _id_from_title(title)
        today      = date.today().isoformat()

        self._deactivate_all()

        tags = [_TAG_TYPE, WorkStatus.ACTIVE.value, f"project_{project_id}"]
        if goal_id:
            tags.append(f"goal_{goal_id}")

        self._ke.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=_project_attribute(project_id),
            value=title,
            tags=tags,
        )

        logger.info("[PROJECT] Active project set: %r (id=%s, goal=%s)", title, project_id, goal_id)
        return WorkProject(
            id=project_id,
            title=title,
            goal_id=goal_id,
            status=WorkStatus.ACTIVE,
            created_at=today,
        )

    def complete_project(self, project_id: str) -> bool:
        return self._set_status(project_id, WorkStatus.COMPLETED)

    # ── Read ───────────────────────────────────────────────────────────────────

    def active_project(self) -> Optional[WorkProject]:
        for record in self._all_project_records():
            if WorkStatus.ACTIVE.value in record.tags:
                return self._record_to_project(record)
        return None

    def all_projects(self) -> list[WorkProject]:
        return [self._record_to_project(r) for r in self._all_project_records()]

    def active_projects(self) -> list[WorkProject]:
        return [p for p in self.all_projects() if p.status == WorkStatus.ACTIVE]

    def projects_for_goal(self, goal_id: str) -> list[WorkProject]:
        tag = f"goal_{goal_id}"
        return [p for p in self.all_projects() if tag in self._tags_for(p.id)]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _all_project_records(self):
        return [
            r for r in self._ke.list_memories(subject=_SUBJECT, limit=200)
            if _TAG_TYPE in r.tags
        ]

    def _deactivate_all(self) -> None:
        for record in self._all_project_records():
            if WorkStatus.ACTIVE.value in record.tags:
                new_tags = [t for t in record.tags if t != WorkStatus.ACTIVE.value]
                new_tags.append(WorkStatus.PAUSED.value)
                self._ke.store_memory(
                    subject=_SUBJECT,
                    category=_CATEGORY,
                    attribute=record.attribute,
                    value=record.value,
                    tags=new_tags,
                )

    def _set_status(self, project_id: str, status: WorkStatus) -> bool:
        attr   = _project_attribute(project_id)
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

    def _record_to_project(self, record) -> WorkProject:
        project_id = record.attribute[len("project_"):] if record.attribute.startswith("project_") else record.attribute
        goal_id    = ""
        for tag in record.tags:
            if tag.startswith("goal_"):
                goal_id = tag[len("goal_"):]
                break
        status = self._status_from_tags(record.tags)
        return WorkProject(
            id=project_id,
            title=record.value,
            goal_id=goal_id,
            status=status,
            created_at=record.created_at.date().isoformat(),
        )

    def _tags_for(self, project_id: str) -> list[str]:
        record = self._ke.recall_memory(_SUBJECT, _project_attribute(project_id))
        return record.tags if record else []

    def _status_from_tags(self, tags: list[str]) -> WorkStatus:
        if WorkStatus.COMPLETED.value in tags:
            return WorkStatus.COMPLETED
        if WorkStatus.PAUSED.value in tags:
            return WorkStatus.PAUSED
        return WorkStatus.ACTIVE
