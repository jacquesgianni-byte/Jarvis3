"""
Temporal Recall Engine (Genesis-031 Sprint-002)

Answers temporal queries ("When did I start my job?") by looking up
temporal metadata stored in KnowledgeEngine memory records.

Responsibilities:
    - Detect "when did I X?" query patterns
    - Search KnowledgeEngine for matching memories
    - Extract resolved_date from record metadata
    - Return a natural language answer

Design constraints:
    - No AI calls
    - No new storage -- reads from KnowledgeEngine only
    - KnowledgeEngine remains single source of truth
    - TemporalParser never called here -- metadata was set at store time

Architecture position:
    Agent._route()
        -> TemporalRecallEngine.detect_query(text)
        -> TemporalRecallEngine.answer(query, knowledge)
        -> KnowledgeEngine.search_memory()
        -> Response

Genesis-031 Sprint-002.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

_WHEN_PATTERNS: list[re.Pattern] = [
    # "When did I move?" / "When did I start?" -- single verb
    re.compile(r"\bwhen\s+did\s+i\s+\w+\??$", re.IGNORECASE),
    # "When did I start my job?" / "When did I buy my car?"
    re.compile(r"\bwhen\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "When was I ..."
    re.compile(r"\bwhen\s+was\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "What day did I ..."
    re.compile(r"\bwhat\s+day\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "What date did I ..."
    re.compile(r"\bwhat\s+date\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
]

# Keywords to extract from the query for memory search
_KEYWORD_STRIP = re.compile(
    r"\b(?:when|did|i|my|a|an|the|was|what|day|date)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TemporalQuery:
    """A detected temporal query."""
    raw_text:    str
    search_hint: str   # Keywords to search memory for


@dataclass(frozen=True)
class TemporalAnswer:
    """Result of answering a temporal query."""
    found:       bool
    answer:      str
    memory_value: Optional[str] = None
    resolved_date: Optional[str] = None


class TemporalRecallEngine:
    """
    Answers when-did-I queries from temporal metadata in KnowledgeEngine.

    Stateless. KnowledgeEngine injected at call time.

    Public API:
        detect_query(text) -> Optional[TemporalQuery]
        answer(query, knowledge) -> TemporalAnswer
    """

    def detect_query(self, text: str) -> Optional[TemporalQuery]:
        """
        Detect a temporal query in the user's message.

        Args:
            text: The user's raw message.

        Returns:
            TemporalQuery if a when-query is detected, else None.
        """
        if not text or not text.strip():
            return None

        for pattern in _WHEN_PATTERNS:
            if pattern.search(text):
                hint = self._extract_search_hint(text)
                if hint:
                    logger.debug("[TEMPORAL_RECALL] Query detected: %r hint=%r", text[:40], hint)
                    return TemporalQuery(raw_text=text, search_hint=hint)

        return None

    def answer(
        self,
        query: TemporalQuery,
        knowledge: "KnowledgeEngine",
    ) -> TemporalAnswer:
        """
        Answer a temporal query from KnowledgeEngine records.

        Searches for memories matching the query hint, then looks for
        temporal metadata (resolved_date) in the record's metadata field.

        Args:
            query:     A TemporalQuery from detect_query().
            knowledge: The KnowledgeEngine instance to search.

        Returns:
            TemporalAnswer with a natural language response.
        """
        # Search for matching memories
        results = knowledge.search_memory(
            query=query.search_hint,
            subject="user",
            limit=10,
        )

        # Also try broader search if narrow search yields nothing
        if not results:
            results = knowledge.search_memory(
                query=query.search_hint,
                limit=10,
            )

        # Find records with temporal information in tags
        for record in results:
            # Check metadata first (future-proof)
            metadata = getattr(record, "metadata", None) or {}
            resolved_date = metadata.get("resolved_date")
            temporal_expr = metadata.get("temporal_expression")

            # Fall back to tags encoding: "resolved:2026-07-27", "expr:last monday"
            if not resolved_date:
                for tag in getattr(record, "tags", []):
                    if tag.startswith("resolved:"):
                        resolved_date = tag[len("resolved:"):]
                    elif tag.startswith("expr:"):
                        temporal_expr = tag[len("expr:"):]

            if resolved_date:
                answer_text = self._format_answer(
                    record.value, resolved_date, temporal_expr
                )
                logger.info(
                    "[TEMPORAL_RECALL] Found: value=%r date=%r",
                    record.value, resolved_date,
                )
                return TemporalAnswer(
                    found=True,
                    answer=answer_text,
                    memory_value=record.value,
                    resolved_date=resolved_date,
                )

        return TemporalAnswer(
            found=False,
            answer="I don't have a specific date recorded for that.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_search_hint(self, text: str) -> str:
        """
        Extract meaningful keywords from a temporal query for memory search.

        "When did I start my new job?" -> "start new job"
        "When did I buy my car?" -> "buy car"
        "When did I move?" -> "move"
        """
        stripped = _KEYWORD_STRIP.sub(" ", text)
        stripped = re.sub(r"[?!.,]", " ", stripped)
        words = [w for w in stripped.split() if len(w) >= 2]
        return " ".join(words[:5])

    def _format_answer(
        self,
        memory_value: str,
        resolved_date: str,
        original_expression: Optional[str],
    ) -> str:
        """
        Format a natural language answer from a memory record.

        Args:
            memory_value:       The stored fact ("started new job")
            resolved_date:      ISO date string ("2026-07-27")
            original_expression: The original temporal phrase ("last Monday")

        Returns:
            A natural language answer string.
        """
        try:
            d = date.fromisoformat(resolved_date)
            date_str = d.strftime("%A, %d %B %Y")  # e.g. "Monday, 27 July 2026"
        except (ValueError, TypeError):
            date_str = resolved_date

        if original_expression:
            return f"That was on {date_str} ({original_expression})."
        return f"That was on {date_str}."
