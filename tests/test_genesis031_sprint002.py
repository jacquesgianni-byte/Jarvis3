"""
Tests for Genesis-031 Sprint-002: Temporal Memory Integration

Covers:
    - MemorySkill.remember() with temporal metadata
    - TemporalRecallEngine.detect_query()
    - TemporalRecallEngine.answer()
    - Full round-trip: store with temporal -> recall when-query
    - Non-temporal memories unaffected
    - KnowledgeEngine metadata preservation
"""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
from core.conversation.temporal_recall_engine import (
    TemporalRecallEngine,
    TemporalQuery,
    TemporalAnswer,
)
from core.conversation.temporal_parser import TemporalParser, TemporalContext, TemporalType, TemporalTense


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REF = date(2026, 7, 29)


@pytest.fixture
def parser() -> TemporalParser:
    return TemporalParser()


@pytest.fixture
def recall() -> TemporalRecallEngine:
    return TemporalRecallEngine()


def _make_record(value: str, metadata: dict = None, attribute: str = "event"):
    r = MagicMock()
    r.value = value
    r.attribute = attribute
    r.subject = "user"
    r.metadata = metadata or {}
    r.tags = ["user_fact"]
    return r


def _make_knowledge(records: list):
    k = MagicMock()
    k.search_memory.return_value = records
    k.recall_memory.return_value = None
    k.store_memory.return_value = MagicMock()
    k.list_memories.return_value = []
    return k


# ===========================================================================
# TemporalRecallEngine -- detect_query
# ===========================================================================

class TestDetectQuery:

    def test_when_did_i_start(self, recall):
        result = recall.detect_query("When did I start my new job?")
        assert result is not None
        assert isinstance(result, TemporalQuery)

    def test_when_did_i_buy(self, recall):
        result = recall.detect_query("When did I buy my car?")
        assert result is not None

    def test_when_did_i_move(self, recall):
        result = recall.detect_query("When did I move?")
        assert result is not None

    def test_what_day_did_i(self, recall):
        result = recall.detect_query("What day did I start my job?")
        assert result is not None

    def test_what_date_did_i(self, recall):
        result = recall.detect_query("What date did I buy my car?")
        assert result is not None

    def test_non_temporal_query_none(self, recall):
        assert recall.detect_query("How old is Leo?") is None

    def test_plain_statement_none(self, recall):
        assert recall.detect_query("I started my job last Monday.") is None

    def test_empty_none(self, recall):
        assert recall.detect_query("") is None

    def test_search_hint_extracted(self, recall):
        result = recall.detect_query("When did I start my new job?")
        assert result is not None
        assert result.search_hint != ""
        assert len(result.search_hint) > 0


# ===========================================================================
# TemporalRecallEngine -- answer
# ===========================================================================

class TestAnswer:

    def test_found_with_resolved_date(self, recall):
        record = _make_record(
            "started new job",
            metadata={
                "resolved_date": "2026-07-27",
                "temporal_expression": "last Monday",
                "temporal_tense": "past",
            }
        )
        k = _make_knowledge([record])
        query = TemporalQuery(raw_text="When did I start my job?", search_hint="start job")
        result = recall.answer(query, k)
        assert result.found is True
        assert "2026-07-27" in result.resolved_date or "Monday" in result.answer

    def test_not_found_returns_graceful(self, recall):
        k = _make_knowledge([])
        query = TemporalQuery(raw_text="When did I buy my car?", search_hint="buy car")
        result = recall.answer(query, k)
        assert result.found is False
        assert result.answer != ""

    def test_record_without_metadata_not_returned(self, recall):
        record = _make_record("started job", metadata={})
        k = _make_knowledge([record])
        query = TemporalQuery(raw_text="When did I start?", search_hint="start")
        result = recall.answer(query, k)
        assert result.found is False

    def test_answer_contains_date(self, recall):
        record = _make_record(
            "bought car",
            metadata={"resolved_date": "2026-07-28", "temporal_expression": "yesterday"}
        )
        k = _make_knowledge([record])
        query = TemporalQuery(raw_text="When did I buy my car?", search_hint="buy car")
        result = recall.answer(query, k)
        assert result.found is True
        assert "2026" in result.answer or "July" in result.answer

    def test_answer_contains_original_expression(self, recall):
        record = _make_record(
            "moved house",
            metadata={
                "resolved_date": "2026-07-08",
                "temporal_expression": "3 weeks ago",
            }
        )
        k = _make_knowledge([record])
        query = TemporalQuery(raw_text="When did I move?", search_hint="move")
        result = recall.answer(query, k)
        assert result.found is True
        assert "3 weeks ago" in result.answer or "2026" in result.answer


# ===========================================================================
# MemorySkill temporal enrichment
# ===========================================================================

