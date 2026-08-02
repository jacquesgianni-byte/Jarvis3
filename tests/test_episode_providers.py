"""
Tests for TemporalEpisodeProvider and LabeledEpisodeProvider.
"""

import datetime
import pytest
from unittest.mock import MagicMock

from core.episodic_memory_engine import (
    EpisodeQuery,
    EpisodeQueryType,
    TemporalEpisodeProvider,
    LabeledEpisodeProvider,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _temporal_query(tc=None):
    return EpisodeQuery(
        query_type=EpisodeQueryType.TEMPORAL,
        label="Yesterday",
        temporal_context=tc or MagicMock(),
        raw_query="What happened yesterday?",
    )


def _labeled_query(label="genesis-027"):
    return EpisodeQuery(
        query_type=EpisodeQueryType.LABELED,
        label=label,
        raw_query=f"What happened during {label}?",
    )


def _make_memory(content: str, tags: list[str]):
    m = MagicMock()
    m.content = content
    m.tags = tags
    return m


def _make_ke(memories):
    ke = MagicMock()
    ke.get_all_memories.return_value = memories
    return ke


def _make_tc(start: datetime.date, end: datetime.date | None = None):
    tc = MagicMock()
    tc.start_date = start
    tc.end_date   = end or start
    return tc


# ─────────────────────────────────────────────
# TemporalEpisodeProvider
# ─────────────────────────────────────────────

class TestTemporalEpisodeProvider:

    def setup_method(self):
        self.provider = TemporalEpisodeProvider()

    def test_can_handle_temporal(self):
        assert self.provider.can_handle(_temporal_query()) is True

    def test_cannot_handle_labeled(self):
        assert self.provider.can_handle(_labeled_query()) is False

    def test_gather_returns_matching_memories(self):
        date = datetime.date(2026, 7, 27)
        memories = [
            _make_memory("We worked on streaming.", [str(date)]),
            _make_memory("We fixed cancellation.",  [str(date)]),
            _make_memory("Old memory.",              ["2026-01-01"]),
        ]
        ke = _make_ke(memories)
        tc = _make_tc(date)
        q = _temporal_query(tc)

        result = self.provider.gather(q, ke)
        assert len(result) == 2
        assert "We worked on streaming." in result
        assert "We fixed cancellation."  in result
        assert "Old memory." not in result

    def test_gather_empty_when_no_match(self):
        date = datetime.date(2026, 7, 27)
        memories = [_make_memory("Old memory.", ["2026-01-01"])]
        ke = _make_ke(memories)
        tc = _make_tc(date)
        q = _temporal_query(tc)
        assert self.provider.gather(q, ke) == []

    def test_gather_with_date_range(self):
        memories = [
            _make_memory("Day 1 memory.", ["2026-07-25"]),
            _make_memory("Day 2 memory.", ["2026-07-26"]),
            _make_memory("Day 3 memory.", ["2026-07-27"]),
            _make_memory("Outside range.", ["2026-07-28"]),
        ]
        ke = _make_ke(memories)
        tc = _make_tc(
            datetime.date(2026, 7, 25),
            datetime.date(2026, 7, 27),
        )
        q = _temporal_query(tc)
        result = self.provider.gather(q, ke)
        assert len(result) == 3
        assert "Outside range." not in result

    def test_gather_empty_when_no_temporal_context(self):
        ke = _make_ke([_make_memory("Memory.", ["2026-07-27"])])
        q = EpisodeQuery(
            query_type=EpisodeQueryType.TEMPORAL,
            label="Yesterday",
            temporal_context=None,
            raw_query="What happened yesterday?",
        )
        assert self.provider.gather(q, ke) == []

    def test_gather_empty_when_ke_has_no_memories(self):
        ke = _make_ke([])
        tc = _make_tc(datetime.date(2026, 7, 27))
        assert self.provider.gather(_temporal_query(tc), ke) == []


# ─────────────────────────────────────────────
# LabeledEpisodeProvider
# ─────────────────────────────────────────────

class TestLabeledEpisodeProvider:

    def setup_method(self):
        self.provider = LabeledEpisodeProvider()

    def test_can_handle_labeled(self):
        assert self.provider.can_handle(_labeled_query()) is True

    def test_cannot_handle_temporal(self):
        assert self.provider.can_handle(_temporal_query()) is False

    def test_gather_returns_matching_memories(self):
        memories = [
            _make_memory("We built the WOS.",            ["genesis-027"]),
            _make_memory("WorkerFactory implemented.",   ["genesis-027"]),
            _make_memory("Unrelated memory.",            ["genesis-026"]),
        ]
        ke = _make_ke(memories)
        q = _labeled_query("genesis-027")
        result = self.provider.gather(q, ke)
        assert len(result) == 2
        assert "We built the WOS." in result
        assert "WorkerFactory implemented." in result
        assert "Unrelated memory." not in result

    def test_gather_case_insensitive(self):
        """Genesis-027 query should match tag 'genesis-027'."""
        memories = [_make_memory("WOS built.", ["genesis-027"])]
        ke = _make_ke(memories)
        q = _labeled_query("Genesis-027")
        result = self.provider.gather(q, ke)
        assert len(result) == 1
        assert "WOS built." in result

    def test_gather_case_insensitive_reverse(self):
        """Lowercase query should match uppercase stored tag."""
        memories = [_make_memory("Some memory.", ["GENESIS-027"])]
        ke = _make_ke(memories)
        q = _labeled_query("genesis-027")
        result = self.provider.gather(q, ke)
        assert len(result) == 1

    def test_gather_empty_when_no_match(self):
        memories = [_make_memory("WOS built.", ["genesis-027"])]
        ke = _make_ke(memories)
        q = _labeled_query("genesis-001")
        assert self.provider.gather(q, ke) == []

    def test_gather_empty_when_no_label(self):
        ke = _make_ke([_make_memory("Memory.", ["genesis-027"])])
        q = EpisodeQuery(
            query_type=EpisodeQueryType.LABELED,
            label=None,
            raw_query="What happened?",
        )
        assert self.provider.gather(q, ke) == []

    def test_gather_empty_ke(self):
        ke = _make_ke([])
        q = _labeled_query("genesis-027")
        assert self.provider.gather(q, ke) == []

    def test_gather_multiple_tags_on_memory(self):
        """Memory with multiple tags — should still match on the target tag."""
        memories = [_make_memory("Multi-tag memory.", ["genesis-027", "sprint-003", "wos"])]
        ke = _make_ke(memories)
        q = _labeled_query("sprint-003")
        result = self.provider.gather(q, ke)
        assert len(result) == 1
        assert "Multi-tag memory." in result

    def test_gather_preserves_order(self):
        """Memories should come back in the order KE stores them."""
        texts = [f"Memory {i}" for i in range(5)]
        memories = [_make_memory(t, ["genesis-027"]) for t in texts]
        ke = _make_ke(memories)
        q = _labeled_query("genesis-027")
        result = self.provider.gather(q, ke)
        assert result == texts
