"""
Tests for Genesis-031 Sprint-001: Temporal Parser

Covers:
    - TemporalContext: to_metadata(), to_tags()
    - TemporalParser.parse(): all expression types
    - TemporalParser.parse_all(): multiple expressions
    - TemporalParser.has_temporal(): fast check
    - Date resolution accuracy
    - Edge cases: empty input, no temporal expression
    - KnowledgeEngine metadata enrichment pattern
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from core.conversation.temporal_parser import (
    TemporalParser,
    TemporalContext,
    TemporalType,
    TemporalTense,
)


# ---------------------------------------------------------------------------
# Fixed reference date for deterministic tests
# Reference: Wednesday 2026-07-29
# ---------------------------------------------------------------------------

REF = date(2026, 7, 29)   # Wednesday


@pytest.fixture
def parser() -> TemporalParser:
    return TemporalParser()


# ===========================================================================
# has_temporal -- fast check
# ===========================================================================

class TestHasTemporal:

    def test_yesterday(self, parser):
        assert parser.has_temporal("I bought a car yesterday") is True

    def test_tomorrow(self, parser):
        assert parser.has_temporal("Meeting tomorrow") is True

    def test_last_week(self, parser):
        assert parser.has_temporal("last week was busy") is True

    def test_no_temporal(self, parser):
        assert parser.has_temporal("The sky is blue") is False

    def test_empty(self, parser):
        assert parser.has_temporal("") is False

    def test_none_like(self, parser):
        assert parser.has_temporal(None) is False


# ===========================================================================
# parse -- present expressions
# ===========================================================================

class TestParsePresent:

    def test_today(self, parser):
        ctx = parser.parse("I am busy today", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PRESENT
        assert ctx.resolved_date == REF
        assert ctx.offset_days == 0

    def test_now(self, parser):
        ctx = parser.parse("I am working now", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PRESENT

    def test_currently(self, parser):
        ctx = parser.parse("currently studying", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PRESENT


# ===========================================================================
# parse -- past expressions
# ===========================================================================

class TestParsePast:

    def test_yesterday(self, parser):
        ctx = parser.parse("I went to the gym yesterday", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST
        assert ctx.resolved_date == REF - timedelta(days=1)
        assert ctx.offset_days == -1

    def test_day_before_yesterday(self, parser):
        ctx = parser.parse("the day before yesterday", REF)
        assert ctx is not None
        assert ctx.resolved_date == REF - timedelta(days=2)
        assert ctx.offset_days == -2

    def test_last_tuesday(self, parser):
        # REF is Wednesday 2026-07-29
        # Last Tuesday = 2026-07-28 (1 day ago)
        ctx = parser.parse("I bought a car last Tuesday", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST
        assert ctx.temporal_type == TemporalType.PAST_NAMED_DAY
        assert ctx.resolved_date.weekday() == 1  # Tuesday

    def test_last_friday(self, parser):
        # REF is Wednesday, last Friday = 5 days ago
        ctx = parser.parse("last Friday", REF)
        assert ctx is not None
        assert ctx.resolved_date.weekday() == 4  # Friday
        assert ctx.resolved_date < REF

    def test_3_days_ago(self, parser):
        ctx = parser.parse("I saw him 3 days ago", REF)
        assert ctx is not None
        assert ctx.resolved_date == REF - timedelta(days=3)
        assert ctx.offset_days == -3

    def test_2_weeks_ago(self, parser):
        ctx = parser.parse("2 weeks ago", REF)
        assert ctx is not None
        assert ctx.offset_days == -14

    def test_last_week(self, parser):
        ctx = parser.parse("last week", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST
        assert ctx.offset_days == -7

    def test_last_month(self, parser):
        ctx = parser.parse("last month", REF)
        assert ctx is not None
        assert ctx.offset_days == -30

    def test_last_year(self, parser):
        ctx = parser.parse("last year", REF)
        assert ctx is not None
        assert ctx.offset_days == -365

    def test_a_week_ago(self, parser):
        ctx = parser.parse("a week ago", REF)
        assert ctx is not None
        assert ctx.offset_days == -7

    def test_recently(self, parser):
        ctx = parser.parse("I recently moved", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST
        assert ctx.resolved_date is None  # vague -- no exact date

    def test_last_night(self, parser):
        ctx = parser.parse("last night", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST

    def test_earlier(self, parser):
        ctx = parser.parse("I called earlier", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.PAST


# ===========================================================================
# parse -- future expressions
# ===========================================================================

class TestParseFuture:

    def test_tomorrow(self, parser):
        ctx = parser.parse("Meeting tomorrow", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.FUTURE
        assert ctx.resolved_date == REF + timedelta(days=1)
        assert ctx.offset_days == 1

    def test_day_after_tomorrow(self, parser):
        ctx = parser.parse("the day after tomorrow", REF)
        assert ctx is not None
        assert ctx.resolved_date == REF + timedelta(days=2)
        assert ctx.offset_days == 2

    def test_next_friday(self, parser):
        # REF is Wednesday, next Friday = 2 days ahead
        ctx = parser.parse("next Friday", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.FUTURE
        assert ctx.resolved_date.weekday() == 4  # Friday
        assert ctx.resolved_date > REF

    def test_next_monday(self, parser):
        # REF is Wednesday, next Monday = 5 days ahead
        ctx = parser.parse("next Monday", REF)
        assert ctx is not None
        assert ctx.resolved_date.weekday() == 0  # Monday

    def test_next_week(self, parser):
        ctx = parser.parse("next week", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.FUTURE
        assert ctx.offset_days == 7

    def test_next_month(self, parser):
        ctx = parser.parse("next month", REF)
        assert ctx is not None
        assert ctx.offset_days == 30

    def test_in_3_days(self, parser):
        ctx = parser.parse("in 3 days", REF)
        assert ctx is not None
        assert ctx.resolved_date == REF + timedelta(days=3)
        assert ctx.offset_days == 3

    def test_in_2_weeks(self, parser):
        ctx = parser.parse("in 2 weeks", REF)
        assert ctx is not None
        assert ctx.offset_days == 14

    def test_soon(self, parser):
        ctx = parser.parse("I'll do it soon", REF)
        assert ctx is not None
        assert ctx.tense == TemporalTense.FUTURE


# ===========================================================================
# parse -- duration expressions
# ===========================================================================

class TestParseDuration:

    def test_for_3_weeks(self, parser):
        ctx = parser.parse("I was away for 3 weeks", REF)
        assert ctx is not None
        assert ctx.temporal_type == TemporalType.DURATION
        assert ctx.offset_days == 21

    def test_over_past_2_months(self, parser):
        ctx = parser.parse("over the past 2 months", REF)
        assert ctx is not None
        assert ctx.temporal_type == TemporalType.DURATION
        assert ctx.tense == TemporalTense.PAST


# ===========================================================================
# parse -- no expression
# ===========================================================================

class TestParseNoExpression:

    def test_no_temporal_returns_none(self, parser):
        assert parser.parse("The sky is blue", REF) is None

    def test_empty_returns_none(self, parser):
        assert parser.parse("", REF) is None

    def test_none_returns_none(self, parser):
        assert parser.parse(None, REF) is None


# ===========================================================================
# parse_all -- multiple expressions
# ===========================================================================

class TestParseAll:

    def test_single_expression(self, parser):
        results = parser.parse_all("I went yesterday", REF)
        assert len(results) == 1
        assert results[0].tense == TemporalTense.PAST

    def test_no_expression(self, parser):
        results = parser.parse_all("Hello world", REF)
        assert results == []

    def test_empty(self, parser):
        assert parser.parse_all("", REF) == []


# ===========================================================================
# TemporalContext -- metadata and tags
# ===========================================================================

class TestTemporalContext:

    def test_to_metadata_contains_expression(self, parser):
        ctx = parser.parse("yesterday", REF)
        assert ctx is not None
        meta = ctx.to_metadata()
        assert "temporal_expression" in meta
        assert meta["temporal_expression"] == "yesterday"

    def test_to_metadata_contains_resolved_date(self, parser):
        ctx = parser.parse("yesterday", REF)
        meta = ctx.to_metadata()
        assert "resolved_date" in meta
        expected = (REF - timedelta(days=1)).isoformat()
        assert meta["resolved_date"] == expected

    def test_to_metadata_contains_tense(self, parser):
        ctx = parser.parse("yesterday", REF)
        meta = ctx.to_metadata()
        assert meta["temporal_tense"] == "past"

    def test_to_metadata_contains_offset(self, parser):
        ctx = parser.parse("yesterday", REF)
        meta = ctx.to_metadata()
        assert meta["offset_days"] == -1

    def test_to_tags_contains_temporal(self, parser):
        ctx = parser.parse("yesterday", REF)
        tags = ctx.to_tags()
        assert "temporal" in tags

    def test_to_tags_contains_tense(self, parser):
        ctx = parser.parse("yesterday", REF)
        tags = ctx.to_tags()
        assert "past" in tags

    def test_to_tags_future(self, parser):
        ctx = parser.parse("tomorrow", REF)
        tags = ctx.to_tags()
        assert "future" in tags

    def test_to_metadata_no_date_for_vague(self, parser):
        ctx = parser.parse("recently", REF)
        assert ctx is not None
        meta = ctx.to_metadata()
        assert "resolved_date" not in meta

    def test_unknown_factory(self):
        ctx = TemporalContext.unknown(REF)
        assert ctx.temporal_type == TemporalType.UNKNOWN
        assert ctx.confidence == 0.0
        assert ctx.resolved_date is None


# ===========================================================================
# KnowledgeEngine enrichment pattern
# ===========================================================================

class TestKnowledgeEngineEnrichment:
    """
    Verifies the enrichment pattern works correctly for KnowledgeEngine.
    Does NOT call KnowledgeEngine -- only verifies the data produced.
    """

    def test_metadata_suitable_for_store_memory(self, parser):
        """metadata dict can be merged into existing store_memory call."""
        ctx = parser.parse("I bought a car last Tuesday", REF)
        assert ctx is not None
        meta = ctx.to_metadata()
        tags = ctx.to_tags()

        # Verify all values are JSON-serialisable primitives
        for k, v in meta.items():
            assert isinstance(k, str)
            assert isinstance(v, (str, int, float, bool))

        # Verify tags are strings
        assert all(isinstance(t, str) for t in tags)

    def test_tags_do_not_conflict_with_existing_tags(self, parser):
        """Temporal tags should be additive -- no conflicts with standard tags."""
        ctx = parser.parse("yesterday", REF)
        tags = ctx.to_tags()
        # No tags that would conflict with existing KnowledgeEngine conventions
        assert "entity_property" not in tags
        assert "group_slot" not in tags
        assert "derived" not in tags

    def test_full_enrichment_example(self, parser):
        """Full enrichment flow: parse -> metadata -> tags ready for store_memory."""
        text = "I started my new job last Monday."
        ctx = parser.parse(text, REF)
        assert ctx is not None

        # Would be called as:
        # knowledge.store_memory(
        #     subject="user",
        #     category="life_event",
        #     attribute="job_start",
        #     value="started new job",
        #     tags=["user_fact"] + ctx.to_tags(),
        #     metadata=ctx.to_metadata(),
        # )
        meta = ctx.to_metadata()
        tags = ctx.to_tags()

        assert ctx.tense == TemporalTense.PAST
        assert ctx.temporal_type == TemporalType.PAST_NAMED_DAY
        assert "temporal" in tags
        assert "past" in tags
        assert "resolved_date" in meta
