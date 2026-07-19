"""
Genesis-022 Sprint-001 — Conversation Models & Exceptions Tests
Completely self-contained. No dependency on other test files.

Coverage:
  - ConversationError hierarchy
  - DecisionType: all types, labels, is_terminal, requires_dispatch
  - Decision: immutable, fields, str, properties
  - SlotStatus: all statuses, labels
  - Slot: immutable, fill(), expire(), is_expired(), TTL=0
  - Topic: immutable, label default, str
  - ConversationTurn: immutable, fields, str
  - ConversationContext: mutable, defaults, terminate(), metadata
  - ConversationContext: effective_input, summary
  - Architectural rule: only ConversationRouter produces Decision
  - Backwards compatibility
"""

import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_exceptions import (
    ConversationError, InvalidInputError, NoDecisionError,
    SlotError, SlotNotFoundError, SlotAlreadyFilledError,
    TopicError, NoActiveTopicError, PolicyViolationError,
    RecoveryError, PipelineError,
)
from core.conversation.conversation_models import (
    DecisionType, Decision, SlotStatus, Slot, Topic,
    ConversationTurn, ConversationContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_decision(
    decision_type=DecisionType.ANSWER_DIRECTLY,
    resolved_input="Hello.",
    confidence=1.0,
    raw_input="Hello.",
    **kwargs,
) -> Decision:
    return Decision(
        decision_type=decision_type,
        resolved_input=resolved_input,
        confidence=confidence,
        raw_input=raw_input,
        **kwargs,
    )


def make_slot(
    name="favourite_colour",
    question="What is your favourite colour?",
    ttl_seconds=300,
    **kwargs,
) -> Slot:
    return Slot(name=name, question=question, ttl_seconds=ttl_seconds, **kwargs)


def make_topic(name="repository_analysis", **kwargs) -> Topic:
    return Topic(name=name, **kwargs)


def make_context(raw_input="Hello.", state=None, **kwargs) -> ConversationContext:
    return ConversationContext(raw_input=raw_input, state=state or {}, **kwargs)


# ===========================================================================
# 1. EXCEPTION HIERARCHY
# ===========================================================================

class TestExceptionHierarchy:

    def test_all_inherit_from_conversation_error(self):
        for exc_class in [
            InvalidInputError, NoDecisionError,
            SlotError, SlotNotFoundError, SlotAlreadyFilledError,
            TopicError, NoActiveTopicError,
            PolicyViolationError, RecoveryError, PipelineError,
        ]:
            assert issubclass(exc_class, ConversationError)

    def test_slot_errors_inherit_from_slot_error(self):
        assert issubclass(SlotNotFoundError, SlotError)
        assert issubclass(SlotAlreadyFilledError, SlotError)

    def test_topic_errors_inherit_from_topic_error(self):
        assert issubclass(NoActiveTopicError, TopicError)

    def test_catch_by_base_class(self):
        with pytest.raises(ConversationError):
            raise InvalidInputError("empty input")

    def test_all_are_exceptions(self):
        for exc_class in [
            ConversationError, InvalidInputError, NoDecisionError,
            SlotNotFoundError, SlotAlreadyFilledError, NoActiveTopicError,
            PolicyViolationError, RecoveryError, PipelineError,
        ]:
            with pytest.raises(exc_class):
                raise exc_class("test")


# ===========================================================================
# 2. DECISION TYPE
# ===========================================================================

class TestDecisionType:

    def test_all_types_exist(self):
        for name in [
            "ANSWER_DIRECTLY", "ASK_FOLLOW_UP", "INVOKE_MEMORY",
            "INVOKE_TOOL", "INVOKE_WORKER", "AI_FALLBACK",
            "SLOT_FILLED", "RECOVERY",
        ]:
            assert hasattr(DecisionType, name)

    def test_values_unique(self):
        values = [d.value for d in DecisionType]
        assert len(values) == len(set(values))

    def test_labels_human_readable(self):
        assert DecisionType.ANSWER_DIRECTLY.label() == "Answer Directly"
        assert DecisionType.INVOKE_WORKER.label() == "Invoke Worker"
        assert DecisionType.AI_FALLBACK.label() == "Ai Fallback"
        assert DecisionType.SLOT_FILLED.label() == "Slot Filled"

    def test_is_terminal_recovery(self):
        assert DecisionType.RECOVERY.is_terminal

    def test_is_terminal_slot_filled(self):
        assert DecisionType.SLOT_FILLED.is_terminal

    def test_is_not_terminal_others(self):
        for dt in [
            DecisionType.ANSWER_DIRECTLY, DecisionType.ASK_FOLLOW_UP,
            DecisionType.INVOKE_MEMORY, DecisionType.INVOKE_TOOL,
            DecisionType.INVOKE_WORKER, DecisionType.AI_FALLBACK,
        ]:
            assert not dt.is_terminal

    def test_requires_dispatch_invoke_types(self):
        for dt in [
            DecisionType.INVOKE_MEMORY, DecisionType.INVOKE_TOOL,
            DecisionType.INVOKE_WORKER, DecisionType.AI_FALLBACK,
        ]:
            assert dt.requires_dispatch

    def test_does_not_require_dispatch_others(self):
        for dt in [
            DecisionType.ANSWER_DIRECTLY, DecisionType.ASK_FOLLOW_UP,
            DecisionType.SLOT_FILLED, DecisionType.RECOVERY,
        ]:
            assert not dt.requires_dispatch


# ===========================================================================
# 3. DECISION
# ===========================================================================

class TestDecision:

    def test_is_frozen(self):
        d = make_decision()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            d.confidence = 0.5

    def test_has_timestamp(self):
        d = make_decision()
        assert isinstance(d.produced_at, datetime)

    def test_default_confidence(self):
        d = make_decision()
        assert d.confidence == 1.0

    def test_default_payload_empty(self):
        assert make_decision().payload == {}

    def test_default_context_snapshot_empty(self):
        assert make_decision().context_snapshot == {}

    def test_str_includes_type(self):
        d = make_decision(DecisionType.INVOKE_WORKER)
        assert "Invoke Worker" in str(d)

    def test_str_includes_confidence(self):
        d = make_decision(confidence=0.85)
        assert "0.85" in str(d)

    def test_is_terminal_property(self):
        assert make_decision(DecisionType.RECOVERY).is_terminal
        assert not make_decision(DecisionType.INVOKE_WORKER).is_terminal

    def test_requires_dispatch_property(self):
        assert make_decision(DecisionType.INVOKE_WORKER).requires_dispatch
        assert not make_decision(DecisionType.ANSWER_DIRECTLY).requires_dispatch

    def test_custom_payload(self):
        d = Decision(
            decision_type=DecisionType.INVOKE_WORKER,
            resolved_input="Plan something.",
            payload={"worker": "planning", "task_type": "plan_implementation"},
        )
        assert d.payload["worker"] == "planning"

    def test_raw_input_preserved(self):
        d = make_decision(raw_input="Fix it.", resolved_input="Fix the bug.")
        assert d.raw_input == "Fix it."
        assert d.resolved_input == "Fix the bug."

    def test_two_decisions_independent(self):
        d1 = make_decision(DecisionType.INVOKE_MEMORY)
        d2 = make_decision(DecisionType.AI_FALLBACK)
        assert d1.decision_type != d2.decision_type


# ===========================================================================
# 4. SLOT STATUS
# ===========================================================================

class TestSlotStatus:

    def test_all_statuses_exist(self):
        for name in ["EMPTY", "FILLED", "EXPIRED"]:
            assert hasattr(SlotStatus, name)

    def test_labels(self):
        assert SlotStatus.EMPTY.label() == "Empty"
        assert SlotStatus.FILLED.label() == "Filled"
        assert SlotStatus.EXPIRED.label() == "Expired"

    def test_values_unique(self):
        values = [s.value for s in SlotStatus]
        assert len(values) == len(set(values))


# ===========================================================================
# 5. SLOT
# ===========================================================================

class TestSlot:

    def test_is_frozen(self):
        s = make_slot()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            s.name = "changed"

    def test_default_status_empty(self):
        assert make_slot().status == SlotStatus.EMPTY

    def test_default_value_none(self):
        assert make_slot().value is None

    def test_default_filled_at_none(self):
        assert make_slot().filled_at is None

    def test_has_timestamp(self):
        assert isinstance(make_slot().asked_at, datetime)

    def test_str_empty_slot(self):
        s = make_slot(name="colour")
        assert "colour" in str(s)
        assert "Empty" in str(s)

    def test_str_filled_slot(self):
        s = make_slot(name="colour").fill("Blue")
        assert "colour" in str(s)
        assert "Blue" in str(s)

    def test_fill_returns_new_instance(self):
        s = make_slot()
        s2 = s.fill("Blue")
        assert s2 is not s
        assert s.status == SlotStatus.EMPTY   # original unchanged
        assert s2.status == SlotStatus.FILLED

    def test_fill_sets_value(self):
        s = make_slot().fill("Blue")
        assert s.value == "Blue"

    def test_fill_sets_filled_at(self):
        s = make_slot().fill("Blue")
        assert s.filled_at is not None

    def test_fill_preserves_name_and_question(self):
        s = make_slot(name="colour", question="What colour?")
        s2 = s.fill("Blue")
        assert s2.name == "colour"
        assert s2.question == "What colour?"

    def test_expire_returns_new_instance(self):
        s = make_slot()
        s2 = s.expire()
        assert s2 is not s
        assert s2.status == SlotStatus.EXPIRED

    def test_expire_clears_value(self):
        s = make_slot()
        s2 = s.expire()
        assert s2.value is None

    def test_not_expired_when_fresh(self):
        assert not make_slot(ttl_seconds=300).is_expired()

    def test_zero_ttl_never_expires(self):
        s = Slot(
            name="s", question="q?",
            asked_at=datetime.now(UTC) - timedelta(days=365),
            ttl_seconds=0,
        )
        assert not s.is_expired()

    def test_expired_after_ttl(self):
        s = Slot(
            name="s", question="q?",
            asked_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
        )
        assert s.is_expired()

    def test_filled_slot_never_expires(self):
        s = Slot(
            name="s", question="q?",
            asked_at=datetime.now(UTC) - timedelta(minutes=10),
            ttl_seconds=60,
            status=SlotStatus.FILLED,
            value="Blue",
        )
        assert not s.is_expired()

    def test_expiry_with_injected_time(self):
        now = datetime.now(UTC)
        s = Slot(name="s", question="q?", asked_at=now, ttl_seconds=60)
        assert s.is_expired(now=now + timedelta(seconds=61))
        assert not s.is_expired(now=now + timedelta(seconds=59))


# ===========================================================================
# 6. TOPIC
# ===========================================================================

class TestTopic:

    def test_is_frozen(self):
        t = make_topic()
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            t.name = "changed"

    def test_has_name(self):
        t = make_topic(name="repository_analysis")
        assert t.name == "repository_analysis"

    def test_default_label_from_name(self):
        t = make_topic(name="repository_analysis")
        assert t.label == "Repository Analysis"

    def test_custom_label(self):
        t = Topic(name="repo", label="Custom Label")
        assert t.label == "Custom Label"

    def test_has_timestamp(self):
        assert isinstance(make_topic().started_at, datetime)

    def test_default_turn_zero(self):
        assert make_topic().turn == 0

    def test_str_includes_name(self):
        t = make_topic(name="planning")
        assert "planning" in str(t)

    def test_default_metadata_empty(self):
        assert make_topic().metadata == {}

    def test_custom_metadata(self):
        t = Topic(name="t", metadata={"key": "value"})
        assert t.metadata["key"] == "value"


# ===========================================================================
# 7. CONVERSATION TURN
# ===========================================================================

class TestConversationTurn:

    def test_is_frozen(self):
        turn = ConversationTurn(raw_input="Hi", decision=make_decision())
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            turn.raw_input = "changed"

    def test_has_auto_turn_id(self):
        turn = ConversationTurn(raw_input="Hi", decision=make_decision())
        assert turn.turn_id and len(turn.turn_id) > 0

    def test_two_turns_different_ids(self):
        d = make_decision()
        t1 = ConversationTurn(raw_input="Hi", decision=d)
        t2 = ConversationTurn(raw_input="Hi", decision=d)
        assert t1.turn_id != t2.turn_id

    def test_has_timestamp(self):
        turn = ConversationTurn(raw_input="Hi", decision=make_decision())
        assert isinstance(turn.timestamp, datetime)

    def test_default_topic_none(self):
        turn = ConversationTurn(raw_input="Hi", decision=make_decision())
        assert turn.topic is None

    def test_str_includes_input(self):
        turn = ConversationTurn(raw_input="Hello Jarvis", decision=make_decision())
        assert "Hello Jarvis" in str(turn)

    def test_str_includes_decision_type(self):
        turn = ConversationTurn(
            raw_input="Hi",
            decision=make_decision(DecisionType.INVOKE_WORKER)
        )
        assert "Invoke Worker" in str(turn)

    def test_with_topic(self):
        topic = make_topic(name="planning")
        turn = ConversationTurn(
            raw_input="Plan something.",
            decision=make_decision(),
            topic=topic,
        )
        assert turn.topic.name == "planning"


# ===========================================================================
# 8. CONVERSATION CONTEXT (mutable pipeline bag)
# ===========================================================================

class TestConversationContext:

    def test_resolved_input_defaults_to_raw(self):
        ctx = make_context(raw_input="Hello.")
        assert ctx.resolved_input == "Hello."

    def test_resolved_input_override(self):
        ctx = ConversationContext(
            raw_input="Fix it.",
            state={},
            resolved_input="Fix the bug.",
        )
        assert ctx.resolved_input == "Fix the bug."
        assert ctx.raw_input == "Fix it."

    def test_effective_input_returns_resolved(self):
        ctx = ConversationContext(
            raw_input="Fix it.", state={}, resolved_input="Fix the bug."
        )
        assert ctx.effective_input() == "Fix the bug."

    def test_effective_input_falls_back_to_raw(self):
        ctx = make_context(raw_input="Hello.")
        ctx.resolved_input = ""
        assert ctx.effective_input() == "Hello."

    def test_default_decision_none(self):
        assert make_context().decision is None

    def test_default_is_terminal_false(self):
        assert not make_context().is_terminal

    def test_default_metadata_empty(self):
        assert make_context().metadata == {}

    def test_has_timestamp(self):
        assert isinstance(make_context().created_at, datetime)

    def test_terminate_sets_decision(self):
        ctx = make_context()
        d = make_decision(DecisionType.RECOVERY)
        ctx.terminate(d)
        assert ctx.decision is d

    def test_terminate_sets_is_terminal(self):
        ctx = make_context()
        ctx.terminate(make_decision(DecisionType.RECOVERY))
        assert ctx.is_terminal

    def test_set_metadata(self):
        ctx = make_context()
        ctx.set_metadata("resolution_confidence", 0.9)
        assert ctx.metadata["resolution_confidence"] == 0.9

    def test_get_metadata(self):
        ctx = make_context()
        ctx.set_metadata("key", "value")
        assert ctx.get_metadata("key") == "value"

    def test_get_metadata_default(self):
        ctx = make_context()
        assert ctx.get_metadata("missing", default="fallback") == "fallback"

    def test_get_metadata_none_default(self):
        ctx = make_context()
        assert ctx.get_metadata("missing") is None

    def test_summary_dict(self):
        ctx = make_context(raw_input="Hello.")
        s = ctx.summary()
        assert isinstance(s, dict)
        assert s["raw_input"] == "Hello."
        assert not s["is_terminal"]
        assert s["decision"] is None

    def test_summary_after_terminate(self):
        ctx = make_context()
        ctx.terminate(make_decision(DecisionType.RECOVERY))
        s = ctx.summary()
        assert s["is_terminal"]
        assert "Recovery" in s["decision"]

    def test_raw_input_never_changed_by_stages(self):
        """Architectural invariant: raw_input is sacred."""
        ctx = make_context(raw_input="Fix it.")
        ctx.resolved_input = "Fix the Repository Pattern."
        assert ctx.raw_input == "Fix it."  # unchanged

    def test_context_is_mutable(self):
        """ConversationContext must be mutable (not frozen)."""
        ctx = make_context()
        ctx.resolved_input = "Modified."
        ctx.is_terminal = True
        assert ctx.resolved_input == "Modified."


# ===========================================================================
# 9. ARCHITECTURAL RULE — only ConversationRouter produces Decision
# ===========================================================================

class TestArchitecturalRule:

    def test_decision_constructible_only_with_all_required_fields(self):
        """Decision requires decision_type and resolved_input at minimum."""
        with pytest.raises(TypeError):
            Decision()  # missing required fields

    def test_context_terminate_requires_decision_argument(self):
        """Stages must pass a Decision to terminate() — they can't set None."""
        ctx = make_context()
        with pytest.raises(TypeError):
            ctx.terminate()  # requires decision argument

    def test_stages_should_not_construct_decisions_directly(self):
        """
        Architectural documentation test.
        ConversationContext.terminate() accepts any Decision — enforcement
        of 'only ConversationRouter may call this' is by convention and
        ConversationPolicy (Sprint-002). This test documents the rule.
        """
        # A pipeline stage CAN call terminate() — the Policy prevents abuse.
        # This test simply confirms the rule is documented and understood.
        ctx = make_context()
        d = make_decision(DecisionType.RECOVERY)
        ctx.terminate(d)  # valid when called by the right component
        assert ctx.is_terminal


# ===========================================================================
# 10. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_conversation_context_unchanged(self):
        from core.conversation.context import ConversationContext as OldCtx
        ctx = OldCtx()
        ctx.pending_question = "test?"
        assert ctx.has_pending_interaction()

    def test_existing_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"

    def test_existing_timeline_unchanged(self):
        from core.conversation.conversation_timeline import ConversationTimeline
        from core.conversation.timeline_event import EventType, TimelineEvent
        tl = ConversationTimeline()
        tl.record(TimelineEvent(EventType.START_PROJECT, "Jarvis", turn=1))
        assert tl.count() == 1

    def test_new_models_importable(self):
        from core.conversation.conversation_models import (
            DecisionType, Decision, SlotStatus, Slot,
            Topic, ConversationTurn, ConversationContext,
        )
        assert DecisionType is not None

    def test_new_exceptions_importable(self):
        from core.conversation.conversation_exceptions import (
            ConversationError, InvalidInputError, PolicyViolationError,
        )
        assert ConversationError is not None

    def test_no_naming_collision_with_genesis_020(self):
        """New ConversationContext does not shadow old one."""
        from core.conversation.context import ConversationContext as Old
        from core.conversation.conversation_models import ConversationContext as New
        assert Old is not New