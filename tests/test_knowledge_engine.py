"""
Standalone test for the Jarvis Knowledge Engine.

Demonstrates all six public API methods without involving
the Agent, Desktop UI, or any AI provider.

Run with:
    python -m tests.test_knowledge_engine
"""

import os
import sys
import tempfile
import json

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.knowledge_engine.engine import KnowledgeEngine
from core.knowledge_engine.json_storage import JsonKnowledgeRepository
from core.knowledge_engine.categories import CategoryLoader


def make_engine() -> KnowledgeEngine:
    """Create a KnowledgeEngine backed by a temporary file for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump([], tmp)
    tmp.close()

    storage = JsonKnowledgeRepository(path=tmp.name)
    engine = KnowledgeEngine(storage=storage)
    return engine


def test_store_and_recall():
    print("\n--- Test: StoreMemory + RecallMemory ---")
    engine = make_engine()

    record = engine.store_memory(
        subject="user",
        category="preferences",
        attribute="favourite_colour",
        value="blue",
        tags=["colour", "preference"]
    )
    print(f"Stored: {record.subject} / {record.attribute} = {record.value}")
    assert record.value == "blue"

    recalled = engine.recall_memory(subject="user", attribute="favourite_colour")
    assert recalled is not None
    assert recalled.value == "blue"
    print(f"Recalled: {recalled.value}")
    print("PASS")


def test_duplicate_detection():
    print("\n--- Test: Duplicate detection → UpdateMemory ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")
    engine.store_memory(subject="user", category="preferences", attribute="drink", value="tea")

    recalled = engine.recall_memory(subject="user", attribute="drink")
    assert recalled is not None
    assert recalled.value == "tea"
    assert recalled.notes is not None
    print(f"Value after duplicate store: {recalled.value}")
    print(f"Notes: {recalled.notes}")
    print("PASS")


def test_update_memory():
    print("\n--- Test: UpdateMemory ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="favourite_colour", value="blue")
    updated = engine.update_memory(subject="user", attribute="favourite_colour", value="green")

    assert updated is not None
    assert updated.value == "green"
    assert "blue" in updated.notes
    print(f"Updated value: {updated.value}")
    print(f"Notes preserved previous value: {'blue' in updated.notes}")
    print("PASS")


def test_forget_soft():
    print("\n--- Test: ForgetMemory (soft delete) ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="favourite_colour", value="blue")
    result = engine.forget_memory(subject="user", attribute="favourite_colour")
    assert result is True

    recalled = engine.recall_memory(subject="user", attribute="favourite_colour")
    assert recalled is None
    print("Soft deleted — RecallMemory returns None")
    print("PASS")


def test_forget_hard():
    print("\n--- Test: ForgetMemory (hard delete) ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="identity", attribute="name", value="Ludovic")
    result = engine.forget_memory(subject="user", attribute="name", permanent=True)
    assert result is True

    recalled = engine.recall_memory(subject="user", attribute="name")
    assert recalled is None
    print("Hard deleted — RecallMemory returns None")
    print("PASS")


def test_search_memory():
    print("\n--- Test: SearchMemory ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="favourite_colour", value="blue", tags=["colour", "preference"])
    engine.store_memory(subject="user", category="identity", attribute="name", value="Ludovic", tags=["name", "identity"])
    engine.store_memory(subject="wife", category="relationships", attribute="name", value="Catriana", tags=["name", "family"])

    results = engine.search_memory(query="colour")
    assert len(results) > 0
    assert results[0].attribute == "favourite_colour"
    print(f"Search 'colour' → {results[0].attribute} = {results[0].value}")

    results = engine.search_memory(query="name", subject="wife")
    assert len(results) > 0
    assert results[0].value == "Catriana"
    print(f"Search 'name' subject='wife' → {results[0].value}")
    print("PASS")


def test_list_memories():
    print("\n--- Test: ListMemories ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="identity", attribute="name", value="Ludovic")
    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee")
    engine.store_memory(subject="user", category="preferences", attribute="favourite_colour", value="blue")
    engine.store_memory(subject="wife", category="relationships", attribute="name", value="Catriana")

    all_memories = engine.list_memories()
    assert len(all_memories) == 4
    print(f"Total memories: {len(all_memories)}")

    user_memories = engine.list_memories(subject="user")
    assert len(user_memories) == 3
    print(f"User memories: {len(user_memories)}")

    pref_memories = engine.list_memories(category="preferences")
    assert len(pref_memories) == 2
    print(f"Preference memories: {len(pref_memories)}")
    print("PASS")


def test_inferred_cannot_overwrite_user():
    print("\n--- Test: Conflict resolution — inferred cannot overwrite user ---")
    engine = make_engine()

    engine.store_memory(subject="user", category="preferences", attribute="drink", value="coffee", source="user")
    result = engine.update_memory(subject="user", attribute="drink", value="water", confidence=0.7, source="inferred")

    recalled = engine.recall_memory(subject="user", attribute="drink")
    assert recalled.value == "coffee"
    print(f"Value after inferred update attempt: {recalled.value} (user wins)")
    print("PASS")


if __name__ == "__main__":
    print("=" * 50)
    print("Jarvis Knowledge Engine — Standalone Tests")
    print("=" * 50)

    test_store_and_recall()
    test_duplicate_detection()
    test_update_memory()
    test_forget_soft()
    test_forget_hard()
    test_search_memory()
    test_list_memories()
    test_inferred_cannot_overwrite_user()

    print("\n" + "=" * 50)
    print("All tests passed.")
    print("=" * 50)