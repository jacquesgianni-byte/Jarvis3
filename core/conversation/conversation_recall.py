"""
Jarvis Conversation Memory — Conversation Recall (Genesis-020 Sprint-001)

Handles temporal and contextual recall queries.

Answers questions like:
    "What project am I working on?"
    "What did we finish yesterday?"
    "Who is Claude?"
    "What milestone did we complete?"
    "What is Genesis-020?"
    "Who are Rex and Tom?"

All recall is deterministic — no LLM required.
Searches the KnowledgeEngine using structured queries.

Constitutional constraints:
    - No LLM calls.
    - No external services.
    - Local-first, deterministic, fast.
    - Uses only the existing KnowledgeEngine API.
"""

from __future__ import annotations

import re
import logging
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Recall query patterns
# ---------------------------------------------------------------------------

_PROJECT_QUERIES = re.compile(
    r"\b(?:what|which)\s+project\s+(?:am i|are we)\s+(?:working on|building|doing)?",
    re.IGNORECASE,
)
_MILESTONE_QUERIES = re.compile(
    r"\b(?:what|which)\s+(?:milestone|genesis|sprint|release)\s+"
    r"(?:did (?:we|i)|have (?:we|i))?\s*(?:finish|complete|ship|freeze|done)?",
    re.IGNORECASE,
)
_TEMPORAL_YESTERDAY = re.compile(
    r"\byesterday\b", re.IGNORECASE
)
_TEMPORAL_TODAY = re.compile(
    r"\btoday\b", re.IGNORECASE
)
_TEMPORAL_LAST_SESSION = re.compile(
    r"\blast\s+(?:session|time|chat|conversation)\b", re.IGNORECASE
)
# Fixed: matches both "who is X" and "who are X and Y"
_PERSON_QUERY = re.compile(
    r"\bwho\s+(?:is|are)\s+([A-Za-z][A-Za-z\s,]+?)(?:\?|$)", re.IGNORECASE
)
_TASK_QUERY = re.compile(
    r"\bwhat\s+(?:are\s+we|am\s+i)\s+(?:doing|working on|starting|building)(?:\s+now|\s+next)?\b",
    re.IGNORECASE,
)
_ACHIEVEMENT_QUERY = re.compile(
    r"\bwhat\s+(?:did\s+(?:we|i)|have\s+(?:we|i))\s+(?:finish|complete|build|ship|achieve|done)\b",
    re.IGNORECASE,
)
_GENESIS_QUERY = re.compile(
    r"\bwhat\s+is\s+(genesis[- ]?[\d\.]+)\b",
    re.IGNORECASE,
)
_WHICH_GENESIS = re.compile(
    r"\bwhich\s+genesis\s+(?:are\s+we\s+on|are\s+we\s+doing|is\s+(?:next|current))\b",
    re.IGNORECASE,
)


@dataclass
class RecallResult:
    """Result of a recall query."""
    found: bool
    answer: str
    attribute: str = ""
    value: str = ""


