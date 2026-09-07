"""
Genesis-073 Layer 3 Retrieval Tests
7 scenarios covering all six categories + negative control + competition.
No real API calls.
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from core.knowledge.situational_memory import (
    MemoryEntry, SituationalMemoryStore,
    QUERY_CATEGORY_MAP, CATEGORY_EXPANSIONS,
)

def _store(tmp_path):
    return SituationalMemoryStore(tmp_path)

def _plant(store, category, content):
    e = MemoryEntry.create(category=category, content=content)
    store.store(e)
    return e

class TestOccupationRetrieval:
    """S1: vocabulary gap -- query uses work, stored uses trade."""
    def test_job_query_finds_trade_entry(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        results = s.query("What do I do for work?")
        assert len(results) == 1
        assert "painter" in results[0].content.lower()

    def test_direct_word_match_also_works(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        results = s.query("What is my trade?")
        assert len(results) == 1

class TestIntentionRetrieval:
    """S2: intention query."""
    def test_planning_query_finds_intention(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "intention", "The user intends to expand Jarvis into a small-business product.")
        results = s.query("What am I planning for Jarvis?")
        assert len(results) == 1
        assert "jarvis" in results[0].content.lower()

class TestConstraintRetrieval:
    """S3: constraint query via vocabulary bridge."""
    def test_constraint_about_memory(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "constraint", "The user does not want Jarvis storing sensitive personal information automatically.")
        results = s.query("What constraint did I give you about memory?")
        assert len(results) == 1
        assert "sensitive" in results[0].content.lower()

class TestNegativeControl:
    """S4: unrelated queries return empty -- no hallucination."""
    def test_unrelated_query_returns_empty(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        results = s.query("What is the capital of France?")
        assert results == []

    def test_empty_store_returns_empty(self, tmp_path):
        s = _store(tmp_path)
        results = s.query("What is my job?")
        assert results == []

    def test_empty_query_returns_empty(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        results = s.query("")
        assert results == []

class TestMultipleMemoryCompetition:
    """S5: most relevant memory ranked first."""
    def test_job_query_prefers_occupation_entry(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        _plant(s, "fact", "The user's favourite colour is blue.")
        results = s.query("What is my job?")
        assert len(results) >= 1
        assert "painter" in results[0].content.lower()

    def test_colour_query_prefers_colour_entry(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "fact", "The user is a painter by trade.")
        _plant(s, "fact", "The user's favourite colour is blue.")
        results = s.query("What is my favourite colour?")
        assert len(results) >= 1
        assert "blue" in results[0].content.lower()

class TestDuplicateMemories:
    """S6: duplicates bounded by max_results."""
    def test_duplicates_bounded_by_max_results(self, tmp_path):
        s = _store(tmp_path)
        for _ in range(5):
            _plant(s, "fact", "The user is a painter by trade.")
        results = s.query("What is my job?", max_results=3)
        assert len(results) <= 3

class TestUnresolvedRetrieval:
    """S7: unresolved category."""
    def test_unresolved_query_finds_entry(self, tmp_path):
        s = _store(tmp_path)
        _plant(s, "unresolved", "It is unclear whether Chase is a third dog or something else.")
        results = s.query("What was unresolved about Chase?")
        assert len(results) == 1
        assert "chase" in results[0].content.lower()

class TestVocabularyConstants:
    """Vocabulary bridge is generic -- not person-specific."""
    def test_all_six_categories_in_query_map(self):
        expected = {"fact","decision","question","constraint","intention","unresolved"}
        assert set(QUERY_CATEGORY_MAP.keys()) == expected

    def test_expansions_do_not_contain_person_specific_answers(self):
        PERSONAL = {
            "gianni","catriana","lucas","leo","rex","tom","chase",
            "painter","melbourne","lmj","jarvis3",
        }
        for category, mapping in CATEGORY_EXPANSIONS.items():
            for key, synonyms in mapping.items():
                for word in synonyms:
                    assert word not in PERSONAL, (
                        f"Personal fact {word!r} in CATEGORY_EXPANSIONS[{category!r}][{key!r}]"
                    )
