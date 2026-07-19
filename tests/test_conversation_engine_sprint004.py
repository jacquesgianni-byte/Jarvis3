"""
Genesis-022 Sprint-004 — Dialogue Manager Tests
Completely self-contained. No dependency on other test files.

Coverage:
  DialogueType:
    - all types exist, labels, unique values
    - is_slot_related, is_continuation properties

  DialogueResult:
    - immutable, fields, str
    - continue_normally() factory
    - unknown() factory
    - slot fields populated correctly

  DialogueManager.is_acknowledgement():
    - all ack patterns: ok, yes, no, sure, got it, etc.
    - non-ack inputs
    - empty/whitespace
    - case-insensitive

  DialogueManager.has_topic_change():
    - topic change markers: actually, never mind, different question, etc.
    - normal input
    - empty/whitespace

  DialogueManager.analyse() — ANSWER_PENDING:
    - pending question answered
    - slot name and value populated
    - pending question text preserved
    - confidence 0.90

  DialogueManager.analyse() — FILL_SLOT:
    - single active slot filled
    - multiple slots, name match
    - multiple slots, no match → CONTINUE

  DialogueManager.analyse() — ACKNOWLEDGEMENT:
    - short acks before routing
    - is_acknowledgement flag set

  DialogueManager.analyse() — TOPIC_CHANGE:
    - topic change detected
    - confidence 0.85

  DialogueManager.analyse() — NEW_CONVERSATION:
    - no context at all → NEW_CONVERSATION

  DialogueManager.analyse() — CONTINUE:
    - normal input with context
    - normal input without context but turns exist

  DialogueManager.analyse() — edge cases:
    - empty input → UNKNOWN
    - whitespace → UNKNOWN
    - punctuation only
    - very long input
    - slot value extraction strips filler phrases

  State read-only guarantee:
    - analyse() never modifies state

  Backwards compatibility
"""

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_dialogue import (
    DialogueType, DialogueResult, DialogueManager,
)
from core.conversation.conversation_state import ConversationState
from core.conversation.conversation_policy import ConversationPolicy
from core.conversation.conversation_models import Slot, SlotStatus, Topic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager() -> DialogueManager:
    return DialogueManager()


def make_policy(**kwargs) -> ConversationPolicy:
    return ConversationPolicy(**kwargs)


def make_state() -> ConversationState:
    return ConversationState()


def state_with_pending(
    slot_name="colour", question="What colour?"
) -> ConversationState:
    s = ConversationState()
    slot = Slot(name=slot_name, question=question)
    s.set_pending(slot)
    return s


def state_with_slot(name="colour", question="What colour?") -> ConversationState:
    s = ConversationState()
    s.add_slot(Slot(name=name, question=question))
    return s


def state_with_context() -> ConversationState:
    s = ConversationState()
    s.set_topic(Topic(name="planning"))
    return s


DEFAULT_POLICY = make_policy()


# ===========================================================================
# 1. DIALOGUE TYPE
# ===========================================================================

class TestDialogueType:

    def test_all_types_exist(self):
        for name in [
            "ANSWER_PENDING", "FILL_SLOT", "CONTINUE",
            "TOPIC_CHANGE", "NEW_CONVERSATION", "ACKNOWLEDGEMENT", "UNKNOWN"
        ]:
            assert hasattr(DialogueType, name)

    def test_values_unique(self):
        values = [d.value for d in DialogueType]
        assert len(values) == len(set(values))

    def test_labels(self):
        assert DialogueType.ANSWER_PENDING.label()   == "Answer Pending"
        assert DialogueType.FILL_SLOT.label()        == "Fill Slot"
        assert DialogueType.CONTINUE.label()         == "Continue"
        assert DialogueType.TOPIC_CHANGE.label()     == "Topic Change"
        assert DialogueType.NEW_CONVERSATION.label() == "New Conversation"
        assert DialogueType.ACKNOWLEDGEMENT.label()  == "Acknowledgement"
        assert DialogueType.UNKNOWN.label()          == "Unknown"

    def test_is_slot_related(self):
        assert DialogueType.ANSWER_PENDING.is_slot_related
        assert DialogueType.FILL_SLOT.is_slot_related
        assert not DialogueType.CONTINUE.is_slot_related
        assert not DialogueType.ACKNOWLEDGEMENT.is_slot_related

    def test_is_continuation(self):
        assert DialogueType.CONTINUE.is_continuation
        assert DialogueType.ACKNOWLEDGEMENT.is_continuation
        assert DialogueType.ANSWER_PENDING.is_continuation
        assert DialogueType.FILL_SLOT.is_continuation
        assert not DialogueType.TOPIC_CHANGE.is_continuation
        assert not DialogueType.NEW_CONVERSATION.is_continuation
        assert not DialogueType.UNKNOWN.is_continuation


