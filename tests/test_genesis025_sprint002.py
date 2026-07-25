"""
Genesis-025 Sprint-002 — SlotCompletionEngine Tests

Coverage:
  - Group declaration detection → MemoryDetection
  - Explicit slot fill detection → MemoryDetection
  - Implicit slot fill (bare name list) → MemoryDetection
  - Backward-compatible keys preserved
  - No detection when no context
  - Parity tests: same input → same result as existing pet-specific code
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.slot_completion_engine import SlotCompletionEngine


# ===========================================================================
# 1. Group declarations → MemoryDetection
# ===========================================================================

class TestGroupDeclarations:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_i_have_2_dogs(self):
        result = self.engine.detect("I have 2 dogs.")
        assert result is not None
        assert result.key == "pets"
        assert "dogs" in result.value

    def test_i_have_3_cats(self):
        result = self.engine.detect("I have 3 cats.")
        assert result is not None
        assert result.key == "pets"
        assert "cats" in result.value

    def test_i_have_2_children(self):
        result = self.engine.detect("I have 2 children.")
        assert result is not None
        assert result.key == "people"

    def test_i_have_3_guitars(self):
        result = self.engine.detect("I have 3 guitars.")
        assert result is not None
        assert result.key == "instruments"

    def test_i_have_2_cars(self):
        result = self.engine.detect("I have 2 cars.")
        assert result is not None
        assert result.key == "vehicles"

    def test_question_not_detected(self):
        result = self.engine.detect("How many dogs do I have?")
        assert result is None

    def test_empty_message(self):
        result = self.engine.detect("")
        assert result is None


# ===========================================================================
# 2. Explicit slot fills → MemoryDetection
# ===========================================================================

class TestExplicitSlotFills:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_their_names_are_animal(self):
        result = self.engine.detect(
            "Their names are Rex and Tom.",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"
        assert "Rex" in result.value
        assert "Tom" in result.value

    def test_their_names_are_person(self):
        result = self.engine.detect(
            "Their names are Alex and Emma.",
            active_kind="person",
        )
        assert result is not None
        assert result.key == "people names"
        assert "Alex" in result.value

    def test_no_explicit_fill_without_active_kind(self):
        result = self.engine.detect("Their names are Rex and Tom.")
        # No active_kind — should still detect as explicit fill
        # because EntityGroupRegistry.detect_slot_fill handles it
        # Only None if active_kind is required and missing
        # (In this implementation, explicit fills need active_kind)
        assert result is None

    def test_skips_already_filled_slot(self):
        result = self.engine.detect(
            "Their names are Rex and Tom.",
            active_kind="animal",
            filled_slots={"names": "already filled"},
        )
        assert result is None


# ===========================================================================
# 3. Implicit slot fills (bare continuations)
# ===========================================================================

class TestImplicitSlotFills:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_bare_names_after_dogs(self):
        result = self.engine.detect(
            "Rex and Tom.",
            active_topic="2 dogs",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"
        assert "Rex" in result.value

    def test_bare_names_after_cats(self):
        result = self.engine.detect(
            "Tom, Tim and Tam.",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_lowercase_names_after_cats(self):
        result = self.engine.detect(
            "tom, tim and tam.",
            active_topic="3 cats",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_bare_names_after_children(self):
        result = self.engine.detect(
            "Alex and Emma.",
            active_topic="2 children",
            active_kind="person",
        )
        assert result is not None
        assert result.key == "people names"

    def test_no_implicit_fill_without_active_topic(self):
        result = self.engine.detect("Rex and Tom.")
        assert result is None

    def test_noise_not_detected_as_names(self):
        result = self.engine.detect(
            "yes",
            active_topic="2 dogs",
            active_kind="animal",
        )
        assert result is None

    def test_question_not_detected_as_names(self):
        result = self.engine.detect(
            "What are their names?",
            active_topic="2 dogs",
            active_kind="animal",
        )
        assert result is None


# ===========================================================================
# 4. Parity tests — same result as existing pet-specific code
# ===========================================================================

class TestParityWithExistingCode:
    """
    These tests verify that SlotCompletionEngine produces the same
    MemoryDetection keys and values as the existing pet-specific code
    in MemoryDetector and ConversationObserver.

    Parity must be maintained throughout Sprint-002 so existing
    MemorySkill acknowledgements and ConversationRecall patterns
    continue to work without modification.
    """

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_declaration_key_matches_existing(self):
        """'I have 2 dogs.' → key='pets' (matches MemoryDetector output)"""
        result = self.engine.detect("I have 2 dogs.")
        assert result.key == "pets"

    def test_slot_fill_key_matches_existing(self):
        """'Their names are...' → key='pet names' (matches existing)"""
        result = self.engine.detect(
            "Their names are Rex and Tom.",
            active_kind="animal",
        )
        assert result.key == "pet names"

    def test_implicit_fill_key_matches_existing(self):
        """Bare names after pets → key='pet names' (matches detect_with_context)"""
        result = self.engine.detect(
            "Rex and Tom.",
            active_topic="2 dogs",
            active_kind="animal",
        )
        assert result.key == "pet names"

    def test_confidence_reasonable(self):
        result = self.engine.detect("I have 2 dogs.")
        assert 0.7 <= result.confidence <= 1.0


# ===========================================================================
# 5. Edge cases
# ===========================================================================

class TestEdgeCases:

    def setup_method(self):
        self.engine = SlotCompletionEngine()

    def test_single_name_implicit_fill(self):
        result = self.engine.detect(
            "Whiskers.",
            active_topic="a cat",
            active_kind="animal",
        )
        assert result is not None
        assert result.key == "pet names"

    def test_and_my_favourite_food_not_detected(self):
        """Preference statements should not be detected as group declarations."""
        result = self.engine.detect("And my favourite food is pizza.")
        assert result is None

    def test_who_are_rex_and_tom_not_detected(self):
        """Questions should not be detected."""
        result = self.engine.detect("Who are Rex and Tom?")
        assert result is None

    def test_i_have_a_brother_detected(self):
        result = self.engine.detect("I have a brother.")
        assert result is not None
        assert result.key == "people"