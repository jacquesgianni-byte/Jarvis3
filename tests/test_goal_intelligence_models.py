"""
Tests — Goal Intelligence Models
Genesis-033 Sprint-002
"""

import pytest
from core.goal_intelligence.models import (
    WorkGoal, WorkProject, WorkTask, WorkStatus, WorkStatus_Summary,
)


class TestWorkStatus:
    def test_active_value(self):
        assert WorkStatus.ACTIVE.value == "active"

    def test_completed_value(self):
        assert WorkStatus.COMPLETED.value == "completed"

    def test_paused_value(self):
        assert WorkStatus.PAUSED.value == "paused"


class TestWorkGoal:
    def test_defaults(self):
        g = WorkGoal(id="g1", title="Release Jarvis 1.0")
        assert g.status == WorkStatus.ACTIVE
        assert g.projects == []
        assert g.created_at == ""

    def test_explicit_status(self):
        g = WorkGoal(id="g1", title="Test", status=WorkStatus.COMPLETED)
        assert g.status == WorkStatus.COMPLETED


class TestWorkProject:
    def test_defaults(self):
        p = WorkProject(id="p1", title="Genesis-033")
        assert p.goal_id == ""
        assert p.status == WorkStatus.ACTIVE
        assert p.tasks == []

    def test_goal_link(self):
        p = WorkProject(id="p1", title="Genesis-033", goal_id="jarvis_1_0")
        assert p.goal_id == "jarvis_1_0"


class TestWorkTask:
    def test_defaults(self):
        t = WorkTask(id="t1", title="Implement GoalEngine")
        assert t.project_id == ""
        assert t.goal_id == ""
        assert t.status == WorkStatus.ACTIVE

    def test_links(self):
        t = WorkTask(id="t1", title="Write tests", project_id="g033", goal_id="jarvis")
        assert t.project_id == "g033"
        assert t.goal_id == "jarvis"


class TestWorkStatusSummary:
    def test_empty_has_nothing(self):
        s = WorkStatus_Summary()
        assert s.has_anything() is False

    def test_with_goal_has_something(self):
        goal = WorkGoal(id="g1", title="Jarvis 1.0")
        s = WorkStatus_Summary(active_goal=goal)
        assert s.has_anything() is True

    def test_to_text_empty(self):
        s = WorkStatus_Summary()
        assert "haven't" in s.to_text()

    def test_to_text_goal_only(self):
        goal = WorkGoal(id="g1", title="Release Jarvis 1.0")
        s = WorkStatus_Summary(active_goal=goal)
        text = s.to_text()
        assert "Release Jarvis 1.0" in text

    def test_to_text_full_hierarchy(self):
        goal    = WorkGoal(id="g1", title="Jarvis 1.0")
        project = WorkProject(id="p1", title="Genesis-033")
        task    = WorkTask(id="t1", title="Implement GoalEngine")
        s = WorkStatus_Summary(active_goal=goal, active_project=project, active_task=task)
        text = s.to_text()
        assert "Jarvis 1.0"          in text
        assert "Genesis-033"          in text
        assert "Implement GoalEngine" in text
        assert "→"                    in text

    def test_to_text_uses_arrow_separator(self):
        goal    = WorkGoal(id="g1", title="A")
        project = WorkProject(id="p1", title="B")
        s = WorkStatus_Summary(active_goal=goal, active_project=project)
        assert "→" in s.to_text()