# ===========================================================================
# 2. DIALOGUE RESULT
# ===========================================================================

class TestDialogueResult:

    def test_is_frozen(self):
        r = DialogueResult.continue_normally("Hello.")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.dialogue_type = DialogueType.UNKNOWN

    def test_continue_normally_factory(self):
        r = DialogueResult.continue_normally("Hello.")
        assert r.dialogue_type == DialogueType.CONTINUE
        assert r.original_input == "Hello."
        assert r.confidence == 1.0

    def test_continue_normally_custom_reason(self):
        r = DialogueResult.continue_normally("Hello.", "custom reason")
        assert r.reason == "custom reason"

    def test_unknown_factory(self):
        r = DialogueResult.unknown("???")
        assert r.dialogue_type == DialogueType.UNKNOWN
        assert r.confidence == 0.0

    def test_str_with_slot(self):
        r = DialogueResult(
            dialogue_type=DialogueType.FILL_SLOT,
            original_input="Blue.",
            slot_name="colour",
            slot_value="Blue",
        )
        assert "colour" in str(r)
        assert "Blue" in str(r)

    def test_str_without_slot(self):
        r = DialogueResult.continue_normally("Hello.")
        assert "Continue" in str(r)

    def test_default_slot_fields_none(self):
        r = DialogueResult.continue_normally("Hello.")
        assert r.slot_name is None
        assert r.slot_value is None
        assert r.pending_question is None

    def test_default_is_acknowledgement_false(self):
        assert not DialogueResult.continue_normally("Hello.").is_acknowledgement

    def test_slot_fields_populated(self):
        r = DialogueResult(
            dialogue_type=DialogueType.ANSWER_PENDING,
            original_input="Blue.",
            slot_name="colour",
            slot_value="Blue",
            pending_question="What colour?",
            confidence=0.90,
        )
        assert r.slot_name == "colour"
        assert r.slot_value == "Blue"
        assert r.pending_question == "What colour?"


# ===========================================================================
# 3. IS_ACKNOWLEDGEMENT
# ===========================================================================

class TestIsAcknowledgement:

    def setup_method(self):
        self.m = make_manager()

    def test_ok(self):         assert self.m.is_acknowledgement("ok")
    def test_okay(self):       assert self.m.is_acknowledgement("okay")
    def test_sure(self):       assert self.m.is_acknowledgement("sure")
    def test_yes(self):        assert self.m.is_acknowledgement("yes")
    def test_yeah(self):       assert self.m.is_acknowledgement("yeah")
    def test_no(self):         assert self.m.is_acknowledgement("no")
    def test_nope(self):       assert self.m.is_acknowledgement("nope")
    def test_got_it(self):     assert self.m.is_acknowledgement("got it")
    def test_understood(self): assert self.m.is_acknowledgement("understood")
    def test_alright(self):    assert self.m.is_acknowledgement("alright")
    def test_noted(self):      assert self.m.is_acknowledgement("noted")
    def test_thanks(self):     assert self.m.is_acknowledgement("thanks")
    def test_thank_you(self):  assert self.m.is_acknowledgement("thank you")
    def test_correct(self):    assert self.m.is_acknowledgement("correct")
    def test_agreed(self):     assert self.m.is_acknowledgement("agreed")
    def test_perfect(self):    assert self.m.is_acknowledgement("perfect")

    def test_case_insensitive_ok(self):   assert self.m.is_acknowledgement("OK")
    def test_case_insensitive_yes(self):  assert self.m.is_acknowledgement("YES")
    def test_ok_with_period(self):        assert self.m.is_acknowledgement("ok.")
    def test_yes_with_exclamation(self):  assert self.m.is_acknowledgement("yes!")

    def test_not_ack_hello(self):
        assert not self.m.is_acknowledgement("Hello Jarvis.")

    def test_not_ack_sentence(self):
        assert not self.m.is_acknowledgement("Yes, I would like to fix the bug.")

    def test_not_ack_empty(self):
        assert not self.m.is_acknowledgement("")

    def test_not_ack_whitespace(self):
        assert not self.m.is_acknowledgement("   ")

    def test_not_ack_question(self):
        assert not self.m.is_acknowledgement("What is the plan?")


