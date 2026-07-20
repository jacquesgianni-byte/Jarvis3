"""
Jarvis Conversation Memory — Conversation Observer (Genesis-020 Sprint-001)

Observes every conversation turn and automatically extracts and stores
facts using the KnowledgeEngine.

Architecture:
    Agent calls observer.observe(user_message, jarvis_response) after
    every successful response. The observer is fire-and-forget from the
    Agent's perspective — it never blocks the conversation pipeline.

    ConversationObserver
        → FactExtractor.extract(user_message)
        → FactClassifier.classify(fact) → (category, attribute)
        → KnowledgeEngine.store_memory(...)

    Also maintains a lightweight ConversationJournal: a rolling log
    of recent conversation turns stored as system-category records
    in the KnowledgeEngine.

Constitutional constraints:
    - Never blocks the conversation pipeline.
    - Never calls AI providers.
    - All fact extraction is deterministic.
    - Uses KnowledgeEngine as the ONLY storage mechanism.
    - Gracefully handles all exceptions — a memory failure must
      never crash Jarvis.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from core.conversation.fact_extractor import ExtractedFact, FactExtractor, FactType
from core.knowledge_engine.models import MemorySource

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fact type → Knowledge Engine category mapping
# ---------------------------------------------------------------------------

_FACT_TYPE_TO_CATEGORY: dict[FactType, str] = {
    FactType.PROJECT:     "projects",
    FactType.MILESTONE:   "projects",
    FactType.TASK:        "projects",
    FactType.ACHIEVEMENT: "projects",
    FactType.PERSON:      "relationships",
    FactType.DECISION:    "general",
    FactType.PREFERENCE:  "preferences",
    FactType.UNKNOWN:     "general",
}

# Maximum number of journal entries to keep
_JOURNAL_MAX_ENTRIES = 50

# Subject used for journal entries
_JOURNAL_SUBJECT = "jarvis"


class ConversationObserver:
    """
    Observes conversation turns and stores extracted facts automatically.

    Called by the Agent after every successful response. Extracts facts
    from the user's message and stores them via the KnowledgeEngine.
    Also maintains a rolling conversation journal for temporal recall.

    This class is the bridge between raw conversation and structured memory.
    """

    def __init__(self, knowledge: "KnowledgeEngine"):
        """
        Args:
            knowledge: The KnowledgeEngine instance (owned by the Agent).
        """
        self._knowledge = knowledge
        self._extractor = FactExtractor()
        self._session_start = datetime.now(UTC)

    def observe(self, user_message: str, jarvis_response: str) -> None:
        """
        Observe a single conversation turn and extract/store facts.

        Called after every successful Agent response. Errors are caught
        and logged — never propagated to the conversation pipeline.

        Args:
            user_message:    The user's message.
            jarvis_response: Jarvis's response text.
        """
        try:
            self._process_turn(user_message, jarvis_response)
        except Exception:
            logger.exception(
                "[MEMORY] ConversationObserver: error processing turn — "
                "conversation continues normally."
            )

    def _process_turn(self, user_message: str, jarvis_response: str) -> None:
        """Process a single conversation turn."""
        if not user_message or not user_message.strip():
            return

        # Extract facts from the user's message
        facts = self._extractor.extract(user_message)

        if facts:
            logger.info(
                "[MEMORY] Extracted %d fact(s) from: %r",
                len(facts), user_message[:60]
            )

        for fact in facts:
            self._store_fact(fact)

        # Journal the conversation turn for temporal recall
        self._journal_turn(user_message, jarvis_response)

    def _store_fact(self, fact: ExtractedFact) -> None:
        """Store a single extracted fact via the KnowledgeEngine."""
        category = _FACT_TYPE_TO_CATEGORY.get(fact.fact_type, "general")

        try:
            self._knowledge.store_memory(
                subject=fact.subject,
                category=category,
                attribute=fact.attribute,
                value=fact.value,
                confidence=fact.confidence,
                source=MemorySource.INFERRED,
                # "derived" tag marks observer-inferred records so the
                # recall layer can exclude them from fuzzy fallback
                # searches and prevent zombie matches after a canonical
                # memory is forgotten. Genesis-024 Sprint-001 fix.
                tags=[fact.fact_type.name.lower(), "auto-extracted", "derived"],
            )
            logger.info(
                "[MEMORY] Stored fact: subject=%r attribute=%r value=%r (type=%s)",
                fact.subject, fact.attribute, fact.value, fact.fact_type.name
            )
        except Exception:
            logger.exception(
                "[MEMORY] Failed to store fact: attribute=%r value=%r",
                fact.attribute, fact.value
            )

    def _journal_turn(self, user_message: str, jarvis_response: str) -> None:
        """
        Store a conversation turn summary in the journal.

        Journal entries use subject="jarvis", category="system",
        attribute="conversation_YYYY-MM-DD_HH-MM-SS".

        This allows temporal recall: "what did we do yesterday?" searches
        for journal entries with yesterday's date in the attribute.
        """
        now = datetime.now(UTC)
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        attribute = f"conversation_{timestamp}"

        # Compact summary: first 120 chars of user message
        summary = user_message.strip()
        if len(summary) > 120:
            summary = summary[:117] + "..."

        try:
            self._knowledge.store_memory(
                subject=_JOURNAL_SUBJECT,
                category="system",
                attribute=attribute,
                value=summary,
                confidence=1.0,
                source=MemorySource.SYSTEM,
                tags=["journal", "conversation", now.strftime("%Y-%m-%d")],
                importance=0.3,
            )
        except Exception:
            logger.exception("[MEMORY] Failed to journal conversation turn.")