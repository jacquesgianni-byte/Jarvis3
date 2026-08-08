"""
TopicTracker — Genesis-043 Sprint-003 (PROP-0002)

Tracks topic history and topic confidence in the current conversation.

Solves the problem identified in PAPER-001:
    ConversationStateEngine.detect_focus_change() detected explicit topic
    switches but did not record topic history or confidence. Topic drift
    (implicit shift without "tell me about X") was not detected at all.

Design:
    - Owned by ConversationState (lives inside the canonical state object)
    - Written by ConversationStateEngine.update_topic()
    - Explicit shifts: "Tell me about X" → high confidence (0.92)
    - Implicit shifts: entity overlap drops between turns → lower confidence
    - Topic history: stack of prior topics, never deleted in session
    - No AI calls. Deterministic.

Architecture position:
    ConversationState
        └── topic_tracker: TopicTracker   ← this module

    ConversationStateEngine
        └── update_topic(name, session, confidence, explicit)
              └── calls ConversationState.topic_tracker.set(name, confidence, turn)

Genesis-043 Sprint-003.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Topic confidence thresholds
EXPLICIT_TOPIC_CONFIDENCE:  float = 0.92   # "Tell me about X"
IMPLICIT_TOPIC_CONFIDENCE:  float = 0.65   # detected from entity overlap
MIN_TOPIC_CONFIDENCE:       float = 0.30   # below this, topic is uncertain
ENTITY_OVERLAP_THRESHOLD:   float = 0.30   # overlap below this = topic shift


@dataclass
class TopicRecord:
    """
    A single topic in the conversation history.

    Attributes:
        name:       Topic name (lowercased canonical form).
        display:    Original casing as first set.
        confidence: How confident we are this is the actual topic.
        turn:       Turn when this topic was set.
        explicit:   True if set via explicit signal ("Tell me about X").
        entity_set: Set of entity names active when this topic was set.
                    Used to detect implicit drift in subsequent turns.
    """
    name:       str
    display:    str
    confidence: float
    turn:       int
    explicit:   bool          = False
    entity_set: frozenset     = field(default_factory=frozenset)

    @property
    def is_confident(self) -> bool:
        return self.confidence >= MIN_TOPIC_CONFIDENCE

    def overlap_with(self, other_entities: set[str]) -> float:
        """
        Compute entity overlap between this topic's entity set and a new set.
        Returns 0.0–1.0. Low overlap suggests a topic shift has occurred.
        """
        if not self.entity_set or not other_entities:
            return 0.0
        intersection = self.entity_set & other_entities
        union        = self.entity_set | other_entities
        return len(intersection) / len(union) if union else 0.0


class TopicTracker:
    """
    Tracks current topic and topic history for the conversation session.

    Owned by ConversationState.
    Written by ConversationStateEngine.update_topic().

    Public API:
        set(name, confidence, turn, explicit, entity_set)
        current → TopicRecord | None
        history → list[TopicRecord]
        detect_shift(new_entities, current_turn) → bool
        confidence → float
        reset()
        summary() → dict
    """

    def __init__(self) -> None:
        self._current:  Optional[TopicRecord] = None
        self._history:  list[TopicRecord]     = []

    # ── Write ──────────────────────────────────────────────────────────

    def set(
        self,
        name:       str,
        confidence: float,
        turn:       int,
        explicit:   bool         = False,
        entity_set: set[str]     = None,
    ) -> TopicRecord:
        """
        Set the current topic. Pushes the previous topic to history.

        Args:
            name:       Topic name (will be lowercased for canonical key).
            confidence: Confidence level (use EXPLICIT/IMPLICIT constants).
            turn:       Current conversation turn.
            explicit:   True if set via an explicit focus change signal.
            entity_set: Active entity names at this turn (for drift detection).
        """
        record = TopicRecord(
            name       = name.strip().lower(),
            display    = name.strip(),
            confidence = confidence,
            turn       = turn,
            explicit   = explicit,
            entity_set = frozenset(entity_set or set()),
        )

        if self._current is not None:
            # Only push to history if this is actually a different topic
            if self._current.name != record.name:
                self._history.append(self._current)
                logger.info(
                    "[TOPIC] Shift: %r → %r (conf=%.2f, explicit=%s, turn=%d)",
                    self._current.display, record.display,
                    confidence, explicit, turn,
                )
            else:
                # Same topic — update confidence only
                logger.debug("[TOPIC] Refreshed: %r (conf=%.2f)", record.display, confidence)
        else:
            logger.info("[TOPIC] Set: %r (conf=%.2f, turn=%d)", record.display, confidence, turn)

        self._current = record
        return record

    # ── Read ───────────────────────────────────────────────────────────

    @property
    def current(self) -> Optional[TopicRecord]:
        """The current active topic, or None."""
        return self._current

    @property
    def current_name(self) -> Optional[str]:
        """Current topic display name, or None."""
        return self._current.display if self._current else None

    @property
    def current_confidence(self) -> float:
        """Current topic confidence, or 0.0 if no topic set."""
        return self._current.confidence if self._current else 0.0

    @property
    def history(self) -> list[TopicRecord]:
        """Read-only view of prior topics (oldest first)."""
        return list(self._history)

    @property
    def history_names(self) -> list[str]:
        """Display names of prior topics (oldest first)."""
        return [t.display for t in self._history]

    def previous(self) -> Optional[TopicRecord]:
        """The most recent prior topic, or None."""
        return self._history[-1] if self._history else None

    # ── Shift detection ────────────────────────────────────────────────

    def detect_shift(
        self,
        new_entities:  set[str],
        current_turn:  int,
    ) -> bool:
        """
        Detect an implicit topic shift based on entity overlap.

        An implicit shift is detected when:
        1. There IS a current topic with an entity_set
        2. The new entity set overlaps poorly with the current topic's entities
        3. The current topic was not set very recently (at least 2 turns ago)

        This is a signal only — ConversationStateEngine decides what to do.

        Args:
            new_entities:  Set of entity names mentioned in the current turn.
            current_turn:  The current conversation turn number.

        Returns:
            True if an implicit topic shift is likely.
        """
        if self._current is None:
            return False
        if not self._current.entity_set or not new_entities:
            return False
        # Don't fire on the same turn the topic was set
        if current_turn - self._current.turn < 2:
            return False

        overlap = self._current.overlap_with(new_entities)
        shift   = overlap < ENTITY_OVERLAP_THRESHOLD
        if shift:
            logger.info(
                "[TOPIC] Implicit shift detected: overlap=%.2f (<%s) current=%r",
                overlap, ENTITY_OVERLAP_THRESHOLD, self._current.display,
            )
        return shift

    # ── Session management ─────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all topic state. Called on session reset."""
        self._current = None
        self._history = []
        logger.info("[TOPIC] Tracker reset.")

    def count(self) -> int:
        """Total distinct topics seen this session (current + history)."""
        return len(self._history) + (1 if self._current else 0)

    def summary(self) -> dict:
        return {
            "current":    self._current.display if self._current else None,
            "confidence": self._current.confidence if self._current else 0.0,
            "explicit":   self._current.explicit if self._current else False,
            "turn":       self._current.turn if self._current else None,
            "history":    self.history_names,
            "total":      self.count(),
        }
