"""
Tests for Genesis-032 Sprint-001: Semantic Recall Engine

Covers:
    - SemanticFact deduplication
    - SemanticProfile: add, by_category, to_text
    - PropertyProvider: reads prop: records
    - GroupProvider: reads group membership
    - TemporalProvider: reads temporal tags
    - ConversationProvider: reads conversation records
    - SemanticRecallEngine: detect_query, recall
    - Unknown entity graceful miss
    - Provider extensibility
    - No regressions
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from core.conversation.semantic_recall_engine import (
    SemanticRecallEngine,
    SemanticProfile,
    SemanticFact,
    PropertyProvider,
    GroupProvider,
    TemporalProvider,
    ConversationProvider,
    SemanticProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(subject, attribute, value, tags=None, category="entity_property"):
    r = MagicMock()
    r.subject = subject
    r.attribute = attribute
    r.value = value
    r.tags = tags or []
    r.category = category
    return r


def _make_knowledge(records=None, search_results=None):
    k = MagicMock()
    k.list_memories.return_value = records or []
    k.search_memory.return_value = search_results or []
    k.recall_memory.return_value = None
    return k


# ===========================================================================
# SemanticFact
# ===========================================================================

class TestSemanticFact:

    def test_dedup_key_with_key(self):
        f = SemanticFact(category="Properties", label="8 years old", source="property", key="age")
        assert f.dedup_key() == "Properties:age"

    def test_dedup_key_without_key(self):
        f = SemanticFact(category="Groups", label="One of your dogs", source="group")
        assert f.dedup_key() == "Groups:one of your dogs"

    def test_same_key_considered_duplicate(self):
        f1 = SemanticFact(category="Properties", label="8 years old", source="p", key="age")
        f2 = SemanticFact(category="Properties", label="nine years old", source="p", key="age")
        assert f1.dedup_key() == f2.dedup_key()


# ===========================================================================
# SemanticProfile
# ===========================================================================

class TestSemanticProfile:

    def test_empty_profile_not_found(self):
        p = SemanticProfile(entity_name="Unknown")
        assert p.found is False

    def test_add_fact_sets_found(self):
        p = SemanticProfile(entity_name="Leo")
        p.add(SemanticFact("Properties", "8 years old", "property", "age"))
        assert p.found is True

    def test_duplicate_fact_not_added(self):
        p = SemanticProfile(entity_name="Leo")
        f = SemanticFact("Properties", "8 years old", "property", "age")
        p.add(f)
        p.add(f)
        assert len(p.facts) == 1

    def test_different_key_both_added(self):
        p = SemanticProfile(entity_name="Leo")
        p.add(SemanticFact("Properties", "8 years old", "property", "age"))
        p.add(SemanticFact("Properties", "brown", "property", "colour"))
        assert len(p.facts) == 2

    def test_by_category_groups_correctly(self):
        p = SemanticProfile(entity_name="Leo")
        p.add(SemanticFact("Properties", "8 years old", "property", "age"))
        p.add(SemanticFact("Relationships", "One of your children", "group"))
        cats = p.by_category()
        assert "Properties" in cats
        assert "Relationships" in cats
        assert len(cats["Properties"]) == 1

    def test_to_text_not_found(self):
        p = SemanticProfile(entity_name="Alice")
        text = p.to_text()
        assert "Alice" in text
        assert "don't have" in text.lower() or "no information" in text.lower()

    def test_to_text_found(self):
        p = SemanticProfile(entity_name="Leo")
        p.add(SemanticFact("Properties", "8 years old", "property", "age"))
        text = p.to_text()
        assert "Leo" in text
        assert "8 years old" in text

    def test_to_text_multiple_facts(self):
        p = SemanticProfile(entity_name="Rex")
        p.add(SemanticFact("Properties", "brown", "property", "colour"))
        p.add(SemanticFact("Relationships", "One of your dogs", "group"))
        text = p.to_text()
        assert "brown" in text
        assert "dogs" in text


# ===========================================================================
# PropertyProvider
# ===========================================================================

class TestPropertyProvider:

    def test_reads_age_property(self):
        records = [_make_record("leo", "prop:age", "8", ["user_fact"])]
        k = _make_knowledge(records=records)
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert profile.found
        assert any("8" in f.label for f in profile.facts)

    def test_reads_colour_property(self):
        records = [_make_record("rex", "prop:colour", "brown")]
        k = _make_knowledge(records=records)
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert any("brown" in f.label for f in profile.facts)

    def test_reads_status_property(self):
        records = [_make_record("canon", "prop:status", "offline")]
        k = _make_knowledge(records=records)
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Canon")
        provider.contribute("canon", k, profile)
        assert any("offline" in f.label for f in profile.facts)

    def test_ignores_non_prop_records(self):
        records = [_make_record("leo", "name", "Leo")]
        k = _make_knowledge(records=records)
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert not profile.found

    def test_no_records_no_facts(self):
        k = _make_knowledge(records=[])
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Alice")
        provider.contribute("alice", k, profile)
        assert not profile.found

    def test_category_is_properties(self):
        records = [_make_record("leo", "prop:age", "8")]
        k = _make_knowledge(records=records)
        provider = PropertyProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert all(f.category == "Properties" for f in profile.facts)


# ===========================================================================
# GroupProvider
# ===========================================================================

class TestGroupProvider:

    def test_finds_group_membership(self):
        records = [
            _make_record("user", "group:dogs:names", "Rex, Tom and Chase",
                        tags=["group_slot"])
        ]
        k = _make_knowledge(search_results=records)
        provider = GroupProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert profile.found
        assert any("dogs" in f.label.lower() for f in profile.facts)

    def test_entity_not_in_group_no_fact(self):
        records = [
            _make_record("user", "group:dogs:names", "Tom and Chase",
                        tags=["group_slot"])
        ]
        k = _make_knowledge(search_results=records)
        provider = GroupProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert not profile.found

    def test_category_is_relationships(self):
        records = [
            _make_record("user", "group:dogs:names", "Rex and Tom",
                        tags=["group_slot"])
        ]
        k = _make_knowledge(search_results=records)
        provider = GroupProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        if profile.found:
            assert all(f.category == "Relationships" for f in profile.facts)


# ===========================================================================
# TemporalProvider
# ===========================================================================

class TestTemporalProvider:

    def test_finds_temporal_record(self):
        records = [
            _make_record("user", "job_start", "Leo started school",
                        tags=["temporal", "past", "resolved:2026-07-27", "expr:last monday"])
        ]
        k = _make_knowledge(search_results=records)
        provider = TemporalProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert profile.found

    def test_no_temporal_tag_ignored(self):
        records = [
            _make_record("user", "name", "Leo is great", tags=["user_fact"])
        ]
        k = _make_knowledge(search_results=records)
        provider = TemporalProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert not profile.found

    def test_category_is_temporal(self):
        records = [
            _make_record("user", "event", "Leo won a prize",
                        tags=["temporal", "past", "expr:yesterday"])
        ]
        k = _make_knowledge(search_results=records)
        provider = TemporalProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        if profile.found:
            assert all(f.category == "Temporal" for f in profile.facts)


# ===========================================================================
# ConversationProvider
# ===========================================================================

class TestConversationProvider:

    def test_finds_conversation_mention(self):
        records = [
            _make_record("jarvis", "conversation_2026-08-01", "leo is 8",
                        tags=["conversation"])
        ]
        k = _make_knowledge(search_results=records)
        provider = ConversationProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert profile.found

    def test_entity_not_mentioned_no_fact(self):
        records = [
            _make_record("jarvis", "conversation_2026-08-01", "the weather is nice",
                        tags=["conversation"])
        ]
        k = _make_knowledge(search_results=records)
        provider = ConversationProvider()
        profile = SemanticProfile(entity_name="Leo")
        provider.contribute("leo", k, profile)
        assert not profile.found


# ===========================================================================
# SemanticRecallEngine -- detect_query
# ===========================================================================

class TestDetectQuery:

    def setup_method(self):
        self.engine = SemanticRecallEngine()

    def test_tell_me_everything_about(self):
        result = self.engine.detect_query("Tell me everything about Leo.")
        assert result is not None
        assert "Leo" in result

    def test_what_do_you_know_about(self):
        result = self.engine.detect_query("What do you know about Rex?")
        assert result is not None
        assert "Rex" in result

    def test_who_is(self):
        # "who is" now falls through to AI -- too generic for semantic recall
        result = self.engine.detect_query("Who is Lucas?")
        assert result is None  # correctly not intercepted

    def test_tell_me_about_canon(self):
        result = self.engine.detect_query("Tell me everything about Canon.")
        assert result is not None
        assert "Canon" in result

    def test_stop_entity_returns_none(self):
        assert self.engine.detect_query("Tell me everything about it.") is None

    def test_empty_returns_none(self):
        assert self.engine.detect_query("") is None

    def test_plain_statement_returns_none(self):
        assert self.engine.detect_query("Leo is 8 years old.") is None

    def test_what_can_you_tell_me(self):
        result = self.engine.detect_query("What can you tell me about Rex?")
        assert result is not None


# ===========================================================================
# SemanticRecallEngine -- recall
# ===========================================================================

class TestRecall:

    def test_unknown_entity_returns_not_found(self):
        k = _make_knowledge()
        engine = SemanticRecallEngine()
        profile = engine.recall("Alice", k)
        assert profile.found is False
        assert "Alice" in profile.entity_name

    def test_known_entity_returns_facts(self):
        prop_records = [_make_record("leo", "prop:age", "8")]
        k = _make_knowledge(records=prop_records)
        engine = SemanticRecallEngine(providers=[PropertyProvider()])
        profile = engine.recall("leo", k)
        assert profile.found
        assert any("8" in f.label for f in profile.facts)

    def test_multiple_providers_combined(self):
        prop_records = [_make_record("rex", "prop:colour", "brown")]
        group_records = [
            _make_record("user", "group:dogs:names", "Rex and Tom", tags=["group_slot"])
        ]

        def search_side(query=None, subject=None, limit=10, **kwargs):
            return group_records

        k = MagicMock()
        k.list_memories.return_value = prop_records
        k.search_memory.side_effect = search_side

        engine = SemanticRecallEngine(providers=[PropertyProvider(), GroupProvider()])
        profile = engine.recall("rex", k)
        categories = profile.by_category()
        assert "Properties" in categories

    def test_provider_failure_does_not_crash(self):
        class BrokenProvider(SemanticProvider):
            name = "broken"
            def contribute(self, entity_name, knowledge, profile):
                raise RuntimeError("Provider failed")

        k = _make_knowledge()
        engine = SemanticRecallEngine(providers=[BrokenProvider()])
        profile = engine.recall("Leo", k)
        assert profile is not None  # Should not raise

    def test_entity_name_titled_in_profile(self):
        k = _make_knowledge()
        engine = SemanticRecallEngine(providers=[])
        profile = engine.recall("leo", k)
        assert profile.entity_name == "Leo"

    def test_to_text_unknown(self):
        k = _make_knowledge()
        engine = SemanticRecallEngine(providers=[])
        profile = engine.recall("Alice", k)
        text = profile.to_text()
        assert "Alice" in text

    def test_extensible_provider_registration(self):
        engine = SemanticRecallEngine(providers=[])
        initial_count = len(engine._providers)

        class ExtraProvider(SemanticProvider):
            name = "extra"
            def contribute(self, entity_name, knowledge, profile):
                profile.add(SemanticFact("Extra", "extra fact", self.name))

        engine.register_provider(ExtraProvider())
        assert len(engine._providers) == initial_count + 1

        k = _make_knowledge()
        profile = engine.recall("test", k)
        assert any(f.source == "extra" for f in profile.facts)
