"""
CFR-003 Regression Tests -- Internal skill names must never become last_topic

Tests the invariant:
    INTERNAL ROUTING/SKILL NAMES MUST NEVER BECOME THE USER'S CONVERSATIONAL TOPIC.

These tests exercise _post_turn() via a minimal stub.
No KnowledgeEngine, no storage, no AI calls needed.
"""

import pytest
from unittest.mock import MagicMock
from core.conversation.session_context import SessionContext
from core.conversation.context import ConversationContext


class _AgentStub:
    """Minimal stub providing exactly what _post_turn() reads/writes."""

    def __init__(self):
        self.context = ConversationContext()
        self.session = SessionContext()
        self.logger = MagicMock()
        self.jarvis_state = MagicMock()
        self.jarvis_state.summariser = MagicMock()
        self.jarvis_state.summariser.add_turn = MagicMock()
        self.jarvis_state.summariser.build_abstract_from_state = MagicMock()
        self.jarvis_state.current_turn = 0
        self.conversation_observer = MagicMock()
        self.context_manager = MagicMock()
        self.timeline = MagicMock()
        self.timeline.count = MagicMock(return_value=0)
        self.timeline.all_events = MagicMock(return_value=[])
        self.timeline.record_from_facts = MagicMock()
        self.decision_engine = MagicMock()
        self.goal_engine = MagicMock()
        self.summary_engine = MagicMock()

    def _post_turn(self, request: str, response_message: str) -> None:
        from core.agent import Agent
        Agent._post_turn(self, request, response_message)


class TestCFR003InternalSkillTopicInvariant:

    def test_followup_resolver_never_becomes_topic(self):
        """Core CFR-003 regression -- four-turn joke chain."""
        agent = _AgentStub()

        agent.context.last_user_message = "Tell me a joke."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Tell me a joke.", "Why don't scientists trust atoms?")
        assert agent.session.last_topic == "joke", f"Turn 1: got {agent.session.last_topic!r}"

        agent.context.last_user_message = "Tell me another one."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Tell me another one.", "Why did the scarecrow win an award?")
        assert agent.session.last_topic == "joke", (
            f"Turn 2: 'followup_resolver' became last_topic. Got {agent.session.last_topic!r}"
        )

        agent.context.last_user_message = "Tell me another one."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Tell me another one.", "What do you call a fake noodle?")
        assert agent.session.last_topic == "joke", (
            f"Turn 3: topic corrupted. Got {agent.session.last_topic!r}"
        )

        agent.context.last_user_message = "Say that again."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Say that again.", "What do you call a fake noodle?")
        assert agent.session.last_topic == "joke", (
            f"Turn 4: topic corrupted after repeat. Got {agent.session.last_topic!r}"
        )

    def test_internal_skills_never_become_topic(self):
        """All _INTERNAL_SKILLS must never pollute last_topic."""
        internal_skills = [
            "followup_resolver", "memory", "memory_store",
            "system", "engineering", "reasoning",
        ]
        for skill_name in internal_skills:
            agent = _AgentStub()
            agent.context.last_user_message = "Tell me a joke."
            agent.context.last_skill = "ai_fallback"
            agent._post_turn("Tell me a joke.", "A joke.")
            assert agent.session.last_topic == "joke"

            agent.context.last_user_message = "Tell me another one."
            agent.context.last_skill = skill_name
            agent._post_turn("Tell me another one.", "Another response.")
            assert agent.session.last_topic == "joke", (
                f"Skill '{skill_name}' became last_topic. Got {agent.session.last_topic!r}"
            )

    def test_topic_preserved_across_repeat(self):
        agent = _AgentStub()
        agent.context.last_user_message = "Tell me a joke."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Tell me a joke.", "A joke.")
        assert agent.session.last_topic == "joke"

        agent.context.last_user_message = "Say that again."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Say that again.", "A joke.")
        assert agent.session.last_topic == "joke", (
            f"last_topic changed after repeat. Got {agent.session.last_topic!r}"
        )


class TestCFR003TopicSwitch:

    def test_topic_switch_updates_topic(self):
        """After topic switch, follow-ups must refer to the NEW topic."""
        agent = _AgentStub()

        agent.context.last_user_message = "Tell me a joke."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Tell me a joke.", "A funny joke.")
        assert agent.session.last_topic == "joke"

        agent.context.last_user_message = "Tell me about Australian history."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Tell me about Australian history.", "Australian history.")
        assert agent.session.last_topic not in ("joke", "followup_resolver"), (
            f"Topic should have switched from 'joke'. Got {agent.session.last_topic!r}"
        )
        new_topic = agent.session.last_topic

        agent.context.last_user_message = "Tell me another one."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Tell me another one.", "More Australian history.")
        assert agent.session.last_topic == new_topic, (
            f"Follow-up should use {new_topic!r}, got {agent.session.last_topic!r}"
        )

    def test_explanation_followup_chain(self):
        agent = _AgentStub()
        agent.context.last_user_message = "Explain recursion."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Explain recursion.", "Recursion is when a function calls itself.")
        assert agent.session.last_topic == "recursion"

        agent.context.last_user_message = "Explain that differently."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Explain that differently.", "Think of recursion like Russian dolls.")
        assert agent.session.last_topic == "recursion", (
            f"Expected 'recursion' after rephrase. Got {agent.session.last_topic!r}"
        )

        agent.context.last_user_message = "Tell me more."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Tell me more.", "Here's more about recursion.")
        assert agent.session.last_topic == "recursion", (
            f"Expected 'recursion' after expand. Got {agent.session.last_topic!r}"
        )

    def test_recipe_followup_chain(self):
        agent = _AgentStub()
        agent.context.last_user_message = "Give me a pasta recipe."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Give me a pasta recipe.", "Here's a pasta recipe...")
        assert agent.session.last_topic == "pasta"

        agent.context.last_user_message = "Tell me another one."
        agent.context.last_skill = "followup_resolver"
        agent._post_turn("Tell me another one.", "Here's another pasta recipe...")
        assert agent.session.last_topic == "pasta", (
            f"Expected 'pasta' after follow-up. Got {agent.session.last_topic!r}"
        )


class TestCFR003AIFallbackTopicExtraction:

    def test_ai_fallback_extracts_topic(self):
        agent = _AgentStub()
        agent.context.last_user_message = "Tell me about black holes."
        agent.context.last_skill = "ai_fallback"
        agent._post_turn("Tell me about black holes.", "Black holes are regions...")
        assert agent.session.last_topic == "black", (
            f"Expected topic from message. Got {agent.session.last_topic!r}"
        )

    def test_unknown_skill_extracts_topic(self):
        agent = _AgentStub()
        agent.context.last_user_message = "Tell me about volcanoes."
        agent.context.last_skill = "unknown"
        agent._post_turn("Tell me about volcanoes.", "Volcanoes are...")
        assert agent.session.last_topic == "volcanoes", (
            f"Expected 'volcanoes'. Got {agent.session.last_topic!r}"
        )
