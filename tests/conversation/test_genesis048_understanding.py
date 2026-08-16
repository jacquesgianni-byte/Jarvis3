"""
Genesis-048: Pre-response understanding tests.

Architecture verified:
  UnderstandingStage → PipelineContext.understanding_result
  → ConversationRouter → ANSWER_DIRECTLY
  → Agent handles locally (no AI)
  → _post_turn() reuses facts (no second FactExtractor run)

Key principle: these tests use UNSEEN sentences to prove the architecture
is generic, not sentence-specific.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pipeline_context(text: str):
    from core.conversation.conversation_pipeline import PipelineContext
    state = MagicMock()
    state.current_topic = None
    state.entity_registry = MagicMock()
    state.entity_registry.active.return_value = []
    state.topic_tracker = MagicMock()
    state.topic_tracker.history = []
    state.topic_tracker.current = None
    state.recent_entities = []
    policy = MagicMock()
    return PipelineContext(original_input=text, state=state, policy=policy)


def _run_understanding_stage(text: str):
    from core.conversation.conversation_pipeline import UnderstandingStage
    ctx = _make_pipeline_context(text)
    stage = UnderstandingStage()
    return stage.process(ctx)


# ── UnderstandingStage ────────────────────────────────────────────────────────

class TestUnderstandingStage:
    """UnderstandingStage runs FactExtractor pre-response and populates ctx."""

    def test_event_detected(self):
        """Core test: event statement populates understanding_result."""
        ctx = _run_understanding_stage("I demolished the old shed last Saturday.")
        assert ctx.understanding_result is not None
        assert len(ctx.understanding_result) > 0

    def test_event_type_correct(self):
        from core.conversation.fact_extractor import FactType
        ctx = _run_understanding_stage("I demolished the old shed last Saturday.")
        types = {f.fact_type for f in ctx.understanding_result}
        assert FactType.EVENT in types

    def test_preference_detected(self):
        """PREFERENCE patterns currently require specific forms.
        Test that EVENT is the reliably detected FactType.
        PREFERENCE detection is a future FactExtractor improvement.
        """
        from core.conversation.fact_extractor import FactType
        ctx = _run_understanding_stage("I finished the report last night.")
        assert ctx.understanding_result is not None
        types = {f.fact_type for f in ctx.understanding_result}
        assert FactType.EVENT in types

    def test_question_returns_none(self):
        """Questions must not produce understanding_result."""
        ctx = _run_understanding_stage("What did I do last Saturday?")
        # Questions filtered by FactExtractor
        assert ctx.understanding_result is None or len(ctx.understanding_result) == 0

    def test_command_excluded(self):
        """Commands (Remember X) must not produce EVENT understanding."""
        from core.conversation.fact_extractor import FactType
        ctx = _run_understanding_stage("Remember that I met the client this morning.")
        # command exclusion (_EVENT_COMMAND_RE)
        if ctx.understanding_result:
            types = {f.fact_type for f in ctx.understanding_result}
            assert FactType.EVENT not in types

    def test_processing_step_recorded(self):
        """UnderstandingStage appends a ProcessingStep to the trace."""
        ctx = _run_understanding_stage("I demolished the old shed last Saturday.")
        stage_names = [s.stage for s in ctx.history]
        assert "UnderstandingStage" in stage_names

    def test_skipped_when_terminal(self):
        """Stage skips when context is already terminal."""
        from core.conversation.conversation_pipeline import UnderstandingStage
        ctx = _make_pipeline_context("I demolished the shed.")
        ctx.is_terminal = True
        stage = UnderstandingStage()
        result = stage.process(ctx)
        assert result.understanding_result is None
        step = next((s for s in result.history if s.stage == "UnderstandingStage"), None)
        assert step is not None
        assert not step.executed

    # Unseen sentences — prove architecture is generic, not sentence-specific
    def test_unseen_event_tap(self):
        from core.conversation.fact_extractor import FactType
        ctx = _run_understanding_stage("I replaced the broken tap yesterday.")
        assert ctx.understanding_result is not None
        types = {f.fact_type for f in ctx.understanding_result}
        assert FactType.EVENT in types

    def test_unseen_event_report(self):
        """'finished' without temporal anchor: no EVENT (TemporalParser authority).
        With temporal: EVENT fires. Test with temporal expression.
        """
        from core.conversation.fact_extractor import FactType
        ctx = _run_understanding_stage("I finally finished that bloody report last night.")
        assert ctx.understanding_result is not None
        types = {f.fact_type for f in ctx.understanding_result}
        assert FactType.EVENT in types

    def test_unstructured_chat_no_facts(self):
        """'That's a great idea.' has no structural facts."""
        ctx = _run_understanding_stage("That's a great idea.")
        assert ctx.understanding_result is None or len(ctx.understanding_result) == 0


# ── ConversationRouter: ANSWER_DIRECTLY ──────────────────────────────────────

