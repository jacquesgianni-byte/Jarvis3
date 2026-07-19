"""
Jarvis Conversation Engine (Genesis-022 Sprint-006)

The single entry point for all conversation processing.

Wires together:
    ConversationPipeline  — Recovery → Resolution → Dialogue
    ConversationRouter    — Pipeline context → Decision
    ConversationState     — live session state
    ConversationPolicy    — all thresholds

Usage:
    engine = ConversationEngine()
    decision = engine.process(user_input)

The Agent calls engine.process() and dispatches based on Decision.decision_type.

Design constraints:
    - Single entry point. Agent calls only this.
    - Owns ConversationState and ConversationPolicy.
    - Delegates all processing to Pipeline and Router.
    - Never dispatches to Workers, Tools, or AI directly.
    - Records each turn in ConversationState.turn_history.
    - Deterministic. No AI calls.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from core.conversation.conversation_models import (
    Decision, DecisionType, ConversationTurn,
)
from core.conversation.conversation_pipeline import ConversationPipeline, PipelineContext
from core.conversation.conversation_policy import ConversationPolicy
from core.conversation.conversation_router import ConversationRouter
from core.conversation.conversation_state import ConversationState

logger = logging.getLogger(__name__)


class ConversationEngine:
    """
    Single entry point for all conversation processing.

    Owns one each of:
        ConversationState    — live mutable session state
        ConversationPolicy   — all decision thresholds
        ConversationPipeline — Recovery → Resolution → Dialogue
        ConversationRouter   — PipelineContext → Decision

    Public API:
        process(raw_input) → Decision
        state              → ConversationState (read access)
        policy             → ConversationPolicy (read access)
        reset()            — reset session state
        last_context       → PipelineContext from most recent run
    """

    def __init__(
        self,
        policy: Optional[ConversationPolicy] = None,
    ) -> None:
        self._state    = ConversationState()
        self._policy   = policy or ConversationPolicy()
        self._pipeline = ConversationPipeline()
        self._router   = ConversationRouter()
        self._last_ctx: Optional[PipelineContext] = None

    # ------------------------------------------------------------------
    # Primary API
    # ------------------------------------------------------------------

    def process(self, raw_input: str) -> Decision:
        """
        Process a user message through the full conversation pipeline.

        Steps:
            1. Run ConversationPipeline (Recovery → Resolution → Dialogue)
            2. Run ConversationRouter on enriched context → Decision
            3. Record turn in ConversationState
            4. Return Decision to Agent for dispatch

        Args:
            raw_input: The user's raw message.

        Returns:
            Decision describing what the Agent should do next.
        """
        logger.info("[ENGINE] Processing: %r", raw_input[:60])

        # Run pipeline
        ctx = self._pipeline.run(raw_input, self._state, self._policy)
        self._last_ctx = ctx

        # Produce decision
        decision = self._router.decide(ctx)

        # Record turn
        try:
            turn = ConversationTurn(
                raw_input=raw_input,
                decision=decision,
                topic=self._state.current_topic,
            )
            self._state.add_turn(turn)
        except Exception:
            logger.exception("[ENGINE] Failed to record turn.")

        logger.info(
            "[ENGINE] Decision: %s (conf=%.2f) in %.1fms",
            decision.decision_type.label(),
            decision.confidence,
            ctx.total_duration_ms(),
        )
        return decision

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> ConversationState:
        """The live conversation state."""
        return self._state

    @property
    def policy(self) -> ConversationPolicy:
        """The active conversation policy."""
        return self._policy

    @property
    def last_context(self) -> Optional[PipelineContext]:
        """The PipelineContext from the most recent process() call."""
        return self._last_ctx

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset conversation state for a new session."""
        self._state.reset()
        self._last_ctx = None
        logger.info("[ENGINE] Session reset.")

    def summary(self) -> dict:
        """Human-readable engine summary for debugging."""
        return {
            "turn_count":    self._state.turn_count,
            "mode":          self._state.mode.label(),
            "has_pending":   self._state.has_pending(),
            "current_topic": (
                self._state.current_topic.name
                if self._state.current_topic else None
            ),
            "pipeline_stages": self._pipeline.stage_names,
            "last_decision": (
                str(self._last_ctx.dialogue_result)
                if self._last_ctx and self._last_ctx.dialogue_result else None
            ),
        }