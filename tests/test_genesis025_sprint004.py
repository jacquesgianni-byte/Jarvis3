"""
Genesis-025 Sprint-004 — ContextualRecallEngine Tests

Coverage:
  - can_answer() returns True only when active_topic set + anaphoric query
  - answer() resolves "What are their names?" via active_topic
  - answer() resolves "What are my dogs' names?" generically
  - answer() resolves "What are their colours?"
  - No active_topic → can_answer returns False
  - Unknown kind → answer returns None
  - ConversationRecall remains unaware of SessionContext
  - Both golden conversations pass through engine
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.contextual_recall_engine import ContextualRecallEngine
from core.conversation.session_context import SessionContext
from core.conversation.conversation_recall import RecallResult


def make_session(active_topic: str = "") -> SessionContext:
    s = SessionContext()
    if active_topic:
        s.set_topic(active_topic, raw=active_topic)
    return s


def make_recall(attr_value: str = "Rex and Tom") -> MagicMock:
    recall = MagicMock()
    result = RecallResult(found=True, answer=attr_value, attribute="pet names", value=attr_value)
    recall.lookup.return_value = result
    return recall


# ===========================================================================
# 1. can_answer()
# ===========================================================================

class TestCanAnswer:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_returns_true_for_their_names_with_topic(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are their names?", session)

    def test_returns_true_for_my_dogs_names_with_topic(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are my dogs' names?", session)

    def test_returns_false_without_active_topic(self):
        session = make_session()
        assert not self.engine.can_answer("What are their names?", session)

    def test_returns_false_for_non_anaphoric_query(self):
        session = make_session("2 dogs")
        assert not self.engine.can_answer("Who are Rex and Tom?", session)

    def test_returns_false_for_empty_query(self):
        session = make_session("2 dogs")
        assert not self.engine.can_answer("", session)

    def test_returns_true_for_their_colours(self):
        session = make_session("3 cats")
        assert self.engine.can_answer("What are their colours?", session)


# ===========================================================================
# 2. answer() — name resolution
# ===========================================================================

class TestAnswerNameResolution:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_their_names_after_dogs(self):
        session = make_session("2 dogs")
        recall = make_recall("Rex and Tom")
        result = self.engine.answer("What are their names?", session, recall)
        assert result is not None
        assert result.found
        recall.lookup.assert_called_once_with("user", "pet names")

    def test_their_names_after_cats(self):
        session = make_session("3 cats")
        recall = make_recall("Tom, Tim and Tam")
        result = self.engine.answer("What are their names?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "pet names")

    def test_my_dogs_names(self):
        session = make_session("2 dogs")
        recall = make_recall("Rex and Tom")
        result = self.engine.answer("What are my dogs' names?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "pet names")

    def test_children_names(self):
        session = make_session("2 children")
        recall = make_recall("Alex and Emma")
        result = self.engine.answer("What are their names?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "people names")

    def test_guitars_names(self):
        session = make_session("3 guitars")
        recall = make_recall("Les Paul and Strat")
        result = self.engine.answer("What are their names?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "instrument names")

    def test_no_active_topic_returns_none(self):
        session = make_session()
        recall = make_recall()
        result = self.engine.answer("What are their names?", session, recall)
        assert result is None

    def test_unknown_kind_returns_none(self):
        session = make_session("2 blorbzorps")
        recall = make_recall()
        result = self.engine.answer("What are their names?", session, recall)
        assert result is None


# ===========================================================================
# 3. answer() — attribute resolution
# ===========================================================================

class TestAnswerAttributeResolution:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_their_colours_after_dogs(self):
        session = make_session("2 dogs")
        recall = make_recall("brown and white")
        result = self.engine.answer("What are their colours?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "pet colours")

    def test_their_ages(self):
        session = make_session("2 dogs")
        recall = make_recall("3 and 5")
        result = self.engine.answer("What are their ages?", session, recall)
        assert result is not None
        recall.lookup.assert_called_once_with("user", "pet ages")


# ===========================================================================
# 4. ConversationRecall independence
# ===========================================================================

class TestConversationRecallIndependence:

    def test_recall_not_given_session_context(self):
        """ConversationRecall must never receive SessionContext directly."""
        engine = ContextualRecallEngine()
        session = make_session("2 dogs")
        recall = make_recall("Rex and Tom")
        engine.answer("What are their names?", session, recall)
        # Verify _recall_attribute was called with only strings, not SessionContext
        call_args = recall.lookup.call_args
        for arg in call_args.args:
            assert not isinstance(arg, SessionContext)

    def test_engine_is_stateless(self):
        """Same inputs always produce same output."""
        engine = ContextualRecallEngine()
        session = make_session("2 dogs")
        recall1 = make_recall("Rex and Tom")
        recall2 = make_recall("Rex and Tom")
        r1 = engine.answer("What are their names?", session, recall1)
        r2 = engine.answer("What are their names?", session, recall2)
        assert r1.found == r2.found


# ===========================================================================
# 5. Golden conversation parity
# ===========================================================================

class TestGoldenConversationParity:

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_gt1_who_are_rex_and_tom_not_intercepted(self):
        """GT1: 'Who are Rex and Tom?' should NOT go through ContextualRecallEngine."""
        session = make_session("2 dogs")
        assert not self.engine.can_answer("Who are Rex and Tom?", session)

    def test_gt2_what_are_their_names_intercepted(self):
        """GT2: 'What are their names?' SHOULD go through ContextualRecallEngine."""
        session = make_session("3 cats")
        assert self.engine.can_answer("What are their names?", session)

    def test_gt2_resolves_to_pet_names_attribute(self):
        """GT2: 'What are their names?' resolves to 'pet names' attribute."""
        session = make_session("3 cats")
        recall = make_recall("Tom, Tim and Tam")
        result = self.engine.answer("What are their names?", session, recall)
        assert result is not None
        recall.lookup.assert_called_with("user", "pet names")


# ===========================================================================
# 6. Anaphoric attribute pattern coverage (GPT Sprint-004 review)
# ===========================================================================

class TestAnaphoricAttributePatterns:
    """
    Verify the parser is generic across different attributes and group types.
    Locks down pattern behaviour before wiring into Agent.
    """

    def setup_method(self):
        self.engine = ContextualRecallEngine()

    def test_their_colours(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are their colours?", session)

    def test_their_colors_us_spelling(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are their colors?", session)

    def test_their_ages(self):
        session = make_session("3 cats")
        assert self.engine.can_answer("What are their ages?", session)

    def test_my_dogs_colours(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are my dogs' colours?", session)

    def test_my_dogs_colors_no_apostrophe(self):
        session = make_session("2 dogs")
        assert self.engine.can_answer("What are my dogs colors?", session)

    def test_my_servers_roles(self):
        session = make_session("5 servers")
        assert self.engine.can_answer("What are my servers' roles?", session)

    def test_colours_resolves_to_correct_attr(self):
        session = make_session("2 dogs")
        recall = make_recall("brown and white")
        result = self.engine.answer("What are their colours?", session, recall)
        assert result is not None
        recall.lookup.assert_called_with("user", "pet colours")

    def test_ages_resolves_to_correct_attr(self):
        session = make_session("3 cats")
        recall = make_recall("2 and 4")
        result = self.engine.answer("What are their ages?", session, recall)
        assert result is not None
        recall.lookup.assert_called_with("user", "pet ages")

    def test_server_roles_resolves_generically(self):
        session = make_session("5 servers")
        recall = make_recall("web and db")
        result = self.engine.answer("What are my servers' roles?", session, recall)
        assert result is not None
        recall.lookup.assert_called_with("user", "group:server:roles")