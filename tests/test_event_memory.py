"""
Tests for EVENT memory architecture.

Covers:
  - FactType.EVENT exists
  - FactExtractor structural detection (no verb vocabulary)
  - TemporalParser is the authority on temporal expressions
  - Questions, commands, intent/modal correctly excluded
  - KnowledgeEngine expired-record lifecycle fix
  - EVENT stored with category=event, expires_at, temporal tags
  - Expired events invisible to search and recall
  - Personal facts (expires_at=None) unaffected
  - Retention period sourced from config, not hard-coded
  - Generic detection: sentences never explicitly programmed
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_extractor():
    from core.conversation.fact_extractor import FactExtractor
    from core.conversation.temporal_parser import TemporalParser
    return FactExtractor(temporal_parser=TemporalParser())


def _make_extractor_no_parser():
    from core.conversation.fact_extractor import FactExtractor
    return FactExtractor()


def _make_engine(tmp_path: Path):
    from core.knowledge_engine.engine import KnowledgeEngine
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    repo = JsonKnowledgeRepository(path=str(tmp_path / "knowledge.json"))
    return KnowledgeEngine(storage=repo)


def _event_facts(text: str):
    from core.conversation.fact_extractor import FactType
    ex = _make_extractor()
    return [f for f in ex.extract(text) if f.fact_type == FactType.EVENT]


# ── FactType.EVENT exists ─────────────────────────────────────────────────────

def test_facttype_event_exists():
    from core.conversation.fact_extractor import FactType
    assert hasattr(FactType, "EVENT")
    assert FactType.EVENT.name == "EVENT"


# ── Structural detection — target sentences ───────────────────────────────────

class TestEventDetectionTargets:
    """These sentences must produce EVENT facts."""

    def test_met_client_this_morning(self):
        facts = _event_facts("I met the client this morning.")
        assert facts, "Should detect EVENT"
        assert facts[0].subject == "user"

    def test_finished_report_last_night(self):
        facts = _event_facts("I finished the report last night.")
        assert facts

    def test_we_had_meeting_yesterday(self):
        facts = _event_facts("We had a meeting yesterday.")
        assert facts

    def test_starting_new_job_next_week(self):
        """bare 'on Monday' not handled by TemporalParser (ambiguous which Monday).
        'next week' IS handled and is unambiguous."""
        facts = _event_facts("I'm starting a new job next week.")
        assert facts

    def test_signed_contract_yesterday(self):
        facts = _event_facts("I signed a contract yesterday.")
        assert facts

    def test_saw_john_yesterday(self):
        facts = _event_facts("I saw John at the pub yesterday.")
        assert facts

    def test_bought_printer_last_month(self):
        facts = _event_facts("I bought a Bambu Lab A1 Mini last month.")
        assert facts

    def test_was_angry_yesterday(self):
        """Past copula 'was' counts as past form."""
        facts = _event_facts("I was really angry with my manager yesterday.")
        assert facts

    def test_demolished_shed_last_saturday(self):
        """
        THE KEY TEST: 'demolished' was never programmed.
        Structural detection must find it generically.
        """
        facts = _event_facts("I demolished the old shed last Saturday.")
        assert facts, (
            "Generic structural detection must find 'demolished' without "
            "a verb vocabulary. This is the standard we hold it to."
        )


# ── Structural detection — correct exclusions ─────────────────────────────────

class TestEventDetectionExclusions:

    def test_question_mark_excluded(self):
        assert not _event_facts("What time is the meeting?")

    def test_question_word_start_excluded(self):
        assert not _event_facts("When did I meet the client?")

    def test_command_excluded(self):
        assert not _event_facts("Remember that I met the client this morning.")

    def test_intent_modal_need_to(self):
        assert not _event_facts("I need to call John tomorrow.")

    def test_intent_modal_going_to(self):
        assert not _event_facts("I'm going to deploy tomorrow.")

    def test_no_temporal_expression_excluded(self):
        """Without temporal anchor: not recallable, not stored."""
        assert not _event_facts("I finished the report.")

    def test_preference_no_temporal_excluded(self):
        assert not _event_facts("I love coffee.")

    def test_ordinary_chat_excluded(self):
        assert not _event_facts("Hello Jarvis.")

    def test_personal_fact_not_event(self):
        """'My name is Gianni' should not be an EVENT."""
        assert not _event_facts("My name is Gianni.")

    def test_no_temporal_parser_returns_empty(self):
        """All existing FactExtractor() callers get no EVENT facts."""
        from core.conversation.fact_extractor import FactType
        ex = _make_extractor_no_parser()
        facts = [f for f in ex.extract("I met the client this morning.")
                 if f.fact_type == FactType.EVENT]
        assert not facts


# ── TemporalParser authority ──────────────────────────────────────────────────

class TestTemporalParserAuthority:
    def test_temporal_ctx_in_payload(self):
        """TemporalContext is stored in metadata — no second parse needed."""
        facts = _event_facts("I met the client this morning.")
        assert facts
        assert "temporal_ctx" in facts[0].metadata
        ctx = facts[0].metadata["temporal_ctx"]
        assert "resolved_date" in ctx
        assert ctx.get("time_of_day_slot") == "morning"

    def test_yesterday_resolved_date(self):
        from datetime import date, timedelta
        facts = _event_facts("I finished the report last night.")
        assert facts
        ctx = facts[0].metadata["temporal_ctx"]
        expected = (date.today() - timedelta(days=1)).isoformat()
        assert ctx.get("resolved_date") == expected


# ── KnowledgeEngine expired-record lifecycle fix ──────────────────────────────

class TestExpiredRecordLifecycleFix:
    def test_expired_event_not_resurrected(self, tmp_path):
        """
        If an event expires, a new statement with the same attribute
        must create a fresh record, not update the expired one.
        """
        k = _make_engine(tmp_path)
        past = datetime.now(UTC) - timedelta(days=1)

        # Store first event, already expired
        k.store_memory(
            subject="user", category="event",
            attribute="met client", value="I met the client last week",
            expires_at=past,
        )
        # Verify it's expired and invisible
        assert k.recall_memory("user", "met client") is None

        # Store second event — should create new, not resurrect
        k.store_memory(
            subject="user", category="event",
            attribute="met client", value="I met the client this morning",
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", "resolved:2026-08-15"],
        )
        record = k.recall_memory("user", "met client")
        assert record is not None
        assert "this morning" in record.value
        assert "resolved:2026-08-15" in record.tags

    def test_personal_fact_unaffected(self, tmp_path):
        """Personal facts (expires_at=None) must be unaffected by lifecycle fix."""
        k = _make_engine(tmp_path)
        k.store_memory(subject="user", category="personal",
                       attribute="name", value="Gianni")
        k.store_memory(subject="user", category="personal",
                       attribute="name", value="Gianni Updated")
        record = k.recall_memory("user", "name")
        assert record is not None
        assert record.value == "Gianni Updated"


# ── EVENT stored correctly in KnowledgeEngine ────────────────────────────────

class TestEventStoredCorrectly:
    def test_event_category(self, tmp_path):
        k = _make_engine(tmp_path)
        k.store_memory(
            subject="user", category="event",
            attribute="met client morning",
            value="I met the client this morning",
            confidence=0.65, importance=0.4,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            tags=["user_event", "resolved:2026-08-15", "tod:morning"],
        )
        results = k.search_memory("client", subject="user")
        assert results
        assert results[0].category == "event"

    def test_event_expires_correctly(self, tmp_path):
        k = _make_engine(tmp_path)
        past = datetime.now(UTC) - timedelta(seconds=1)
        k.store_memory(
            subject="user", category="event",
            attribute="met client", value="I met the client this morning",
            expires_at=past,
        )
        # Both search and recall must return nothing
        assert k.recall_memory("user", "met client") is None
        results = k.search_memory("client", subject="user")
        assert not any(r.attribute == "met client" for r in results)

    def test_event_below_personal_importance(self, tmp_path):
        """Events (importance=0.4) score below personal facts (importance=0.8+)."""
        k = _make_engine(tmp_path)
        k.store_memory(subject="user", category="personal",
                       attribute="name", value="Gianni", importance=1.0)
        k.store_memory(subject="user", category="event",
                       attribute="met someone", value="I met someone yesterday",
                       importance=0.4,
                       expires_at=datetime.now(UTC) + timedelta(days=30),
                       tags=["user_event"])
        results = k.search_memory("gianni met", subject="user", limit=10)
        # Personal fact should rank higher than event
        personal = next((r for r in results if r.category == "personal"), None)
        event = next((r for r in results if r.category == "event"), None)
        if personal and event:
            personal_idx = results.index(personal)
            event_idx = results.index(event)
            assert personal_idx < event_idx, "Personal fact must rank above event"


# ── Retention period from config ──────────────────────────────────────────────

def test_retention_from_config():
    """EVENT_MEMORY_RETENTION_DAYS comes from config, not a hard-coded literal."""
    from core.config import EVENT_MEMORY_RETENTION_DAYS
    assert isinstance(EVENT_MEMORY_RETENTION_DAYS, int)
    assert EVENT_MEMORY_RETENTION_DAYS > 0


# ── Regression: TemporalRecallEngine query pattern coverage ──────────────────

class TestTemporalRecallQueryPatterns:
    """
    Regression for missing 'what did I [verb]' pattern in _WHEN_PATTERNS.
    Root cause: detect_query() returned None for 'What did I do last Saturday?'
    despite the event being correctly stored with resolved: tag.
    Fix: added generic r'\bwhat\s+did\s+i\s+(.+?)\??$' pattern.
    """

    def setup_method(self):
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        self.engine = TemporalRecallEngine()

    def test_what_did_i_do_last_saturday(self):
        q = self.engine.detect_query("What did I do last Saturday?")
        assert q is not None, "Should detect temporal query"
        assert q.search_hint

    def test_what_did_i_finish_last_night(self):
        q = self.engine.detect_query("What did I finish last night?")
        assert q is not None

    def test_what_did_i_sign_yesterday(self):
        q = self.engine.detect_query("What did I sign yesterday?")
        assert q is not None

    def test_what_did_i_do_this_morning(self):
        q = self.engine.detect_query("What did I do this morning?")
        assert q is not None

    def test_what_did_i_demolished(self):
        """The exact Test B query that was failing."""
        q = self.engine.detect_query("What did I do last Saturday?")
        assert q is not None
        assert "saturday" in q.search_hint.lower() or "last" in q.search_hint.lower()

    def test_existing_when_did_i_still_works(self):
        """Existing patterns must be unaffected."""
        q = self.engine.detect_query("When did I meet the client?")
        assert q is not None

    def test_end_to_end_what_did_i_recall(self, tmp_path):
        """
        Full end-to-end: store event, recall with 'What did I do'.
        Proves the complete pipeline works for Test B scenario.
        """
        from core.skills.memory import MemorySkill
        from core.conversation.temporal_parser import TemporalParser
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        k = _make_engine(tmp_path)
        skill = MemorySkill(k, temporal_parser=TemporalParser())
        recall = TemporalRecallEngine()

        # Store the event (simulating what MemorySkill.remember() does)
        skill.remember("demolished old shed", "I demolished the old shed last Saturday")

        # Recall with the 'what did I' pattern
        query = recall.detect_query("What did I do last Saturday?")
        assert query is not None, "detect_query must return a query"

        answer = recall.answer(query, k)
        assert answer.found, (
            f"Should find the demolished shed event. Answer: {answer.answer}"
        )
