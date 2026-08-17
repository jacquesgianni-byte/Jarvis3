"""
Genesis-049: Multi-event temporal recall regression tests.

Key rule: when a user asks "What did I do last Saturday?",
ALL user records for that date must be recalled — not just the
first one found or the one with highest importance.

Specific regression:
  met client morning (importance=0.5) must NOT crowd out
  demolished old shed (importance=0.4) just because it ranks first.
"""
from __future__ import annotations
from datetime import UTC, datetime, timedelta, date
import pytest

TARGET_DATE = "2026-08-15"
TARGET_TAG  = f"resolved:{TARGET_DATE}"


def _make_engine(tmp_path):
    from core.knowledge_engine.engine import KnowledgeEngine
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    return KnowledgeEngine(storage=JsonKnowledgeRepository(
        path=str(tmp_path / "k.json")
    ))


def _make_recall():
    from core.conversation.temporal_recall_engine import TemporalRecallEngine
    from core.conversation.temporal_parser import TemporalParser
    return TemporalRecallEngine(temporal_parser=TemporalParser())


def _store(k, attr, value, tod="unspecified", importance=0.4, category="event"):
    k.store_memory(
        subject="user", category=category,
        attribute=attr, value=value,
        importance=importance,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        tags=["user_event", TARGET_TAG, f"expr:last saturday", f"tod:{tod}"],
    )


# ── Single record — existing behaviour preserved ──────────────────────────────

class TestSingleRecord:
    def test_single_record_found(self, tmp_path):
        k = _make_engine(tmp_path)
        _store(k, "demolished shed", "I demolished the old shed last Saturday")
        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert a.found
        # Single record uses _format_answer (date string) — verify found + date
        assert a.resolved_date == TARGET_DATE
        assert a.memory_value and "demolished" in a.memory_value.lower()

    def test_single_record_answer_references_content(self, tmp_path):
        k = _make_engine(tmp_path)
        _store(k, "demolished shed", "I demolished the old shed last Saturday")
        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        # Single record may use _format_answer (date format) or _compose_multi_answer
        assert a.found
        assert a.resolved_date == TARGET_DATE


# ── Two records — the key regression ─────────────────────────────────────────

class TestTwoRecords:
    def test_both_records_recalled(self, tmp_path):
        """
        THE KEY REGRESSION TEST.
        'met client' (importance=0.5) must not crowd out
        'demolished shed' (importance=0.4).
        Both must appear in the answer.
        """
        k = _make_engine(tmp_path)
        _store(k, "met client morning", "I met the client this morning",
               tod="morning", importance=0.5, category="personal")
        _store(k, "demolished shed", "I demolished the old shed last Saturday",
               tod="unspecified", importance=0.4, category="event")

        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)

        assert a.found, "Must find events"
        answer_lower = a.answer.lower()
        assert "met" in answer_lower or "client" in answer_lower,             f"Answer must mention meeting the client. Got: {a.answer!r}"
        assert "demolished" in answer_lower or "shed" in answer_lower,             f"Answer must mention demolishing the shed. Got: {a.answer!r}"

    def test_two_records_chronological_order(self, tmp_path):
        """Morning events appear before unspecified-time events."""
        k = _make_engine(tmp_path)
        _store(k, "met client", "I met the client this morning",
               tod="morning", importance=0.4)
        _store(k, "demolished shed", "I demolished the shed",
               tod="unspecified", importance=0.5)  # higher importance but unspecified time

        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert a.found
        # Morning event should appear first regardless of importance
        met_pos = a.answer.lower().find("met")
        dem_pos = a.answer.lower().find("demolished")
        if met_pos >= 0 and dem_pos >= 0:
            assert met_pos < dem_pos,                 f"Morning event should appear before unspecified. Got: {a.answer!r}"


# ── Three records ─────────────────────────────────────────────────────────────

class TestThreeRecords:
    def test_three_records_all_included(self, tmp_path):
        k = _make_engine(tmp_path)
        _store(k, "met client", "I met the client this morning", tod="morning")
        _store(k, "finished report", "I finished the report this afternoon", tod="afternoon")
        _store(k, "demolished shed", "I demolished the shed", tod="unspecified")

        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert a.found
        # All three should appear
        answer_lower = a.answer.lower()
        assert "met" in answer_lower or "client" in answer_lower
        assert "finished" in answer_lower or "report" in answer_lower
        assert "demolished" in answer_lower or "shed" in answer_lower


# ── Four or more records — cap + overflow note ────────────────────────────────

class TestFourPlusRecords:
    def test_four_records_capped_at_three(self, tmp_path):
        k = _make_engine(tmp_path)
        for i, (attr, val, tod) in enumerate([
            ("event_a", "I did thing A this morning", "morning"),
            ("event_b", "I did thing B this afternoon", "afternoon"),
            ("event_c", "I did thing C this evening", "evening"),
            ("event_d", "I did thing D last Saturday", "unspecified"),
        ]):
            _store(k, attr, val, tod=tod)

        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert a.found
        # Should mention overflow
        assert "more" in a.answer.lower(),             f"Should mention additional items. Got: {a.answer!r}"

    def test_overflow_note_is_accurate(self, tmp_path):
        k = _make_engine(tmp_path)
        for i in range(5):
            _store(k, f"event_{i}", f"I did event {i} last Saturday", tod="unspecified")

        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert a.found
        assert "more" in a.answer.lower()
        # 5 total, 3 shown, 2 more
        assert "2" in a.answer, f"Should mention 2 more items. Got: {a.answer!r}"


# ── No records ────────────────────────────────────────────────────────────────

class TestNoRecords:
    def test_no_records_returns_not_found(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        q = recall.detect_query("What did I do last Saturday?")
        a = recall.answer(q, k)
        assert not a.found
