"""
Jarvis Contextual Recall Engine (Genesis-025 Sprint-004)

Lightweight orchestration layer that resolves conversational context
before delegating to ConversationRecall for factual lookup.

Responsibilities:
    - Resolve pronoun references (their, them, those, it, they)
    - Resolve active group context (active_topic → kind → attribute)
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
"""

from __future__ import annotations

import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_recall import ConversationRecall, RecallResult
    from core.conversation.session_context import SessionContext

from core.conversation.entity_group_registry import EntityGroupRegistry, SLOT_SCHEMAS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured recall request
# ---------------------------------------------------------------------------

from dataclasses import dataclass

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
# Contextual query patterns
#
# These patterns identify queries that require conversational context
# to resolve — they cannot be answered by ConversationRecall alone.
# ---------------------------------------------------------------------------

# Anaphoric name queries — "What are their names?" / "What are my dogs' names?"
_ANAPHORIC_NAMES = re.compile(
    r"\bwhat\s+(?:are\s+)?(?:their|(?:my\s+)?(?:\w+(?:'s?)?)\s+)?names?\b",
    re.IGNORECASE,
)

# Anaphoric attribute queries — "What are their colours?" / "How old are they?"
_ANAPHORIC_ATTR = re.compile(
    r"\bwhat\s+(?:are\s+)?(?:their|my\s+\w+(?:'s?)?)\s+"
    r"(?P<attr>colours?|colors?|breeds?|ages?|roles?|makes?|types?)\b",
    re.IGNORECASE,
)

# Slot attribute name normalisation
_ATTR_CANONICAL: dict[str, str] = {
    "colour": "colours", "color": "colours", "colors": "colours",
    "breed": "breeds", "age": "ages", "role": "roles",
    "make": "makes", "type": "types",
}

# KnowledgeEngine attribute name for each (kind, slot) pair
# Mirrors _COMPAT_SLOT_KEYS in SlotCompletionEngine
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

    The Agent calls can_answer() and answer() here first. If this engine
    can resolve the query using SessionContext, it does so and returns.
    Otherwise it returns None and the Agent falls through to ConversationRecall.

    Public API:
        can_answer(query, session) -> bool
        answer(query, session, recall) -> Optional[RecallResult]
    """

    def __init__(self) -> None:
        self._registry = EntityGroupRegistry()

    def can_answer(self, query: str, session: "SessionContext") -> bool:
        """
        Return True if this engine can handle the query using session context.

        Only returns True when:
        1. The query is anaphoric (uses "their", "my X's"), AND
        2. There is an active group topic in SessionContext
        """
        if not query or not session:
            return False

        if not session.active_topic:
            return False

        return bool(
            _ANAPHORIC_NAMES.search(query) or
            _ANAPHORIC_ATTR.search(query)
        )

    def resolve(
        self,
        query: str,
        session: "SessionContext",
    ) -> "Optional[RecallRequest]":
        """
        Resolve conversational context into a structured RecallRequest.

        The Agent passes the returned RecallRequest to
        ConversationRecall.lookup() — keeping the two components
        fully decoupled. Genesis-025 Sprint-004.

        Args:
            query:   The user's natural language question.
            session: Current SessionContext (read-only).

        Returns:
            RecallRequest if resolved, None if context insufficient.
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
        Resolve conversational context and delegate to ConversationRecall.

        Convenience method for tests. In production, Agent should prefer
        resolve() + recall.lookup() for cleaner separation.

        # TODO (Genesis-026): Remove this method once Agent uses resolve()
        # directly. This exists only for test compatibility during Sprint-004.
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

        Returns the slot name (e.g. "names", "colours") or None.
        """
        # "What are their names?" / "What are my dogs' names?"
        if _ANAPHORIC_NAMES.search(query):
            return "names"

        # "What are their colours?" / "What are their ages?"
        m = _ANAPHORIC_ATTR.search(query)
        if m:
            raw_attr = m.group("attr").lower().rstrip("s") + "s"
            return _ATTR_CANONICAL.get(raw_attr, raw_attr)

        return None