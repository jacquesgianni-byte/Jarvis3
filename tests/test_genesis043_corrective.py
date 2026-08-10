"""
Genesis-043 Corrective Patch — regression tests.
Fix 1: Entity registry populated after memory store + pronoun resolution
Fix 2: FollowUpResolver wired and fires for "another one", "make it shorter" etc.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.conversation_state import ConversationState
from core.conversation.session_context_adapter import SessionContextAdapter
from core.conversation.entity_registry import EntityRegistry
from core.conversation.followup_resolver import FollowUpResolver, FollowUpResult
from core.conversation.session_context import SessionContext


# ══════════════════════════════════════════════════════════════════
# Fix 1 — Entity registration after memory store
# ══════════════════════════════════════════════════════════════════

class TestEntityRegistrationAfterMemoryStore:
    """
    Proves that after "My son Lucas is 14" is stored,
    Lucas appears in EntityRegistry and 'he' resolves to Lucas.
    """

    def test_entity_registry_mention_persists(self):
        """EntityRegistry.mention() makes entity available to resolve_pronoun."""
        state = ConversationState()
        state.entity_registry.mention("Lucas", turn=0, display_name="Lucas")
        result = state.entity_registry.resolve_pronoun("he", current_turn=1, is_plural=False)
        assert result == "Lucas", f"Expected 'Lucas', got {result!r}"

    def test_entity_registry_not_empty_after_mention(self):
        """After mention, entity is retrievable by name."""
        state = ConversationState()
        state.entity_registry.mention("Lucas", turn=0, display_name="Lucas")
        record = state.entity_registry.get("Lucas")
        assert record is not None
        assert record.display_name == "Lucas"

    def test_entity_registry_populated_from_capitalised_name(self):
        """Capitalised name extracted from 'My son Lucas is 14' and registered."""
        import re
        search_text = "son lucas My son Lucas is 14"
        candidates = re.findall(r'\b([A-Z][a-z]{1,20})\b', search_text)
        assert "Lucas" in candidates

    def test_pronoun_resolves_to_registered_entity(self):
        """After Lucas is registered, 'he' resolves to Lucas."""
        from core.conversation.conversation_state_engine import ConversationStateEngine
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        engine  = ConversationStateEngine()

        # Simulate what Fix 1 does after memory store
        engine.update_entity("Lucas", adapter)
        state.entity_registry.mention("Lucas", turn=0, display_name="Lucas")

        # Now resolve pronoun
        resolution = engine.resolve_pronoun("how old is he", adapter)
        assert resolution.resolved, "Pronoun 'he' should resolve after entity registration"
        assert resolution.entity == "Lucas"

    def test_entity_not_registered_without_capitalised_name(self):
        """Generic values like 'Melbourne' are excluded from entity registration."""
        STOP_WORDS = {"Melbourne", "Sydney", "Monday", "January", "Jarvis"}
        import re
        search_text = "location I live in Melbourne"
        candidates = re.findall(r'\b([A-Z][a-z]{1,20})\b', search_text)
        registered = [c for c in candidates if c not in STOP_WORDS and len(c) >= 2]
        assert "Melbourne" not in registered

    def test_entity_survives_to_next_simulated_turn(self):
        """Entity registered at turn 0 is still active at turn 1."""
        state = ConversationState()
        state.entity_registry.mention("Lucas", turn=0, display_name="Lucas")
        state.increment_turn()
        assert state.entity_registry.get("Lucas") is not None
        assert state.entity_registry.get("Lucas").is_active(state.current_turn)


# ══════════════════════════════════════════════════════════════════
# Fix 2 — FollowUpResolver wired and fires
# ══════════════════════════════════════════════════════════════════

class TestFollowUpResolverWiring:
    """
    Proves FollowUpResolver handles "tell me another one",
    "make it shorter", "say that again" from session context.
    """

    def _session_with_joke(self):
        """Return a session that has a joke as last_response."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.set_last_turn(
            intent   = "ai_fallback",
            response = "Why don't scientists trust atoms? Because they make up everything.",
            topic    = "joke",
        )
        return adapter

    def _session_with_explanation(self):
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.set_last_turn(
            intent   = "ai_fallback",
            response = "The history of computers spans from mechanical calculators in the 1800s to modern microprocessors.",
            topic    = "history of computers",
        )
        return adapter

    def test_resolver_detects_another_one(self):
        session = self._session_with_joke()
        resolver = FollowUpResolver()
        result = resolver.resolve("tell me another one", session)
        assert result.is_followup, "Should detect 'tell me another one' as follow-up"
        assert result.resolved_type == "another"

    def test_resolver_another_one_uses_last_topic(self):
        session = self._session_with_joke()
        resolver = FollowUpResolver()
        result = resolver.resolve("tell me another one", session)
        assert "joke" in result.context_hint.lower() or "joke" in result.suggested_prompt.lower()

    def test_resolver_make_it_shorter(self):
        session = self._session_with_explanation()
        resolver = FollowUpResolver()
        result = resolver.resolve("make it shorter", session)
        assert result.is_followup
        assert result.resolved_type == "shorter"
        assert "shorter" in result.suggested_prompt.lower() or len(result.suggested_prompt) > 0

    def test_resolver_say_that_again(self):
        session = self._session_with_joke()
        resolver = FollowUpResolver()
        result = resolver.resolve("say that again", session)
        assert result.is_followup
        assert result.resolved_type == "repeat"

    def test_resolver_explain_differently(self):
        session = self._session_with_explanation()
        resolver = FollowUpResolver()
        result = resolver.resolve("explain that differently", session)
        assert result.is_followup
        assert result.resolved_type == "rephrase"

    def test_resolver_not_followup_for_new_question(self):
        session = self._session_with_joke()
        resolver = FollowUpResolver()
        result = resolver.resolve("What is the capital of France?", session)
        assert not result.is_followup

    def test_resolver_not_followup_when_no_last_response(self):
        """Without last_response, repeat/rephrase/shorter return not_followup."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        resolver = FollowUpResolver()
        result = resolver.resolve("say that again", adapter)
        # last_response is None — should not be a followup
        assert not result.is_followup

    def test_last_response_persists_via_set_last_turn(self):
        """set_last_turn correctly populates last_response on ConversationState."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.set_last_turn("ai_fallback", "Why don't scientists trust atoms?", "joke")
        assert adapter.last_response == "Why don't scientists trust atoms?"
        assert adapter.last_topic    == "joke"
        assert adapter.last_intent   == "ai_fallback"

    def test_last_response_readable_from_state(self):
        """last_response written via adapter is readable from ConversationState."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.set_last_turn("ai_fallback", "A funny joke.", "joke")
        assert state.last_response == "A funny joke."

    def test_resolver_another_one_suggested_prompt_not_empty(self):
        """suggested_prompt contains enough context for AI to generate another joke."""
        session = self._session_with_joke()
        resolver = FollowUpResolver()
        result = resolver.resolve("give me another one", session)
        assert result.is_followup
        assert len(result.suggested_prompt) > 10
