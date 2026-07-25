"""
Jarvis Slot Completion Engine (Genesis-025 Sprint-002)

Orchestrates generic slot completion for grouped entity declarations.

This is the single entry point for the Agent at Step 4. It replaces
noun-specific logic (pet patterns, detect_with_context) with a generic
mechanism that handles any entity kind defined in EntityGroupRegistry.

Responsibilities:
    - Detect group declarations ("I have 2 dogs.")
    - Detect explicit slot fills ("Their names are Rex and Tom.")
    - Detect implicit slot fills ("Rex and Tom." after "I have 2 dogs.")
    - Return MemoryDetection objects the Agent stores without modification
    - Never write to KnowledgeEngine directly
    - Never call AI

Design constraints:
    - Stateless — all context supplied by the Agent as arguments
    - No KnowledgeEngine dependency
    - No SessionContext dependency
    - Deterministic — same input + same context → same output
    - Backward compatible — existing MemoryDetection keys preserved

Architecture position:
    Agent.process() Step 4
        └── SlotCompletionEngine.detect()   ← this module
                └── EntityGroupRegistry     (Sprint-001)
                └── MemoryDetection         (existing model)

Backward compatibility mapping:
    group declaration  → MemoryDetection(key="pets", value="2 dogs")
    slot fill (names)  → MemoryDetection(key="pet names", value="Rex and Tom")

    These keys are intentionally preserved so existing MemorySkill
    acknowledgements and ConversationRecall patterns continue to work
    without modification during the Sprint-002/Sprint-003 transition.
    They will be replaced with generic keys in Sprint-003.
"""

from __future__ import annotations

import re
import logging
from typing import Optional

from core.conversation.entity_group_registry import (
    EntityGroupRegistry,
    GroupDeclaration,
    SlotFill,
    SLOT_SCHEMAS,
)
from core.conversation.memory_detection import MemoryDetection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatible key mapping
#
# Maps (kind, slot) → MemoryDetection key used by existing MemorySkill
# and ConversationRecall. Preserves existing behaviour during transition.
#
# Sprint-003 will replace these with generic keys like "group:animal:names".
# ---------------------------------------------------------------------------
_COMPAT_DECLARATION_KEYS: dict[str, str] = {
    "animal":     "pets",
    "person":     "people",
    "vehicle":    "vehicles",
    "instrument": "instruments",
    "server":     "servers",
    "project":    "projects",
}

_COMPAT_SLOT_KEYS: dict[tuple[str, str], str] = {
    ("animal",  "names"): "pet names",
    ("person",  "names"): "people names",
    ("vehicle", "names"): "vehicle names",
}

# Matches a bare name or comma-separated name list (case-insensitive)
# Used for implicit slot fill detection
_NAME_LIST_RE = re.compile(
    r"^[A-Za-z][a-zA-Z]+(?:(?:[,\s]+(?:and\s+)?)[A-Za-z][a-zA-Z]+)*\.?$",
    re.IGNORECASE,
)

# Pattern to check if active_topic looks like a group quantity
_GROUP_TOPIC_RE = re.compile(
    r"^(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|some|several|many)\s+\w+",
    re.IGNORECASE,
)


