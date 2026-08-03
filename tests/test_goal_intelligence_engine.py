"""
Tests — GoalIntelligenceEngine (end-to-end)
Genesis-033 Sprint-002

Tests the full pipeline: utterance → detection → storage → response.
Uses the same in-memory KE stub as tracker tests.
"""

import pytest
from core.goal_intelligence.engine import GoalIntelligenceEngine


# ── In-memory KE stub (same as tracker tests) ─────────────────────────────────

class _MemoryStore:
    def __init__(self):
        self._records: dict = {}

    def store_memory(self, subject, category, attribute, value, tags=None, **kwargs):
        from datetime import datetime, UTC
        from uuid import uuid4

        class Rec:
            pass

        key = f"{subject}::{attribute}"
        r = Rec()
        r.id = str(uuid4())
        r.subject = subject
        r.category = category
        r.attribute = attribute
        r.value = value
        r.tags = list(tags or [])
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
        return results[:limit]

    def search_memory(self, query, subject=None, **kwargs):
        return self.list_memories(subject=subject)


@pytest.fixture()
def engine():
    return GoalIntelligenceEngine(_MemoryStore())


# ── can_answer ─────────────────────────────────────────────────────────────────

class TestCanAnswer:
    def test_goal_declaration(self, engine):
        assert engine.can_answer("My goal is to release Jarvis 1.0") is True

    def test_project_declaration(self, engine):
        assert engine.can_answer("I'm working on Genesis-033") is True

    def test_task_declaration(self, engine):
        assert engine.can_answer("Today I'm implementing GoalEngine") is True

    def test_what_am_i_working_on(self, engine):
        assert engine.can_answer("What am I working on?") is True

    def test_what_are_my_goals(self, engine):
        assert engine.can_answer("What are my goals?") is True

    def test_unrelated(self, engine):
        assert engine.can_answer("What's the weather?") is False

    def test_greeting(self, engine):
        assert engine.can_answer("Hello Jarvis") is False


# ── Desktop validation scenarios ───────────────────────────────────────────────

class TestDesktopScenarios:
    """Mirrors the five desktop validation scenarios from the sprint spec."""

    def test_scenario_1_goal_stored(self, engine):
        """My goal is to release Jarvis 1.0 → stored correctly."""
        response = engine.process("My goal is to release Jarvis 1.0")
        assert "release Jarvis 1.0" in response or "Jarvis 1.0" in response
        assert engine._goals.active_goal() is not None

    def test_scenario_2_project_recognised(self, engine):
        """I'm working on Genesis-033 → active project recognised."""
        engine.process("My goal is to release Jarvis 1.0")
        response = engine.process("I'm working on Genesis-033")
        assert "Genesis-033" in response
        assert engine._projects.active_project() is not None
        assert engine._projects.active_project().title == "Genesis-033"

    def test_scenario_3_task_recognised(self, engine):
        """Today I'm implementing GoalEngine → task recognised."""
        engine.process("My goal is to release Jarvis 1.0")
        engine.process("I'm working on Genesis-033")
        response = engine.process("Today I'm implementing GoalEngine")
        assert "GoalEngine" in response
        assert engine._tasks.active_task() is not None
        assert engine._tasks.active_task().title == "GoalEngine"

    def test_scenario_4_goal_recall(self, engine):
        """What are my goals? → lists active goals."""
        engine.process("My goal is to release Jarvis 1.0")
        response = engine.process("What are my goals?")
        assert "Jarvis 1.0" in response or "release" in response.lower()

    def test_scenario_5_status_recall(self, engine):
        """What am I working on? → shows current project and task."""
        engine.process("My goal is to release Jarvis 1.0")
        engine.process("I'm working on Genesis-033")
        engine.process("Today I'm implementing GoalEngine")
        response = engine.process("What am I working on?")
        assert "Genesis-033"         in response
        assert "GoalEngine"          in response


# ── Hierarchy linkage ──────────────────────────────────────────────────────────

class TestHierarchy:
    def test_project_links_to_active_goal(self, engine):
        engine.process("My goal is to release Jarvis 1.0")
        goal = engine._goals.active_goal()
        engine.process("I'm working on Genesis-033")
        project = engine._projects.active_project()
        assert project.goal_id == goal.id

    def test_task_links_to_active_project(self, engine):
        engine.process("My goal is to release Jarvis 1.0")
        engine.process("I'm working on Genesis-033")
        project = engine._projects.active_project()
        engine.process("I'm implementing GoalEngine")
        task = engine._tasks.active_task()
        assert task.project_id == project.id

    def test_task_links_to_active_goal(self, engine):
        engine.process("My goal is to release Jarvis 1.0")
        goal = engine._goals.active_goal()
        engine.process("I'm working on Genesis-033")
        engine.process("I'm implementing GoalEngine")
        task = engine._tasks.active_task()
        assert task.goal_id == goal.id


# ── Status recall ──────────────────────────────────────────────────────────────

class TestStatusRecall:
    def test_empty_status(self, engine):
        response = engine.process("What am I working on?")
        assert "haven't" in response.lower() or "no" in response.lower() or "yet" in response.lower()

    def test_goal_only_status(self, engine):
        engine.process("My goal is to release Jarvis 1.0")
        response = engine.process("What am I working on?")
        assert "Jarvis 1.0" in response

    def test_full_status_contains_all_levels(self, engine):
        engine.process("My goal is to release Jarvis 1.0")
        engine.process("I'm working on Genesis-033")
        engine.process("I'm implementing GoalEngine")
        response = engine.process("What am I working on?")
        assert "Jarvis 1.0"          in response
        assert "Genesis-033"          in response
        assert "GoalEngine"           in response


# ── Response format ────────────────────────────────────────────────────────────

class TestResponseFormat:
    def test_goal_declaration_mentions_title(self, engine):
        response = engine.process("My goal is to release Jarvis 1.0")
        assert response != ""
        assert "Jarvis 1.0" in response or "release" in response.lower()

    def test_project_declaration_mentions_title(self, engine):
        response = engine.process("I'm working on Genesis-033")
        assert "Genesis-033" in response

    def test_task_declaration_mentions_title(self, engine):
        response = engine.process("I'm implementing GoalEngine")
        assert "GoalEngine" in response

    def test_unknown_utterance_returns_empty(self, engine):
        response = engine.process("What is the weather?")
        assert response == ""

    def test_no_ai_calls(self, engine):
        """GoalIntelligenceEngine never calls an AI model."""
        # Confirmed by design — engine has no ai attribute
        assert not hasattr(engine, "_ai")
        assert not hasattr(engine, "ai")
