"""
SessionContextAdapter — Genesis-043 Sprint-001

DEPRECATED — Genesis-044 Sprint-002

This adapter has been retired from active runtime use.
Agent.session now points directly to ConversationState (jarvis_state).

This file is retained ONLY because existing test files import it directly.
It will be deleted once all test references are updated.

DO NOT use this adapter in new code.
DO NOT pass this adapter to any component.
DO NOT add new methods here.
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState, ContextSlot


class SessionContextAdapter:
    """
    Temporary compatibility adapter — retired in Genesis-044 Sprint-001.
    Delegates all reads/writes to ConversationState.
    """

    def __init__(self, state: "ConversationState") -> None:
        self._s = state

    # ── ContextSlot properties ─────────────────────────────────────────

    @property
    def active_person(self) -> Optional["ContextSlot"]:
        return self._s.active_person

    @active_person.setter
    def active_person(self, slot: Optional["ContextSlot"]) -> None:
        self._s._active_person = slot

    @property
    def active_topic(self) -> Optional["ContextSlot"]:
        return self._s.active_topic

    @active_topic.setter
    def active_topic(self, slot: Optional["ContextSlot"]) -> None:
        self._s._active_topic = slot

    @property
    def active_project(self) -> Optional["ContextSlot"]:
        return self._s.active_project

    @active_project.setter
    def active_project(self, slot: Optional["ContextSlot"]) -> None:
        self._s._active_project = slot

    @property
    def active_task(self) -> Optional["ContextSlot"]:
        return self._s.active_task

    @active_task.setter
    def active_task(self, slot: Optional["ContextSlot"]) -> None:
        self._s._active_task = slot

    @property
    def active_milestone(self) -> Optional["ContextSlot"]:
        return self._s.active_milestone

    @active_milestone.setter
    def active_milestone(self, slot: Optional["ContextSlot"]) -> None:
        self._s._active_milestone = slot

    # ── Turn counter ───────────────────────────────────────────────────

    @property
    def current_turn(self) -> int:
        return self._s.current_turn

    def increment_turn(self) -> None:
        self._s.increment_turn()

    # ── ContextSlot helpers ────────────────────────────────────────────

    def is_usable(self, slot) -> bool:
        return self._s.is_usable(slot)

    def fresh(self, slot):
        return self._s.fresh(slot)

    def effective_confidence(self, slot) -> float:
        return self._s.effective_confidence(slot)

    # ── Slot setters ───────────────────────────────────────────────────

    def set_person(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._s.set_person(value, raw, confidence)

    def set_topic(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._s.set_active_topic(value, raw, confidence)

    def set_active_topic(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        """Alias for set_topic — direct ConversationState API name."""
        self._s.set_active_topic(value, raw, confidence)

    def set_project(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._s.set_project(value, raw, confidence)

    def set_task(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._s.set_task(value, raw, confidence)

    def set_milestone(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._s.set_milestone(value, raw, confidence)

    # ── Follow-up context ──────────────────────────────────────────────

    @property
    def last_intent(self) -> Optional[str]:
        return self._s.last_intent

    @last_intent.setter
    def last_intent(self, value: Optional[str]) -> None:
        self._s._last_intent = value

    @property
    def last_response(self) -> Optional[str]:
        return self._s.last_response

    @last_response.setter
    def last_response(self, value: Optional[str]) -> None:
        self._s._last_response = value

    @property
    def last_topic(self) -> Optional[str]:
        return self._s.last_topic

    @last_topic.setter
    def last_topic(self, value: Optional[str]) -> None:
        self._s._last_topic = value

    def set_last_turn(self, intent: str, response: str, topic: str = "") -> None:
        self._s.set_last_turn(intent, response, topic)

    # ── Reset ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Resets the context slots on the underlying ConversationState."""
        self._s._ctx_turn         = 0
        self._s._active_person    = None
        self._s._active_topic     = None
        self._s._active_project   = None
        self._s._active_task      = None
        self._s._active_milestone = None
        self._s._last_intent      = None
        self._s._last_response    = None
        self._s._last_topic       = None

    # ── Summary ────────────────────────────────────────────────────────

    def summary(self) -> dict:
        def slot_info(slot):
            if slot is None:
                return None
            ec = slot.effective_confidence(self._s.current_turn)
            return {"value": slot.value, "confidence": ec, "turn": slot.turn}
        return {
            "turn":      self._s.current_turn,
            "project":   slot_info(self._s.active_project),
            "milestone": slot_info(self._s.active_milestone),
            "task":      slot_info(self._s.active_task),
            "person":    slot_info(self._s.active_person),
            "topic":     slot_info(self._s.active_topic),
        }
