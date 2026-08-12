"""
CFR-006 Regression Tests — Focus Signal Architecture

Tests that the FocusSignalStage produces non-binding evidence and that
ConversationRouter correctly decides whether to authorise a focus change
based on conversational context.

Validates the architectural contract:
    FocusSignalStage → PipelineContext → ConversationRouter → Decision

These tests validate BEHAVIOUR, not implementation details.
No noun-specific exceptions. No word lists tested.
"""

import pytest

from core.conversation.conversation_pipeline import (
    ConversationPipeline, FocusSignal, FocusSignalStage, PipelineContext,
)
from core.conversation.conversation_router import ConversationRouter
from core.conversation.conversation_state import ConversationState
from core.conversation.conversation_policy import ConversationPolicy
from core.conversation.conversation_models import DecisionType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state() -> ConversationState:
    """Fresh ConversationState with no prior context."""
    return ConversationState()


def make_state_with_entity(name: str) -> ConversationState:
    """ConversationState that has seen a named entity in this session."""
    state = ConversationState()
    # mention() is the correct write API for EntityRegistry
    state.entity_registry.mention(name, turn=state.current_turn)
    state.add_recent_entity(name)
    return state


def make_state_with_topic(name: str) -> ConversationState:
    """ConversationState that has an entity in topic history."""
    state = ConversationState()
    state.topic_tracker.set(name=name, confidence=0.85, turn=1, explicit=True)
    state.increment_turn()
    state.increment_turn()
    return state


def run_pipeline(text: str, state: ConversationState = None) -> PipelineContext:
    """Run the full pipeline and return the enriched context."""
    if state is None:
        state = make_state()
    policy = ConversationPolicy()
    pipeline = ConversationPipeline()
    return pipeline.run(text, state, policy)


def route(text: str, state: ConversationState = None) -> DecisionType:
    """Run pipeline + router and return Decision."""
    ctx = run_pipeline(text, state)
    router = ConversationRouter()
    return router.decide(ctx)


# ---------------------------------------------------------------------------
# Group A: FocusSignalStage produces correct evidence (not decisions)
# ---------------------------------------------------------------------------

class TestFocusSignalStageEvidence:
    """FocusSignalStage detects patterns and records them as evidence only."""

    def test_tell_me_about_common_noun_produces_signal_not_state_mutation(self):
        """
        'Tell me about computers' should produce a FocusSignal
        but NOT mutate ConversationState.
        """
        state = make_state()
        ctx = run_pipeline("Tell me about computers", state)

        assert ctx.focus_signal_result is not None
        assert ctx.focus_signal_result.detected is True
        assert ctx.focus_signal_result.candidate.lower() == "computers"

        # Stage must NOT have mutated state
        assert state.active_topic is None
        assert state.active_person is None

    def test_tell_me_about_my_produces_possessive_signal(self):
        """'Tell me about my computers' — possessive group signal."""
        ctx = run_pipeline("Tell me about my computers")
        assert ctx.focus_signal_result is not None
        assert ctx.focus_signal_result.detected is True
        assert ctx.focus_signal_result.is_group is True
        assert ctx.focus_signal_result.possessive is True

    def test_plain_statement_produces_no_signal(self):
        """A plain statement with no focus pattern produces no FocusSignal."""
        ctx = run_pipeline("The weather is nice today")
        sig = ctx.focus_signal_result
        assert sig is None or sig.detected is False

    def test_tell_me_more_produces_no_focus_signal(self):
        """'Tell me more' has no entity to capture — no signal."""
        ctx = run_pipeline("Tell me more")
        sig = ctx.focus_signal_result
        assert sig is None or sig.detected is False

    def test_back_to_hp_produces_return_signal(self):
        """'Back to HP' should produce a signal with is_return=True."""
        ctx = run_pipeline("Back to HP")
        assert ctx.focus_signal_result is not None
        assert ctx.focus_signal_result.detected is True
        assert ctx.focus_signal_result.is_return is True

    def test_incidental_mention_no_focus_signal(self):
        """'I was reading about computers yesterday' — no focus pattern."""
        ctx = run_pipeline("I was reading about computers yesterday")
        sig = ctx.focus_signal_result
        assert sig is None or sig.detected is False

    def test_pipeline_stage_names_include_focus_signal_stage(self):
        """FocusSignalStage must appear in the pipeline stage trace."""
        ctx = run_pipeline("Hello")
        assert "FocusSignalStage" in ctx.stage_names()


# ---------------------------------------------------------------------------
# Group B: Router rejects ungrounded signals
# ---------------------------------------------------------------------------

class TestRouterRejectsUngroundedSignals:
    """Ungrounded focus signals must NOT produce FOCUS_CHANGE decisions."""

    def test_cfr006_tell_me_about_computers_routes_as_information_request(self):
        """
        CFR-006 primary case: 'Tell me about computers' with no prior context.
        Must NOT produce FOCUS_CHANGE.
        """
        decision = route("Tell me about computers")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE, (
            "CFR-006: 'Tell me about computers' must route as information request, "
            f"not FOCUS_CHANGE. Got: {decision.decision_type}"
        )

    def test_what_about_dogs_no_context_not_focus_change(self):
        """'What about dogs?' with no prior context — information request."""
        decision = route("What about dogs?")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_back_to_hp_no_prior_history_not_focus_change(self):
        """'Back to HP' when HP has never been discussed — no valid return."""
        decision = route("Back to HP")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_tell_me_about_history_not_focus_change(self):
        """'Tell me about history' — common noun, no session context."""
        decision = route("Tell me about history")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_what_about_software_not_focus_change(self):
        """'What about software?' — common noun, ungrounded."""
        decision = route("What about software?")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_speaking_of_travel_not_focus_change(self):
        """'Speaking of travel' with no prior travel context."""
        decision = route("Speaking of travel, I went to Japan")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE


