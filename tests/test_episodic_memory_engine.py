"""
Tests for EpisodicMemoryEngine — parse_query, recall, format_response.
"""

import pytest
from unittest.mock import MagicMock, patch
from core.episodic_memory_engine import (
    EpisodicMemoryEngine,
    EpisodeQuery,
    EpisodeQueryType,
    EpisodeSummary,
)


# ─────────────────────────────────────────────
# Helpers / Fixtures
# ─────────────────────────────────────────────

def _make_engine(memories=None):
    """Return an EpisodicMemoryEngine with stub KE and TemporalParser."""
    ke = MagicMock()
    ke.list_memories.return_value = memories or []
    tp = MagicMock()
    tp.parse.return_value = None
    return EpisodicMemoryEngine(ke, tp), ke, tp


def _temporal_query(label="Yesterday", tc=None):
    return EpisodeQuery(
        query_type=EpisodeQueryType.TEMPORAL,
        label=label,
        temporal_context=tc or MagicMock(),
        raw_query=f"What happened {label.lower()}?",
    )


def _labeled_query(label="genesis-027"):
    return EpisodeQuery(
        query_type=EpisodeQueryType.LABELED,
        label=label,
        raw_query=f"What happened during {label}?",
    )


# ─────────────────────────────────────────────
# parse_query — TEMPORAL detection
# ─────────────────────────────────────────────

