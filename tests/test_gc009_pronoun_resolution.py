"""
GC-009 — Pronoun Resolution Regression Tests

Verifies that pet-related pronouns resolve correctly after pet statements,
using the existing ContextManager and ContextResolver architecture.

Coverage:
  - ContextManager sets active_topic for pet facts (I have N dogs, their names are X)
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


def make_session() -> SessionContext:
    return SessionContext()


def make_manager(session: SessionContext) -> ContextManager:
    return ContextManager(session)


def make_resolver(session: SessionContext) -> ContextResolver:
    return ContextResolver(session)


# ===========================================================================
# 1. ContextManager — PET facts set active_topic
# ===========================================================================

class TestContextManagerPetFacts:

    def test_i_have_dogs_sets_topic(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("I have 2 dogs.", "")
        assert session.active_topic is not None
        assert "dog" in session.active_topic.value.lower()

    def test_their_names_sets_topic(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("Their names are Rex and Tom.", "")
        assert session.active_topic is not None
        assert "Rex" in session.active_topic.value or "Tom" in session.active_topic.value

    def test_my_dogs_are_sets_topic(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("My dogs are Rex and Tom.", "")
        assert session.active_topic is not None

    def test_i_have_cat_sets_topic(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("I have a cat.", "")
        assert session.active_topic is not None
        assert "cat" in session.active_topic.value.lower()

    def test_pet_topic_overrides_previous(self):
        session = make_session()
        manager = make_manager(session)
        manager.update("I have 2 dogs.", "")
        manager.update("Their names are Rex and Tom.", "")
        assert session.active_topic is not None
        assert "Rex" in session.active_topic.value or "Tom" in session.active_topic.value


# ===========================================================================
# 2. ContextManager — existing person detection unchanged
# ===========================================================================

class TestContextManagerPersonFacts:

    def test_claude_sets_person(self):
        """Original _PERSON_PATTERNS detects Claude by name."""
        session = make_session()
        manager = make_manager(session)
        manager.update("Claude is my senior engineer.", "")
        assert session.active_person is not None
        assert "Claude" in session.active_person.value

    def test_gpt_sets_person(self):
        """Original _PERSON_PATTERNS detects GPT by name."""
        session = make_session()
        manager = make_manager(session)
        manager.update("GPT handles the specs.", "")
        assert session.active_person is not None


# ===========================================================================
# 3. ContextResolver — resolves "they/them" via active_topic
# ===========================================================================

class TestContextResolverPronouns:

    def test_they_resolves_after_pet_statement(self):
        session = make_session()
        manager = make_manager(session)
        resolver = make_resolver(session)

        # Turn 1: store pet facts
        manager.update("I have 2 dogs.", "")
        manager.update("Their names are Rex and Tom.", "")

        # Turn 2: resolve "they"
        assert resolver.needs_resolution("Who are they?")
        resolution = resolver.resolve("Who are they?")
        assert resolution.resolved
        assert resolution.context_hint is not None

    def test_no_resolution_without_context(self):
        session = make_session()
        resolver = make_resolver(session)
        # No prior context set
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