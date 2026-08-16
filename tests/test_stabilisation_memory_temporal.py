"""
Stabilisation regression tests: memory temporal enrichment (Test A fix).

Verifies that event-style memory statements ("Remember that I met the client
this morning") are stored with correct temporal tags so that
TemporalRecallEngine can answer recall queries locally without AI fallback.

Acceptance criteria:
  1. "this morning" -> tod:morning tag persisted
  2. "yesterday"    -> resolved:YYYY-MM-DD tag persisted
  3. No temporal expression -> no tod: tag (no clock inference)
  4. Existing key/value memories (non-temporal) unchanged
  5. END-TO-END: TemporalRecallEngine answers without AI fallback,
     answer contains "morning"
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine(tmp_path: Path):
    """Fresh isolated KnowledgeEngine per test via tmp_path."""
    from core.knowledge_engine.engine import KnowledgeEngine
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    repo = JsonKnowledgeRepository(path=str(tmp_path / "knowledge.json"))
    return KnowledgeEngine(storage=repo)


def _make_skill(tmp_path: Path, with_parser: bool = True):
    """Fresh isolated KnowledgeEngine + MemorySkill per test."""
    from core.skills.memory import MemorySkill
    from core.conversation.temporal_parser import TemporalParser
    k = _make_engine(tmp_path)
    parser = TemporalParser() if with_parser else None
    skill = MemorySkill(k, temporal_parser=parser)
    return skill, k


def _tags(k, query: str) -> list:
    records = k.search_memory(query, subject="user")
    assert records, f"No memory record found for query: {query!r}"
    return getattr(records[0], "tags", [])


# ── Test 1: "this morning" -> tod:morning tag ────────────────────────────────

class TestMorningSlotPersisted:
    def test_this_morning_stores_tod_morning_tag(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client this morning")
        tags = _tags(k, "met client")
        assert "tod:morning" in tags, f"Expected tod:morning in tags, got: {tags}"

    def test_this_morning_stores_resolved_tag_today(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client this morning")
        tags = _tags(k, "met client")
        expected_tag = f"resolved:{date.today().isoformat()}"
        assert expected_tag in tags, f"Expected {expected_tag!r} in tags, got: {tags}"

    def test_this_morning_stores_expr_tag(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client this morning")
        tags = _tags(k, "met client")
        assert any(t.startswith("expr:") for t in tags), (
            f"Expected expr: tag in tags, got: {tags}"
        )


# ── Test 2: "yesterday" -> resolved: tag yesterday ───────────────────────────

class TestYesterdayPersisted:
    def test_yesterday_stores_resolved_tag(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client yesterday")
        tags = _tags(k, "met client")
        expected = f"resolved:{(date.today() - timedelta(days=1)).isoformat()}"
        assert expected in tags, f"Expected {expected!r} in tags, got: {tags}"

    def test_yesterday_no_tod_tag(self, tmp_path):
        """Plain past-day expressions have no sub-day slot."""
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client yesterday")
        tags = _tags(k, "met client")
        tod_tags = [t for t in tags if t.startswith("tod:")]
        for t in tod_tags:
            assert t == "tod:unspecified", (
                f"Unexpected time-of-day tag for 'yesterday': {t}"
            )


# ── Test 3: No temporal expression -> no tod: tag inferred ───────────────────

class TestNoTemporalExpression:
    def test_no_expression_no_resolved_tag(self, tmp_path):
        """Critical: "I met the client" must not produce a resolved: tag."""
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client")
        tags = _tags(k, "met client")
        resolved_tags = [t for t in tags if t.startswith("resolved:")]
        assert not resolved_tags, (
            f"Should not have inferred resolved: tag: {resolved_tags}"
        )

    def test_no_expression_no_tod_tag(self, tmp_path):
        """Critical: never infer time-of-day from clock."""
        skill, k = _make_skill(tmp_path)
        skill.remember("met client", "I met the client")
        tags = _tags(k, "met client")
        tod_tags = [t for t in tags if t.startswith("tod:")]
        assert not tod_tags, (
            f"Should not have inferred tod: tag: {tod_tags}"
        )

    def test_no_expression_memory_still_stored(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        result = skill.remember("met client", "I met the client")
        assert result.success


# ── Test 4: Existing memories unchanged ──────────────────────────────────────

class TestExistingMemoriesUnchanged:
    def test_name_memory_unchanged(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        result = skill.remember("name", "Gianni")
        assert result.success
        record = k.recall_memory(subject="user", attribute="name")
        assert record is not None
        assert record.value == "Gianni"

    def test_favourite_colour_unchanged(self, tmp_path):
        skill, k = _make_skill(tmp_path)
        result = skill.remember("favourite colour", "blue")
        assert result.success
        record = k.recall_memory(subject="user", attribute="favourite colour")
        assert record.value == "blue"

    def test_no_parser_caller_unaffected(self, tmp_path):
        """Callers without temporal_parser get identical behaviour to before."""
        skill, k = _make_skill(tmp_path, with_parser=False)
        result = skill.remember("name", "Gianni")
        assert result.success
        record = k.recall_memory(subject="user", attribute="name")
        assert record.value == "Gianni"

    def test_caller_supplied_metadata_wins(self, tmp_path):
        """Caller-supplied temporal_metadata must not be overwritten."""
        skill, k = _make_skill(tmp_path)
        caller_meta = {
            "resolved_date": "2026-01-01",
            "temporal_expression": "new year",
            "time_of_day_slot": "unspecified",
        }
        skill.remember(
            "met client",
            "I met the client this morning",
            temporal_metadata=caller_meta,
        )
        tags = _tags(k, "met client")
        assert "resolved:2026-01-01" in tags, (
            f"Caller-supplied resolved_date was overwritten. Tags: {tags}"
        )


# ── Test 5: END-TO-END — TemporalRecallEngine answers locally ─────────────────

class TestEndToEndTemporalRecall:
    """
    Acceptance test: exact Test A failure scenario.

    Store: "I met the client this morning"
    Recall: "When did I meet the client?"
    Expected: found=True, answer contains "morning", no AI fallback.
    """

    def _setup(self, tmp_path):
        from core.skills.memory import MemorySkill
        from core.conversation.temporal_parser import TemporalParser
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        k = _make_engine(tmp_path)
        skill = MemorySkill(k, temporal_parser=TemporalParser())
        recall = TemporalRecallEngine()
        return skill, recall, k

    def test_store_then_recall_finds_record(self, tmp_path):
        skill, recall, k = self._setup(tmp_path)
        skill.remember("met client", "I met the client this morning")

        query = recall.detect_query("When did I meet the client?")
        assert query is not None, "TemporalRecallEngine did not detect temporal query"

        answer = recall.answer(query, k)
        assert answer.found, (
            f"TemporalRecallEngine returned found=False — would fall back to AI. "
            f"Answer: {answer.answer}"
        )

    def test_recall_answer_contains_morning(self, tmp_path):
        skill, recall, k = self._setup(tmp_path)
        skill.remember("met client", "I met the client this morning")

        query = recall.detect_query("When did I meet the client?")
        assert query is not None
        answer = recall.answer(query, k)
        assert answer.found

        assert "morning" in answer.answer.lower(), (
            f"Expected 'morning' in answer, got: {answer.answer!r}"
        )

    def test_recall_answer_not_parenthetical(self, tmp_path):
        """Answer uses structured slot, not "(this morning)" parenthetical."""
        skill, recall, k = self._setup(tmp_path)
        skill.remember("met client", "I met the client this morning")

        query = recall.detect_query("When did I meet the client?")
        assert query is not None
        answer = recall.answer(query, k)
        assert answer.found
        assert "(this morning)" not in answer.answer, (
            f"Answer used old parenthetical form: {answer.answer!r}"
        )

    def test_yesterday_recall_found(self, tmp_path):
        skill, recall, k = self._setup(tmp_path)
        skill.remember("met client", "I met the client yesterday")

        query = recall.detect_query("When did I meet the client?")
        assert query is not None
        answer = recall.answer(query, k)
        assert answer.found, (
            f"Should have found yesterday record. Answer: {answer.answer}"
        )

    def test_no_temporal_expression_recall_not_found(self, tmp_path):
        """
        "I met the client" (no time) -> no resolved: tag
        -> TemporalRecallEngine correctly returns found=False.
        Correct — Jarvis must not hallucinate a date.
        """
        skill, recall, k = self._setup(tmp_path)
        skill.remember("met client", "I met the client")

        query = recall.detect_query("When did I meet the client?")
        if query is not None:
            answer = recall.answer(query, k)
            assert not answer.found, (
                f"Should not have found a date for non-temporal memory. "
                f"Answer: {answer.answer}"
            )


# ── Test 6: MemorySkill.execute() event-style branch ─────────────────────────

class TestExecuteEventStyle:
    """
    Stabilisation: Test A — explicit memory pathway.
    "Remember that [clause]" must reach remember() with temporal enrichment.
    Implicit memory ("I met the client.") is NOT tested here — future work.
    """

    def _setup(self, tmp_path):
        from core.skills.memory import MemorySkill
        from core.conversation.temporal_parser import TemporalParser
        k = _make_engine(tmp_path)
        skill = MemorySkill(k, temporal_parser=TemporalParser())
        return skill, k

    def test_execute_remember_that_morning(self, tmp_path):
        """Core Test A: explicit event memory with morning slot."""
        skill, k = self._setup(tmp_path)
        result = skill.execute("Remember that I met the client this morning.")
        assert result.success, f"execute() failed: {result.message}"
        tags = _tags(k, "met client")
        assert "tod:morning" in tags, f"Expected tod:morning in tags: {tags}"

    def test_execute_remember_that_last_night(self, tmp_path):
        skill, k = self._setup(tmp_path)
        result = skill.execute("Remember that I deployed last night.")
        assert result.success
        tags = _tags(k, "deployed")
        assert "tod:night" in tags, f"Expected tod:night in tags: {tags}"

    def test_execute_remember_that_no_time(self, tmp_path):
        """Event without temporal expression — stored but no temporal tags."""
        skill, k = self._setup(tmp_path)
        result = skill.execute("Remember that I finished the report.")
        assert result.success
        # Memory stored — no tod: tag inferred
        records = k.search_memory("finished report", subject="user")
        assert records, "No record stored"
        tags = getattr(records[0], "tags", [])
        tod_tags = [t for t in tags if t.startswith("tod:")]
        assert not tod_tags, f"Should not have tod: tag: {tod_tags}"

    def test_execute_key_value_path_unchanged(self, tmp_path):
        """Existing key/value path must be unaffected.
        execute() lowercases the request before regex matching,
        so stored value is lowercase — existing behaviour.
        """
        skill, k = self._setup(tmp_path)
        result = skill.execute("Remember my name is Gianni.")
        assert result.success
        record = k.recall_memory(subject="user", attribute="name")
        assert record is not None
        assert record.value == "gianni"  # execute() lowercases before matching

    def test_execute_end_to_end_temporal_recall(self, tmp_path):
        """
        Full Test A acceptance: execute() -> remember() -> TemporalParser ->
        tod:morning tag -> TemporalRecallEngine answers locally.
        """
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        skill, k = self._setup(tmp_path)
        recall = TemporalRecallEngine()

        skill.execute("Remember that I met the client this morning.")

        query = recall.detect_query("When did I meet the client?")
        assert query is not None, "TemporalRecallEngine did not detect query"

        answer = recall.answer(query, k)
        assert answer.found, (
            f"TemporalRecallEngine returned found=False — would fall back to AI. "
            f"Answer: {answer.answer}"
        )
        assert "morning" in answer.answer.lower(), (
            f"Expected 'morning' in answer, got: {answer.answer!r}"
        )
        assert "(this morning)" not in answer.answer, (
            f"Answer used old parenthetical form: {answer.answer!r}"
        )
