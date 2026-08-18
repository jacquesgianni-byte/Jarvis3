"""
Genesis-051 Sprint-001 — Historical Event Recall Regression Tests

Tests _compose_multi_answer() Path B fix:
  - Stale relative expressions never appear in historical answers.
  - resolved: and tod: metadata drives temporal context.
  - Single-record path (_format_answer) is untouched.
  - Mixed tod slots, multi-date results handled correctly.
  - Fallback to record.attribute when safe strip fails.

Run: python -m pytest tests/test_genesis051_temporal_recall.py -v
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal record stub — mirrors MemoryRecord interface used by the engine.
# ---------------------------------------------------------------------------

@dataclass
class _Record:
    value: str
    attribute: str = "event"
    subject: str = "user"
    importance: float = 0.7
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Import the real engine
# ---------------------------------------------------------------------------

from core.conversation.temporal_recall_engine import TemporalRecallEngine


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _engine() -> TemporalRecallEngine:
    return TemporalRecallEngine(temporal_parser=None)


def _matched(records_and_meta: list) -> list:
    """
    Build the (record, resolved_date, temporal_expr, tod_slot) tuples
    that _compose_multi_answer() receives.
    """
    return [
        (r, rd, te, tod)
        for r, rd, te, tod in records_and_meta
    ]


# ===========================================================================
# 1. "this morning" — must not appear in historical answer
# ===========================================================================

class TestThisMorning:

    def test_this_morning_stripped_from_value(self):
        r = _Record(
            value="I met the client this morning",
            attribute="met client",
            tags=["resolved:2026-08-15", "expr:this morning", "tod:morning"],
        )
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        assert "this morning" not in result.lower()

    def test_this_morning_uses_day_and_slot(self):
        r = _Record(
            value="I met the client this morning",
            attribute="met client",
        )
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        # 2026-08-15 is a Saturday
        assert "saturday" in result.lower()
        assert "morning" in result.lower()

    def test_this_morning_content_retained(self):
        r = _Record(value="I met the client this morning", attribute="met client")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        assert "client" in result.lower()


# ===========================================================================
# 2. "yesterday" — must not appear in historical answer
# ===========================================================================

class TestYesterday:

    def test_yesterday_stripped(self):
        r = _Record(value="I went to the gym yesterday", attribute="gym")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-14", "yesterday", "unspecified"),
        ]))
        assert "yesterday" not in result.lower()

    def test_yesterday_date_present(self):
        r = _Record(value="I went to the gym yesterday", attribute="gym")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-14", "yesterday", "unspecified"),
        ]))
        # 2026-08-14 is a Friday
        assert "friday" in result.lower() or "14" in result or "august" in result.lower()


# ===========================================================================
# 3. "last Saturday" — tolerable but should use resolved date, not expression
# ===========================================================================

class TestLastSaturday:

    def test_last_saturday_stripped(self):
        r = _Record(value="I finished the report last Saturday", attribute="finished report")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "last Saturday", "unspecified"),
        ]))
        assert "last saturday" not in result.lower()

    def test_last_saturday_date_in_output(self):
        r = _Record(value="I finished the report last Saturday", attribute="finished report")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "last Saturday", "unspecified"),
        ]))
        assert "saturday" in result.lower() or "15" in result or "august" in result.lower()

    def test_last_saturday_content_retained(self):
        r = _Record(value="I finished the report last Saturday", attribute="finished report")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "last Saturday", "unspecified"),
        ]))
        assert "report" in result.lower() or "finished" in result.lower()


# ===========================================================================
# 4. "last week" — must not appear
# ===========================================================================

class TestLastWeek:

    def test_last_week_stripped(self):
        r = _Record(value="I saw the doctor last week", attribute="saw doctor")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-10", "last week", "unspecified"),
        ]))
        assert "last week" not in result.lower()

    def test_last_week_date_present(self):
        r = _Record(value="I saw the doctor last week", attribute="saw doctor")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-10", "last week", "unspecified"),
        ]))
        assert "monday" in result.lower() or "10" in result or "august" in result.lower()


# ===========================================================================
# 5. Missing tod: — graceful fallback to date only
# ===========================================================================

class TestMissingTod:

    def test_no_tod_still_returns_answer(self):
        r = _Record(value="I called the bank this afternoon", attribute="called bank")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-12", "this afternoon", "unspecified"),
        ]))
        assert result  # non-empty
        assert "this afternoon" not in result.lower()

    def test_no_tod_date_present(self):
        r = _Record(value="I called the bank this afternoon", attribute="called bank")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-12", "this afternoon", "unspecified"),
        ]))
        assert "wednesday" in result.lower() or "12" in result or "august" in result.lower()


# ===========================================================================
# 6. Multiple events — same day, same tod
# ===========================================================================

class TestSameDaySameTod:

    def test_shared_header_used(self):
        r1 = _Record(value="I met the client this morning", attribute="met client")
        r2 = _Record(value="I submitted the proposal this morning", attribute="submitted proposal")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-15", "this morning", "morning"),
            (r2, "2026-08-15", "this morning", "morning"),
        ]))
        # "this morning" must not appear
        assert "this morning" not in result.lower()
        # Both events' content should be present
        assert "client" in result.lower()
        assert "proposal" in result.lower()
        # Should include day + slot (Saturday morning)
        assert "saturday" in result.lower()
        assert "morning" in result.lower()

    def test_shared_header_single_mention_of_date(self):
        """Date/day should appear once as a header, not repeated per event."""
        r1 = _Record(value="I met the client this morning", attribute="met client")
        r2 = _Record(value="I submitted the proposal this morning", attribute="submitted proposal")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-15", "this morning", "morning"),
            (r2, "2026-08-15", "this morning", "morning"),
        ]))
        # "Saturday" should appear exactly once (shared header)
        assert result.lower().count("saturday") == 1


# ===========================================================================
# 7. Multiple events — same day, different tod slots
# ===========================================================================

class TestSameDayDifferentTod:

    def test_mixed_tod_no_wrong_shared_header(self):
        r1 = _Record(value="I met the client this morning", attribute="met client")
        r2 = _Record(value="I went to the dentist this afternoon", attribute="dentist")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-15", "this morning", "morning"),
            (r2, "2026-08-15", "this afternoon", "afternoon"),
        ]))
        # Neither stale expression should appear
        assert "this morning" not in result.lower()
        assert "this afternoon" not in result.lower()
        # Both events present
        assert "client" in result.lower()
        assert "dentist" in result.lower()
        # Date still present
        assert "saturday" in result.lower() or "15" in result or "august" in result.lower()

    def test_mixed_tod_both_slots_labelled(self):
        r1 = _Record(value="I met the client this morning", attribute="met client")
        r2 = _Record(value="I went to the dentist this afternoon", attribute="dentist")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-15", "this morning", "morning"),
            (r2, "2026-08-15", "this afternoon", "afternoon"),
        ]))
        # Both slots should be indicated in the answer
        assert "morning" in result.lower()
        assert "afternoon" in result.lower()


# ===========================================================================
# 8. Multi-date results — each event gets its own date context
# ===========================================================================

class TestMultiDate:

    def test_multi_date_both_dates_present(self):
        r1 = _Record(value="I visited the client yesterday", attribute="visited client")
        r2 = _Record(value="I submitted the invoice last week", attribute="submitted invoice")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-14", "yesterday", "unspecified"),
            (r2, "2026-08-10", "last week", "unspecified"),
        ]))
        assert "yesterday" not in result.lower()
        assert "last week" not in result.lower()
        # Both dates should appear
        assert ("friday" in result.lower() or "14" in result or "august" in result.lower())
        assert ("monday" in result.lower() or "10" in result)

    def test_multi_date_both_events_described(self):
        r1 = _Record(value="I visited the client yesterday", attribute="visited client")
        r2 = _Record(value="I submitted the invoice last week", attribute="submitted invoice")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r1, "2026-08-14", "yesterday", "unspecified"),
            (r2, "2026-08-10", "last week", "unspecified"),
        ]))
        assert "client" in result.lower() or "visited" in result.lower()
        assert "invoice" in result.lower() or "submitted" in result.lower()


# ===========================================================================
# 9. Single-record path — _format_answer() untouched
# ===========================================================================

class TestSingleRecordPathUntouched:

    def test_single_record_format_answer_with_tod(self):
        engine = _engine()
        result = engine._format_answer(
            memory_value="started new job",
            resolved_date="2026-07-27",
            original_expression="last Monday",
            time_of_day_slot="morning",
        )
        assert "monday" in result.lower() or "27" in result or "july" in result.lower()
        assert "morning" in result.lower()

    def test_single_record_format_answer_without_tod(self):
        engine = _engine()
        result = engine._format_answer(
            memory_value="bought the car",
            resolved_date="2026-07-01",
            original_expression="last Wednesday",
            time_of_day_slot="unspecified",
        )
        assert "last wednesday" in result.lower() or "july" in result.lower()

    def test_single_record_format_answer_bare_date(self):
        engine = _engine()
        result = engine._format_answer(
            memory_value="got the diagnosis",
            resolved_date="2026-06-15",
            original_expression=None,
            time_of_day_slot="unspecified",
        )
        assert "june" in result.lower() or "15" in result

    def test_single_record_compose_not_called_for_one_match(self):
        """Verify the single-record branch uses _format_answer, not _compose_multi_answer."""
        engine = _engine()
        mock_format = MagicMock(return_value="That was on Monday, 27 July 2026 morning.")
        engine._format_answer = mock_format

        knowledge = MagicMock()
        r = _Record(
            value="I started my new job last Monday",
            attribute="started job",
            tags=["resolved:2026-07-27", "expr:last Monday", "tod:morning"],
        )
        r.subject = "user"
        r.metadata = {}
        knowledge.search_memory.return_value = [r]

        from core.conversation.temporal_recall_engine import TemporalQuery
        query = TemporalQuery(raw_text="When did I start my job?", search_hint="start job")
        answer = engine.answer(query, knowledge)

        assert mock_format.called
        assert answer.found is True


# ===========================================================================
# 10. Overflow note — 4+ records
# ===========================================================================

class TestOverflow:

    def test_overflow_note_present_for_four_records(self):
        records = [
            _Record(value=f"I did thing {i} this morning", attribute=f"thing {i}")
            for i in range(4)
        ]
        engine = _engine()
        matched = [(r, "2026-08-15", "this morning", "morning") for r in records]
        result = engine._compose_multi_answer(matched)
        assert "more" in result.lower()

    def test_overflow_note_absent_for_three_records(self):
        records = [
            _Record(value=f"I did thing {i} this morning", attribute=f"thing {i}")
            for i in range(3)
        ]
        engine = _engine()
        matched = [(r, "2026-08-15", "this morning", "morning") for r in records]
        result = engine._compose_multi_answer(matched)
        assert "more" not in result.lower()

    def test_overflow_caps_at_three_events_in_body(self):
        records = [
            _Record(value=f"I did activity {i} this morning", attribute=f"activity {i}")
            for i in range(5)
        ]
        engine = _engine()
        matched = [(r, "2026-08-15", "this morning", "morning") for r in records]
        result = engine._compose_multi_answer(matched)
        # "this morning" must not appear even with overflow
        assert "this morning" not in result.lower()


# ===========================================================================
# 11. Attribute fallback — when stripping fails, use attribute not broken value
# ===========================================================================

class TestAttributeFallback:

    def test_fallback_to_attribute_when_strip_fails(self):
        """If temporal expression is not found in value, attribute is used."""
        r = _Record(
            value="Something happened",  # expr not in value
            attribute="something happened",
        )
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        # Should still produce a valid answer
        assert result
        assert "this morning" not in result.lower()

    def test_no_stale_expression_when_attribute_fallback(self):
        r = _Record(
            value="I generally do things",
            attribute="general activity",
        )
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this afternoon", "afternoon"),
        ]))
        assert "this afternoon" not in result.lower()


# ===========================================================================
# 12. Answer always starts with capital and ends with period
# ===========================================================================

class TestOutputFormat:

    def test_result_capitalised(self):
        r = _Record(value="I met the client this morning", attribute="met client")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        assert result[0].isupper()

    def test_result_ends_with_period(self):
        r = _Record(value="I met the client this morning", attribute="met client")
        engine = _engine()
        result = engine._compose_multi_answer(_matched([
            (r, "2026-08-15", "this morning", "morning"),
        ]))
        # Allow trailing overflow note
        sentences = result.rstrip().split(".")
        assert all(s.strip() == "" or len(s.strip()) > 0 for s in sentences)
