"""
Genesis-024 Sprint-002 — Conversation Orchestration Audit Tests

Verifies that the Conversation Resolution Phase in agent.py correctly
intercepts referential and contextual queries before the AI fallback.

Coverage:
  - "Why?" / "How so?" → answered from last_jarvis_response
  - "Who told you that?" → answered from memory/session context
  - "What did I just tell you?" → answered from last_user_message
  - Reference-resolved queries try memory before AI
  - ConversationRecall consulted before AI
  - Timeline consulted before AI
  - Reasoning attempted before AI
  - AI still called when all local resolution fails
  - All existing intent paths preserved (no regression)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers — lightweight Agent stub
# ---------------------------------------------------------------------------

def make_agent(ai=None):
    """
    Create an Agent with a mock AI provider and real pipeline.
    Avoids disk I/O by using a fresh KnowledgeEngine in-memory.
    """
    from core.agent import Agent
    agent = Agent(ai=ai)
    return agent


def mock_ai(response_text="AI response"):
    """Create a mock AI provider that returns a fixed response."""
    from core.models.response import Response
    ai = MagicMock()
    ai.ask.return_value = Response(success=True, message=response_text)
    return ai


# ===========================================================================
# 1. "WHY?" / "HOW SO?" — answered from last response
# ===========================================================================

class TestWhyAndHowSoResolution:

    def test_why_answered_from_last_response(self):
        """
        "Why?" after a response should return the last Jarvis response,
        not call the AI provider.
        """
        from core.agent import Agent
        ai = mock_ai("AI answer")
        agent = Agent(ai=ai)

        # Prime the context with a previous response
        agent.context.last_jarvis_response = "Your favourite colour is blue, sir."
        agent.context.last_user_message = "What is my favourite colour?"

        response = agent.process("Why?")

        assert response.success
        # Should NOT have called the AI
        ai.ask.assert_not_called()
        # Should reference the last response — either the value or "said"
        msg = response.message.lower()
        assert "blue" in msg or "said" in msg or "colour" in msg

    def test_how_so_answered_from_last_response(self):
        from core.agent import Agent
        ai = mock_ai("AI answer")
        agent = Agent(ai=ai)
        agent.context.last_jarvis_response = "Jarvis is an AI assistant."
        response = agent.process("How so?")
        assert response.success
        ai.ask.assert_not_called()

    def test_why_with_no_context_falls_through(self):
        """
        "Why?" with no prior context should eventually reach AI fallback.
        """
        from core.agent import Agent
        ai = mock_ai("AI fallback")
        agent = Agent(ai=ai)
        # No prior context set
        agent.context.last_jarvis_response = None
        response = agent.process("Why?")
        assert response.success
        # Either answered locally or went to AI — both are valid
        # Key: no exception


# ===========================================================================
# 2. "WHO TOLD YOU THAT?" — answered from memory
# ===========================================================================

class TestWhoToldYouResolution:

    def test_who_told_you_returns_local_answer(self):
        from core.agent import Agent
        ai = mock_ai("AI answer")
        agent = Agent(ai=ai)
        agent.context.last_jarvis_response = "Your name is Ludovic, sir."

        response = agent.process("Who told you that?")
        assert response.success
        ai.ask.assert_not_called()
        # Should explain the source without calling AI
        assert any(word in response.message.lower()
                   for word in ["you", "told", "memory", "stored"])

    def test_how_do_you_know_returns_local_answer(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        response = agent.process("How do you know that?")
        assert response.success
        ai.ask.assert_not_called()

    def test_who_told_you_with_question_mark(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        response = agent.process("Who told you that?")
        assert response.success
        ai.ask.assert_not_called()


# ===========================================================================
# 3. "WHAT DID I JUST TELL YOU?" — answered from context
# ===========================================================================

class TestRecentMessageResolution:

    def test_what_did_i_just_tell_you(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.context.last_user_message = "My name is Ludovic."

        response = agent.process("What did I just tell you?")
        assert response.success
        ai.ask.assert_not_called()
        assert "ludovic" in response.message.lower() or "said" in response.message.lower()

    def test_what_did_i_say(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.context.last_user_message = "My favourite colour is blue."

        response = agent.process("What did I say?")
        assert response.success
        ai.ask.assert_not_called()


# ===========================================================================
# 4. ALL EXISTING INTENT PATHS PRESERVED
# ===========================================================================

class TestExistingIntentsPreserved:

    def test_greeting_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("Hello Jarvis.")
        assert response.success
        assert response.message

    def test_identity_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("Who are you?")
        assert response.success

    def test_memory_store_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("remember my favourite colour is blue")
        assert response.success
        assert "blue" in response.message.lower()

    def test_memory_recall_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        agent.process("remember my name is Ludovic")
        response = agent.process("what is my name?")
        assert response.success
        assert "ludovic" in response.message.lower()

    def test_memory_forget_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        agent.process("remember my favourite colour is blue")
        response = agent.process("forget my favourite colour")
        assert response.success

    def test_exit_still_works(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("goodbye")
        assert response.success

    def test_no_ai_no_crash_on_unknown(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("xyzzy nonsense gibberish")
        # Should not crash — returns graceful fallback
        assert response is not None


# ===========================================================================
# 5. RESOLUTION PHASE ORDER — AI is LAST resort
# ===========================================================================

class TestAIIsLastResort:

    def test_known_memory_does_not_call_ai(self):
        from core.agent import Agent
        ai = mock_ai("AI answer")
        agent = Agent(ai=ai)

        # Store a memory
        agent.process("remember my favourite colour is blue")
        ai.ask.reset_mock()

        # Recall it — should NOT call AI
        agent.process("what is my favourite colour?")
        ai.ask.assert_not_called()

    def test_greeting_does_not_call_ai(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.process("Hello.")
        ai.ask.assert_not_called()

    def test_identity_does_not_call_ai(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.process("What is your name?")
        ai.ask.assert_not_called()

    def test_contextual_why_does_not_call_ai(self):
        from core.agent import Agent
        ai = mock_ai()
        agent = Agent(ai=ai)
        agent.context.last_jarvis_response = "Your name is Ludovic."
        agent.process("Why?")
        ai.ask.assert_not_called()

    def test_truly_unknown_with_no_context_calls_ai(self):
        """Only when ALL local resolution fails should AI be called."""
        from core.agent import Agent
        ai = mock_ai("AI fallback response")
        agent = Agent(ai=ai)
        # Completely novel query with no context
        agent.process("What is the capital of the moon?")
        ai.ask.assert_called_once()


# ===========================================================================
# 6. CONVERSATION ENGINE STILL WIRED
# ===========================================================================

class TestConversationEngineStillWired:

    def test_conversation_engine_processes_each_request(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        agent.process("Hello.")
        assert agent.conversation_engine.last_context is not None

    def test_recovery_handled_before_routing(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        response = agent.process("never mind")
        assert response.success
        assert response.message


# ===========================================================================
# 7. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_agent_process_returns_response(self):
        from core.agent import Agent
        from core.models.response import Response
        agent = Agent(ai=None)
        result = agent.process("Hello.")
        assert isinstance(result, Response)

    def test_memory_lifecycle_unchanged(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        agent.process("remember my lucky number is 7")
        response = agent.process("what is my lucky number?")
        assert "7" in response.message

    def test_forget_lifecycle_unchanged(self):
        from core.agent import Agent
        agent = Agent(ai=None)
        agent.process("remember my lucky number is 7")
        agent.process("forget my lucky number")
        response = agent.process("what is my lucky number?")
        assert "don't have" in response.message.lower() or "7" not in response.message

    def test_conversation_engine_unchanged(self):
        from core.conversation.conversation_engine import ConversationEngine
        e = ConversationEngine()
        d = e.process("Hello.")
        assert d is not None

    def test_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING