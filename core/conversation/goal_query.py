"""
Jarvis Goal Query Engine (Genesis-020 Sprint-005)

Answers natural language questions about goals.
All queries are deterministic — zero AI calls.

Handles:
    "What are we working on?"
    "What is our current goal?"
    "What should we do next?"
    "Which goals are completed?"
    "Which goals are blocked?"
    "Show goals" / "/goals"
    "Why is this goal important?"
    "What goals do we have?"
    "How many goals are active?"
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.conversation.goal import GoalStatus, GoalPriority

if TYPE_CHECKING:
    from core.conversation.goal_engine import GoalEngine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

_WHAT_ARE_WE_WORKING   = re.compile(r"\bwhat are we (?:working on|doing|building|focusing on)\b", re.IGNORECASE)
_CURRENT_GOAL          = re.compile(r"\bwhat(?:'s| is) (?:our|the) (?:current|main|primary) goal\b", re.IGNORECASE)
_WHAT_NEXT             = re.compile(r"\bwhat (?:should we|do we) (?:do|work on|tackle|start) next\b", re.IGNORECASE)
_WHICH_COMPLETED       = re.compile(r"\bwhich goals? (?:are|have been|were) (?:completed?|done|finished|achieved)\b", re.IGNORECASE)
_WHICH_BLOCKED         = re.compile(r"\bwhich goals? (?:are|have been) (?:blocked?|stuck|stalled)\b", re.IGNORECASE)
_WHAT_GOALS            = re.compile(r"\bwhat goals? (?:do we have|are there|exist|have we)\b", re.IGNORECASE)
_SHOW_GOALS            = re.compile(r"\b(?:show|list|display|inspect) goals?\b|^/goals$", re.IGNORECASE)
_HOW_MANY_GOALS        = re.compile(r"\bhow many goals?\b", re.IGNORECASE)
_WHY_GOAL              = re.compile(r"\bwhy (?:is|are|do we have|did we add) (?:this|that|the) goal\b", re.IGNORECASE)
_ACTIVE_GOALS          = re.compile(r"\b(?:active|current|open|in.?progress) goals?\b", re.IGNORECASE)
_PLANNED_GOALS         = re.compile(r"\b(?:planned?|upcoming|future) goals?\b", re.IGNORECASE)
_EXPLAIN_GOAL          = re.compile(r"\b(?:explain|describe|tell me about) (?:the\s+)?(.+?) goal\b", re.IGNORECASE)


@dataclass(frozen=True)
class GoalQueryResult:
    """Result of a goal query."""
    answered: bool
    question: str
    answer:   str        = ""
    goals:    tuple      = field(default_factory=tuple)

    @classmethod
    def miss(cls, question: str) -> "GoalQueryResult":
        return cls(answered=False, question=question)

    @classmethod
    def empty(cls, question: str, message: str) -> "GoalQueryResult":
        return cls(answered=True, question=question, answer=message)


class GoalQueryEngine:
    """
    Answers natural language questions about goals.

    Wraps a GoalEngine and translates pattern-matched queries
    into deterministic goal lookups. Zero AI calls.
    """

    def __init__(self, engine: "GoalEngine") -> None:
        self._engine = engine

    def can_answer(self, query: str) -> bool:
        """Return True if this engine can attempt to answer the query."""
        return any(p.search(query) for p in [
            _WHAT_ARE_WE_WORKING,
            _CURRENT_GOAL,
            _WHAT_NEXT,
            _WHICH_COMPLETED,
            _WHICH_BLOCKED,
            _WHAT_GOALS,
            _SHOW_GOALS,
            _HOW_MANY_GOALS,
            _WHY_GOAL,
            _ACTIVE_GOALS,
            _PLANNED_GOALS,
            _EXPLAIN_GOAL,
        ])

    def answer(self, query: str) -> GoalQueryResult:
        """Answer a natural language question about goals."""
        try:
            return self._answer(query)
        except Exception:
            logger.exception("[GOALS] Query engine error.")
            return GoalQueryResult.miss(query)

    def _answer(self, query: str) -> GoalQueryResult:
        e = self._engine

        # /goals or "show goals"
        if _SHOW_GOALS.search(query):
            return self._show_all(query)

        # "How many goals?"
        if _HOW_MANY_GOALS.search(query):
            total = e.count()
            active = len(e.active())
            return GoalQueryResult(
                answered=True, question=query,
                answer=(
                    f"We have {total} goal{'s' if total != 1 else ''} recorded, sir. "
                    f"{active} {'are' if active != 1 else 'is'} currently active."
                ),
                goals=tuple(e.all_goals()),
            )

        # "What are we working on?" / "What is our current goal?"
        if _WHAT_ARE_WE_WORKING.search(query) or _CURRENT_GOAL.search(query):
            goal = e.current_goal()
            if not goal:
                # Fall back to planned
                goal = e.next_goal()
                if not goal:
                    return GoalQueryResult.empty(query,
                        "No active goals recorded yet, sir.")
                return GoalQueryResult(
                    answered=True, question=query,
                    answer=f"No active goals, but the next planned goal is: {goal.title}.",
                    goals=(goal,),
                )
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Current goal: {goal.title}. {goal.description}".strip(),
                goals=(goal,),
            )

        # "What should we do next?"
        if _WHAT_NEXT.search(query):
            goal = e.next_goal() or e.current_goal()
            if not goal:
                return GoalQueryResult.empty(query,
                    "No planned or active goals to suggest, sir.")
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Next up: {goal.title} [{goal.priority.label()} priority]. {goal.description}".strip(),
                goals=(goal,),
            )

        # "Which goals are completed?"
        if _WHICH_COMPLETED.search(query):
            goals = e.completed()
            if not goals:
                return GoalQueryResult.empty(query, "No completed goals yet, sir.")
            titles = [g.title for g in goals]
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Completed goals: {'; '.join(titles)}.",
                goals=tuple(goals),
            )

        # "Which goals are blocked?"
        if _WHICH_BLOCKED.search(query):
            goals = e.blocked()
            if not goals:
                return GoalQueryResult.empty(query, "No blocked goals, sir.")
            parts = [f"{g.title} (blocked by: {g.blocked_by or 'unknown'})" for g in goals]
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Blocked goals: {'; '.join(parts)}.",
                goals=tuple(goals),
            )

        # "What goals do we have?" / "Active goals" / "Planned goals"
        if _WHAT_GOALS.search(query) or _ACTIVE_GOALS.search(query):
            goals = e.open_goals()
            if not goals:
                return GoalQueryResult.empty(query, "No open goals recorded, sir.")
            titles = [f"{g.title} [{g.status.label()}]" for g in goals]
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Open goals: {'; '.join(titles)}.",
                goals=tuple(goals),
            )

        if _PLANNED_GOALS.search(query):
            goals = e.planned()
            if not goals:
                return GoalQueryResult.empty(query, "No planned goals, sir.")
            titles = [g.title for g in goals]
            return GoalQueryResult(
                answered=True, question=query,
                answer=f"Planned goals: {'; '.join(titles)}.",
                goals=tuple(goals),
            )

        # "Why is this goal important?" / "Explain the X goal"
        if _WHY_GOAL.search(query) or _EXPLAIN_GOAL.search(query):
            return self._answer_explain(query)

        return GoalQueryResult.miss(query)

    def _answer_explain(self, query: str) -> GoalQueryResult:
        """Explain a specific goal by searching for its title."""
        # Try to extract topic
        m = _EXPLAIN_GOAL.search(query)
        if m:
            topic = m.group(1).strip()
            results = self._engine.search(topic)
            if results:
                g = results[0]
                return GoalQueryResult(
                    answered=True, question=query,
                    answer=g.explain(), goals=(g,)
                )
        # Fall back to current goal
        goal = self._engine.current_goal()
        if goal:
            return GoalQueryResult(
                answered=True, question=query,
                answer=goal.explain(), goals=(goal,)
            )
        return GoalQueryResult.empty(query, "No goal found to explain, sir.")

    def _show_all(self, query: str) -> GoalQueryResult:
        """Full goal list for the inspector."""
        goals = self._engine.all_goals()
        if not goals:
            return GoalQueryResult.empty(query, "No goals recorded yet, sir.")
        lines = ["Goals:"]
        for g in goals:
            lines.append(f"  [{g.status.label():<10}] [{g.priority.label():<8}] {g.title}")
        return GoalQueryResult(
            answered=True, question=query,
            answer="\n".join(lines), goals=tuple(goals)
        )