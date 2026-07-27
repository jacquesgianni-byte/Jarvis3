"""
GC-002 â€” Relationship Recall Tests

Coverage:
  - FactExtractor: workplace extraction ("I work at X")
  - FactExtractor: PET and WORKPLACE fact types exist
  - ConversationRecall: workplace query ("Where do I work?")
  - ConversationRecall: relationship recall via "{X} role" attributes
    * pets (GC-001 backwards compatibility)
    * family (son, daughter)
    * work relationships (manager)
    * favourite places
  - ConversationRecall: plural person query ("Who are Rex and Tom?")
  - No regressions against existing sprint-001 behaviour
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.fact_extractor import ExtractedFact, FactExtractor, FactType
from core.conversation.conversation_recall import ConversationRecall


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_knowledge():
    k = MagicMock()
    k.recall_memory.return_value = None
    k.search_memory.return_value = []
    k.store_memory.return_value = MagicMock()
    return k


def make_mock_record(attribute, value, subject="user", tags=None):
    r = MagicMock()
    r.attribute = attribute
    r.value = value
    r.subject = subject
    r.tags = tags or []
    r.updated_at = datetime.now(UTC)
    return r


# ===========================================================================
# 1. FACT EXTRACTOR â€” Workplace extraction
# ===========================================================================

class TestFactExtractorWorkplace:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_i_work_at(self):
        facts = self.extractor.extract("I work at Academy of Healthcare.")
        workplace = [f for f in facts if f.fact_type == FactType.WORKPLACE]
        assert len(workplace) == 1
        assert "Academy of Healthcare" in workplace[0].value

    def test_i_work_for(self):
        facts = self.extractor.extract("I work for Google.")
        workplace = [f for f in facts if f.fact_type == FactType.WORKPLACE]
        assert len(workplace) == 1
        assert "Google" in workplace[0].value

    def test_i_am_employed_at(self):
        facts = self.extractor.extract("I am employed at Microsoft.")
        workplace = [f for f in facts if f.fact_type == FactType.WORKPLACE]
        assert len(workplace) == 1
        assert "Microsoft" in workplace[0].value

    def test_workplace_attribute(self):
        facts = self.extractor.extract("I work at Academy of Healthcare.")
        workplace = [f for f in facts if f.fact_type == FactType.WORKPLACE]
        assert workplace[0].attribute == "workplace"
        assert workplace[0].subject == "user"

    def test_workplace_confidence(self):
        facts = self.extractor.extract("I work at Academy of Healthcare.")
        workplace = [f for f in facts if f.fact_type == FactType.WORKPLACE]
        assert 0.7 <= workplace[0].confidence <= 1.0

    def test_question_not_extracted(self):
        facts = self.extractor.extract("Where do I work?")
        assert facts == []


# ===========================================================================
# 2. FACT EXTRACTOR - PET fact type
#
# CV-001 update (Genesis-026): _extract_possessions() now returns [].
# Possession detection ("I have 2 dogs", "Their names are Rex and Tom")
# is handled exclusively by SlotCompletionEngine at Step 4 - before AI,
# before post-turn - which is the correct single interpretation path.
#
# These tests now verify the NEW correct behaviour: FactExtractor does NOT
# extract possession facts, preventing ontology corruption for non-animal
# entities (servers, cars, children, planes).
# ===========================================================================

class TestFactExtractorPets:

    def setup_method(self):
        self.extractor = FactExtractor()

    def test_i_have_dogs_not_extracted_by_fact_extractor(self):
        """CV-001: FactExtractor must not extract possession facts."""
        facts = self.extractor.extract("I have 2 dogs.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

    def test_their_names_are_not_extracted_by_fact_extractor(self):
        """CV-001: FactExtractor must not extract name slot fills."""
        facts = self.extractor.extract("Their names are Rex and Tom.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

    def test_i_have_servers_not_extracted(self):
        """CV-001: Non-animal possession must not produce any fact."""
        facts = self.extractor.extract("I have 5 servers.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

    def test_i_have_cars_not_extracted(self):
        """CV-001: Vehicle possession must not produce any fact."""
        facts = self.extractor.extract("I have 2 cars.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

    def test_i_have_children_not_extracted(self):
        """CV-001: Person possession must not produce any fact."""
        facts = self.extractor.extract("I have 3 children.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

    def test_i_have_planes_not_extracted(self):
        """CV-001: Unknown entity possession must not produce any fact."""
        facts = self.extractor.extract("I have 2 planes.")
        pets = [f for f in facts if f.fact_type == FactType.PET]
        assert len(pets) == 0

# ===========================================================================
# 3. FACT EXTRACTOR â€” FactType completeness
# ===========================================================================

class TestFactTypeCompleteness:

    def test_pet_fact_type_exists(self):
        assert hasattr(FactType, "PET")

    def test_workplace_fact_type_exists(self):
        assert hasattr(FactType, "WORKPLACE")

    def test_all_original_fact_types_exist(self):
        for name in ["PROJECT", "MILESTONE", "PERSON", "TASK",
                     "DECISION", "ACHIEVEMENT", "PREFERENCE", "UNKNOWN"]:
            assert hasattr(FactType, name)


# ===========================================================================
# 4. CONVERSATION RECALL â€” Workplace query
# ===========================================================================

class TestConversationRecallWorkplace:

    def test_can_answer_where_do_i_work(self):
        recall = ConversationRecall(make_mock_knowledge())
        assert recall.can_answer("Where do I work?")

    def test_can_answer_where_am_i_employed(self):
        recall = ConversationRecall(make_mock_knowledge())
        assert recall.can_answer("Where am I employed?")

    def test_recalls_workplace(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record(
            "workplace", "Academy of Healthcare"
        )
        recall = ConversationRecall(k)
        result = recall.answer("Where do I work?")
        assert result.found
        assert "Academy of Healthcare" in result.answer

    def test_workplace_miss_returns_not_found(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        recall = ConversationRecall(k)
        result = recall.answer("Where do I work?")
        assert not result.found


# ===========================================================================
# 5. CONVERSATION RECALL â€” Pet recall (GC-001 backwards compat)
# ===========================================================================

class TestConversationRecallPets:

    def test_who_are_rex_and_tom(self):
        k = make_mock_knowledge()
        pet_names_record = make_mock_record(
            "pet names", "Rex and Tom",
            tags=["pet", "auto-extracted", "derived"]
        )
        pets_record = make_mock_record("pets", "2 dogs")
        k.recall_memory.side_effect = lambda s, a: (
            pets_record if (s == "user" and a == "pets") else None
        )
        k.search_memory.return_value = [pet_names_record]
        recall = ConversationRecall(k)
        result = recall.answer("Who are Rex and Tom?")
        assert result.found
        assert "Rex and Tom" in result.answer
        assert "dogs" in result.answer

    def test_pet_answer_without_pets_record_uses_fallback(self):
        k = make_mock_knowledge()
        pet_names_record = make_mock_record(
            "pet names", "Rex and Tom",
            tags=["pet", "auto-extracted", "derived"]
        )
        k.recall_memory.return_value = None
        k.search_memory.return_value = [pet_names_record]
        recall = ConversationRecall(k)
        result = recall.answer("Who are Rex and Tom?")
        assert result.found
        assert "Rex and Tom" in result.answer
        assert "pets" in result.answer

    def test_plural_who_are_matches(self):
        recall = ConversationRecall(make_mock_knowledge())
        assert recall.can_answer("Who are Rex and Tom?")

    def test_singular_who_is_still_matches(self):
        recall = ConversationRecall(make_mock_knowledge())
        assert recall.can_answer("Who is Claude?")


# ===========================================================================
# 6. CONVERSATION RECALL â€” Family relationship recall
# ===========================================================================

class TestConversationRecallFamily:

    def test_who_is_son(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = [
            make_mock_record("son role", "Alex", tags=["person", "auto-extracted"])
        ]
        recall = ConversationRecall(k)
        result = recall.answer("Who is Alex?")
        assert result.found
        assert "Alex" in result.answer
        assert "son" in result.answer.lower()

    def test_who_is_daughter(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = [
            make_mock_record("daughter role", "Emma", tags=["person", "auto-extracted"])
        ]
        recall = ConversationRecall(k)
        result = recall.answer("Who is Emma?")
        assert result.found
        assert "Emma" in result.answer
        assert "daughter" in result.answer.lower()


# ===========================================================================
# 7. CONVERSATION RECALL â€” Work relationship recall
# ===========================================================================

class TestConversationRecallWorkRelationships:

    def test_who_is_manager(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = [
            make_mock_record("manager role", "Sarah", tags=["person", "auto-extracted"])
        ]
        recall = ConversationRecall(k)
        result = recall.answer("Who is Sarah?")
        assert result.found
        assert "Sarah" in result.answer
        assert "manager" in result.answer.lower()

    def test_unknown_role_uses_fallback_template(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = [
            make_mock_record("mentor role", "James", tags=["person", "auto-extracted"])
        ]
        recall = ConversationRecall(k)
        result = recall.answer("Who is James?")
        assert result.found
        assert "James" in result.answer
        assert "mentor" in result.answer.lower()


# ===========================================================================
# 8. CONVERSATION RECALL â€” Favourite places
# ===========================================================================

class TestConversationRecallFavouritePlaces:

    def test_favourite_cafe_role(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = [
            make_mock_record(
                "favourite cafe role", "Little Bean",
                tags=["person", "auto-extracted"]
            )
        ]
        recall = ConversationRecall(k)
        result = recall.answer("Who is Little Bean?")
        assert result.found
        assert "Little Bean" in result.answer


# ===========================================================================
# 9. CONVERSATION RECALL â€” can_answer coverage
# ===========================================================================

class TestConversationRecallCanAnswer:

    def setup_method(self):
        self.recall = ConversationRecall(make_mock_knowledge())

    def test_who_is_query(self):
        assert self.recall.can_answer("Who is Claude?")

    def test_who_are_query(self):
        assert self.recall.can_answer("Who are Rex and Tom?")

    def test_where_do_i_work(self):
        assert self.recall.can_answer("Where do I work?")

    def test_project_query(self):
        assert self.recall.can_answer("What project am I working on?")

    def test_unrelated_query_false(self):
        assert not self.recall.can_answer("Write me a poem.")

    def test_weather_false(self):
        assert not self.recall.can_answer("What is the weather?")


# ===========================================================================
# 10. BACKWARDS COMPATIBILITY â€” sprint-001 recall unchanged
# ===========================================================================

class TestBackwardsCompatibility:

    def test_project_recall_unchanged(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record("current project", "Jarvis OS")
        recall = ConversationRecall(k)
        result = recall.answer("What project am I working on?")
        assert result.found
        assert "Jarvis OS" in result.answer

    def test_person_role_recall_unchanged(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = make_mock_record(
            "role", "senior engineer", subject="claude"
        )
        recall = ConversationRecall(k)
        result = recall.answer("Who is Claude?")
        assert result.found
        assert "engineer" in result.answer.lower()

    def test_miss_returns_not_found(self):
        k = make_mock_knowledge()
        k.recall_memory.return_value = None
        k.search_memory.return_value = []
        recall = ConversationRecall(k)
        result = recall.answer("What project am I working on?")
        assert not result.found
        assert result.answer == ""

    def test_extractor_does_not_mutate_input(self):
        extractor = FactExtractor()
        original = "I work at Academy of Healthcare."
        extractor.extract(original)
        assert original == "I work at Academy of Healthcare."