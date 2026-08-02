"""
Semantic Recall Engine (Genesis-032 Sprint-001)

Assembles a coherent picture of an entity from everything already stored
across all knowledge subsystems. No AI. No new storage. Pure synthesis.

Responsibilities:
    - Accept a query entity name
    - Collect facts from multiple providers
    - Merge duplicates
    - Sort into categories
    - Produce a structured SemanticProfile

Architecture:
    SemanticRecallEngine
        -> PropertyProvider       (prop:age, prop:colour, etc.)
        -> GroupProvider          (entity group membership)
        -> TemporalProvider       (temporal tags on memories)
        -> ConversationProvider   (recent conversation references)
        -> [future providers]

Design constraints:
    - No AI calls
    - No new storage -- reads existing KnowledgeEngine records only
    - No hardcoded entity types (no if person / if pet / if device)
    - Provider-driven -- new providers plug in without changing engine
    - Deterministic -- same knowledge -> same output

Genesis-032 Sprint-001.
"""

from __future__ import annotations

import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SemanticFact -- atomic unit of knowledge about an entity
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticFact:
    """
    A single piece of knowledge about an entity.

    category:  Grouping label ("Properties", "Groups", "Temporal", etc.)
    label:     Human-readable fact ("8 years old", "brown", "offline")
    source:    Which provider contributed this fact
    key:       Optional machine key for deduplication ("age", "colour")
    """
    category: str
    label:    str
    source:   str
    key:      str = ""

    def dedup_key(self) -> str:
        """Key used to detect duplicate facts."""
        if self.key:
            return f"{self.category}:{self.key}"
        return f"{self.category}:{self.label.lower()}"


# ---------------------------------------------------------------------------
# SemanticProfile -- structured result for one entity
# ---------------------------------------------------------------------------

@dataclass
class SemanticProfile:
    """
    All known facts about an entity, organised by category.

    entity_name:  The queried name (e.g. "Leo", "Rex", "Canon")
    facts:        List of SemanticFact objects
    found:        True if any facts were found
    """
    entity_name: str
    facts:       list[SemanticFact] = field(default_factory=list)
    found:       bool = False

    def add(self, fact: SemanticFact) -> None:
        """Add a fact, silently dropping duplicates."""
        dk = fact.dedup_key()
        if any(f.dedup_key() == dk for f in self.facts):
            return
        self.facts.append(fact)
        self.found = True

    def by_category(self) -> dict[str, list[SemanticFact]]:
        """Return facts grouped by category, preserving insertion order."""
        result: dict[str, list[SemanticFact]] = {}
        for f in self.facts:
            result.setdefault(f.category, []).append(f)
        return result

    def to_text(self) -> str:
        """
        Render the profile as natural conversational prose.

        Example:
            "Here's what I know about Leo. He is 9 years old, likes football,
            and is very smart. Leo is one of your children."
        """
        if not self.found:
            return f"I don't have any information stored about {self.entity_name}."

        cats = self.by_category()
        parts = []

        # Properties first -- core facts
        props = cats.get("Properties", [])
        if props:
            prop_labels = [f.label for f in props]
            if len(prop_labels) == 1:
                parts.append(f"{self.entity_name} is {prop_labels[0]}")
            elif len(prop_labels) == 2:
                parts.append(f"{self.entity_name} is {prop_labels[0]} and {prop_labels[1]}")
            else:
                parts.append(
                    f"{self.entity_name} is {', '.join(prop_labels[:-1])}, and {prop_labels[-1]}"
                )

        # Relationships -- group membership
        rels = cats.get("Relationships", [])
        for f in rels:
            parts.append(f.label)

        # Temporal -- when things happened
        temps = cats.get("Temporal", [])
        for f in temps:
            parts.append(f.label.lower())

        # Conversation -- skip "Discussed recently" if we have real facts
        conv = cats.get("Conversation", [])
        if conv and len(parts) == 0:
            parts.append(conv[0].label.lower())

        if not parts:
            return f"I don't have any information stored about {self.entity_name}."

        intro = f"Here's what I know about {self.entity_name}. "
        return intro + ". ".join(p[0].upper() + p[1:] for p in parts) + "."


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class SemanticProvider(ABC):
    """
    Abstract base for semantic fact providers.

    Each provider reads from one knowledge subsystem and contributes
    SemanticFact objects to a SemanticProfile.

    Implement contribute(entity_name, knowledge, profile) to add facts.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for source attribution."""

    @abstractmethod
    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        """
        Add facts about entity_name to profile.

        Args:
            entity_name: The entity to look up (e.g. "leo", "rex")
            knowledge:   KnowledgeEngine instance for record lookup
            profile:     SemanticProfile to add facts to
        """