# ===========================================================================
# 4. HAS_TOPIC_CHANGE
# ===========================================================================

class TestHasTopicChange:

    def setup_method(self):
        self.m = make_manager()

    def test_actually(self):
        assert self.m.has_topic_change("Actually, let's do something else.")

    def test_never_mind(self):
        assert self.m.has_topic_change("Never mind, forget that.")

    def test_forget_it(self):
        assert self.m.has_topic_change("Forget it.")

    def test_different_question(self):
        assert self.m.has_topic_change("Different question — what is SOLID?")

    def test_by_the_way(self):
        assert self.m.has_topic_change("By the way, what is the Repository Pattern?")

    def test_btw(self):
        assert self.m.has_topic_change("BTW, can you explain that?")

    def test_moving_on(self):
        assert self.m.has_topic_change("Moving on — what should we do next?")

    def test_normal_input_no_change(self):
        assert not self.m.has_topic_change("Fix the login bug.")

    def test_empty_no_change(self):
        assert not self.m.has_topic_change("")

    def test_question_no_change(self):
        assert not self.m.has_topic_change("What is the Repository Pattern?")


# ===========================================================================
# 5. ANALYSE — ANSWER_PENDING
# ===========================================================================

class TestAnalyseAnswerPending:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_answers_pending_question(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.dialogue_type == DialogueType.ANSWER_PENDING

    def test_slot_name_populated(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.slot_name == "colour"

    def test_slot_value_extracted(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.slot_value == "Blue"

    def test_pending_question_preserved(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.pending_question == "What colour?"

    def test_confidence_is_high(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.confidence == 0.90

    def test_original_input_preserved(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Blue please.", s, self.p)
        assert result.original_input == "Blue please."

    def test_filler_phrase_stripped(self):
        s = state_with_pending("name", "What is your name?")
        result = self.m.analyse("My name is Claude.", s, self.p)
        assert result.slot_value == "Claude"

    def test_it_is_stripped(self):
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("It's blue.", s, self.p)
        assert result.slot_value == "blue"

    def test_expired_pending_no_answer(self):
        from datetime import UTC, datetime, timedelta
        s = ConversationState()
        expired = Slot(
            name="colour", question="What colour?",
            asked_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        s._pending = expired
        # has_pending() auto-clears expired — so this is CONTINUE or NEW_CONVERSATION
        result = self.m.analyse("Blue.", s, self.p)
        assert result.dialogue_type != DialogueType.ANSWER_PENDING


# ===========================================================================
# 6. ANALYSE — FILL_SLOT
# ===========================================================================

class TestAnalyseFillSlot:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_single_active_slot_filled(self):
        s = state_with_slot("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.dialogue_type == DialogueType.FILL_SLOT

    def test_single_slot_name_populated(self):
        s = state_with_slot("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.slot_name == "colour"

    def test_single_slot_value_populated(self):
        s = state_with_slot("colour", "What colour?")
        result = self.m.analyse("Blue.", s, self.p)
        assert result.slot_value is not None
        assert len(result.slot_value) > 0

    def test_multiple_slots_name_match(self):
        s = make_state()
        s.add_slot(Slot(name="colour", question="What colour?"))
        s.add_slot(Slot(name="size", question="What size?"))
        result = self.m.analyse("The colour is red.", s, self.p)
        assert result.dialogue_type == DialogueType.FILL_SLOT
        assert result.slot_name == "colour"

    def test_multiple_slots_no_match_continues(self):
        s = make_state()
        s.add_slot(Slot(name="colour", question="What colour?"))
        s.add_slot(Slot(name="size", question="What size?"))
        # Input doesn't match either slot name
        result = self.m.analyse("What about tomorrow?", s, self.p)
        # No match → falls through to CONTINUE
        assert result.dialogue_type in (DialogueType.CONTINUE, DialogueType.NEW_CONVERSATION)


# ===========================================================================
# 7. ANALYSE — ACKNOWLEDGEMENT
# ===========================================================================

class TestAnalyseAcknowledgement:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_ok_is_ack(self):
        s = state_with_context()
        result = self.m.analyse("ok", s, self.p)
        assert result.dialogue_type == DialogueType.ACKNOWLEDGEMENT

    def test_sure_is_ack(self):
        s = make_state()
        result = self.m.analyse("sure", s, self.p)
        assert result.dialogue_type == DialogueType.ACKNOWLEDGEMENT

    def test_got_it_is_ack(self):
        s = make_state()
        result = self.m.analyse("got it", s, self.p)
        assert result.dialogue_type == DialogueType.ACKNOWLEDGEMENT

    def test_ack_has_high_confidence(self):
        result = self.m.analyse("ok", make_state(), self.p)
        assert result.confidence >= 0.90

    def test_ack_flag_set(self):
        result = self.m.analyse("ok.", make_state(), self.p)
        assert result.is_acknowledgement

    def test_ack_detected_before_pending(self):
        """Ack is detected before checking pending state."""
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("ok", s, self.p)
        assert result.dialogue_type == DialogueType.ACKNOWLEDGEMENT

    def test_ack_preserves_original(self):
        result = self.m.analyse("OK.", make_state(), self.p)
        assert result.original_input == "OK."


# ===========================================================================
# 8. ANALYSE — TOPIC_CHANGE
# ===========================================================================

class TestAnalyseTopicChange:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_never_mind_is_topic_change(self):
        s = state_with_context()
        result = self.m.analyse("Never mind, forget that.", s, self.p)
        assert result.dialogue_type == DialogueType.TOPIC_CHANGE

    def test_actually_is_topic_change(self):
        s = make_state()
        result = self.m.analyse("Actually, different question.", s, self.p)
        assert result.dialogue_type == DialogueType.TOPIC_CHANGE

    def test_topic_change_confidence(self):
        s = make_state()
        result = self.m.analyse("Never mind.", s, self.p)
        assert result.confidence == 0.85

    def test_topic_change_detected_before_pending(self):
        """Topic change takes priority over pending questions."""
        s = state_with_pending("colour", "What colour?")
        result = self.m.analyse("Actually, never mind.", s, self.p)
        assert result.dialogue_type == DialogueType.TOPIC_CHANGE


# ===========================================================================
# 9. ANALYSE — NEW_CONVERSATION
# ===========================================================================

class TestAnalyseNewConversation:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_no_context_is_new(self):
        s = make_state()  # completely empty
        result = self.m.analyse("Hello Jarvis.", s, self.p)
        assert result.dialogue_type == DialogueType.NEW_CONVERSATION

    def test_new_conversation_confidence(self):
        s = make_state()
        result = self.m.analyse("Hello.", s, self.p)
        assert result.confidence == 0.70

    def test_with_context_not_new(self):
        s = state_with_context()  # has topic
        result = self.m.analyse("What should we do next?", s, self.p)
        assert result.dialogue_type != DialogueType.NEW_CONVERSATION


# ===========================================================================
# 10. ANALYSE — CONTINUE
# ===========================================================================

class TestAnalyseContinue:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_normal_input_with_context_continues(self):
        s = state_with_context()
        result = self.m.analyse("What should we do next?", s, self.p)
        assert result.dialogue_type == DialogueType.CONTINUE

    def test_continue_confidence_is_one(self):
        s = state_with_context()
        result = self.m.analyse("Tell me more.", s, self.p)
        assert result.confidence == 1.0

    def test_input_with_turns_continues(self):
        from core.conversation.conversation_models import Decision, DecisionType, ConversationTurn
        s = make_state()
        d = Decision(decision_type=DecisionType.ANSWER_DIRECTLY, resolved_input="Hi")
        s.add_turn(ConversationTurn(raw_input="Hi", decision=d))
        result = self.m.analyse("What next?", s, self.p)
        assert result.dialogue_type == DialogueType.CONTINUE


# ===========================================================================
# 11. ANALYSE — UNKNOWN / EDGE CASES
# ===========================================================================

class TestAnalyseEdgeCases:

    def setup_method(self):
        self.m = make_manager()
        self.p = DEFAULT_POLICY

    def test_empty_input_unknown(self):
        result = self.m.analyse("", make_state(), self.p)
        assert result.dialogue_type == DialogueType.UNKNOWN

    def test_whitespace_only_unknown(self):
        result = self.m.analyse("   ", make_state(), self.p)
        assert result.dialogue_type == DialogueType.UNKNOWN

    def test_unknown_has_zero_confidence(self):
        result = self.m.analyse("", make_state(), self.p)
        assert result.confidence == 0.0

    def test_original_input_always_preserved(self):
        s = make_state()
        result = self.m.analyse("Fix the bug.", s, self.p)
        assert result.original_input == "Fix the bug."

    def test_state_not_modified(self):
        s = state_with_pending("colour", "What colour?")
        original_pending = s.pending_slot.name
        self.m.analyse("Blue.", s, self.p)
        assert s.pending_slot.name == original_pending  # unchanged

    def test_very_long_input(self):
        s = state_with_context()
        long = "Please " + "really " * 100 + "help me."
        result = self.m.analyse(long, s, self.p)
        assert result.original_input == long

    def test_punctuation_only(self):
        result = self.m.analyse("...", make_state(), self.p)
        # Not an ack, not a topic change — falls through
        assert result.dialogue_type in (
            DialogueType.CONTINUE,
            DialogueType.NEW_CONVERSATION,
            DialogueType.UNKNOWN,
        )


# ===========================================================================
# 12. SLOT VALUE EXTRACTION
# ===========================================================================

class TestSlotValueExtraction:

    def setup_method(self):
        self.m = make_manager()

    def _extract(self, text):
        return self.m._extract_slot_value(text)

    def test_plain_value(self):
        assert self._extract("Blue") == "Blue"

    def test_my_name_is_stripped(self):
        assert self._extract("My name is Claude") == "Claude"

    def test_its_stripped(self):
        assert self._extract("It's blue") == "blue"

    def test_it_is_stripped(self):
        assert self._extract("It is blue") == "blue"

    def test_im_stripped(self):
        assert self._extract("I'm Claude") == "Claude"

    def test_trailing_punctuation_removed(self):
        assert self._extract("Blue.") == "Blue"

    def test_preserves_multi_word(self):
        result = self._extract("Visual Studio Code")
        assert "Visual Studio Code" in result

    def test_empty_falls_back(self):
        result = self._extract("")
        assert result == ""


# ===========================================================================
# 13. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_genesis_020_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_sprint001_models_unchanged(self):
        from core.conversation.conversation_models import DecisionType, Decision
        d = Decision(
            decision_type=DecisionType.INVOKE_WORKER,
            resolved_input="Plan it.",
        )
        assert d.decision_type == DecisionType.INVOKE_WORKER

    def test_sprint003_resolver_unchanged(self):
        from core.conversation.conversation_resolver import ReferenceResolver
        from core.conversation.conversation_state import ConversationState
        from core.conversation.conversation_policy import ConversationPolicy
        s = ConversationState()
        s.update_reference(current_it="Visual Studio")
        r = ReferenceResolver()
        result = r.resolve("Close it.", s, ConversationPolicy())
        assert result.resolved

    def test_dialogue_manager_importable(self):
        from core.conversation.conversation_dialogue import (
            DialogueManager, DialogueResult, DialogueType,
        )
        assert DialogueManager is not None