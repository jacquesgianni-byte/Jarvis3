"""
Genesis-032 Sprint-003: EpisodicMemoryEngine

Assembles related memories into coherent episodes by time window or label.
No AI summarisation. No inference. Pure deterministic grouping.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# ─────────────────────────────────────────────
# Enums & Data Models
# ─────────────────────────────────────────────

class EpisodeQueryType(Enum):
    TEMPORAL = auto()
    LABELED  = auto()


@dataclass
class EpisodeQuery:
    query_type:       EpisodeQueryType
    label:            Optional[str]    = None   # for LABELED queries
    temporal_context: Optional[object] = None   # TemporalContext for TEMPORAL queries
    raw_query:        str              = ""


@dataclass
class EpisodeSummary:
    label:        str
    memories:     list[str]       = field(default_factory=list)
    memory_count: int             = 0
    time_range:   Optional[str]   = None

    def __post_init__(self):
        self.memory_count = len(self.memories)


# ─────────────────────────────────────────────
# Provider base class
# ─────────────────────────────────────────────

class EpisodeProvider(ABC):
    """Abstract base for episode providers."""

    @abstractmethod
    def can_handle(self, query: EpisodeQuery) -> bool: ...

    @abstractmethod
    def gather(self, query: EpisodeQuery, knowledge_engine) -> list[str]: ...


# ─────────────────────────────────────────────
# TemporalEpisodeProvider
# ─────────────────────────────────────────────

class TemporalEpisodeProvider(EpisodeProvider):
    """Gathers memories whose temporal tags fall within a resolved date range."""

    def can_handle(self, query: EpisodeQuery) -> bool:
        return query.query_type is EpisodeQueryType.TEMPORAL

    def gather(self, query: EpisodeQuery, knowledge_engine) -> list[str]:
        if query.temporal_context is None:
            return []

        tc = query.temporal_context
        # TemporalContext exposes .start_date and .end_date (datetime.date objects)
        start = getattr(tc, "start_date", None)
        end   = getattr(tc, "end_date",   None)

        if start is None:
            return []

        results: list[str] = []
        for memory in _iter_memories(knowledge_engine):
            mem_date = _extract_date_tag(memory)
            if mem_date is None:
                continue
            if end is not None:
                if start <= mem_date <= end:
                    results.append(_memory_content(memory))
            else:
                if mem_date == start:
                    results.append(_memory_content(memory))

        return results


# ─────────────────────────────────────────────
# LabeledEpisodeProvider
# ─────────────────────────────────────────────

class LabeledEpisodeProvider(EpisodeProvider):
    """Gathers memories whose tags match a normalised label."""

    def can_handle(self, query: EpisodeQuery) -> bool:
        return query.query_type is EpisodeQueryType.LABELED

    def gather(self, query: EpisodeQuery, knowledge_engine) -> list[str]:
        if not query.label:
            return []

        target = _normalise_label(query.label)
        results: list[str] = []

        for memory in _iter_memories(knowledge_engine):
            tags = _extract_tags(memory)
            if any(_normalise_label(t) == target for t in tags):
                results.append(_memory_content(memory))

        return results


# ─────────────────────────────────────────────
# EpisodicMemoryEngine
# ─────────────────────────────────────────────

# Trigger phrases — data-driven, ordered longest-first to avoid short-phrase
# shadowing longer ones.
_TRIGGER_PHRASES: list[str] = [
    "what was happening",
    "what happened during",
    "what happened",
    "what did we do during",
    "what did we do",
    "what did i do during",
    "what did i do",
    "tell me about",
    "recap of",
    "recap",
    "summary of",
]

# Temporal signal words — if the remainder contains one of these, treat as
# TEMPORAL; otherwise LABELED.
_TEMPORAL_SIGNALS: list[str] = [
    "yesterday",
    "today",
    "last week",
    "this week",
    "last month",
    "this month",
    "last tuesday",
    "last monday",
    "last wednesday",
    "last thursday",
    "last friday",
    "last saturday",
    "last sunday",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "ago",
]


class EpisodicMemoryEngine:
    """
    Assembles episodes from existing KnowledgeEngine memories on demand.

    No new storage layer. Episodes emerge from temporal tags and label tags
    already recorded in KnowledgeEngine.
    """

    def __init__(self, knowledge_engine, temporal_parser):
        self._knowledge_engine = knowledge_engine
        self._temporal_parser  = temporal_parser
        self._providers: list[EpisodeProvider] = [
            TemporalEpisodeProvider(),
            LabeledEpisodeProvider(),
        ]

    # ── Query parsing ──────────────────────────────────────────────────────

    def parse_query(self, utterance: str) -> Optional[EpisodeQuery]:
        """
        Detect episodic recall intent and return an EpisodeQuery, or None.
        """
        lower = utterance.lower().strip()

        remainder: Optional[str] = None
        for phrase in _TRIGGER_PHRASES:
            if lower.startswith(phrase):
                remainder = lower[len(phrase):].strip()
                # Strip leading connectives
                remainder = re.sub(r"^(during|in|on|about|at)\s+", "", remainder).strip()
                break
            # Also check if phrase appears mid-sentence after punctuation
            match = re.search(r"(?:^|[.?!,]\s*)" + re.escape(phrase), lower)
            if match:
                remainder = lower[match.end():].strip()
                remainder = re.sub(r"^(during|in|on|about|at)\s+", "", remainder).strip()
                break

        if remainder is None:
            return None

        # Classify remainder
        if self._is_temporal(remainder):
            tc = self._resolve_temporal(remainder, utterance)
            label = self._temporal_label(remainder)
            return EpisodeQuery(
                query_type=EpisodeQueryType.TEMPORAL,
                temporal_context=tc,
                label=label,
                raw_query=utterance,
            )
        else:
            label = remainder.strip("?!. ") or utterance
            return EpisodeQuery(
                query_type=EpisodeQueryType.LABELED,
                label=label,
                raw_query=utterance,
            )

    def _is_temporal(self, text: str) -> bool:
        for signal in _TEMPORAL_SIGNALS:
            if signal in text:
                return True
        # Matches patterns like "3 days ago", "2 weeks ago"
        if re.search(r"\d+\s+(?:day|week|month)s?\s+ago", text):
            return True
        return False

    def _resolve_temporal(self, remainder: str, original: str):
        """Ask TemporalParser to resolve the date range."""
        try:
            return self._temporal_parser.parse(remainder) or self._temporal_parser.parse(original)
        except Exception:
            return None

    def _temporal_label(self, remainder: str) -> str:
        """Produce a readable label from the temporal remainder."""
        return remainder.strip("?!. ").title() or "that time"

    # ── Recall ─────────────────────────────────────────────────────────────

    def recall(self, query: EpisodeQuery) -> Optional[EpisodeSummary]:
        for provider in self._providers:
            if provider.can_handle(query):
                memories = provider.gather(query, self._knowledge_engine)
                label = query.label or query.raw_query
                # Humanise LABELED label capitalisation
                if query.query_type is EpisodeQueryType.LABELED and query.label:
                    label = query.label.title()
                summary = EpisodeSummary(label=label, memories=memories)
                return summary if memories else None
        return None

    # ── Formatting ─────────────────────────────────────────────────────────

    def format_response(self, summary: Optional[EpisodeSummary]) -> str:
        if summary is None or summary.memory_count == 0:
            label = summary.label if summary else "that period"
            return f"I don't have any memories from {label}."

        if summary.memory_count == 1:
            return f"From {summary.label}: {summary.memories[0]}"

        lines = "\n".join(f"- {m}" for m in summary.memories)
        return f"Here's what I have from {summary.label}:\n{lines}"


# ─────────────────────────────────────────────
# Internal helpers — adapt to KnowledgeEngine API
# ─────────────────────────────────────────────

def _iter_memories(knowledge_engine):
    """
    Yield all memory objects from KnowledgeEngine.
    Tries several known API shapes; returns empty iterator if none match.
    """
    # Shape 1: ke.get_all_memories() → list
    get_all = getattr(knowledge_engine, "get_all_memories", None)
    if callable(get_all):
        yield from (get_all() or [])
        return

    # Shape 2: ke.memories → list
    memories_attr = getattr(knowledge_engine, "memories", None)
    if isinstance(memories_attr, list):
        yield from memories_attr
        return

    # Shape 3: ke.memory_store → dict/list
    store = getattr(knowledge_engine, "memory_store", None)
    if isinstance(store, dict):
        for items in store.values():
            if isinstance(items, list):
                yield from items
        return
    if isinstance(store, list):
        yield from store


def _memory_content(memory) -> str:
    """Extract the plain-text content of a memory object."""
    # Dataclass / object with .content attribute
    content = getattr(memory, "content", None)
    if content is not None:
        return str(content)
    # Dict
    if isinstance(memory, dict):
        return str(memory.get("content") or memory.get("text") or memory)
    return str(memory)


def _extract_date_tag(memory) -> Optional[object]:
    """
    Extract a datetime.date from a memory's temporal tags.
    Returns None if no date found.
    """
    import datetime

    tags = _extract_tags(memory)
    for tag in tags:
        # ISO date string: "2026-07-27"
        try:
            return datetime.date.fromisoformat(tag)
        except (ValueError, TypeError):
            pass

    # Check dedicated date attribute
    for attr in ("date", "created_at", "timestamp"):
        val = getattr(memory, attr, None) or (memory.get(attr) if isinstance(memory, dict) else None)
        if val is None:
            continue
        if isinstance(val, datetime.date):
            return val
        if isinstance(val, datetime.datetime):
            return val.date()
        try:
            return datetime.date.fromisoformat(str(val)[:10])
        except (ValueError, TypeError):
            pass

    return None


def _extract_tags(memory) -> list[str]:
    """Extract all tags from a memory object as a list of strings."""
    # Object with .tags attribute
    tags_attr = getattr(memory, "tags", None)
    if isinstance(tags_attr, list):
        return [str(t) for t in tags_attr]
    if isinstance(tags_attr, set):
        return [str(t) for t in tags_attr]

    # Dict
    if isinstance(memory, dict):
        raw = memory.get("tags", [])
        if isinstance(raw, (list, set)):
            return [str(t) for t in raw]

    return []


def _normalise_label(label: str) -> str:
    """Lowercase and strip whitespace for comparison."""
    return label.lower().strip()
