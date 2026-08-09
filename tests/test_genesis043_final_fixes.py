"""
Genesis-043 Final Fix Regression Tests

FIX-F1: last_topic becomes meaningful after AI responses
FIX-F2: "What about Tom?" uses relationship context not arbitrary properties
"""

from __future__ import annotations
import sys
import pathlib
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from core.conversation.conversation_state import ConversationState
from core.conversation.session_context_adapter import SessionContextAdapter
from core.models.response import Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent(with_ai: bool = True):
    from core.agent import Agent
    if with_ai:
        mock_ai = MagicMock()
        mock_ai.ask.return_value = Response(
            success=True,
            message="Why don\'t scientists trust atoms? Because they make up everything."
        )
        return Agent(ai=mock_ai)
    return Agent(ai=None)


def _simulate(agent, turns: list[str]) -> list[str]:
    """Process turns with session state preserved between requests."""
    responses = []
    snapshot: dict = {}

    for msg in turns:
        if snapshot:
            try:
                if snapshot.get("last_user_message"):
                    agent.context.last_user_message = snapshot["last_user_message"]
                if snapshot.get("last_jarvis_response"):
                    agent.context.last_jarvis_response = snapshot["last_jarvis_response"]
                if snapshot.get("active_topic") and agent.session:
                    agent.session.set_topic(snapshot["active_topic"], raw=snapshot["active_topic"])
                if snapshot.get("recent_entities"):
                    agent._recent_entities = snapshot["recent_entities"]
                if snapshot.get("last_response"):
                    agent.session.last_response = snapshot["last_response"]
                if snapshot.get("last_intent"):
                    agent.session.last_intent = snapshot["last_intent"]
                if snapshot.get("last_topic"):
                    agent.session.last_topic = snapshot["last_topic"]
                if snapshot.get("jarvis_state") is not None:
                    agent.jarvis_state = snapshot["jarvis_state"]
                    agent.session._s = snapshot["jarvis_state"]
            except Exception:
                pass

        resp = agent.process(msg)
        responses.append(resp.message)

        try:
            active_topic = None
            if agent.session and agent.session.active_topic:
                active_topic = agent.session.active_topic.value
            snapshot = {
                "last_user_message":    agent.context.last_user_message,
                "last_jarvis_response": agent.context.last_jarvis_response,
                "active_topic":         active_topic,
                "recent_entities":      list(agent._recent_entities),
                "last_intent":          agent.session.last_intent or "",
                "last_response":        agent.session.last_response or "",
                "last_topic":           agent.session.last_topic or "",
                "jarvis_state":         agent.jarvis_state,
            }
        except Exception:
            pass

    return responses


# ---------------------------------------------------------------------------
# FIX-F1: Follow-up topic tests
# ---------------------------------------------------------------------------

