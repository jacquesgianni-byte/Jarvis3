"""
Goal & Task Intelligence — Data Models
Genesis-033 Sprint-002

Structured models for WorkGoal, WorkProject, and WorkTask.
These are the in-memory representations produced by the trackers.
Persistence is delegated to KnowledgeEngine — no separate storage layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WorkStatus(str, Enum):
    ACTIVE    = "active"
    COMPLETED = "completed"
    PAUSED    = "paused"


@dataclass
class WorkGoal:
    """A high-level persistent goal (e.g. 'Release Jarvis 1.0')."""
    id:          str
    title:       str
    status:      WorkStatus = WorkStatus.ACTIVE
    projects:    list[str]  = field(default_factory=list)   # project ids
    created_at:  str        = ""                             # ISO date string


@dataclass
class WorkProject:
    """
    A project under a goal (e.g. 'Genesis-033').
    Projects belong to a goal.
    """
    id:         str
    title:      str
    goal_id:    str         = ""
    status:     WorkStatus  = WorkStatus.ACTIVE
    tasks:      list[str]   = field(default_factory=list)   # task ids
    created_at: str         = ""


@dataclass
class WorkTask:
    """
    A concrete task under a project (e.g. 'Implement GoalEngine').
    Tasks belong to a project.
    """
    id:         str
    title:      str
    project_id: str         = ""
    goal_id:    str         = ""
    status:     WorkStatus  = WorkStatus.ACTIVE
    created_at: str         = ""


@dataclass
class WorkStatus_Summary:
    """Aggregated view of current work state — what am I working on?"""
    active_goal:    Optional[WorkGoal]    = None
    active_project: Optional[WorkProject] = None
    active_task:    Optional[WorkTask]    = None

    def has_anything(self) -> bool:
        return any([self.active_goal, self.active_project, self.active_task])

    def to_text(self) -> str:
        """Render a human-readable status summary."""
        if not self.has_anything():
            return "You haven't set any goals, projects, or tasks yet, sir."

        parts: list[str] = []
        if self.active_goal:
            parts.append(f"Goal: {self.active_goal.title}")
        if self.active_project:
            parts.append(f"Project: {self.active_project.title}")
        if self.active_task:
            parts.append(f"Task: {self.active_task.title}")

        return " → ".join(parts) + "."
