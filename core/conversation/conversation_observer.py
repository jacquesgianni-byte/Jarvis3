"""
Jarvis Conversation Observer (Genesis-020 Sprint-001)

Observes each conversation turn and extracts structured facts into
the KnowledgeEngine.

Responsibilities:
    - Run FactExtractor on every user message
    - Store extracted facts via KnowledgeEngine
    - Store conversation journal entries

Design constraints:
    - No AI calls
    - No external services
    - Write-only to KnowledgeEngine (never reads for routing)
    - Deterministic — same input → same facts stored
    - Purely observational — does not infer conversational meaning

Architecture position:
    Agent._post_turn()
        └── ConversationObserver.observe()   ← this module
                └── FactExtractor            (reads user message)
                └── KnowledgeEngine          (writes facts)

Genesis-025 Sprint-003:
    _infer_pet_name_continuation() removed. Bare name list inference
    is now handled by SlotCompletionEngine at Step 4 (before AI),
    which is earlier and produces a proper acknowledgement response.
    ConversationObserver returns to being purely observational.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.conversation.fact_extractor import ExtractedFact, FactExtractor, FactType

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)

# Category for all facts stored via this observer
_CATEGORY = "general"


class ConversationObserver:
    """
    Observes each conversation turn and extracts structured facts.

    Called by Agent._post_turn() after every user message. Extracts
    facts via FactExtractor and stores them in the KnowledgeEngine.
    Also stores a journal entry for each turn.

    Purely observational — does not infer conversational meaning or
    perform context-aware completion. That responsibility belongs to
    SlotCompletionEngine (Genesis-025).
    """

    def __init__(self, knowledge: "KnowledgeEngine") -> None:
        self._knowledge = knowledge
        self._extractor = FactExtractor()

    def observe(self, user_message: str, jarvis_response: str) -> None:
        """
        Process one conversation turn.

        Args:
            user_message:    The user's raw message.
            jarvis_response: Jarvis's response (stored in journal).
        """
        if not user_message or not user_message.strip():
            return

        # Extract facts from the user message
        facts = self._extractor.extract(user_message)

        # Store extracted facts
        if facts:
            self._store_facts(facts, user_message)

        # Store journal entry
        self._store_journal(user_message, jarvis_response)

    def _store_facts(self, facts: list[ExtractedFact], raw: str) -> None:
        """Store a list of extracted facts in the KnowledgeEngine."""
        for fact in facts:
            try:
                self._knowledge.store_memory(
                    subject=fact.subject,
                    category=_CATEGORY,
                    attribute=fact.attribute,
                    value=fact.value,
                    tags=self._tags_for(fact),
                )
                logger.info(
                    "[OBSERVER] Stored fact: subject=%r attribute=%r value=%r",
                    fact.subject, fact.attribute, fact.value,
                )
            except Exception:
                logger.exception(
                    "[OBSERVER] Failed to store fact: %r", fact
                )

    def _tags_for(self, fact: ExtractedFact) -> list[str]:
        """Return appropriate tags for a fact based on its type."""
        base = ["auto-extracted", "derived"]
        if fact.fact_type == FactType.PET:
            base.append("pet")
        return base

    def _store_journal(self, user_message: str, jarvis_response: str) -> None:
        """Store a journal entry for this conversation turn."""
        from datetime import UTC, datetime
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        try:
            self._knowledge.store_memory(
                subject="jarvis",
                category="system",
                attribute=f"conversation_{timestamp}",
                value=user_message.strip(),
                tags=["journal", "conversation"],
            )
        except Exception:
            logger.exception("[OBSERVER] Failed to store journal entry.")