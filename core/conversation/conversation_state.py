"""
Jarvis Conversation State (Genesis-022 Sprint-002)

The live, mutable state for one conversation session.

ConversationState is the single source of truth for what is happening
in the current conversation. It is owned by the ConversationEngine
and passed (by reference) into each pipeline stage via ConversationContext.

Design constraints:
    - In-memory only. No persistence.
    - No KnowledgeEngine integration.
    - No Worker integration.
    - No AI calls.
    - Mutable by design — state changes as the conversation progresses.
    - All public models stored inside state are immutable (Slot, Topic, etc.)
      State mutates by replacing them, never by mutating them in place.

Tracked state:
    - current_topic:      The active conversation topic (or None).
    - topic_history:      Stack of previous topics for recovery.
    - mode:               Current conversation mode (NORMAL, AWAITING_ANSWER, etc.)
    - pending_question:   The slot currently being filled (or None).
    - active_slots:       Dict of slot name → Slot for all open slots.
    - turn_history:       Recent ConversationTurns (capped at max_turns).
    - reference_context:  What "it", "that", "him" currently refer to.
    - turn_count:         Total turns processed this session.
    - metadata:           Arbitrary session metadata for future stages.
    - created_at:         Session start time.
    - last_updated:       Last time state was modified.
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
# ReferenceContext
# ---------------------------------------------------------------------------

@dataclass
class ReferenceContext:
    """
    Tracks what ambiguous references currently point to.

    Used by the ReferenceResolver (Sprint-003) to resolve
    pronouns and vague references ("it", "that", "him", etc.)

    All fields are mutable — they are updated as the conversation evolves.
    """
    # What "it" / "that" / "this" currently refers to
    current_it:      Optional[str] = None
    # What "him" / "her" / "they" currently refers to
    current_person:  Optional[str] = None
    # What "the project" currently refers to
    current_project: Optional[str] = None
    # What "the plan" / "the task" currently refers to
    current_task:    Optional[str] = None
    # Generic last-mentioned entity
    last_entity:     Optional[str] = None

    def update(self, **kwargs: str) -> None:
        """Update one or more reference slots."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def clear(self) -> None:
        """Reset all references."""
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
# ConversationState
# ---------------------------------------------------------------------------

