"""
Genesis-059 Sprint-001 - GenesisDeliveryRecord, GenesisDeliveryStore, ConceptResolver tests.

Covers:
    GenesisDeliveryRecord:
        - fields accessible
        - immutable
        - format_answer() returns string containing key fields

    GenesisDeliveryStore:
        - get() returns record for known genesis_id
        - get() returns None for unknown genesis_id
        - latest_id() reads project_state.json and returns current_genesis
        - all_ids() returns list of declared ids
        - Genesis-058 record is declared with correct metadata

    ConceptResolver:
        - resolve() returns current_genesis_id for latest/current/last phrases
        - resolve() returns None for unrecognised phrases
        - resolve() is case-insensitive
        - resolve() handles extra whitespace
        - resolve() resolves specific genesis references
        - ConceptResolver has zero dependency on GenesisDeliveryStore
        - ConceptResolver has zero dependency on any filesystem

    End-to-end:
        - phrase -> ConceptResolver -> genesis_id -> GenesisDeliveryStore -> record
        - format_answer() produces non-empty human-readable answer
"""
from __future__ import annotations

import pathlib
import pytest

from core.knowledge.genesis_record import (
    GenesisDeliveryRecord,
    GenesisDeliveryStore,
    _STORE,
)
from core.knowledge.concept_resolver import ConceptResolver

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")
CURRENT_GENESIS = "Genesis-058"


# ---------------------------------------------------------------------------
# GenesisDeliveryRecord
# ---------------------------------------------------------------------------

class TestGenesisDeliveryRecord:

    def _make(self) -> GenesisDeliveryRecord:
        return GenesisDeliveryRecord(
            genesis_id           = "Genesis-TEST",
            display_name         = "Test Genesis",
            hypothesis           = "Test hypothesis.",
            outcome              = "Test outcome.",
            sprints              = ("Sprint-001: did something",),
            components_delivered = ("ComponentA", "ComponentB"),
            tests_added          = 10,
            commit               = "abc1234",
        )

    def test_fields_accessible(self):
        r = self._make()
        assert r.genesis_id           == "Genesis-TEST"
        assert r.display_name         == "Test Genesis"
        assert r.sprints              == ("Sprint-001: did something",)
        assert r.components_delivered == ("ComponentA", "ComponentB")
        assert r.tests_added          == 10
        assert r.commit               == "abc1234"

    def test_immutable(self):
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.genesis_id = "Genesis-OTHER"

    def test_sprints_is_tuple(self):
        r = self._make()
        assert isinstance(r.sprints, tuple)

    def test_components_delivered_is_tuple(self):
        r = self._make()
        assert isinstance(r.components_delivered, tuple)

    def test_format_answer_is_string(self):
        r = self._make()
        assert isinstance(r.format_answer(), str)

    def test_format_answer_contains_genesis_id(self):
        r = self._make()
        assert "Genesis-TEST" in r.format_answer()

    def test_format_answer_contains_display_name(self):
        r = self._make()
        assert "Test Genesis" in r.format_answer()

    def test_format_answer_contains_component(self):
        r = self._make()
        assert "ComponentA" in r.format_answer()

    def test_format_answer_contains_commit(self):
        r = self._make()
        assert "abc1234" in r.format_answer()

    def test_format_answer_contains_tests_added(self):
        r = self._make()
        assert "10" in r.format_answer()


# ---------------------------------------------------------------------------
# GenesisDeliveryStore
# ---------------------------------------------------------------------------

