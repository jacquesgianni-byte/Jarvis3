"""
Tests for Genesis-029 Sprint-001: Conversation State Engine

Covers:
    - Entity extraction from statements
    - Active entity tracking via SessionContext
    - Pronoun resolution (he, she, it, they, their)
    - Context decay / expiry
    - Pronoun rewriting
    - No regressions on Genesis-028 property system
"""

from __future__ import annotations

import pytest
from core.conversation.conversation_state_engine import (
    ConversationStateEngine,
    PronounResolution,
)
from core.conversation.session_context import SessionContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> ConversationStateEngine:
    return ConversationStateEngine()


@pytest.fixture
def session() -> SessionContext:
    return SessionContext()


# ===========================================================================
# Entity extraction
# ===========================================================================

class TestExtractEntityFromText:

    def test_simple_is_statement(self, engine):
        assert engine.extract_entity_from_text("Leo is 9.") == "Leo"

    def test_colour_statement(self, engine):
        assert engine.extract_entity_from_text("Rex is brown.") == "Rex"

    def test_status_statement(self, engine):
        assert engine.extract_entity_from_text("Canon is offline.") == "Canon"

    def test_is_now_statement(self, engine):
        assert engine.extract_entity_from_text("Leo is now 10.") == "Leo"

    def test_weighs_statement(self, engine):
        assert engine.extract_entity_from_text("Tom weighs 35 kg.") == "Tom"

    def test_question_returns_none(self, engine):
        assert engine.extract_entity_from_text("How old is Leo?") is None

    def test_pronoun_subject_returns_none(self, engine):
        assert engine.extract_entity_from_text("He is brown.") is None

    def test_empty_returns_none(self, engine):
        assert engine.extract_entity_from_text("") is None

    def test_none_returns_none(self, engine):
        assert engine.extract_entity_from_text(None) is None

    def test_multiword_subject(self, engine):
        result = engine.extract_entity_from_text("Server Alpha is online.")
        assert result == "Server"  # first capitalised word

    def test_stop_subject_i_returns_none(self, engine):
        assert engine.extract_entity_from_text("I is wrong.") is None


# ===========================================================================
# update_entity
# ===========================================================================

class TestUpdateEntity:

    def test_sets_active_person(self, engine, session):
        engine.update_entity("Leo", session)
        assert session.active_person is not None
        assert session.active_person.value == "Leo"

    def test_overwrites_previous_entity(self, engine, session):
        engine.update_entity("Leo", session)
        engine.update_entity("Lucas", session)
        assert session.active_person.value == "Lucas"

    def test_stop_subject_not_set(self, engine, session):
        engine.update_entity("he", session)
        assert session.active_person is None

    def test_empty_not_set(self, engine, session):
        engine.update_entity("", session)
        assert session.active_person is None

    def test_short_name_not_set(self, engine, session):
        engine.update_entity("A", session)
        assert session.active_person is None


# ===========================================================================
# update_group
# ===========================================================================

class TestUpdateGroup:

    def test_sets_active_topic(self, engine, session):
        engine.update_group("3 dogs", session)
        assert session.active_topic is not None
        assert session.active_topic.value == "3 dogs"

    def test_overwrites_previous_group(self, engine, session):
        engine.update_group("3 dogs", session)
        engine.update_group("2 children", session)
        assert session.active_topic.value == "2 children"

    def test_empty_not_set(self, engine, session):
        engine.update_group("", session)
        assert session.active_topic is None


# ===========================================================================
# resolve_pronoun — singular
# ===========================================================================

class TestResolveSingularPronoun:

    def test_he_resolves_to_active_person(self, engine, session):
        engine.update_entity("Leo", session)
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.resolved is True
        assert result.entity == "Leo"
        assert result.pronoun == "he"
        assert result.is_plural is False

    def test_she_resolves_to_active_person(self, engine, session):
        engine.update_entity("Luna", session)
        result = engine.resolve_pronoun("What colour is she?", session)
        assert result.resolved is True
        assert result.entity == "Luna"

    def test_it_resolves_to_active_person(self, engine, session):
        engine.update_entity("Canon", session)
        result = engine.resolve_pronoun("Is it offline?", session)
        assert result.resolved is True
        assert result.entity == "Canon"

    def test_no_active_entity_returns_not_found(self, engine, session):
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.resolved is False

    def test_no_pronoun_returns_not_found(self, engine, session):
        engine.update_entity("Leo", session)
        result = engine.resolve_pronoun("How old is Leo?", session)
        assert result.resolved is False

    def test_most_recent_entity_wins(self, engine, session):
        engine.update_entity("Lucas", session)
        engine.update_entity("Leo", session)
        result = engine.resolve_pronoun("He likes football.", session)
        assert result.entity == "Leo"

    def test_his_resolves(self, engine, session):
        engine.update_entity("Rex", session)
        result = engine.resolve_pronoun("What is his colour?", session)
        assert result.resolved is True
        assert result.entity == "Rex"


# ===========================================================================
# resolve_pronoun — plural
# ===========================================================================