# ---------------------------------------------------------------------------
# PropertyProvider
# ---------------------------------------------------------------------------

class PropertyProvider(SemanticProvider):
    """
    Reads generic property records (prop:age, prop:colour, etc.)
    from KnowledgeEngine and contributes them as facts.
    """

    name = "property"

    _PROP_LABELS: dict[str, str] = {
        "age":      "{value} years old",
        "colour":   "{value}",
        "color":    "{value}",
        "weight":   "weighs {value}",
        "status":   "{value}",
        "location": "located in {value}",
        "priority": "{value} priority",
        "interest": "likes {value}",
        "property": "{value}",
    }

    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        records = knowledge.list_memories(
            subject=entity_name.lower(),
            category="entity_property",
        )
        for record in records:
            if not record.attribute.startswith("prop:"):
                continue
            prop_key = record.attribute[len("prop:"):]
            template = self._PROP_LABELS.get(prop_key, "{value}")
            label = template.format(value=record.value)
            profile.add(SemanticFact(
                category="Properties",
                label=label,
                source=self.name,
                key=prop_key,
            ))


# ---------------------------------------------------------------------------
# GroupProvider
# ---------------------------------------------------------------------------

class GroupProvider(SemanticProvider):
    """
    Reads EntityGroup slot records to determine group membership.

    Searches for records where the entity name appears in a names slot,
    then contributes membership facts like "One of your dogs".
    """

    name = "group"

    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        # Search for name records on user subject
        search_results = knowledge.search_memory(
            query="names",
            subject="user",
            limit=20,
        )

        for record in search_results:
            # Only look at slot records that contain the entity in their value
            if not self._entity_in_value(entity_name, record.value):
                continue
            if "names" not in record.attribute and "group_slot" not in record.tags:
                continue

            # Extract group kind from attribute (e.g. "group:dogs:names" -> "dogs")
            group_kind = self._extract_group_kind(record.attribute, record.subject)
            if not group_kind:
                continue

            label = f"One of your {group_kind}"
            profile.add(SemanticFact(
                category="Relationships",
                label=label,
                source=self.name,
                key=f"group:{group_kind}",
            ))

    def _entity_in_value(self, entity_name: str, value: str) -> bool:
        """Check if entity name appears as a whole word in the value."""
        pattern = re.compile(
            rf"\b{re.escape(entity_name)}\b",
            re.IGNORECASE,
        )
        return bool(pattern.search(value))

    def _extract_group_kind(self, attribute: str, subject: str) -> Optional[str]:
        """
        Extract the group kind from a slot attribute string.

        Handles:
            "group:printer:names" -> "printers"
            "pet names"           -> "pets"
            "people names"        -> "people"
            "vehicle names"       -> "vehicles"
        """
        # Format 1: "group:{kind}:names"
        m = re.match(r"group:([^:]+):names?", attribute, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            return kind + "s" if not kind.endswith("s") else kind

        # Format 2: "{kind} names" e.g. "pet names", "people names"
        m = re.match(r"^(\w+)\s+names?$", attribute, re.IGNORECASE)
        if m:
            kind = m.group(1).lower()
            if kind not in ("user", "my", "your", "name"):
                return kind + "s" if not kind.endswith("s") else kind

        return None


# ---------------------------------------------------------------------------
# TemporalProvider
# ---------------------------------------------------------------------------

class TemporalProvider(SemanticProvider):
    """
    Reads records tagged with temporal information to contribute
    when-facts: "Mentioned last Monday", "Discussed yesterday".
    """

    name = "temporal"

    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        # Search all records for this entity with temporal tags
        results = knowledge.search_memory(
            query=entity_name,
            limit=20,
        )

        for record in results:
            if "temporal" not in record.tags:
                continue
            if not self._entity_in_value(entity_name, record.value):
                continue

            # Extract resolved date or expression from tags
            resolved_date = None
            expression = None
            for tag in record.tags:
                if tag.startswith("resolved:"):
                    resolved_date = tag[len("resolved:"):]
                elif tag.startswith("expr:"):
                    expression = tag[len("expr:"):]

            if expression:
                label = f"Mentioned {expression}"
            elif resolved_date:
                label = f"Mentioned on {resolved_date}"
            else:
                label = "Mentioned recently"

            profile.add(SemanticFact(
                category="Temporal",
                label=label,
                source=self.name,
                key=f"temporal:{record.attribute}",
            ))

    def _entity_in_value(self, entity_name: str, value: str) -> bool:
        pattern = re.compile(rf"\b{re.escape(entity_name)}\b", re.IGNORECASE)
        return bool(pattern.search(value))


# ---------------------------------------------------------------------------
# ConversationProvider
# ---------------------------------------------------------------------------

class ConversationProvider(SemanticProvider):
    """
    Reads recent conversation records to contribute recency facts:
    "Discussed in this conversation".
    """

    name = "conversation"

    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        results = knowledge.search_memory(
            query=entity_name,
            subject="jarvis",
            limit=10,
        )

        mentioned = False
        for record in results:
            if not self._entity_in_value(entity_name, record.value):
                continue
            mentioned = True
            break

        if mentioned:
            profile.add(SemanticFact(
                category="Conversation",
                label="Discussed recently",
                source=self.name,
                key="conversation_mention",
            ))

    def _entity_in_value(self, entity_name: str, value: str) -> bool:
        pattern = re.compile(rf"\b{re.escape(entity_name)}\b", re.IGNORECASE)
        return bool(pattern.search(value))


# ---------------------------------------------------------------------------
# SemanticRecallEngine
# ---------------------------------------------------------------------------

class SemanticRecallEngine:
    """
    Assembles a complete semantic profile for an entity by collecting
    facts from all registered providers.

    Stateless -- all state lives in KnowledgeEngine.
    Providers are registered at construction time.
    New providers can be added without modifying this class.

    Public API:
        recall(entity_name, knowledge) -> SemanticProfile
        detect_query(text) -> Optional[str]  (entity name or None)
    """

    # Patterns that trigger a "tell me everything about X" query
    _QUERY_PATTERNS: list[re.Pattern] = [
        re.compile(r"\btell\s+me\s+everything\s+about\s+([A-Za-z][\w\s\-]*?)(?:\.|$|\?)", re.IGNORECASE),
        re.compile(r"\bwhat\s+(?:do\s+you\s+know|can\s+you\s+tell\s+me)\s+about\s+([A-Za-z][\w\s\-]*?)(?:\.|$|\?)", re.IGNORECASE),
        re.compile(r"\bsummar(?:ise|ize)\s+(?:everything\s+about\s+|what\s+you\s+know\s+about\s+)?([A-Za-z][\w\s\-]*?)(?:\.|$|\?)", re.IGNORECASE),
        re.compile(r"\btell\s+me\s+about\s+([A-Za-z][\w\s\-]*?)(?:\.|$|\?)", re.IGNORECASE),
    ]

    _STOP_ENTITIES: frozenset[str] = frozenset({
        "he", "she", "it", "they", "we", "i", "you",
        "that", "this", "my", "your", "the", "a", "an",
    })

    def __init__(self, providers: Optional[list[SemanticProvider]] = None) -> None:
        self._providers: list[SemanticProvider] = providers or [
            PropertyProvider(),
            GroupProvider(),
            TemporalProvider(),
            ConversationProvider(),
        ]

    def register_provider(self, provider: SemanticProvider) -> None:
        """Register an additional provider."""
        self._providers.append(provider)

    def recall(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
    ) -> SemanticProfile:
        """
        Assemble a complete semantic profile for an entity.

        Args:
            entity_name: The entity to look up.
            knowledge:   KnowledgeEngine for all provider lookups.

        Returns:
            SemanticProfile with all known facts, or empty profile if unknown.
        """
        profile = SemanticProfile(entity_name=entity_name.title())

        for provider in self._providers:
            try:
                provider.contribute(entity_name.lower(), knowledge, profile)
            except Exception:
                logger.exception(
                    "[SEMANTIC] Provider %r failed for entity %r",
                    provider.name, entity_name,
                )

        logger.info(
            "[SEMANTIC] Recall: entity=%r facts=%d found=%s",
            entity_name, len(profile.facts), profile.found,
        )

        return profile

    def detect_query(self, text: str) -> Optional[str]:
        """
        Detect a semantic recall query and extract the entity name.

        Args:
            text: The user's raw message.

        Returns:
            Entity name string if detected, else None.
        """
        if not text or not text.strip():
            return None

        for pattern in self._QUERY_PATTERNS:
            m = pattern.search(text)
            if not m:
                continue

            entity = m.group(1).strip().rstrip("?.!")
            # Clean up trailing words like "please"
            entity = re.sub(r"\s+(?:please|now|quickly)$", "", entity, flags=re.IGNORECASE).strip()

            if entity.lower() in self._STOP_ENTITIES:
                continue
            if len(entity) < 2:
                continue

            logger.debug("[SEMANTIC] Query detected: entity=%r from %r", entity, text[:40])
            return entity

        return None
