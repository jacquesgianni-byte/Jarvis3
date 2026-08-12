"""
Jarvis Conversation Pipeline (Genesis-022 Sprint-005)

Orchestrates the conversation processing stages in order.

The pipeline:
    1. Receives raw user input and ConversationState
    2. Creates a PipelineContext (the processing bag)
    3. Runs each stage in sequence
    4. Returns the fully enriched PipelineContext for the Router

The pipeline does NOT make business decisions.
It simply runs stages and collects results.
Only ConversationRouter (Sprint-006) produces the final Decision.

Stage order:
    Stage 1: RecoveryStage     — check for recovery patterns first
    Stage 2: ResolutionStage   — resolve pronouns and references
    Stage 3: DialogueStage     — check pending questions and slot fills

Each stage:
    - receives PipelineContext
    - enriches PipelineContext
    - returns PipelineContext
    - sets is_terminal=True for early exit (recovery reset, slot fill)

Processing trace (telemetry):
    Each stage appends a ProcessingStep to PipelineContext.history
    so the Engineering Console can show exactly how a message was handled.

    ProcessingStep(
        stage="RecoveryStage",
        executed=True,
        duration_ms=1,
        outcome="no recovery"
    )
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from core.conversation.conversation_dialogue import DialogueManager, DialogueResult
from core.conversation.conversation_recovery import RecoveryHandler, RecoveryResult
from core.conversation.conversation_resolver import ReferenceResolver, ResolutionResult

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState
    from core.conversation.conversation_policy import ConversationPolicy


# ---------------------------------------------------------------------------
# ProcessingStep — telemetry / trace entry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProcessingStep:
    """
    A single stage's execution record in the processing trace.

    Immutable. Appended to PipelineContext.history by each stage.
    Used by the Engineering Console (F12) for debugging and visibility.

    Attributes:
        stage:       Name of the pipeline stage.
        executed:    True if the stage ran (False if skipped).
        duration_ms: How long the stage took in milliseconds.
        outcome:     Human-readable one-line result.
        metadata:    Optional structured data about the stage's work.
    """
    stage:       str
    executed:    bool
    duration_ms: float            = 0.0
    outcome:     str              = ""
    metadata:    dict[str, Any]   = field(default_factory=dict)

    def __str__(self) -> str:
        status = "✓" if self.executed else "–"
        return f"{status} {self.stage} ({self.duration_ms:.1f}ms): {self.outcome}"


# ---------------------------------------------------------------------------
# PipelineContext — the mutable processing bag
# ---------------------------------------------------------------------------

@dataclass
class PipelineContext:
    """
    The mutable processing bag passed between pipeline stages.

    Created at the start of each pipeline run.
    Fully enriched after all stages complete.
    Passed to ConversationRouter (Sprint-006) for final Decision.

    Attributes:
        original_input:   The user's raw input — NEVER modified.
        current_input:    Working copy — updated by ResolutionStage.
        state:            The live ConversationState (may be modified by Recovery).
        policy:           The ConversationPolicy for threshold decisions.
        recovery_result:  Set by RecoveryStage.
        resolution_result: Set by ResolutionStage.
        dialogue_result:  Set by DialogueStage.
        is_terminal:      True if pipeline should stop early.
        history:          Processing trace (one entry per stage).
        metadata:         Arbitrary cross-stage data.
        started_at:       Pipeline start time (for total duration).
    """
    original_input:    str
    state:             "ConversationState"
    policy:            "ConversationPolicy"
    current_input:     str                         = ""
    recovery_result:   Optional[RecoveryResult]    = None
    resolution_result: Optional[ResolutionResult]  = None
    dialogue_result:   Optional[DialogueResult]    = None
    is_terminal:       bool                        = False
    history:           list[ProcessingStep]        = field(default_factory=list)
    metadata:          dict[str, Any]              = field(default_factory=dict)
    started_at:        float                       = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        if not self.current_input:
            self.current_input = self.original_input

    def effective_input(self) -> str:
        """The input to use for routing — resolved if possible."""
        if self.resolution_result and self.resolution_result.resolved:
            return self.resolution_result.resolved_input
        return self.current_input or self.original_input

    def total_duration_ms(self) -> float:
        """Total pipeline duration in milliseconds."""
        return (time.perf_counter() - self.started_at) * 1000

    def append_step(self, step: ProcessingStep) -> None:
        """Add a processing step to the trace."""
        self.history.append(step)

    def stage_names(self) -> list[str]:
        """Names of all stages that were executed."""
        return [s.stage for s in self.history if s.executed]

    def summary(self) -> dict:
        """Human-readable pipeline summary for debugging."""
        return {
            "original_input":  self.original_input,
            "effective_input": self.effective_input(),
            "is_terminal":     self.is_terminal,
            "stages_run":      self.stage_names(),
            "total_ms":        round(self.total_duration_ms(), 2),
            "recovery":        str(self.recovery_result) if self.recovery_result else None,
            "resolution":      str(self.resolution_result) if self.resolution_result else None,
            "dialogue":        str(self.dialogue_result) if self.dialogue_result else None,
        }


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

class RecoveryStage:
    """
    Stage 1: Check for recovery patterns before any other processing.

    If a full reset occurs (should_continue=False), marks context
    as terminal so the pipeline stops.
    """

    NAME = "RecoveryStage"

    def __init__(self) -> None:
        self._handler = RecoveryHandler()

    def process(self, ctx: PipelineContext) -> PipelineContext:
        start = time.perf_counter()
        result = self._handler.check(ctx.original_input, ctx.state)
        ctx.recovery_result = result
        duration = (time.perf_counter() - start) * 1000

        if result.recovered and not result.should_continue:
            ctx.is_terminal = True
            outcome = f"terminal recovery: {result.action.label()}"
        elif result.recovered:
            outcome = f"soft recovery: {result.action.label()}"
        else:
            outcome = "no recovery"

        ctx.append_step(ProcessingStep(
            stage=self.NAME,
            executed=True,
            duration_ms=round(duration, 2),
            outcome=outcome,
            metadata={"action": result.action.label(), "recovered": result.recovered},
        ))
        return ctx


class ResolutionStage:
    """
    Stage 2: Resolve pronouns and references in the input.

    Updates ctx.current_input with the resolved version.
    Skipped if context is terminal.
    """

    NAME = "ResolutionStage"

    def __init__(self) -> None:
        self._resolver = ReferenceResolver()

    def process(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.is_terminal:
            ctx.append_step(ProcessingStep(
                stage=self.NAME, executed=False,
                outcome="skipped (terminal context)",
            ))
            return ctx

        start = time.perf_counter()

        if self._resolver.has_reference(ctx.current_input):
            result = self._resolver.resolve(ctx.current_input, ctx.state, ctx.policy)
            ctx.resolution_result = result
            if result.resolved:
                ctx.current_input = result.resolved_input
                outcome = f"resolved {result.pronoun!r} → {result.replacement!r}"
            else:
                outcome = f"reference detected but not resolved (conf={result.confidence:.2f})"
        else:
            ctx.resolution_result = ResolutionResult.no_resolution(
                ctx.current_input, "No reference detected."
            )
            outcome = "no reference"

        duration = (time.perf_counter() - start) * 1000
        ctx.append_step(ProcessingStep(
            stage=self.NAME,
            executed=True,
            duration_ms=round(duration, 2),
            outcome=outcome,
            metadata={"resolved": ctx.resolution_result.resolved if ctx.resolution_result else False},
        ))
        return ctx


class DialogueStage:
    """
    Stage 3: Check for pending questions, slot fills, acks, topic changes.

    May mark context as terminal for ANSWER_PENDING / FILL_SLOT
    so the router knows the input was consumed by dialogue.
    Skipped if context is terminal.
    """

    NAME = "DialogueStage"

    def __init__(self) -> None:
        self._manager = DialogueManager()

    def process(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.is_terminal:
            ctx.append_step(ProcessingStep(
                stage=self.NAME, executed=False,
                outcome="skipped (terminal context)",
            ))
            return ctx

        start = time.perf_counter()
        result = self._manager.analyse(ctx.current_input, ctx.state, ctx.policy)
        ctx.dialogue_result = result

        duration = (time.perf_counter() - start) * 1000
        ctx.append_step(ProcessingStep(
            stage=self.NAME,
            executed=True,
            duration_ms=round(duration, 2),
            outcome=result.dialogue_type.label(),
            metadata={
                "dialogue_type": result.dialogue_type.label(),
                "slot_name":     result.slot_name,
                "is_ack":        result.is_acknowledgement,
            },
        ))
        return ctx


# ---------------------------------------------------------------------------
# ConversationPipeline
# ---------------------------------------------------------------------------

class ConversationPipeline:
    """
    Orchestrates the conversation processing stages in order.

    Produces a fully enriched PipelineContext for the Router.
    Makes no routing decisions itself.

    Default stage order:
        1. RecoveryStage
        2. ResolutionStage
        3. DialogueStage

    Public API:
        run(raw_input, state, policy) → PipelineContext
    """

    def __init__(self) -> None:
        self._stages = [
            RecoveryStage(),
            ResolutionStage(),
            DialogueStage(),
        ]

    def run(
        self,
        raw_input: str,
        state: "ConversationState",
        policy: "ConversationPolicy",
    ) -> PipelineContext:
        """
        Run all pipeline stages and return the enriched context.

        Stages run in order. If any stage sets ctx.is_terminal=True,
        subsequent stages record themselves as skipped.

        Args:
            raw_input: The user's original message.
            state:     The live ConversationState.
            policy:    The ConversationPolicy.

        Returns:
            PipelineContext fully enriched by all executed stages.
        """
        ctx = PipelineContext(
            original_input=raw_input,
            state=state,
            policy=policy,
        )

        for stage in self._stages:
            ctx = stage.process(ctx)

        return ctx

    @property
    def stage_count(self) -> int:
        """Number of stages in the pipeline."""
        return len(self._stages)

    @property
    def stage_names(self) -> list[str]:
        """Names of all pipeline stages."""
        return [s.NAME for s in self._stages]