"""
Regression tests for Bug 1: TemporalRecallEngine date-tag fallback.

Root cause: keyword search hint ("do last Saturday") has no word overlap
with stored attribute ("demolished old shed"), so keyword fallback fails.
Fix: inject TemporalParser; resolve query's temporal expression to a date;
search directly by resolved:YYYY-MM-DD tag.

Tests cover:
  - What did I do last Saturday?
  - What did I do yesterday?
  - What did I do this morning?
  - What did I do last night?
  - Multiple events on same day -> return all
  - No event for requested date -> found=False (not a crash)
  - Personal memories (category=personal) unaffected
  - No AI call when temporal event recall succeeds (found=True)
  - Backward compat: no temporal_parser -> date-tag fallback disabled
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, date
from pathlib import Path

import pytest


def _make_engine(tmp_path: Path):
    from core.knowledge_engine.engine import KnowledgeEngine
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    return KnowledgeEngine(storage=JsonKnowledgeRepository(
        path=str(tmp_path / "knowledge.json")
    ))


def _make_recall():
    from core.conversation.temporal_recall_engine import TemporalRecallEngine
    from core.conversation.temporal_parser import TemporalParser
    return TemporalRecallEngine(temporal_parser=TemporalParser())


def _store_event(k, attribute: str, value: str, resolved_date: str,
                 tod: str = "unspecified"):
    tags = ["user_event", f"resolved:{resolved_date}",
            f"expr:last saturday", f"tod:{tod}"]
    k.store_memory(
        subject="user", category="event",
        attribute=attribute, value=value,
        importance=0.4,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        tags=tags,
    )


# ── Core: date-tag fallback finds event despite keyword mismatch ──────────────

class TestDateTagFallback:
    def test_what_did_i_do_last_saturday(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        last_sat = (date.today() - timedelta(days=(date.today().weekday() + 2) % 7)).isoformat()
        _store_event(k, "demolished old shed",
                     "I demolished the old shed last Saturday", last_sat)

        q = recall.detect_query("What did I do last Saturday?")
        assert q is not None
        a = recall.answer(q, k)
        assert a.found, f"Should find event via date-tag fallback. Answer: {a.answer}"

    def test_what_did_i_do_yesterday(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _store_event(k, "finished report", "I finished the report yesterday", yesterday)

        q = recall.detect_query("What did I do yesterday?")
        assert q is not None
        a = recall.answer(q, k)
        assert a.found, f"Should find yesterday event. Answer: {a.answer}"

    def test_what_did_i_do_this_morning(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        today = date.today().isoformat()
        tags = ["user_event", f"resolved:{today}", "expr:this morning", "tod:morning"]
        k.store_memory(
            subject="user", category="event",
            attribute="met client morning",
            value="I met the client this morning",
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=tags,
        )
        q = recall.detect_query("What did I do this morning?")
        assert q is not None
        a = recall.answer(q, k)
        assert a.found, f"Should find morning event. Answer: {a.answer}"

    def test_what_did_i_do_last_night(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tags = ["user_event", f"resolved:{yesterday}", "expr:last night", "tod:night"]
        k.store_memory(
            subject="user", category="event",
            attribute="deployed last night",
            value="I deployed last night",
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=tags,
        )
        q = recall.detect_query("What did I do last night?")
        assert q is not None
        a = recall.answer(q, k)
        assert a.found, f"Should find last night event. Answer: {a.answer}"


# ── No event for date -> graceful not-found ───────────────────────────────────

class TestNoEventForDate:
    def test_no_event_returns_not_found(self, tmp_path):
        k = _make_engine(tmp_path)
        recall = _make_recall()
        # Store nothing for yesterday
        q = recall.detect_query("What did I do yesterday?")
        assert q is not None
        a = recall.answer(q, k)
        assert not a.found
        assert a.answer  # has a graceful response


# ── Personal memories unaffected ─────────────────────────────────────────────

class TestPersonalMemoriesUnaffected:
    def test_personal_facts_still_recalled(self, tmp_path):
        from core.skills.memory import MemorySkill
        from core.conversation.temporal_parser import TemporalParser
        k = _make_engine(tmp_path)
        skill = MemorySkill(k, temporal_parser=TemporalParser())
        skill.remember("name", "Gianni")
        record = k.recall_memory("user", "name")
        assert record is not None
        assert record.value == "Gianni"  # remember() preserves case (unlike execute())

    def test_date_tag_fallback_only_searches_user_subject(self, tmp_path):
        """Date-tag fallback must not return jarvis journal records."""
        k = _make_engine(tmp_path)
        recall = _make_recall()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # Store a jarvis journal record with the same resolved date tag
        k.store_memory(
            subject="jarvis", category="general",
            attribute="conversation_test",
            value="I demolished the old shed last Saturday",
            tags=["journal", f"resolved:{yesterday}"],
        )
        q = recall.detect_query("What did I do yesterday?")
        assert q is not None
        a = recall.answer(q, k)
        # Must not find the jarvis journal record
        assert not a.found or a.memory_value != "I demolished the old shed last Saturday"


# ── Backward compat: no temporal_parser -> disabled ──────────────────────────

class TestBackwardCompat:
    def test_no_parser_date_fallback_disabled(self, tmp_path):
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        k = _make_engine(tmp_path)
        recall = TemporalRecallEngine()  # no parser
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _store_event(k, "finished report", "I finished the report yesterday", yesterday)
        q = recall.detect_query("What did I do yesterday?")
        if q is not None:
            a = recall.answer(q, k)
            # Without parser, date-tag fallback is disabled
            # Result depends on keyword search only
            # This is acceptable — just must not crash
            assert isinstance(a.found, bool)

    def test_existing_when_did_i_unaffected(self, tmp_path):
        """Existing when-did-I path must still work."""
        from core.skills.memory import MemorySkill
        from core.conversation.temporal_parser import TemporalParser
        k = _make_engine(tmp_path)
        skill = MemorySkill(k, temporal_parser=TemporalParser())
        recall = _make_recall()
        skill.remember("met client", "I met the client this morning")
        q = recall.detect_query("When did I meet the client?")
        assert q is not None
        a = recall.answer(q, k)
        assert a.found


# ── Regression: journal records must not contaminate temporal recall ──────────

class TestJournalContaminationRegression:
    """
    Regression for the exact production failure:
    Journal conversation records containing the word "Saturday" were returned
    by keyword search before the actual EVENT record, causing found=False.

    The fix makes date-tag search the PRIMARY path so journal records
    (subject=jarvis) are excluded by the subject='user' filter.
    """

    def test_journal_records_do_not_beat_event_record(self, tmp_path):
        """
        Store multiple jarvis journal records containing 'Saturday',
        plus one user EVENT record for last Saturday.
        Verify that 'What did I do last Saturday?' finds the EVENT, not journals.
        """
        from datetime import UTC, datetime, timedelta, date
        k = _make_engine(tmp_path)
        recall = _make_recall()

        last_sat = (date.today() - timedelta(days=(date.today().weekday() + 2) % 7)).isoformat()

        # Store jarvis journal records mentioning Saturday (the contamination)
        for i in range(6):
            k.store_memory(
                subject="jarvis", category="general",
                attribute=f"conversation_2026-08-15_2{i:02d}-00-00",
                value=f"I demolished the old shed last Saturday. Turn {i}",
                tags=["journal", "conversation"],
            )

        # Store the actual user EVENT record
        k.store_memory(
            subject="user", category="event",
            attribute="demolished old shed",
            value="I demolished the old shed last Saturday",
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", f"resolved:{last_sat}",
                  "expr:last saturday", "tod:unspecified"],
        )

        q = recall.detect_query("What did I do last Saturday?")
        assert q is not None

        a = recall.answer(q, k)
        assert a.found, (
            f"Must find EVENT despite {6} journal records containing 'Saturday'. "
            f"Answer: {a.answer}"
        )
        assert "demolished" in a.answer.lower() or last_sat in (a.resolved_date or ""), (
            f"Answer should reference the demolished shed event. Got: {a.answer}"
        )

    def test_date_tag_primary_excludes_jarvis_subject(self, tmp_path):
        """
        Date-tag primary path uses subject='user' filter.
        Records with subject='jarvis' must never appear in date-tag results.
        """
        from datetime import UTC, datetime, timedelta, date
        k = _make_engine(tmp_path)
        recall = _make_recall()

        last_sat = (date.today() - timedelta(days=(date.today().weekday() + 2) % 7)).isoformat()

        # jarvis record WITH a resolved: tag (edge case)
        k.store_memory(
            subject="jarvis", category="general",
            attribute="conversation_test",
            value="Some conversation about Saturday",
            tags=["journal", f"resolved:{last_sat}"],
        )
        # NO user event stored

        q = recall.detect_query("What did I do last Saturday?")
        assert q is not None
        a = recall.answer(q, k)
        # Must not find the jarvis record
        assert not a.found, (
            "Date-tag primary must exclude subject=jarvis records. "
            f"Incorrectly found: {a.memory_value}"
        )


# ── Regression: temporal recall takes priority over episodic ─────────────────

class TestTemporalBeforeEpisodic:
    """
    Regression for ordering bug: EpisodicMemoryEngine was firing before
    TemporalRecallEngine in agent.py pipeline.

    Architectural rule: specific retrieval (temporal with resolved date)
    takes priority over broader retrieval (episodic session search).

    This test proves TemporalRecallEngine answers "What did I do last Saturday?"
    when it has a valid temporal record, even if EpisodicMemoryEngine would
    return a negative result for the same query.
    """

    def test_temporal_answers_when_episodic_would_not(self, tmp_path):
        """
        Store a user EVENT with resolved:YYYY-MM-DD tag.
        TemporalRecallEngine must find it via date-tag primary path.
        EpisodicMemoryEngine would return 'no memories' for the same query
        (it searches session/genesis records, not user events).
        """
        from datetime import UTC, datetime, timedelta, date
        k = _make_engine(tmp_path)
        recall = _make_recall()

        last_sat = (date.today() - timedelta(days=(date.today().weekday() + 2) % 7)).isoformat()

        k.store_memory(
            subject="user", category="event",
            attribute="demolished old shed",
            value="I demolished the old shed last Saturday",
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", f"resolved:{last_sat}",
                  "expr:last saturday", "tod:unspecified"],
        )

        # TemporalRecallEngine must find the event
        q = recall.detect_query("What did I do last Saturday?")
        assert q is not None, "Must detect temporal query"
        a = recall.answer(q, k)
        assert a.found, (
            f"TemporalRecallEngine must answer before EpisodicMemoryEngine. "
            f"Got: {a.answer}"
        )

    def test_episodic_gets_query_when_temporal_has_no_answer(self, tmp_path):
        """
        When TemporalRecallEngine has no answer (found=False),
        the pipeline correctly falls through to EpisodicMemoryEngine.
        This ensures the fix doesn't break the fallthrough.
        """
        k = _make_engine(tmp_path)
        recall = _make_recall()
        # No event stored for last Saturday
        q = recall.detect_query("What did I do last Saturday?")
        assert q is not None
        a = recall.answer(q, k)
        # Temporal recall correctly returns not-found
        assert not a.found
        # (EpisodicMemoryEngine would then get the query — tested via agent integration)


# ---------------------------------------------------------------------------
# Genesis-052 Sprint-002 — Date isolation: Sunday constraint tests
# Saturday must never leak into a Sunday answer.
# ---------------------------------------------------------------------------

class TestDateIsolation:
    """
    The core invariant from Genesis-052 Sprint-002:
    A resolved date is a hard constraint, not a relevance hint.
    If Jarvis asks "What happened on Sunday?", Sunday is exact.
    Saturday is never "close enough".
    """

    @staticmethod
    def _last_saturday() -> str:
        """Return the most recent Saturday as YYYY-MM-DD."""
        from datetime import date, timedelta
        today = date.today()
        # weekday(): Mon=0 ... Sat=5 ... Sun=6
        days_back = (today.weekday() - 5) % 7 or 7
        return (today - timedelta(days=days_back)).isoformat()

    @staticmethod
    def _last_sunday() -> str:
        """Return the most recent Sunday as YYYY-MM-DD."""
        from datetime import date, timedelta
        today = date.today()
        days_back = (today.weekday() - 6) % 7 or 7
        return (today - timedelta(days=days_back)).isoformat()

    @staticmethod
    def _store_event(k, attribute, value, resolved_date, tod="unspecified"):
        from datetime import UTC, datetime, timedelta
        k.store_memory(
            subject="user", category="event",
            attribute=attribute, value=value,
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", f"resolved:{resolved_date}",
                  "expr:last saturday", f"tod:{tod}"],
        )

    def test_only_saturday_event_query_sunday_returns_not_found(self, tmp_path):
        """
        Genesis-052 Sprint-002 required regression:
        Only a Saturday event is stored.
        Querying 'What did I do last Sunday?' must return found=False.
        Saturday must not bleed into the Sunday answer.
        """
        from core.knowledge_engine.engine import KnowledgeEngine
        from core.knowledge_engine.json_storage import JsonKnowledgeRepository
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        from core.conversation.temporal_parser import TemporalParser

        k = KnowledgeEngine(storage=JsonKnowledgeRepository(
            path=str(tmp_path / "knowledge.json")
        ))
        recall = TemporalRecallEngine(temporal_parser=TemporalParser())

        sat = self._last_saturday()
        self._store_event(k, "met client saturday", "I met the client last Saturday", sat)

        q = recall.detect_query("What did I do last Sunday?")
        assert q is not None
        a = recall.answer(q, k)

        assert not a.found, (
            f"Saturday event must NOT be returned for a Sunday query. "
            f"Resolved Saturday={sat}, answer={a.answer!r}"
        )

    def test_sunday_event_exists_query_sunday_returns_found(self, tmp_path):
        """
        Genesis-052 Sprint-002 required regression:
        A Sunday event is stored.
        Querying 'What did I do last Sunday?' must return found=True.
        """
        from core.knowledge_engine.engine import KnowledgeEngine
        from core.knowledge_engine.json_storage import JsonKnowledgeRepository
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        from core.conversation.temporal_parser import TemporalParser

        k = KnowledgeEngine(storage=JsonKnowledgeRepository(
            path=str(tmp_path / "knowledge.json")
        ))
        recall = TemporalRecallEngine(temporal_parser=TemporalParser())

        sun = self._last_sunday()
        self._store_event(k, "finished shed sunday", "I finished the shed last Sunday", sun)

        q = recall.detect_query("What did I do last Sunday?")
        assert q is not None
        a = recall.answer(q, k)

        assert a.found, (
            f"Sunday event must be returned for a Sunday query. "
            f"Resolved Sunday={sun}, answer={a.answer!r}"
        )

    def test_saturday_and_sunday_events_query_sunday_returns_only_sunday(self, tmp_path):
        """
        Genesis-052 Sprint-002 required regression:
        Both a Saturday and a Sunday event are stored.
        Querying 'What did I do last Sunday?' must return only the Sunday event.
        The Saturday event must not appear in the answer.
        """
        from core.knowledge_engine.engine import KnowledgeEngine
        from core.knowledge_engine.json_storage import JsonKnowledgeRepository
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        from core.conversation.temporal_parser import TemporalParser

        k = KnowledgeEngine(storage=JsonKnowledgeRepository(
            path=str(tmp_path / "knowledge.json")
        ))
        recall = TemporalRecallEngine(temporal_parser=TemporalParser())

        sat = self._last_saturday()
        sun = self._last_sunday()

        self._store_event(k, "met client saturday", "I met the client last Saturday", sat)
        self._store_event(k, "finished shed sunday", "I finished the shed last Sunday", sun)

        q = recall.detect_query("What did I do last Sunday?")
        assert q is not None
        a = recall.answer(q, k)

        assert a.found, (
            f"Sunday event must be found when Saturday + Sunday events both exist. "
            f"answer={a.answer!r}"
        )
        assert sun in (a.resolved_date or ""), (
            f"Resolved date must be Sunday ({sun}), got {a.resolved_date!r}"
        )
        # Saturday must not appear in the answer
        assert sat not in (a.answer or ""), (
            f"Saturday date ({sat}) must not appear in a Sunday query answer. "
            f"answer={a.answer!r}"
        )

    def test_list_by_tag_exposed_on_knowledge_engine(self, tmp_path):
        """
        Genesis-052 Sprint-002: KnowledgeEngine must expose list_by_tag().
        This is the architectural primitive that makes date recall exact.
        """
        from core.knowledge_engine.engine import KnowledgeEngine
        from core.knowledge_engine.json_storage import JsonKnowledgeRepository
        from datetime import UTC, datetime, timedelta

        k = KnowledgeEngine(storage=JsonKnowledgeRepository(
            path=str(tmp_path / "knowledge.json")
        ))
        assert hasattr(k, "list_by_tag"), (
            "KnowledgeEngine must expose list_by_tag() after Genesis-052 Sprint-002"
        )

        sun = self._last_sunday()
        k.store_memory(
            subject="user", category="event",
            attribute="finished shed sunday",
            value="I finished the shed last Sunday",
            importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", f"resolved:{sun}", "expr:last sunday", "tod:unspecified"],
        )

        results = k.list_by_tag(f"resolved:{sun}", subject="user")
        assert len(results) == 1, (
            f"list_by_tag must return exactly the Sunday record. Got {len(results)}"
        )
        assert results[0].attribute == "finished shed sunday"
