"""
Tests for Genesis-026: Unknown Entity Classification Fix (Pre Sprint-003)

Verifies that unrecognised entity nouns (planes, guitars, servers, etc.)
are never silently mapped onto an existing schema (pets, pet names, etc.).

Regression suite for the bug:
    "I have 2 planes." → attribute='pets', value='2 planes'   ← BUG (fixed)
    "I have 2 planes." → None                                  ← CORRECT

Two layers are tested:
    1. MemoryDetector in isolation (unit)
    2. SlotCompletionEngine in isolation (unit)

Golden conversation regression:
    Known entity (dogs) must still work end-to-end.
    Unknown entity (planes) must not corrupt the schema.
"""

import pytest

from core.conversation.memory_detector import MemoryDetector
from core.conversation.slot_completion_engine import SlotCompletionEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector():
    return MemoryDetector()


@pytest.fixture
def slot_engine():
    return SlotCompletionEngine()


# ---------------------------------------------------------------------------
# MemoryDetector — unknown nouns must NOT match "pets"
# ---------------------------------------------------------------------------

class TestMemoryDetectorUnknownEntities:

    def test_planes_not_classified_as_pets(self, detector):
        result = detector.detect("I have 2 planes.")
        assert result is None or result.key != "pets", (
            f"'I have 2 planes.' must not produce key='pets', got {result}"
        )

    def test_planes_not_classified_as_pets_no_period(self, detector):
        result = detector.detect("I have 2 planes")
        assert result is None or result.key != "pets"

    def test_guitars_not_classified_as_pets(self, detector):
        result = detector.detect("I have 3 guitars.")
        assert result is None or result.key != "pets"

    def test_servers_not_classified_as_pets(self, detector):
        result = detector.detect("I have 5 servers.")
        assert result is None or result.key != "pets"

    def test_children_not_classified_as_pets(self, detector):
        # "children" is a person kind — not pets
        result = detector.detect("I have 2 children.")
        assert result is None or result.key != "pets"

    def test_cars_not_classified_as_pets(self, detector):
        result = detector.detect("I have 2 cars.")
        assert result is None or result.key != "pets"

    def test_bikes_not_classified_as_pets(self, detector):
        result = detector.detect("I have 3 bikes.")
        assert result is None or result.key != "pets"


# ---------------------------------------------------------------------------
# MemoryDetector — known animal nouns MUST still match "pets"
# ---------------------------------------------------------------------------

class TestMemoryDetectorKnownAnimals:

    def test_dogs_classified_as_pets(self, detector):
        result = detector.detect("I have 2 dogs.")
        assert result is not None
        assert result.key == "pets"
        assert "dogs" in result.value

    def test_cats_classified_as_pets(self, detector):
        result = detector.detect("I have 3 cats.")
        assert result is not None
        assert result.key == "pets"
        assert "cats" in result.value

    def test_fish_classified_as_pets(self, detector):
        result = detector.detect("I have some fish.")
        assert result is not None
        assert result.key == "pets"

    def test_rabbits_classified_as_pets(self, detector):
        result = detector.detect("I have 2 rabbits.")
        assert result is not None
        assert result.key == "pets"

    def test_birds_classified_as_pets(self, detector):
        result = detector.detect("I have a bird.")
        assert result is not None
        assert result.key == "pets"

    def test_pets_generic_classified_as_pets(self, detector):
        result = detector.detect("I have 2 pets.")
        assert result is not None
        assert result.key == "pets"


# ---------------------------------------------------------------------------
# MemoryDetector — "Their names are" must NOT produce "pet names"
# for unknown entities (no active kind context)
# ---------------------------------------------------------------------------

class TestMemoryDetectorTheirNames:

    def test_their_names_no_context_returns_none(self, detector):
        """Without active animal context, 'Their names are X' must not
        be stored as pet names. SlotCompletionEngine owns this pattern."""
        result = detector.detect("Their names are Jumbo and Jet.")
        # Must either return None or not store as "pet names"
        assert result is None or result.key != "pet names", (
            f"'Their names are Jumbo and Jet.' must not produce key='pet names' "
            f"without active animal context, got {result}"
        )

    def test_their_names_with_unknown_context_hint_returns_none(self, detector):
        """Context hint for unknown entity must not trigger pet names."""
        result = detector.detect_with_context(
            "Their names are Jumbo and Jet.",
            context_hint="2 planes",
        )
        assert result is None or result.key != "pet names"

    def test_their_names_with_animal_context_hint_accepted(self, detector):
        """Bare name list with animal context hint should still work via
        detect_with_context (GC-012 path — implicit fill)."""
        result = detector.detect_with_context(
            "Rex and Tom.",
            context_hint="2 dogs",
        )
        assert result is not None
        assert result.key == "pet names"


