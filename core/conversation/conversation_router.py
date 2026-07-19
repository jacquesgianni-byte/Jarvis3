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
from core.conversation.conversation_pipeline import PipelineContext
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