"""
Jarvis Session Summary Query Engine (Genesis-020 Sprint-006)

Answers natural language questions about the current session.
All queries are deterministic — zero AI calls.

Handles:
    "Summarise this session"
    "What happened today?"
    "Show session summary"
    "How many goals completed?"
    "How many decisions made?"
    "How long was this session?"
    "/summary"
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.session_summary_engine import SessionSummaryEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

_SUMMARISE          = re.compile(r"\b(?:summarise|summarize|summary of|give me a summary)\b", re.IGNORECASE)
_WHAT_HAPPENED      = re.compile(r"\bwhat happened (?:today|this session|in this session|so far)\b", re.IGNORECASE)
_SHOW_SUMMARY       = re.compile(r"\b(?:show|display|print) (?:session\s+)?summary\b|^/summary$", re.IGNORECASE)
_HOW_MANY_GOALS     = re.compile(r"\bhow many goals? (?:were\s+)?(?:completed?|done|finished)\b", re.IGNORECASE)
_HOW_MANY_DECISIONS = re.compile(r"\bhow many decisions? (?:were\s+)?(?:made|recorded|taken)\b", re.IGNORECASE)
_HOW_LONG           = re.compile(r"\bhow long (?:was|is|has been) (?:this\s+)?(?:session|conversation|chat)\b", re.IGNORECASE)
_HOW_MANY_TURNS     = re.compile(r"\bhow many turns?\b", re.IGNORECASE)
_SESSION_STATS      = re.compile(r"\b(?:session\s+)?(?:stats?|statistics|metrics?)\b", re.IGNORECASE)
_WHAT_DID_WE_DO     = re.compile(r"\bwhat did we (?:do|accomplish|achieve|build|create) (?:today|this session|so far)\b", re.IGNORECASE)
_KEY_EVENTS         = re.compile(r"\b(?:key|important|significant) events?\b", re.IGNORECASE)


@dataclass(frozen=True)
class SummaryQueryResult:
    """Result of a session summary query."""
    answered: bool
    question: str
    answer:   str   = ""

    @classmethod
    def miss(cls, question: str) -> "SummaryQueryResult":
        return cls(answered=False, question=question)

    @classmethod
    def empty(cls, question: str, message: str) -> "SummaryQueryResult":
        return cls(answered=True, question=question, answer=message)


class SessionSummaryQueryEngine:
    """
    Answers natural language questions about the current session.
    Wraps a SessionSummaryEngine. Zero AI calls.
    """

    def __init__(self, engine: "SessionSummaryEngine") -> None:
        self._engine = engine

    def can_answer(self, query: str) -> bool:
        """Return True if this engine can attempt to answer the query."""
        return any(p.search(query) for p in [
            _SUMMARISE,
            _WHAT_HAPPENED,
            _SHOW_SUMMARY,
            _HOW_MANY_GOALS,
            _HOW_MANY_DECISIONS,
            _HOW_LONG,
            _HOW_MANY_TURNS,
            _SESSION_STATS,
            _WHAT_DID_WE_DO,
            _KEY_EVENTS,
        ])

    def answer(self, query: str) -> SummaryQueryResult:
        """Answer a natural language question about the session."""
        try:
            return self._answer(query)
        except Exception:
            logger.exception("[SUMMARY] Query engine error.")
            return SummaryQueryResult.miss(query)

    def _answer(self, query: str) -> SummaryQueryResult:
        e = self._engine

        if e.is_empty():
            return SummaryQueryResult.empty(query,
                "The session has just started — nothing to summarise yet, sir.")

        summary = e.current_summary()

        # Full summary
        if (_SUMMARISE.search(query) or _SHOW_SUMMARY.search(query) or
                _WHAT_HAPPENED.search(query) or _WHAT_DID_WE_DO.search(query)):
            return SummaryQueryResult(
                answered=True, question=query,
                answer=summary.format(),
            )

        # "How many goals completed?"
        if _HOW_MANY_GOALS.search(query):
            n = summary.goals_completed
            return SummaryQueryResult(
                answered=True, question=query,
                answer=(
                    f"{n} goal{'s' if n != 1 else ''} "
                    f"{'were' if n != 1 else 'was'} completed this session, sir."
                ),
            )

        # "How many decisions made?"
        if _HOW_MANY_DECISIONS.search(query):
            n = summary.decisions_made
            return SummaryQueryResult(
                answered=True, question=query,
                answer=(
                    f"{n} architectural decision{'s' if n != 1 else ''} "
                    f"{'were' if n != 1 else 'was'} recorded this session, sir."
                ),
            )

        # "How long was this session?"
        if _HOW_LONG.search(query):
            return SummaryQueryResult(
                answered=True, question=query,
                answer=f"This session has been running for {summary.duration_str}, sir.",
            )

        # "How many turns?"
        if _HOW_MANY_TURNS.search(query):
            n = summary.turn_count
            return SummaryQueryResult(
                answered=True, question=query,
                answer=f"We have had {n} conversation turn{'s' if n != 1 else ''} so far, sir.",
            )

        # "Session stats"
        if _SESSION_STATS.search(query):
            stats = e.session_statistics()
            lines = [
                f"Session Statistics:",
                f"  Turns:      {stats['turn_count']}",
                f"  Goals:      {stats['goals_created']} created, {stats['goals_completed']} completed",
                f"  Decisions:  {stats['decisions_made']} made",
                f"  Memories:   {stats['memories_created']} added",
            ]
            return SummaryQueryResult(
                answered=True, question=query,
                answer="\n".join(lines),
            )

        # "Key events"
        if _KEY_EVENTS.search(query):
            events = e.important_events()
            if not events:
                return SummaryQueryResult.empty(query,
                    "No key events recorded yet, sir.")
            lines = ["Key Events:"] + [f"  • {ev}" for ev in events]
            return SummaryQueryResult(
                answered=True, question=query,
                answer="\n".join(lines),
            )

        return SummaryQueryResult.miss(query)