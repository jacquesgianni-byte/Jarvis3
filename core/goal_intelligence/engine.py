"""
Goal & Task Intelligence — Engine
Genesis-033 Sprint-002

GoalIntelligenceEngine is the single public entry point for Goal & Task Intelligence.
The agent imports and calls only this class.

Responsibilities:
  - Accept a user utterance
  - Delegate detection to WorkDetector
  - Delegate storage/recall to GoalTracker, ProjectTracker, TaskTracker
  - Return a plain-text response string

No AI calls. No new storage layer. Fully deterministic.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.goal_intelligence.detector import WorkDetector, DetectionKind
from core.goal_intelligence.goal_tracker import GoalTracker
from core.goal_intelligence.project_tracker import ProjectTracker
from core.goal_intelligence.task_tracker import TaskTracker
from core.goal_intelligence.models import WorkStatus_Summary

logger = logging.getLogger(__name__)


class GoalIntelligenceEngine:
    """
    Facade over WorkDetector + GoalTracker + ProjectTracker + TaskTracker.

    Public API (called by Agent):
        can_answer(utterance)   -> bool
        process(utterance)      -> str   (human-readable response)
    """

    def __init__(self, knowledge_engine) -> None:
        self._detector = WorkDetector()
        self._goals    = GoalTracker(knowledge_engine)
        self._projects = ProjectTracker(knowledge_engine)
        self._tasks    = TaskTracker(knowledge_engine)

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_answer(self, utterance: str) -> bool:
        """Return True if this utterance is a Goal/Project/Task statement."""
        return self._detector.detect(utterance) is not None

    def process(self, utterance: str) -> str:
        """
        Process a Goal/Project/Task utterance and return a response string.
        Returns empty string if nothing was detected (caller should check can_answer first).
        """
        detection = self._detector.detect(utterance)
        if detection is None:
            return ""

        kind  = detection.kind
        value = detection.value

        # ── Declarations ───────────────────────────────────────────────────────

        if kind == DetectionKind.GOAL_DECLARATION:
            goal = self._goals.set_active_goal(value)
            return f"Understood, sir. Active goal set: {goal.title}."

        if kind == DetectionKind.PROJECT_DECLARATION:
            active_goal = self._goals.active_goal()
            goal_id     = active_goal.id if active_goal else ""
            project     = self._projects.set_active_project(value, goal_id=goal_id)
            if active_goal:
                return (
                    f"Got it, sir. Active project: {project.title} "
                    f"(under goal: {active_goal.title})."
                )
            return f"Got it, sir. Active project: {project.title}."

        if kind == DetectionKind.TASK_DECLARATION:
            active_goal    = self._goals.active_goal()
            active_project = self._projects.active_project()
            goal_id        = active_goal.id    if active_goal    else ""
            project_id     = active_project.id if active_project else ""
            task = self._tasks.set_active_task(
                value, project_id=project_id, goal_id=goal_id
            )
            if active_project:
                return (
                    f"Noted, sir. Current task: {task.title} "
                    f"(on project: {active_project.title})."
                )
            return f"Noted, sir. Current task: {task.title}."

        # ── Recall queries ──────────────────────────────────────────────────────

        if kind == DetectionKind.STATUS_RECALL:
            return self._status_response()

        if kind == DetectionKind.GOAL_RECALL:
            return self._goal_recall_response()

        if kind == DetectionKind.PROJECT_RECALL:
            return self._project_recall_response()

        if kind == DetectionKind.TASK_RECALL:
            return self._task_recall_response()

        return ""

    # ── Response builders ──────────────────────────────────────────────────────

    def _status_response(self) -> str:
        summary = WorkStatus_Summary(
            active_goal=self._goals.active_goal(),
            active_project=self._projects.active_project(),
            active_task=self._tasks.active_task(),
        )
        return summary.to_text()

    def _goal_recall_response(self) -> str:
        goals = self._goals.all_goals()
        if not goals:
            return "You haven't set any goals yet, sir."
        active    = [g for g in goals if g.status == WorkStatus_Summary.__mro__[0] or True]
        # separate by status
        by_status: dict[str, list[str]] = {}
        for g in goals:
            by_status.setdefault(g.status.value, []).append(g.title)

        parts: list[str] = []
        if by_status.get("active"):
            parts.append("Active: " + ", ".join(by_status["active"]))
        if by_status.get("paused"):
            parts.append("Paused: " + ", ".join(by_status["paused"]))
        if by_status.get("completed"):
            parts.append("Completed: " + ", ".join(by_status["completed"]))

        return "Your goals — " + " | ".join(parts) + "."

    def _project_recall_response(self) -> str:
        project = self._projects.active_project()
        if project is None:
            return "You don't have an active project set, sir."
        goal = self._goals.active_goal()
        if goal:
            return f"Current project: {project.title} (goal: {goal.title})."
        return f"Current project: {project.title}."

    def _task_recall_response(self) -> str:
        task = self._tasks.active_task()
        if task is None:
            return "You don't have a current task set, sir."
        project = self._projects.active_project()
        if project:
            return f"Current task: {task.title} (project: {project.title})."
        return f"Current task: {task.title}."
