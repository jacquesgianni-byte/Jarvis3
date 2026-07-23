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
    "Who is Sarah?" (manager)
    "Where do I work?"

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
_TEMPORAL_YESTERDAY = re.compile(r"\byesterday\b", re.IGNORECASE)
_TEMPORAL_TODAY     = re.compile(r"\btoday\b",     re.IGNORECASE)
_TEMPORAL_LAST_SESSION = re.compile(
    r"\blast\s+(?:session|time|chat|conversation)\b", re.IGNORECASE
)
# Matches both "who is X" and "who are X and Y"
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
    r"\bwhat\s+is\s+(genesis[- ]?[\d\.]+)\b", re.IGNORECASE,
)
_WHICH_GENESIS = re.compile(
    r"\bwhich\s+genesis\s+(?:are\s+we\s+on|are\s+we\s+doing|is\s+(?:next|current))\b",
    re.IGNORECASE,
)
_WORKPLACE_QUERY = re.compile(
    r"\b(?:where\s+do\s+i\s+work|where\s+am\s+i\s+(?:employed|working)|"
    r"what\s+(?:company|organisation|organization|workplace|place)\s+do\s+i\s+work\s+(?:at|for))\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Relationship answer templates
# ---------------------------------------------------------------------------
_ROLE_ANSWER_TEMPLATES: dict[str, str] = {
    "manager":   "{value} is your manager.",
    "son":       "{value} is your son.",
    "daughter":  "{value} is your daughter.",
    "wife":      "{value} is your wife.",
    "husband":   "{value} is your husband.",
    "partner":   "{value} is your partner.",
    "friend":    "{value} is your friend.",
    "colleague": "{value} is your colleague.",
    "boss":      "{value} is your boss.",
    "assistant": "{value} is your assistant.",
}
_ROLE_FALLBACK_TEMPLATE = "Your {relationship} is {value}."

_ATTRIBUTE_ANSWER_TEMPLATES: dict[str, str] = {
    "workplace": "You work at {value}.",
}


@dataclass
class RecallResult:
    """Result of a recall query."""
    found:     bool
    answer:    str
    attribute: str = ""
    value:     str = ""


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
        """Return True if this class can handle the query."""
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
            _WORKPLACE_QUERY.search(query),
        ])

    def answer(self, query: str, resolved_entity: str = "") -> RecallResult:
        """
        Answer a contextual/temporal memory query.

        Args:
            query:           The user's natural language question.
            resolved_entity: Optional pre-resolved entity name from
                             ContextResolver (GC-009). When provided,
                             person lookup uses this value directly
                             instead of extracting from the query text.
                             Allows "Who are they?" to resolve via
                             "Rex and Tom" rather than the literal "they".
        """
        # GC-009: if a resolved entity is provided, try person lookup first.
        if resolved_entity:
            result = self._recall_person(resolved_entity)
            if result.found:
                return result

        # Workplace query: "Where do I work?"
        if _WORKPLACE_QUERY.search(query):
            return self._recall_attribute("user", "workplace")

        # Person query: "Who is Claude?" / "Who are Rex and Tom?"
        m = _PERSON_QUERY.search(query)
        if m:
            return self._recall_person(m.group(1).strip())

        # Genesis query: "What is Genesis-020?"
        m = _GENESIS_QUERY.search(query)
        if m:
            return self._recall_genesis(m.group(1).strip())

        if _WHICH_GENESIS.search(query):
            return self._recall_current_task()

        if _PROJECT_QUERIES.search(query):
            return self._recall_attribute("user", "current project")

        if _TASK_QUERY.search(query):
            return self._recall_attribute("user", "current task")

        if _MILESTONE_QUERIES.search(query) or _ACHIEVEMENT_QUERY.search(query):
            return self._recall_attribute("user", "last milestone")

        if _TEMPORAL_YESTERDAY.search(query):
            return self._recall_journal(days_ago=1)

        if _TEMPORAL_TODAY.search(query):
            return self._recall_journal(days_ago=0)

        if _TEMPORAL_LAST_SESSION.search(query):
            return self._recall_journal(days_ago=1)

        return RecallResult(found=False, answer="")

    # ------------------------------------------------------------------
    # Recall helpers
    # ------------------------------------------------------------------

    def _recall_attribute(self, subject: str, attribute: str) -> RecallResult:
        """
        Recall a specific subject+attribute from the KnowledgeEngine.

        If an answer template exists for the attribute, wraps the value
        in a natural sentence. Otherwise returns the bare stored value.
        """
        record = self._knowledge.recall_memory(subject, attribute)
        if not record:
            return RecallResult(found=False, answer="")

        template = _ATTRIBUTE_ANSWER_TEMPLATES.get(attribute)
        answer = template.format(value=record.value) if template else record.value

        return RecallResult(
            found=True,
            answer=answer,
            attribute=attribute,
            value=record.value,
        )

    def _recall_person(self, name: str) -> RecallResult:
        """
        Recall what we know about a named person, pet, or relationship.

        Resolution ladder:
            1. Direct role lookup by name
            2. search_memory for the name across all records
               (excluding journal/conversation records — GC-010)
               a. Pet records → "X are your N dogs."
               b. subject != "user" and attribute == "role" →
                  use subject as relationship
               c. "{relationship} role" attribute → compose via templates
               d. Anything else → return bare value
            3. Miss → not found.
        """
        name_lower = name.lower().strip()

        # 1. Direct role lookup by name
        record = self._knowledge.recall_memory(name_lower, "role")
        if record:
            return RecallResult(
                found=True,
                answer=record.value,
                attribute="role",
                value=record.value,
            )

        # 2. Search all records for the name.
        # GC-010: exclude journal/conversation records — they survive forget
        # and would return stale answers after a memory has been deleted.
        results = self._knowledge.search_memory(name_lower, subject=None)
        results = [r for r in results if not r.attribute.startswith("conversation_")]

        if not results:
            # Authoritative miss — ConversationRecall owns this query and
            # has determined nothing is stored. Return found=True with a
            # "not stored" message so the agent never falls through to AI
            # for questions recall explicitly owns. GC-010.
            return RecallResult(
                found=True,
                answer=f"I don't have any information about {name} stored, sir.",
                attribute="",
                value="",
            )

        r = results[0]

        # 2a. Pet records — tagged "pet", attribute ends with "names"
        if "pet" in (r.tags or []) and r.attribute.endswith("names"):
            pet_type = self._knowledge.recall_memory("user", "pets")
            animal = pet_type.value if pet_type else "pets"
            answer = f"{r.value} are your {animal}."
            return RecallResult(
                found=True,
                answer=answer,
                attribute=r.attribute,
                value=r.value,
            )

        # 2b. subject != "user" and attribute == "role"
        # e.g. subject="son", attribute="role", value="Alex"
        if r.attribute == "role" and r.subject not in ("user", "jarvis", ""):
            relationship = r.subject.strip()
            template = _ROLE_ANSWER_TEMPLATES.get(relationship)
            if template:
                answer = template.format(value=r.value, relationship=relationship)
            else:
                answer = _ROLE_FALLBACK_TEMPLATE.format(
                    value=r.value, relationship=relationship
                )
            return RecallResult(
                found=True,
                answer=answer,
                attribute=r.attribute,
                value=r.value,
            )

        # 2c. "{relationship} role" attribute — e.g. "manager role"
        if r.attribute.endswith(" role"):
            relationship = r.attribute[: -len(" role")].strip()
            template = _ROLE_ANSWER_TEMPLATES.get(relationship)
            if template:
                answer = template.format(value=r.value, relationship=relationship)
            else:
                answer = _ROLE_FALLBACK_TEMPLATE.format(
                    value=r.value, relationship=relationship
                )
            return RecallResult(
                found=True,
                answer=answer,
                attribute=r.attribute,
                value=r.value,
            )

        # 2d. Anything else — return the bare value
        return RecallResult(
            found=True,
            answer=r.value,
            attribute=r.attribute,
            value=r.value,
        )

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
        """Recall journal entries from a specific day."""
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