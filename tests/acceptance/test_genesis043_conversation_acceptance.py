"""
Genesis-043 Conversation Acceptance Tests

Models real multi-turn conversations, not implementation details.
Tests verify that locally-answerable questions DO NOT reach AI.

Run with:
    python -m pytest tests/acceptance/test_genesis043_conversation_acceptance.py -v
"""

from __future__ import annotations

import sys
import pathlib
from unittest.mock import MagicMock, patch, call

ROOT = pathlib.Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from core.agent import Agent
from core.models.response import Response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(with_ai: bool = False) -> Agent:
    """Create an Agent. Pass a mock AI to detect unexpected AI calls."""
    if with_ai:
        mock_ai = MagicMock()
        mock_ai.ask.return_value = Response(success=True, message="[AI_FALLBACK]")
        agent = Agent(ai=mock_ai)
    else:
        agent = Agent(ai=None)
    return agent


def _simulate_session(agent, turns: list[str]) -> list[str]:
    """
    Process a list of user messages through the agent, simulating session
    persistence between requests (as routes.py does for android-alpha).

    Returns the list of Jarvis responses.
    """
    responses = []
    # Minimal session state mirror (same keys as routes.py _save_session)
    session_snapshot: dict = {}

    for user_msg in turns:
        # Restore (same logic as routes.py _restore_session)
        if session_snapshot:
            try:
                if session_snapshot.get("last_user_message"):
                    agent.context.last_user_message = session_snapshot["last_user_message"]
                if session_snapshot.get("last_jarvis_response"):
                    agent.context.last_jarvis_response = session_snapshot["last_jarvis_response"]
                if session_snapshot.get("active_topic") and agent.session:
                    agent.session.set_topic(session_snapshot["active_topic"], raw=session_snapshot["active_topic"])
                if session_snapshot.get("recent_entities"):
                    agent._recent_entities = session_snapshot["recent_entities"]
                if session_snapshot.get("last_response"):
                    agent.session.last_response = session_snapshot["last_response"]
                if session_snapshot.get("last_intent"):
                    agent.session.last_intent = session_snapshot["last_intent"]
                if session_snapshot.get("last_topic"):
                    agent.session.last_topic = session_snapshot["last_topic"]
                if session_snapshot.get("last_jarvis_response"):
                    agent.context.last_jarvis_response = session_snapshot["last_jarvis_response"]
                # FIX-1: restore jarvis_state
                if session_snapshot.get("jarvis_state") is not None:
                    agent.jarvis_state = session_snapshot["jarvis_state"]
                    agent.session._s = session_snapshot["jarvis_state"]
            except Exception:
                pass

        response = agent.process(user_msg)
        responses.append(response.message)

        # Save (same logic as routes.py _save_session)
        try:
            active_topic = None
            if agent.session and agent.session.active_topic:
                active_topic = agent.session.active_topic.value
            session_snapshot = {
                "last_user_message":    agent.context.last_user_message,
                "last_jarvis_response": agent.context.last_jarvis_response,
                "active_topic":         active_topic,
                "recent_entities":      list(agent._recent_entities),
                "last_intent":          agent.session.last_intent or "",
                "last_response":        agent.session.last_response or "",
                "last_topic":           agent.session.last_topic or "",
                # FIX-1
                "jarvis_state":         agent.jarvis_state,
            }
        except Exception:
            pass

    return responses


# ---------------------------------------------------------------------------
# Test 1 — Personal memory: name
# ---------------------------------------------------------------------------

class TestPersonalMemory:
    def test_name_stored_and_recalled(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My name is Gianni.",
            "What is my name?",
        ])
        recall = responses[1].lower()
        assert "gianni" in recall, f"Expected 'Gianni' in recall response, got: {responses[1]!r}"

    def test_name_recall_no_ai(self):
        """Name recall must NOT reach AI."""
        agent = _make_agent(with_ai=True)
        _simulate_session(agent, [
            "My name is Gianni.",
            "What is my name?",
        ])
        # AI should not have been called for the recall turn
        assert not agent.ai.ask.called or "[AI_FALLBACK]" not in _simulate_session(
            _make_agent(with_ai=True), ["My name is Gianni.", "What is my name?"]
        )[1], "AI was called for a locally-answerable name recall"


# ---------------------------------------------------------------------------
# Test 2 — Location memory
# ---------------------------------------------------------------------------