class ConversationState:
    """
    The live, mutable state of one conversation session.

    Owned by ConversationEngine. Passed into each pipeline stage via
    ConversationContext so stages can read and update state without
    owning it.

    All immutable models (Slot, Topic) are replaced rather than mutated.
    Mutable containers (dicts, lists) are managed via dedicated methods.

    Public API:
        # Topic
        set_topic(topic)
        clear_topic()
        push_topic(topic)    — save current, set new
        pop_topic()          — restore previous

        # Mode
        set_mode(mode)
        is_mode(mode)

        # Pending question
        set_pending(slot)
        clear_pending()
        has_pending()

        # Slots
        add_slot(slot)
        fill_slot(name, value) → Slot
        get_slot(name) → Slot | None
        active_slots()
        filled_slots()

        # Turn history
        add_turn(turn)
        recent_turns(n) → list[ConversationTurn]
        last_turn() → ConversationTurn | None

        # Reference context
        update_reference(**kwargs)
        clear_references()

        # Metadata
        set_metadata(key, value)
        get_metadata(key, default)

        # Reset
        reset()
        summary()
    """

    DEFAULT_MAX_TURNS: int = 20   # maximum turns kept in history

    def __init__(self, max_turns: int = DEFAULT_MAX_TURNS) -> None:
        self._max_turns:       int                          = max_turns
        self._mode:            ConversationMode             = ConversationMode.NORMAL
        self._current_topic:   Optional[Topic]              = None
        self._topic_history:   list[Topic]                  = []
        self._pending:         Optional[Slot]               = None
        self._slots:           dict[str, Slot]              = {}
        self._turns:           list[ConversationTurn]       = []
        self._references:      ReferenceContext             = ReferenceContext()
        self._metadata:        dict[str, Any]               = {}
        self._turn_count:      int                          = 0
        self._created_at:      datetime                     = datetime.now(UTC)
        self._last_updated:    datetime                     = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Internal touch helper
    # ------------------------------------------------------------------

    def _touch(self) -> None:
        self._last_updated = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Topic management
    # ------------------------------------------------------------------

    @property
    def current_topic(self) -> Optional[Topic]:
        """The active conversation topic, or None."""
        return self._current_topic

    def set_topic(self, topic: Topic) -> None:
        """Set the active topic. Does not push to history."""
        self._current_topic = topic
        self._touch()

    def clear_topic(self) -> None:
        """Clear the active topic."""
        self._current_topic = None
        self._touch()

    def push_topic(self, topic: Topic) -> None:
        """
        Save the current topic to history and activate the new one.
        Used when the user changes subject mid-conversation.
        """
        if self._current_topic is not None:
            self._topic_history.append(self._current_topic)
        self._current_topic = topic
        self._touch()

    def pop_topic(self) -> Optional[Topic]:
        """
        Restore the previous topic and return it.
        Returns None if topic history is empty.
        Used for conversation recovery ("go back to what we were discussing").
        """
        if not self._topic_history:
            self._current_topic = None
            return None
        self._current_topic = self._topic_history.pop()
        self._touch()
        return self._current_topic

    @property
    def topic_history(self) -> list[Topic]:
        """Read-only view of the topic history stack."""
        return list(self._topic_history)

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    @property
    def mode(self) -> ConversationMode:
        return self._mode

    def set_mode(self, mode: ConversationMode) -> None:
        """Set the current conversation mode."""
        self._mode = mode
        self._touch()

    def is_mode(self, mode: ConversationMode) -> bool:
        """Return True if the current mode matches."""
        return self._mode == mode

    # ------------------------------------------------------------------
    # Pending question
    # ------------------------------------------------------------------

    def set_pending(self, slot: Slot) -> None:
        """
        Register a pending question slot.
        Sets mode to AWAITING_ANSWER automatically.
        """
        self._pending = slot
        self._mode = ConversationMode.AWAITING_ANSWER
        self._touch()

    def clear_pending(self) -> None:
        """
        Clear the pending question and return mode to NORMAL.
        """
        self._pending = None
        if self._mode == ConversationMode.AWAITING_ANSWER:
            self._mode = ConversationMode.NORMAL
        self._touch()

    def has_pending(self) -> bool:
        """
        True if a pending question exists and has not expired.
        Expired pending slots are auto-cleared.
        """
        if self._pending is None:
            return False
        if self._pending.is_expired():
            self.clear_pending()
            return False
        return True

    @property
    def pending_slot(self) -> Optional[Slot]:
        """The current pending slot, or None if none/expired."""
        if not self.has_pending():
            return None
        return self._pending

    # ------------------------------------------------------------------
    # Slot management
    # ------------------------------------------------------------------

    def add_slot(self, slot: Slot) -> None:
        """Register a new slot. Replaces any existing slot with the same name."""
        self._slots[slot.name] = slot
        self._touch()

    def fill_slot(self, name: str, value: str) -> Slot:
        """
        Fill a slot with a value.

        Args:
            name:  The slot name.
            value: The value to fill.

        Returns:
            The updated (filled) Slot.

        Raises:
            KeyError: If the slot does not exist.
        """
        if name not in self._slots:
            raise KeyError(f"Slot {name!r} not found.")
        filled = self._slots[name].fill(value)
        self._slots[name] = filled
        self._touch()
        return filled

    def get_slot(self, name: str) -> Optional[Slot]:
        """Return a slot by name, or None if not found."""
        return self._slots.get(name)

    def active_slots(self) -> list[Slot]:
        """Return all slots that are EMPTY (awaiting a value)."""
        return [
            s for s in self._slots.values()
            if s.status == SlotStatus.EMPTY and not s.is_expired()
        ]

    def filled_slots(self) -> list[Slot]:
        """Return all FILLED slots."""
        return [s for s in self._slots.values() if s.status == SlotStatus.FILLED]

    def all_slots(self) -> list[Slot]:
        """Return all registered slots regardless of status."""
        return list(self._slots.values())

    def clear_slots(self) -> None:
        """Remove all slots."""
        self._slots.clear()
        self._touch()

    # ------------------------------------------------------------------
    # Turn history
    # ------------------------------------------------------------------

    def add_turn(self, turn: ConversationTurn) -> None:
        """
        Record a completed conversation turn.
        History is capped at max_turns (oldest removed first).
        """
        self._turns.append(turn)
        self._turn_count += 1
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)
        self._touch()

    def recent_turns(self, n: int = 5) -> list[ConversationTurn]:
        """Return the most recent n turns (oldest first)."""
        return list(self._turns[-n:])

    def last_turn(self) -> Optional[ConversationTurn]:
        """Return the most recent turn, or None if no turns yet."""
        return self._turns[-1] if self._turns else None

    @property
    def turn_count(self) -> int:
        """Total number of turns processed (not capped)."""
        return self._turn_count

    # ------------------------------------------------------------------
    # Reference context
    # ------------------------------------------------------------------

    def update_reference(self, **kwargs: str) -> None:
        """
        Update the reference context.

        Keyword args: it, person, project, task, entity.

        Example:
            state.update_reference(person="Claude", project="Jarvis OS")
        """
        self._references.update(**kwargs)
        self._touch()

    def clear_references(self) -> None:
        """Reset all reference context."""
        self._references.clear()
        self._touch()

    @property
    def references(self) -> ReferenceContext:
        """The current reference context."""
        return self._references

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def set_metadata(self, key: str, value: Any) -> None:
        """Store arbitrary session metadata."""
        self._metadata[key] = value
        self._touch()

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve session metadata."""
        return self._metadata.get(key, default)

    def has_metadata(self, key: str) -> bool:
        """True if metadata key exists."""
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
        """
        Reset all state. Called at the end of a session or for testing.
        Does not reset turn_count or created_at.
        """
        self._mode           = ConversationMode.NORMAL
        self._current_topic  = None
        self._topic_history  = []
        self._pending        = None
        self._slots          = {}
        self._turns          = []
        self._references     = ReferenceContext()
        self._metadata       = {}
        self._touch()

    # ------------------------------------------------------------------
    # Summary / debug
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Human-readable state snapshot for debugging."""
        return {
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
        }

    def __repr__(self) -> str:
        return (
            f"ConversationState("
            f"mode={self._mode.label()}, "
            f"turns={self._turn_count}, "
            f"topic={self._current_topic.name if self._current_topic else None!r}"
            f")"
        )