# ---------------------------------------------------------------------------
# Group C: Router authorises grounded signals
# ---------------------------------------------------------------------------

class TestRouterAuthorisesGroundedSignals:
    """Grounded focus signals SHOULD produce FOCUS_CHANGE decisions."""

    def test_tell_me_about_my_computers_is_focus_change(self):
        """'Tell me about my computers' — possessive, always grounded."""
        decision = route("Tell me about my computers")
        assert decision.decision_type == DecisionType.FOCUS_CHANGE, (
            f"Expected FOCUS_CHANGE for possessive group, got {decision.decision_type}"
        )
        assert decision.payload.get("is_group") is True

    def test_tell_me_about_lucas_known_entity_is_focus_change(self):
        """'Tell me about Lucas' when Lucas is in EntityRegistry."""
        state = make_state_with_entity("Lucas")
        decision = route("Tell me about Lucas", state)
        assert decision.decision_type == DecisionType.FOCUS_CHANGE, (
            f"Expected FOCUS_CHANGE for known entity Lucas, got {decision.decision_type}"
        )

    def test_back_to_hp_with_prior_history_is_focus_change(self):
        """'Back to HP' when HP is in TopicTracker history."""
        state = make_state_with_topic("HP")
        decision = route("Back to HP", state)
        assert decision.decision_type == DecisionType.FOCUS_CHANGE, (
            f"Expected FOCUS_CHANGE for return to known topic HP, got {decision.decision_type}"
        )

    def test_tell_me_about_my_printers_is_focus_change(self):
        """'Tell me about my printers' — possessive group."""
        decision = route("Tell me about my printers")
        assert decision.decision_type == DecisionType.FOCUS_CHANGE

    def test_what_about_chase_known_entity_is_focus_change(self):
        """'What about Chase?' when Chase is a known entity."""
        state = make_state_with_entity("Chase")
        decision = route("What about Chase?", state)
        assert decision.decision_type == DecisionType.FOCUS_CHANGE

    def test_focus_change_decision_carries_candidate_payload(self):
        """FOCUS_CHANGE decision must carry focus_candidate in payload."""
        state = make_state_with_entity("Lucas")
        decision = route("Tell me about Lucas", state)
        assert decision.decision_type == DecisionType.FOCUS_CHANGE
        assert "focus_candidate" in decision.payload
        assert decision.payload["focus_candidate"].lower() == "lucas"

    def test_focus_change_confidence_is_high(self):
        """FOCUS_CHANGE decision must have confidence above threshold."""
        state = make_state_with_entity("Rex")
        decision = route("Tell me about Rex", state)
        assert decision.decision_type == DecisionType.FOCUS_CHANGE
        assert decision.confidence >= 0.70


# ---------------------------------------------------------------------------
# Group D: Normal routing not affected
# ---------------------------------------------------------------------------

class TestNormalRoutingUnaffected:
    """Non-focus utterances must route normally after CFR-006 changes."""

    def test_tell_me_more_not_focus_change(self):
        """'Tell me more' — no entity, not a focus change."""
        decision = route("Tell me more")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_what_is_it_used_for_not_focus_change(self):
        """'What is it used for?' — pronoun, not focus pattern."""
        state = make_state()
        state.set_person("Python", raw="Python", confidence=0.90)
        decision = route("What is it used for?", state)
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_incidental_mention_not_focus(self):
        """'I use computers every day' — incidental, no focus."""
        decision = route("I use computers every day")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE

    def test_my_friend_knows_history_not_focus(self):
        """'My friend knows a lot about history' — no focus signal."""
        decision = route("My friend knows a lot about history")
        assert decision.decision_type != DecisionType.FOCUS_CHANGE


# ---------------------------------------------------------------------------
# Group E: FocusSignal dataclass integrity
# ---------------------------------------------------------------------------

class TestFocusSignalDataclass:
    """FocusSignal dataclass behaves correctly."""

    def test_not_detected_factory(self):
        sig = FocusSignal.not_detected()
        assert sig.detected is False
        assert sig.candidate == ""
        assert sig.raw_confidence == 0.0

    def test_detected_signal_fields(self):
        sig = FocusSignal(
            detected=True,
            candidate="Lucas",
            pattern="entity",
            is_group=False,
            possessive=False,
            is_return=False,
            raw_confidence=0.92,
        )
        assert sig.detected is True
        assert sig.candidate == "Lucas"
        assert sig.raw_confidence == 0.92
        assert sig.is_group is False

    def test_str_not_detected(self):
        sig = FocusSignal.not_detected()
        assert "not detected" in str(sig)

    def test_str_detected(self):
        sig = FocusSignal(
            detected=True, candidate="HP", pattern="entity",
            is_group=False, possessive=False, is_return=True,
            raw_confidence=0.92,
        )
        s = str(sig)
        assert "HP" in s
        assert "return=True" in s
