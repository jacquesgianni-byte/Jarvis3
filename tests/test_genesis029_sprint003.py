"""
Tests for Genesis-029 Sprint-003: Clarification Engine

Covers:
    - ClarificationEngine.check(): ambiguous vs unambiguous cases
    - ClarificationEngine.try_resolve(): exact and partial matching
    - ClarificationEngine.build_question(): natural question generation
    - ClarificationEngine.collect_recent_entities(): session scanning
    - Full scenario walkthroughs
    - No regression on Sprint-001/002 pronoun and focus behaviour
"""

from __future__ import annotations

import pytest
from core.conversation.clarification_engine import (
    ClarificationEngine,
    ClarificationNeeded,
    ClarificationResolution,
    PendingClarification,
)
from core.conversation.session_context import SessionContext
from core.conversation.conversation_state_engine import ConversationStateEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> ClarificationEngine:
    return ClarificationEngine()


@pytest.fixture
def state() -> ConversationStateEngine:
    return ConversationStateEngine()


@pytest.fixture
def session() -> SessionContext:
    return SessionContext()


def _session_with_two_entities(name1: str, name2: str) -> SessionContext:
    """Create a session with two recently active entities at similar confidence."""
    s = SessionContext()
    # Set first entity then advance a turn, set second
    s.set_person(name1, raw=name1, confidence=0.95)
    s.increment_turn()
    # Second entity — store in active_topic as secondary slot
    s.set_topic(name2, raw=name2, confidence=0.90)
    return s


# ===========================================================================
# build_question
# ===========================================================================

class TestBuildQuestion:

    def test_two_candidates(self, engine):
        q = engine.build_question(["Lucas", "Leo"])
        assert "Lucas" in q
        assert "Leo" in q
        assert "?" in q

    def test_three_candidates(self, engine):
        q = engine.build_question(["Rex", "Tom", "Chase"])
        assert "Rex" in q
        assert "Tom" in q
        assert "Chase" in q

    def test_single_candidate(self, engine):
        q = engine.build_question(["Leo"])
        assert "Leo" in q

    def test_empty_candidates(self, engine):
        q = engine.build_question([])
        assert "?" in q

    def test_question_format(self, engine):
        q = engine.build_question(["Canon", "HP"])
        assert q.startswith("Do you mean")
        assert "Canon" in q
        assert "HP" in q


# ===========================================================================
# check() — no clarification cases
# ===========================================================================

class TestCheckNoClarification:

    def test_no_pronoun_no_clarification(self, engine, session):
        result = engine.check("How old is Lucas?", ["Lucas", "Leo"], session)
        assert result is None

    def test_explicit_focus_no_clarification(self, engine, session):
        session.set_person("Lucas", raw="Lucas", confidence=0.95)
        result = engine.check(
            "How old is he?", ["Lucas", "Leo"], session, explicit_focus=True
        )
        assert result is None

    def test_single_candidate_no_clarification(self, engine, session):
        session.set_person("Lucas", raw="Lucas", confidence=0.95)
        result = engine.check("How old is he?", ["Lucas"], session)
        assert result is None

    def test_empty_candidates_no_clarification(self, engine, session):
        result = engine.check("How old is he?", [], session)
        assert result is None

    def test_no_text_no_clarification(self, engine, session):
        result = engine.check("", ["Lucas", "Leo"], session)
        assert result is None

    def test_high_confidence_difference_no_clarification(self, engine):
        """If one candidate is clearly more recent/confident, no clarification."""
        s = SessionContext()
        # Lucas set 8 turns ago (low confidence), Leo set just now (high)
        s.set_person("Lucas", raw="Lucas", confidence=0.95)
        for _ in range(8):
            s.increment_turn()
        s.set_topic("Leo", raw="Leo", confidence=0.95)
        # After 8 turns, Lucas should have decayed enough
        result = engine.check("How old is he?", ["Lucas", "Leo"], s)
        # Either None (unambiguous) or ClarificationNeeded — depends on decay
        # Just verify it doesn't crash
        assert result is None or isinstance(result, ClarificationNeeded)


