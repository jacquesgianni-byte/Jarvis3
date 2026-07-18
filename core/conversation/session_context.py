"""
Jarvis Session Context Model (Genesis-020 Sprint-002 — Revised)

In-memory working memory for the current conversation session.

Design:
    Long-term memory  → KnowledgeEngine (persisted to disk)
    Working memory    → SessionContext  (in-memory, session-only)

Key design decisions (post-review):
    - Natural decay: slot weight decays linearly per turn so stale
      context fades rather than dropping to zero at a hard threshold.
    - Confidence-aware: each slot carries a confidence value set at
      write time and reduced by decay on reads.
    - Shared workspace: owned by JarvisCore so future Workers can
      read the same context without passing parameters.
    - Never mutated by resolvers: resolvers read; only ContextManager writes.

Decay model:
    effective_confidence = slot.confidence * max(0, 1 - turns_elapsed / DECAY_TURNS)
    A slot set 5 turns ago at confidence=0.9 with DECAY_TURNS=10
    has effective_confidence = 0.9 * (1 - 5/10) = 0.45
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


DECAY_TURNS: int = 10          # turns over which a slot decays to zero
MIN_CONFIDENCE: float = 0.20   # below this, slot is treated as absent


@dataclass
class ContextSlot:
    """
    A single active context slot with decay-aware confidence.

    Attributes:
        value:      The resolved value ("Claude", "Genesis-020", etc.)
        raw:        The original text that triggered this slot being set.
        turn:       Turn counter when this slot was last set/refreshed.
        confidence: Confidence at write time (0.0–1.0).
    """
    value:      str
    raw:        str   = ""
    turn:       int   = 0
    confidence: float = 1.0

    def __str__(self) -> str:
        return self.value

    def effective_confidence(self, current_turn: int) -> float:
        """
        Return confidence adjusted for natural decay.

        Confidence decays linearly from its original value to zero
        over DECAY_TURNS turns. Never goes negative.
        """
        elapsed = current_turn - self.turn
        decay = max(0.0, 1.0 - elapsed / DECAY_TURNS)
        return round(self.confidence * decay, 4)

    def is_usable(self, current_turn: int) -> bool:
        """True if effective confidence is above the minimum threshold."""
        return self.effective_confidence(current_turn) >= MIN_CONFIDENCE


@dataclass
class SessionContext:
    """
    In-memory working memory for the current conversation session.

    Tracks what the conversation is currently about so that
    ambiguous references ("it", "him", "the project") can be
    resolved deterministically without calling the AI.

    Owned by JarvisCore — not the Agent — so future Workers can
    share the same workspace without parameter passing.

    All slots are Optional[ContextSlot]. None means nothing is
    currently in focus for that dimension.
    """

    active_project:   Optional[ContextSlot] = field(default=None)
    active_milestone: Optional[ContextSlot] = field(default=None)
    active_task:      Optional[ContextSlot] = field(default=None)
    active_person:    Optional[ContextSlot] = field(default=None)
    active_topic:     Optional[ContextSlot] = field(default=None)

    _turn: int = field(default=0, repr=False)

    def increment_turn(self) -> None:
        """Advance the turn counter. Called once per conversation turn."""
        self._turn += 1

    @property
    def current_turn(self) -> int:
        return self._turn

    def is_usable(self, slot: Optional[ContextSlot]) -> bool:
        """Return True if slot exists and has sufficient effective confidence."""
        if slot is None:
            return False
        return slot.is_usable(self._turn)

    def fresh(self, slot: Optional[ContextSlot]) -> Optional[ContextSlot]:
        """Return slot if usable, otherwise None."""
        return slot if self.is_usable(slot) else None

    def effective_confidence(self, slot: Optional[ContextSlot]) -> float:
        """Return effective confidence for a slot (0.0 if None/stale)."""
        if slot is None:
            return 0.0
        return slot.effective_confidence(self._turn)

    # ------------------------------------------------------------------
    # Slot setters — always go through here so turn is recorded
    # ------------------------------------------------------------------

    def set_project(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self.active_project = ContextSlot(value=value, raw=raw,
                                          turn=self._turn, confidence=confidence)

    def set_milestone(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self.active_milestone = ContextSlot(value=value, raw=raw,
                                            turn=self._turn, confidence=confidence)

    def set_task(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self.active_task = ContextSlot(value=value, raw=raw,
                                       turn=self._turn, confidence=confidence)

    def set_person(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self.active_person = ContextSlot(value=value, raw=raw,
                                         turn=self._turn, confidence=confidence)

    def set_topic(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self.active_topic = ContextSlot(value=value, raw=raw,
                                        turn=self._turn, confidence=confidence)

    def reset(self) -> None:
        """Clear all active context slots. Called on session end."""
        self.active_project   = None
        self.active_milestone = None
        self.active_task      = None
        self.active_person    = None
        self.active_topic     = None
        self._turn = 0

    def summary(self) -> dict:
        """Human-readable summary for debugging and the Context Inspector."""
        def slot_info(slot):
            if slot is None:
                return None
            ec = slot.effective_confidence(self._turn)
            return {"value": slot.value, "confidence": ec, "turn": slot.turn}

        return {
            "turn":      self._turn,
            "project":   slot_info(self.active_project),
            "milestone": slot_info(self.active_milestone),
            "task":      slot_info(self.active_task),
            "person":    slot_info(self.active_person),
            "topic":     slot_info(self.active_topic),
        }