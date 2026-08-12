"""
Jarvis Conversation Engine Models (Genesis-022 Sprint-001)

Core data structures for the Conversation Engine.

Design constraints:
    - All models are immutable (frozen dataclasses) except where
      mutability is architecturally required (ConversationContext).
    - ConversationContext is mutable — it is the pipeline's shared bag.
    - Decision is immutable — it is the final output of the pipeline.
    - Only ConversationRouter may produce a Decision.
      Pipeline stages enrich ConversationContext; they never set
      ctx.decision directly (that is the router's job, enforced by
      ConversationPolicy in Sprint-002).
    - No AI calls, no I/O, no side effects anywhere in this module.

Components:
    DecisionType      — enum of all possible routing outcomes
    Decision          — the final immutable routing decision
    SlotStatus        — enum: EMPTY / FILLED / EXPIRED
    Slot              — a single conversation slot (what Jarvis is asking for)
    Topic             — the current conversation topic
    ConversationTurn  — one complete turn (user input + decision)
    ConversationContext — mutable pipeline processing bag
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Optional


# ---------------------------------------------------------------------------
# DecisionType
# ---------------------------------------------------------------------------

class DecisionType(Enum):
    """
    All possible routing outcomes from the ConversationRouter.

    The ConversationRouter produces exactly one Decision per pipeline run.
    Pipeline stages never produce DecisionType values directly.
    """
    ANSWER_DIRECTLY = auto()   # engine answers from its own knowledge
    ASK_FOLLOW_UP   = auto()   # engine asks the user a clarifying question
    INVOKE_MEMORY   = auto()   # route to KnowledgeEngine
    INVOKE_TOOL     = auto()   # route to ToolManager
    INVOKE_WORKER   = auto()   # route to WorkerCoordinator
    AI_FALLBACK     = auto()   # route to AI provider
    SLOT_FILLED     = auto()   # a pending slot was filled — continue routing
    RECOVERY        = auto()   # conversation recovery ("never mind", etc.)

    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def is_terminal(self) -> bool:
        """True if this decision ends the current pipeline run."""
        return self in (
            DecisionType.RECOVERY,
            DecisionType.SLOT_FILLED,
        )

    @property
    def requires_dispatch(self) -> bool:
        """True if this decision requires calling a downstream system."""
        return self in (
            DecisionType.INVOKE_MEMORY,
            DecisionType.INVOKE_TOOL,
            DecisionType.INVOKE_WORKER,
            DecisionType.AI_FALLBACK,
        )


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Decision:
    """
    The final immutable routing decision produced by ConversationRouter.

    Only ConversationRouter may create Decision instances.
    Pipeline stages enrich ConversationContext — they never create Decisions.

    Attributes:
        decision_type:   What should happen next.
        resolved_input:  The reference-resolved version of the user's input.
                         May equal raw_input if no resolution was performed.
        confidence:      Router confidence in this decision (0.0–1.0).
        payload:         Structured data for the downstream system.
                         e.g. {"worker": "planning", "task_type": "plan_implementation"}
        raw_input:       The original user input, preserved unchanged.
        context_snapshot: Snapshot of ConversationState at decision time.
        produced_at:     UTC timestamp when this decision was produced.
    """
    decision_type:    DecisionType
    resolved_input:   str
    confidence:       float               = 1.0
    payload:          dict[str, Any]      = field(default_factory=dict)
    raw_input:        str                 = ""
    context_snapshot: dict[str, Any]      = field(default_factory=dict)
    reason:           str                 = ""
    produced_at:      datetime            = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __str__(self) -> str:
        return (
            f"Decision({self.decision_type.label()}, "
            f"confidence={self.confidence:.2f})"
        )

    @property
    def is_terminal(self) -> bool:
        return self.decision_type.is_terminal

    @property
    def requires_dispatch(self) -> bool:
        return self.decision_type.requires_dispatch


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class SlotStatus(Enum):
    """Lifecycle state of a conversation slot."""
    EMPTY   = auto()   # not yet filled
    FILLED  = auto()   # has a value
    EXPIRED = auto()   # TTL exceeded without being filled

    def label(self) -> str:
        return self.name.title()


@dataclass(frozen=True)
class Slot:
    """
    A single conversation slot — a named piece of information Jarvis
    is trying to collect from the user.

    Immutable. A filled slot is represented by creating a new Slot
    instance with status=FILLED and value set.

    Attributes:
        name:        Slot identifier. e.g. "favourite_colour", "root_path"
        question:    The question Jarvis asked to fill this slot.
        status:      EMPTY / FILLED / EXPIRED
        value:       The filled value (None if EMPTY or EXPIRED).
        asked_at:    When the question was registered.
        filled_at:   When the slot was filled (None if not yet filled).
        ttl_seconds: How long before this slot expires (0 = never).
    """
    name:        str
    question:    str
    status:      SlotStatus            = SlotStatus.EMPTY
    value:       Optional[str]         = None
    asked_at:    datetime              = field(
        default_factory=lambda: datetime.now(UTC)
    )
    filled_at:   Optional[datetime]    = None
    ttl_seconds: int                   = 300

    def __str__(self) -> str:
        if self.status == SlotStatus.FILLED:
            return f"Slot({self.name}={self.value!r})"
        return f"Slot({self.name}, {self.status.label()})"

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """True if this slot has exceeded its TTL without being filled."""
        if self.status == SlotStatus.FILLED:
            return False
        if self.ttl_seconds == 0:
            return False
        reference = now or datetime.now(UTC)
        elapsed = (reference - self.asked_at).total_seconds()
        return elapsed > self.ttl_seconds

    def fill(self, value: str) -> "Slot":
        """Return a new filled Slot. Immutability preserved."""
        return Slot(
            name=self.name,
            question=self.question,
            status=SlotStatus.FILLED,
            value=value,
            asked_at=self.asked_at,
            filled_at=datetime.now(UTC),
            ttl_seconds=self.ttl_seconds,
        )

    def expire(self) -> "Slot":
        """Return a new expired Slot. Immutability preserved."""
        return Slot(
            name=self.name,
            question=self.question,
            status=SlotStatus.EXPIRED,
            value=None,
            asked_at=self.asked_at,
            filled_at=None,
            ttl_seconds=self.ttl_seconds,
        )


# ---------------------------------------------------------------------------
# Topic
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Topic:
    """
    The current conversation topic.

    Immutable. Topic changes produce new Topic instances.
    ConversationState maintains topic history for recovery.

    Attributes:
        name:       Short topic identifier. e.g. "repository_analysis"
        label:      Human-readable topic label.
        started_at: When this topic became active.
        turn:       Conversation turn when this topic was set.
        metadata:   Optional structured data about the topic.
    """
    name:       str
    label:      str                = ""
    started_at: datetime           = field(
        default_factory=lambda: datetime.now(UTC)
    )
    turn:       int                = 0
    metadata:   dict[str, Any]     = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Topic({self.name!r})"

    def __post_init__(self) -> None:
        # Default label to name if not provided
        if not self.label:
            object.__setattr__(self, "label", self.name.replace("_", " ").title())


# ---------------------------------------------------------------------------
# ConversationTurn
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConversationTurn:
    """
    One complete conversation turn — user input and the resulting Decision.

    Immutable. Stored in ConversationState.turn_history.

    Attributes:
        turn_id:     Unique identifier for this turn.
        raw_input:   The user's original message.
        decision:    The Decision produced for this turn.
        timestamp:   UTC when this turn was processed.
        topic:       The active topic at the time of this turn.
    """
    raw_input:  str
    decision:   Decision
    timestamp:  datetime        = field(
        default_factory=lambda: datetime.now(UTC)
    )
    turn_id:    str             = field(
        default_factory=lambda: str(uuid.uuid4())[:8]
    )
    topic:      Optional[Topic] = None

    def __str__(self) -> str:
        return (
            f"Turn({self.turn_id}: "
            f"{self.raw_input[:40]!r} → {self.decision.decision_type.label()})"
        )


# ---------------------------------------------------------------------------
# ConversationContext (pipeline bag — mutable)
# ---------------------------------------------------------------------------

@dataclass
class ConversationContext:
    """
    Mutable pipeline processing bag.

    Passed between pipeline stages. Each stage may enrich this context
    but must never set `decision` directly — only ConversationRouter
    may produce a Decision.

    The `is_terminal` flag signals early pipeline exit. A stage sets
    it to True when further processing is unnecessary (e.g. recovery
    detected, slot filled). The pipeline stops after the current stage.

    Attributes:
        raw_input:      The user's original message (never modified).
        resolved_input: Set by ResolutionStage. Defaults to raw_input.
        state:          Reference to the live ConversationState.
        decision:       Set ONLY by ConversationRouter (RoutingStage).
        is_terminal:    Set by any stage to signal early exit.
        metadata:       Arbitrary stage-to-stage data.
        created_at:     When this context was created.
    """
    raw_input:      str
    state:          Any                  # ConversationState (typed in Sprint-002)
    resolved_input: str                  = ""
    decision:       Optional[Decision]   = None
    is_terminal:    bool                 = False
    metadata:       dict[str, Any]       = field(default_factory=dict)
    created_at:     datetime             = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        # resolved_input defaults to raw_input if not set
        if not self.resolved_input:
            self.resolved_input = self.raw_input

    def effective_input(self) -> str:
        """Return resolved_input if set, else raw_input."""
        return self.resolved_input or self.raw_input

    def terminate(self, decision: Decision) -> None:
        """
        Mark this context as terminal with a final decision.

        Called by stages that short-circuit the pipeline
        (e.g. recovery detected, slot filled).
        The decision must be passed in — stages never construct
        Decision objects independently.
        """
        self.decision = decision
        self.is_terminal = True

    def set_metadata(self, key: str, value: Any) -> None:
        """Store stage-to-stage metadata."""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve stage-to-stage metadata."""
        return self.metadata.get(key, default)

    def summary(self) -> dict:
        """Human-readable snapshot for debugging."""
        return {
            "raw_input":      self.raw_input,
            "resolved_input": self.resolved_input,
            "is_terminal":    self.is_terminal,
            "decision":       str(self.decision) if self.decision else None,
            "metadata_keys":  list(self.metadata.keys()),
        }