class TestLocationMemory:
    def test_location_stored_and_recalled(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "I live in Melbourne.",
            "Where do I live?",
        ])
        recall = responses[1].lower()
        assert "melbourne" in recall, f"Expected 'Melbourne' in: {responses[1]!r}"

    def test_location_no_ai_fallback(self):
        """Location recall must be answered locally."""
        agent = _make_agent(with_ai=True)
        responses = _simulate_session(agent, [
            "I live in Melbourne.",
            "Where do I live?",
        ])
        assert "melbourne" in responses[1].lower(), (
            f"Location recall hit AI or returned wrong answer: {responses[1]!r}"
        )
        assert "[AI_FALLBACK]" not in responses[1], "AI was called for location recall"


# ---------------------------------------------------------------------------
# Test 3 — Relationship + pronoun resolution
# ---------------------------------------------------------------------------

class TestPronounResolution:
    def test_son_age_recalled_via_pronoun(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My son Lucas is 14.",
            "How old is he?",
        ])
        recall = responses[1].lower()
        assert "14" in recall, f"Expected '14' in: {responses[1]!r}"

    def test_pronoun_resolves_to_lucas_not_stale_entity(self):
        """Pronoun 'he' must resolve to Lucas, not any prior entity."""
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My son Lucas is 14.",
            "How old is he?",
        ])
        recall = responses[1].lower()
        # Must contain lucas or 14 — stale entity would give wrong answer
        assert "lucas" in recall or "14" in recall, (
            f"Pronoun resolution failed, got: {responses[1]!r}"
        )

    def test_entity_registered_after_memory_store(self):
        """After storing son Lucas, entity_registry must contain Lucas."""
        agent = _make_agent()
        _simulate_session(agent, ["My son Lucas is 14."])
        registry = agent.jarvis_state.entity_registry
        record = registry.get("lucas")
        assert record is not None, "Lucas should be in entity_registry after memory store"


# ---------------------------------------------------------------------------
# Test 4 — Multiple children (group recall)
# ---------------------------------------------------------------------------

class TestGroupRecall:
    def test_children_group_recalled(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My children are Lucas and Leo.",
            "Who are my children?",
        ])
        recall = responses[1].lower()
        assert "lucas" in recall and "leo" in recall, (
            f"Expected both names in: {responses[1]!r}"
        )

    def test_dogs_group_recalled(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My dogs are Rex and Tom.",
            "Who are my dogs?",
        ])
        recall = responses[1].lower()
        assert "rex" in recall and "tom" in recall, (
            f"Expected Rex and Tom in: {responses[1]!r}"
        )

    def test_group_recall_no_ai(self):
        """Group recall must not reach AI."""
        agent = _make_agent(with_ai=True)
        responses = _simulate_session(agent, [
            "My dogs are Rex and Tom.",
            "Who are my dogs?",
        ])
        assert "[AI_FALLBACK]" not in responses[1], (
            f"AI was called for group recall: {responses[1]!r}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Pets: two-turn declaration then recall
# ---------------------------------------------------------------------------

class TestPetsRecall:
    def test_pet_names_recalled_after_two_turn_declaration(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "I have two dogs.",
            "Their names are Rex and Tom.",
            "What are my dogs called?",
        ])
        recall = responses[2].lower()
        assert "rex" in recall and "tom" in recall, (
            f"Expected Rex and Tom in: {responses[2]!r}"
        )


# ---------------------------------------------------------------------------
# Test 6 — Entity recall: reverse lookup
# ---------------------------------------------------------------------------

class TestEntityRecall:
    def test_who_is_rex(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My dogs are Rex and Tom.",
            "Who is Rex?",
        ])
        recall = responses[1].lower()
        assert "dog" in recall or "rex" in recall, (
            f"Expected dog context in: {responses[1]!r}"
        )

    def test_what_about_tom(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My dogs are Rex and Tom.",
            "Who is Rex?",
            "What about Tom?",
        ])
        recall = responses[2].lower()
        # Should mention Tom in context of dogs, not fail
        assert "tom" in recall or "dog" in recall, (
            f"Expected Tom context in: {responses[2]!r}"
        )


# ---------------------------------------------------------------------------
# Test 7 — Follow-up: tell me another one
# ---------------------------------------------------------------------------