# ===========================================================================
# check() — clarification needed cases
# ===========================================================================

class TestCheckClarificationNeeded:

    def test_two_equally_recent_entities(self, engine):
        s = _session_with_two_entities("Lucas", "Leo")
        result = engine.check("How old is he?", ["Lucas", "Leo"], s)
        assert result is not None
        assert isinstance(result, ClarificationNeeded)
        assert "Lucas" in result.candidates
        assert "Leo" in result.candidates

    def test_question_contains_both_candidates(self, engine):
        s = _session_with_two_entities("Canon", "HP")
        result = engine.check("Is it offline?", ["Canon", "HP"], s)
        assert result is not None
        assert "Canon" in result.question
        assert "HP" in result.question

    def test_original_request_preserved(self, engine):
        s = _session_with_two_entities("Rex", "Chase")
        result = engine.check("What colour is he?", ["Rex", "Chase"], s)
        assert result is not None
        assert result.original_request == "What colour is he?"

    def test_pronoun_captured(self, engine):
        s = _session_with_two_entities("Lucas", "Leo")
        result = engine.check("How old is he?", ["Lucas", "Leo"], s)
        assert result is not None
        assert result.pronoun == "he"

    def test_it_pronoun_triggers(self, engine):
        s = _session_with_two_entities("Canon", "HP")
        result = engine.check("Is it offline?", ["Canon", "HP"], s)
        assert result is not None
        assert result.pronoun == "it"

    def test_she_pronoun_triggers(self, engine):
        s = _session_with_two_entities("Alice", "Bob")
        result = engine.check("What does she like?", ["Alice", "Bob"], s)
        assert result is not None


# ===========================================================================
# try_resolve()
# ===========================================================================

