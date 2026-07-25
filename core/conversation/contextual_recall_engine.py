"""
Jarvis Contextual Recall Engine (Genesis-025 Sprint-004)

Lightweight orchestration layer that resolves conversational context
before delegating to ConversationRecall for factual lookup.

Responsibilities:
    - Resolve pronoun references (their, them, those, it, they)
    - Resolve active group context (active_topic → kind → attribute)
    - Normalize natural paraphrases to canonical slot names
    - Rewrite contextual recall requests into explicit recall operations
    - Delegate all factual lookup to ConversationRecall

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
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_recall import ConversationRecall, RecallResult
    from core.conversation.session_context import SessionContext

from core.conversation.entity_group_registry import EntityGroupRegistry, SLOT_SCHEMAS

logger = logging.getLogger(__name__)


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

    Genesis-025 Sprint-004.
    """
    subject:   str    # e.g. "user"
    attribute: str    # e.g. "pet names", "group:server:roles"


# ---------------------------------------------------------------------------
# Slot resolution patterns
#
# Genesis-026 Sprint-001: Each pattern group maps natural paraphrases
# to a canonical slot name. All patterns are entity-agnostic — they
# work for any EntityGroup kind without special-casing.
#
# Design principle: semantic equivalence over exact wording.
# "Who are they?" and "What are their names?" both resolve to slot="names".
# ---------------------------------------------------------------------------

# NAMES slot — "What are their names?", "Who are they?", "What are they called?"
_NAMES_PATTERNS = [
    # Canonical: "What are their names?" / "What are my dogs' names?"
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+names?\b",
        re.IGNORECASE,
    ),
    # Identity: "Who are they?" / "Who are those?" / "Who are them?"
    re.compile(
        r"\bwho\s+(?:are|were|is)\s+(?:they|those|them)\b",
        re.IGNORECASE,
    ),
    # Called/named: "What are they called?" / "What did I call them?"
    # "What are my dogs called?" / "What did I name them?"
    re.compile(
        r"\bwhat\s+(?:are|were)\s+(?:they|those|my\s+\w+(?:'s?)?)\s+(?:called|named)\b",
        re.IGNORECASE,
    ),
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
    # Can you: "Can you tell me their names?" / "Can you remind me what they're called?"
    re.compile(
        r"\bcan\s+you\s+(?:tell|remind)\s+me\s+(?:their\s+names?|what\s+they(?:'re|\s+are)\s+called)\b",
        re.IGNORECASE,
    ),
    # Which names: "Which names did I give them?" / "What names did I give them?"
    re.compile(
        r"\b(?:which|what)\s+names?\s+did\s+(?:i|you)\s+give\s+(?:them|those)\b",
        re.IGNORECASE,
    ),
    # Again: "Tell me their names again" / "What were their names again?"
    re.compile(
        r"\bwhat\s+(?:are|were)\s+their\s+names?\s+again\b",
        re.IGNORECASE,
    ),
]

# COLOURS slot — "What colour are they?", "What do they look like?"
_COLOURS_PATTERNS = [
    re.compile(
        r"\bwhat\s+colou?rs?\s+(?:are|were|is)\s+(?:they|those|them)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+colou?r\s+(?:are|is)\s+(?:they|those|it)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+colou?rs?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:do|did)\s+they\s+look\s+like\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdescribe\s+(?:them|those|it)\b",
        re.IGNORECASE,
    ),
]

# AGES slot — "How old are they?", "What are their ages?"
_AGES_PATTERNS = [
    re.compile(
        r"\bhow\s+old\s+(?:are|were|is)\s+(?:they|those|them|it)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+ages?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:ages?|age)\s+(?:are|were|is)\s+(?:they|those|them)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\btell\s+me\s+(?:their\s+ages?|how\s+old\s+they\s+are)\b",
        re.IGNORECASE,
    ),
]

# BREEDS slot — "What breed are they?", "What are their breeds?"
_BREEDS_PATTERNS = [
    re.compile(
        r"\bwhat\s+breeds?\s+(?:are|were|is)\s+(?:they|those|them|it)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+breeds?\b",
        re.IGNORECASE,
    ),
]

# ROLES slot — "What are their roles?", "What do they do?"
_ROLES_PATTERNS = [
    re.compile(
        r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+roles?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat\s+(?:do|did)\s+they\s+do\b",
        re.IGNORECASE,
    ),
]

# Master slot → pattern list mapping
_SLOT_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("names",   _NAMES_PATTERNS),
    ("colours", _COLOURS_PATTERNS),
    ("ages",    _AGES_PATTERNS),
    ("breeds",  _BREEDS_PATTERNS),
    ("roles",   _ROLES_PATTERNS),
]

# ---------------------------------------------------------------------------
# Anaphoric query detection for can_answer()
# ---------------------------------------------------------------------------

_ANY_CONTEXTUAL = re.compile(
    r"\b(?:"
    r"what\s+(?:are|were|did|do|colou?r)\s+(?:they|those|them|their|my\s+\w)"
    r"|who\s+(?:are|were|is)\s+(?:they|those|them)\b"
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


class ContextualRecallEngine:
    """
    Resolves conversational context before delegating to ConversationRecall.

    Genesis-026 Sprint-001: Expanded semantic coverage — multiple natural
    phrasings now resolve to the same RecallRequest without entity-specific
    logic. All patterns are generic and slot-agnostic where possible.

    Public API:
        can_answer(query, session) -> bool
        resolve(query, session) -> Optional[RecallRequest]
        answer(query, session, recall) -> Optional[RecallResult]  # for tests
    """

    def __init__(self) -> None:
        self._registry = EntityGroupRegistry()

    def can_answer(self, query: str, session: "SessionContext") -> bool:
        """
        Return True if this engine can handle the query using session context.
        """
        if not query or not session:
            return False
        if not session.active_topic:
            return False
        return bool(_ANY_CONTEXTUAL.search(query))

    def resolve(
        self,
        query: str,
        session: "SessionContext",
    ) -> "Optional[RecallRequest]":
        """
        Resolve conversational context into a structured RecallRequest.
        """
        if not session.active_topic:
            return None

        active_topic = session.active_topic.value
        kind = self._registry.infer_kind(active_topic)

        if not kind:
            logger.debug(
                "[CTXRECALL] Cannot infer kind from active_topic=%r", active_topic
            )
            return None

        slot = self._resolve_slot(query, kind)
        if not slot:
            return None

        attr = _KIND_SLOT_TO_ATTR.get((kind, slot), f"group:{kind}:{slot}")

        logger.info(
            "[CTXRECALL] Resolved: query=%r active_topic=%r kind=%r slot=%r attr=%r",
            query, active_topic, kind, slot, attr,
        )

        return RecallRequest(subject="user", attribute=attr)

    def answer(
        self,
        query: str,
        session: "SessionContext",
        recall: "ConversationRecall",
    ) -> "Optional[RecallResult]":
        """
        Convenience method for tests.

        # TODO (Genesis-026): Agent should use resolve() + recall.lookup()
        # directly for cleaner separation.
        """
        req = self.resolve(query, session)
        if req is None:
            return None
        return recall.lookup(req.subject, req.attribute)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_slot(self, query: str, kind: str) -> Optional[str]:
        """
        Determine which slot the query is asking about.

        Genesis-026 Sprint-001: Expanded from 2 patterns to full semantic
        coverage across names, colours, ages, breeds, roles.
        All patterns are entity-agnostic.

        Returns the slot name (e.g. "names", "colours") or None.
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