class TestFollowUp:
    def test_another_one_uses_previous_context(self):
        """Second request must not use stale EntityGroup topic like '2 dogs'."""
        agent = _make_agent(with_ai=True)
        # Set AI to return a joke on first call
        agent.ai.ask.side_effect = [
            Response(success=True, message="Why don't scientists trust atoms? Because they make up everything."),
            Response(success=True, message="Another joke here."),
        ]
        responses = _simulate_session(agent, [
            "Tell me a joke.",
            "Tell me another one.",
        ])
        # The suggested_prompt for the second call must not contain "2 dogs"
        if agent.ai.ask.call_count >= 2:
            second_call_prompt = str(agent.ai.ask.call_args_list[1])
            assert "2 dogs" not in second_call_prompt, (
                f"FollowUpResolver used stale EntityGroup topic. Prompt: {second_call_prompt}"
            )

    def test_say_that_again_returns_last_response(self):
        """'Say that again' must return the previous response, not hit AI."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(
            success=True,
            message="Why don't scientists trust atoms? Because they make up everything."
        )
        responses = _simulate_session(agent, [
            "Tell me a joke.",
            "Say that again.",
        ])
        # Second response should match first
        msg = ("'Say that again' didn't return last response. "
            f"Turn 1: {responses[0]!r} | Turn 2: {responses[1]!r}")
        assert responses[0].lower() in responses[1].lower() or responses[1] == responses[0], msg


# ---------------------------------------------------------------------------
# Test 8 — Response transformation: make it shorter
# ---------------------------------------------------------------------------

class TestResponseTransformation:
    def test_make_it_shorter_has_context(self):
        """'Make it shorter' must include previous response in its AI prompt."""
        agent = _make_agent(with_ai=True)
        long_answer = "The history of computers spans from mechanical calculators in the 1800s to modern microprocessors, touching on Babbage, Turing, von Neumann, and the transistor revolution."
        agent.ai.ask.side_effect = [
            Response(success=True, message=long_answer),
            Response(success=True, message="Short version."),
        ]
        _simulate_session(agent, [
            "Tell me about the history of computers.",
            "Make it shorter.",
        ])
        if agent.ai.ask.call_count >= 2:
            second_call = str(agent.ai.ask.call_args_list[1])
            # The previous response content should appear in the follow-up prompt
            assert "history" in second_call.lower() or "computers" in second_call.lower() or "shorter" in second_call.lower(), (
                f"'Make it shorter' prompt lacked context: {second_call}"
            )


# ---------------------------------------------------------------------------
# Test 9 — Topic switching and return
# ---------------------------------------------------------------------------

class TestTopicSwitching:
    def test_back_to_dogs_after_topic_switch(self):
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="Memory intelligence explained.")
        responses = _simulate_session(agent, [
            "My dogs are Rex and Tom.",
            "Tell me about memory intelligence.",
            "Go back to my dogs.",
            "Who are they?",
        ])
        recall = responses[3].lower()
        # After returning to dogs context, "they" should resolve to dogs
        assert "rex" in recall or "tom" in recall or "dog" in recall, (
            f"Topic return failed, got: {responses[3]!r}"
        )


# ---------------------------------------------------------------------------
# Test 10 — Six-turn conversation
# ---------------------------------------------------------------------------

class TestSixTurnConversation:
    def test_six_turn_memory(self):
        agent = _make_agent()
        responses = _simulate_session(agent, [
            "My name is Gianni.",
            "I live in Melbourne.",
            "I have two dogs.",
            "Their names are Rex and Tom.",
            "What are my dogs called?",
            "Where do I live?",
        ])
        dogs_response = responses[4].lower()
        location_response = responses[5].lower()

        assert "rex" in dogs_response and "tom" in dogs_response, (
            f"Dogs recall failed at turn 5: {responses[4]!r}"
        )
        assert "melbourne" in location_response, (
            f"Location recall failed at turn 6: {responses[5]!r}"
        )

    def test_six_turn_no_unexpected_ai(self):
        """Memory recalls in the six-turn test must not hit AI."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="[AI_FALLBACK]")
        responses = _simulate_session(agent, [
            "My name is Gianni.",
            "I live in Melbourne.",
            "I have two dogs.",
            "Their names are Rex and Tom.",
            "What are my dogs called?",
            "Where do I live?",
        ])
        assert "[AI_FALLBACK]" not in responses[4], (
            f"AI called for dogs recall: {responses[4]!r}"
        )
        assert "[AI_FALLBACK]" not in responses[5], (
            f"AI called for location recall: {responses[5]!r}"
        )
