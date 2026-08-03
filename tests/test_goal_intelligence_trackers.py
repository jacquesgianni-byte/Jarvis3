"""
Tests — Goal, Project, and Task Trackers
Genesis-033 Sprint-002

Uses an in-memory KnowledgeEngine (InMemoryKnowledgeEngine) to isolate
tracker tests from disk I/O.
"""

import pytest
from core.goal_intelligence.goal_tracker import GoalTracker
from core.goal_intelligence.project_tracker import ProjectTracker
from core.goal_intelligence.task_tracker import TaskTracker
from core.goal_intelligence.models import WorkStatus


# ── Minimal in-memory KnowledgeEngine stub ────────────────────────────────────

class _MemoryStore:
    """Simple dict-backed store mimicking KnowledgeEngine's public API."""

    def __init__(self):
        self._records: dict[str, object] = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, UTC
        from uuid import uuid4

        class Rec:
            pass

        key = f"{subject}::{attribute}"
        r = Rec()
        r.id         = str(uuid4())
        r.subject    = subject
        r.category   = category
        r.attribute  = attribute
        r.value      = value
        r.tags       = list(tags or [])
        r.created_at = datetime.now(UTC)
        r.updated_at = datetime.now(UTC)
        r.expires_at = None
        self._records[key] = r
        return r

    def recall_memory(self, subject, attribute, category=None):
        return self._records.get(f"{subject}::{attribute}")

    def update_memory(self, subject, attribute, value, **kwargs):
        key = f"{subject}::{attribute}"
        if key in self._records:
            self._records[key].value = value
        return self._records.get(key)

    def list_memories(self, subject=None, category=None, limit=100, **kwargs):
        results = list(self._records.values())
        if subject:
            results = [r for r in results if r.subject == subject]
        if category:
            results = [r for r in results if r.category == category]
        return results[:limit]

    def search_memory(self, query, subject=None, **kwargs):
        return self.list_memories(subject=subject)


@pytest.fixture()
def ke():
    return _MemoryStore()


# ── GoalTracker ────────────────────────────────────────────────────────────────

class TestGoalTracker:
    def test_set_active_goal_returns_work_goal(self, ke):
        tracker = GoalTracker(ke)
        goal = tracker.set_active_goal("Release Jarvis 1.0")
        assert goal.title == "Release Jarvis 1.0"
        assert goal.status == WorkStatus.ACTIVE

    def test_active_goal_recalled(self, ke):
        tracker = GoalTracker(ke)
        tracker.set_active_goal("Release Jarvis 1.0")
        active = tracker.active_goal()
        assert active is not None
        assert active.title == "Release Jarvis 1.0"

    def test_set_active_deactivates_previous(self, ke):
        tracker = GoalTracker(ke)
        tracker.set_active_goal("Goal A")
        tracker.set_active_goal("Goal B")
        active = tracker.active_goal()
        assert active.title == "Goal B"

    def test_all_goals_includes_both(self, ke):
        tracker = GoalTracker(ke)
        tracker.set_active_goal("Goal A")
        tracker.set_active_goal("Goal B")
        all_g = tracker.all_goals()
        titles = [g.title for g in all_g]
        assert "Goal A" in titles
        assert "Goal B" in titles

    def test_active_goal_none_when_empty(self, ke):
        tracker = GoalTracker(ke)
        assert tracker.active_goal() is None

    def test_goal_id_derived_from_title(self, ke):
        tracker = GoalTracker(ke)
        goal = tracker.set_active_goal("Release Jarvis 1.0")
        assert "release" in goal.id or "jarvis" in goal.id

    def test_complete_goal(self, ke):
        tracker = GoalTracker(ke)
        goal = tracker.set_active_goal("Release Jarvis 1.0")
        result = tracker.complete_goal(goal.id)
        assert result is True


# ── ProjectTracker ─────────────────────────────────────────────────────────────

class TestProjectTracker:
    def test_set_active_project_returns_work_project(self, ke):
        tracker = ProjectTracker(ke)
        project = tracker.set_active_project("Genesis-033")
        assert project.title == "Genesis-033"
        assert project.status == WorkStatus.ACTIVE

    def test_active_project_recalled(self, ke):
        tracker = ProjectTracker(ke)
        tracker.set_active_project("Genesis-033")
        active = tracker.active_project()
        assert active is not None
        assert active.title == "Genesis-033"

    def test_project_links_to_goal(self, ke):
        tracker = ProjectTracker(ke)
        project = tracker.set_active_project("Genesis-033", goal_id="release_jarvis_1_0")
        assert project.goal_id == "release_jarvis_1_0"

    def test_set_active_deactivates_previous(self, ke):
        tracker = ProjectTracker(ke)
        tracker.set_active_project("Genesis-032")
        tracker.set_active_project("Genesis-033")
        active = tracker.active_project()
        assert active.title == "Genesis-033"

    def test_active_project_none_when_empty(self, ke):
        tracker = ProjectTracker(ke)
        assert tracker.active_project() is None

    def test_all_projects_populated(self, ke):
        tracker = ProjectTracker(ke)
        tracker.set_active_project("Genesis-032")
        tracker.set_active_project("Genesis-033")
        all_p = tracker.all_projects()
        titles = [p.title for p in all_p]
        assert "Genesis-033" in titles


# ── TaskTracker ────────────────────────────────────────────────────────────────

class TestTaskTracker:
    def test_set_active_task_returns_work_task(self, ke):
        tracker = TaskTracker(ke)
        task = tracker.set_active_task("Implement GoalEngine")
        assert task.title == "Implement GoalEngine"
        assert task.status == WorkStatus.ACTIVE

    def test_active_task_recalled(self, ke):
        tracker = TaskTracker(ke)
        tracker.set_active_task("Implement GoalEngine")
        active = tracker.active_task()
        assert active is not None
        assert active.title == "Implement GoalEngine"

    def test_task_links_to_project(self, ke):
        tracker = TaskTracker(ke)
        task = tracker.set_active_task("Write tests", project_id="genesis_033")
        assert task.project_id == "genesis_033"

    def test_task_links_to_goal(self, ke):
        tracker = TaskTracker(ke)
        task = tracker.set_active_task("Write tests", goal_id="jarvis_1_0")
        assert task.goal_id == "jarvis_1_0"

    def test_set_active_completes_previous(self, ke):
        tracker = TaskTracker(ke)
        tracker.set_active_task("Task A")
        tracker.set_active_task("Task B")
        active = tracker.active_task()
        assert active.title == "Task B"

    def test_active_task_none_when_empty(self, ke):
        tracker = TaskTracker(ke)
        assert tracker.active_task() is None

    def test_complete_task(self, ke):
        tracker = TaskTracker(ke)
        task = tracker.set_active_task("Implement GoalEngine")
        result = tracker.complete_task(task.id)
        assert result is True

    def test_all_tasks_populated(self, ke):
        tracker = TaskTracker(ke)
        tracker.set_active_task("Task A")
        tracker.set_active_task("Task B")
        all_t = tracker.all_tasks()
        titles = [t.title for t in all_t]
        assert "Task A" in titles
        assert "Task B" in titles
