"""
Tests for Genesis-032 Sprint-002: Relationship Recall Engine

Covers:
    - GroupRelationshipScanner: scan membership
    - RelationshipProvider: contributes sibling facts
    - RelationshipRecallEngine: detect_query, answer
    - how_related, who_related, which_group query types
    - Unknown entity graceful miss
    - No regressions on Sprint-001
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from core.conversation.relationship_recall import (
    RelationshipProvider,
    RelationshipRecallEngine,
    GroupRelationshipScanner,
    RelationshipFact,
)
from core.conversation.semantic_recall_engine import SemanticProfile, SemanticFact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(subject, attribute, value, tags=None):
    r = MagicMock()
    r.subject = subject
    r.attribute = attribute
    r.value = value
    r.tags = tags or []
    return r


def _make_knowledge_with_groups(groups: dict[str, list[str]]):
    """
    Build a mock KnowledgeEngine with group slot records.
    groups = {"dogs": ["Rex", "Tom"], "children": ["Lucas", "Leo"]}
    """
    records = []
    for kind, members in groups.items():
        value = ", ".join(members)
        records.append(_make_record(
            "user",
            f"group:{kind}:names",
            value,
            tags=["group_slot"],
        ))

    k = MagicMock()
    k.search_memory.return_value = records
    k.list_memories.return_value = []
    k.recall_memory.return_value = None
    return k


# ===========================================================================
# GroupRelationshipScanner
# ===========================================================================

class TestGroupRelationshipScanner:

    def test_scans_single_group(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        scanner = GroupRelationshipScanner()
        membership = scanner.scan(k)
        assert "rex" in membership
        assert "tom" in membership
        assert "dogs" in membership["rex"]

    def test_scans_multiple_groups(self):
        k = _make_knowledge_with_groups({
            "dogs": ["Rex", "Tom"],
            "children": ["Lucas", "Leo"],
        })
        scanner = GroupRelationshipScanner()
        membership = scanner.scan(k)
        assert "dogs" in membership.get("rex", [])
        assert "children" in membership.get("lucas", [])

    def test_empty_knowledge_returns_empty(self):
        k = MagicMock()
        k.search_memory.return_value = []
        scanner = GroupRelationshipScanner()
        assert scanner.scan(k) == {}

    def test_names_lowercased(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "TOM"]})
        scanner = GroupRelationshipScanner()
        membership = scanner.scan(k)
        assert "rex" in membership
        assert "tom" in membership

    def test_splits_and_separator(self):
        records = [_make_record("user", "group:dogs:names", "Rex, Tom and Chase")]
        k = MagicMock()
        k.search_memory.return_value = records
        scanner = GroupRelationshipScanner()
        membership = scanner.scan(k)
        assert "rex" in membership
        assert "tom" in membership
        assert "chase" in membership


# ===========================================================================
# RelationshipProvider
# ===========================================================================

class TestRelationshipProvider:

    def test_contributes_sibling_fact(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert profile.found
        assert any("Tom" in f.label for f in profile.facts)

    def test_no_siblings_no_fact(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex"]})
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        # Single member -- no sibling fact
        assert not profile.found

    def test_unknown_entity_no_fact(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Alice")
        provider.contribute("alice", k, profile)
        assert not profile.found

    def test_category_is_relationships(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert all(f.category == "Relationships" for f in profile.facts)

    def test_source_is_relationship(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        assert all(f.source == "relationship" for f in profile.facts)

    def test_multiple_groups(self):
        records = [
            _make_record("user", "group:dogs:names", "Rex, Tom"),
            _make_record("user", "group:pets:names", "Rex, Luna"),
        ]
        k = MagicMock()
        k.search_memory.return_value = records
        provider = RelationshipProvider()
        profile = SemanticProfile(entity_name="Rex")
        provider.contribute("rex", k, profile)
        # Should have facts for both groups
        assert profile.found


# ===========================================================================
# RelationshipRecallEngine -- detect_query
# ===========================================================================

class TestDetectQuery:

    def setup_method(self):
        self.engine = RelationshipRecallEngine()

    def test_how_is_related_to(self):
        q = self.engine.detect_query("How is Rex related to Tom?")
        assert q is not None
        assert q.query_type == "how_related"
        assert q.entity_a.lower() == "rex"
        assert q.entity_b.lower() == "tom"

    def test_relationship_between(self):
        q = self.engine.detect_query("What is the relationship between Rex and Tom?")
        assert q is not None
        assert q.query_type == "how_related"

    def test_are_related(self):
        q = self.engine.detect_query("Are Rex and Tom related?")
        assert q is not None
        assert q.query_type == "how_related"

    def test_who_is_related_to(self):
        q = self.engine.detect_query("Who is related to Leo?")
        assert q is not None
        assert q.query_type == "who_related"
        assert q.entity_a.lower() == "leo"

    def test_who_lives_with(self):
        q = self.engine.detect_query("Who lives with Leo?")
        assert q is not None
        assert q.query_type == "who_related"

    def test_which_printers_belong(self):
        q = self.engine.detect_query("Which printers belong to me?")
        assert q is not None
        assert q.query_type == "which_group"
        assert "printer" in q.group_hint

    def test_which_of_my(self):
        q = self.engine.detect_query("Which of my dogs is brown?")
        assert q is not None
        assert q.query_type == "which_group"

    def test_plain_statement_none(self):
        assert self.engine.detect_query("Rex is brown.") is None

    def test_empty_none(self):
        assert self.engine.detect_query("") is None


# ===========================================================================
# RelationshipRecallEngine -- answer: how_related
# ===========================================================================

class TestAnswerHowRelated:

    def setup_method(self):
        self.engine = RelationshipRecallEngine()

    def test_shared_group_returns_answer(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        q = self.engine.RelationshipQuery(
            query_type="how_related", entity_a="Rex", entity_b="Tom"
        )
        result = self.engine.answer(q, k)
        assert result.found is True
        assert "Rex" in result.answer
        assert "Tom" in result.answer
        assert "dogs" in result.answer.lower()

    def test_no_shared_group_not_found(self):
        k = _make_knowledge_with_groups({
            "dogs": ["Rex"],
            "children": ["Leo"],
        })
        q = self.engine.RelationshipQuery(
            query_type="how_related", entity_a="Rex", entity_b="Leo"
        )
        result = self.engine.answer(q, k)
        assert result.found is False

    def test_unknown_both_not_found(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        q = self.engine.RelationshipQuery(
            query_type="how_related", entity_a="Alice", entity_b="Bob"
        )
        result = self.engine.answer(q, k)
        assert result.found is False


# ===========================================================================
# RelationshipRecallEngine -- answer: who_related
# ===========================================================================

class TestAnswerWhoRelated:

    def setup_method(self):
        self.engine = RelationshipRecallEngine()

    def test_finds_siblings(self):
        k = _make_knowledge_with_groups({"children": ["Lucas", "Leo"]})
        q = self.engine.RelationshipQuery(
            query_type="who_related", entity_a="Leo"
        )
        result = self.engine.answer(q, k)
        assert result.found is True
        assert "Lucas" in result.answer

    def test_unknown_entity_not_found(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        q = self.engine.RelationshipQuery(
            query_type="who_related", entity_a="Alice"
        )
        result = self.engine.answer(q, k)
        assert result.found is False

    def test_only_member_returns_answer(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex"]})
        q = self.engine.RelationshipQuery(
            query_type="who_related", entity_a="Rex"
        )
        result = self.engine.answer(q, k)
        assert result.found is True
        assert "Rex" in result.answer


# ===========================================================================
# RelationshipRecallEngine -- answer: which_group
# ===========================================================================

class TestAnswerWhichGroup:

    def setup_method(self):
        self.engine = RelationshipRecallEngine()

    def test_finds_group_members(self):
        k = _make_knowledge_with_groups({"printers": ["HP", "Canon", "Epson"]})
        q = self.engine.RelationshipQuery(
            query_type="which_group", entity_a="", group_hint="printers"
        )
        result = self.engine.answer(q, k)
        assert result.found is True
        assert "HP" in result.answer or "Canon" in result.answer

    def test_unknown_group_not_found(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex", "Tom"]})
        q = self.engine.RelationshipQuery(
            query_type="which_group", entity_a="", group_hint="printers"
        )
        result = self.engine.answer(q, k)
        assert result.found is False

    def test_single_member_singular(self):
        k = _make_knowledge_with_groups({"dogs": ["Rex"]})
        q = self.engine.RelationshipQuery(
            query_type="which_group", entity_a="", group_hint="dogs"
        )
        result = self.engine.answer(q, k)
        assert result.found is True
        assert "Rex" in result.answer


# ===========================================================================
# Sprint-001 regression guard
# ===========================================================================

class TestSprint001Regression:

    def test_semantic_recall_engine_unchanged(self):
        from core.conversation.semantic_recall_engine import SemanticRecallEngine
        engine = SemanticRecallEngine()
        assert engine.detect_query("Tell me everything about Leo.") is not None
        assert engine.detect_query("Tell me everything about Rex.") is not None

    def test_relationship_provider_plugs_into_semantic_engine(self):
        from core.conversation.semantic_recall_engine import SemanticRecallEngine
        engine = SemanticRecallEngine()
        initial_count = len(engine._providers)
        engine.register_provider(RelationshipProvider())
        assert len(engine._providers) == initial_count + 1
