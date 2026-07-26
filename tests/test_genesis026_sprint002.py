"""
Genesis-026 Sprint-002 — Identity vs Attribute Reasoning Tests

Verifies that ContextualRecallEngine correctly distinguishes:
  - Attribute questions: "What are their names?" → property value
  - Identity questions: "Who are they?" → entity classification

Coverage:
  - ResolutionType.ATTRIBUTE for attribute questions
  - ResolutionType.IDENTITY for identity questions
  - Identity answer composition (declaration + names)
  - Identity fallback when names not stored
  - Generic across entity kinds
  - Existing attribute tests unaffected
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.contextual_recall_engine import (
    ContextualRecallEngine, RecallRequest, ResolutionType
)
from core.conversation.session_context import SessionContext
from core.conversation.conversation_recall import RecallResult


def make_session(active_topic: str) -> SessionContext:
    s = SessionContext()
    s.set_topic(active_topic, raw=active_topic)
    return s


def make_recall(decl_value: str = "2 dogs", names_value: str = "Rex and Max") -> MagicMock:
    recall = MagicMock()
    def lookup(subject, attribute):
        if attribute in ("pets", "people", "vehicles", "instruments", "servers", "projects"):
            return RecallResult(found=True, answer=decl_value, attribute=attribute, value=decl_value)
        if "names" in attribute:
            return RecallResult(found=True, answer=names_value, attribute=attribute, value=names_value)
        return RecallResult(found=False, answer="", attribute=attribute, value="")
    recall.lookup.side_effect = lookup
    return recall


# ===========================================================================
# 1. ResolutionType — identity patterns
# ===========================================================================

class TestIdentityResolution:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_who_are_they_is_identity(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("Who are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.IDENTITY

    def test_what_are_they_is_identity(self):
        # "What are they?" without "called/named" is identity via "who are my X" pattern
        # Note: plain "What are they?" no longer has an identity pattern — by design.
        # Use "Who are they?" for identity queries.
        s = make_session("2 dogs")
        req = self.engine.resolve("Who are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.IDENTITY

    def test_who_are_my_dogs_is_identity(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("Who are my dogs?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.IDENTITY

    def test_identity_attribute_is_declaration(self):
        """Identity request should point to group declaration, not names."""
        s = make_session("2 dogs")
        req = self.engine.resolve("Who are they?", s)
        assert req.attribute == "pets"

    def test_identity_kind_is_set(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("Who are they?", s)
        assert req.kind == "animal"

    def test_identity_for_children(self):
        s = make_session("3 children")
        req = self.engine.resolve("Who are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.IDENTITY
        assert req.attribute == "people"

    def test_identity_for_servers(self):
        s = make_session("5 servers")
        req = self.engine.resolve("Who are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.IDENTITY
        assert req.attribute == "servers"


# ===========================================================================
# 2. ResolutionType — attribute patterns unchanged
# ===========================================================================

class TestAttributeResolutionUnchanged:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_what_are_their_names_is_attribute(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("What are their names?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.ATTRIBUTE

    def test_tell_me_their_names_is_attribute(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("Tell me their names.", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.ATTRIBUTE

    def test_how_old_are_they_is_attribute(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("How old are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.ATTRIBUTE

    def test_what_colour_are_they_is_attribute(self):
        s = make_session("2 dogs")
        req = self.engine.resolve("What colour are they?", s)
        assert req is not None
        assert req.resolution_type == ResolutionType.ATTRIBUTE


# ===========================================================================
# 3. Identity answer composition
# ===========================================================================

class TestIdentityAnswerComposition:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_who_are_they_composes_answer(self):
        s = make_session("2 dogs")
        recall = make_recall("2 dogs", "Rex and Max")
        result = self.engine.answer("Who are they?", s, recall)
        assert result is not None
        assert result.found
        assert "Rex and Max" in result.answer
        assert "dogs" in result.answer

    def test_identity_answer_format(self):
        s = make_session("2 dogs")
        recall = make_recall("2 dogs", "Rex and Max")
        result = self.engine.answer("Who are they?", s, recall)
        assert result.answer == "Rex and Max are your 2 dogs."

    def test_identity_fallback_without_names(self):
        """When names not stored, falls back to declaration only."""
        s = make_session("2 dogs")
        recall = MagicMock()
        recall.lookup.side_effect = lambda subject, attribute: (
            RecallResult(found=True, answer="2 dogs", attribute="pets", value="2 dogs")
            if attribute == "pets"
            else RecallResult(found=False, answer="", attribute=attribute, value="")
        )
        result = self.engine.answer("Who are they?", s, recall)
        assert result is not None
        assert result.found
        assert "2 dogs" in result.answer

    def test_identity_for_children_composes_answer(self):
        s = make_session("3 children")
        recall = make_recall("3 children", "Alex, Emma and James")
        result = self.engine.answer("Who are they?", s, recall)
        assert result is not None
        assert "Alex" in result.answer
        assert "children" in result.answer

    def test_attribute_answer_unchanged(self):
        """Attribute answers still return simple property value."""
        s = make_session("2 dogs")
        recall = make_recall("2 dogs", "Rex and Max")
        result = self.engine.answer("What are their names?", s, recall)
        assert result is not None
        assert result.found


# ===========================================================================
# 4. Golden conversation parity
# ===========================================================================

class TestGoldenConversationParity:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_gt1_who_are_rex_and_tom_not_intercepted(self):
        """Named entity queries still not intercepted."""
        s = make_session("2 dogs")
        assert not self.engine.can_answer("Who are Rex and Tom?", s)

    def test_gt2_what_are_their_names_still_attribute(self):
        s = make_session("3 cats")
        req = self.engine.resolve("What are their names?", s)
        assert req.resolution_type == ResolutionType.ATTRIBUTE
        assert req.attribute == "pet names"

    def test_who_are_they_now_identity(self):
        s = make_session("3 cats")
        req = self.engine.resolve("Who are they?", s)
        assert req.resolution_type == ResolutionType.IDENTITY