# ---------------------------------------------------------------------------
# SlotCompletionEngine — unknown entity must return None
# ---------------------------------------------------------------------------

class TestSlotCompletionEngineUnknownEntities:

    def test_planes_declaration_returns_none(self, slot_engine):
        result = slot_engine.detect("I have 2 planes.")
        assert result is None, (
            f"SlotCompletionEngine must return None for unknown entity 'planes', "
            f"got key={result.key!r} value={result.value!r}"
        )

    def test_planes_slot_fill_returns_none_without_active_kind(self, slot_engine):
        result = slot_engine.detect(
            "Their names are Jumbo and Jet.",
            active_topic="",
        )
        assert result is None

    def test_planes_slot_fill_returns_none_with_unknown_topic(self, slot_engine):
        result = slot_engine.detect(
            "Their names are Jumbo and Jet.",
            active_topic="2 planes",
        )
        assert result is None


# ---------------------------------------------------------------------------
# SlotCompletionEngine — known entities must still work
# ---------------------------------------------------------------------------

class TestSlotCompletionEngineKnownEntities:

    def test_dogs_declaration_detected(self, slot_engine):
        result = slot_engine.detect("I have 2 dogs.")
        assert result is not None
        assert result.key == "pets"
        assert result.value == "2 dogs"
        assert result.is_group_declaration is True

    def test_dogs_names_slot_fill_detected(self, slot_engine):
        result = slot_engine.detect(
            "Their names are Rex and Tom.",
            active_topic="2 dogs",
        )
        assert result is not None
        assert result.key == "pet names"
        assert "Rex" in result.value
        assert "Tom" in result.value

    def test_cats_declaration_detected(self, slot_engine):
        result = slot_engine.detect("I have 3 cats.")
        assert result is not None
        assert result.key == "pets"

    def test_vehicles_declaration_detected(self, slot_engine):
        result = slot_engine.detect("I have 2 cars.")
        assert result is not None
        assert result.key == "vehicles"
        assert result.is_group_declaration is True

    def test_children_declaration_detected(self, slot_engine):
        result = slot_engine.detect("I have 2 children.")
        assert result is not None
        assert result.key == "people"
        assert result.is_group_declaration is True


# ---------------------------------------------------------------------------
# Golden conversation regression
# Planes conversation must not corrupt a subsequent dogs conversation
# ---------------------------------------------------------------------------

class TestGoldenConversationRegression:

    def test_planes_then_dogs_no_corruption(self, detector, slot_engine):
        """
        Regression for the original bug:
            User: I have 2 planes.
            User: Their names are Jumbo and Jet.
            User: I have 2 dogs.
            User: Their names are Rex and Tom.
            → Dogs must produce "Rex and Tom", NOT "Jumbo and Jet"

        This test verifies the detection layer produces correct keys.
        It does not test KnowledgeEngine storage (integration test scope).
        """
        # Turn 1: planes declaration — must not produce pets
        r1 = slot_engine.detect("I have 2 planes.") or detector.detect("I have 2 planes.")
        assert r1 is None or r1.key != "pets", (
            f"Turn 1: planes must not be classified as pets. Got {r1}"
        )

        # Turn 2: plane names — no active kind, must return None
        active_topic_after_planes = ""  # planes never set active_topic
        r2 = slot_engine.detect(
            "Their names are Jumbo and Jet.",
            active_topic=active_topic_after_planes,
        ) or detector.detect("Their names are Jumbo and Jet.")
        assert r2 is None or r2.key != "pet names", (
            f"Turn 2: plane names must not be stored as pet names. Got {r2}"
        )

        # Turn 3: dogs declaration — must produce pets
        r3 = slot_engine.detect("I have 2 dogs.")
        assert r3 is not None
        assert r3.key == "pets"
        assert r3.value == "2 dogs"
        active_topic_after_dogs = r3.value  # "2 dogs"

        # Turn 4: dog names — must produce pet names with Rex and Tom
        r4 = slot_engine.detect(
            "Their names are Rex and Tom.",
            active_topic=active_topic_after_dogs,
        )
        assert r4 is not None
        assert r4.key == "pet names"
        assert "Rex" in r4.value
        assert "Tom" in r4.value
        # Must NOT contain Jumbo or Jet
        assert "Jumbo" not in r4.value
        assert "Jet" not in r4.value