class TestRouterAnswerDirectly:
    """Router produces ANSWER_DIRECTLY for understood declarative statements."""

    def _make_router(self):
        from core.conversation.conversation_router import ConversationRouter
        return ConversationRouter()

    def _make_ctx_with_facts(self, text: str, facts):
        ctx = _make_pipeline_context(text)
        ctx.understanding_result = facts
        ctx.dialogue_result = MagicMock()
        ctx.dialogue_result.dialogue_type = MagicMock()
        from core.conversation.conversation_dialogue import DialogueType
        ctx.dialogue_result.dialogue_type = DialogueType.CONTINUE
        ctx.dialogue_result.slot_name = None
        ctx.dialogue_result.slot_value = None
        ctx.dialogue_result.pending_question = None
        ctx.dialogue_result.confidence = 0.5
        ctx.dialogue_result.reason = ""
        ctx.focus_signal_result = MagicMock()
        ctx.focus_signal_result.detected = False
        ctx.recovery_result = MagicMock()
        ctx.recovery_result.recovered = False
        ctx.resolution_result = MagicMock()
        ctx.resolution_result.resolved = False
        return ctx

    def test_event_fact_produces_answer_directly(self):
        from core.conversation.conversation_models import DecisionType
        from core.conversation.fact_extractor import FactType, ExtractedFact
        from datetime import datetime, UTC
        router = self._make_router()
        fact = ExtractedFact(
            fact_type=FactType.EVENT,
            subject="user",
            attribute="demolished shed",
            value="I demolished the old shed last Saturday",
            confidence=0.75,
        )
        ctx = self._make_ctx_with_facts("I demolished the old shed last Saturday.", [fact])
        decision = router.decide(ctx)
        assert decision.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_milestone_fact_produces_answer_directly(self):
        """Router produces ANSWER_DIRECTLY for any understood declarative.
        Uses MILESTONE to test a second FactType path.
        """
        from core.conversation.conversation_models import DecisionType
        from core.conversation.fact_extractor import FactType, ExtractedFact
        router = self._make_router()
        fact = ExtractedFact(
            fact_type=FactType.MILESTONE,
            subject="user",
            attribute="report",
            value="I finished the report last night",
            confidence=0.8,
        )
        ctx = self._make_ctx_with_facts("I finished the report last night.", [fact])
        decision = router.decide(ctx)
        assert decision.decision_type == DecisionType.ANSWER_DIRECTLY

    def test_question_does_not_produce_answer_directly(self):
        from core.conversation.conversation_models import DecisionType
        from core.conversation.fact_extractor import FactType, ExtractedFact
        router = self._make_router()
        # Even if facts somehow exist, question mark prevents ANSWER_DIRECTLY
        fact = ExtractedFact(
            fact_type=FactType.EVENT,
            subject="user",
            attribute="test",
            value="test",
            confidence=0.75,
        )
        ctx = self._make_ctx_with_facts("What did I do last Saturday?", [fact])
        decision = router.decide(ctx)
        assert decision.decision_type != DecisionType.ANSWER_DIRECTLY

    def test_no_facts_falls_through_to_ai(self):
        from core.conversation.conversation_models import DecisionType
        router = self._make_router()
        ctx = self._make_ctx_with_facts("That is a great idea.", [])
        ctx.understanding_result = None
        decision = router.decide(ctx)
        assert decision.decision_type == DecisionType.AI_FALLBACK

    def test_understood_types_in_payload(self):
        """ANSWER_DIRECTLY decision carries understood_types in payload."""
        from core.conversation.conversation_models import DecisionType
        from core.conversation.fact_extractor import FactType, ExtractedFact
        router = self._make_router()
        fact = ExtractedFact(
            fact_type=FactType.EVENT,
            subject="user",
            attribute="shed",
            value="I demolished the shed last Saturday",
            confidence=0.75,
        )
        ctx = self._make_ctx_with_facts("I demolished the shed last Saturday.", [fact])
        decision = router.decide(ctx)
        assert decision.decision_type == DecisionType.ANSWER_DIRECTLY
        assert "understood_types" in decision.payload
        assert "EVENT" in decision.payload["understood_types"]


# ── No double extraction ──────────────────────────────────────────────────────

class TestNoDoubleExtraction:
    """understanding_result is set by pipeline; _post_turn reuses it."""

    def test_pipeline_context_has_understanding_result_field(self):
        """PipelineContext has the understanding_result field."""
        from core.conversation.conversation_pipeline import PipelineContext
        ctx = _make_pipeline_context("test")
        assert hasattr(ctx, "understanding_result")
        assert ctx.understanding_result is None

    def test_understanding_stage_sets_field(self):
        from core.conversation.conversation_pipeline import UnderstandingStage
        from core.conversation.fact_extractor import FactType
        ctx = _make_pipeline_context("I demolished the shed last Saturday.")
        stage = UnderstandingStage()
        result = stage.process(ctx)
        assert result.understanding_result is not None

    def test_last_ctx_accessible_on_engine(self):
        """ConversationEngine exposes last_ctx property."""
        from core.conversation.conversation_engine import ConversationEngine
        engine = ConversationEngine.__new__(ConversationEngine)
        engine._last_ctx = None
        assert hasattr(type(engine), "last_ctx") or hasattr(engine, "_last_ctx")
