"""
GC-012 â€” Contextual Fact Completion Tests

Genesis-025 Sprint-003 update:
    _infer_pet_name_continuation() removed from ConversationObserver.
    Bare name list inference now handled by SlotCompletionEngine at Step 4.
    Tests updated to validate SlotCompletionEngine for inference cases,
    ConversationObserver for explicit extraction cases.

Coverage:
  - SlotCompletionEngine: bare name inference after pet context
  - ConversationObserver: explicit form extraction still works
  - ConversationRecall: pet name recall pattern
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from datetime import UTC, datetime

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_observer import ConversationObserver
from core.conversation.slot_completion_engine import SlotCompletionEngine


def make_pet_record(value="3 cats"):
    r = MagicMock()
    r.value = value
    r.attribute = "pets"
    r.subject = "user"
    r.tags = ["pet", "auto-extracted"]
    r.updated_at = datetime.now(UTC)
    return r


def make_engine_mock(pets_value=None):
    engine = MagicMock()
    engine.store_memory.return_value = MagicMock()
    engine.update_memory.return_value = MagicMock()
    if pets_value:
        engine.recall_memory.return_value = make_pet_record(pets_value)
    else:
        engine.recall_memory.return_value = None
    return engine


# ===========================================================================
# 1. SlotCompletionEngine â€” bare name inference (replaces Observer inference)
#    Genesis-025 Sprint-003: inference moved from ConversationObserver to here
# ===========================================================================

class TestSlotCompletionEngineBareNameInference:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_bare_names_after_cats_detected(self):
        """SlotCompletionEngine detects 'Tom, Tim and Tam.' after cat context."""
        result = self.engine.detect(
            "Tom, Tim and Tam.",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"
        assert "Tom" in result.value

    def test_bare_names_after_dogs_detected(self):
        """SlotCompletionEngine detects 'Rex and Tom.' after dog context."""
        result = self.engine.detect(
            "Rex and Tom.",
            active_topic="2 dogs",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_single_name_after_pets_detected(self):
        result = self.engine.detect(
            "Whiskers.",
            active_topic="a cat",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_no_inference_without_active_topic(self):
        """Without active_topic, bare names not detected as pet names."""
        result = self.engine.detect("Tom, Tim and Tam.")
        assert result is None

    def test_noise_not_detected(self):
        result = self.engine.detect(
            "yes",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is None

    def test_question_not_detected(self):
        result = self.engine.detect(
            "What are their names?",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is None


# ===========================================================================
# 2. ConversationObserver â€” explicit extraction still works
# ===========================================================================

class TestConversationObserverExplicitExtraction:

    def test_explicit_form_not_stored_by_observer(self):
        """CV-001: FactExtractor no longer extracts possession facts.
        SlotCompletionEngine at Step 4 handles this. Observer only journals."""
        engine = make_engine_mock()
        observer = ConversationObserver(engine)
        observer.observe("Their names are Rex and Tom.", "")
        stored_attrs = [
            c.kwargs.get('attribute') or (c.args[2] if len(c.args) > 2 else '')
            for c in engine.store_memory.call_args_list
        ]
        # Only journal entry stored - FactExtractor no longer extracts pet names
        assert "pet names" not in stored_attrs
    def test_observer_no_longer_does_inference(self):
        """ConversationObserver no longer infers bare name lists."""
        engine = make_engine_mock(pets_value="3 cats")
        observer = ConversationObserver(engine)
        observer.observe("Tom, Tim and Tam.", "")
        stored_attrs = [
            c.kwargs.get('attribute') or (c.args[2] if len(c.args) > 2 else '')
            for c in engine.store_memory.call_args_list
        ]
        # Only journal entry stored â€” no pet names inferred
        assert "pet names" not in stored_attrs


# ===========================================================================
# 3. ConversationRecall â€” pet name recall pattern (unchanged)
# ===========================================================================

class TestPetNameRecallPattern:

    def test_what_are_their_names_can_answer(self):
        from core.conversation.conversation_recall import ConversationRecall
        r = ConversationRecall(MagicMock())
        assert r.can_answer("What are their names?")

    def test_what_are_my_dogs_names_can_answer(self):
        from core.conversation.conversation_recall import ConversationRecall
        r = ConversationRecall(MagicMock())
        assert r.can_answer("What are my dogs' names?")

    def test_recall_pet_names_with_stored_record(self):
        from core.conversation.conversation_recall import ConversationRecall
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

    def test_who_are_they_golden_conversation(self):
        from core.conversation.conversation_recall import ConversationRecall
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