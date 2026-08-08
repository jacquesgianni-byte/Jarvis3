"""
EntityRegistry — Genesis-043 Sprint-002 (PROP-0001)

Tracks all named entities mentioned in the current conversation session
with salience scoring and last_mentioned_turn.

Solves the core problem identified in PAPER-001:
    ConversationStateEngine.update_entity() only tracked ONE active entity
    (active_person). Multi-entity conversations degraded after 3-4 turns
    because pronoun resolution had no way to pick between entities.

Design:
    - Owned by ConversationState (lives inside the canonical state object)
    - Written by ConversationStateEngine.update_entity()
    - Read by pronoun resolution and ClarificationEngine
    - No AI calls. No KnowledgeEngine. Purely in-memory session data.
    - Salience decays with turns — same model as ContextSlot

Architecture position:
    ConversationState
        └── entity_registry: EntityRegistry   ← this module

    ConversationStateEngine.update_entity()
        └── calls ConversationState.entity_registry.mention(name, turn)

    Agent._route() ClarificationEngine check
        └── reads ConversationState.entity_registry.recent(n)

Genesis-043 Sprint-002.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Salience decay — same constants as ContextSlot
_DECAY_TURNS:    int   = 10
_MIN_SALIENCE:   float = 0.15
_BASE_SALIENCE:  float = 1.0
_MENTION_BOOST:  float = 0.20   # each re-mention boosts salience


@dataclass
class EntityRecord:
    """
    A single named entity tracked in the current conversation session.

    Attributes:
        name:               Canonical lowercase entity name.
        display_name:       Original casing as first mentioned.
        first_seen_turn:    Turn when entity was first mentioned.
        last_mentioned_turn: Turn when entity was most recently mentioned.
        mention_count:      How many times mentioned this session.
        salience:           Base salience (boosted by re-mentions).
    """
    name:                str
    display_name:        str
    first_seen_turn:     int
    last_mentioned_turn: int
    mention_count:       int   = 1
    salience:            float = _BASE_SALIENCE

    def effective_salience(self, current_turn: int) -> float:
        """
        Salience decays linearly from last_mentioned_turn over DECAY_TURNS.
        Re-mentions reset the decay clock via last_mentioned_turn.
        """
        elapsed = current_turn - self.last_mentioned_turn
        decay   = max(0.0, 1.0 - elapsed / _DECAY_TURNS)
        return round(min(1.0, self.salience) * decay, 4)

    def is_active(self, current_turn: int) -> bool:
        return self.effective_salience(current_turn) >= _MIN_SALIENCE

    def mention(self, turn: int) -> None:
        """Record a new mention — boosts salience and resets decay clock."""
        self.last_mentioned_turn = turn
        self.mention_count      += 1
        self.salience            = min(1.0, self.salience + _MENTION_BOOST)


class EntityRegistry:
    """
    Tracks all named entities mentioned in the current session.

    Owned by ConversationState. Written by ConversationStateEngine.
    Read by pronoun resolution and ClarificationEngine.

    Public API:
        mention(name, turn)              — record a mention (add or update)
        get(name) -> EntityRecord|None   — look up by name
        most_salient(turn) -> str|None   — highest salience entity name
        recent(n, turn) -> list[str]     — n most recently mentioned names
        active(turn) -> list[EntityRecord] — all above MIN_SALIENCE threshold
        all_names() -> list[str]         — all tracked names regardless of salience
        resolve_pronoun(pronoun, turn) -> str|None — best entity for pronoun
        reset()                          — clear all (new session)
        summary(turn) -> dict            — debug snapshot
    """

    def __init__(self) -> None:
        self._entities: dict[str, EntityRecord] = {}

    # ── Write ──────────────────────────────────────────────────────────

    def mention(self, name: str, turn: int, display_name: str = "") -> EntityRecord:
        """
        Record that an entity was mentioned at this turn.
        Creates a new EntityRecord or updates an existing one.
        """
        key = name.strip().lower()
        if not key:
            raise ValueError("Entity name cannot be empty")

        if key in self._entities:
            self._entities[key].mention(turn)
            logger.debug("[ENTITY] Re-mention: %r (turn=%d, count=%d, salience=%.2f)",
                         key, turn, self._entities[key].mention_count,
                         self._entities[key].salience)
        else:
            record = EntityRecord(
                name=key,
                display_name=display_name or name.strip(),
                first_seen_turn=turn,
                last_mentioned_turn=turn,
                mention_count=1,
                salience=_BASE_SALIENCE,
            )
            self._entities[key] = record
            logger.info("[ENTITY] New entity: %r (turn=%d)", key, turn)

        return self._entities[key]

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, name: str) -> Optional[EntityRecord]:
        return self._entities.get(name.strip().lower())

    def most_salient(self, current_turn: int) -> Optional[str]:
        """Return the display_name of the entity with highest effective salience."""
        active = self.active(current_turn)
        if not active:
            return None
        best = max(active, key=lambda e: e.effective_salience(current_turn))
        return best.display_name

    def most_salient_excluding(
        self, current_turn: int, exclude: str
    ) -> Optional[str]:
        """Return highest-salience entity other than the excluded name."""
        active = self.active(current_turn)
        filtered = [e for e in active if e.name != exclude.lower()]
        if not filtered:
            return None
        best = max(filtered, key=lambda e: e.effective_salience(current_turn))
        return best.display_name

    def recent(self, n: int, current_turn: int) -> list[str]:
        """Return display_names of n most recently mentioned active entities."""
        active = self.active(current_turn)
        sorted_by_recency = sorted(
            active, key=lambda e: e.last_mentioned_turn, reverse=True
        )
        return [e.display_name for e in sorted_by_recency[:n]]

    def active(self, current_turn: int) -> list[EntityRecord]:
        """Return all entity records above the salience threshold."""
        return [
            e for e in self._entities.values()
            if e.is_active(current_turn)
        ]

    def all_names(self) -> list[str]:
        """Return all tracked entity names regardless of salience."""
        return [e.display_name for e in self._entities.values()]

    def resolve_pronoun(
        self, pronoun: str, current_turn: int, is_plural: bool = False
    ) -> Optional[str]:
        """
        Return the best entity name to resolve a pronoun against.

        Singular pronouns (he/she/it) → highest-salience entity.
        Plural pronouns (they/them) → most recently mentioned entity
        (as a proxy for group reference — TopicTracker refines this in S3).
        """
        active = self.active(current_turn)
        if not active:
            return None

        if is_plural:
            # For plural pronouns, return the most recently mentioned entity
            best = max(active, key=lambda e: e.last_mentioned_turn)
        else:
            # For singular pronouns, return highest salience
            best = max(active, key=lambda e: e.effective_salience(current_turn))

        return best.display_name

    # ── Session management ─────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all entities. Called on session reset."""
        self._entities.clear()
        logger.info("[ENTITY] Registry reset.")

    def count(self) -> int:
        return len(self._entities)

    def summary(self, current_turn: int) -> dict:
        return {
            "total":  len(self._entities),
            "active": len(self.active(current_turn)),
            "entities": [
                {
                    "name":     e.display_name,
                    "salience": e.effective_salience(current_turn),
                    "mentions": e.mention_count,
                    "last_turn": e.last_mentioned_turn,
                }
                for e in sorted(
                    self._entities.values(),
                    key=lambda x: x.effective_salience(current_turn),
                    reverse=True,
                )
            ],
        }
