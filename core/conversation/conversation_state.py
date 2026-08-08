"""
Jarvis Conversation State
Genesis-022 Sprint-002 (original) — evolved in Genesis-043 Sprint-001

THE canonical owner of all conversational state.

Genesis-043 additions:
    - ContextSlot: decay-aware slot model (migrated from session_context.py)
    - active_person / active_topic / active_project / active_task / active_milestone
    - current_turn counter with decay support
    - last_intent / last_response / last_topic (migrated from session_context.py)
    - recent_entities list (migrated from Agent._recent_entities)
    - dialogue_act: current dialogue act (inform/clarify/confirm/ask)
    - session_summary: compressed text summary (populated in Genesis-043 S4)

Migration note:
    SessionContext is now a compatibility adapter (SessionContextAdapter).
    It delegates all reads/writes to this class.
    It will be retired in Genesis-044 Sprint-001.

Design constraints:
    - In-memory only. No persistence.
    - No KnowledgeEngine integration.
    - No Worker integration.
    - No AI calls.
    - Mutable by design.
    - All public models stored are immutable (Slot, Topic, ContextSlot).
      State mutates by replacing them, never by mutating them in place.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Any, Optional

from core.conversation.conversation_models import (
    ConversationTurn, Decision, Slot, SlotStatus, Topic,
)


# ---------------------------------------------------------------------------
# ConversationMode
# ---------------------------------------------------------------------------

class ConversationMode(Enum):
    """
    The current operational mode of the conversation.

    NORMAL:           Standard input → Decision routing.
    AWAITING_ANSWER:  A question has been asked; next input is an answer.
    RECOVERING:       Processing a "never mind" / interruption.
    CONFIRMING:       Waiting for yes/no confirmation before acting.
    """
    NORMAL          = auto()
    AWAITING_ANSWER = auto()
    RECOVERING      = auto()
    CONFIRMING      = auto()

    def label(self) -> str:
        return self.name.replace("_", " ").title()


# ---------------------------------------------------------------------------
# ContextSlot  (Genesis-043 Sprint-001 — migrated from session_context.py)
# ---------------------------------------------------------------------------

DECAY_TURNS: int = 10
MIN_CONFIDENCE: float = 0.20


@dataclass
class ContextSlot:
    """
    A single active context slot with decay-aware confidence.

    Migrated from session_context.py in Genesis-043 Sprint-001.
    session_context.py re-exports this class for backward compatibility.

    Attributes:
        value:      The resolved value ("Claude", "Genesis-020", etc.)
        raw:        The original text that triggered this slot.
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
        elapsed = current_turn - self.turn
        decay   = max(0.0, 1.0 - elapsed / DECAY_TURNS)
        return round(self.confidence * decay, 4)

    def is_usable(self, current_turn: int) -> bool:
        return self.effective_confidence(current_turn) >= MIN_CONFIDENCE


# ---------------------------------------------------------------------------
# ReferenceContext  (Genesis-022 — kept for ConversationEngine pipeline)
# NOTE: Nothing outside the Genesis-022 pipeline writes to this at runtime.
#       It will be retired in Genesis-044 once ConversationEngine is unified.
# ---------------------------------------------------------------------------

@dataclass
class ReferenceContext:
    """
    Tracks what ambiguous references currently point to.
    Used inside the ConversationEngine pipeline (Genesis-022).
    Will be retired in Genesis-044.
    """
    current_it:      Optional[str] = None
    current_person:  Optional[str] = None
    current_project: Optional[str] = None
    current_task:    Optional[str] = None
    last_entity:     Optional[str] = None

    def update(self, **kwargs: str) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def clear(self) -> None:
        self.current_it      = None
        self.current_person  = None
        self.current_project = None
        self.current_task    = None
        self.last_entity     = None

    def summary(self) -> dict:
        return {
            "it":      self.current_it,
            "person":  self.current_person,
            "project": self.current_project,
            "task":    self.current_task,
            "entity":  self.last_entity,
        }


# ---------------------------------------------------------------------------
# ConversationState — canonical owner of all conversational state
# ---------------------------------------------------------------------------

