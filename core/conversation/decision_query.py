"""
Jarvis Decision Query Engine (Genesis-020 Sprint-004)

Answers natural language questions about architectural decisions.

All queries are deterministic — zero AI calls.

Handles:
    "Why did we adopt Event Sourcing?"
    "What architectural decisions have we made?"
    "What did we decide yesterday?"
    "Which decisions are still active?"
    "Which decision replaced the old architecture?"
    "Why did we reject that idea?"
    "What decisions have we superseded?"
    "How many decisions have we made?"
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.conversation.architectural_decision import DecisionStatus

if TYPE_CHECKING:
    from core.conversation.decision_engine import DecisionEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

_WHY_DID_WE       = re.compile(r"\bwhy did we (?:adopt|choose|use|decide|pick|go with|select)\b", re.IGNORECASE)
_WHY_DID_WE_REJECT= re.compile(r"\bwhy did we (?:reject|not use|avoid|drop)\b", re.IGNORECASE)
_WHAT_DECISIONS   = re.compile(r"\bwhat (?:architectural\s+)?decisions (?:have we|did we)\s*(?:make|made|taken|recorded)?\b", re.IGNORECASE)
_WHAT_DECIDED_WHEN= re.compile(r"\bwhat did we decide (?:today|yesterday|recently|last)\b", re.IGNORECASE)
_WHICH_ACTIVE     = re.compile(r"\bwhich decisions? (?:are|is) (?:still\s+)?(?:active|current|in effect)\b", re.IGNORECASE)
_WHICH_SUPERSEDED = re.compile(r"\bwhich decisions? (?:have been|were|are)\s+(?:superseded|replaced|overridden)\b", re.IGNORECASE)
_WHICH_REPLACED   = re.compile(r"\bwhich decision (?:replaced|superseded)\b", re.IGNORECASE)
_WHY_REJECTED     = re.compile(r"\bwhy (?:was|were|did we) (?:that |it |the\s+\w+\s+)?(?:idea|decision|approach|option)?\s*rejected\b", re.IGNORECASE)
_HOW_MANY         = re.compile(r"\bhow many decisions\b", re.IGNORECASE)
_SHOW_DECISIONS   = re.compile(r"\b(?:show|list|display|inspect) decisions?\b|^/decisions$", re.IGNORECASE)
_EXPLAIN_DECISION = re.compile(r"\b(?:explain|tell me about|describe|what is) (?:the\s+)?(.+?) decision\b", re.IGNORECASE)

# Value extraction — what topic is being asked about
_TOPIC_IN_QUERY   = re.compile(r"\b(?:adopt|choose|use|decide|pick|go with|select|reject)\s+(.+?)(?:\?|$|\s+because)", re.IGNORECASE)


@dataclass(frozen=True)
class DecisionQueryResult:
    """Result of a decision query."""
    answered:  bool
    question:  str
    answer:    str             = ""
    decisions: tuple           = field(default_factory=tuple)

    @classmethod
    def miss(cls, question: str) -> "DecisionQueryResult":
        return cls(answered=False, question=question)

    @classmethod
    def empty(cls, question: str, message: str) -> "DecisionQueryResult":
        return cls(answered=True, question=question, answer=message)


class DecisionQueryEngine:
    """
    Answers natural language questions about architectural decisions.

    Wraps a DecisionEngine and translates pattern-matched queries
    into deterministic decision lookups.
    """

    def __init__(self, engine: "DecisionEngine") -> None:
        self._engine = engine

    def can_answer(self, query: str) -> bool:
        """Return True if this engine can attempt to answer the query."""
        return any(p.search(query) for p in [
            _WHY_DID_WE,
            _WHY_DID_WE_REJECT,
            _WHAT_DECISIONS,
            _WHAT_DECIDED_WHEN,
            _WHICH_ACTIVE,
            _WHICH_SUPERSEDED,
            _WHICH_REPLACED,
            _WHY_REJECTED,
            _HOW_MANY,
            _SHOW_DECISIONS,
            _EXPLAIN_DECISION,
        ])

    def answer(self, query: str) -> DecisionQueryResult:
        """Answer a natural language question about decisions."""
        try:
            return self._answer(query)
        except Exception:
            logger.exception("[DECISIONS] Query engine error.")
            return DecisionQueryResult.miss(query)

    def _answer(self, query: str) -> DecisionQueryResult:
        e = self._engine

        # /decisions or "show decisions" — full inspector view
        if _SHOW_DECISIONS.search(query):
            return self._show_all(query)

        # "How many decisions have we made?"
        if _HOW_MANY.search(query):
            total = e.count()
            active = len(e.active())
            return DecisionQueryResult(
                answered=True, question=query,
                answer=(
                    f"We have recorded {total} architectural decision"
                    f"{'s' if total != 1 else ''}, sir. "
                    f"{active} {'are' if active != 1 else 'is'} currently active."
                ),
                decisions=tuple(e.all_decisions()),
            )

        # "What decisions have we made?"
        if _WHAT_DECISIONS.search(query):
            decisions = e.all_decisions()
            if not decisions:
                return DecisionQueryResult.empty(query,
                    "No architectural decisions have been recorded yet, sir.")
            titles = [f"{d.title} [{d.status.label()}]" for d in decisions]
            answer = f"Architectural decisions recorded: {'; '.join(titles)}."
            return DecisionQueryResult(answered=True, question=query,
                answer=answer, decisions=tuple(decisions))

        # "Which decisions are still active?"
        if _WHICH_ACTIVE.search(query):
            decisions = e.active()
            if not decisions:
                return DecisionQueryResult.empty(query,
                    "No active decisions recorded yet, sir.")
            titles = [d.title for d in decisions]
            answer = f"Active decisions: {'; '.join(titles)}."
            return DecisionQueryResult(answered=True, question=query,
                answer=answer, decisions=tuple(decisions))

        # "Which decisions have been superseded?"
        if _WHICH_SUPERSEDED.search(query):
            decisions = e.superseded()
            if not decisions:
                return DecisionQueryResult.empty(query,
                    "No decisions have been superseded yet, sir.")
            titles = [d.title for d in decisions]
            answer = f"Superseded decisions: {'; '.join(titles)}."
            return DecisionQueryResult(answered=True, question=query,
                answer=answer, decisions=tuple(decisions))

        # "What did we decide today/yesterday?"
        if _WHAT_DECIDED_WHEN.search(query):
            return self._answer_temporal(query)

        # "Why did we reject that?"
        if _WHY_REJECTED.search(query) or _WHY_DID_WE_REJECT.search(query):
            decisions = e.rejected()
            if not decisions:
                return DecisionQueryResult.empty(query,
                    "No rejected decisions have been recorded, sir.")
            latest = decisions[-1]
            answer = (
                f"The most recently rejected decision was {latest.title!r}. "
                f"Reason: {latest.reason}"
            )
            return DecisionQueryResult(answered=True, question=query,
                answer=answer, decisions=(latest,))

        # "Explain the X decision" / "Why did we adopt X?"
        if _WHY_DID_WE.search(query) or _EXPLAIN_DECISION.search(query):
            return self._answer_why(query)

        return DecisionQueryResult.miss(query)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _answer_why(self, query: str) -> DecisionQueryResult:
        """Answer 'why did we adopt X?' by searching for matching decisions."""
        # Extract the topic from the query
        topic = self._extract_topic(query)
        if topic:
            results = self._engine.search(topic)
            if results:
                d = results[0]
                return DecisionQueryResult(
                    answered=True, question=query,
                    answer=d.explain(),
                    decisions=(d,),
                )

        # Fall back to most recent active decision
        active = self._engine.active()
        if active:
            d = active[-1]
            return DecisionQueryResult(
                answered=True, question=query,
                answer=d.explain(),
                decisions=(d,),
            )

        return DecisionQueryResult.empty(query,
            "No matching decision found, sir.")

    def _answer_temporal(self, query: str) -> DecisionQueryResult:
        """Answer 'what did we decide today/yesterday?'"""
        from datetime import UTC, datetime, timedelta
        q_lower = query.lower()
        if "yesterday" in q_lower:
            decisions = self._engine.yesterday()
            label = "Yesterday"
        else:
            decisions = self._engine.today()
            label = "Today"

        if not decisions:
            return DecisionQueryResult.empty(query,
                f"{label} no decisions were recorded, sir.")

        titles = [d.title for d in decisions]
        answer = f"{label}'s decisions: {'; '.join(titles)}."
        return DecisionQueryResult(answered=True, question=query,
            answer=answer, decisions=tuple(decisions))

    def _show_all(self, query: str) -> DecisionQueryResult:
        """Full decision list for the inspector."""
        decisions = self._engine.all_decisions()
        if not decisions:
            return DecisionQueryResult.empty(query,
                "No decisions recorded yet, sir.")
        lines = ["Architectural Decisions:"]
        for d in decisions:
            lines.append(f"  [{d.status.label():<12}] {d.title}")
        return DecisionQueryResult(answered=True, question=query,
            answer="\n".join(lines), decisions=tuple(decisions))

    def _extract_topic(self, query: str) -> str:
        """Extract the topic being asked about from a why/explain query."""
        # "Why did we adopt Event Sourcing?" → "Event Sourcing"
        m = re.search(
            r"\b(?:adopt|choose|use|decide|pick|go with|select|"
            r"explain|tell me about|describe)\s+(?:the\s+)?(.+?)(?:\?|$|\s+because|\s+decision)",
            query, re.IGNORECASE
        )
        if m:
            return m.group(1).strip().rstrip("?.,")
        return ""