class TestResolvePluralPronoun:

    def test_they_resolves_to_active_group(self, engine, session):
        engine.update_group("3 dogs", session)
        result = engine.resolve_pronoun("What are their names?", session)
        assert result.resolved is True
        assert result.entity == "3 dogs"
        assert result.is_plural is True

    def test_their_resolves_to_active_group(self, engine, session):
        engine.update_group("2 children", session)
        result = engine.resolve_pronoun("What are their ages?", session)
        assert result.resolved is True
        assert result.entity == "2 children"

    def test_no_active_group_returns_not_found(self, engine, session):
        result = engine.resolve_pronoun("What are their names?", session)
        assert result.resolved is False


# ===========================================================================
# rewrite_with_entity
# ===========================================================================

class TestRewriteWithEntity:

    def test_replaces_he_with_entity(self, engine):
        resolution = PronounResolution(
            resolved=True, pronoun="he", entity="Leo", is_plural=False
        )
        result = engine.rewrite_with_entity("How old is he?", resolution)
        assert result == "How old is Leo?"

    def test_replaces_it_with_entity(self, engine):
        resolution = PronounResolution(
            resolved=True, pronoun="it", entity="Canon", is_plural=False
        )
        result = engine.rewrite_with_entity("Is it offline?", resolution)
        assert result == "Is Canon offline?"

    def test_replaces_she_with_entity(self, engine):
        resolution = PronounResolution(
            resolved=True, pronoun="she", entity="Luna", is_plural=False
        )
        result = engine.rewrite_with_entity("What colour is she?", resolution)
        assert result == "What colour is Luna?"

    def test_no_resolution_returns_original(self, engine):
        resolution = PronounResolution.not_found()
        original = "How old is he?"
        result = engine.rewrite_with_entity(original, resolution)
        assert result == original

    def test_replaces_their_with_entity(self, engine):
        resolution = PronounResolution(
            resolved=True, pronoun="their", entity="dogs", is_plural=True
        )
        result = engine.rewrite_with_entity("What are their names?", resolution)
        assert "dogs" in result


# ===========================================================================
# Context decay
# ===========================================================================

class TestContextDecay:

    def test_entity_decays_after_many_turns(self, engine, session):
        engine.update_entity("Leo", session)
        # Advance turns past decay threshold
        for _ in range(12):
            session.increment_turn()
        result = engine.resolve_pronoun("How old is he?", session)
        # After full decay, should not resolve
        assert result.resolved is False

    def test_entity_usable_within_decay_window(self, engine, session):
        engine.update_entity("Leo", session)
        # Advance a few turns — still within window
        for _ in range(3):
            session.increment_turn()
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.resolved is True
        assert result.entity == "Leo"


# ===========================================================================
# Integration scenarios
# ===========================================================================

class TestIntegrationScenarios:

    def test_scenario_1_children(self, engine, session):
        """Leo is 9. He likes football. → he = Leo"""
        engine.update_entity("Leo", session)
        result = engine.resolve_pronoun("He likes football.", session)
        assert result.resolved is True
        assert result.entity == "Leo"

    def test_scenario_2_printers(self, engine, session):
        """Canon is offline. Is it offline? → it = Canon"""
        engine.update_entity("Canon", session)
        result = engine.resolve_pronoun("Is it offline?", session)
        assert result.resolved is True
        assert result.entity == "Canon"

    def test_scenario_3_pets(self, engine, session):
        """Rex is brown. What colour is he? → he = Rex"""
        engine.update_entity("Rex", session)
        result = engine.resolve_pronoun("What colour is he?", session)
        assert result.resolved is True
        assert result.entity == "Rex"

    def test_scenario_4_most_recent_entity(self, engine, session):
        """Lucas is 14. Leo is 9. He is very smart. → he = Leo"""
        engine.update_entity("Lucas", session)
        engine.update_entity("Leo", session)
        result = engine.resolve_pronoun("He is very smart.", session)
        assert result.resolved is True
        assert result.entity == "Leo"

    def test_rewrite_then_query(self, engine, session):
        """Full flow: resolve + rewrite → correct property key"""
        engine.update_entity("Rex", session)
        resolution = engine.resolve_pronoun("What colour is he?", session)
        assert resolution.resolved
        rewritten = engine.rewrite_with_entity("What colour is he?", resolution)
        assert "Rex" in rewritten
        assert "he" not in rewritten.lower()

    def test_entity_updates_across_turns(self, engine, session):
        """Each new named entity becomes the active subject."""
        engine.update_entity("Rex", session)
        session.increment_turn()
        engine.update_entity("Tom", session)
        session.increment_turn()
        result = engine.resolve_pronoun("Is he black?", session)
        assert result.entity == "Tom"  # most recent

    def test_extract_then_update_then_resolve(self, engine, session):
        """Full pipeline: extract entity from text → update → resolve pronoun."""
        entity = engine.extract_entity_from_text("Canon is offline.")
        assert entity == "Canon"
        engine.update_entity(entity, session)
        result = engine.resolve_pronoun("Is it still offline?", session)
        assert result.resolved is True
        assert result.entity == "Canon"