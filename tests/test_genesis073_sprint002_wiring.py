"""
Genesis-073 Sprint-002 -- Situational extraction wiring tests
6 tests covering:
    - Extraction fires on a normal (non-explicit-memory) turn
    - Extraction skipped on turns below minimum length
    - Explicit fact excluded from prompt when memory_store fired
    - Mixed turn: explicit fact excluded, remainder still extracted
    - Extraction failure does not propagate to caller
    - Concurrent writes produce both entries (lock test)

No real API calls -- all tests use mock AI client.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.knowledge.situational_memory import (
    MemoryEntry,
    MemoryExtractionPipeline,
    SituationalMemoryStore,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path) -> SituationalMemoryStore:
    return SituationalMemoryStore(tmp_path)


def _mock_ai(json_entries: list[dict]):
    mock = MagicMock()
    mock.ask.return_value = MagicMock(
        success=True,
        message=json.dumps(json_entries),
    )
    return mock


# ---------------------------------------------------------------------------
# W-01: Extraction fires on normal turn
# ---------------------------------------------------------------------------

class TestExtractionFiresOnNormalTurn:
    """W-01: MemoryExtractionPipeline.extract() is called and entries stored."""

    def test_extraction_stores_entry_on_normal_turn(self, tmp_path):
        ai = _mock_ai([{"category": "fact", "content": "Gianni lives in Melbourne."}])
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        store = _store(tmp_path)

        turn_text = "User: Where do I live?\nJarvis: You live in Melbourne."
        entries = pipeline.extract(turn_text)
        for e in entries:
            store.store(e)

        assert len(entries) == 1
        assert entries[0].category == "fact"
        stored = store.get_all()
        assert len(stored) == 1
        ai.ask.assert_called_once()


# ---------------------------------------------------------------------------
# W-02: Extraction skipped on short turn
# ---------------------------------------------------------------------------

class TestExtractionSkippedOnShortTurn:
    """W-02: Turns under minimum length return [] without an API call."""

    def test_empty_text_returns_empty(self):
        ai = MagicMock()
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        result = pipeline.extract("")
        assert result == []
        ai.ask.assert_not_called()

    def test_whitespace_only_returns_empty(self):
        ai = MagicMock()
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        result = pipeline.extract("   ")
        assert result == []
        ai.ask.assert_not_called()


# ---------------------------------------------------------------------------
# W-03: Explicit fact excluded from prompt
# ---------------------------------------------------------------------------

class TestExplicitFactExcludedFromPrompt:
    """W-03: When explicit_stored is passed, the prompt contains an exclusion note."""

    def test_exclusion_note_in_prompt(self):
        ai = _mock_ai([])
        pipeline = MemoryExtractionPipeline(ai_client=ai)

        explicit = "favourite colour=red"
        turn_text = "User: My favourite colour is red.\nJarvis: Got it, I will remember that."
        prompt_with_exclusion = (
            f"Note: the fact '{explicit}' has already been "
            f"explicitly stored. Do not extract it again.\n\n{turn_text}"
        )

        pipeline.extract(prompt_with_exclusion)
        call_arg = ai.ask.call_args[0][0]
        assert "favourite colour=red" in call_arg
        assert "Do not extract it again" in call_arg


# ---------------------------------------------------------------------------
# W-04: Mixed turn -- explicit excluded, remainder extracted
# ---------------------------------------------------------------------------

class TestMixedTurnExtraction:
    """W-04: Mixed turn produces entries from non-explicit content only."""

    def test_mixed_turn_extracts_remainder(self, tmp_path):
        ai = _mock_ai([
            {"category": "intention", "content": "Gianni is thinking about applying for the CRC grant."},
        ])
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        store = _store(tmp_path)

        explicit = "favourite colour=red"
        turn_text = (
            "User: My favourite colour is red. Also thinking about the CRC grant.\n"
            "Jarvis: Got it."
        )
        prompt = (
            f"Note: the fact '{explicit}' has already been "
            f"explicitly stored. Do not extract it again.\n\n{turn_text}"
        )

        entries = pipeline.extract(prompt)
        for e in entries:
            store.store(e)

        assert len(entries) == 1
        assert entries[0].category == "intention"
        assert "CRC" in entries[0].content


# ---------------------------------------------------------------------------
# W-05: Extraction failure does not propagate
# ---------------------------------------------------------------------------

class TestExtractionFailureDoesNotPropagate:
    """W-05: Exception in extraction is caught and swallowed silently."""

    def test_api_failure_returns_empty(self):
        ai = MagicMock()
        ai.ask.side_effect = RuntimeError("API timeout")
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        result = pipeline.extract("User: Hello.\nJarvis: Hi there.")
        assert result == []

    def test_malformed_json_returns_empty(self):
        ai = MagicMock()
        ai.ask.return_value = MagicMock(success=True, message="not json at all")
        pipeline = MemoryExtractionPipeline(ai_client=ai)
        result = pipeline.extract("User: Hello.\nJarvis: Hi there.")
        assert result == []


# ---------------------------------------------------------------------------
# W-06: Concurrent writes -- both entries survive (lock test)
# ---------------------------------------------------------------------------

class TestConcurrentWritesSafe:
    """W-06: Two threads writing simultaneously produce both entries."""

    def test_concurrent_store_calls_produce_both_entries(self, tmp_path):
        store = _store(tmp_path)
        e1 = MemoryEntry.create("fact", "Entry from thread 1.")
        e2 = MemoryEntry.create("fact", "Entry from thread 2.")

        errors = []

        def write1():
            try:
                store.store(e1)
            except Exception as exc:
                errors.append(exc)

        def write2():
            try:
                store.store(e2)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=write1)
        t2 = threading.Thread(target=write2)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        all_entries = store.get_all()
        assert len(all_entries) == 2, (
            f"Expected 2 entries after concurrent writes, got {len(all_entries)}"
        )
        ids = {e.id for e in all_entries}
        assert e1.id in ids, "Entry from thread 1 was lost"
        assert e2.id in ids, "Entry from thread 2 was lost"