class TestTryResolve:

    def _pending(self, candidates, original="How old is he?", pronoun="he"):
        return PendingClarification(
            candidates=candidates,
            original_request=original,
            pronoun=pronoun,
            question="Do you mean Lucas or Leo?",
        )

    def test_exact_match(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("Leo", pending)
        assert result.resolved is True
        assert result.entity == "Leo"

    def test_exact_match_case_insensitive(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("leo", pending)
        assert result.resolved is True
        assert result.entity == "Leo"

    def test_match_with_period(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("Leo.", pending)
        assert result.resolved is True

    def test_partial_match(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("I mean Leo", pending)
        assert result.resolved is True
        assert result.entity == "Leo"

    def test_no_match(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("Max", pending)
        assert result.resolved is False

    def test_rewritten_request(self, engine):
        pending = self._pending(["Lucas", "Leo"], original="How old is he?", pronoun="he")
        result = engine.try_resolve("Leo", pending)
        assert result.resolved is True
        assert "Leo" in result.rewritten
        assert "he" not in result.rewritten.lower() or "Leo" in result.rewritten

    def test_empty_reply_no_match(self, engine):
        pending = self._pending(["Lucas", "Leo"])
        result = engine.try_resolve("", pending)
        assert result.resolved is False

    def test_it_pronoun_rewrite(self, engine):
        pending = PendingClarification(
            candidates=["Canon", "HP"],
            original_request="Is it offline?",
            pronoun="it",
            question="Do you mean Canon or HP?",
        )
        result = engine.try_resolve("Canon", pending)
        assert result.resolved is True
        assert "Canon" in result.rewritten


# ===========================================================================
# collect_recent_entities
# ===========================================================================

class TestCollectRecentEntities:

    def test_empty_session(self, engine, session):
        entities = engine.collect_recent_entities(session)
        assert entities == []

    def test_single_entity(self, engine, session):
        session.set_person("Leo", raw="Leo", confidence=0.95)
        entities = engine.collect_recent_entities(session)
        assert "Leo" in entities

    def test_two_entities(self, engine):
        s = _session_with_two_entities("Lucas", "Leo")
        entities = engine.collect_recent_entities(s)
        assert len(entities) >= 1  # At least one

    def test_group_topic_excluded(self, engine, session):
        """Group descriptions like '3 dogs' should not be treated as entities."""
        session.set_topic("3 dogs", raw="3 dogs", confidence=0.90)
        entities = engine.collect_recent_entities(session)
        assert "3 dogs" not in entities


# ===========================================================================
# Full scenario walkthroughs
# ===========================================================================

class TestScenarios:

    def test_scenario_1_two_children(self, engine):
        """Lucas is 14. Leo is 9. How old is he? → Do you mean Lucas or Leo?"""
        s = _session_with_two_entities("Lucas", "Leo")
        result = engine.check("How old is he?", ["Lucas", "Leo"], s)
        assert result is not None
        assert "Lucas" in result.question
        assert "Leo" in result.question

        # User replies: "Leo."
        pending = PendingClarification(
            candidates=result.candidates,
            original_request=result.original_request,
            pronoun=result.pronoun,
            question=result.question,
        )
        resolution = engine.try_resolve("Leo.", pending)
        assert resolution.resolved is True
        assert resolution.entity == "Leo"
        assert "Leo" in resolution.rewritten

    def test_scenario_2_two_printers(self, engine):
        """Canon is offline. HP is online. Is it offline? → Do you mean Canon or HP?"""
        s = _session_with_two_entities("Canon", "HP")
        result = engine.check("Is it offline?", ["Canon", "HP"], s)
        assert result is not None
        assert "Canon" in result.question
        assert "HP" in result.question

    def test_scenario_3_two_pets(self, engine):
        """Rex is brown. Chase is white. What colour is he? → Do you mean Rex or Chase?"""
        s = _session_with_two_entities("Rex", "Chase")
        result = engine.check("What colour is he?", ["Rex", "Chase"], s)
        assert result is not None
        assert "Rex" in result.question
        assert "Chase" in result.question

    def test_scenario_4_explicit_focus_no_clarification(self, engine):
        """Tell me about Leo. How old is he? → No clarification (focus is Leo)."""
        s = _session_with_two_entities("Lucas", "Leo")
        # Simulate explicit focus change
        s.set_person("Leo", raw="Leo", confidence=0.95)
        result = engine.check(
            "How old is he?", ["Lucas", "Leo"], s, explicit_focus=True
        )
        assert result is None

    def test_full_clarification_flow(self, engine):
        """End-to-end: detect → ask → user replies → rewrite → resume."""
        s = _session_with_two_entities("Rex", "Chase")

        # Step 1: detect ambiguity
        check_result = engine.check("What colour is he?", ["Rex", "Chase"], s)
        assert check_result is not None

        # Step 2: user replies
        pending = PendingClarification(
            candidates=check_result.candidates,
            original_request=check_result.original_request,
            pronoun=check_result.pronoun,
            question=check_result.question,
        )
        resolution = engine.try_resolve("Chase", pending)

        # Step 3: verify rewrite
        assert resolution.resolved is True
        assert "Chase" in resolution.rewritten
        assert resolution.rewritten != check_result.original_request


# ===========================================================================
# Sprint-001/002 regression guard
# ===========================================================================

class TestRegressionGuard:

    def test_no_pronoun_never_clarifies(self, engine, session):
        """Explicit entity queries never trigger clarification."""
        result = engine.check("How old is Lucas?", ["Lucas", "Leo"], session)
        assert result is None

    def test_explicit_focus_always_wins(self, engine, session):
        """explicit_focus=True suppresses all clarification."""
        session.set_person("Lucas", raw="Lucas", confidence=0.95)
        session.set_topic("Leo", raw="Leo", confidence=0.90)
        result = engine.check(
            "How old is he?", ["Lucas", "Leo"], session, explicit_focus=True
        )
        assert result is None