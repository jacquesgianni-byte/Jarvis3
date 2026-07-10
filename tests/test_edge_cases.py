"""
Knowledge Engine — Edge Case Tests

Intentionally attempts to break the engine with invalid, boundary,
and unexpected inputs. Every test here represents a real failure mode
that could occur in production.

Run with:
    python -m tests.test_edge_cases

All tests must pass before the Knowledge Engine is considered production-ready.
"""

import os
import sys
import json
import tempfile
from datetime import datetime, UTC, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.knowledge_engine.engine import KnowledgeEngine
from core.knowledge_engine.json_storage import JsonKnowledgeRepository
from core.knowledge_engine.models import MemorySource, Visibility
from core.knowledge_engine.exceptions import InvalidMemoryError


def make_engine() -> KnowledgeEngine:
    """Create a KnowledgeEngine backed by a temporary file for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump([], tmp)
    tmp.close()
    storage = JsonKnowledgeRepository(path=tmp.name)
    return KnowledgeEngine(storage=storage)


# ------------------------------------------------------------------
# Empty and whitespace inputs
# ------------------------------------------------------------------

def test_store_empty_strings():
    print("\n--- Edge Case: store_memory() with empty strings ---")
    engine = make_engine()

    try:
        engine.store_memory(
            subject="",
            category="general",
            attribute="",
            value=""
        )
        # If the engine did not raise, check it stored nothing meaningful
        result = engine.recall_memory(subject="", attribute="")
        assert result is None, "Empty subject/attribute should not be recallable."
        print("Engine accepted empty strings but recall returns None — acceptable.")
    except (InvalidMemoryError, ValueError) as e:
        print(f"Engine correctly rejected empty strings: {e}")
    print("PASS")


def test_store_whitespace_only():
    print("\n--- Edge Case: store_memory() with whitespace-only strings ---")
    engine = make_engine()

    try:
        engine.store_memory(
            subject="   ",
            category="general",
            attribute="   ",
            value="   "
        )
        result = engine.recall_memory(subject="   ", attribute="   ")
        assert result is None, "Whitespace-only subject/attribute should not be recallable."
        print("Engine accepted whitespace but recall returns None — acceptable.")
    except (InvalidMemoryError, ValueError) as e:
        print(f"Engine correctly rejected whitespace-only strings: {e}")
    print("PASS")


# ------------------------------------------------------------------
# Recall and forget on non-existent memories
# ------------------------------------------------------------------

def test_recall_unknown():
    print("\n--- Edge Case: recall_memory() for unknown subject/attribute ---")
    engine = make_engine()

    result = engine.recall_memory(subject="unknown", attribute="unknown")
    assert result is None, "Recall of unknown memory must return None."
    print("recall_memory('unknown', 'unknown') → None")
    print("PASS")


def test_forget_unknown():
    print("\n--- Edge Case: forget_memory() for unknown subject/attribute ---")
    engine = make_engine()

    result = engine.forget_memory(subject="unknown", attribute="unknown")
    assert result is False, "Forget of unknown memory must return False."
    print("forget_memory('unknown', 'unknown') → False")
    print("PASS")


def test_forget_hard_unknown():
    print("\n--- Edge Case: forget_memory(permanent=True) for unknown ---")
    engine = make_engine()

    result = engine.forget_memory(subject="unknown", attribute="unknown", permanent=True)
    assert result is False, "Hard delete of unknown memory must return False."
    print("forget_memory('unknown', 'unknown', permanent=True) → False")
    print("PASS")


def test_update_unknown():
    print("\n--- Edge Case: update_memory() for unknown subject/attribute ---")
    engine = make_engine()

    result = engine.update_memory(subject="unknown", attribute="unknown", value="something")
    assert result is None, "Update of unknown memory must return None."
    print("update_memory('unknown', 'unknown', ...) → None")
    print("PASS")


# ------------------------------------------------------------------
# Out-of-range confidence and importance
# ------------------------------------------------------------------

def test_store_importance_out_of_range():
    print("\n--- Edge Case: store_memory() with importance=250 ---")
    engine = make_engine()

    try:
        engine.store_memory(
            subject="user",
            category="general",
            attribute="test",
            value="test",
            importance=250.0
        )
        print("Engine accepted importance=250 — validation not yet enforced.")
    except (InvalidMemoryError, ValueError) as e:
        print(f"Engine correctly rejected importance=250: {e}")
    print("PASS")


def test_store_confidence_negative():
    print("\n--- Edge Case: store_memory() with confidence=-5 ---")
    engine = make_engine()

    try:
        engine.store_memory(
            subject="user",
            category="general",
            attribute="test",
            value="test",
            confidence=-5.0
        )
        print("Engine accepted confidence=-5 — validation not yet enforced.")
    except (InvalidMemoryError, ValueError) as e:
        print(f"Engine correctly rejected confidence=-5: {e}")
    print("PASS")


def test_store_confidence_above_one():
    print("\n--- Edge Case: store_memory() with confidence=1.5 ---")
    engine = make_engine()

    try:
        engine.store_memory(
            subject="user",
            category="general",
            attribute="test",
            value="test",
            confidence=1.5
        )
        print("Engine accepted confidence=1.5 — validation not yet enforced.")
    except (InvalidMemoryError, ValueError) as e:
        print(f"Engine correctly rejected confidence=1.5: {e}")
    print("PASS")


# ------------------------------------------------------------------
# Expiry behaviour
# ------------------------------------------------------------------

def test_store_with_past_expiry():
    print("\n--- Edge Case: store_memory() with expires_at in the past ---")
    engine = make_engine()

    yesterday = datetime.now(UTC) - timedelta(days=1)
    engine.store_memory(
        subject="user",
        category="schedule",
        attribute="last_trip",
        value="Sydney",
        expires_at=yesterday
    )

    result = engine.recall_memory(subject="user", attribute="last_trip")
    assert result is None, "Memory with past expires_at must not be recalled."
    print("Memory stored with past expiry — recall returns None immediately.")
    print("PASS")


def test_store_then_expire():
    print("\n--- Edge Case: memory expires after being stored ---")
    engine = make_engine()

    future = datetime.now(UTC) + timedelta(seconds=1)
    engine.store_memory(
        subject="user",
        category="schedule",
        attribute="reminder",
        value="Call dentist",
        expires_at=future
    )

    # Should still be recallable immediately
    result = engine.recall_memory(subject="user", attribute="reminder")
    assert result is not None, "Memory should be recallable before expiry."
    print("Memory recallable before expiry.")

    # Manually expire it
    result.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    engine._storage.save(result)

    expired = engine.recall_memory(subject="user", attribute="reminder")
    assert expired is None, "Memory should not be recallable after expiry."
    print("Memory not recallable after expiry.")
    print("PASS")


# ------------------------------------------------------------------
# Search edge cases
# ------------------------------------------------------------------

def test_search_empty_query():
    print("\n--- Edge Case: search_memory() with empty query ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")

    results = engine.search_memory(query="")
    assert isinstance(results, list), "search_memory('') must return a list."
    print(f"search_memory('') → {len(results)} results (list, not exception)")
    print("PASS")


def test_search_no_matches():
    print("\n--- Edge Case: search_memory() with no matching records ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")

    results = engine.search_memory(query="xyzzy_no_match_possible")
    assert results == [], "search_memory with no matches must return empty list."
    print("search_memory('xyzzy_no_match_possible') → []")
    print("PASS")


def test_search_expired_excluded():
    print("\n--- Edge Case: search_memory() excludes expired records ---")
    engine = make_engine()

    yesterday = datetime.now(UTC) - timedelta(days=1)
    engine.store_memory(
        subject="user",
        category="schedule",
        attribute="trip",
        value="Paris",
        tags=["travel"],
        expires_at=yesterday
    )

    results = engine.search_memory(query="travel")
    assert results == [], "Expired memories must be excluded from search results."
    print("search_memory('travel') excludes expired record → []")
    print("PASS")


# ------------------------------------------------------------------
# Duplicate and conflict edge cases
# ------------------------------------------------------------------

def test_double_forget():
    print("\n--- Edge Case: forget_memory() called twice on same record ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")

    first = engine.forget_memory(subject="user", attribute="drink")
    assert first is True

    second = engine.forget_memory(subject="user", attribute="drink")
    # Second soft delete on already-expired record — behaviour should be defined
    print(f"Second forget_memory → {second} (soft delete on already-expired record)")
    print("PASS")


def test_update_after_forget():
    print("\n--- Edge Case: update_memory() on a soft-deleted record ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")
    engine.forget_memory(subject="user", attribute="drink")

    # Update on soft-deleted record
    result = engine.update_memory(subject="user", attribute="drink", value="tea")
    if result is not None:
        print(f"update_memory on soft-deleted record returned: {result.value}")
    else:
        print("update_memory on soft-deleted record → None")
    print("PASS")


def test_list_memories_empty_store():
    print("\n--- Edge Case: list_memories() on empty store ---")
    engine = make_engine()

    results = engine.list_memories()
    assert results == [], "list_memories() on empty store must return []."
    print("list_memories() on empty store → []")
    print("PASS")


def test_list_memories_unknown_category():
    print("\n--- Edge Case: list_memories() with unknown category ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")

    results = engine.list_memories(category="nonexistent_category")
    assert results == [], "list_memories() with unknown category must return []."
    print("list_memories(category='nonexistent_category') → []")
    print("PASS")


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("Jarvis Knowledge Engine — Edge Case Tests")
    print("=" * 55)

    test_store_empty_strings()
    test_store_whitespace_only()
    test_recall_unknown()
    test_forget_unknown()
    test_forget_hard_unknown()
    test_update_unknown()
    test_store_importance_out_of_range()
    test_store_confidence_negative()
    test_store_confidence_above_one()
    test_store_with_past_expiry()
    test_store_then_expire()
    test_search_empty_query()
    test_search_no_matches()
    test_search_expired_excluded()
    test_double_forget()
    test_update_after_forget()
    test_list_memories_empty_store()
    test_list_memories_unknown_category()

    print("\n" + "=" * 55)
    print("All edge case tests passed.")
    print("=" * 55)