"""
GC-009 — Pronoun Resolution Regression Tests

Verifies that pet-related pronouns resolve correctly after pet statements,
using the existing ContextManager and ContextResolver architecture.

Genesis-025 Sprint-003 update:
    _detect_pet() removed from ContextManager — pet topic is now set via
    SlotCompletionEngine → MemorySkill → active_topic (set by Agent after
    storing the memory). Tests updated to reflect new architecture.

Coverage:
  - SlotCompletionEngine detects pet facts (replaces ContextManager pet tests)
  - ContextResolver resolves "they/them" via active_topic after pet statements
  - Existing project/milestone/task/person resolution unchanged
  - Unrelated queries not resolved
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.context_manager import ContextManager
from core.conversation.context_resolver import ContextResolver
from core.conversation.session_context import SessionContext
from core.conversation.slot_completion_engine import SlotCompletionEngine


def make_session() -> SessionContext:
    return SessionContext()


def make_manager(session: SessionContext) -> ContextManager:
    return ContextManager(session)


def make_resolver(session: SessionContext) -> ContextResolver:
    return ContextResolver(session)


# ===========================================================================
# 1. SlotCompletionEngine — detects pet facts (replaces ContextManager tests)
#    Genesis-025 Sprint-003: active_topic set by Agent after SlotCompletionEngine
#    returns a MemoryDetection, not by ContextManager directly.
# ===========================================================================

class TestSlotCompletionEnginePetFacts:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_i_have_dogs_detected(self):
        result = self.engine.detect("I have 2 dogs.")
        assert result is not None
        assert result.key == "pets"
        assert "dog" in result.value.lower()

    def test_their_names_detected(self):
        result = self.engine.detect(
            "Their names are Rex and Tom.",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_my_dogs_are_detected(self):
        # "My dogs are Rex and Tom." is caught by MemoryDetector not
        # SlotCompletionEngine — it has no possession signal.
        from core.conversation.memory_detector import MemoryDetector
        result = MemoryDetector().detect("My dogs are Rex and Tom.")
        assert result is not None
        assert result.key == "pet names"

    def test_i_have_cat_detected(self):
        result = self.engine.detect("I have a cat.")
        assert result is not None
        assert result.key == "pets"
        assert "cat" in result.value.lower()

    def test_implicit_names_after_cats(self):
        result = self.engine.detect(
            "Their names are Rex and Tom.",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"


# ===========================================================================
# 2. ContextManager — existing person detection unchanged
# ===========================================================================

class TestContextManagerPersonFacts:

    def test_claude_sets_person(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("Claude is my senior engineer.", "")
        assert session.active_person is not None
        assert "Claude" in session.active_person.value

    def test_gpt_sets_person(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("GPT handles the specs.", "")
        assert session.active_person is not None


# ===========================================================================
# 3. ContextResolver — resolves "they/them" via active_topic
#    active_topic must be set manually in tests (Agent does this in production)
# ===========================================================================

class TestContextResolverPronouns:

    def test_they_resolves_when_topic_set(self):
        session = make_session()
        resolver = make_resolver(session)

        # Simulate Agent setting active_topic after storing pet memory
        session.set_topic("Rex and Tom", raw="Their names are Rex and Tom.")
        session.increment_turn()

        assert resolver.needs_resolution("Who are they?")
        resolution = resolver.resolve("Who are they?")
        assert resolution.resolved
        assert resolution.context_hint is not None

    def test_no_resolution_without_context(self):
        session = make_session()
        resolver = make_resolver(session)
        resolution = resolver.resolve("Who are they?")
        assert not resolution.resolved

    def test_needs_resolution_detects_they(self):
        session = make_session()
        resolver = make_resolver(session)
        assert resolver.needs_resolution("Who are they?")

    def test_needs_resolution_detects_it(self):
        session = make_session()
        resolver = make_resolver(session)
        assert resolver.needs_resolution("What colour is it?")


# ===========================================================================
# 4. Existing resolution unchanged
# ===========================================================================

class TestExistingResolutionUnchanged:

    def test_project_detection_unchanged(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("I'm building Genesis-022.", "")
        assert session.active_project is not None

    def test_milestone_detection_unchanged(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("We finished Genesis-021.", "")
        assert session.active_milestone is not None

    def test_unrelated_query_not_resolved(self):
        session = make_session()
        resolver = make_resolver(session)
        assert not resolver.needs_resolution("Who invented the steam engine?")

    def test_turn_increments(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("I have 2 dogs.", "")
        manager.update("Their names are Rex and Tom.", "")
        assert session.current_turn == 2