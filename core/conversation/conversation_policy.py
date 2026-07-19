"""
Jarvis Conversation Policy (Genesis-022 Sprint-002)

Centralises all confidence thresholds and ambiguity rules for the
Conversation Engine. No threshold values are hard-coded anywhere else.

Future components must query ConversationPolicy rather than embedding
policy logic inline. This ensures that tuning conversation behaviour
requires changes in exactly one place.

Design constraints:
    - No AI calls.
    - No routing.
    - No Worker calls.
    - Fully deterministic.
    - All thresholds are configurable at construction time.
    - Default thresholds reflect conservative, safe behaviour.

Policy responsibilities:
    - Reference resolution threshold (how confident must we be to resolve?)
    - Ambiguity threshold (when is confidence too low to act?)
    - Clarification threshold (when should we ask rather than assume?)
    - Confirmation threshold (when is an action risky enough to confirm first?)
    - Maximum turns before topic reset
    - Slot TTL defaults
    - Turn history window size

Usage:
    policy = ConversationPolicy()

    if policy.should_resolve(resolution_confidence=0.85):
        # perform resolution
        ...

    if policy.is_ambiguous(decision_confidence=0.45):
        # ask for clarification
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class PolicyThresholds:
    """
    Immutable snapshot of all policy thresholds.

    Returned by ConversationPolicy.snapshot() for inspection
    and testing without exposing mutable internals.
    """
    resolution_threshold:    float
    ambiguity_threshold:     float
    clarification_threshold: float
    confirmation_threshold:  float
    max_topic_turns:         int
    default_slot_ttl:        int
    max_turn_history:        int


class ConversationPolicy:
    """
    Centralised conversation decision thresholds.

    All confidence checks in the Conversation Engine pipeline
    go through this class. No component embeds raw float comparisons.

    Default thresholds (conservative, safe):
        resolution_threshold:    0.75  — minimum confidence to resolve a reference
        ambiguity_threshold:     0.60  — below this, decision is ambiguous
        clarification_threshold: 0.50  — below this, ask for clarification
        confirmation_threshold:  0.85  — above this for risky actions, require confirm
        max_topic_turns:         10    — turns before topic is considered stale
        default_slot_ttl:        300   — seconds before a pending slot expires
        max_turn_history:        20    — turns kept in ConversationState history

    All thresholds are validated at construction:
        - Confidence thresholds must be in [0.0, 1.0]
        - Integer thresholds must be positive
        - Resolution >= ambiguity >= clarification (logical ordering)
    """

    def __init__(
        self,
        resolution_threshold:    float = 0.75,
        ambiguity_threshold:     float = 0.60,
        clarification_threshold: float = 0.50,
        confirmation_threshold:  float = 0.85,
        max_topic_turns:         int   = 10,
        default_slot_ttl:        int   = 300,
        max_turn_history:        int   = 20,
    ) -> None:
        self._validate_thresholds(
            resolution_threshold,
            ambiguity_threshold,
            clarification_threshold,
            confirmation_threshold,
            max_topic_turns,
            default_slot_ttl,
            max_turn_history,
        )
        self._resolution_threshold    = resolution_threshold
        self._ambiguity_threshold     = ambiguity_threshold
        self._clarification_threshold = clarification_threshold
        self._confirmation_threshold  = confirmation_threshold
        self._max_topic_turns         = max_topic_turns
        self._default_slot_ttl        = default_slot_ttl
        self._max_turn_history        = max_turn_history

    # ------------------------------------------------------------------
    # Reference resolution
    # ------------------------------------------------------------------

    def should_resolve(self, resolution_confidence: float) -> bool:
        """
        Return True if a reference resolution should be applied.

        Resolution is only applied when confidence is at or above the
        resolution threshold. Below threshold, the original input is
        used unchanged.

        Args:
            resolution_confidence: Confidence score from ReferenceResolver.
        """
        return resolution_confidence >= self._resolution_threshold

    @property
    def resolution_threshold(self) -> float:
        """Minimum confidence required to apply a reference resolution."""
        return self._resolution_threshold

    # ------------------------------------------------------------------
    # Ambiguity
    # ------------------------------------------------------------------

    def is_ambiguous(self, decision_confidence: float) -> bool:
        """
        Return True if a decision confidence is too low to act on directly.

        When ambiguous, the engine should ask for clarification rather
        than proceeding with a potentially wrong interpretation.

        Args:
            decision_confidence: Confidence score from ConversationRouter.
        """
        return decision_confidence < self._ambiguity_threshold

    @property
    def ambiguity_threshold(self) -> float:
        """Confidence below which a decision is considered ambiguous."""
        return self._ambiguity_threshold

    # ------------------------------------------------------------------
    # Clarification
    # ------------------------------------------------------------------

    def requires_clarification(self, decision_confidence: float) -> bool:
        """
        Return True if confidence is so low that we must ask before acting.

        Clarification threshold is stricter than ambiguity — below this
        level the engine should always ask rather than guess.

        Args:
            decision_confidence: Confidence score from ConversationRouter.
        """
        return decision_confidence < self._clarification_threshold

    @property
    def clarification_threshold(self) -> float:
        """Confidence below which clarification is always required."""
        return self._clarification_threshold

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def requires_confirmation(
        self,
        decision_confidence: float,
        is_destructive: bool = False,
    ) -> bool:
        """
        Return True if an action requires explicit user confirmation.

        Confirmation is required when:
            - The action is destructive (is_destructive=True), OR
            - Confidence is at or above the confirmation threshold
              AND the action would trigger irreversible downstream work.

        In Genesis-022, this is used to gate INVOKE_WORKER decisions
        that would kick off multi-step workflows.

        Args:
            decision_confidence: Router confidence in the decision.
            is_destructive:      True if the action could cause harm if wrong.
        """
        if is_destructive:
            return True
        return decision_confidence >= self._confirmation_threshold

    @property
    def confirmation_threshold(self) -> float:
        """Confidence above which high-stakes actions require confirmation."""
        return self._confirmation_threshold

    # ------------------------------------------------------------------
    # Topic staleness
    # ------------------------------------------------------------------

    def is_topic_stale(self, turns_since_topic_set: int) -> bool:
        """
        Return True if the current topic has been active too long
        without being refreshed.

        A stale topic suggests the conversation has moved on and the
        topic reference should be cleared.

        Args:
            turns_since_topic_set: How many turns since the topic was last set.
        """
        return turns_since_topic_set >= self._max_topic_turns

    @property
    def max_topic_turns(self) -> int:
        """Maximum turns before a topic is considered stale."""
        return self._max_topic_turns

    # ------------------------------------------------------------------
    # Slot and history configuration
    # ------------------------------------------------------------------

    @property
    def default_slot_ttl(self) -> int:
        """Default TTL (seconds) for pending conversation slots."""
        return self._default_slot_ttl

    @property
    def max_turn_history(self) -> int:
        """Maximum number of turns kept in ConversationState history."""
        return self._max_turn_history

    # ------------------------------------------------------------------
    # Batch confidence checks
    # ------------------------------------------------------------------

    def classify_confidence(self, confidence: float) -> str:
        """
        Classify a confidence score into a human-readable band.

        Returns one of: "high", "medium", "low", "very_low"

        Used for logging and debugging rather than routing decisions.
        """
        if confidence >= self._confirmation_threshold:
            return "high"
        if confidence >= self._resolution_threshold:
            return "medium"
        if confidence >= self._clarification_threshold:
            return "low"
        return "very_low"

    def best_of(self, confidences: list[float]) -> Optional[float]:
        """
        Return the highest confidence from a list, or None if list is empty.

        Utility for stages that produce multiple candidate resolutions.
        """
        if not confidences:
            return None
        return max(confidences)

    # ------------------------------------------------------------------
    # Snapshot / debug
    # ------------------------------------------------------------------

    def snapshot(self) -> PolicyThresholds:
        """Return an immutable snapshot of all policy thresholds."""
        return PolicyThresholds(
            resolution_threshold=self._resolution_threshold,
            ambiguity_threshold=self._ambiguity_threshold,
            clarification_threshold=self._clarification_threshold,
            confirmation_threshold=self._confirmation_threshold,
            max_topic_turns=self._max_topic_turns,
            default_slot_ttl=self._default_slot_ttl,
            max_turn_history=self._max_turn_history,
        )

    def summary(self) -> dict:
        """Human-readable policy summary for debugging."""
        return {
            "resolution_threshold":    self._resolution_threshold,
            "ambiguity_threshold":     self._ambiguity_threshold,
            "clarification_threshold": self._clarification_threshold,
            "confirmation_threshold":  self._confirmation_threshold,
            "max_topic_turns":         self._max_topic_turns,
            "default_slot_ttl":        self._default_slot_ttl,
            "max_turn_history":        self._max_turn_history,
        }

    def __repr__(self) -> str:
        return (
            f"ConversationPolicy("
            f"resolution={self._resolution_threshold}, "
            f"ambiguity={self._ambiguity_threshold}, "
            f"clarification={self._clarification_threshold}, "
            f"confirmation={self._confirmation_threshold}"
            f")"
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_thresholds(
        resolution: float,
        ambiguity: float,
        clarification: float,
        confirmation: float,
        max_topic_turns: int,
        default_slot_ttl: int,
        max_turn_history: int,
    ) -> None:
        """Validate all threshold values at construction time."""
        for name, value in [
            ("resolution_threshold",    resolution),
            ("ambiguity_threshold",     ambiguity),
            ("clarification_threshold", clarification),
            ("confirmation_threshold",  confirmation),
        ]:
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a number, got {type(value).__name__}")
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0.0, 1.0], got {value}")

        for name, value in [
            ("max_topic_turns",  max_topic_turns),
            ("default_slot_ttl", default_slot_ttl),
            ("max_turn_history", max_turn_history),
        ]:
            if not isinstance(value, int):
                raise TypeError(f"{name} must be an int, got {type(value).__name__}")
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")

        # Logical ordering: resolution >= ambiguity >= clarification
        if resolution < ambiguity:
            raise ValueError(
                f"resolution_threshold ({resolution}) must be >= "
                f"ambiguity_threshold ({ambiguity})"
            )
        if ambiguity < clarification:
            raise ValueError(
                f"ambiguity_threshold ({ambiguity}) must be >= "
                f"clarification_threshold ({clarification})"
            )