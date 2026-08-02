"""
Relationship Recall (Genesis-032 Sprint-002)

Introduces RelationshipProvider -- a new SemanticProvider that discovers
relationships between entities from existing KnowledgeEngine records.

Also introduces RelationshipRecallEngine -- a standalone query engine for
direct relationship questions like "How is Rex related to Tom?"

Architecture:
    RelationshipProvider plugs into SemanticRecallEngine as a standard provider.
    RelationshipRecallEngine handles direct relationship queries in Agent._route().

Design constraints:
    - No AI calls
    - No new storage -- reads from KnowledgeEngine only
    - No hardcoded entity types (no if person / if pet / if device)
    - Relationship names are data, not code
    - KnowledgeEngine remains single source of truth

Relationship types discovered:
    - member_of   -- entities in the same group ("Rex and Tom are both your dogs")
    - owned_by    -- ownership from group membership ("belongs to you")
    - sibling     -- two entities in the same group

Genesis-032 Sprint-002.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.conversation.semantic_recall_engine import (
    SemanticProvider,
    SemanticProfile,
    SemanticFact,
)

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RelationshipFact -- a typed relationship between two entities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RelationshipFact:
    """
    A discovered relationship between two entities.

    entity_a:         First entity (the one being queried)
    entity_b:         Second entity (the related one), or group name
    relationship:     Relationship type ("member_of", "sibling", "owned_by")
    label:            Human-readable description
    group_kind:       The group kind if relationship comes from a group
    """
    entity_a:     str
    entity_b:     str
    relationship: str
    label:        str
    group_kind:   str = ""


# ---------------------------------------------------------------------------
# GroupRelationshipScanner -- discovers relationships from group slots
# ---------------------------------------------------------------------------

class GroupRelationshipScanner:
    """
    Scans KnowledgeEngine group slot records to discover entity relationships.

    Handles two storage formats:
        1. "group:{kind}:names"  e.g. "group:printer:names" -> "HP, Canon"
        2. "{kind} names"        e.g. "pet names" -> "rex and tom"
                                      "people names" -> "lucas and leo"
    """

    _NAME_SPLIT = re.compile(
        r"\s*,\s*(?:and\s+)?|\s+and\s+",
        re.IGNORECASE,
    )

    # Format 1: "group:{kind}:names"
    _GROUP_ATTR_V1 = re.compile(
        r"^group:([^:]+):names?$",
        re.IGNORECASE,
    )

    # Format 2: "{kind} names" e.g. "pet names", "people names", "vehicle names"
    _GROUP_ATTR_V2 = re.compile(
        r"^(\w+)\s+names?$",
        re.IGNORECASE,
    )

    # Map plural/alias kind names to canonical group kinds
    _KIND_MAP: dict[str, str] = {
        "pet":      "pets",
        "people":   "children",
        "person":   "children",
        "child":    "children",
        "children": "children",
        "vehicle":  "vehicles",
        "server":   "servers",
        "printer":  "printers",
        "dog":      "dogs",
        "dogs":     "dogs",
        "cat":      "cats",
        "cats":     "cats",
        "pets":     "pets",
    }

    def scan(self, knowledge: "KnowledgeEngine") -> dict[str, list[str]]:
        """
        Return a mapping of entity_name -> list of group_kinds.
        """
        membership: dict[str, list[str]] = {}

        # Search broadly for name records
        results = knowledge.search_memory(query="names", subject="user", limit=50)

        for record in results:
            group_kind = self._extract_kind(record.attribute)
            if not group_kind:
                continue

            names = self._split_names(record.value)
            for name in names:
                name_lower = name.lower()
                if not name_lower or len(name_lower) < 2:
                    continue
                if name_lower not in membership:
                    membership[name_lower] = []
                if group_kind not in membership[name_lower]:
                    membership[name_lower].append(group_kind)

        return membership

    # Words that are already correct plural forms -- don't add 's'
    _ALREADY_PLURAL: frozenset[str] = frozenset({
        "children", "dogs", "cats", "pets", "servers", "printers",
        "vehicles", "people", "sheep", "fish", "mice",
    })

    def _extract_kind(self, attribute: str) -> Optional[str]:
        """Extract group kind from attribute string."""
        # Format 1: "group:{kind}:names"
        m = self._GROUP_ATTR_V1.match(attribute)
        if m:
            kind = m.group(1).lower()
            return self._to_plural(kind)

        # Format 2: "{kind} names"
        m = self._GROUP_ATTR_V2.match(attribute)
        if m:
            kind = m.group(1).lower()
            if kind in ("name",):
                return None
            return self._to_plural(kind)

        return None

    def _to_plural(self, kind: str) -> str:
        """Convert a kind word to its correct plural form."""
        # Check map first
        if kind in self._KIND_MAP:
            return self._KIND_MAP[kind]
        # Already plural
        if kind in self._ALREADY_PLURAL:
            return kind
        # Default: add s
        return kind + "s"

        return None

    def _split_names(self, value: str) -> list[str]:
        """Split a name list string into individual names."""
        parts = self._NAME_SPLIT.split(value)
        return [p.strip().rstrip(".") for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# RelationshipProvider
# ---------------------------------------------------------------------------

class RelationshipProvider(SemanticProvider):
    """
    Discovers entity relationships from group membership and contributes
    them as SemanticFacts to a SemanticProfile.

    Plugs into SemanticRecallEngine like any other provider.
    No special handling required in the engine.
    """

    name = "relationship"

    def __init__(self):
        self._scanner = GroupRelationshipScanner()

    def contribute(
        self,
        entity_name: str,
        knowledge: "KnowledgeEngine",
        profile: SemanticProfile,
    ) -> None:
        """
        Add relationship facts about entity_name to profile.

        Finds all groups the entity belongs to, then finds siblings
        (other entities in the same group).
        """
        membership = self._scanner.scan(knowledge)
        entity_groups = membership.get(entity_name.lower(), [])

        for group_kind in entity_groups:
            # Find siblings -- other entities in the same group
            siblings = [
                name for name, groups in membership.items()
                if group_kind in groups and name != entity_name.lower()
            ]

            if siblings:
                sibling_names = ", ".join(s.title() for s in siblings)
                label = f"In the same group as {sibling_names} ({group_kind})"
                profile.add(SemanticFact(
                    category="Relationships",
                    label=label,
                    source=self.name,
                    key=f"sibling:{group_kind}",
                ))

        logger.debug(
            "[RELATIONSHIP] entity=%r groups=%r",
            entity_name, entity_groups,
        )


# ---------------------------------------------------------------------------
# RelationshipRecallEngine
# ---------------------------------------------------------------------------

class RelationshipRecallEngine:
    """
    Answers direct relationship questions deterministically.

    "How is Rex related to Tom?" -> "Rex and Tom are both your dogs."
    "Who is related to Leo?" -> "Leo is one of your children, along with Lucas."
    "Which printer belongs to me?" -> "HP, Canon and Epson are your printers."

    Stateless. KnowledgeEngine injected at call time.

    Public API:
        detect_query(text) -> Optional[RelationshipQuery]
        answer(query, knowledge) -> RelationshipAnswer
    """

    # ---------------------------------------------------------------------------
    # Query patterns
    # ---------------------------------------------------------------------------

    _HOW_RELATED_PATTERNS: list[re.Pattern] = [
        # "How is Rex related to Tom?"
        re.compile(
            r"\bhow\s+(?:is|are)\s+([A-Za-z][\w\-]*)\s+(?:and\s+)?(?:related\s+to|connected\s+to)\s+([A-Za-z][\w\-]*)\b",
            re.IGNORECASE,
        ),
        # "What is the relationship between Rex and Tom?"
        re.compile(
            r"\brelationship\s+between\s+([A-Za-z][\w\-]*)\s+and\s+([A-Za-z][\w\-]*)\b",
            re.IGNORECASE,
        ),
        # "Are Rex and Tom related?"
        re.compile(
            r"\bare\s+([A-Za-z][\w\-]*)\s+and\s+([A-Za-z][\w\-]*)\s+related\b",
            re.IGNORECASE,
        ),
    ]

    _WHO_RELATED_PATTERNS: list[re.Pattern] = [
        # "Who is related to Leo?"
        re.compile(r"\bwho\s+is\s+related\s+to\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
        # "Who lives with Leo?" / "Who is with Leo?"
        re.compile(r"\bwho\s+(?:lives?\s+with|is\s+with|belongs?\s+with)\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
        # "Who else is in Leo's group?"
        re.compile(r"\bwho\s+else\s+is\s+(?:in\s+)?([A-Za-z][\w\-]*)'?s?\s+group\b", re.IGNORECASE),
    ]

    _WHICH_PATTERNS: list[re.Pattern] = [
        # "Which printers belong to me?" / "Which dogs are mine?"
        re.compile(
            r"\bwhich\s+(\w+)\s+(?:belong(?:s)?\s+to\s+me|(?:are|is)\s+mine)\b",
            re.IGNORECASE,
        ),
        # "Which of my printers ..."
        re.compile(
            r"\bwhich\s+of\s+my\s+(\w+)\b",
            re.IGNORECASE,
        ),
    ]

    @dataclass(frozen=True)
    class RelationshipQuery:
        query_type: str        # "how_related", "who_related", "which_group"
        entity_a:   str        # Primary entity
        entity_b:   str = ""   # Secondary entity (for how_related)
        group_hint: str = ""   # Group kind hint (for which_group)

    @dataclass(frozen=True)
    class RelationshipAnswer:
        found:  bool
        answer: str

    def detect_query(self, text: str) -> Optional["RelationshipRecallEngine.RelationshipQuery"]:
        """
        Detect a relationship query in the user's message.

        Returns RelationshipQuery if detected, else None.
        """
        if not text or not text.strip():
            return None

        # "How is Rex related to Tom?"
        for pattern in self._HOW_RELATED_PATTERNS:
            m = pattern.search(text)
            if m:
                return self.RelationshipQuery(
                    query_type="how_related",
                    entity_a=m.group(1).strip(),
                    entity_b=m.group(2).strip(),
                )

        # "Who is related to Leo?"
        for pattern in self._WHO_RELATED_PATTERNS:
            m = pattern.search(text)
            if m:
                return self.RelationshipQuery(
                    query_type="who_related",
                    entity_a=m.group(1).strip(),
                )

        # "Which printers belong to me?"
        for pattern in self._WHICH_PATTERNS:
            m = pattern.search(text)
            if m:
                return self.RelationshipQuery(
                    query_type="which_group",
                    entity_a="",
                    group_hint=m.group(1).strip().lower(),
                )

        return None

    def answer(
        self,
        query: "RelationshipRecallEngine.RelationshipQuery",
        knowledge: "KnowledgeEngine",
    ) -> "RelationshipRecallEngine.RelationshipAnswer":
        """
        Answer a relationship query from KnowledgeEngine records.

        Args:
            query:     A RelationshipQuery from detect_query().
            knowledge: KnowledgeEngine instance.

        Returns:
            RelationshipAnswer with natural language response.
        """
        scanner = GroupRelationshipScanner()
        membership = scanner.scan(knowledge)

        if query.query_type == "how_related":
            return self._answer_how_related(query, membership)
        elif query.query_type == "who_related":
            return self._answer_who_related(query, membership)
        elif query.query_type == "which_group":
            return self._answer_which_group(query, membership)

        return self.RelationshipAnswer(found=False, answer="I'm not sure how to answer that.")

    # ------------------------------------------------------------------
    # Internal answer handlers
    # ------------------------------------------------------------------

    def _answer_how_related(
        self,
        query: "RelationshipRecallEngine.RelationshipQuery",
        membership: dict[str, list[str]],
    ) -> "RelationshipRecallEngine.RelationshipAnswer":
        """Answer: "How is Rex related to Tom?" """
        a = query.entity_a.lower()
        b = query.entity_b.lower()

        groups_a = set(membership.get(a, []))
        groups_b = set(membership.get(b, []))
        shared = groups_a & groups_b

        if shared:
            group = next(iter(shared))
            answer = (
                f"{query.entity_a.title()} and {query.entity_b.title()} "
                f"are both your {group}."
            )
            return self.RelationshipAnswer(found=True, answer=answer)

        if groups_a and not groups_b:
            answer = (
                f"I know {query.entity_a.title()} is one of your {', '.join(groups_a)}, "
                f"but I don't have any information about {query.entity_b.title()}."
            )
            return self.RelationshipAnswer(found=True, answer=answer)

        return self.RelationshipAnswer(
            found=False,
            answer=f"I don't have a relationship stored between {query.entity_a.title()} and {query.entity_b.title()}.",
        )

    def _answer_who_related(
        self,
        query: "RelationshipRecallEngine.RelationshipQuery",
        membership: dict[str, list[str]],
    ) -> "RelationshipRecallEngine.RelationshipAnswer":
        """Answer: "Who is related to Leo?" """
        entity = query.entity_a.lower()
        entity_groups = membership.get(entity, [])

        if not entity_groups:
            return self.RelationshipAnswer(
                found=False,
                answer=f"I don't have any relationship information stored about {query.entity_a.title()}.",
            )

        parts = []
        for group_kind in entity_groups:
            siblings = [
                name.title() for name, groups in membership.items()
                if group_kind in groups and name != entity
            ]
            if siblings:
                if len(siblings) == 1:
                    parts.append(
                        f"{query.entity_a.title()} is one of your {group_kind}, "
                        f"along with {siblings[0]}."
                    )
                else:
                    sibling_str = ", ".join(siblings[:-1]) + f" and {siblings[-1]}"
                    parts.append(
                        f"{query.entity_a.title()} is one of your {group_kind}, "
                        f"along with {sibling_str}."
                    )
            else:
                parts.append(
                    f"{query.entity_a.title()} is your only {group_kind.rstrip('s')}."
                )

        return self.RelationshipAnswer(found=True, answer=" ".join(parts))

    def _answer_which_group(
        self,
        query: "RelationshipRecallEngine.RelationshipQuery",
        membership: dict[str, list[str]],
    ) -> "RelationshipRecallEngine.RelationshipAnswer":
        """Answer: "Which printers belong to me?" """
        hint = query.group_hint.lower().rstrip("s")  # normalize: "dogs" -> "dog"

        # Collect all unique group kinds
        all_kinds: set[str] = set()
        for groups in membership.values():
            all_kinds.update(groups)

        # Find matching kind -- exact first, then partial
        matched_kind = None
        for kind in all_kinds:
            kind_stem = kind.rstrip("s")
            if kind_stem == hint or kind == query.group_hint.lower():
                matched_kind = kind
                break

        # Broader match -- hint stem appears in kind or kind appears in hint
        if not matched_kind:
            for kind in all_kinds:
                kind_stem = kind.rstrip("s")
                if hint in kind_stem or kind_stem in hint:
                    matched_kind = kind
                    break

        # Synonym match -- "dogs" -> "pets", "kids" -> "children"
        _SYNONYMS: dict[str, list[str]] = {
            "dog":      ["pet", "pets"],
            "dogs":     ["pet", "pets"],
            "cat":      ["pet", "pets"],
            "cats":     ["pet", "pets"],
            "kid":      ["children", "child", "people"],
            "kids":     ["children", "child", "people"],
            "child":    ["children", "people"],
            "children": ["people"],
        }
        if not matched_kind:
            synonyms = _SYNONYMS.get(hint, []) + _SYNONYMS.get(query.group_hint.lower(), [])
            for kind in all_kinds:
                if kind in synonyms or kind.rstrip("s") in synonyms:
                    matched_kind = kind
                    break

        if not matched_kind:
            return self.RelationshipAnswer(
                found=False,
                answer=f"I don't have any {query.group_hint} stored.",
            )

        # Collect members of matched kind
        matches = [
            name.title() for name, groups in membership.items()
            if matched_kind in groups
        ]

        if not matches:
            return self.RelationshipAnswer(
                found=False,
                answer=f"I don't have any {query.group_hint} stored.",
            )

        if len(matches) == 1:
            answer = f"{matches[0]} is your {matched_kind.rstrip('s')}."
        elif len(matches) == 2:
            answer = f"{matches[0]} and {matches[1]} are your {matched_kind}."
        else:
            names = ", ".join(matches[:-1]) + f" and {matches[-1]}"
            answer = f"{names} are your {matched_kind}."

        return self.RelationshipAnswer(found=True, answer=answer)
