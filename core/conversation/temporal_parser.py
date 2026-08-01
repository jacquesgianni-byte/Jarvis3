"""
Temporal Parser (Genesis-031 Sprint-001)

Detects and resolves temporal expressions in natural language into
structured TemporalContext dataclasses with resolved dates.

Responsibilities:
    - Detect temporal expressions: "yesterday", "last Tuesday", "next week"
    - Resolve relative expressions to absolute dates
    - Produce TemporalContext for enriching KnowledgeEngine records
    - Never own or store facts -- enrichment only

Design constraints:
    - No AI calls
    - No KnowledgeEngine writes
    - Deterministic -- same input + same reference_date -> same output
    - No new storage systems -- enriches existing MemoryRecord.metadata/tags

Architecture position:
    MemoryDetector / SlotCompletionEngine
        -> TemporalParser.parse(text, reference_date)
        -> TemporalContext (structured temporal metadata)
        -> KnowledgeEngine.store_memory(..., metadata=ctx.to_metadata(), tags=ctx.to_tags())

KnowledgeEngine remains the single source of truth.
TemporalParser only produces structured temporal information.

Genesis-031 Sprint-001.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Temporal type classification
# ---------------------------------------------------------------------------

class TemporalType(str, Enum):
    PAST_RELATIVE   = "past_relative"    # "yesterday", "last week", "3 days ago"
    PAST_NAMED_DAY  = "past_named_day"   # "last Tuesday"
    PRESENT         = "present"          # "today", "now", "currently"
    FUTURE_RELATIVE = "future_relative"  # "tomorrow", "next week", "in 3 days"
    FUTURE_NAMED_DAY = "future_named_day" # "next Friday"
    ABSOLUTE        = "absolute"         # "on the 15th", "in January"
    DURATION        = "duration"         # "for 3 weeks", "over 2 months"
    UNKNOWN         = "unknown"


class TemporalTense(str, Enum):
    PAST    = "past"
    PRESENT = "present"
    FUTURE  = "future"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Day name mapping
# ---------------------------------------------------------------------------

_DAY_NAMES: dict[str, int] = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}

_MONTH_NAMES: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_WORD_NUMBERS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "a": 1, "an": 1,
}

_UNIT_TO_DAYS: dict[str, int] = {
    "day": 1, "days": 1,
    "week": 7, "weeks": 7,
    "month": 30, "months": 30,
    "year": 365, "years": 365,
    "fortnight": 14, "fortnights": 14,
}


# ---------------------------------------------------------------------------
# TemporalContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TemporalContext:
    """
    Structured temporal information extracted from a statement.

    Produced by TemporalParser. Consumed by the memory pipeline to
    enrich KnowledgeEngine records without creating new storage.

    Fields:
        expression:    The raw temporal phrase found ("last Tuesday")
        temporal_type: Classification of the expression
        tense:         Past / present / future
        resolved_date: Absolute date if resolvable, else None
        offset_days:   Days from reference_date (negative = past)
        reference_date: The date used for resolution
        confidence:    How confident we are in the resolution
    """
    expression:    str
    temporal_type: TemporalType
    tense:         TemporalTense
    resolved_date: Optional[date]
    offset_days:   Optional[int]
    reference_date: date
    confidence:    float = 0.90

    def to_metadata(self) -> dict:
        """
        Convert to a dict suitable for KnowledgeEngine record metadata.

        Merges into MemoryRecord.metadata without replacing existing fields.
        """
        m: dict = {
            "temporal_expression": self.expression,
            "temporal_type":       self.temporal_type.value,
            "temporal_tense":      self.tense.value,
        }
        if self.resolved_date:
            m["resolved_date"] = self.resolved_date.isoformat()
        if self.offset_days is not None:
            m["offset_days"] = self.offset_days
        return m

    def to_tags(self) -> list[str]:
        """
        Return tags to add to KnowledgeEngine record tags list.
        """
        tags = ["temporal", self.tense.value]
        if self.temporal_type != TemporalType.UNKNOWN:
            tags.append(self.temporal_type.value)
        return tags

    @classmethod
    def unknown(cls, reference_date: date) -> "TemporalContext":
        """Return an unknown/unresolved TemporalContext."""
        return cls(
            expression="",
            temporal_type=TemporalType.UNKNOWN,
            tense=TemporalTense.UNKNOWN,
            resolved_date=None,
            offset_days=None,
            reference_date=reference_date,
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Detection patterns
#
# Each entry: (compiled regex, handler_name)
# Handlers are methods on TemporalParser.
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[re.Pattern, str]] = [

    # Multi-word patterns FIRST -- must come before single-word to avoid partial matches

    # "the day before yesterday"
    (re.compile(r"\bthe\s+day\s+before\s+yesterday\b", re.IGNORECASE), "day_before_yesterday"),

    # "the day after tomorrow"
    (re.compile(r"\bthe\s+day\s+after\s+tomorrow\b", re.IGNORECASE), "day_after_tomorrow"),

    # "last night" / "this morning" / "this evening"
    (re.compile(r"\b(?:last night|this morning|this afternoon|this evening|tonight)\b", re.IGNORECASE), "time_of_day"),

    # "earlier today" / "earlier"
    (re.compile(r"\b(?:earlier today|earlier)\b", re.IGNORECASE), "earlier"),

    # "over the past N days/weeks"
    (re.compile(r"\bover\s+(?:the\s+)?(?:past|last)\s+(\d+)\s+(days?|weeks?|months?|years?)\b", re.IGNORECASE), "duration_past"),

    # "a week ago" / "a month ago"
    (re.compile(r"\ba\s+(week|month|year|day)\s+ago\b", re.IGNORECASE), "a_unit_ago"),

    # "recently" / "a while ago" / "lately"
    (re.compile(r"\b(?:recently|a while ago|lately|not long ago)\b", re.IGNORECASE), "recently"),

    # "soon" / "shortly" / "in a bit"
    (re.compile(r"\b(?:soon|shortly|in a bit|in a moment)\b", re.IGNORECASE), "soon"),

    # "N days/weeks/months ago" or "three weeks ago"
    (re.compile(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(days?|weeks?|months?|years?|fortnights?)\s+ago\b", re.IGNORECASE), "n_units_ago"),

    # "in N days/weeks/months" or "in three days"
    (re.compile(r"\bin\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(days?|weeks?|months?|years?)\b", re.IGNORECASE), "in_n_units"),

    # "for N days/weeks/months" (duration)
    (re.compile(r"\bfor\s+(\d+)\s+(days?|weeks?|months?|years?)\b", re.IGNORECASE), "duration"),

    # "last <day>" e.g. "last Tuesday"
    (re.compile(r"\blast\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.IGNORECASE), "last_named_day"),

    # "next <day>" e.g. "next Friday"
    (re.compile(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.IGNORECASE), "next_named_day"),

    # "this <day>" e.g. "this Wednesday"
    (re.compile(r"\bthis\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.IGNORECASE), "this_named_day"),

    # "last week/month/year"
    (re.compile(r"\blast\s+(week|month|year)\b", re.IGNORECASE), "last_unit"),

    # "next week/month/year"
    (re.compile(r"\bnext\s+(week|month|year)\b", re.IGNORECASE), "next_unit"),

    # Single-word patterns LAST
    # "yesterday"
    (re.compile(r"\byesterday\b", re.IGNORECASE), "yesterday"),

    # "today" / "now" / "currently"
    (re.compile(r"\b(?:today|now|currently|at the moment|right now)\b", re.IGNORECASE), "today"),

    # "tomorrow"
    (re.compile(r"\btomorrow\b", re.IGNORECASE), "tomorrow"),
]


# ---------------------------------------------------------------------------
# TemporalParser
# ---------------------------------------------------------------------------

class TemporalParser:
    """
    Detects and resolves temporal expressions in natural language.

    Stateless -- reference_date must be supplied on each call.
    Typically reference_date = date.today() in production.

    Public API:
        parse(text, reference_date) -> Optional[TemporalContext]
        parse_all(text, reference_date) -> list[TemporalContext]
        has_temporal(text) -> bool
    """

    def parse(
        self,
        text: str,
        reference_date: Optional[date] = None,
    ) -> Optional[TemporalContext]:
        """
        Parse the first temporal expression found in text.

        Args:
            text:           The user's raw message.
            reference_date: Date to resolve relative expressions against.
                            Defaults to today.

        Returns:
            TemporalContext if a temporal expression is found, else None.
        """
        if not text or not text.strip():
            return None

        ref = reference_date or date.today()

        for pattern, handler_name in _PATTERNS:
            m = pattern.search(text)
            if m:
                handler = getattr(self, f"_handle_{handler_name}", None)
                if handler:
                    ctx = handler(m, ref)
                    if ctx:
                        logger.debug(
                            "[TEMPORAL] %r -> type=%s tense=%s date=%s",
                            ctx.expression, ctx.temporal_type.value,
                            ctx.tense.value, ctx.resolved_date,
                        )
                        return ctx

        return None

    def parse_all(
        self,
        text: str,
        reference_date: Optional[date] = None,
    ) -> list[TemporalContext]:
        """
        Parse ALL temporal expressions found in text.

        Args:
            text:           The user's raw message.
            reference_date: Date to resolve relative expressions against.

        Returns:
            List of TemporalContext objects (may be empty).
        """
        if not text or not text.strip():
            return []

        ref = reference_date or date.today()
        results = []
        matched_spans: list[tuple[int, int]] = []

        for pattern, handler_name in _PATTERNS:
            for m in pattern.finditer(text):
                # Skip overlapping matches
                start, end = m.span()
                if any(s <= start < e or s < end <= e for s, e in matched_spans):
                    continue

                handler = getattr(self, f"_handle_{handler_name}", None)
                if handler:
                    ctx = handler(m, ref)
                    if ctx:
                        results.append(ctx)
                        matched_spans.append((start, end))

        return results

    def has_temporal(self, text: str) -> bool:
        """
        Return True if text contains any temporal expression.

        Fast check -- does not resolve dates.
        """
        if not text:
            return False
        for pattern, _ in _PATTERNS:
            if pattern.search(text):
                return True
        return False

    # ------------------------------------------------------------------
    # Handlers -- one per pattern entry
    # ------------------------------------------------------------------

    def _handle_yesterday(self, m: re.Match, ref: date) -> TemporalContext:
        resolved = ref - timedelta(days=1)
        return TemporalContext(
            expression="yesterday",
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-1,
            reference_date=ref,
        )

    def _handle_today(self, m: re.Match, ref: date) -> TemporalContext:
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PRESENT,
            tense=TemporalTense.PRESENT,
            resolved_date=ref,
            offset_days=0,
            reference_date=ref,
        )

    def _handle_tomorrow(self, m: re.Match, ref: date) -> TemporalContext:
        resolved = ref + timedelta(days=1)
        return TemporalContext(
            expression="tomorrow",
            temporal_type=TemporalType.FUTURE_RELATIVE,
            tense=TemporalTense.FUTURE,
            resolved_date=resolved,
            offset_days=1,
            reference_date=ref,
        )

    def _handle_last_named_day(self, m: re.Match, ref: date) -> TemporalContext:
        day_name = m.group(1).lower()
        target_weekday = _DAY_NAMES.get(day_name)
        if target_weekday is None:
            return None
        days_back = (ref.weekday() - target_weekday) % 7
        if days_back == 0:
            days_back = 7
        resolved = ref - timedelta(days=days_back)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_NAMED_DAY,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-days_back,
            reference_date=ref,
        )

    def _handle_next_named_day(self, m: re.Match, ref: date) -> TemporalContext:
        day_name = m.group(1).lower()
        target_weekday = _DAY_NAMES.get(day_name)
        if target_weekday is None:
            return None
        days_ahead = (target_weekday - ref.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved = ref + timedelta(days=days_ahead)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.FUTURE_NAMED_DAY,
            tense=TemporalTense.FUTURE,
            resolved_date=resolved,
            offset_days=days_ahead,
            reference_date=ref,
        )

    def _handle_this_named_day(self, m: re.Match, ref: date) -> TemporalContext:
        day_name = m.group(1).lower()
        target_weekday = _DAY_NAMES.get(day_name)
        if target_weekday is None:
            return None
        days_ahead = (target_weekday - ref.weekday()) % 7
        resolved = ref + timedelta(days=days_ahead)
        tense = TemporalTense.FUTURE if days_ahead > 0 else TemporalTense.PRESENT
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.FUTURE_NAMED_DAY if days_ahead > 0 else TemporalType.PRESENT,
            tense=tense,
            resolved_date=resolved,
            offset_days=days_ahead,
            reference_date=ref,
        )

    def _handle_n_units_ago(self, m: re.Match, ref: date) -> TemporalContext:
        raw_n = m.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _WORD_NUMBERS.get(raw_n, 1)
        unit = m.group(2).lower()
        days = _UNIT_TO_DAYS.get(unit, 1) * n
        resolved = ref - timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-days,
            reference_date=ref,
        )

    def _handle_last_unit(self, m: re.Match, ref: date) -> TemporalContext:
        unit = m.group(1).lower()
        days = _UNIT_TO_DAYS.get(unit, 7)
        resolved = ref - timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-days,
            reference_date=ref,
        )

    def _handle_next_unit(self, m: re.Match, ref: date) -> TemporalContext:
        unit = m.group(1).lower()
        days = _UNIT_TO_DAYS.get(unit, 7)
        resolved = ref + timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.FUTURE_RELATIVE,
            tense=TemporalTense.FUTURE,
            resolved_date=resolved,
            offset_days=days,
            reference_date=ref,
        )

    def _handle_in_n_units(self, m: re.Match, ref: date) -> TemporalContext:
        raw_n = m.group(1).lower()
        n = int(raw_n) if raw_n.isdigit() else _WORD_NUMBERS.get(raw_n, 1)
        unit = m.group(2).lower()
        days = _UNIT_TO_DAYS.get(unit, 1) * n
        resolved = ref + timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.FUTURE_RELATIVE,
            tense=TemporalTense.FUTURE,
            resolved_date=resolved,
            offset_days=days,
            reference_date=ref,
        )

    def _handle_a_unit_ago(self, m: re.Match, ref: date) -> TemporalContext:
        unit = m.group(1).lower()
        days = _UNIT_TO_DAYS.get(unit, 7)
        resolved = ref - timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-days,
            reference_date=ref,
        )

    def _handle_day_before_yesterday(self, m: re.Match, ref: date) -> TemporalContext:
        resolved = ref - timedelta(days=2)
        return TemporalContext(
            expression="the day before yesterday",
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=resolved,
            offset_days=-2,
            reference_date=ref,
        )

    def _handle_day_after_tomorrow(self, m: re.Match, ref: date) -> TemporalContext:
        resolved = ref + timedelta(days=2)
        return TemporalContext(
            expression="the day after tomorrow",
            temporal_type=TemporalType.FUTURE_RELATIVE,
            tense=TemporalTense.FUTURE,
            resolved_date=resolved,
            offset_days=2,
            reference_date=ref,
        )

    def _handle_recently(self, m: re.Match, ref: date) -> TemporalContext:
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=None,
            offset_days=None,
            reference_date=ref,
            confidence=0.70,
        )

    def _handle_soon(self, m: re.Match, ref: date) -> TemporalContext:
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.FUTURE_RELATIVE,
            tense=TemporalTense.FUTURE,
            resolved_date=None,
            offset_days=None,
            reference_date=ref,
            confidence=0.70,
        )

    def _handle_time_of_day(self, m: re.Match, ref: date) -> TemporalContext:
        expr = m.group(0).lower()
        if "last night" in expr:
            resolved = ref - timedelta(days=1)
            tense = TemporalTense.PAST
            offset = -1
        elif "tomorrow" in expr:
            resolved = ref + timedelta(days=1)
            tense = TemporalTense.FUTURE
            offset = 1
        else:
            resolved = ref
            tense = TemporalTense.PRESENT
            offset = 0
        return TemporalContext(
            expression=expr,
            temporal_type=TemporalType.PRESENT if tense == TemporalTense.PRESENT else (
                TemporalType.PAST_RELATIVE if tense == TemporalTense.PAST else TemporalType.FUTURE_RELATIVE
            ),
            tense=tense,
            resolved_date=resolved,
            offset_days=offset,
            reference_date=ref,
        )

    def _handle_earlier(self, m: re.Match, ref: date) -> TemporalContext:
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=ref,
            offset_days=0,
            reference_date=ref,
            confidence=0.75,
        )

    def _handle_duration(self, m: re.Match, ref: date) -> TemporalContext:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = _UNIT_TO_DAYS.get(unit, 1) * n
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.DURATION,
            tense=TemporalTense.UNKNOWN,
            resolved_date=None,
            offset_days=days,
            reference_date=ref,
        )

    def _handle_duration_past(self, m: re.Match, ref: date) -> TemporalContext:
        n = int(m.group(1))
        unit = m.group(2).lower()
        days = _UNIT_TO_DAYS.get(unit, 1) * n
        start = ref - timedelta(days=days)
        return TemporalContext(
            expression=m.group(0).lower(),
            temporal_type=TemporalType.DURATION,
            tense=TemporalTense.PAST,
            resolved_date=start,
            offset_days=-days,
            reference_date=ref,
        )