class TestMemorySkillTemporal:

    def test_remember_with_temporal_metadata_calls_store(self):
        from core.skills.memory import MemorySkill
        k = MagicMock()
        k.store_memory.return_value = MagicMock()
        skill = MemorySkill(k)

        metadata = {"resolved_date": "2026-07-27", "temporal_expression": "last Monday"}
        tags = ["temporal", "past"]

        skill.remember("job_start", "started new job", temporal_metadata=metadata, temporal_tags=tags)

        k.store_memory.assert_called_once()
        call_kwargs = k.store_memory.call_args.kwargs
        # Temporal info encoded as tags (KnowledgeEngine has no metadata param)
        assert "temporal" in call_kwargs["tags"]
        assert "past" in call_kwargs["tags"]
        assert "user_fact" in call_kwargs["tags"]
        assert any("resolved:" in t for t in call_kwargs["tags"])

    def test_remember_without_temporal_unchanged(self):
        from core.skills.memory import MemorySkill
        k = MagicMock()
        k.store_memory.return_value = MagicMock()
        skill = MemorySkill(k)

        skill.remember("name", "Gianni")

        k.store_memory.assert_called_once()
        call_kwargs = k.store_memory.call_args.kwargs
        assert call_kwargs.get("metadata") is None
        assert "user_fact" in call_kwargs["tags"]

    def test_remember_returns_response(self):
        from core.skills.memory import MemorySkill
        k = MagicMock()
        k.store_memory.return_value = MagicMock()
        skill = MemorySkill(k)
        result = skill.remember("event", "started job", temporal_metadata={"resolved_date": "2026-07-27"})
        assert result.success is True


# ===========================================================================
# Round-trip integration
# ===========================================================================

class TestRoundTrip:
    """
    Full flow: parse temporal expression -> enrich metadata -> recall.
    Uses in-memory store to simulate KnowledgeEngine.
    """

    def _make_store_engine(self):
        """Simple dict-backed KnowledgeEngine mock."""
        _store: list = []

        def store_memory(subject, category, attribute, value, tags=None, metadata=None):
            r = MagicMock()
            r.subject = subject
            r.attribute = attribute
            r.value = value
            r.tags = tags or []
            r.metadata = metadata or {}
            _store.append(r)
            return r

        def search_memory(query=None, subject=None, limit=10, **kwargs):
            results = []
            for r in _store:
                if query and (query.lower() in r.value.lower() or query.lower() in r.attribute.lower()):
                    results.append(r)
            return results[:limit] if results else _store[:limit]

        k = MagicMock()
        k.store_memory.side_effect = store_memory
        k.search_memory.side_effect = search_memory
        return k

    def test_store_and_recall_job_start(self):
        parser = TemporalParser()
        recall = TemporalRecallEngine()
        k = self._make_store_engine()

        # Parse "I started my new job last Monday"
        text = "I started my new job last Monday"
        ctx = parser.parse(text, REF)
        assert ctx is not None

        # Store with temporal metadata
        k.store_memory(
            subject="user",
            category="personal",
            attribute="job_start",
            value="started new job",
            tags=["user_fact"] + ctx.to_tags(),
            metadata=ctx.to_metadata(),
        )

        # Recall "When did I start my job?"
        query = recall.detect_query("When did I start my job?")
        assert query is not None
        answer = recall.answer(query, k)
        assert answer.found is True
        assert answer.resolved_date is not None

    def test_store_and_recall_car_purchase(self):
        parser = TemporalParser()
        recall = TemporalRecallEngine()
        k = self._make_store_engine()

        ctx = parser.parse("I bought a new car yesterday", REF)
        assert ctx is not None
        assert ctx.resolved_date == REF - timedelta(days=1)

        k.store_memory(
            subject="user",
            category="personal",
            attribute="car_purchase",
            value="bought new car",
            tags=["user_fact"] + ctx.to_tags(),
            metadata=ctx.to_metadata(),
        )

        query = recall.detect_query("When did I buy my car?")
        assert query is not None
        answer = recall.answer(query, k)
        assert answer.found is True

    def test_store_and_recall_house_move(self):
        parser = TemporalParser()
        recall = TemporalRecallEngine()
        k = self._make_store_engine()

        ctx = parser.parse("I moved house three weeks ago", REF)
        assert ctx is not None

        k.store_memory(
            subject="user",
            category="personal",
            attribute="house_move",
            value="moved house",
            tags=["user_fact"] + ctx.to_tags(),
            metadata=ctx.to_metadata(),
        )

        query = recall.detect_query("When did I move?")
        answer = recall.answer(query, k)
        assert answer.found is True

    def test_non_temporal_memory_unaffected(self):
        """Memories without temporal context store and retrieve normally."""
        from core.skills.memory import MemorySkill
        k = self._make_store_engine()
        skill = MemorySkill(k)

        # Store without temporal
        result = skill.remember("name", "Gianni")
        assert result.success is True

        # Verify no temporal tags added
        call_kwargs = k.store_memory.call_args.kwargs
        assert "temporal" not in call_kwargs.get("tags", [])
        assert call_kwargs.get("metadata") is None