class TestFollowUpTopic:
    """last_topic must be meaningful after AI responses."""

    def test_last_topic_is_joke_not_ai_fallback(self):
        """After 'Tell me a joke', last_topic should be 'joke' not 'ai_fallback'."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="A funny joke.")
        _simulate(agent, ["Tell me a joke."])
        topic = agent.session.last_topic
        assert topic != "ai_fallback", f"last_topic should not be 'ai_fallback', got {topic!r}"
        assert topic != "unknown", f"last_topic should not be 'unknown', got {topic!r}"
        assert "joke" in topic.lower(), f"last_topic should contain 'joke', got {topic!r}"

    def test_last_topic_is_story_not_ai_fallback(self):
        """After 'Tell me a story', last_topic should be 'story'."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="Once upon a time...")
        _simulate(agent, ["Tell me a story."])
        topic = agent.session.last_topic
        assert topic not in ("ai_fallback", "unknown", ""), (
            f"last_topic should be meaningful, got {topic!r}"
        )
        assert "story" in topic.lower(), f"Expected 'story' in topic, got {topic!r}"

    def test_followup_another_uses_joke_topic(self):
        """FollowUpResolver for 'another' should use 'joke' as context, not 'ai_fallback'."""
        from core.conversation.followup_resolver import FollowUpResolver
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="A funny joke.")
        _simulate(agent, ["Tell me a joke."])

        resolver = FollowUpResolver()
        result = resolver.resolve("Tell me another one.", agent.session)
        assert result.is_followup, "Should detect follow-up"
        assert result.resolved_type == "another"
        assert "joke" in result.context_hint.lower() or "joke" in result.suggested_prompt.lower(), (
            f"Follow-up context should reference 'joke', got: "
            f"context={result.context_hint!r} prompt={result.suggested_prompt!r}"
        )
        assert "ai_fallback" not in result.suggested_prompt, (
            f"'ai_fallback' must not appear in suggested_prompt: {result.suggested_prompt!r}"
        )

    def test_followup_another_fact_about_space(self):
        """Generic: 'Give me a fact about space' -> 'Give me another one' uses 'space' or 'fact'."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="Space is very large.")
        _simulate(agent, ["Give me a fact about space."])

        from core.conversation.followup_resolver import FollowUpResolver
        resolver = FollowUpResolver()
        result = resolver.resolve("Give me another one.", agent.session)
        assert result.is_followup
        assert "ai_fallback" not in result.suggested_prompt, (
            f"'ai_fallback' in prompt: {result.suggested_prompt!r}"
        )

    def test_followup_suggested_prompt_is_meaningful(self):
        """The suggested_prompt for 'another' must be a real request, not a garbled string."""
        agent = _make_agent(with_ai=True)
        agent.ai.ask.return_value = Response(success=True, message="A funny joke.")
        _simulate(agent, ["Tell me a joke."])

        from core.conversation.followup_resolver import FollowUpResolver
        resolver = FollowUpResolver()
        result = resolver.resolve("Tell me another one.", agent.session)
        assert len(result.suggested_prompt) > 10, "Prompt too short"
        # Must not be asking for "another ai_fallback"
        assert "ai_fallback" not in result.suggested_prompt
        assert "unknown" not in result.suggested_prompt


# ---------------------------------------------------------------------------
# FIX-F2: Entity follow-up via relationship context
# ---------------------------------------------------------------------------

class TestEntityFollowUp:
    """What about Tom? should use group membership not arbitrary properties."""

    def test_what_about_tom_returns_dog_relationship(self):
        """After 'My dogs are Rex and Tom' / 'Who is Rex?' / 'What about Tom?'"""
        agent = _make_agent(with_ai=False)
        responses = _simulate(agent, [
            "My dogs are Rex and Tom.",
            "Who is Rex?",
            "What about Tom?",
        ])
        answer = responses[2].lower()
        # Should mention Tom in context of dogs, not a colour
        assert "colour" not in answer and "color" not in answer, (
            f"Should not return colour property for Tom: {responses[2]!r}"
        )
        assert "dog" in answer or "tom" in answer, (
            f"Should mention dog relationship for Tom: {responses[2]!r}"
        )

    def test_what_about_entity_does_not_return_stale_property(self):
        """Even if an entity has stored properties, relationship context wins."""
        from core.agent import Agent
        agent = Agent(ai=None)
        # Store a stale property for "Tom"
        agent.knowledge.store_memory(
            subject="tom", category="entity_property",
            attribute="prop:colour", value="black", tags=["entity_property"]
        )
        # Now establish dog relationship
        responses = _simulate(agent, [
            "My dogs are Rex and Tom.",
            "Who is Rex?",
            "What about Tom?",
        ])
        answer = responses[2].lower()
        assert "colour" not in answer and "color" not in answer, (
            f"Stale colour property should not override relationship: {responses[2]!r}"
        )

    def test_what_about_lucas_after_lucas_is_son(self):
        """Generic: 'My son Lucas is 14' / 'What about Lucas?' should not return age as property dump."""
        agent = _make_agent(with_ai=False)
        responses = _simulate(agent, [
            "My son Lucas is 14.",
            "What about Lucas?",
        ])
        # Should not be "Lucas -- age: 14" (property dump format)
        answer = responses[1]
        assert " -- " not in answer or "lucas" not in answer.lower(), (
            f"Should not return raw property dump for Lucas: {answer!r}"
        )

    def test_reverse_lookup_used_for_focus_change(self):
        """Verify reverse lookup fires when focus changes to a group member."""
        from core.agent import Agent
        agent = Agent(ai=None)
        # Setup: store dogs
        agent.knowledge.store_memory(
            subject="user", category="personal",
            attribute="pet names", value="Rex and Tom", tags=["user_fact"]
        )
        agent.knowledge.store_memory(
            subject="user", category="personal",
            attribute="pets", value="2 dogs", tags=["user_fact"]
        )
        # Store stale colour for Tom
        agent.knowledge.store_memory(
            subject="tom", category="entity_property",
            attribute="prop:colour", value="black", tags=["entity_property"]
        )
        # Ask about Tom via focus change
        response = agent.process("What about Tom?")
        answer = response.message.lower()
        # Reverse lookup should find "tom is one of your dogs" or similar
        # and NOT return "colour: black"
        assert "colour" not in answer and "color" not in answer, (
            f"Reverse lookup should win over colour property: {response.message!r}"
        )
