"""
Jarvis Contextual Recall Engine (Genesis-025 Sprint-004)

Lightweight orchestration layer that resolves conversational context
before delegating to ConversationRecall for factual lookup.

Responsibilities:
    - Resolve pronoun references (their, them, those, it, they)
    - Resolve active group context (active_topic → kind → attribute)
    - Normalize natural paraphrases to canonical slot names
    - Distinguish attribute questions from identity questions
    - Rewrite contextual recall requests into explicit recall operations
    - Delegate all factual lookup to ConversationRecall
    - Perform reverse member lookup ("Who is Rex?" → "Rex is one of your dogs.")

Does NOT:
    - Store data
    - Query AI
    - Access KnowledgeEngine directly
    - Contain noun-specific logic

Design constraints:
    - Receives SessionContext and ConversationRecall as dependencies
    - ConversationRecall remains unaware of SessionContext
    - Stateless — same inputs → same output
    - Generic — works for any EntityGroup kind

Architecture position:
    Agent
        └── ContextualRecallEngine   ← this module
                └── ConversationRecall
                        └── KnowledgeEngine

Genesis-026 Sprint-001:
    Expanded semantic coverage — multiple natural phrasings normalize
    to the same RecallRequest without adding entity-specific logic.

Genesis-026 Sprint-002:
    Identity vs Attribute distinction — "Who are they?" returns entity
    classification, "What are their names?" returns a property value.
    ResolutionType enum used for type safety and future extensibility.

Genesis-026 Sprint-003:
    Reverse entity lookup — "Who is Rex?" → "Rex is one of your dogs."
    ReverseLookupRequest dataclass added. reverse_lookup() method added.
    Parser (ReverseEntityParser) is responsible for query parsing;
    this module is responsible only for reasoning and lookup.
    Works for any member identifier: Rex, staging, db01, GPU-7, printer3.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_recall import ConversationRecall, RecallResult
    from core.conversation.session_context import SessionContext

from core.conversation.entity_group_registry import (
    EntityGroupRegistry, SLOT_SCHEMAS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ResolutionType enum
#
# Genesis-026 Sprint-002: typed enum replaces string literals for safety
# and future extensibility. New resolution types (SUMMARY, COUNT, etc.)
# can be added here without changing existing code paths.
# ---------------------------------------------------------------------------

class ResolutionType(Enum):
    ATTRIBUTE = auto()   # "What are their names?" → return a property
    IDENTITY  = auto()   # "Who are they?" → return what the entity IS


# ---------------------------------------------------------------------------
# Structured recall request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecallRequest:
    """
    Structured recall request produced by ContextualRecallEngine.

    Separates conversational context resolution from factual retrieval.
    The Agent passes this to ConversationRecall.lookup() — neither
    component needs to know about the other's internals.

    Genesis-025 Sprint-004: initial version.
    Genesis-026 Sprint-002: added resolution_type for identity vs attribute.
    """
    subject:         str             # e.g. "user"
    attribute:       str             # e.g. "pet names", "group:server:roles"
    resolution_type: ResolutionType = ResolutionType.ATTRIBUTE
    kind:            str = ""        # e.g. "animal" — used for identity answers


# ---------------------------------------------------------------------------
# Reverse lookup request (Genesis-026 Sprint-003)
#
# Produced by ReverseEntityParser from raw queries like "Who is Rex?".
# Passed to ContextualRecallEngine.reverse_lookup() for reasoning.
# Keeps parsing entirely separate from lookup reasoning — the parser
# evolves independently as new phrasings are added.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReverseLookupRequest:
    """
    Structured request for reverse member lookup.

    Created by ReverseEntityParser, consumed by
    ContextualRecallEngine.reverse_lookup().

    members: List of extracted member identifiers (e.g. ["Rex"],
             ["Rex", "Tom"], ["staging"], ["db01", "prod"]).
             Identifiers are preserved as extracted — no name
             classification is applied.

    Genesis-026 Sprint-003.
    """
    members: list[str]


# ---------------------------------------------------------------------------
# Identity patterns
#
# Genesis-026 Sprint-002: questions that ask WHAT something IS, not
# what a specific property is. Separate from attribute patterns.
# All patterns are entity-agnostic.
# ---------------------------------------------------------------------------

_IDENTITY_PATTERNS = [
    # "Who are they?" / "Who are those?" / "Who are them?"
    re.compile(
        r"\bwho\s+(?:are|were|is)\s+(?:they|those|them)\b",
        re.IGNORECASE,
    ),
    # "Who are my dogs?" / "Who are my children?"
    re.compile(
        r"\bwho\s+are\s+my\s+\w+\b",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Attribute slot resolution patterns
#
# Genesis-026 Sprint-001: Each pattern group maps natural paraphrases
# to a canonical slot name. All patterns are entity-agnostic.
# Genesis-026 Sprint-002: "who" patterns moved to _IDENTITY_PATTERNS.
# ---------------------------------------------------------------------------

_NAMES_PATTERNS = [
    # Canonical: "What are their names?" / "What are my dogs' names?"
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+names?\b",
        re.IGNORECASE,
    ),
    # Called/named: "What are they called?" / "What are my dogs called?"
    re.compile(
        r"\bwhat\s+(?:are|were)\s+(?:they|those|my\s+\w+(?:'s?)?)\s+(?:called|named)\b",
        re.IGNORECASE,
    ),
    # "What did I call them?" / "What did I name them?"
    re.compile(
        r"\bwhat\s+did\s+(?:i|you)\s+(?:call|name)\s+(?:them|those)\b",
        re.IGNORECASE,
    ),
    # Remind: "Remind me of their names" / "Remind me what they're called"
    re.compile(
        r"\bremind\s+me\s+(?:of\s+)?(?:their\s+names?|what\s+they(?:'re|\s+are)\s+called)\b",
        re.IGNORECASE,
    ),
    # Tell: "Tell me their names" / "Tell me their names again"
    re.compile(
        r"\btell\s+me\s+(?:their\s+names?|what\s+they(?:'re|\s+are)\s+called)\b",
        re.IGNORECASE,
    ),
    # Can you: "Can you tell me their names?"
    re.compile(
        r"\bcan\s+you\s+(?:tell|remind)\s+me\s+(?:their\s+names?|what\s+they(?:'re|\s+are)\s+called)\b",
        re.IGNORECASE,
    ),
    # Which names: "Which names did I give them?"
    re.compile(
        r"\b(?:which|what)\s+names?\s+did\s+(?:i|you)\s+give\s+(?:them|those)\b",
        re.IGNORECASE,
    ),
    # Again: "What were their names again?"
    re.compile(
        r"\bwhat\s+(?:are|were)\s+their\s+names?\s+again\b",
        re.IGNORECASE,
    ),
]

_COLOURS_PATTERNS = [
    re.compile(r"\bwhat\s+colou?rs?\s+(?:are|were|is)\s+(?:they|those|them)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+colou?r\s+(?:are|is)\s+(?:they|those|it)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+colou?rs?\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:do|did)\s+they\s+look\s+like\b", re.IGNORECASE),
    re.compile(r"\bdescribe\s+(?:them|those|it)\b", re.IGNORECASE),
]

_AGES_PATTERNS = [
    re.compile(r"\bhow\s+old\s+(?:are|were|is)\s+(?:they|those|them|it)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+ages?\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:ages?|age)\s+(?:are|were|is)\s+(?:they|those|them)\b", re.IGNORECASE),
    re.compile(r"\btell\s+me\s+(?:their\s+ages?|how\s+old\s+they\s+are)\b", re.IGNORECASE),
]

_BREEDS_PATTERNS = [
    re.compile(r"\bwhat\s+breeds?\s+(?:are|were|is)\s+(?:they|those|them|it)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+breeds?\b", re.IGNORECASE),
]

_ROLES_PATTERNS = [
    re.compile(r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+roles?\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:do|did)\s+they\s+do\b", re.IGNORECASE),
]

# Master slot → pattern list mapping (attribute questions only)
_SLOT_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("names",   _NAMES_PATTERNS),
    ("colours", _COLOURS_PATTERNS),
    ("ages",    _AGES_PATTERNS),
    ("breeds",  _BREEDS_PATTERNS),
    ("roles",   _ROLES_PATTERNS),
]

# ---------------------------------------------------------------------------
# can_answer() detection pattern
# ---------------------------------------------------------------------------

_ANY_CONTEXTUAL = re.compile(
    r"\b(?:"
    r"what\s+(?:are|were|did|do|colou?r)\s+(?:they|those|them|their|my\s+\w)"
    r"|who\s+(?:are|were|is)\s+(?:they|those|them|my\s+\w)\b"
    r"|how\s+old\s+(?:are|were|is)\s+(?:they|those|them|it)"
    r"|remind\s+me"
    r"|tell\s+me\s+their"
    r"|can\s+you\s+(?:tell|remind)\s+me\s+their"
    r"|describe\s+(?:them|those|it)"
    r"|which\s+names?\s+did\s+(?:i|you)\s+give"
    r"|what\s+did\s+(?:i|you)\s+(?:call|name)\s+(?:them|those)"
    r")",
    re.IGNORECASE,
)

# KnowledgeEngine attribute name for each (kind, slot) pair
_KIND_SLOT_TO_ATTR: dict[tuple[str, str], str] = {
    ("animal",  "names"):   "pet names",
    ("animal",  "colours"): "pet colours",
    ("animal",  "breeds"):  "pet breeds",
    ("animal",  "ages"):    "pet ages",
    ("person",  "names"):   "people names",
    ("person",  "roles"):   "people roles",
    ("vehicle", "names"):   "vehicle names",
    ("vehicle", "colours"): "vehicle colours",
    ("instrument", "names"): "instrument names",
    ("server",  "names"):   "server names",
    ("project", "names"):   "project names",
}

# KnowledgeEngine attribute for group declarations (kind → attribute)
_KIND_TO_DECLARATION_ATTR: dict[str, str] = {
    "animal":     "pets",
    "person":     "people",
    "vehicle":    "vehicles",
    "instrument": "instruments",
    "server":     "servers",
    "project":    "projects",
}

# ---------------------------------------------------------------------------
# Reverse lookup support (Genesis-026 Sprint-003)
#
# _NAMES_ATTR_TO_KIND: inverted from _KIND_SLOT_TO_ATTR for names slot only.
# Maps KnowledgeEngine "names" attribute key → entity kind.
# e.g. "pet names" → "animal", "server names" → "server"
#
# Computed at module load — no runtime cost, no duplicate state.
# Automatically includes any new (kind, "names") entries added to
# _KIND_SLOT_TO_ATTR in the future.
# ---------------------------------------------------------------------------

_NAMES_ATTR_TO_KIND: dict[str, str] = {
    attr: kind
    for (kind, slot), attr in _KIND_SLOT_TO_ATTR.items()
    if slot == "names"
}


class ContextualRecallEngine:
    """
    Resolves conversational context before delegating to ConversationRecall.

    Genesis-026 Sprint-002: Distinguishes attribute questions ("What are
    their names?") from identity questions ("Who are they?") using the
    ResolutionType enum. The Agent formats the answer differently based
    on the resolution type.

    Genesis-026 Sprint-003: Adds reverse_lookup() for member-to-group
    resolution ("Who is Rex?" → "Rex is one of your dogs."). The parser
    (ReverseEntityParser) is responsible for extracting member names from
    raw queries; this engine is responsible only for reasoning and lookup.

    Public API:
        can_answer(query, session) -> bool
        resolve(query, session) -> Optional[RecallRequest]
        answer(query, session, recall) -> Optional[RecallResult]
        reverse_lookup(request, recall) -> Optional[RecallResult]  # Sprint-003
    """

    def __init__(self) -> None:
        self._registry = EntityGroupRegistry()

    def can_answer(self, query: str, session: "SessionContext") -> bool:
        """Return True if this engine can handle the query using session context."""
        if not query or not session:
            return False
        if not session.active_topic:
            return False
        # Check identity patterns too
        for pattern in _IDENTITY_PATTERNS:
            if pattern.search(query):
                return True
        return bool(_ANY_CONTEXTUAL.search(query))

    def resolve(
        self,
        query: str,
        session: "SessionContext",
    ) -> "Optional[RecallRequest]":
        """
        Resolve conversational context into a structured RecallRequest.

        Genesis-026 Sprint-002: returns ResolutionType.IDENTITY for
        identity questions, ResolutionType.ATTRIBUTE for attribute questions.
        """
        if not session.active_topic:
            return None

        active_topic = session.active_topic.value
        kind = self._registry.infer_kind(active_topic)

        if not kind:
            logger.debug("[CTXRECALL] Cannot infer kind from active_topic=%r", active_topic)
            return None

        # Check identity patterns first — they take priority
        for pattern in _IDENTITY_PATTERNS:
            if pattern.search(query):
                # Identity: return the group declaration attribute
                decl_attr = _KIND_TO_DECLARATION_ATTR.get(kind, f"group:{kind}")
                logger.info(
                    "[CTXRECALL] Identity: query=%r kind=%r attr=%r",
                    query, kind, decl_attr,
                )
                return RecallRequest(
                    subject="user",
                    attribute=decl_attr,
                    resolution_type=ResolutionType.IDENTITY,
                    kind=kind,
                )

        # Attribute: resolve slot and return attribute
        slot = self._resolve_slot(query, kind)
        if not slot:
            return None

        attr = _KIND_SLOT_TO_ATTR.get((kind, slot), f"group:{kind}:{slot}")
        logger.info(
            "[CTXRECALL] Attribute: query=%r kind=%r slot=%r attr=%r",
            query, kind, slot, attr,
        )
        return RecallRequest(
            subject="user",
            attribute=attr,
            resolution_type=ResolutionType.ATTRIBUTE,
            kind=kind,
        )

    def answer(
        self,
        query: str,
        session: "SessionContext",
        recall: "ConversationRecall",
    ) -> "Optional[RecallResult]":
        """
        Resolve and delegate to ConversationRecall.

        Genesis-026 Sprint-002: identity questions do a two-step lookup
        to compose a natural identity answer.
        """
        req = self.resolve(query, session)
        if req is None:
            return None

        if req.resolution_type == ResolutionType.IDENTITY:
            return self._answer_identity(req, recall)

        return recall.lookup(req.subject, req.attribute)

    def reverse_lookup(
        self,
        request: ReverseLookupRequest,
        recall: "ConversationRecall",
    ) -> "Optional[RecallResult]":
        """
        Perform reverse member lookup: given member identifiers, find which
        EntityGroup they belong to and compose a natural identity answer.

        Called by the Agent after ReverseEntityParser has parsed the raw
        query into a ReverseLookupRequest. This method contains only
        reasoning and lookup — no query parsing.

        Algorithm:
            For each known names attribute (pet names, server names, etc.):
                1. Look up the stored value (e.g. "Rex and Tom")
                2. Check whether any queried member appears in that value
                3. If found, look up the group declaration (e.g. "2 dogs")
                4. Compose and return the answer

        Handles single and multiple members generically.
        Works for any identifier: Rex, staging, db01, GPU-7, printer3.

        Args:
            request: ReverseLookupRequest with extracted member list.
            recall:  ConversationRecall instance for KnowledgeEngine access.

        Returns:
            RecallResult with a natural answer, or None if not found.

        Genesis-026 Sprint-003.
        """
        from core.conversation.conversation_recall import RecallResult

        if not request.members:
            return None

        members_lower = [m.lower() for m in request.members]

        # Search all known names attributes for a match.
        # _NAMES_ATTR_TO_KIND is derived from _KIND_SLOT_TO_ATTR at module
        # load — no hardcoding, automatically covers all registered kinds.
        for names_attr, kind in _NAMES_ATTR_TO_KIND.items():
            names_result = recall.lookup("user", names_attr)
            if not names_result or not names_result.found or not names_result.value:
                continue

            stored_names_lower = names_result.value.lower()

            # Check whether any queried member appears in the stored value.
            # Word-boundary check: "Rex" should not match "Rexton".
            matched = [
                m for m in request.members
                if re.search(
                    r"(?<![a-z0-9_-])" + re.escape(m.lower()) + r"(?![a-z0-9_-])",
                    stored_names_lower,
                )
            ]

            if not matched:
                continue

            # Found — look up the group declaration for count/noun context.
            decl_attr = _KIND_TO_DECLARATION_ATTR.get(kind, f"group:{kind}")
            decl_result = recall.lookup("user", decl_attr)
            declaration = decl_result.value if decl_result and decl_result.found else None

            answer = self._compose_reverse_answer(matched, kind, declaration)

            logger.info(
                "[CTXRECALL] Reverse lookup: members=%r kind=%r decl=%r → %r",
                matched, kind, declaration, answer,
            )

            return RecallResult(
                found=True,
                answer=answer,
                attribute=names_attr,
                value=names_result.value,
            )

        logger.debug(
            "[CTXRECALL] Reverse lookup: no match found for members=%r",
            request.members,
        )
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compose_reverse_answer(
        self,
        matched: list[str],
        kind: str,
        declaration: Optional[str],
    ) -> str:
        """
        Compose a natural identity answer for a reverse lookup result.

        Single member:   "Rex is one of your dogs."
        Multiple members: "Rex and Tom are your dogs."

        The noun comes from the group declaration (e.g. "2 dogs") when
        available, or falls back to the entity kind (e.g. "animals").

        Args:
            matched:     List of matched member identifiers.
            kind:        Entity kind string (e.g. "animal", "server").
            declaration: Group declaration value (e.g. "2 dogs"), or None.

        Returns:
            A natural language answer string.
        """
        # Extract the noun from the declaration (e.g. "dogs" from "2 dogs")
        # or fall back to kind-based noun.
        if declaration:
            # Take the last word of the declaration as the noun
            # "2 dogs" → "dogs", "5 servers" → "servers", "some children" → "children"
            noun = declaration.split()[-1]
        else:
            # Fallback: use the kind with a generic plural
            _KIND_NOUNS: dict[str, str] = {
                "animal":     "pets",
                "person":     "people",
                "vehicle":    "vehicles",
                "instrument": "instruments",
                "server":     "servers",
                "project":    "projects",
            }
            noun = _KIND_NOUNS.get(kind, f"{kind}s")

        if len(matched) == 1:
            name = matched[0].capitalize()
            return f"{name} is one of your {noun}."
        else:
            # Join multiple names naturally: "Rex and Tom" or "Rex, Tom and Max"
            if len(matched) == 2:
                names_str = f"{matched[0].capitalize()} and {matched[1].capitalize()}"
            else:
                caps = [m.capitalize() for m in matched]
                names_str = ", ".join(caps[:-1]) + f" and {caps[-1]}"
            return f"{names_str} are your {noun}."

    def _answer_identity(
        self,
        req: RecallRequest,
        recall: "ConversationRecall",
    ) -> "Optional[RecallResult]":
        """
        Compose an identity answer from group declaration + member names.

        Two-step lookup:
        1. Group declaration: recall("user", "pets") → "2 dogs"
        2. Member names: recall("user", "pet names") → "Rex and Max"

        Answer: "Rex and Max are your 2 dogs."

        If names are not stored, falls back to declaration only:
        "You have 2 dogs."
        """
        from core.conversation.conversation_recall import RecallResult

        # Step 1: group declaration ("2 dogs", "5 servers")
        decl_result = recall.lookup(req.subject, req.attribute)

        if not decl_result or not decl_result.found:
            return None

        declaration = decl_result.value  # e.g. "2 dogs"

        # Step 2: member names
        names_attr = _KIND_SLOT_TO_ATTR.get((req.kind, "names"), f"group:{req.kind}:names")
        names_result = recall.lookup(req.subject, names_attr)

        if names_result and names_result.found and names_result.value:
            answer = f"{names_result.value} are your {declaration}."
        else:
            answer = f"You have {declaration}."

        logger.info("[CTXRECALL] Identity answer: %r", answer)

        return RecallResult(
            found=True,
            answer=answer,
            attribute=req.attribute,
            value=declaration,
        )

    def _resolve_slot(self, query: str, kind: str) -> Optional[str]:
        """
        Determine which attribute slot the query is asking about.

        Returns the slot name (e.g. "names", "colours") or None.
        Identity questions are handled before this method is called.
        """
        for slot, patterns in _SLOT_PATTERNS:
            for pattern in patterns:
                if pattern.search(query):
                    logger.debug(
                        "[CTXRECALL] Slot=%r matched by pattern %r",
                        slot, pattern.pattern[:40],
                    )
                    return slot
        return None