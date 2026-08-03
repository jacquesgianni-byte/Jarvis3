"""
Tests — Goal Intelligence Detector
Genesis-033 Sprint-002
"""

import pytest
from core.goal_intelligence.detector import WorkDetector, DetectionKind


class TestGoalDeclarations:
    def setup_method(self):
        self.d = WorkDetector()

    def test_my_goal_is_to(self):
        r = self.d.detect("My goal is to release Jarvis 1.0")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION
        assert "release Jarvis 1.0" in r.value.lower() or "Jarvis" in r.value

    def test_my_goal_is(self):
        r = self.d.detect("My goal is Jarvis 1.0")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION
        assert "Jarvis 1.0" in r.value

    def test_i_want_to(self):
        r = self.d.detect("I want to build a robot")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION
        assert "build a robot" in r.value.lower()

    def test_i_am_trying_to(self):
        r = self.d.detect("I'm trying to finish the project")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION

    def test_my_objective_is(self):
        r = self.d.detect("My objective is to ship Jarvis 1.0")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION

    def test_set_goal_to(self):
        r = self.d.detect("Set my goal to release Jarvis 1.0")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_DECLARATION


class TestProjectDeclarations:
    def setup_method(self):
        self.d = WorkDetector()

    def test_im_working_on(self):
        r = self.d.detect("I'm working on Genesis-033")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION
        assert "Genesis-033" in r.value

    def test_current_project_is(self):
        r = self.d.detect("Current project is Genesis-033")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION

    def test_my_project_is(self):
        r = self.d.detect("My project is the new dashboard")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION

    def test_i_have_started(self):
        r = self.d.detect("I've started Genesis-033")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION

    def test_active_project_is(self):
        r = self.d.detect("The active project is Genesis-033")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION


class TestTaskDeclarations:
    def setup_method(self):
        self.d = WorkDetector()

    def test_today_im_implementing(self):
        r = self.d.detect("Today I'm implementing GoalEngine")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION
        assert "GoalEngine" in r.value

    def test_im_implementing(self):
        r = self.d.detect("I'm implementing GoalEngine")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_im_writing(self):
        r = self.d.detect("I'm writing the tests")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_my_task_is(self):
        r = self.d.detect("My task is to write tests")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_im_fixing(self):
        r = self.d.detect("I'm fixing the memory bug")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_im_working_on_implementing(self):
        r = self.d.detect("I'm working on implementing GoalEngine")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION


class TestRecallQueries:
    def setup_method(self):
        self.d = WorkDetector()

    def test_what_are_my_goals(self):
        r = self.d.detect("What are my goals?")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_RECALL
        assert r.value == ""

    def test_what_is_my_goal(self):
        r = self.d.detect("What is my goal?")
        assert r is not None
        assert r.kind == DetectionKind.GOAL_RECALL

    def test_what_am_i_working_on(self):
        r = self.d.detect("What am I working on?")
        assert r is not None
        assert r.kind == DetectionKind.STATUS_RECALL

    def test_what_am_i_doing(self):
        r = self.d.detect("What am I doing?")
        assert r is not None
        assert r.kind == DetectionKind.STATUS_RECALL

    def test_current_project(self):
        r = self.d.detect("Current project")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_RECALL

    def test_what_is_my_current_task(self):
        r = self.d.detect("What is my current task?")
        assert r is not None
        assert r.kind == DetectionKind.TASK_RECALL

    def test_my_current_task(self):
        r = self.d.detect("My current task")
        assert r is not None
        assert r.kind == DetectionKind.TASK_RECALL

    def test_status_update(self):
        r = self.d.detect("Status update")
        assert r is not None
        assert r.kind == DetectionKind.STATUS_RECALL


class TestNoDetection:
    def setup_method(self):
        self.d = WorkDetector()

    def test_unrelated_query(self):
        assert self.d.detect("What is the weather today?") is None

    def test_greeting(self):
        assert self.d.detect("Hello Jarvis") is None

    def test_memory_statement(self):
        assert self.d.detect("My dog is called Rex") is None

    def test_general_question(self):
        assert self.d.detect("Tell me about Python") is None

    def test_empty_string(self):
        assert self.d.detect("") is None


class TestTaskBeforeProject:
    """Task patterns must take priority over project patterns for specific verbs."""

    def setup_method(self):
        self.d = WorkDetector()

    def test_implementing_is_task_not_project(self):
        r = self.d.detect("I'm implementing the new engine")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_writing_is_task_not_project(self):
        r = self.d.detect("I'm writing unit tests")
        assert r is not None
        assert r.kind == DetectionKind.TASK_DECLARATION

    def test_working_on_genesis_is_project(self):
        r = self.d.detect("I'm working on Genesis-033")
        assert r is not None
        assert r.kind == DetectionKind.PROJECT_DECLARATION