class ConversationRecall:
    """
    Answers contextual and temporal memory questions.

    Sits above the KnowledgeEngine and translates natural language
    recall queries into structured knowledge lookups.

    Returns RecallResult — callers decide how to phrase the response.
    """

    def __init__(self, knowledge: "KnowledgeEngine"):
        self._knowledge = knowledge

    def can_answer(self, query: str) -> bool:
        """
        Return True if this class can handle the query.

        Used by the MemorySkill to decide whether to route a question
        to ConversationRecall before standard knowledge lookup.
        """
        return any([
            _PROJECT_QUERIES.search(query),
            _MILESTONE_QUERIES.search(query),
            _TEMPORAL_YESTERDAY.search(query),
            _TEMPORAL_TODAY.search(query),
            _TEMPORAL_LAST_SESSION.search(query),
            _PERSON_QUERY.search(query),
            _TASK_QUERY.search(query),
            _ACHIEVEMENT_QUERY.search(query),
            _GENESIS_QUERY.search(query),
            _WHICH_GENESIS.search(query),
        ])

    def answer(self, query: str) -> RecallResult:
        """
        Answer a contextual/temporal memory query.

        Args:
            query: The user's natural language question.

        Returns:
            RecallResult with found=True if an answer was found.
        """
        # Person query: "Who is Claude?" / "Who are Rex and Tom?"
        m = _PERSON_QUERY.search(query)
        if m:
            return self._recall_person(m.group(1).strip())

        # Genesis query: "What is Genesis-020?"
        m = _GENESIS_QUERY.search(query)
        if m:
            return self._recall_genesis(m.group(1).strip())

        # Which Genesis are we on?
        if _WHICH_GENESIS.search(query):
            return self._recall_current_task()

        # Project query
        if _PROJECT_QUERIES.search(query):
            return self._recall_attribute("user", "current project")

        # Current task
        if _TASK_QUERY.search(query):
            return self._recall_attribute("user", "current task")

        # Milestone
        if _MILESTONE_QUERIES.search(query) or _ACHIEVEMENT_QUERY.search(query):
            return self._recall_attribute("user", "last milestone")

        # Temporal: yesterday
        if _TEMPORAL_YESTERDAY.search(query):
            return self._recall_journal(days_ago=1)

        # Temporal: today
        if _TEMPORAL_TODAY.search(query):
            return self._recall_journal(days_ago=0)

        # Temporal: last session
        if _TEMPORAL_LAST_SESSION.search(query):
            return self._recall_journal(days_ago=1)

        return RecallResult(found=False, answer="")

    # ------------------------------------------------------------------
    # Recall helpers
    # ------------------------------------------------------------------

    def _recall_attribute(self, subject: str, attribute: str) -> RecallResult:
        """Recall a specific subject+attribute from the KnowledgeEngine."""
        record = self._knowledge.recall_memory(subject, attribute)
        if record:
            return RecallResult(
                found=True,
                answer=record.value,
                attribute=attribute,
                value=record.value,
            )
        return RecallResult(found=False, answer="")

    def _recall_person(self, name: str) -> RecallResult:
        """Recall what we know about a named person or pet."""
        name_lower = name.lower().strip()
        record = self._knowledge.recall_memory(name_lower, "role")
        if record:
            return RecallResult(
                found=True,
                answer=record.value,
                attribute="role",
                value=record.value,
            )
        # Search all records for the name.
        results = self._knowledge.search_memory(name_lower, subject=None)
        if results:
            r = results[0]
            # If the record is tagged as a pet and the attribute ends with
            # "names", compose a meaningful answer rather than returning the
            # bare stored value. Uses tags so future memory types (children's
            # names, colleagues' names) can follow the same pattern with their
            # own tags without adding more attribute hardcoding here.
            # TODO: generalise to a tag-driven answer template registry.
            if "pet" in (r.tags or []) and r.attribute.endswith("names"):
                pet_type = self._knowledge.recall_memory("user", "pets")
                animal = pet_type.value if pet_type else "pets"
                answer = f"{r.value} are your {animal}."
                logger.info("[RECALL] pet answer=%r", answer)
                return RecallResult(
                    found=True,
                    answer=answer,
                    attribute=r.attribute,
                    value=r.value,
                )
            return RecallResult(
                found=True,
                answer=r.value,
                attribute=r.attribute,
                value=r.value,
            )
        return RecallResult(found=False, answer="")

    def _recall_genesis(self, name: str) -> RecallResult:
        """Recall what we know about a specific Genesis milestone."""
        results = self._knowledge.search_memory(name.lower())
        if results:
            r = results[0]
            return RecallResult(
                found=True,
                answer=r.value,
                attribute=r.attribute,
                value=r.value,
            )
        return RecallResult(found=False, answer="")

    def _recall_current_task(self) -> RecallResult:
        """Recall the current task or project."""
        for attribute in ("current task", "current project", "last milestone"):
            result = self._recall_attribute("user", attribute)
            if result.found:
                return result
        return RecallResult(found=False, answer="")

    def _recall_journal(self, days_ago: int = 0) -> RecallResult:
        """
        Recall journal entries from a specific day.

        Searches for system journal records tagged with the target date.
        """
        target_date = (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

        results = self._knowledge.search_memory(
            query=target_date,
            subject="jarvis",
            category="system",
        )

        journal_entries = [
            r for r in results
            if target_date in r.tags or target_date in r.attribute
        ]

        if not journal_entries:
            return RecallResult(found=False, answer="")

        journal_entries.sort(key=lambda r: r.updated_at, reverse=True)
        summaries = [r.value for r in journal_entries[:5]]
        combined = "; ".join(summaries)

        return RecallResult(
            found=True,
            answer=combined,
            attribute=f"journal_{target_date}",
            value=combined,
        )