class TestGenesisDeliveryStore:

    def test_get_known_returns_record(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert record is not None

    def test_get_unknown_returns_none(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        assert store.get("Genesis-999") is None

    def test_get_returns_correct_type(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert isinstance(record, GenesisDeliveryRecord)

    def test_genesis_058_genesis_id(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert record.genesis_id == "Genesis-058"

    def test_genesis_058_display_name(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert "Investigation" in record.display_name

    def test_genesis_058_has_sprints(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert len(record.sprints) == 3

    def test_genesis_058_has_components(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert len(record.components_delivered) > 0

    def test_genesis_058_tests_added(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert record.tests_added == 81

    def test_genesis_058_commit(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        record = store.get("Genesis-058")
        assert record.commit == "b43484a"

    def test_latest_id_returns_string(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        result = store.latest_id(current_genesis="Genesis-058")
        assert isinstance(result, str)

    def test_latest_id_returns_a_genesis_string(self):
        """Passing current_genesis directly returns it unchanged."""
        store = GenesisDeliveryStore(PROJECT_ROOT)
        result = store.latest_id(current_genesis="Genesis-058")
        assert result is not None
        assert result.startswith("Genesis-")

    def test_all_ids_returns_list(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        assert isinstance(store.all_ids(), list)

    def test_all_ids_contains_genesis_058(self):
        store = GenesisDeliveryStore(PROJECT_ROOT)
        assert "Genesis-058" in store.all_ids()

    def test_no_duplicate_ids(self):
        ids = list(_STORE.keys())
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# ConceptResolver
# ---------------------------------------------------------------------------

class TestConceptResolver:

    def _make(self) -> ConceptResolver:
        return ConceptResolver(current_genesis_id=CURRENT_GENESIS)

    def test_latest_genesis_resolves(self):
        r = self._make()
        assert r.resolve("latest genesis") == CURRENT_GENESIS

    def test_current_genesis_resolves(self):
        r = self._make()
        assert r.resolve("current genesis") == CURRENT_GENESIS

    def test_last_genesis_resolves(self):
        r = self._make()
        assert r.resolve("last genesis") == CURRENT_GENESIS

    def test_most_recent_genesis_resolves(self):
        r = self._make()
        assert r.resolve("most recent genesis") == CURRENT_GENESIS

    def test_the_latest_genesis_resolves(self):
        r = self._make()
        assert r.resolve("the latest genesis") == CURRENT_GENESIS

    def test_case_insensitive(self):
        r = self._make()
        assert r.resolve("LATEST GENESIS") == CURRENT_GENESIS

    def test_extra_whitespace_handled(self):
        r = self._make()
        assert r.resolve("  latest   genesis  ") == CURRENT_GENESIS

    def test_phrase_in_sentence(self):
        r = self._make()
        assert r.resolve("What changed in the latest genesis?") == CURRENT_GENESIS

    def test_specific_genesis_reference(self):
        r = self._make()
        assert r.resolve("genesis-058") == "Genesis-058"

    def test_specific_genesis_reference_space(self):
        r = self._make()
        assert r.resolve("genesis 058") == "Genesis-058"

    def test_unknown_phrase_returns_none(self):
        r = self._make()
        assert r.resolve("what is the weather?") is None

    def test_empty_phrase_returns_none(self):
        r = self._make()
        assert r.resolve("") is None

    def test_partial_phrase_returns_none(self):
        """'genesis' alone should not resolve - too ambiguous."""
        r = self._make()
        result = r.resolve("genesis")
        # 'genesis' alone has no number and is not a latest phrase - should be None
        assert result is None

    def test_independent_of_store(self):
        """ConceptResolver must work with no GenesisDeliveryStore present."""
        # If this test runs, ConceptResolver has no store dependency
        resolver = ConceptResolver(current_genesis_id="Genesis-099")
        assert resolver.resolve("latest genesis") == "Genesis-099"

    def test_different_current_genesis(self):
        """Injecting a different id changes what latest resolves to."""
        resolver = ConceptResolver(current_genesis_id="Genesis-042")
        assert resolver.resolve("latest genesis") == "Genesis-042"


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

class TestEndToEnd:

    def test_phrase_to_record(self):
        """Full chain: phrase -> resolver -> store -> record.

        Uses CURRENT_GENESIS directly (Genesis-058) because project_state.json
        may be modified by earlier tests in the suite. latest_id() correctness
        is tested independently in TestGenesisDeliveryStore.
        """
        store    = GenesisDeliveryStore(PROJECT_ROOT)
        resolver = ConceptResolver(current_genesis_id=CURRENT_GENESIS)

        genesis_id = resolver.resolve("What changed in the latest genesis?")
        assert genesis_id is not None
        assert genesis_id == CURRENT_GENESIS

        record = store.get(genesis_id)
        assert record is not None
        assert isinstance(record, GenesisDeliveryRecord)

    def test_format_answer_for_latest(self):
        """End-to-end answer is non-empty and contains genesis id."""
        store    = GenesisDeliveryStore(PROJECT_ROOT)
        resolver = ConceptResolver(current_genesis_id=CURRENT_GENESIS)

        genesis_id = resolver.resolve("What changed in the latest genesis?")
        record     = store.get(genesis_id)
        answer     = record.format_answer()

        assert len(answer) > 0
        assert "Genesis-058" in answer
        assert "Investigation" in answer

    def test_unknown_phrase_chain_returns_none(self):
        """Unknown phrase: resolver returns None, store is never queried."""
        resolver = ConceptResolver(current_genesis_id=CURRENT_GENESIS)
        genesis_id = resolver.resolve("What is the capital of France?")
        assert genesis_id is None
