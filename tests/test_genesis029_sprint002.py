"""
Tests for Genesis-029 Sprint-002: Conversation Focus & Topic Switching

Covers:
    - detect_focus_change: entity patterns
    - detect_focus_change: group patterns
    - apply_focus_change: session state updates
    - Pronoun resolution after focus change
    - Full scenario walkthroughs
    - No regression on Sprint-001 pronoun resolution
"""

from __future__ import annotations

import pytest
from core.conversation.conversation_state_engine import (
    ConversationStateEngine,
    FocusChange,
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
# detect_focus_change — entity patterns
# ===========================================================================

class TestDetectFocusChangeEntity:

    def test_tell_me_about_entity(self, engine):
        result = engine.detect_focus_change("Tell me about Lucas.")
        assert result.detected is True
        assert result.entity == "Lucas"
        assert result.is_group is False

    def test_what_about_entity(self, engine):
        result = engine.detect_focus_change("What about Chase?")
        assert result.detected is True
        assert result.entity == "Chase"
        assert result.is_group is False

    def test_lets_talk_about_entity(self, engine):
        result = engine.detect_focus_change("Let's talk about Rex.")
        assert result.detected is True
        assert result.entity == "Rex"
        assert result.is_group is False

    def test_back_to_entity(self, engine):
        result = engine.detect_focus_change("Back to Lucas.")
        assert result.detected is True
        assert result.entity == "Lucas"
        assert result.is_group is False

    def test_speaking_of_entity(self, engine):
        result = engine.detect_focus_change("Speaking of Canon.")
        assert result.detected is True
        assert result.entity == "Canon"
        assert result.is_group is False

    def test_tell_me_about_hp(self, engine):
        result = engine.detect_focus_change("Tell me about HP.")
        assert result.detected is True
        assert result.entity == "HP"
        assert result.is_group is False

    def test_what_about_lowercase(self, engine):
        result = engine.detect_focus_change("what about Chase?")
        assert result.detected is True
        assert result.entity == "Chase"

    def test_stop_subject_not_detected(self, engine):
        result = engine.detect_focus_change("Tell me about it.")
        assert result.detected is False

    def test_empty_returns_not_found(self, engine):
        assert engine.detect_focus_change("").detected is False

    def test_none_returns_not_found(self, engine):
        assert engine.detect_focus_change(None).detected is False

    def test_plain_statement_not_detected(self, engine):
        result = engine.detect_focus_change("Lucas is 14.")
        assert result.detected is False

    def test_confidence_set(self, engine):
        result = engine.detect_focus_change("Tell me about Lucas.")
        assert result.confidence > 0.0


# ===========================================================================
# detect_focus_change — group patterns
# ===========================================================================

class TestDetectFocusChangeGroup:

    def test_lets_talk_about_my_group(self, engine):
        result = engine.detect_focus_change("Let's talk about my printers.")
        assert result.detected is True
        assert result.entity == "printers"
        assert result.is_group is True

    def test_tell_me_about_my_group(self, engine):
        result = engine.detect_focus_change("Tell me about my children.")
        assert result.detected is True
        assert result.entity == "children"
        assert result.is_group is True

    def test_what_about_my_group(self, engine):
        result = engine.detect_focus_change("What about my dogs?")
        assert result.detected is True
        assert result.entity == "dogs"
        assert result.is_group is True

    def test_now_lets_talk_about_my_group(self, engine):
        result = engine.detect_focus_change("Now let's talk about my children.")
        assert result.detected is True
        assert result.entity == "children"
        assert result.is_group is True

    def test_back_to_my_group(self, engine):
        result = engine.detect_focus_change("Back to my printers.")
        assert result.detected is True
        assert result.entity == "printers"
        assert result.is_group is True

    def test_group_takes_priority_over_entity(self, engine):
        # "Tell me about my printers" should be group, not entity "my"
        result = engine.detect_focus_change("Tell me about my printers.")
        assert result.is_group is True

    def test_stop_group_not_detected(self, engine):
        result = engine.detect_focus_change("Tell me about my other thing.")
        assert result.detected is False or result.entity not in ("other", "thing")


# ===========================================================================
# apply_focus_change
# ===========================================================================

class TestApplyFocusChange:

    def test_entity_change_updates_active_person(self, engine, session):
        change = FocusChange(detected=True, entity="Lucas", is_group=False, confidence=0.92)
        engine.apply_focus_change(change, session)
        assert session.active_person is not None
        assert session.active_person.value == "Lucas"

    def test_group_change_updates_active_topic(self, engine, session):
        change = FocusChange(detected=True, entity="printers", is_group=True, confidence=0.92)
        engine.apply_focus_change(change, session)
        assert session.active_topic is not None
        assert session.active_topic.value == "printers"

    def test_not_detected_does_nothing(self, engine, session):
        engine.update_entity("Leo", session)
        change = FocusChange.not_found()
        engine.apply_focus_change(change, session)
        # Entity unchanged
        assert session.active_person.value == "Leo"

    def test_entity_change_overwrites_previous(self, engine, session):
        engine.update_entity("Leo", session)
        change = FocusChange(detected=True, entity="Lucas", is_group=False, confidence=0.92)
        engine.apply_focus_change(change, session)
        assert session.active_person.value == "Lucas"


# ===========================================================================
# Pronoun resolution after focus change
# ===========================================================================

class TestPronounAfterFocusChange:

    def test_he_resolves_to_focus_entity(self, engine, session):
        # Set initial entity
        engine.update_entity("Leo", session)
        # Switch focus to Lucas
        change = engine.detect_focus_change("Tell me about Lucas.")
        engine.apply_focus_change(change, session)
        # He should now refer to Lucas
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.resolved is True
        assert result.entity == "Lucas"

    def test_it_resolves_to_focus_entity(self, engine, session):
        engine.update_entity("Canon", session)
        change = engine.detect_focus_change("Tell me about HP.")
        engine.apply_focus_change(change, session)
        result = engine.resolve_pronoun("Is it online?", session)
        assert result.resolved is True
        assert result.entity == "HP"

    def test_he_resolves_after_what_about(self, engine, session):
        engine.update_entity("Rex", session)
        change = engine.detect_focus_change("What about Chase?")
        engine.apply_focus_change(change, session)
        result = engine.resolve_pronoun("What colour is he?", session)
        assert result.resolved is True
        assert result.entity == "Chase"

    def test_focus_switch_then_switch_again(self, engine, session):
        engine.update_entity("Leo", session)
        # Switch to Lucas
        change1 = engine.detect_focus_change("Tell me about Lucas.")
        engine.apply_focus_change(change1, session)
        assert engine.resolve_pronoun("How old is he?", session).entity == "Lucas"
        # Switch back to Leo
        change2 = engine.detect_focus_change("Tell me about Leo.")
        engine.apply_focus_change(change2, session)
        assert engine.resolve_pronoun("How old is he?", session).entity == "Leo"


# ===========================================================================
# Full scenario walkthroughs
# ===========================================================================

class TestScenarios:

    def test_scenario_1_entity_switch(self, engine, session):
        """Lucas is 14. Leo is 9. Tell me about Lucas. How old is he? → Lucas"""
        engine.update_entity("Lucas", session)
        session.increment_turn()
        engine.update_entity("Leo", session)
        session.increment_turn()
        # Focus switch
        change = engine.detect_focus_change("Tell me about Lucas.")
        assert change.detected
        engine.apply_focus_change(change, session)
        # Pronoun should now resolve to Lucas
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.resolved is True
        assert result.entity == "Lucas"

    def test_scenario_2_switch_again(self, engine, session):
        """Tell me about Leo. How old is he? → Leo"""
        engine.update_entity("Lucas", session)
        change = engine.detect_focus_change("Tell me about Leo.")
        assert change.detected
        engine.apply_focus_change(change, session)
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.entity == "Leo"

    def test_scenario_3_device_context(self, engine, session):
        """Canon is offline. HP is online. Tell me about HP. Is it online? → HP"""
        engine.update_entity("Canon", session)
        session.increment_turn()
        engine.update_entity("HP", session)
        session.increment_turn()
        change = engine.detect_focus_change("Tell me about HP.")
        engine.apply_focus_change(change, session)
        result = engine.resolve_pronoun("Is it online?", session)
        assert result.resolved is True
        assert result.entity == "HP"

    def test_scenario_4_pet_context(self, engine, session):
        """Rex is brown. Chase is white. What about Chase? What colour is he? → Chase"""
        engine.update_entity("Rex", session)
        session.increment_turn()
        engine.update_entity("Chase", session)
        session.increment_turn()
        change = engine.detect_focus_change("What about Chase?")
        assert change.detected
        engine.apply_focus_change(change, session)
        result = engine.resolve_pronoun("What colour is he?", session)
        assert result.resolved is True
        assert result.entity == "Chase"

    def test_scenario_5_group_switch(self, engine, session):
        """Let's talk about my printers. → active group = printers"""
        change = engine.detect_focus_change("Let's talk about my printers.")
        assert change.detected
        assert change.is_group is True
        engine.apply_focus_change(change, session)
        assert session.active_topic.value == "printers"
        # Now switch to children
        change2 = engine.detect_focus_change("Now let's talk about my children.")
        assert change2.detected
        engine.apply_focus_change(change2, session)
        assert session.active_topic.value == "children"

    def test_no_false_positive_on_plain_statement(self, engine, session):
        """Plain statements don't trigger focus changes."""
        engine.update_entity("Leo", session)
        change = engine.detect_focus_change("Leo is 9.")
        assert change.detected is False
        # Entity still Leo
        result = engine.resolve_pronoun("How old is he?", session)
        assert result.entity == "Leo"

    def test_sprint001_pronoun_still_works(self, engine, session):
        """Sprint-001 pronoun resolution unchanged after Sprint-002 additions."""
        engine.update_entity("Rex", session)
        result = engine.resolve_pronoun("What colour is he?", session)
        assert result.resolved is True
        assert result.entity == "Rex"
        rewritten = engine.rewrite_with_entity("What colour is he?", result)
        assert "Rex" in rewritten