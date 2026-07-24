"""
GC-012 — Contextual Fact Completion Tests

Verifies that bare continuation sentences are correctly inferred
as pet name assignments when the knowledge store already contains
a pet quantity fact.

Coverage:
  - "I have 3 cats." then "Tom, Tim and Tam." → pet names stored
  - "I have 2 dogs." then "Rex and Tom." → pet names stored
  - Explicit form still works: "Their names are Rex and Tom."
  - Non-name continuations not misclassified
  - Single name continuation works
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call
from datetime import UTC, datetime

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_observer import ConversationObserver


def make_pet_record(value="3 cats"):
    r = MagicMock()
    r.value = value
    r.attribute = "pets"
    r.subject = "user"
    r.tags = ["pet", "auto-extracted"]
    r.updated_at = datetime.now(UTC)
    return r


def make_engine(pets_value=None):
    engine = MagicMock()
    engine.store_memory.return_value = MagicMock()
    engine.update_memory.return_value = MagicMock()
    if pets_value:
        engine.recall_memory.return_value = make_pet_record(pets_value)
    else:
        engine.recall_memory.return_value = None
    return engine


class TestContextualPetNameInference:

    def test_bare_names_after_cats_stored_as_pet_names(self):
        """'I have 3 cats.' then 'Tom, Tim and Tam.' → pet names stored."""
        engine = make_engine(pets_value="3 cats")
        observer = ConversationObserver(engine)
        observer.observe("Tom, Tim and Tam.", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" in stored_attrs

    def test_bare_names_after_dogs_stored_as_pet_names(self):
        """'I have 2 dogs.' then 'Rex and Tom.' → pet names stored."""
        engine = make_engine(pets_value="2 dogs")
        observer = ConversationObserver(engine)
        observer.observe("Rex and Tom.", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" in stored_attrs

    def test_single_name_after_pets_stored(self):
        """Single name continuation works."""
        engine = make_engine(pets_value="a cat")
        observer = ConversationObserver(engine)
        observer.observe("Whiskers.", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" in stored_attrs

    def test_no_inference_without_pet_context(self):
        """Without a stored pet fact, bare names not stored as pet names."""
        engine = make_engine(pets_value=None)
        observer = ConversationObserver(engine)
        observer.observe("Tom, Tim and Tam.", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" not in stored_attrs

    def test_explicit_form_still_works(self):
        """'Their names are Rex and Tom.' still works as before."""
        engine = make_engine(pets_value=None)
        observer = ConversationObserver(engine)
        observer.observe("Their names are Rex and Tom.", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" in stored_attrs

    def test_noise_words_not_stored_as_names(self):
        """Generic words not stored as pet names."""
        engine = make_engine(pets_value="3 cats")
        observer = ConversationObserver(engine)
        observer.observe("yes", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" not in stored_attrs

    def test_question_not_stored_as_names(self):
        """Questions not stored as pet names."""
        engine = make_engine(pets_value="3 cats")
        observer = ConversationObserver(engine)
        observer.observe("What are their names?", "")
        stored_attrs = [c.kwargs.get('attribute') or c.args[2]
                        for c in engine.store_memory.call_args_list]
        assert "pet names" not in stored_attrs


# ===========================================================================
# Recall pattern tests — "What are their names?" routes to ConversationRecall
# ===========================================================================

class TestPetNameRecallPattern:

    def test_what_are_their_names_can_answer(self):
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        r = ConversationRecall(MagicMock())
        assert r.can_answer("What are their names?")

    def test_what_are_my_dogs_names_can_answer(self):
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        r = ConversationRecall(MagicMock())
        assert r.can_answer("What are my dogs' names?")

    def test_what_are_my_cats_names_can_answer(self):
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        r = ConversationRecall(MagicMock())
        assert r.can_answer("What are my cats' names?")

    def test_recall_pet_names_with_stored_record(self):
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        engine = MagicMock()
        pet_names = MagicMock()
        pet_names.value = "Tom, Tim and Tam"
        pet_type = MagicMock()
        pet_type.value = "3 cats"
        engine.recall_memory.side_effect = lambda s, a: (
            pet_names if a == "pet names" else
            pet_type if a == "pets" else None
        )
        r = ConversationRecall(engine)
        result = r.answer("What are their names?")
        assert result.found
        assert "Tom" in result.answer
        assert "Tim" in result.answer
        assert "Tam" in result.answer

    def test_recall_pet_names_not_stored_returns_authoritative_miss(self):
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        engine = MagicMock()
        engine.recall_memory.return_value = None
        r = ConversationRecall(engine)
        result = r.answer("What are their names?")
        assert result.found  # authoritative miss — no AI fallback
        assert "don't have" in result.answer.lower() or "not" in result.answer.lower()

    def test_who_are_they_golden_conversation(self):
        """GC-001 golden conversation still passes."""
        from core.conversation.conversation_recall import ConversationRecall
        from unittest.mock import MagicMock
        engine = MagicMock()
        pet_names = MagicMock()
        pet_names.value = "Rex and Tom"
        pet_names.attribute = "pet names"
        pet_names.tags = ["pet", "auto-extracted", "derived"]
        pet_type = MagicMock()
        pet_type.value = "2 dogs"
        engine.recall_memory.side_effect = lambda s, a: (
            pet_type if (s == "user" and a == "pets") else None
        )
        engine.search_memory.return_value = [pet_names]
        r = ConversationRecall(engine)
        result = r.answer("Who are Rex and Tom?")
        assert result.found
        assert "dogs" in result.answer.lower()