class ConversationState:
    """
    THE canonical owner of all conversational state.

    Genesis-022: mode, slots, turns, topic history, reference context.
    Genesis-043: ContextSlots (person/topic/project/task/milestone),
                 turn counter with decay, last_intent/response/topic,
                 recent_entities, dialogue_act, session_summary.

    SessionContextAdapter reads/writes this object during the Genesis-043
    migration period. All other components will be updated to read this
    directly in Genesis-044.

    Public API (Genesis-022, unchanged):
        set_topic / clear_topic / push_topic / pop_topic
        set_mode / is_mode
        set_pending / clear_pending / has_pending
        add_slot / fill_slot / get_slot / active_slots / filled_slots
        add_turn / recent_turns / last_turn
        update_reference / clear_references
        set_metadata / get_metadata
        reset / summary

    Public API (Genesis-043, new):
        set_person / set_topic_slot / set_project / set_task / set_milestone
        increment_turn / current_turn
        is_usable / fresh / effective_confidence
        set_last_turn
        add_recent_entity
        active_person / active_topic / active_project / active_task / active_milestone
        last_intent / last_response / last_topic
        recent_entities
        dialogue_act / set_dialogue_act
        session_summary / set_session_summary
    """

    DEFAULT_MAX_TURNS:        int = 20
    DEFAULT_MAX_RECENT_ENTS:  int = 5

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        # ── Genesis-022 fields ─────────────────────────────────────────
        self._max_turns:      int                    = max_turns
        self._mode:           ConversationMode       = ConversationMode.NORMAL
        self._current_topic:  Optional[Topic]        = None
        self._topic_history:  list[Topic]            = []
        self._pending:        Optional[Slot]         = None
        self._slots:          dict[str, Slot]        = {}
        self._turns:          list[ConversationTurn] = []
        self._references:     ReferenceContext       = ReferenceContext()
        self._metadata:       dict[str, Any]         = {}
        self._turn_count:     int                    = 0
        self._created_at:     datetime               = datetime.now(UTC)
        self._last_updated:   datetime               = datetime.now(UTC)

        # ── Genesis-043 fields (migrated from SessionContext) ──────────
        self._ctx_turn:       int                        = 0
        self._active_person:  Optional[ContextSlot]     = None
        self._active_topic:   Optional[ContextSlot]     = None
        self._active_project: Optional[ContextSlot]     = None
        self._active_task:    Optional[ContextSlot]     = None
        self._active_milestone: Optional[ContextSlot]   = None

        # ── Genesis-043 fields (migrated from Agent._recent_entities) ──
        self._recent_entities: list[str]                = []

        # ── Genesis-043 fields (migrated from SessionContext follow-up) ─
        self._last_intent:    Optional[str]             = None
        self._last_response:  Optional[str]             = None
        self._last_topic:     Optional[str]             = None

        # ── Genesis-043 new fields (PAPER-001) ─────────────────────────
        self._dialogue_act:   str                       = "inform"
        self._session_summary: str                      = ""

        # ── Genesis-043 Sprint-002: EntityRegistry (PROP-0001) ─────────
        from core.conversation.entity_registry import EntityRegistry
        self.entity_registry: EntityRegistry            = EntityRegistry()

        # ── Genesis-043 Sprint-003: TopicTracker (PROP-0002) ────────────
        from core.conversation.topic_tracker import TopicTracker
        self.topic_tracker: TopicTracker                = TopicTracker()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _touch(self) -> None:
        self._last_updated = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Genesis-043: Turn counter (used by ContextSlot decay)
    # ------------------------------------------------------------------

    def increment_turn(self) -> None:
        """Advance the context turn counter. Called once per conversation turn."""
        self._ctx_turn += 1

    @property
    def current_turn(self) -> int:
        """Current context turn (used for ContextSlot decay calculation)."""
        return self._ctx_turn

    # ------------------------------------------------------------------
    # Genesis-043: ContextSlot helpers
    # ------------------------------------------------------------------

    def is_usable(self, slot: Optional[ContextSlot]) -> bool:
        if slot is None:
            return False
        return slot.is_usable(self._ctx_turn)

    def fresh(self, slot: Optional[ContextSlot]) -> Optional[ContextSlot]:
        return slot if self.is_usable(slot) else None

    def effective_confidence(self, slot: Optional[ContextSlot]) -> float:
        if slot is None:
            return 0.0
        return slot.effective_confidence(self._ctx_turn)

    # ------------------------------------------------------------------
    # Genesis-043: Active context slots
    # ------------------------------------------------------------------

    @property
    def active_person(self) -> Optional[ContextSlot]:
        return self._active_person

    @property
    def active_topic(self) -> Optional[ContextSlot]:
        return self._active_topic

    @property
    def active_project(self) -> Optional[ContextSlot]:
        return self._active_project

    @property
    def active_task(self) -> Optional[ContextSlot]:
        return self._active_task

    @property
    def active_milestone(self) -> Optional[ContextSlot]:
        return self._active_milestone

    # Setters — always record the current ctx_turn
    def set_person(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._active_person = ContextSlot(
            value=value, raw=raw, turn=self._ctx_turn, confidence=confidence
        )
        self._touch()

    def set_topic_slot(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        """Set active_topic as a ContextSlot (different from set_topic which sets Topic object)."""
        self._active_topic = ContextSlot(
            value=value, raw=raw, turn=self._ctx_turn, confidence=confidence
        )
        self._touch()

    def set_project(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._active_project = ContextSlot(
            value=value, raw=raw, turn=self._ctx_turn, confidence=confidence
        )
        self._touch()

    def set_task(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._active_task = ContextSlot(
            value=value, raw=raw, turn=self._ctx_turn, confidence=confidence
        )
        self._touch()

    def set_milestone(self, value: str, raw: str = "", confidence: float = 1.0) -> None:
        self._active_milestone = ContextSlot(
            value=value, raw=raw, turn=self._ctx_turn, confidence=confidence
        )
        self._touch()

    # ------------------------------------------------------------------
    # Genesis-043: Follow-up context (migrated from SessionContext)
    # ------------------------------------------------------------------

    @property
    def last_intent(self) -> Optional[str]:
        return self._last_intent

    @property
    def last_response(self) -> Optional[str]:
        return self._last_response

    @property
    def last_topic(self) -> Optional[str]:
        return self._last_topic

    def set_last_turn(self, intent: str, response: str, topic: str = "") -> None:
        """Record last turn context. Called by Agent._post_turn()."""
        self._last_intent   = intent
        self._last_response = response
        self._last_topic    = topic or self._last_topic
        self._touch()

    # ------------------------------------------------------------------
    # Genesis-043: Recent entities (migrated from Agent._recent_entities)
    # ------------------------------------------------------------------

    @property
    def recent_entities(self) -> list[str]:
        return list(self._recent_entities)

    def add_recent_entity(self, entity: str) -> None:
        """Add entity to recent list. Caps at DEFAULT_MAX_RECENT_ENTS."""
        if entity not in self._recent_entities:
            self._recent_entities.append(entity)
        if len(self._recent_entities) > self.DEFAULT_MAX_RECENT_ENTS:
            self._recent_entities.pop(0)

    def clear_recent_entities(self) -> None:
        self._recent_entities = []

    # ------------------------------------------------------------------
    # Genesis-043: Dialogue act (PAPER-001)
    # ------------------------------------------------------------------

    @property
    def dialogue_act(self) -> str:
        """Current dialogue act: inform / clarify / confirm / ask."""
        return self._dialogue_act

    def set_dialogue_act(self, act: str) -> None:
        self._dialogue_act = act
        self._touch()

    # ------------------------------------------------------------------
    # Genesis-043: Session summary (PAPER-001 — populated in Sprint-004)
    # ------------------------------------------------------------------

    @property
    def session_summary(self) -> str:
        return self._session_summary

    def set_session_summary(self, summary: str) -> None:
        self._session_summary = summary
        self._touch()

    # ------------------------------------------------------------------
    # Genesis-022: Topic management (unchanged)
    # ------------------------------------------------------------------

    @property
    def current_topic(self) -> Optional[Topic]:
        return self._current_topic

    def set_topic(self, topic: Topic) -> None:
        self._current_topic = topic
        self._touch()

    def clear_topic(self) -> None:
        self._current_topic = None
        self._touch()

    def push_topic(self, topic: Topic) -> None:
        if self._current_topic is not None:
            self._topic_history.append(self._current_topic)
        self._current_topic = topic
        self._touch()

    def pop_topic(self) -> Optional[Topic]:
        if not self._topic_history:
            self._current_topic = None
            return None
        self._current_topic = self._topic_history.pop()
        self._touch()
        return self._current_topic

    @property
    def topic_history(self) -> list[Topic]:
        return list(self._topic_history)

    # ------------------------------------------------------------------
    # Genesis-022: Mode management (unchanged)
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ConversationMode:
        return self._mode

    def set_mode(self, mode: ConversationMode) -> None:
        self._mode = mode
        self._touch()

    def is_mode(self, mode: ConversationMode) -> bool:
        return self._mode == mode

    # ------------------------------------------------------------------
    # Genesis-022: Pending question (unchanged)
    # ------------------------------------------------------------------

    def set_pending(self, slot: Slot) -> None:
        self._pending = slot
        self._mode = ConversationMode.AWAITING_ANSWER
        self._touch()

    def clear_pending(self) -> None:
        self._pending = None
        if self._mode == ConversationMode.AWAITING_ANSWER:
            self._mode = ConversationMode.NORMAL
        self._touch()

    def has_pending(self) -> bool:
        if self._pending is None:
            return False
        if self._pending.is_expired():
            self.clear_pending()
            return False
        return True

    @property
    def pending_slot(self) -> Optional[Slot]:
        if not self.has_pending():
            return None
        return self._pending

    # ------------------------------------------------------------------
    # Genesis-022: Slot management (unchanged)
    # ------------------------------------------------------------------

    def add_slot(self, slot: Slot) -> None:
        self._slots[slot.name] = slot
        self._touch()

    def fill_slot(self, name: str, value: str) -> Slot:
        if name not in self._slots:
            raise KeyError(f"Slot {name!r} not found.")
        filled = self._slots[name].fill(value)
        self._slots[name] = filled
        self._touch()
        return filled

    def get_slot(self, name: str) -> Optional[Slot]:
        return self._slots.get(name)

    def active_slots(self) -> list[Slot]:
        return [
            s for s in self._slots.values()
            if s.status == SlotStatus.EMPTY and not s.is_expired()
        ]

    def filled_slots(self) -> list[Slot]:
        return [s for s in self._slots.values() if s.status == SlotStatus.FILLED]

    def all_slots(self) -> list[Slot]:
        return list(self._slots.values())

    def clear_slots(self) -> None:
        self._slots.clear()
        self._touch()

    # ------------------------------------------------------------------
    # Genesis-022: Turn history (unchanged)
    # ------------------------------------------------------------------

    def add_turn(self, turn: ConversationTurn) -> None:
        self._turns.append(turn)
        self._turn_count += 1
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._touch()

    def recent_turns(self, n: int = 5) -> list[ConversationTurn]:
        return list(self._turns[-n:])

    def last_turn(self) -> Optional[ConversationTurn]:
        return self._turns[-1] if self._turns else None

    @property
    def turn_count(self) -> int:
        return self._turn_count

    # ------------------------------------------------------------------
    # Genesis-022: Reference context (unchanged — retired in Genesis-044)
    # ------------------------------------------------------------------

    def update_reference(self, **kwargs: str) -> None:
        self._references.update(**kwargs)
        self._touch()

    def clear_references(self) -> None:
        self._references.clear()
        self._touch()

    @property
    def references(self) -> ReferenceContext:
        return self._references

    # ------------------------------------------------------------------
    # Genesis-022: Metadata (unchanged)
    # ------------------------------------------------------------------

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value
        self._touch()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def has_metadata(self, key: str) -> bool:
        return key in self._metadata

    # ------------------------------------------------------------------
    # Session info
    # ------------------------------------------------------------------

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def last_updated(self) -> datetime:
        return self._last_updated

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all state for a new session."""
        # Genesis-022 fields
        self._mode           = ConversationMode.NORMAL
        self._current_topic  = None
        self._topic_history  = []
        self._pending        = None
        self._slots          = {}
        self._turns          = []
        self._references     = ReferenceContext()
        self._metadata       = {}
        # Genesis-043 fields
        self._ctx_turn          = 0
        self._active_person     = None
        self._active_topic      = None
        self._active_project    = None
        self._active_task       = None
        self._active_milestone  = None
        self._recent_entities   = []
        self._last_intent       = None
        self._last_response     = None
        self._last_topic        = None
        self._dialogue_act      = "inform"
        self._session_summary   = ""
        # Genesis-043 Sprint-002
        self.entity_registry.reset()
        # Genesis-043 Sprint-003
        self.topic_tracker.reset()
        self._touch()

    # ------------------------------------------------------------------
    # Summary / debug
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        def slot_info(slot):
            if slot is None:
                return None
            return {
                "value":      slot.value,
                "confidence": slot.effective_confidence(self._ctx_turn),
                "turn":       slot.turn,
            }

        return {
            # Genesis-022
            "mode":            self._mode.label(),
            "turn_count":      self._turn_count,
            "current_topic":   self._current_topic.name if self._current_topic else None,
            "topic_history":   len(self._topic_history),
            "has_pending":     self.has_pending(),
            "pending_slot":    self._pending.name if self._pending else None,
            "active_slots":    len(self.active_slots()),
            "filled_slots":    len(self.filled_slots()),
            "recent_turns":    len(self._turns),
            "references":      self._references.summary(),
            "metadata_keys":   list(self._metadata.keys()),
            "created_at":      self._created_at.isoformat(),
            "last_updated":    self._last_updated.isoformat(),
            # Genesis-043
            "ctx_turn":        self._ctx_turn,
            "active_person":   slot_info(self._active_person),
            "active_topic":    slot_info(self._active_topic),
            "active_project":  slot_info(self._active_project),
            "active_task":     slot_info(self._active_task),
            "active_milestone": slot_info(self._active_milestone),
            "recent_entities": self._recent_entities,
            "last_intent":     self._last_intent,
            "last_response":   self._last_response,
            "last_topic":      self._last_topic,
            "dialogue_act":    self._dialogue_act,
            "session_summary": self._session_summary[:80] if self._session_summary else "",
            # Genesis-043 Sprint-002
            "entity_registry": self.entity_registry.summary(self._ctx_turn),
            # Genesis-043 Sprint-003
            "topic_tracker":   self.topic_tracker.summary(),
        }

    def __repr__(self) -> str:
        return (
            f"ConversationState("
            f"mode={self._mode.label()}, "
            f"turns={self._turn_count}, "
            f"ctx_turn={self._ctx_turn}, "
            f"person={self._active_person.value if self._active_person else None!r}"
            f")"
        )
