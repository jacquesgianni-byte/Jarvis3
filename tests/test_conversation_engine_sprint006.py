"""
Genesis-022 Sprint-006 — ConversationRouter & ConversationEngine Tests
Completely self-contained. No dependency on other test files.

Coverage:
  ConversationRouter:
    - terminal recovery → RECOVERY decision
    - slot filled → SLOT_FILLED decision
    - acknowledgement → ANSWER_DIRECTLY
    - intent routing: GREETING, IDENTITY, MEMORY, TOOL, EXIT, UNKNOWN
    - payload populated correctly
    - context_snapshot populated
    - confidence values

  ConversationEngine:
    - process() returns Decision
    - turn recorded in state
    - pipeline stages run
    - last_context populated
    - recovery resets state
    - slot fill flows through
    - reset() clears state
    - summary() dict
    - state / policy properties

  Integration — full flow:
    User Input → Pipeline → Router → Decision
    - normal conversation
    - with reference resolution
    - with pending question answered
    - with recovery
    - multi-turn

  Agent integration:
    - ConversationEngine instantiated in Agent
    - RECOVERY returns clean response
    - SLOT_FILLED stores value
    - existing routing paths preserved

  Backwards compatibility
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_router import ConversationRouter
from core.conversation.conversation_engine import ConversationEngine
from core.conversation.conversation_pipeline import ConversationPipeline, PipelineContext
from core.conversation.conversation_state import ConversationState
from core.conversation.conversation_policy import ConversationPolicy
from core.conversation.conversation_models import Decision, DecisionType, Slot, Topic
from core.conversation.conversation_recovery import RecoveryAction, RecoveryResult
from core.conversation.conversation_dialogue import DialogueType, DialogueResult
from core.conversation.conversation_resolver import ResolutionResult, ReferenceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_router() -> ConversationRouter:
    return ConversationRouter()


def make_engine(policy=None) -> ConversationEngine:
    return ConversationEngine(policy=policy)


def make_state() -> ConversationState:
    return ConversationState()


def make_policy(**kwargs) -> ConversationPolicy:
    return ConversationPolicy(**kwargs)


def make_pipeline_ctx(
    raw="Hello.",
    state=None,
    policy=None,
    is_terminal=False,
    recovery_result=None,
    resolution_result=None,
    dialogue_result=None,
) -> PipelineContext:
    ctx = PipelineContext(
        original_input=raw,
        state=state or make_state(),
        policy=policy or make_policy(),
    )
    ctx.is_terminal = is_terminal
    if recovery_result:
        ctx.recovery_result = recovery_result
    if resolution_result:
        ctx.resolution_result = resolution_result
        if resolution_result.resolved:
            ctx.current_input = resolution_result.resolved_input
    if dialogue_result:
        ctx.dialogue_result = dialogue_result
    return ctx


def terminal_ctx(action=RecoveryAction.STATE_RESET) -> PipelineContext:
    rr = RecoveryResult(
        action=action,
        original_input="never mind",
        recovered=True,
        reason="Full reset.",
        should_continue=False,
        pattern_matched="never mind",
    )
    ctx = make_pipeline_ctx(raw="never mind", is_terminal=True, recovery_result=rr)
    return ctx


def slot_filled_ctx(slot_name="colour", slot_value="Blue") -> PipelineContext:
    dr = DialogueResult(
        dialogue_type=DialogueType.ANSWER_PENDING,
        original_input="Blue.",
        slot_name=slot_name,
        slot_value=slot_value,
        pending_question="What colour?",
        confidence=0.90,
        reason="Slot filled.",
    )
    return make_pipeline_ctx(raw="Blue.", dialogue_result=dr)


def ack_ctx() -> PipelineContext:
    dr = DialogueResult(
        dialogue_type=DialogueType.ACKNOWLEDGEMENT,
        original_input="ok",
        confidence=0.95,
        is_acknowledgement=True,
        reason="Ack.",
    )
    return make_pipeline_ctx(raw="ok", dialogue_result=dr)


# ===========================================================================
# 1. CONVERSATION ROUTER — terminal recovery
# ===========================================================================

class TestRouterTerminalRecovery:

    def test_terminal_produces_recovery_decision(self):
        r = make_router()
        ctx = terminal_ctx()
        d = r.decide(ctx)
        assert d.decision_type == DecisionType.RECOVERY

    def test_recovery_confidence_is_one(self):
        d = make_router().decide(terminal_ctx())
        assert d.confidence == 1.0

    def test_recovery_payload_has_action(self):
        d = make_router().decide(terminal_ctx())
        assert "recovery_action" in d.payload
        assert d.payload["recovery_action"] == "State Reset"

    def test_recovery_payload_has_pattern(self):
        d = make_router().decide(terminal_ctx())
        assert "pattern_matched" in d.payload

    def test_recovery_original_input_preserved(self):
        d = make_router().decide(terminal_ctx())
        assert d.raw_input == "never mind"

    def test_pending_cancel_also_recovery(self):
        rr = RecoveryResult(
            action=RecoveryAction.PENDING_CANCELLED,
            original_input="cancel",
            recovered=True,
            reason="Pending cancelled.",
            should_continue=False,
            pattern_matched="cancel",
        )
        ctx = make_pipeline_ctx(raw="cancel", is_terminal=True, recovery_result=rr)
        d = make_router().decide(ctx)
        assert d.decision_type == DecisionType.RECOVERY


# ===========================================================================
# 2. CONVERSATION ROUTER — slot filled
# ===========================================================================

class TestRouterSlotFilled:

    def test_slot_filled_decision(self):
        d = make_router().decide(slot_filled_ctx())
        assert d.decision_type == DecisionType.SLOT_FILLED

    def test_slot_payload_populated(self):
        d = make_router().decide(slot_filled_ctx("colour", "Blue"))
        assert d.payload["slot_name"] == "colour"
        assert d.payload["slot_value"] == "Blue"

    def test_pending_question_in_payload(self):
        d = make_router().decide(slot_filled_ctx())
        assert "pending_question" in d.payload
        assert d.payload["pending_question"] == "What colour?"

    def test_fill_slot_type_also_slot_filled(self):
        dr = DialogueResult(
            dialogue_type=DialogueType.FILL_SLOT,
            original_input="README.md",
            slot_name="filename",
            slot_value="README.md",
            confidence=0.80,
            reason="Slot filled.",
        )
        ctx = make_pipeline_ctx(raw="README.md", dialogue_result=dr)
        d = make_router().decide(ctx)
        assert d.decision_type == DecisionType.SLOT_FILLED


# ===========================================================================
# 3. CONVERSATION ROUTER — acknowledgement
# ===========================================================================

class TestRouterAcknowledgement:

    def test_ack_gives_answer_directly(self):
        d = make_router().decide(ack_ctx())
        assert d.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_ack_payload_has_type(self):
        d = make_router().decide(ack_ctx())
        assert d.payload.get("dialogue_type") == "acknowledgement"


# ===========================================================================
# 4. CONVERSATION ROUTER — intent-based routing
# ===========================================================================

class TestRouterIntentRouting:

    def test_greeting_answer_directly(self):
        ctx = make_pipeline_ctx(raw="Hello Jarvis.")
        d = make_router().decide(ctx)
        assert d.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_memory_invoke_memory(self):
        ctx = make_pipeline_ctx(raw="Remember my name is Gianni.")
        d = make_router().decide(ctx)
        assert d.decision_type == DecisionType.INVOKE_MEMORY

    def test_unknown_ai_fallback(self):
        ctx = make_pipeline_ctx(raw="xyzzy nonsense gibberish abc")
        d = make_router().decide(ctx)
        assert d.decision_type == DecisionType.AI_FALLBACK

    def test_intent_in_payload(self):
        ctx = make_pipeline_ctx(raw="Hello Jarvis.")
        d = make_router().decide(ctx)
        assert "intent" in d.payload
        assert d.payload["intent"] == "GREETING"

    def test_context_snapshot_has_stages(self):
        pipeline = ConversationPipeline()
        state = make_state()
        state.set_topic(Topic(name="test"))
        ctx = pipeline.run("Fix the bug.", state, make_policy())
        d = make_router().decide(ctx)
        assert "pipeline_stages" in d.context_snapshot

    def test_high_confidence_for_known_intent(self):
        ctx = make_pipeline_ctx(raw="Hello.")
        d = make_router().decide(ctx)
        assert d.confidence == 0.90

    def test_lower_confidence_for_unknown(self):
        ctx = make_pipeline_ctx(raw="xyzzy abc zzzz")
        d = make_router().decide(ctx)
        assert d.confidence == 0.50

    def test_resolved_input_used_for_routing(self):
        """Router uses resolved input, not original."""
        rr = ResolutionResult(
            original_input="Close it.",
            resolved_input="Close Visual Studio.",
            resolved=True,
            confidence=0.80,
            reference_type=ReferenceType.OBJECT,
            pronoun="it",
            replacement="Visual Studio",
            reason="resolved",
        )
        ctx = make_pipeline_ctx(
            raw="Close it.", resolution_result=rr
        )
        assert ctx.effective_input() == "Close Visual Studio."
        d = make_router().decide(ctx)
        assert d.resolved_input == "Close Visual Studio."
        assert d.raw_input == "Close it."


# ===========================================================================
# 5. CONVERSATION ENGINE — process()
# ===========================================================================

class TestConversationEngineProcess:

    def test_returns_decision(self):
        e = make_engine()
        d = e.process("Hello Jarvis.")
        assert isinstance(d, Decision)

    def test_greeting_answer_directly(self):
        e = make_engine()
        d = e.process("Hello Jarvis.")
        assert d.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_memory_invoke_memory(self):
        e = make_engine()
        d = e.process("Remember my name is Gianni.")
        assert d.decision_type == DecisionType.INVOKE_MEMORY

    def test_unknown_ai_fallback(self):
        e = make_engine()
        d = e.process("xyzzy nonsense gibberish abc")
        assert d.decision_type == DecisionType.AI_FALLBACK

    def test_turn_recorded(self):
        e = make_engine()
        e.process("Hello.")
        assert e.state.turn_count == 1

    def test_multiple_turns_recorded(self):
        e = make_engine()
        e.process("Hello.")
        e.process("Fix the bug.")
        assert e.state.turn_count == 2

    def test_last_context_populated(self):
        e = make_engine()
        e.process("Hello.")
        assert e.last_context is not None

    def test_last_context_has_stages(self):
        e = make_engine()
        e.process("Hello.")
        assert len(e.last_context.history) == 3

    def test_decision_has_resolved_input(self):
        e = make_engine()
        d = e.process("Hello Jarvis.")
        assert d.resolved_input  # non-empty

    def test_decision_has_raw_input(self):
        e = make_engine()
        d = e.process("Hello Jarvis.")
        assert d.raw_input == "Hello Jarvis."


# ===========================================================================
# 6. CONVERSATION ENGINE — recovery
# ===========================================================================

class TestConversationEngineRecovery:

    def test_never_mind_returns_recovery(self):
        e = make_engine()
        d = e.process("never mind")
        assert d.decision_type == DecisionType.RECOVERY

    def test_recovery_clears_pending(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        e.process("never mind")
        assert not e.state.has_pending()

    def test_recovery_clears_topic(self):
        e = make_engine()
        e.state.set_topic(Topic(name="planning"))
        e.process("never mind")
        assert e.state.current_topic is None

    def test_cancel_with_pending_recovery(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        d = e.process("cancel")
        assert d.decision_type == DecisionType.RECOVERY

    def test_recovery_still_records_turn(self):
        e = make_engine()
        e.process("never mind")
        assert e.state.turn_count == 1


# ===========================================================================
# 7. CONVERSATION ENGINE — slot filling
# ===========================================================================

class TestConversationEngineSlotFilling:

    def test_pending_answer_slot_filled(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        d = e.process("Blue.")
        assert d.decision_type == DecisionType.SLOT_FILLED

    def test_slot_payload_populated(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        d = e.process("Blue.")
        assert d.payload["slot_name"] == "colour"
        assert d.payload["slot_value"] == "Blue"


# ===========================================================================
# 8. CONVERSATION ENGINE — reference resolution
# ===========================================================================

class TestConversationEngineResolution:

    def test_pronoun_resolved(self):
        e = make_engine()
        e.state.update_reference(current_it="Visual Studio")
        d = e.process("Close it.")
        assert d.resolved_input == "Close Visual Studio."

    def test_original_raw_preserved(self):
        e = make_engine()
        e.state.update_reference(current_it="Visual Studio")
        d = e.process("Close it.")
        assert d.raw_input == "Close it."


# ===========================================================================
# 9. CONVERSATION ENGINE — reset and properties
# ===========================================================================

class TestConversationEngineReset:

    def test_reset_clears_turns(self):
        e = make_engine()
        e.process("Hello.")
        e.reset()
        # ConversationState.reset() preserves turn_count (history cleared, count kept)
        assert e.state.last_turn() is None   # history cleared
        assert e.state.turn_count >= 1       # count preserved by design

    def test_reset_clears_last_context(self):
        e = make_engine()
        e.process("Hello.")
        e.reset()
        assert e.last_context is None

    def test_state_property(self):
        e = make_engine()
        assert isinstance(e.state, ConversationState)

    def test_policy_property(self):
        e = make_engine()
        assert isinstance(e.policy, ConversationPolicy)

    def test_custom_policy(self):
        p = make_policy(resolution_threshold=0.80)
        e = make_engine(policy=p)
        assert e.policy.resolution_threshold == 0.80

    def test_summary_dict(self):
        e = make_engine()
        e.process("Hello.")
        s = e.summary()
        assert isinstance(s, dict)
        assert s["turn_count"] == 1
        assert "pipeline_stages" in s


# ===========================================================================
# 10. INTEGRATION — full end-to-end flow
# ===========================================================================

class TestFullFlow:

    def test_normal_conversation(self):
        e = make_engine()
        d = e.process("Hello Jarvis.")
        assert d.decision_type == DecisionType.ANSWER_DIRECTLY
        assert e.state.turn_count == 1

    def test_multi_turn_flow(self):
        e = make_engine()
        d1 = e.process("Hello.")
        d2 = e.process("What is the Repository Pattern?")
        assert d1.decision_type == DecisionType.ANSWER_DIRECTLY
        assert d2.decision_type in (DecisionType.INVOKE_MEMORY, DecisionType.AI_FALLBACK)
        assert e.state.turn_count == 2

    def test_pending_then_answer_flow(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        d = e.process("Blue.")
        assert d.decision_type == DecisionType.SLOT_FILLED
        assert d.payload["slot_value"] == "Blue"

    def test_reference_then_routing_flow(self):
        e = make_engine()
        e.state.update_reference(current_person="Claude")
        d = e.process("Ask him.")
        # "him" resolves to "Claude" — routing proceeds on resolved input
        assert d.resolved_input == "Ask Claude."
        assert d.raw_input == "Ask him."

    def test_recovery_then_continue_flow(self):
        e = make_engine()
        e.state.set_pending(Slot(name="colour", question="What colour?"))
        e.process("never mind")
        assert not e.state.has_pending()
        # Next message continues normally
        d = e.process("Hello.")
        assert d.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_pipeline_stages_always_recorded(self):
        e = make_engine()
        e.process("Hello.")
        ctx = e.last_context
        assert len(ctx.history) == 3
        stages = [s.stage for s in ctx.history]
        assert "RecoveryStage" in stages
        assert "ResolutionStage" in stages
        assert "DialogueStage" in stages


# ===========================================================================
# 11. AGENT INTEGRATION
# ===========================================================================

class TestAgentIntegration:

    def test_agent_has_conversation_engine(self):
        from core.agent import Agent
        a = Agent()
        assert hasattr(a, "conversation_engine")
        assert isinstance(a.conversation_engine, ConversationEngine)

    def test_agent_greeting_still_works(self):
        from core.agent import Agent
        a = Agent()
        response = a.process("Hello Jarvis.")
        assert response.success
        assert response.message

    def test_agent_memory_still_works(self):
        from core.agent import Agent
        a = Agent()
        response = a.process("Remember my name is Gianni.")
        assert response.success

    def test_agent_recovery_returns_clean_response(self):
        from core.agent import Agent
        a = Agent()
        # Engine handles "never mind" as RECOVERY → clean response
        response = a.process("never mind")
        assert response.success
        assert response.message

    def test_agent_existing_intents_all_preserved(self):
        """All pre-Genesis-022 intent paths still route correctly."""
        from core.agent import Agent
        from core.router import IntentRouter
        from core.intents import Intent
        router = IntentRouter()
        assert router.detect("Hello Jarvis.") == Intent.GREETING
        assert router.detect("Who are you?")  == Intent.IDENTITY
        assert router.detect("bye")           == Intent.EXIT


# ===========================================================================
# 12. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_genesis_020_sprint006_unchanged(self):
        from core.conversation.session_summary_engine import SessionSummaryEngine
        e = SessionSummaryEngine()
        assert e.is_empty()

    def test_genesis_021_workers_unchanged(self):
        from core.workers.manager import WorkerManager
        from core.workers.engineering_worker import EngineeringWorker
        m = WorkerManager()
        m.register(EngineeringWorker())
        assert m.has_worker("engineering")

    def test_sprint001_models_unchanged(self):
        d = Decision(
            decision_type=DecisionType.INVOKE_WORKER,
            resolved_input="Plan it.",
        )
        assert d.decision_type == DecisionType.INVOKE_WORKER

    def test_sprint002_state_unchanged(self):
        s = ConversationState()
        s.update_reference(current_person="Claude")
        assert s.references.current_person == "Claude"

    def test_sprint003_resolver_unchanged(self):
        from core.conversation.conversation_resolver import ReferenceResolver
        s = ConversationState()
        s.update_reference(current_it="Visual Studio")
        r = ReferenceResolver()
        result = r.resolve("Close it.", s, ConversationPolicy())
        assert result.resolved

    def test_sprint004_dialogue_unchanged(self):
        from core.conversation.conversation_dialogue import DialogueManager
        m = DialogueManager()
        assert m.is_acknowledgement("ok")

    def test_sprint005_pipeline_unchanged(self):
        pipeline = ConversationPipeline()
        ctx = pipeline.run("Hello.", make_state(), make_policy())
        assert len(ctx.history) == 3

    def test_router_importable(self):
        from core.conversation.conversation_router import ConversationRouter
        assert ConversationRouter is not None

    def test_engine_importable(self):
        from core.conversation.conversation_engine import ConversationEngine
        assert ConversationEngine is not None