"""
Tests for Genesis-028 Sprint-001: Generic Property Assignment

Covers:
    - PropertyAssigner: detect_assignment, detect_query, detect_group_query
    - PropertyRecallEngine: store, retrieve, scan_group
    - Integration: full assignment → retrieval round trip

Zero regressions: does not modify or import any Genesis-027 WOS modules.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from core.conversation.property_assigner import (
    PropertyAssigner,
    PropertyAssignment,
    PropertyQuery,
    GroupPropertyQuery,
)
from core.conversation.property_recall_engine import (
    PropertyRecallEngine,
    StoreResult,
    RetrieveResult,
    ScanResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def assigner() -> PropertyAssigner:
    return PropertyAssigner()


@pytest.fixture
def mock_knowledge():
    """Minimal KnowledgeEngine mock."""
    k = MagicMock()
    k.store_memory.return_value = MagicMock()
    k.recall_memory.return_value = None
    k.list_memories.return_value = []
    k.search_memory.return_value = []
    return k


@pytest.fixture
def engine(mock_knowledge) -> PropertyRecallEngine:
    return PropertyRecallEngine(mock_knowledge)


def _make_record(subject: str, attribute: str, value: str):
    """Build a minimal MemoryRecord-like mock."""
    r = MagicMock()
    r.subject = subject
    r.attribute = attribute
    r.value = value
    r.tags = ["entity_property"]
    r.is_expired.return_value = False
    return r


# ===========================================================================
# PropertyAssigner — detect_assignment
# ===========================================================================

class TestDetectAssignment:

    def test_name_is_age_integer(self, assigner):
        result = assigner.detect_assignment("Lucas is 14.")
        assert result is not None
        assert result.subject == "lucas"
        assert result.property_key == "age"
        assert result.value == "14"

    def test_name_is_age_no_period(self, assigner):
        result = assigner.detect_assignment("Leo is 8")
        assert result is not None
        assert result.subject == "leo"
        assert result.property_key == "age"
        assert result.value == "8"

    def test_name_is_colour(self, assigner):
        result = assigner.detect_assignment("Rex is brown.")
        assert result is not None
        assert result.subject == "rex"
        assert result.property_key == "colour"
        assert result.value == "brown"

    def test_name_is_status_offline(self, assigner):
        result = assigner.detect_assignment("Voron is offline.")
        assert result is not None
        assert result.subject == "voron"
        assert result.property_key == "status"
        assert result.value == "offline"

    def test_name_is_status_online(self, assigner):
        result = assigner.detect_assignment("Server Alpha is online.")
        assert result is not None
        assert result.property_key == "status"
        assert result.value == "online"

    def test_weighs_with_unit(self, assigner):
        result = assigner.detect_assignment("Tom weighs 35 kg.")
        assert result is not None
        assert result.subject == "tom"
        assert result.property_key == "weight"
        assert result.value == "35 kg"

    def test_located_in(self, assigner):
        result = assigner.detect_assignment("Server Alpha is located in Sydney.")
        assert result is not None
        assert result.property_key == "location"
        assert result.value == "Sydney"

    def test_priority(self, assigner):
        result = assigner.detect_assignment("Project Atlas is high priority.")
        assert result is not None
        assert result.subject == "project atlas"
        assert result.property_key == "priority"

    def test_question_not_assignment(self, assigner):
        result = assigner.detect_assignment("How old is Leo?")
        assert result is None

    def test_stop_subject_rejected(self, assigner):
        result = assigner.detect_assignment("He is 14.")
        assert result is None

    def test_empty_string(self, assigner):
        assert assigner.detect_assignment("") is None

    def test_none_input(self, assigner):
        assert assigner.detect_assignment(None) is None

    def test_multiword_subject(self, assigner):
        result = assigner.detect_assignment("Rex is brown.")
        assert result is not None
        # Subject is single word
        assert result.subject == "rex"

    def test_colour_black(self, assigner):
        result = assigner.detect_assignment("Tom is black.")
        assert result is not None
        assert result.property_key == "colour"

    def test_colour_white(self, assigner):
        result = assigner.detect_assignment("Luna is white.")
        assert result is not None
        assert result.property_key == "colour"

    def test_age_with_years_old(self, assigner):
        result = assigner.detect_assignment("Lucas is 14 years old.")
        assert result is not None
        assert result.property_key == "age"

    def test_numeric_value_preserved(self, assigner):
        result = assigner.detect_assignment("Tom weighs 35 kg.")
        assert result is not None
        assert "35" in result.value

    def test_confidence_set(self, assigner):
        result = assigner.detect_assignment("Rex is brown.")
        assert result is not None
        assert 0 < result.confidence <= 1.0


# ===========================================================================
# PropertyAssigner — detect_query
# ===========================================================================

class TestDetectQuery:

    def test_how_old_is(self, assigner):
        result = assigner.detect_query("How old is Leo?")
        assert result is not None
        assert result.subject == "leo"
        assert result.property_key == "age"

    def test_what_colour_is(self, assigner):
        result = assigner.detect_query("What colour is Rex?")
        assert result is not None
        assert result.subject == "rex"
        assert result.property_key == "colour"

    def test_what_color_is_american(self, assigner):
        result = assigner.detect_query("What color is Rex?")
        assert result is not None
        assert result.property_key == "colour"

    def test_how_much_does_weigh(self, assigner):
        result = assigner.detect_query("How much does Tom weigh?")
        assert result is not None
        assert result.subject == "tom"
        assert result.property_key == "weight"

    def test_where_is(self, assigner):
        result = assigner.detect_query("Where is Voron?")
        assert result is not None
        assert result.subject == "voron"
        assert result.property_key == "location"

    def test_non_query_returns_none(self, assigner):
        result = assigner.detect_query("Rex is brown.")
        assert result is None

    def test_empty_returns_none(self, assigner):
        assert assigner.detect_query("") is None

    def test_stop_subject_rejected(self, assigner):
        result = assigner.detect_query("How old is he?")
        assert result is None

    def test_is_entity_status(self, assigner):
        result = assigner.detect_query("Is Voron offline?")
        assert result is not None
        assert result.subject == "voron"
        assert result.property_key == "status"


# ===========================================================================
# PropertyAssigner — detect_group_query
# ===========================================================================

class TestDetectGroupQuery:

    def test_which_printer_offline(self, assigner):
        result = assigner.detect_group_query("Which printer is offline?")
        assert result is not None
        assert result.kind_hint == "printer"
        assert result.value == "offline"
        assert result.property_key == "status"

    def test_which_dog_brown(self, assigner):
        result = assigner.detect_group_query("Which dog is brown?")
        assert result is not None
        assert result.kind_hint == "dog"
        assert result.value == "brown"
        assert result.property_key == "colour"

    def test_which_child_is_14(self, assigner):
        result = assigner.detect_group_query("Which child is 14?")
        assert result is not None
        assert result.kind_hint == "child"
        assert result.value == "14"

    def test_non_group_query_none(self, assigner):
        result = assigner.detect_group_query("How old is Leo?")
        assert result is None

    def test_empty_returns_none(self, assigner):
        assert assigner.detect_group_query("") is None


# ===========================================================================
# PropertyRecallEngine — store
# ===========================================================================

class TestPropertyRecallEngineStore:

    def test_store_calls_knowledge_engine(self, engine, mock_knowledge):
        assignment = PropertyAssignment(
            subject="rex", property_key="colour", value="brown"
        )
        result = engine.store(assignment)
        assert result.success is True
        mock_knowledge.store_memory.assert_called_once()

    def test_store_uses_correct_attribute(self, engine, mock_knowledge):
        assignment = PropertyAssignment(
            subject="leo", property_key="age", value="8"
        )
        engine.store(assignment)
        call_kwargs = mock_knowledge.store_memory.call_args
        assert call_kwargs.kwargs["attribute"] == "prop:age"

    def test_store_uses_entity_property_category(self, engine, mock_knowledge):
        assignment = PropertyAssignment(
            subject="voron", property_key="status", value="offline"
        )
        engine.store(assignment)
        call_kwargs = mock_knowledge.store_memory.call_args
        assert call_kwargs.kwargs["category"] == "entity_property"

    def test_store_unknown_entity_does_not_crash(self, engine, mock_knowledge):
        """Storing a property for an entity not in any group should succeed gracefully."""
        assignment = PropertyAssignment(
            subject="unknown_entity", property_key="colour", value="blue"
        )
        result = engine.store(assignment)
        assert result.success is True  # store doesn't require prior entity registration

    def test_store_failure_returns_graceful_result(self, engine, mock_knowledge):
        mock_knowledge.store_memory.side_effect = Exception("Storage error")
        assignment = PropertyAssignment(
            subject="rex", property_key="colour", value="brown"
        )
        result = engine.store(assignment)
        assert result.success is False
        assert "wasn't able" in result.message.lower() or "not" in result.message.lower()

    def test_store_result_contains_subject_and_key(self, engine, mock_knowledge):
        assignment = PropertyAssignment(
            subject="lucas", property_key="age", value="14"
        )
        result = engine.store(assignment)
        assert result.subject == "lucas"
        assert result.property_key == "age"
        assert result.value == "14"


# ===========================================================================
# PropertyRecallEngine — retrieve
# ===========================================================================

class TestPropertyRecallEngineRetrieve:

    def test_retrieve_found(self, engine, mock_knowledge):
        mock_knowledge.recall_memory.return_value = _make_record(
            "leo", "prop:age", "8"
        )
        query = PropertyQuery(subject="leo", property_key="age")
        result = engine.retrieve(query)
        assert result.found is True
        assert result.value == "8"
        assert "Leo" in result.message
        assert "8" in result.message

    def test_retrieve_not_found(self, engine, mock_knowledge):
        mock_knowledge.recall_memory.return_value = None
        query = PropertyQuery(subject="leo", property_key="age")
        result = engine.retrieve(query)
        assert result.found is False
        assert result.value is None

    def test_retrieve_uses_correct_attribute(self, engine, mock_knowledge):
        mock_knowledge.recall_memory.return_value = None
        query = PropertyQuery(subject="rex", property_key="colour")
        engine.retrieve(query)
        mock_knowledge.recall_memory.assert_called_once_with(
            subject="rex", attribute="prop:colour"
        )

    def test_retrieve_colour(self, engine, mock_knowledge):
        mock_knowledge.recall_memory.return_value = _make_record(
            "rex", "prop:colour", "brown"
        )
        query = PropertyQuery(subject="rex", property_key="colour")
        result = engine.retrieve(query)
        assert result.found is True
        assert "brown" in result.message
        assert "Rex" in result.message


# ===========================================================================
# PropertyRecallEngine — scan_group
# ===========================================================================

class TestPropertyRecallEngineScanGroup:

    def test_scan_finds_matching_member(self, engine, mock_knowledge):
        def recall_side_effect(subject, attribute):
            if subject == "voron" and attribute == "prop:status":
                return _make_record("voron", "prop:status", "offline")
            return None

        mock_knowledge.recall_memory.side_effect = recall_side_effect

        gq = GroupPropertyQuery(kind_hint="printer", property_key="status", value="offline")
        result = engine.scan_group(gq, ["voron", "bambu", "prusa"])
        assert result.found is True
        assert "Voron" in result.matches or "voron" in [m.lower() for m in result.matches]

    def test_scan_no_match_returns_not_found(self, engine, mock_knowledge):
        mock_knowledge.recall_memory.return_value = None
        mock_knowledge.search_memory.return_value = []

        gq = GroupPropertyQuery(kind_hint="printer", property_key="status", value="offline")
        result = engine.scan_group(gq, ["bambu", "prusa"])
        assert result.found is False
        assert result.matches == []

    def test_scan_empty_members_no_crash(self, engine, mock_knowledge):
        mock_knowledge.search_memory.return_value = []
        gq = GroupPropertyQuery(kind_hint="printer", property_key="status", value="offline")
        result = engine.scan_group(gq, [])
        assert result.found is False

    def test_scan_multiple_matches(self, engine, mock_knowledge):
        def recall_side_effect(subject, attribute):
            if attribute == "prop:colour" and subject in ("rex", "tom"):
                return _make_record(subject, "prop:colour", "brown")
            return None

        mock_knowledge.recall_memory.side_effect = recall_side_effect

        gq = GroupPropertyQuery(kind_hint="dog", property_key="colour", value="brown")
        result = engine.scan_group(gq, ["rex", "tom", "max"])
        assert result.found is True
        assert len(result.matches) == 2

    def test_scan_case_insensitive_value_match(self, engine, mock_knowledge):
        def recall_side_effect(subject, attribute):
            if subject == "voron":
                return _make_record("voron", "prop:status", "Offline")
            return None

        mock_knowledge.recall_memory.side_effect = recall_side_effect

        gq = GroupPropertyQuery(kind_hint="printer", property_key="status", value="offline")
        result = engine.scan_group(gq, ["voron"])
        assert result.found is True


# ===========================================================================
# Round-trip integration tests
# ===========================================================================

class TestRoundTrip:
    """
    End-to-end tests: detect assignment → store → detect query → retrieve.
    Uses a minimal in-memory store to avoid needing a real KnowledgeEngine.
    """

    def _make_engine_with_store(self):
        """Build a PropertyRecallEngine backed by a dict-based mock store."""
        _store: dict[tuple[str, str], str] = {}

        def store_memory(subject, category, attribute, value, tags=None):
            _store[(subject, attribute)] = value
            r = MagicMock()
            r.subject = subject
            r.attribute = attribute
            r.value = value
            return r

        def recall_memory(subject, attribute):
            val = _store.get((subject, attribute))
            if val is None:
                return None
            return _make_record(subject, attribute, val)

        def list_memories(subject=None, category=None, **kwargs):
            results = []
            for (s, a), v in _store.items():
                if subject and s != subject:
                    continue
                results.append(_make_record(s, a, v))
            return results

        def search_memory(query, **kwargs):
            return []

        k = MagicMock()
        k.store_memory.side_effect = store_memory
        k.recall_memory.side_effect = recall_memory
        k.list_memories.side_effect = list_memories
        k.search_memory.side_effect = search_memory

        return PropertyRecallEngine(k), PropertyAssigner()

    def test_children_age_round_trip(self):
        engine, assigner = self._make_engine_with_store()

        # Store: "Lucas is 14."
        pa = assigner.detect_assignment("Lucas is 14.")
        assert pa is not None
        store_result = engine.store(pa)
        assert store_result.success

        # Store: "Leo is 8."
        pa2 = assigner.detect_assignment("Leo is 8.")
        assert pa2 is not None
        engine.store(pa2)

        # Query: "How old is Leo?"
        pq = assigner.detect_query("How old is Leo?")
        assert pq is not None
        result = engine.retrieve(pq)
        assert result.found is True
        assert result.value == "8"
        assert "Leo" in result.message

    def test_pet_colour_round_trip(self):
        engine, assigner = self._make_engine_with_store()

        # Store: "Rex is brown."
        pa = assigner.detect_assignment("Rex is brown.")
        assert pa is not None
        engine.store(pa)

        # Query: "What colour is Rex?"
        pq = assigner.detect_query("What colour is Rex?")
        assert pq is not None
        result = engine.retrieve(pq)
        assert result.found is True
        assert "brown" in result.message

    def test_device_status_round_trip(self):
        engine, assigner = self._make_engine_with_store()

        # Store: "Voron is offline."
        pa = assigner.detect_assignment("Voron is offline.")
        assert pa is not None
        engine.store(pa)

        # Group query: "Which printer is offline?"
        gq = assigner.detect_group_query("Which printer is offline?")
        assert gq is not None
        scan = engine.scan_group(gq, ["voron", "bambu", "prusa"])
        assert scan.found is True
        assert any("voron" == m.lower() for m in scan.matches)

    def test_multiple_properties_same_entity(self):
        engine, assigner = self._make_engine_with_store()

        engine.store(PropertyAssignment(subject="rex", property_key="colour", value="brown"))
        engine.store(PropertyAssignment(subject="rex", property_key="weight", value="30 kg"))

        colour_result = engine.retrieve(PropertyQuery(subject="rex", property_key="colour"))
        weight_result = engine.retrieve(PropertyQuery(subject="rex", property_key="weight"))

        assert colour_result.found and colour_result.value == "brown"
        assert weight_result.found and weight_result.value == "30 kg"

    def test_unknown_entity_query_graceful(self):
        engine, assigner = self._make_engine_with_store()

        pq = PropertyQuery(subject="nobody", property_key="age")
        result = engine.retrieve(pq)
        assert result.found is False
        assert result.value is None
        # Should not raise

    def test_different_entities_different_values(self):
        engine, assigner = self._make_engine_with_store()

        engine.store(PropertyAssignment(subject="lucas", property_key="age", value="14"))
        engine.store(PropertyAssignment(subject="leo", property_key="age", value="8"))

        r_lucas = engine.retrieve(PropertyQuery(subject="lucas", property_key="age"))
        r_leo = engine.retrieve(PropertyQuery(subject="leo", property_key="age"))

        assert r_lucas.value == "14"
        assert r_leo.value == "8"

    def test_numeric_string_and_multiword_values(self):
        engine, _ = self._make_engine_with_store()

        engine.store(PropertyAssignment(subject="alpha", property_key="location", value="located in Sydney"))
        engine.store(PropertyAssignment(subject="atlas", property_key="priority", value="high priority"))
        engine.store(PropertyAssignment(subject="tom", property_key="weight", value="35 kg"))

        r1 = engine.retrieve(PropertyQuery(subject="alpha", property_key="location"))
        r2 = engine.retrieve(PropertyQuery(subject="atlas", property_key="priority"))
        r3 = engine.retrieve(PropertyQuery(subject="tom", property_key="weight"))

        assert r1.found and "Sydney" in r1.value
        assert r2.found and "high priority" in r2.value
        assert r3.found and "35 kg" in r3.value