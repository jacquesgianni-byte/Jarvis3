"""
Jarvis Conversation Router (Genesis-022 Sprint-006)

Consumes the enriched PipelineContext and produces a final Decision.

The ConversationRouter is the ONLY component that produces a Decision.
Pipeline stages enrich context — the Router interprets it and decides.

Design constraints:
    - Deterministic. No AI calls.
    - Reads PipelineContext produced by ConversationPipeline.
    - Consults existing IntentRouter for intent classification.
    - Returns exactly one Decision per call.
    - Never modifies ConversationState directly.
    - Preserves all existing routing paths unchanged.

Routing priority:
    1. Terminal recovery (pipeline stopped early) → RECOVERY
    2. Slot filled / pending answered → SLOT_FILLED
    3. Acknowledgement with no pending → ANSWER_DIRECTLY
    4. Topic change → ANSWER_DIRECTLY (let Agent handle)
    5. Intent-based routing (preserves existing IntentRouter behaviour)
    6. AI fallback
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

from core.conversation.conversation_models import Decision, DecisionType
from core.conversation.conversation_dialogue import DialogueType
from core.conversation.conversation_pipeline import PipelineContext, FocusSignal
from core.conversation.conversation_recovery import RecoveryAction
from core.intents import Intent
from core.router import IntentRouter

if TYPE_CHECKING:
    from core.conversation.conversation_policy import ConversationPolicy

logger = logging.getLogger(__name__)

# Mapping from Intent to DecisionType
_INTENT_TO_DECISION: dict[Intent, DecisionType] = {
    Intent.GREETING:    DecisionType.ANSWER_DIRECTLY,
    Intent.IDENTITY:    DecisionType.ANSWER_DIRECTLY,
    Intent.MEMORY:      DecisionType.INVOKE_MEMORY,
    Intent.REASONING:   DecisionType.INVOKE_MEMORY,
    Intent.TOOL:        DecisionType.INVOKE_TOOL,
    Intent.ENGINEERING: DecisionType.INVOKE_MEMORY,   # Academy lookup
    Intent.EXIT:        DecisionType.ANSWER_DIRECTLY,
    Intent.UNKNOWN:     DecisionType.AI_FALLBACK,
}



# Contextual confidence thresholds for Router focus change authorisation (CFR-006)
_FOCUS_GROUNDED_THRESHOLD:    float = 0.70   # minimum to authorise focus change
_FOCUS_POSSESSIVE_CONFIDENCE: float = 0.88   # possessive 'my X' always grounded
_FOCUS_RETURN_BOOST:          float = 0.15   # 'back to X' where X is in history

class ConversationRouter:
    """
    Produces a Decision from an enriched PipelineContext.

    Reads the results of all pipeline stages (recovery, resolution,
    dialogue) and determines the appropriate DecisionType. Falls back
    to the existing IntentRouter for intent classification so all
    pre-existing routing behaviour is preserved.

    Public API:
        decide(ctx) → Decision
    """

    def __init__(self) -> None:
        self._intent_router = IntentRouter()


    def _evaluate_focus_signal(self, ctx):
        """
        Evaluate a FocusSignal against ConversationState for contextual grounding.

        Returns 0.0-1.0. Above _FOCUS_GROUNDED_THRESHOLD -> FOCUS_CHANGE.
        Below threshold -> route as information request.

        Grounding signals (no noun lists, context only - CFR-006):
          - Possessive 'my X'        -> always grounded
          - Entity in EntityRegistry -> session-grounded
          - Entity in TopicTracker   -> conversationally anchored
          - 'back to' with history   -> valid return
          - Recent entities list     -> recently active
        """
        signal = ctx.focus_signal_result
        if signal is None or not signal.detected:
            return 0.0

        state = ctx.state

        # Possessive group patterns are unambiguous -- always grounded
        if signal.possessive or signal.is_group:
            return _FOCUS_POSSESSIVE_CONFIDENCE

        confidence = signal.raw_confidence * 0.40
        candidate_lower = signal.candidate.lower()

        # Signal 1: Entity known in EntityRegistry
        try:
            current_turn = getattr(state, 'current_turn', 0)
            active_entities = {
                e.name.lower()
                for e in state.entity_registry.active(current_turn)
            }
            if candidate_lower in active_entities:
                confidence += 0.35
                logger.debug("[ROUTER] Focus grounding: %r in EntityRegistry (+0.35)", signal.candidate)
        except Exception:
            pass

        # Signal 2: Entity in TopicTracker history or current
        try:
            topic_names = [t.name for t in state.topic_tracker.history]
            if state.topic_tracker.current:
                topic_names.append(state.topic_tracker.current.name)
            if candidate_lower in topic_names:
                confidence += 0.30
                logger.debug("[ROUTER] Focus grounding: %r in TopicTracker (+0.30)", signal.candidate)
        except Exception:
            pass

        # Signal 3: 'back to' -- valid if entity is in topic history OR current
        if signal.is_return:
            try:
                topic_names = [t.name for t in state.topic_tracker.history]
                if state.topic_tracker.current:
                    topic_names.append(state.topic_tracker.current.name)
                if candidate_lower in topic_names:
                    confidence += _FOCUS_RETURN_BOOST
                else:
                    confidence -= 0.25
            except Exception:
                pass

        # Signal 4: Recent entities list
        try:
            recent = [e.lower() for e in state.recent_entities]
            if candidate_lower in recent:
                confidence += 0.20
                logger.debug("[ROUTER] Focus grounding: %r in recent_entities (+0.20)", signal.candidate)
        except Exception:
            pass

        return max(0.0, min(1.0, confidence))

    def decide(self, ctx: PipelineContext) -> Decision:
        """
        Produce a Decision from an enriched PipelineContext.

        Args:
            ctx: Fully enriched PipelineContext from ConversationPipeline.

        Returns:
            An immutable Decision describing what the Agent should do next.
        """
        effective = ctx.effective_input()
        original  = ctx.original_input

        # 1. Terminal recovery — pipeline stopped early
        if ctx.is_terminal and ctx.recovery_result:
            action = ctx.recovery_result.action
            logger.info("[ROUTER] Terminal recovery: %s", action.label())
            return Decision(
                decision_type=DecisionType.RECOVERY,
                resolved_input=effective,
                raw_input=original,
                confidence=1.0,
                reason=ctx.recovery_result.reason,
                payload={
                    "recovery_action": action.label(),
                    "pattern_matched": ctx.recovery_result.pattern_matched,
                },
            )

        # 2. Slot filled / pending question answered
        if ctx.dialogue_result and ctx.dialogue_result.dialogue_type in (
            DialogueType.ANSWER_PENDING, DialogueType.FILL_SLOT,
        ):
            logger.info(
                "[ROUTER] Slot fill: slot=%r value=%r",
                ctx.dialogue_result.slot_name,
                ctx.dialogue_result.slot_value,
            )
            return Decision(
                decision_type=DecisionType.SLOT_FILLED,
                resolved_input=effective,
                raw_input=original,
                confidence=ctx.dialogue_result.confidence,
                reason=ctx.dialogue_result.reason,
                payload={
                    "slot_name":        ctx.dialogue_result.slot_name,
                    "slot_value":       ctx.dialogue_result.slot_value,
                    "pending_question": ctx.dialogue_result.pending_question,
                    "dialogue_type":    ctx.dialogue_result.dialogue_type.label(),
                },
            )

        # 3. Pure acknowledgement — confirm and continue
        if (ctx.dialogue_result
                and ctx.dialogue_result.dialogue_type == DialogueType.ACKNOWLEDGEMENT):
            logger.info("[ROUTER] Acknowledgement — answer directly.")
            return Decision(
                decision_type=DecisionType.ANSWER_DIRECTLY,
                resolved_input=effective,
                raw_input=original,
                confidence=ctx.dialogue_result.confidence,
                reason="User acknowledged. No further action required.",
                payload={"dialogue_type": "acknowledgement"},
            )

        # 3b. Genesis-048: Understood declarative statement -> ANSWER_DIRECTLY
        # UnderstandingStage detected structured facts before AI was called.
        # Core understands the input - no AI needed for the routing decision.
        _ur = getattr(ctx, "understanding_result", None)
        if _ur:
            _inp = ctx.original_input
            _is_question = _inp.rstrip().endswith("?")
            _is_q_word = bool(__import__("re").match(
                r"(?i)^\s*(?:what|who|where|when|why|how|which|can|could|would|should|will|did|do|does|is|are|have|has|had)\b",
                _inp))
            _is_cmd = bool(__import__("re").match(
                r"(?i)^\s*(?:remember|note|save|store|forget|tell|show|find|get|set|remind)\b",
                _inp))
            if not _is_question and not _is_q_word and not _is_cmd:
                from core.conversation.fact_extractor import FactType as _FT
                _UNDERSTOOD = frozenset({_FT.EVENT, _FT.MILESTONE, _FT.ACHIEVEMENT,
                                         _FT.PREFERENCE, _FT.PROJECT, _FT.TASK,
                                         _FT.PERSON, _FT.WORKPLACE})
                _types = {fct.fact_type for fct in _ur if fct.fact_type in _UNDERSTOOD}
                if _types:
                    _names = ", ".join(t.name for t in _types)
                    logger.info("[ROUTER] Understood declarative: %s -> ANSWER_DIRECTLY", _names)
                    return Decision(
                        decision_type=DecisionType.ANSWER_DIRECTLY,
                        resolved_input=effective,
                        raw_input=original,
                        confidence=0.80,
                        reason=f"Core understands: {_names}",
                        payload={"understood_types": [t.name for t in _types],
                                 "fact_count": len(_ur)},
                    )

        # 3a. Focus signal -- Router evaluates grounding. (CFR-006)
        if ctx.focus_signal_result and ctx.focus_signal_result.detected:
            _focus_conf = self._evaluate_focus_signal(ctx)
            logger.info(
                "[ROUTER] FocusSignal candidate=%r contextual_conf=%.2f threshold=%.2f",
                ctx.focus_signal_result.candidate, _focus_conf, _FOCUS_GROUNDED_THRESHOLD,
            )
            if _focus_conf >= _FOCUS_GROUNDED_THRESHOLD:
                logger.info("[ROUTER] Focus change AUTHORISED: %r", ctx.focus_signal_result.candidate)
                return Decision(
                    decision_type=DecisionType.FOCUS_CHANGE,
                    resolved_input=effective,
                    raw_input=original,
                    confidence=_focus_conf,
                    reason=f"Focus signal grounded: {ctx.focus_signal_result.candidate!r}",
                    payload={
                        "focus_candidate": ctx.focus_signal_result.candidate,
                        "is_group":        ctx.focus_signal_result.is_group,
                        "possessive":      ctx.focus_signal_result.possessive,
                        "is_return":       ctx.focus_signal_result.is_return,
                        "pattern":         ctx.focus_signal_result.pattern,
                    },
                )
            else:
                logger.info(
                    "[ROUTER] Focus signal REJECTED (conf=%.2f < %.2f) -- information request",
                    _focus_conf, _FOCUS_GROUNDED_THRESHOLD,
                )

        # 4. Intent-based routing via existing IntentRouter
        intent = self._intent_router.detect(effective)
        decision_type = _INTENT_TO_DECISION.get(intent, DecisionType.AI_FALLBACK)
        confidence = 0.90 if intent != Intent.UNKNOWN else 0.50

        logger.info(
            "[ROUTER] Intent=%s → DecisionType=%s",
            intent.name, decision_type.label(),
        )

        return Decision(
            decision_type=decision_type,
            resolved_input=effective,
            raw_input=original,
            confidence=confidence,
            reason=f"Intent {intent.name} → {decision_type.label()}",
            payload={
                "intent":        intent.name,
                "dialogue_type": ctx.dialogue_result.dialogue_type.label()
                                 if ctx.dialogue_result else None,
                "resolved":      ctx.resolution_result.resolved
                                 if ctx.resolution_result else False,
            },
            context_snapshot={
                "pipeline_stages": ctx.stage_names(),
                "is_terminal":     ctx.is_terminal,
            },
        )