class TestParseQueryTemporal:

    def test_yesterday(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What happened yesterday?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL

    def test_last_tuesday(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What did we do last Tuesday?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL

    def test_what_did_i_do(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What did I do yesterday?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL

    def test_what_was_happening(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What was happening last week?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL

    def test_recap_temporal(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("Recap yesterday")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL

    def test_summary_of_temporal(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("Summary of last week")
        assert q is not None
        assert q.query_type is EpisodeQueryType.TEMPORAL


# ─────────────────────────────────────────────
# parse_query — LABELED detection
# ─────────────────────────────────────────────

class TestParseQueryLabeled:

    def test_genesis_sprint(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What happened during Genesis-027?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.LABELED
        assert "genesis-027" in q.label.lower()

    def test_tell_me_about_label(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("Tell me about Genesis-032")
        assert q is not None
        assert q.query_type is EpisodeQueryType.LABELED

    def test_recap_of_sprint(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("Recap of Sprint-003")
        assert q is not None
        assert q.query_type is EpisodeQueryType.LABELED

    def test_what_happened_in_sprint(self):
        engine, _, _ = _make_engine()
        q = engine.parse_query("What happened during sprint-001?")
        assert q is not None
        assert q.query_type is EpisodeQueryType.LABELED


# ─────────────────────────────────────────────
# parse_query — non-episodic returns None
# ─────────────────────────────────────────────

class TestParseQueryNone:

    def test_general_question(self):
        engine, _, _ = _make_engine()
        assert engine.parse_query("Who is Rex?") is None

    def test_empty_string(self):
        engine, _, _ = _make_engine()
        assert engine.parse_query("") is None

    def test_unrelated_statement(self):
        engine, _, _ = _make_engine()
        assert engine.parse_query("The sky is blue") is None

    def test_how_is_related(self):
        engine, _, _ = _make_engine()
        assert engine.parse_query("How is Rex related to Tom?") is None

    def test_set_memory(self):
        engine, _, _ = _make_engine()
        assert engine.parse_query("Remember that Rex is my dog") is None


# ─────────────────────────────────────────────
# parse_query — all trigger phrases fire
# ─────────────────────────────────────────────

@pytest.mark.parametrize("utterance", [
    "What happened during Genesis-027?",
    "What did we do last Tuesday?",
    "What did I do yesterday?",
    "Tell me about Genesis-027",
    "What was happening last week?",
    "Recap of last month",
    "Recap yesterday",
    "Summary of Genesis-027",
])
def test_all_trigger_phrases(utterance):
    engine, _, _ = _make_engine()
    q = engine.parse_query(utterance)
    assert q is not None, f"Trigger phrase not detected in: {utterance!r}"


# ─────────────────────────────────────────────
# recall()
# ─────────────────────────────────────────────

class TestRecall:

    def _labeled_ke(self, label="genesis-027", texts=("Memory A", "Memory B")):
        ke = MagicMock()
        memories = []
        for text in texts:
            m = MagicMock()
            m.value = text
            m.tags = [label]
            memories.append(m)
        ke.list_memories.return_value = memories
        return ke

    def test_labeled_recall_returns_summary(self):
        ke = self._labeled_ke()
        tp = MagicMock()
        engine = EpisodicMemoryEngine(ke, tp)
        q = _labeled_query("genesis-027")
        summary = engine.recall(q)
        assert summary is not None
        assert summary.memory_count == 2
        assert "Memory A" in summary.memories

    def test_labeled_recall_no_match_returns_none(self):
        ke = self._labeled_ke(label="genesis-027")
        tp = MagicMock()
        engine = EpisodicMemoryEngine(ke, tp)
        q = _labeled_query("genesis-001")
        summary = engine.recall(q)
        assert summary is None

    def test_temporal_recall_returns_summary(self):
        import datetime
        ke = MagicMock()
        m = MagicMock()
        m.value = "We worked on streaming."
        m.tags = ["2026-07-27"]
        ke.list_memories.return_value = [m]

        tc = MagicMock()
        tc.start_date = datetime.date(2026, 7, 27)
        tc.end_date   = datetime.date(2026, 7, 27)

        tp = MagicMock()
        tp.parse.return_value = tc
        engine = EpisodicMemoryEngine(ke, tp)

        q = EpisodeQuery(
            query_type=EpisodeQueryType.TEMPORAL,
            label="Yesterday",
            temporal_context=tc,
            raw_query="What happened yesterday?",
        )
        summary = engine.recall(q)
        assert summary is not None
        assert summary.memory_count == 1

    def test_temporal_recall_no_match_returns_none(self):
        import datetime
        ke = MagicMock()
        m = MagicMock()
        m.value = "Old memory."
        m.tags = ["2026-01-01"]
        ke.list_memories.return_value = [m]

        tc = MagicMock()
        tc.start_date = datetime.date(2026, 7, 27)
        tc.end_date   = datetime.date(2026, 7, 27)

        tp = MagicMock()
        engine = EpisodicMemoryEngine(ke, tp)

        q = EpisodeQuery(
            query_type=EpisodeQueryType.TEMPORAL,
            label="Yesterday",
            temporal_context=tc,
            raw_query="What happened yesterday?",
        )
        summary = engine.recall(q)
        assert summary is None


# ─────────────────────────────────────────────
# format_response()
# ─────────────────────────────────────────────

class TestFormatResponse:

    def _engine(self):
        engine, _, _ = _make_engine()
        return engine

    def test_none_summary(self):
        engine = self._engine()
        result = engine.format_response(None)
        assert "don't have any memories" in result

    def test_zero_memories(self):
        engine = self._engine()
        summary = EpisodeSummary(label="Genesis-001", memories=[])
        result = engine.format_response(summary)
        assert "don't have any memories" in result
        assert "Genesis-001" in result

    def test_one_memory(self):
        engine = self._engine()
        summary = EpisodeSummary(label="Yesterday", memories=["We fixed the bug."])
        result = engine.format_response(summary)
        assert result.startswith("From Yesterday:")
        assert "We fixed the bug." in result

    def test_two_plus_memories(self):
        engine = self._engine()
        summary = EpisodeSummary(
            label="Genesis-027",
            memories=["We built the WOS.", "WorkerFactory was implemented.", "CodingWorker was registered."],
        )
        result = engine.format_response(summary)
        assert "Here's what I have from Genesis-027:" in result
        assert "- We built the WOS." in result
        assert "- WorkerFactory was implemented." in result
        assert "- CodingWorker was registered." in result

    def test_two_memories(self):
        engine = self._engine()
        summary = EpisodeSummary(label="Last Tuesday", memories=["Task A", "Task B"])
        result = engine.format_response(summary)
        assert "Here's what I have from Last Tuesday:" in result
        assert "- Task A" in result
        assert "- Task B" in result
