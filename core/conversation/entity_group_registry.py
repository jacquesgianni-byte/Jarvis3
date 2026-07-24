"""
Jarvis Entity Group Registry (Genesis-025 Sprint-001)

Defines the data model and schema registry for generic slot completion.

This module is the foundation of Genesis-025. It replaces noun-specific
logic (pet patterns, dog/cat hardcoding) with a generic mechanism that
handles any grouped entity: animals, people, vehicles, instruments, etc.

Responsibilities:
    - Define EntityGroup and EntityGroupRecord data models
    - Provide EntityGroupRegistry with slot schemas per kind
    - Infer entity kind from natural language declarations
    - Produce KnowledgeEngine-compatible tag sets

Design constraints:
    - No AI calls
    - No KnowledgeEngine dependency (pure data model)
    - No SessionContext dependency
    - Deterministic — same input → same output
    - Extensible via registry data, not code changes

Architecture position:
    SlotCompletionEngine (Sprint-002)
        └── EntityGroupRegistry   ← this module
                └── EntityGroup   (data model)
                └── EntityGroupRecord (storage model)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Entity kind inference patterns
#
# Maps natural language group declarations to a canonical kind string.
# Each entry: (compiled regex, kind)
# Order matters — more specific patterns first.
# ---------------------------------------------------------------------------

_KIND_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Animals
    (re.compile(r"\b(?:dogs?|puppies|puppy)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:cats?|kittens?|kitten)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:birds?|parrots?|budgies?)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:fish|goldfish|tropical fish)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:rabbits?|bunnies|bunny)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:hamsters?|guinea pigs?)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\b(?:horses?|ponies|pony)\b", re.IGNORECASE), "animal"),
    (re.compile(r"\bpets?\b", re.IGNORECASE), "animal"),

    # People
    (re.compile(r"\b(?:children|child|kids?|sons?|daughters?)\b", re.IGNORECASE), "person"),
    (re.compile(r"\b(?:siblings?|brothers?|sisters?)\b", re.IGNORECASE), "person"),
    (re.compile(r"\b(?:employees?|staff|team members?|colleagues?)\b", re.IGNORECASE), "person"),
    (re.compile(r"\b(?:friends?|mates?|buddies|buddy)\b", re.IGNORECASE), "person"),

    # Vehicles
    (re.compile(r"\b(?:cars?|vehicles?|automobiles?)\b", re.IGNORECASE), "vehicle"),
    (re.compile(r"\b(?:motorbikes?|motorcycles?|bikes?)\b", re.IGNORECASE), "vehicle"),
    (re.compile(r"\b(?:trucks?|vans?|utes?)\b", re.IGNORECASE), "vehicle"),

    # Instruments
    (re.compile(r"\b(?:guitars?|basses?|bass guitars?)\b", re.IGNORECASE), "instrument"),
    (re.compile(r"\b(?:pianos?|keyboards?|synths?)\b", re.IGNORECASE), "instrument"),
    (re.compile(r"\b(?:drums?|drum kits?)\b", re.IGNORECASE), "instrument"),
    (re.compile(r"\b(?:violins?|cellos?|violas?)\b", re.IGNORECASE), "instrument"),
    (re.compile(r"\binstruments?\b", re.IGNORECASE), "instrument"),

    # Servers / tech
    (re.compile(r"\b(?:servers?|machines?|nodes?|instances?)\b", re.IGNORECASE), "server"),
    (re.compile(r"\b(?:projects?|repos?|repositories)\b", re.IGNORECASE), "project"),
]

# Pattern to extract quantity from a group declaration
_QUANTITY_PATTERN = re.compile(
    r"\b(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|some|several|many|a few)\b",
    re.IGNORECASE,
)

# Words that signal possession ("I have", "I own", "I've got", etc.)
_POSSESSION_SIGNAL = re.compile(
    r"\bi\s+(?:have|own|possess|keep)\b|\bi(?:'ve| have)\s+got\b",
    re.IGNORECASE,
)

# Canonical quantity normalisation
_WORD_TO_INT: dict[str, int] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "some": 0, "several": 0, "many": 0, "a few": 0,
}


# ---------------------------------------------------------------------------
# Slot schemas
#
# Maps entity kind → ordered list of expected slot names.
# Slots are filled in order — the first unfilled slot is the default
# target for bare continuations.
#
# Extending to a new entity type: add one entry here. No code changes.
# ---------------------------------------------------------------------------

SLOT_SCHEMAS: dict[str, list[str]] = {
    "animal":     ["names", "breeds", "colours", "ages"],
    "person":     ["names", "roles", "ages"],
    "vehicle":    ["names", "colours", "makes", "plates"],
    "instrument": ["names", "types", "colours"],
    "server":     ["names", "roles", "ips"],
    "project":    ["names", "statuses", "owners"],
}

# Default schema used when kind is unknown
_DEFAULT_SCHEMA: list[str] = ["names", "descriptions"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class GroupStatus(str, Enum):
    OPEN   = "open"    # accepting slot fills
    CLOSED = "closed"  # all key slots filled or topic changed


@dataclass
class EntityGroup:
    """
    In-memory representation of a declared entity group.

    Created when a user says "I have N things." Tracks which slots
    have been filled and whether the group is still open for completion.

    This is a transient object — it is not persisted directly.
    Persistence happens via EntityGroupRecord → KnowledgeEngine tags.
    """
    kind:       str                    # canonical kind ("animal", "person", etc.)
    raw_kind:   str                    # original word ("dogs", "cats", "guitars")
    count:      Optional[int]          # None if uncountable ("some", "several")
    raw_value:  str                    # original declaration value ("2 dogs")
    slots:      dict[str, str] = field(default_factory=dict)
    status:     GroupStatus = GroupStatus.OPEN
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    turn:       int = 0

    def schema(self) -> list[str]:
        """Return the slot schema for this kind."""
        return SLOT_SCHEMAS.get(self.kind, _DEFAULT_SCHEMA)

    def next_unfilled_slot(self) -> Optional[str]:
        """Return the first slot name not yet filled, or None if all filled."""
        for slot in self.schema():
            if slot not in self.slots:
                return slot
        return None

    def is_complete(self) -> bool:
        """Return True if all schema slots are filled."""
        return self.next_unfilled_slot() is None

    def fill(self, slot: str, value: str) -> None:
        """Fill a slot with a value."""
        self.slots[slot] = value
        if self.is_complete():
            self.status = GroupStatus.CLOSED

    def close(self) -> None:
        """Explicitly close this group (e.g. when topic changes)."""
        self.status = GroupStatus.CLOSED

    def knowledge_attribute(self) -> str:
        """Return the KnowledgeEngine attribute name for this group."""
        return f"group:{self.kind}"

    def slot_attribute(self, slot: str) -> str:
        """Return the KnowledgeEngine attribute name for a specific slot."""
        return f"group:{self.kind}:{slot}"

    def knowledge_tags(self) -> list[str]:
        """Return tags for the group declaration record."""
        tags = ["group", f"group_kind:{self.kind}"]
        if self.status == GroupStatus.OPEN:
            tags.append("group_open")
        return tags

    def slot_tags(self, slot: str) -> list[str]:
        """Return tags for a slot record."""
        return ["group_slot", f"group_kind:{self.kind}", f"slot:{slot}"]


@dataclass(frozen=True)
class GroupDeclaration:
    """
    Result of detecting a group declaration in a user message.

    Returned by EntityGroupRegistry.detect_declaration().
    Contains everything needed to create an EntityGroup.
    """
    kind:      str
    raw_kind:  str
    count:     Optional[int]
    raw_value: str            # e.g. "2 dogs"
    confidence: float = 0.90


@dataclass(frozen=True)
class SlotFill:
    """
    Result of detecting a slot fill in a user message.

    Returned by EntityGroupRegistry.detect_slot_fill().
    """
    slot:      str
    value:     str
    kind:      str
    confidence: float = 0.85


# ---------------------------------------------------------------------------
# EntityGroupRegistry
# ---------------------------------------------------------------------------

class EntityGroupRegistry:
    """
    Detects group declarations and slot fills in natural language.

    Stateless — receives all context as arguments. No KnowledgeEngine
    or SessionContext dependency. Pure classification logic.

    Public API:
        detect_declaration(text) -> Optional[GroupDeclaration]
        detect_slot_fill(text, active_kind, active_slots) -> Optional[SlotFill]
        infer_kind(text) -> Optional[str]
        schema_for(kind) -> list[str]
    """

    def detect_declaration(self, text: str) -> Optional[GroupDeclaration]:
        """
        Detect a group declaration in a user message.

        Matches patterns like:
            "I have 2 dogs."
            "I own 3 guitars."
            "I've got some children."

        Args:
            text: The user's raw message.

        Returns:
            GroupDeclaration if detected, None otherwise.
        """
        if not text or not text.strip():
            return None

        # Must contain a possession signal
        if not _POSSESSION_SIGNAL.search(text):
            return None
        
        # Exclude questions
        if text.strip().endswith("?"):
            return None

        # Must contain a known entity kind
        kind, raw_kind = self._infer_kind_and_raw(text)
        if not kind:
            return None

        # Extract quantity
        count, raw_qty = self._extract_quantity(text)
        raw_value = f"{raw_qty} {raw_kind}".strip() if raw_qty else raw_kind

        return GroupDeclaration(
            kind=kind,
            raw_kind=raw_kind,
            count=count,
            raw_value=raw_value,
            confidence=0.90,
        )

    def detect_slot_fill(
        self,
        text: str,
        active_kind: str,
        filled_slots: dict[str, str],
    ) -> Optional[SlotFill]:
        """
        Detect a slot fill for an active group.

        Matches explicit forms like:
            "Their names are Rex and Tom."
            "They are brown and white."

        Args:
            text:         The user's raw message.
            active_kind:  The kind of the currently open group.
            filled_slots: Slots already filled for this group.

        Returns:
            SlotFill if detected, None otherwise.
        """
        if not text or not active_kind:
            return None

        schema = SLOT_SCHEMAS.get(active_kind, _DEFAULT_SCHEMA)

        # Check explicit slot fill patterns
        for slot in schema:
            if slot in filled_slots:
                continue
            pattern = _EXPLICIT_SLOT_PATTERNS.get(slot)
            if pattern:
                m = pattern.search(text)
                if m:
                    value = m.group(1).strip().rstrip(".")
                    return SlotFill(
                        slot=slot,
                        value=value,
                        kind=active_kind,
                        confidence=0.90,
                    )

        return None

    def infer_kind(self, text: str) -> Optional[str]:
        """Return the canonical kind for a text, or None."""
        kind, _ = self._infer_kind_and_raw(text)
        return kind

    def schema_for(self, kind: str) -> list[str]:
        """Return the slot schema for a kind."""
        return SLOT_SCHEMAS.get(kind, _DEFAULT_SCHEMA)

    def next_slot(self, kind: str, filled_slots: dict[str, str]) -> Optional[str]:
        """Return the first unfilled slot for a kind."""
        for slot in self.schema_for(kind):
            if slot not in filled_slots:
                return slot
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _infer_kind_and_raw(self, text: str) -> tuple[Optional[str], str]:
        """Return (canonical_kind, raw_word) or (None, '')."""
        for pattern, kind in _KIND_PATTERNS:
            m = pattern.search(text)
            if m:
                return kind, m.group(0)
        return None, ""

    def _extract_quantity(self, text: str) -> tuple[Optional[int], str]:
        """Return (int_count_or_None, raw_quantity_string)."""
        m = _QUANTITY_PATTERN.search(text)
        if not m:
            return None, ""
        raw = m.group(1).lower()
        # Try numeric digit first, then word lookup
        try:
            count = int(raw)
            return count, raw
        except ValueError:
            pass
        word_count = _WORD_TO_INT.get(raw)
        if word_count == 0:
            return None, raw  # uncountable ("some", "several")
        return word_count, raw


# ---------------------------------------------------------------------------
# Explicit slot fill patterns
#
# Maps slot name → regex that captures the value.
# Used by detect_slot_fill() for explicit forms.
# Bare continuations (implicit fills) are handled by SlotCompletionEngine.
# ---------------------------------------------------------------------------

_EXPLICIT_SLOT_PATTERNS: dict[str, re.Pattern] = {
    "names": re.compile(
        r"\b(?:their|his|her|its|my\s+\w+(?:'s)?)\s+names?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "colours": re.compile(
        r"\b(?:their|his|her|its)\s+colou?rs?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "breeds": re.compile(
        r"\b(?:their|his|her|its)\s+breeds?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "ages": re.compile(
        r"\b(?:their|his|her|its)\s+ages?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "roles": re.compile(
        r"\b(?:their|his|her|its)\s+roles?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "makes": re.compile(
        r"\b(?:their|his|her|its)\s+makes?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
    "types": re.compile(
        r"\b(?:their|his|her|its)\s+types?\s+(?:is|are)\s+(.+)",
        re.IGNORECASE,
    ),
}