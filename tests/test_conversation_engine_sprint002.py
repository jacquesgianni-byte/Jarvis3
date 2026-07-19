"""
Genesis-022 Sprint-002 — Conversation State & Policy Tests
Completely self-contained. No dependency on other test files.

Coverage:
  ConversationState:
    - creation and default values
    - topic: set, clear, push, pop, history
    - mode: set, is_mode
    - pending: set, clear, has_pending, auto-clear on expiry
    - slots: add, fill, get, active_slots, filled_slots, clear
    - turn history: add, recent_turns, last_turn, cap behaviour
    - reference context: update, clear, summary
    - metadata: set, get, has
    - reset behaviour
    - summary dict
    - edge cases

  ConversationMode:
    - all modes exist, labels correct

  ReferenceContext:
    - update, clear, summary

  ConversationPolicy:
    - default thresholds
    - configurable thresholds
    - should_resolve()
    - is_ambiguous()
    - requires_clarification()
    - requires_confirmation()
    - is_topic_stale()
    - classify_confidence()
    - best_of()
    - snapshot() / summary()
    - validation: out-of-range values raise
    - validation: logical ordering enforced
    - validation: wrong types raise

  PolicyThresholds:
    - frozen dataclass

  Backwards compatibility
"""

import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_state import (
    ConversationState, ConversationMode, ReferenceContext,
)
from core.conversation.conversation_policy import (
    ConversationPolicy, PolicyThresholds,
)
from core.conversation.conversation_models import (
    Decision, DecisionType, Slot, SlotStatus, Topic, ConversationTurn,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(max_turns=20) -> ConversationState:
    return ConversationState(max_turns=max_turns)


def make_policy(**kwargs) -> ConversationPolicy:
    return ConversationPolicy(**kwargs)


def make_slot(name="colour", question="What colour?", ttl=300) -> Slot:
    return Slot(name=name, question=question, ttl_seconds=ttl)


def make_topic(name="planning") -> Topic:
    return Topic(name=name)


def make_decision(dt=DecisionType.ANSWER_DIRECTLY) -> Decision:
    return Decision(decision_type=dt, resolved_input="Hello.")


def make_turn(raw="Hello.", dt=DecisionType.ANSWER_DIRECTLY) -> ConversationTurn:
    return ConversationTurn(raw_input=raw, decision=make_decision(dt))


# ===========================================================================
# 1. CONVERSATION MODE
# ===========================================================================

class TestConversationMode:

    def test_all_modes_exist(self):
        for name in ["NORMAL", "AWAITING_ANSWER", "RECOVERING", "CONFIRMING"]:
            assert hasattr(ConversationMode, name)

    def test_labels(self):
        assert ConversationMode.NORMAL.label() == "Normal"
        assert ConversationMode.AWAITING_ANSWER.label() == "Awaiting Answer"
        assert ConversationMode.RECOVERING.label() == "Recovering"
        assert ConversationMode.CONFIRMING.label() == "Confirming"

    def test_values_unique(self):
        values = [m.value for m in ConversationMode]
        assert len(values) == len(set(values))


# ===========================================================================
# 2. REFERENCE CONTEXT
# ===========================================================================

class TestReferenceContext:

    def test_defaults_all_none(self):
        rc = ReferenceContext()
        assert rc.current_it is None
        assert rc.current_person is None
        assert rc.current_project is None
        assert rc.current_task is None
        assert rc.last_entity is None

    def test_update_single_field(self):
        rc = ReferenceContext()
        rc.update(current_person="Claude")
        assert rc.current_person == "Claude"

    def test_update_multiple_fields(self):
        rc = ReferenceContext()
        rc.update(current_it="the bug", current_person="Claude")
        assert rc.current_it == "the bug"
        assert rc.current_person == "Claude"

    def test_update_ignores_unknown_fields(self):
        rc = ReferenceContext()
        rc.update(nonexistent_field="value")  # should not raise

    def test_clear_resets_all(self):
        rc = ReferenceContext()
        rc.update(current_person="Claude", current_it="the plan")
        rc.clear()
        assert rc.current_person is None
        assert rc.current_it is None

    def test_summary_dict(self):
        rc = ReferenceContext()
        rc.update(current_person="Claude")
        s = rc.summary()
        assert isinstance(s, dict)
        assert s["person"] == "Claude"
        assert s["it"] is None


# ===========================================================================
# 3. CONVERSATION STATE — creation and defaults
# ===========================================================================

class TestConversationStateDefaults:

    def test_default_mode_normal(self):
        assert make_state().mode == ConversationMode.NORMAL

    def test_default_topic_none(self):
        assert make_state().current_topic is None

    def test_default_no_pending(self):
        assert not make_state().has_pending()

    def test_default_turn_count_zero(self):
        assert make_state().turn_count == 0

    def test_default_active_slots_empty(self):
        assert make_state().active_slots() == []

    def test_default_filled_slots_empty(self):
        assert make_state().filled_slots() == []

    def test_default_last_turn_none(self):
        assert make_state().last_turn() is None

    def test_default_topic_history_empty(self):
        assert make_state().topic_history == []

    def test_has_created_at(self):
        assert isinstance(make_state().created_at, datetime)

    def test_has_last_updated(self):
        assert isinstance(make_state().last_updated, datetime)


# ===========================================================================
# 4. CONVERSATION STATE — topic management
# ===========================================================================

class TestConversationStateTopic:

    def test_set_topic(self):
        s = make_state()
        t = make_topic("planning")
        s.set_topic(t)
        assert s.current_topic is t

    def test_clear_topic(self):
        s = make_state()
        s.set_topic(make_topic())
        s.clear_topic()
        assert s.current_topic is None

    def test_push_topic_saves_current(self):
        s = make_state()
        t1 = make_topic("planning")
        t2 = make_topic("debugging")
        s.set_topic(t1)
        s.push_topic(t2)
        assert s.current_topic is t2
        assert len(s.topic_history) == 1
        assert s.topic_history[0] is t1

    def test_push_topic_with_no_current(self):
        s = make_state()
        t = make_topic("planning")
        s.push_topic(t)
        assert s.current_topic is t
        assert s.topic_history == []

    def test_pop_topic_restores_previous(self):
        s = make_state()
        t1 = make_topic("planning")
        t2 = make_topic("debugging")
        s.set_topic(t1)
        s.push_topic(t2)
        restored = s.pop_topic()
        assert restored is t1
        assert s.current_topic is t1

    def test_pop_topic_empty_history_returns_none(self):
        s = make_state()
        result = s.pop_topic()
        assert result is None
        assert s.current_topic is None

    def test_topic_history_is_copy(self):
        s = make_state()
        s.set_topic(make_topic("t1"))
        s.push_topic(make_topic("t2"))
        history = s.topic_history
        history.clear()
        assert len(s.topic_history) == 1  # original unaffected

    def test_multiple_pushes_and_pops(self):
        s = make_state()
        topics = [make_topic(f"t{i}") for i in range(3)]
        for t in topics:
            s.push_topic(t)
        assert s.current_topic is topics[2]
        s.pop_topic()
        assert s.current_topic is topics[1]


# ===========================================================================
# 5. CONVERSATION STATE — mode management
# ===========================================================================

class TestConversationStateMode:

    def test_set_mode(self):
        s = make_state()
        s.set_mode(ConversationMode.CONFIRMING)
        assert s.mode == ConversationMode.CONFIRMING

    def test_is_mode_true(self):
        s = make_state()
        assert s.is_mode(ConversationMode.NORMAL)

    def test_is_mode_false(self):
        s = make_state()
        assert not s.is_mode(ConversationMode.RECOVERING)

    def test_set_pending_changes_mode(self):
        s = make_state()
        s.set_pending(make_slot())
        assert s.mode == ConversationMode.AWAITING_ANSWER

    def test_clear_pending_restores_normal(self):
        s = make_state()
        s.set_pending(make_slot())
        s.clear_pending()
        assert s.mode == ConversationMode.NORMAL

    def test_clear_pending_keeps_non_awaiting_mode(self):
        s = make_state()
        s.set_mode(ConversationMode.CONFIRMING)
        s.clear_pending()
        assert s.mode == ConversationMode.CONFIRMING


# ===========================================================================
# 6. CONVERSATION STATE — pending question
# ===========================================================================

class TestConversationStatePending:

    def test_set_pending(self):
        s = make_state()
        slot = make_slot("colour")
        s.set_pending(slot)
        assert s.has_pending()

    def test_pending_slot_property(self):
        s = make_state()
        slot = make_slot("colour")
        s.set_pending(slot)
        assert s.pending_slot is slot

    def test_clear_pending(self):
        s = make_state()
        s.set_pending(make_slot())
        s.clear_pending()
        assert not s.has_pending()
        assert s.pending_slot is None

    def test_no_pending_initially(self):
        assert not make_state().has_pending()

    def test_expired_pending_auto_cleared(self):
        s = make_state()
        expired = Slot(
            name="colour", question="q?",
            asked_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        s._pending = expired  # inject directly to bypass mode change
        assert not s.has_pending()
        assert s._pending is None

    def test_zero_ttl_pending_never_expires(self):
        s = make_state()
        slot = Slot(
            name="colour", question="q?",
            asked_at=datetime.now(UTC) - timedelta(days=1),
            ttl_seconds=0,
        )
        s.set_pending(slot)
        assert s.has_pending()

    def test_replace_pending(self):
        s = make_state()
        s.set_pending(make_slot("colour"))
        s.set_pending(make_slot("name"))
        assert s.pending_slot.name == "name"


# ===========================================================================
# 7. CONVERSATION STATE — slot management
# ===========================================================================

class TestConversationStateSlots:

    def test_add_slot(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        assert s.get_slot("colour") is not None

    def test_get_slot_missing_returns_none(self):
        assert make_state().get_slot("nonexistent") is None

    def test_fill_slot(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        filled = s.fill_slot("colour", "Blue")
        assert filled.status == SlotStatus.FILLED
        assert filled.value == "Blue"

    def test_fill_slot_updates_stored_slot(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        s.fill_slot("colour", "Blue")
        assert s.get_slot("colour").status == SlotStatus.FILLED

    def test_fill_slot_missing_raises(self):
        s = make_state()
        with pytest.raises(KeyError):
            s.fill_slot("nonexistent", "value")

    def test_active_slots_excludes_filled(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        s.add_slot(make_slot("name"))
        s.fill_slot("colour", "Blue")
        active = s.active_slots()
        assert len(active) == 1
        assert active[0].name == "name"

    def test_filled_slots(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        s.add_slot(make_slot("name"))
        s.fill_slot("colour", "Blue")
        filled = s.filled_slots()
        assert len(filled) == 1
        assert filled[0].name == "colour"

    def test_all_slots(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        s.add_slot(make_slot("name"))
        assert len(s.all_slots()) == 2

    def test_add_slot_replaces_existing(self):
        s = make_state()
        s.add_slot(Slot(name="colour", question="Old?"))
        s.add_slot(Slot(name="colour", question="New?"))
        assert s.get_slot("colour").question == "New?"

    def test_clear_slots(self):
        s = make_state()
        s.add_slot(make_slot("colour"))
        s.clear_slots()
        assert s.all_slots() == []


# ===========================================================================
# 8. CONVERSATION STATE — turn history
# ===========================================================================

class TestConversationStateTurns:

    def test_add_turn(self):
        s = make_state()
        s.add_turn(make_turn("Hello."))
        assert s.turn_count == 1

    def test_last_turn(self):
        s = make_state()
        t = make_turn("Hello.")
        s.add_turn(t)
        assert s.last_turn() is t

    def test_last_turn_none_initially(self):
        assert make_state().last_turn() is None

    def test_recent_turns(self):
        s = make_state()
        for i in range(5):
            s.add_turn(make_turn(f"Turn {i}"))
        recent = s.recent_turns(3)
        assert len(recent) == 3
        assert recent[-1].raw_input == "Turn 4"

    def test_recent_turns_returns_all_when_fewer_than_n(self):
        s = make_state()
        s.add_turn(make_turn("Only one."))
        assert len(s.recent_turns(10)) == 1

    def test_turn_history_capped_at_max(self):
        s = make_state(max_turns=3)
        for i in range(5):
            s.add_turn(make_turn(f"Turn {i}"))
        # Only 3 stored but count reflects all 5
        assert len(s.recent_turns(10)) == 3
        assert s.turn_count == 5

    def test_oldest_turn_removed_when_cap_reached(self):
        s = make_state(max_turns=3)
        for i in range(4):
            s.add_turn(make_turn(f"Turn {i}"))
        turns = s.recent_turns(10)
        assert turns[0].raw_input == "Turn 1"  # Turn 0 evicted


# ===========================================================================
# 9. CONVERSATION STATE — reference context
# ===========================================================================

class TestConversationStateReferences:

    def test_update_reference(self):
        s = make_state()
        s.update_reference(current_person="Claude")
        assert s.references.current_person == "Claude"

    def test_clear_references(self):
        s = make_state()
        s.update_reference(current_person="Claude", current_it="the plan")
        s.clear_references()
        assert s.references.current_person is None
        assert s.references.current_it is None

    def test_references_property(self):
        s = make_state()
        assert isinstance(s.references, ReferenceContext)

    def test_multiple_reference_updates(self):
        s = make_state()
        s.update_reference(current_person="Claude")
        s.update_reference(current_person="GPT")
        assert s.references.current_person == "GPT"


# ===========================================================================
# 10. CONVERSATION STATE — metadata
# ===========================================================================

class TestConversationStateMetadata:

    def test_set_and_get_metadata(self):
        s = make_state()
        s.set_metadata("session_id", "abc-123")
        assert s.get_metadata("session_id") == "abc-123"

    def test_get_metadata_default(self):
        s = make_state()
        assert s.get_metadata("missing", default="fallback") == "fallback"

    def test_get_metadata_none_default(self):
        assert make_state().get_metadata("missing") is None

    def test_has_metadata_true(self):
        s = make_state()
        s.set_metadata("key", "value")
        assert s.has_metadata("key")

    def test_has_metadata_false(self):
        assert not make_state().has_metadata("nonexistent")


# ===========================================================================
# 11. CONVERSATION STATE — reset
# ===========================================================================

class TestConversationStateReset:

    def test_reset_clears_topic(self):
        s = make_state()
        s.set_topic(make_topic())
        s.reset()
        assert s.current_topic is None

    def test_reset_clears_pending(self):
        s = make_state()
        s.set_pending(make_slot())
        s.reset()
        assert not s.has_pending()

    def test_reset_clears_slots(self):
        s = make_state()
        s.add_slot(make_slot())
        s.reset()
        assert s.all_slots() == []

    def test_reset_clears_turns(self):
        s = make_state()
        s.add_turn(make_turn())
        s.reset()
        assert s.last_turn() is None

    def test_reset_clears_references(self):
        s = make_state()
        s.update_reference(current_person="Claude")
        s.reset()
        assert s.references.current_person is None

    def test_reset_restores_mode_normal(self):
        s = make_state()
        s.set_mode(ConversationMode.CONFIRMING)
        s.reset()
        assert s.mode == ConversationMode.NORMAL

    def test_reset_clears_metadata(self):
        s = make_state()
        s.set_metadata("key", "value")
        s.reset()
        assert not s.has_metadata("key")

    def test_reset_preserves_turn_count(self):
        s = make_state()
        s.add_turn(make_turn())
        s.add_turn(make_turn())
        s.reset()
        assert s.turn_count == 2  # count preserved, history cleared

    def test_reset_preserves_created_at(self):
        s = make_state()
        created = s.created_at
        s.reset()
        assert s.created_at == created


# ===========================================================================
# 12. CONVERSATION STATE — summary and repr
# ===========================================================================

class TestConversationStateSummary:

    def test_summary_is_dict(self):
        assert isinstance(make_state().summary(), dict)

    def test_summary_has_mode(self):
        s = make_state()
        assert "mode" in s.summary()
        assert s.summary()["mode"] == "Normal"

    def test_summary_has_turn_count(self):
        s = make_state()
        s.add_turn(make_turn())
        assert s.summary()["turn_count"] == 1

    def test_summary_has_pending(self):
        s = make_state()
        s.set_pending(make_slot("colour"))
        assert s.summary()["has_pending"] is True
        assert s.summary()["pending_slot"] == "colour"

    def test_summary_has_topic(self):
        s = make_state()
        s.set_topic(make_topic("planning"))
        assert s.summary()["current_topic"] == "planning"

    def test_repr_includes_mode(self):
        s = make_state()
        assert "Normal" in repr(s)


# ===========================================================================
# 13. CONVERSATION POLICY — defaults
# ===========================================================================

class TestConversationPolicyDefaults:

    def test_default_resolution_threshold(self):
        assert make_policy().resolution_threshold == 0.75

    def test_default_ambiguity_threshold(self):
        assert make_policy().ambiguity_threshold == 0.60

    def test_default_clarification_threshold(self):
        assert make_policy().clarification_threshold == 0.50

    def test_default_confirmation_threshold(self):
        assert make_policy().confirmation_threshold == 0.85

    def test_default_max_topic_turns(self):
        assert make_policy().max_topic_turns == 10

    def test_default_slot_ttl(self):
        assert make_policy().default_slot_ttl == 300

    def test_default_max_turn_history(self):
        assert make_policy().max_turn_history == 20


# ===========================================================================
# 14. CONVERSATION POLICY — should_resolve
# ===========================================================================

class TestConversationPolicyShouldResolve:

    def test_above_threshold_resolves(self):
        p = make_policy(resolution_threshold=0.75)
        assert p.should_resolve(0.80)
        assert p.should_resolve(0.75)  # exact threshold

    def test_below_threshold_no_resolve(self):
        p = make_policy(resolution_threshold=0.75)
        assert not p.should_resolve(0.74)
        assert not p.should_resolve(0.0)

    def test_full_confidence_resolves(self):
        assert make_policy().should_resolve(1.0)

    def test_zero_confidence_no_resolve(self):
        assert not make_policy().should_resolve(0.0)


# ===========================================================================
# 15. CONVERSATION POLICY — is_ambiguous
# ===========================================================================

class TestConversationPolicyAmbiguity:

    def test_below_threshold_is_ambiguous(self):
        p = make_policy(ambiguity_threshold=0.60)
        assert p.is_ambiguous(0.59)
        assert p.is_ambiguous(0.0)

    def test_at_threshold_not_ambiguous(self):
        p = make_policy(ambiguity_threshold=0.60)
        assert not p.is_ambiguous(0.60)

    def test_above_threshold_not_ambiguous(self):
        p = make_policy(ambiguity_threshold=0.60)
        assert not p.is_ambiguous(0.90)

    def test_full_confidence_not_ambiguous(self):
        assert not make_policy().is_ambiguous(1.0)


# ===========================================================================
# 16. CONVERSATION POLICY — requires_clarification
# ===========================================================================

class TestConversationPolicyClarification:

    def test_below_threshold_requires_clarification(self):
        p = make_policy(clarification_threshold=0.50)
        assert p.requires_clarification(0.49)
        assert p.requires_clarification(0.0)

    def test_at_threshold_no_clarification(self):
        p = make_policy(clarification_threshold=0.50)
        assert not p.requires_clarification(0.50)

    def test_above_threshold_no_clarification(self):
        p = make_policy(clarification_threshold=0.50)
        assert not p.requires_clarification(0.75)


# ===========================================================================
# 17. CONVERSATION POLICY — requires_confirmation
# ===========================================================================

class TestConversationPolicyConfirmation:

    def test_destructive_always_requires_confirmation(self):
        p = make_policy()
        assert p.requires_confirmation(0.1, is_destructive=True)
        assert p.requires_confirmation(1.0, is_destructive=True)

    def test_high_confidence_requires_confirmation(self):
        p = make_policy(confirmation_threshold=0.85)
        assert p.requires_confirmation(0.90)
        assert p.requires_confirmation(0.85)

    def test_low_confidence_no_confirmation(self):
        p = make_policy(confirmation_threshold=0.85)
        assert not p.requires_confirmation(0.84)
        assert not p.requires_confirmation(0.0)

    def test_non_destructive_below_threshold_no_confirmation(self):
        p = make_policy(confirmation_threshold=0.85)
        assert not p.requires_confirmation(0.70, is_destructive=False)


# ===========================================================================
# 18. CONVERSATION POLICY — topic staleness
# ===========================================================================

class TestConversationPolicyTopicStaleness:

    def test_below_max_not_stale(self):
        p = make_policy(max_topic_turns=10)
        assert not p.is_topic_stale(9)
        assert not p.is_topic_stale(0)

    def test_at_max_is_stale(self):
        p = make_policy(max_topic_turns=10)
        assert p.is_topic_stale(10)

    def test_above_max_is_stale(self):
        p = make_policy(max_topic_turns=10)
        assert p.is_topic_stale(15)


# ===========================================================================
# 19. CONVERSATION POLICY — classify_confidence and best_of
# ===========================================================================

class TestConversationPolicyHelpers:

    def test_classify_high(self):
        p = make_policy()
        assert p.classify_confidence(0.90) == "high"
        assert p.classify_confidence(0.85) == "high"

    def test_classify_medium(self):
        p = make_policy()
        assert p.classify_confidence(0.75) == "medium"
        assert p.classify_confidence(0.80) == "medium"

    def test_classify_low(self):
        p = make_policy()
        assert p.classify_confidence(0.50) == "low"
        assert p.classify_confidence(0.60) == "low"

    def test_classify_very_low(self):
        p = make_policy()
        assert p.classify_confidence(0.0) == "very_low"
        assert p.classify_confidence(0.49) == "very_low"

    def test_best_of_returns_max(self):
        p = make_policy()
        assert p.best_of([0.3, 0.9, 0.6]) == 0.9

    def test_best_of_empty_returns_none(self):
        assert make_policy().best_of([]) is None

    def test_best_of_single(self):
        assert make_policy().best_of([0.7]) == 0.7


# ===========================================================================
# 20. CONVERSATION POLICY — validation
# ===========================================================================

class TestConversationPolicyValidation:

    def test_out_of_range_resolution_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(resolution_threshold=1.1)

    def test_negative_resolution_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(resolution_threshold=-0.1)

    def test_out_of_range_ambiguity_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(ambiguity_threshold=1.5)

    def test_wrong_type_resolution_raises(self):
        with pytest.raises(TypeError):
            ConversationPolicy(resolution_threshold="high")

    def test_zero_max_topic_turns_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(max_topic_turns=0)

    def test_negative_slot_ttl_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(default_slot_ttl=-1)

    def test_resolution_below_ambiguity_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(resolution_threshold=0.50, ambiguity_threshold=0.60)

    def test_ambiguity_below_clarification_raises(self):
        with pytest.raises(ValueError):
            ConversationPolicy(ambiguity_threshold=0.40, clarification_threshold=0.50)

    def test_equal_thresholds_allowed(self):
        # resolution == ambiguity == clarification is valid
        p = ConversationPolicy(
            resolution_threshold=0.60,
            ambiguity_threshold=0.60,
            clarification_threshold=0.60,
        )
        assert p.resolution_threshold == 0.60

    def test_non_int_max_topic_turns_raises(self):
        with pytest.raises(TypeError):
            ConversationPolicy(max_topic_turns=5.5)


# ===========================================================================
# 21. POLICY THRESHOLDS — snapshot
# ===========================================================================

class TestPolicyThresholds:

    def test_snapshot_is_frozen(self):
        snap = make_policy().snapshot()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            snap.resolution_threshold = 0.9

    def test_snapshot_matches_policy(self):
        p = make_policy(resolution_threshold=0.80, ambiguity_threshold=0.65)
        snap = p.snapshot()
        assert snap.resolution_threshold == 0.80
        assert snap.ambiguity_threshold == 0.65

    def test_summary_is_dict(self):
        assert isinstance(make_policy().summary(), dict)

    def test_repr_includes_thresholds(self):
        p = make_policy()
        r = repr(p)
        assert "resolution" in r
        assert "ambiguity" in r


# ===========================================================================
# 22. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_conversation_context_unchanged(self):
        from core.conversation.context import ConversationContext
        ctx = ConversationContext()
        ctx.pending_question = "test?"
        assert ctx.has_pending_interaction()

    def test_genesis_020_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_genesis_022_sprint001_models_unchanged(self):
        from core.conversation.conversation_models import DecisionType, Decision
        d = Decision(
            decision_type=DecisionType.INVOKE_WORKER,
            resolved_input="Plan it.",
        )
        assert d.decision_type == DecisionType.INVOKE_WORKER

    def test_new_state_importable(self):
        from core.conversation.conversation_state import ConversationState
        assert ConversationState is not None

    def test_new_policy_importable(self):
        from core.conversation.conversation_policy import ConversationPolicy
        assert ConversationPolicy is not None

    def test_no_collision_with_old_context(self):
        from core.conversation.context import ConversationContext as Old
        from core.conversation.conversation_models import ConversationContext as New
        assert Old is not New