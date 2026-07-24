"""
Jarvis Conversation Observer (Genesis-020 Sprint-001)

Observes each conversation turn and extracts structured facts into
the KnowledgeEngine.

Responsibilities:
    - Run FactExtractor on every user message
    - Store extracted facts via KnowledgeEngine
    - Store conversation journal entries
    - GC-012: infer pet names from bare continuation sentences

Design constraints:
    - No AI calls
    - No external services
    - Write-only to KnowledgeEngine (never reads for routing)
    - Deterministic — same input → same facts stored

Architecture position:
    Agent._post_turn()
        └── ConversationObserver.observe()   ← this module
                └── FactExtractor            (reads user message)
                └── KnowledgeEngine          (writes facts)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from core.conversation.fact_extractor import ExtractedFact, FactExtractor, FactType

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GC-012: Continuation inference patterns
# ---------------------------------------------------------------------------

# Matches a pet quantity stored in knowledge ("3 cats", "2 dogs", "a cat")
_PET_TOPIC_RE = re.compile(
    r"^(\d+|a|an|one|two|three|four|five|some)\s+"
    r"(?:dogs?|cats?|pets?|birds?|fish|rabbits?|hamsters?)$",
    re.IGNORECASE,
)

# Matches a bare name or comma-separated name list ("Tom, Tim and Tam")
_NAME_LIST_RE = re.compile(
    r"^[A-Z][a-z]+(?:(?:[,\s]+(?:and\s+)?)[A-Z][a-z]+)*\.?$"
)

# Category for all facts stored via this observer
_CATEGORY = "general"


class ConversationObserver:
    """
    Observes each conversation turn and extracts structured facts.

    Called by Agent._post_turn() after every user message. Extracts
    facts via FactExtractor and stores them in the KnowledgeEngine.
    Also stores a journal entry for each turn.

    GC-012: When FactExtractor finds no facts, attempts context-aware
    inference for bare name continuations after pet statements.
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
        else:
            # GC-012: no facts extracted — try context-aware inference
            inferred_name = self._infer_pet_name_continuation(user_message)
            if inferred_name:
                self._knowledge.store_memory(
                    subject="user",
                    category=_CATEGORY,
                    attribute="pet names",
                    value=inferred_name,
                    tags=["pet", "auto-extracted", "inferred"],
                )
                logger.info(
                    "[OBSERVER] Inferred pet names from continuation: %r",
                    inferred_name,
                )

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

    def _infer_pet_name_continuation(self, text: str) -> str:
        """
        GC-012: Infer pet names from a bare name list when pets are stored.

        When the user says "I have 3 cats." and then "Tom, Tim and Tam.",
        the second message has no explicit signal. This method checks:
          1. The message looks like a name or comma-separated name list.
          2. The knowledge store already contains a pet quantity for the user.

        If both are true, the message is inferred as pet names.

        Returns the inferred name string, or empty string if no inference.
        """
        stripped = text.strip().rstrip(".")

        # Must look like a name or comma-separated name list
        if not _NAME_LIST_RE.match(stripped):
            return ""

        # Must have a pet quantity already stored
        pet_record = self._knowledge.recall_memory("user", "pets")
        if not pet_record:
            return ""

        # Pet record value must look like a quantity + animal
        pet_value = getattr(pet_record, 'value', None)
        if not isinstance(pet_value, str):
            return ""
        if not _PET_TOPIC_RE.match(pet_value.strip()):
            return ""

        logger.debug(
            "[OBSERVER] Inferred %r as pet names (context: %r)",
            stripped, pet_record.value,
        )
        return stripped