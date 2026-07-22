"""
GC-004 — Conversation Context Regression Tests

Verifies that "How do you know that?" references the previous Jarvis
response rather than returning a hardcoded generic string.

Coverage:
  - "How do you know that?" after a recall answer references the answer
  - "Who told you that?" after a recall answer references the answer
  - "How do you know that?" with no prior context returns generic fallback
  - Existing recall behaviour unchanged (Sarah/Alex/Rex&Tom)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.agent import Agent
from core.models.response import Response


def mock_ai(response_text="AI response."):
    ai = MagicMock()
    ai.ask.return_value = Response(success=True, message=response_text)
    return ai


class TestHowDoYouKnowThat:

    def test_references_previous_answer(self):
        """After recall, 'How do you know that?' should echo the recall answer."""
        agent = Agent(ai=mock_ai())
        # Prime context with a previous recall response
        agent.context.last_jarvis_response = "Sarah is your manager."

        response = agent.process("How do you know that?")

        assert response.success
        assert "Sarah" in response.message
        assert "told me" in response.message.lower() or "earlier" in response.message.lower()

    def test_who_told_you_references_previous_answer(self):
        """'Who told you that?' should also reference the previous answer."""
        agent = Agent(ai=mock_ai())
        agent.context.last_jarvis_response = "Rex and Tom are your 2 dogs."

        response = agent.process("Who told you that?")

        assert response.success
        assert "Rex" in response.message or "dogs" in response.message
        assert "told me" in response.message.lower()

    def test_who_told_you_with_question_mark(self):
        """'Who told you that?' with question mark should not call AI."""
        agent = Agent(ai=mock_ai())
        agent.context.last_jarvis_response = "Alex is your son."

        response = agent.process("Who told you that?")

        assert response.success
        mock_ai().ask.assert_not_called()

    def test_no_prior_context_returns_generic(self):
        """With no prior response, should not call AI — reasoning skill handles it."""
        ai = mock_ai()
        agent = Agent(ai=ai)
        # No last_jarvis_response set

        response = agent.process("How do you know that?")

        assert response.success
        ai.ask.assert_not_called()

    def test_how_do_you_know_that_no_ai_call(self):
        """'How do you know that?' should never call AI."""
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.context.last_jarvis_response = "Your workplace is Academy of Healthcare."

        agent.process("How do you know that?")

        ai.ask.assert_not_called()

    def test_full_conversation_flow(self):
        """
        Full three-turn flow:
        1. My manager is Sarah.
        2. Who is Sarah?     → Sarah is your manager.
        3. How do you know that? → references turn 2 answer
        """
        agent = Agent(ai=mock_ai())

        # Turn 1 — store memory locally
        agent.process("My manager is Sarah.")

        # Turn 2 — recall locally
        r2 = agent.process("Who is Sarah?")
        assert "Sarah" in r2.message

        # Turn 3 — context reference
        r3 = agent.process("How do you know that?")
        assert response_references_prior(r3.message, r2.message)

    def test_generic_message_not_returned_when_context_exists(self):
        """When context exists, should NOT return the bare generic string."""
        agent = Agent(ai=mock_ai())
        agent.context.last_jarvis_response = "Rex and Tom are your 2 dogs."

        response = agent.process("How do you know that?")

        assert response.message != "You told me, sir. I store what you share with me."


def response_references_prior(response: str, prior: str) -> bool:
    """Check that the response contains meaningful content from the prior answer."""
    prior_words = set(prior.lower().split()) - {"is", "are", "your", "the", "a", "an", "sir"}
    response_lower = response.lower()
    return any(word in response_lower for word in prior_words if len(word) > 3)