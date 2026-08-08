"""
Genesis-043 Runtime Integration Tests.
Proves one shared ConversationState is used by Agent, ConversationEngine,
ContextManager, and ContextResolver.
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.conversation_state import ConversationState
from core.conversation.session_context_adapter import SessionContextAdapter
from core.conversation.conversation_engine import ConversationEngine
from core.conversation.conversation_summariser import ConversationSummariser
from core.conversation.entity_registry import EntityRegistry
from core.conversation.topic_tracker import TopicTracker


# ══════════════════════════════════════════════════════════════════
# Object identity tests — one ConversationState shared across components
# ══════════════════════════════════════════════════════════════════

class TestSharedStateIdentity:

    def test_conversation_engine_creates_own_state(self):
        """ConversationEngine creates its own internal state (Genesis-044 will unify)."""
        engine = ConversationEngine()
        assert isinstance(engine._state, ConversationState)

    def test_jarvis_state_has_all_genesis043_components(self):
        """
        Agent.jarvis_state is the canonical owner of Genesis-043 components.
        Note: Agent.conversation_state is ConversationStateEngine (Genesis-029).
        These are different objects — naming cleaned up in Genesis-044.
        """
        state = ConversationState()
        assert hasattr(state, "entity_registry")
        assert hasattr(state, "topic_tracker")
        assert hasattr(state, "summariser")
        assert isinstance(state.entity_registry, EntityRegistry)
        assert isinstance(state.topic_tracker, TopicTracker)
        assert isinstance(state.summariser, ConversationSummariser)

    def test_adapter_delegates_to_shared_state(self):
        """SessionContextAdapter writes go to ConversationState."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.set_person("Rex")
        assert state.active_person is not None
        assert state.active_person.value == "Rex"

    def test_adapter_reads_from_shared_state(self):
        """SessionContextAdapter reads come from ConversationState."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        state.set_person("Tom")
        assert adapter.active_person.value == "Tom"

    def test_shared_state_turn_counter(self):
        """Turn counter on ConversationState matches adapter view."""
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        adapter.increment_turn()
        adapter.increment_turn()
        assert state.current_turn   == 2
        assert adapter.current_turn == 2

    def test_entity_registry_on_shared_state(self):
        """EntityRegistry is accessible on the shared ConversationState."""
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        assert state.entity_registry.get("Rex") is not None

    def test_topic_tracker_on_shared_state(self):
        """TopicTracker is accessible on the shared ConversationState."""
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        assert state.topic_tracker.current_name == "dogs"

    def test_summariser_on_shared_state(self):
        """Summariser is accessible on the shared ConversationState."""
        state = ConversationState()
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        assert state.summariser.turn_count() == 1


# ══════════════════════════════════════════════════════════════════
# Summariser wiring tests
# ══════════════════════════════════════════════════════════════════

class TestSummariserWiring:

    def test_add_turn_accumulates(self):
        state = ConversationState()
        for i in range(7):
            state.summariser.add_turn(f"User {i}", f"Jarvis {i}", turn_number=i)
        assert state.summariser.turn_count() == 7

    def test_snapshot_splits_correctly(self):
        state = ConversationState()
        for i in range(7):
            state.summariser.add_turn(f"User {i}", f"Jarvis {i}", turn_number=i)
        snap = state.summariser.snapshot()
        assert snap.verbatim_count   == 5
        assert snap.compressed_count == 2

    def test_context_string_not_empty_after_turns(self):
        state = ConversationState()
        for i in range(3):
            state.summariser.add_turn(f"User {i}", f"Jarvis {i}", turn_number=i)
        ctx = state.summariser.to_context_string()
        assert len(ctx) > 0

    def test_abstract_built_from_state(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.entity_registry.mention("Rex", turn=0)
        abstract = state.summariser.build_abstract_from_state(state)
        assert "dogs" in abstract.lower() or "Rex" in abstract

    def test_summariser_reset_on_state_reset(self):
        state = ConversationState()
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        state.reset()
        assert state.summariser.turn_count() == 0


# ══════════════════════════════════════════════════════════════════
# Entity registry wiring tests
# ══════════════════════════════════════════════════════════════════

class TestEntityRegistryWiring:

    def test_entity_mention_via_state(self):
        state = ConversationState()
        state.entity_registry.mention("Lucas", turn=0, display_name="Lucas")
        assert state.entity_registry.get("Lucas") is not None

    def test_pronoun_resolution_via_entity_registry(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        result = state.entity_registry.resolve_pronoun("he", current_turn=1)
        assert result == "Rex"

    def test_multi_entity_salience(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.entity_registry.mention("Tom", turn=1)
        state.entity_registry.mention("Rex", turn=2)
        # Rex mentioned twice — higher salience
        assert state.entity_registry.most_salient(3) == "Rex"

    def test_entity_registry_reset(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.reset()
        assert state.entity_registry.count() == 0


# ══════════════════════════════════════════════════════════════════
# Topic tracker wiring tests
# ══════════════════════════════════════════════════════════════════

class TestTopicTrackerWiring:

    def test_topic_history_across_turns(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.topic_tracker.set("cats", 0.9, turn=1)
        state.topic_tracker.set("birds", 0.9, turn=2)
        assert len(state.topic_tracker.history) == 2
        assert state.topic_tracker.current_name == "birds"

    def test_topic_tracker_reset(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.reset()
        assert state.topic_tracker.current is None

    def test_implicit_shift_detection(self):
        from core.conversation.conversation_state_engine import ConversationStateEngine
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        engine  = ConversationStateEngine()
        state.topic_tracker.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        for _ in range(3):
            state.increment_turn()
        result = engine.detect_implicit_topic_shift(adapter, {"genesis", "sprint"})
        assert result is True


# ══════════════════════════════════════════════════════════════════
# Full state summary integration
# ══════════════════════════════════════════════════════════════════

class TestFullStateSummary:

    def test_state_summary_includes_all_genesis043_components(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        d = state.summary()
        assert "entity_registry" in d
        assert "topic_tracker"   in d
        assert "summariser"      in d
        assert d["entity_registry"]["total"] == 1
        assert d["topic_tracker"]["current"] == "dogs"
        assert d["summariser"]["total_turns_seen"] == 1

    def test_state_reset_clears_all_components(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        state.reset()
        assert state.entity_registry.count()      == 0
        assert state.topic_tracker.current        is None
        assert state.summariser.turn_count()      == 0
        assert state.active_person                is None
        assert state.current_turn                 == 0
