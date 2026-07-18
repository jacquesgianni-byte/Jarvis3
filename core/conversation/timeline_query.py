"""
Jarvis Timeline Query Engine (Genesis-020 Sprint-003)

Answers natural language questions about conversation history
using the ConversationTimeline.

Design:
    All queries are deterministic — zero AI calls.
    Translates natural language patterns into timeline queries.
    Returns QueryResult with the answer and the matching events.

Handles questions like:
    "What did we finish today?"
    "What are we currently working on?"
    "Which Genesis are we up to?"
    "When did we freeze Sprint-001?"
    "What happened before Sprint-002?"
    "What decisions did we make?"
    "What did we start?"
    "Who have we mentioned?"
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Optional, TYPE_CHECKING

from core.conversation.timeline_event import EventType, TimelineEvent

if TYPE_CHECKING:
    from core.conversation.conversation_timeline import ConversationTimeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

_WHAT_DID_WE_FINISH    = re.compile(r"\bwhat did we (?:finish|complete|ship|freeze)\b", re.IGNORECASE)
_WHAT_ARE_WE_DOING     = re.compile(r"\bwhat are we (?:doing|working on|building|currently)\b", re.IGNORECASE)
_WHICH_GENESIS         = re.compile(r"\bwhich genesis\b", re.IGNORECASE)
_WHEN_DID_WE_FREEZE    = re.compile(r"\bwhen did we (?:freeze|frozen?|complete|finish)\b", re.IGNORECASE)
_WHAT_HAPPENED_BEFORE  = re.compile(r"\bwhat happened (?:before|prior to)\b", re.IGNORECASE)
_WHAT_DECISIONS        = re.compile(r"\bwhat decisions\b", re.IGNORECASE)
_WHAT_DID_WE_START     = re.compile(r"\bwhat did we (?:start|begin|kick off)\b", re.IGNORECASE)
_WHO_HAVE_WE_MENTIONED = re.compile(r"\bwho (?:have we|did we) (?:mention(?:ed)?|talk(?:ed)? about|discuss(?:ed)?)\b", re.IGNORECASE)
_WHAT_HAPPENED_TODAY   = re.compile(r"\bwhat happened today\b", re.IGNORECASE)
_WHAT_HAPPENED_YESTERDAY = re.compile(r"\bwhat happened yesterday\b", re.IGNORECASE)
_SHOW_TIMELINE         = re.compile(r"\b(?:show|inspect|display) timeline\b|^/timeline$", re.IGNORECASE)

# Value references in queries — "when did we freeze Sprint-001"
_VALUE_IN_QUERY        = re.compile(r"\b(sprint[- ]?\d+|genesis[- ]?[\d\.]+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class QueryResult:
    """
    Result of a timeline query.

    Attributes:
        answered:   True if the timeline had enough information.
        question:   The original query.
        answer:     Human-readable answer string.
        events:     The matching timeline events.
    """
    answered: bool
    question: str
    answer:   str               = ""
    events:   tuple             = field(default_factory=tuple)

    @classmethod
    def miss(cls, question: str) -> "QueryResult":
        return cls(answered=False, question=question)


class TimelineQueryEngine:
    """
    Answers natural language questions about conversation history.

    Wraps a ConversationTimeline and translates pattern-matched
    queries into deterministic timeline lookups.

    Called by the Agent in the MEMORY routing path as a final
    fallback before calling the AI provider.
    """

    def __init__(self, timeline: "ConversationTimeline") -> None:
        self._timeline = timeline

    def can_answer(self, query: str) -> bool:
        """Return True if this engine can attempt to answer the query."""
        return any(p.search(query) for p in [
            _WHAT_DID_WE_FINISH,
            _WHAT_ARE_WE_DOING,
            _WHICH_GENESIS,
            _WHEN_DID_WE_FREEZE,
            _WHAT_HAPPENED_BEFORE,
            _WHAT_DECISIONS,
            _WHAT_DID_WE_START,
            _WHO_HAVE_WE_MENTIONED,
            _WHAT_HAPPENED_TODAY,
            _WHAT_HAPPENED_YESTERDAY,
            _SHOW_TIMELINE,
        ])

    def answer(self, query: str) -> QueryResult:
        """
        Answer a natural language question about conversation history.

        Returns QueryResult with answered=True if events were found,
        False if the timeline had no matching events.
        """
        try:
            return self._answer(query)
        except Exception:
            logger.exception("[TIMELINE] Query engine error.")
            return QueryResult.miss(query)

    def _answer(self, query: str) -> QueryResult:
        tl = self._timeline

        if _SHOW_TIMELINE.search(query):
            return self._show_full_timeline(query)

        if _WHAT_HAPPENED_TODAY.search(query):
            events = tl.today_events()
            if not events:
                return QueryResult(answered=True, question=query,
                    answer="Nothing was recorded in the timeline today yet, sir.",
                    events=tuple(events))
            return self._summarise_events("Today", events, query)

        if _WHAT_HAPPENED_YESTERDAY.search(query):
            events = tl.yesterday_events()
            if not events:
                return QueryResult(answered=True, question=query,
                    answer="Nothing was recorded in the timeline yesterday, sir.",
                    events=tuple(events))
            return self._summarise_events("Yesterday", events, query)

        if _WHAT_DID_WE_FINISH.search(query):
            events = (tl.events_of_type(EventType.FINISH_SPRINT) +
                      tl.events_of_type(EventType.FREEZE) +
                      tl.events_of_type(EventType.ACHIEVEMENT))
            events.sort(key=lambda e: e.turn)
            if not events:
                return QueryResult.miss(query)
            latest = events[-1]
            others = [e.value for e in events[:-1]]
            answer = f"The most recent completion was {latest.value} (turn {latest.turn})."
            if others:
                answer += f" Earlier: {', '.join(others)}."
            return QueryResult(answered=True, question=query, answer=answer,
                               events=tuple(events))

        if _WHAT_ARE_WE_DOING.search(query):
            sprint = tl.latest(EventType.START_SPRINT)
            project = tl.latest(EventType.START_PROJECT)
            if not sprint and not project:
                return QueryResult.miss(query)
            parts = []
            if sprint:
                parts.append(f"working on {sprint.value}")
            if project and (not sprint or project.turn > sprint.turn):
                parts.append(f"building {project.value}")
            answer = "Currently " + " and ".join(parts) + ", sir."
            events = [e for e in [sprint, project] if e]
            return QueryResult(answered=True, question=query, answer=answer,
                               events=tuple(events))

        if _WHICH_GENESIS.search(query):
            # Find the latest Genesis project or sprint
            all_events = (tl.events_of_type(EventType.START_PROJECT) +
                          tl.events_of_type(EventType.START_SPRINT) +
                          tl.events_of_type(EventType.FREEZE))
            genesis_events = [e for e in all_events
                              if re.search(r"\bgenesis\b", e.value, re.IGNORECASE)]
            if not genesis_events:
                return QueryResult.miss(query)
            genesis_events.sort(key=lambda e: e.turn)
            latest = genesis_events[-1]
            answer = f"The latest Genesis milestone recorded is {latest.value}, sir."
            return QueryResult(answered=True, question=query, answer=answer,
                               events=(latest,))

        if _WHEN_DID_WE_FREEZE.search(query):
            # Try to match a specific value in the query
            value_match = _VALUE_IN_QUERY.search(query)
            freeze_events = (tl.events_of_type(EventType.FREEZE) +
                             tl.events_of_type(EventType.FINISH_SPRINT))
            if value_match:
                target = value_match.group(1).lower()
                matching = [e for e in freeze_events
                            if target in e.value.lower()]
                if matching:
                    e = matching[-1]
                    answer = (f"{e.value} was frozen at turn {e.turn}"
                              f" on {e.date_str()}, sir.")
                    return QueryResult(answered=True, question=query,
                                       answer=answer, events=(e,))
            # Fall back to most recent freeze
            if freeze_events:
                freeze_events.sort(key=lambda e: e.turn)
                e = freeze_events[-1]
                answer = f"The most recent freeze was {e.value} at turn {e.turn}, sir."
                return QueryResult(answered=True, question=query,
                                   answer=answer, events=(e,))
            return QueryResult.miss(query)

        if _WHAT_HAPPENED_BEFORE.search(query):
            value_match = _VALUE_IN_QUERY.search(query)
            if not value_match:
                return QueryResult.miss(query)
            target = value_match.group(1).lower()
            all_events = tl.all_events()
            # Find the turn of the first event matching the target
            ref_turn = None
            for e in all_events:
                if target in e.value.lower():
                    ref_turn = e.turn
                    break
            if ref_turn is None:
                return QueryResult.miss(query)
            before = tl.query(until_turn=ref_turn - 1)
            if not before:
                return QueryResult(answered=True, question=query,
                    answer=f"Nothing was recorded before {value_match.group(1)}, sir.",
                    events=tuple())
            return self._summarise_events(
                f"Before {value_match.group(1)}", before[-5:], query)

        if _WHAT_DECISIONS.search(query):
            events = tl.events_of_type(EventType.DECISION)
            if not events:
                return QueryResult(answered=True, question=query,
                    answer="No decisions have been recorded in the timeline yet, sir.",
                    events=tuple())
            values = [e.value for e in events[-5:]]
            answer = f"Decisions recorded: {'; '.join(values)}."
            return QueryResult(answered=True, question=query, answer=answer,
                               events=tuple(events))

        if _WHAT_DID_WE_START.search(query):
            events = (tl.events_of_type(EventType.START_PROJECT) +
                      tl.events_of_type(EventType.START_SPRINT) +
                      tl.events_of_type(EventType.TASK))
            events.sort(key=lambda e: e.turn)
            if not events:
                return QueryResult.miss(query)
            values = [e.value for e in events[-5:]]
            answer = f"Started: {'; '.join(values)}, sir."
            return QueryResult(answered=True, question=query, answer=answer,
                               events=tuple(events))

        if _WHO_HAVE_WE_MENTIONED.search(query):
            events = tl.events_of_type(EventType.PERSON)
            if not events:
                return QueryResult(answered=True, question=query,
                    answer="No people have been recorded in the timeline yet, sir.",
                    events=tuple())
            names = list(dict.fromkeys(e.value for e in events))  # unique, ordered
            answer = f"People mentioned: {', '.join(names)}, sir."
            return QueryResult(answered=True, question=query, answer=answer,
                               events=tuple(events))

        return QueryResult.miss(query)

    def _summarise_events(
        self, label: str, events: list[TimelineEvent], query: str
    ) -> QueryResult:
        """Produce a readable summary of a list of events."""
        parts = [f"{e.event_type.label()}: {e.value} (turn {e.turn})"
                 for e in events]
        answer = f"{label} — " + "; ".join(parts) + "."
        return QueryResult(answered=True, question=query, answer=answer,
                           events=tuple(events))

    def _show_full_timeline(self, query: str) -> QueryResult:
        """Return a full formatted timeline for the inspector."""
        events = self._timeline.all_events()
        if not events:
            return QueryResult(answered=True, question=query,
                answer="The timeline is empty, sir.", events=tuple())
        lines = ["Timeline:"]
        for e in events:
            lines.append(f"  Turn {e.turn:>3} — {e.event_type.label():<16} {e.value}")
        return QueryResult(answered=True, question=query,
            answer="\n".join(lines), events=tuple(events))