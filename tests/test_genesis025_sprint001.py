"""
Genesis-025 Sprint-001 — EntityGroupRegistry Tests

Coverage:
  - GroupDeclaration detection for all entity kinds
  - SlotFill detection for explicit forms
  - Kind inference from natural language
  - Schema lookup and next-slot logic
  - EntityGroup data model
  - Edge cases: no possession signal, unknown kind, bare messages
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.entity_group_registry import (
    EntityGroup, EntityGroupRegistry, GroupDeclaration,
    GroupStatus, SlotFill, SLOT_SCHEMAS,
)


# ===========================================================================
# 1. EntityGroupRegistry — detect_declaration
# ===========================================================================

class TestDetectDeclaration:

    def setup_method(self):
        self.registry = EntityGroupRegistry()

    # Animals
    def test_i_have_2_dogs(self):
        result = self.registry.detect_declaration("I have 2 dogs.")
        assert result is not None
        assert result.kind == "animal"
        assert result.count == 2

    def test_i_have_3_cats(self):
        result = self.registry.detect_declaration("I have 3 cats.")
        assert result is not None
        assert result.kind == "animal"
        assert result.count == 3

    def test_i_have_a_cat(self):
        result = self.registry.detect_declaration("I have a cat.")
        assert result is not None
        assert result.kind == "animal"
        assert result.count == 1

    def test_ive_got_some_fish(self):
        result = self.registry.detect_declaration("I've got some fish.")
        assert result is not None
        assert result.kind == "animal"
        assert result.count is None  # uncountable

    # People
    def test_i_have_2_children(self):
        result = self.registry.detect_declaration("I have 2 children.")
        assert result is not None
        assert result.kind == "person"
        assert result.count == 2

    def test_i_have_3_employees(self):
        result = self.registry.detect_declaration("I have 3 employees.")
        assert result is not None
        assert result.kind == "person"

    def test_i_have_a_brother(self):
        result = self.registry.detect_declaration("I have a brother.")
        assert result is not None
        assert result.kind == "person"

    # Vehicles
    def test_i_have_2_cars(self):
        result = self.registry.detect_declaration("I have 2 cars.")
        assert result is not None
        assert result.kind == "vehicle"
        assert result.count == 2

    def test_i_own_a_motorbike(self):
        result = self.registry.detect_declaration("I own a motorbike.")
        assert result is not None
        assert result.kind == "vehicle"

    # Instruments
    def test_i_have_3_guitars(self):
        result = self.registry.detect_declaration("I have 3 guitars.")
        assert result is not None
        assert result.kind == "instrument"
        assert result.count == 3

    def test_i_own_a_piano(self):
        result = self.registry.detect_declaration("I own a piano.")
        assert result is not None
        assert result.kind == "instrument"

    # No match cases
    def test_no_possession_signal(self):
        result = self.registry.detect_declaration("Two dogs named Rex and Tom.")
        assert result is None

    def test_unknown_kind(self):
        result = self.registry.detect_declaration("I have 2 blorbzorps.")
        assert result is None

    def test_question_not_detected(self):
        result = self.registry.detect_declaration("How many dogs do I have?")
        assert result is None

    def test_empty_string(self):
        result = self.registry.detect_declaration("")
        assert result is None


# ===========================================================================
# 2. EntityGroupRegistry — detect_slot_fill
# ===========================================================================

class TestDetectSlotFill:

    def setup_method(self):
        self.registry = EntityGroupRegistry()

    def test_their_names_are(self):
        result = self.registry.detect_slot_fill(
            "Their names are Rex and Tom.", "animal", {}
        )
        assert result is not None
        assert result.slot == "names"
        assert "Rex" in result.value
        assert "Tom" in result.value

    def test_their_colours_are(self):
        result = self.registry.detect_slot_fill(
            "Their colours are brown and white.", "animal", {}
        )
        assert result is not None
        assert result.slot == "colours"

    def test_their_ages_are(self):
        result = self.registry.detect_slot_fill(
            "Their ages are 3 and 5.", "animal", {}
        )
        assert result is not None
        assert result.slot == "ages"

    def test_skips_filled_slot(self):
        result = self.registry.detect_slot_fill(
            "Their names are Rex and Tom.",
            "animal",
            {"names": "already filled"},
        )
        assert result is None

    def test_no_match_returns_none(self):
        result = self.registry.detect_slot_fill(
            "I like pizza.", "animal", {}
        )
        assert result is None

    def test_empty_active_kind_returns_none(self):
        result = self.registry.detect_slot_fill(
            "Their names are Rex.", "", {}
        )
        assert result is None


# ===========================================================================
# 3. EntityGroupRegistry — infer_kind
# ===========================================================================

class TestInferKind:

    def setup_method(self):
        self.registry = EntityGroupRegistry()

    def test_dogs_is_animal(self):
        assert self.registry.infer_kind("2 dogs") == "animal"

    def test_cats_is_animal(self):
        assert self.registry.infer_kind("3 cats") == "animal"

    def test_children_is_person(self):
        assert self.registry.infer_kind("2 children") == "person"

    def test_guitars_is_instrument(self):
        assert self.registry.infer_kind("3 guitars") == "instrument"

    def test_cars_is_vehicle(self):
        assert self.registry.infer_kind("2 cars") == "vehicle"

    def test_servers_is_server(self):
        assert self.registry.infer_kind("5 servers") == "server"

    def test_unknown_returns_none(self):
        assert self.registry.infer_kind("blorbzorps") is None

    def test_empty_returns_none(self):
        assert self.registry.infer_kind("") is None


# ===========================================================================
# 4. EntityGroupRegistry — schema and next_slot
# ===========================================================================

class TestSchemaAndNextSlot:

    def setup_method(self):
        self.registry = EntityGroupRegistry()

    def test_animal_schema_has_names(self):
        schema = self.registry.schema_for("animal")
        assert "names" in schema

    def test_person_schema_has_names(self):
        schema = self.registry.schema_for("person")
        assert "names" in schema

    def test_unknown_kind_returns_default(self):
        schema = self.registry.schema_for("unknown_kind_xyz")
        assert len(schema) > 0

    def test_next_slot_empty_filled(self):
        slot = self.registry.next_slot("animal", {})
        assert slot == "names"  # first slot in animal schema

    def test_next_slot_names_filled(self):
        slot = self.registry.next_slot("animal", {"names": "Rex and Tom"})
        assert slot == "breeds"  # second slot

    def test_next_slot_all_filled(self):
        all_filled = {s: "x" for s in SLOT_SCHEMAS["animal"]}
        slot = self.registry.next_slot("animal", all_filled)
        assert slot is None


# ===========================================================================
# 5. EntityGroup data model
# ===========================================================================

class TestEntityGroup:

    def test_initial_status_open(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        assert group.status == GroupStatus.OPEN

    def test_fill_slot(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        group.fill("names", "Rex and Tom")
        assert group.slots["names"] == "Rex and Tom"

    def test_next_unfilled_slot(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        assert group.next_unfilled_slot() == "names"
        group.fill("names", "Rex and Tom")
        assert group.next_unfilled_slot() == "breeds"

    def test_knowledge_attribute(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        assert group.knowledge_attribute() == "group:animal"

    def test_slot_attribute(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        assert group.slot_attribute("names") == "group:animal:names"

    def test_knowledge_tags_open(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        tags = group.knowledge_tags()
        assert "group" in tags
        assert "group_kind:animal" in tags
        assert "group_open" in tags

    def test_slot_tags(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        tags = group.slot_tags("names")
        assert "group_slot" in tags
        assert "group_kind:animal" in tags
        assert "slot:names" in tags

    def test_close(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        group.close()
        assert group.status == GroupStatus.CLOSED

    def test_schema_returns_correct_slots(self):
        group = EntityGroup(
            kind="animal", raw_kind="dogs",
            count=2, raw_value="2 dogs"
        )
        assert group.schema() == SLOT_SCHEMAS["animal"]


# ===========================================================================
# 6. SLOT_SCHEMAS completeness
# ===========================================================================

class TestSlotSchemas:

    def test_all_kinds_have_names_slot(self):
        for kind, schema in SLOT_SCHEMAS.items():
            assert "names" in schema, f"{kind} schema missing 'names' slot"

    def test_all_schemas_non_empty(self):
        for kind, schema in SLOT_SCHEMAS.items():
            assert len(schema) > 0, f"{kind} schema is empty"

    def test_known_kinds_present(self):
        for kind in ["animal", "person", "vehicle", "instrument", "server", "project"]:
            assert kind in SLOT_SCHEMAS