class SlotCompletionEngine:
    """
    Generic slot completion engine for grouped entity declarations.

    Called by the Agent at Step 4, before MemoryDetector. Returns a
    MemoryDetection if the message is a group declaration or slot fill,
    or None if the message should be handled by MemoryDetector instead.

    Public API:
        detect(message, active_topic, active_kind, filled_slots) -> Optional[MemoryDetection]
    """

    def __init__(self) -> None:
        self._registry = EntityGroupRegistry()

    def detect(
        self,
        message: str,
        active_topic: str = "",
        active_kind: str = "",
        filled_slots: dict[str, str] | None = None,
    ) -> Optional[MemoryDetection]:
        """
        Detect a group declaration or slot fill in a user message.

        Args:
            message:      The user's raw message.
            active_topic: The current active_topic value from SessionContext
                          (e.g. "2 dogs", "3 cats"). Empty if not set.
            active_kind:  Optional kind hint. If empty, inferred from
                          active_topic internally. The Agent should never
                          need to pass this — it is available for testing.
            filled_slots: Slots already filled for the active group.
                          Empty dict if no group is active.

        Returns:
            MemoryDetection if a group declaration or slot fill is detected.
            None if the message should be handled by MemoryDetector instead.
        """
        if not message or not message.strip():
            return None

        filled = filled_slots or {}

        # Infer kind from active_topic if not supplied by caller.
        # This keeps EntityGroupRegistry internal to SlotCompletionEngine —
        # the Agent never accesses _registry directly. GC-025 Sprint-002.
        kind = active_kind or (
            self._registry.infer_kind(active_topic) if active_topic else ""
        )

        # 1. Check for group declaration ("I have 2 dogs.")
        declaration = self._registry.detect_declaration(message)
        if declaration:
            return self._declaration_to_detection(declaration)

        # 2. Check for explicit slot fill ("Their names are Rex and Tom.")
        if kind:
            slot_fill = self._registry.detect_slot_fill(message, kind, filled)
            if slot_fill:
                return self._slot_fill_to_detection(slot_fill)

        # 3. Check for implicit slot fill (bare name list after active group)
        if active_topic and _GROUP_TOPIC_RE.match(active_topic):
            implicit = self._detect_implicit_fill(message, active_topic, kind, filled)
            if implicit:
                return implicit

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _declaration_to_detection(self, declaration: GroupDeclaration) -> MemoryDetection:
        """Convert a GroupDeclaration to a backward-compatible MemoryDetection."""
        key = _COMPAT_DECLARATION_KEYS.get(declaration.kind, f"group:{declaration.kind}")
        logger.info(
            "[SLOT] Group declaration: kind=%r count=%r raw=%r → key=%r",
            declaration.kind, declaration.count, declaration.raw_value, key,
        )
        return MemoryDetection(
            key=key,
            value=declaration.raw_value,
            confidence=declaration.confidence,
        )

    def _slot_fill_to_detection(self, slot_fill: SlotFill) -> MemoryDetection:
        """Convert a SlotFill to a backward-compatible MemoryDetection."""
        key = _COMPAT_SLOT_KEYS.get(
            (slot_fill.kind, slot_fill.slot),
            f"group:{slot_fill.kind}:{slot_fill.slot}",
        )
        logger.info(
            "[SLOT] Explicit slot fill: kind=%r slot=%r value=%r → key=%r",
            slot_fill.kind, slot_fill.slot, slot_fill.value, key,
        )
        return MemoryDetection(
            key=key,
            value=slot_fill.value,
            confidence=slot_fill.confidence,
        )

    def _detect_implicit_fill(
        self,
        message: str,
        active_topic: str,
        active_kind: str,
        filled_slots: dict[str, str],
    ) -> Optional[MemoryDetection]:
        """
        Detect an implicit slot fill from a bare continuation.

        When active_topic is set (e.g. "2 dogs") and the message looks
        like a name list ("Rex and Tom."), infer it as filling the next
        unfilled slot for the active kind.
        """
        stripped = message.strip().rstrip(".")
        if not _NAME_LIST_RE.match(stripped):
            return None
        if len(stripped) <= 3:
            return None

        # Infer kind from active_topic if not already known

        # Infer kind from active_topic if not already known
        kind = active_kind or self._registry.infer_kind(active_topic)
        if not kind:
            return None

        # Find the next unfilled slot
        next_slot = self._registry.next_slot(kind, filled_slots)
        if not next_slot:
            return None

        key = _COMPAT_SLOT_KEYS.get((kind, next_slot), f"group:{kind}:{next_slot}")
        logger.info(
            "[SLOT] Implicit slot fill: kind=%r slot=%r value=%r → key=%r",
            kind, next_slot, stripped, key,
        )
        return MemoryDetection(
            key=key,
            value=stripped,
            confidence=0.82,
        )