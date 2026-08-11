"""
Genesis-043 Sprint-001 — ConversationState evolution tests.
Tests new Genesis-043 fields without breaking Genesis-022 behaviour.
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.conversation_state import (
    ConversationState, ConversationMode, ContextSlot,
    ReferenceContext, DECAY_TURNS, MIN_CONFIDENCE,
)
from core.conversation.session_context_adapter import SessionContextAdapter


# ══════════════════════════════════════════════════════════════════
# ContextSlot (decay model)
# ══════════════════════════════════════════════════════════════════

class TestContextSlot:

    def test_effective_confidence_at_creation(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=0.9)
        assert slot.effective_confidence(0) == 0.9

    def test_effective_confidence_decays(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=1.0)
        assert slot.effective_confidence(5) < 1.0
        assert slot.effective_confidence(5) == pytest.approx(0.5)

    def test_effective_confidence_reaches_zero(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=1.0)
        assert slot.effective_confidence(DECAY_TURNS) == 0.0

    def test_effective_confidence_never_negative(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=1.0)
        assert slot.effective_confidence(DECAY_TURNS * 2) == 0.0

    def test_is_usable_fresh(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=1.0)
        assert slot.is_usable(0)

    def test_is_not_usable_when_stale(self):
        slot = ContextSlot(value="Rex", turn=0, confidence=1.0)
        assert not slot.is_usable(DECAY_TURNS + 5)

    def test_str_returns_value(self):
        slot = ContextSlot(value="Genesis-043")
        assert str(slot) == "Genesis-043"


# ══════════════════════════════════════════════════════════════════
# ConversationState — Genesis-022 fields (regression)
# ══════════════════════════════════════════════════════════════════

class TestConversationStateGenesis022:

    def _make(self): return ConversationState()

    def test_default_mode_is_normal(self):
        assert self._make().mode == ConversationMode.NORMAL

    def test_set_mode(self):
        s = self._make()
        s.set_mode(ConversationMode.AWAITING_ANSWER)
        assert s.mode == ConversationMode.AWAITING_ANSWER

    def test_turn_count_starts_zero(self):
        assert self._make().turn_count == 0

    def test_no_pending_by_default(self):
        assert not self._make().has_pending()

    def test_no_current_topic_by_default(self):
        assert self._make().current_topic is None

    def test_topic_history_empty(self):
        assert self._make().topic_history == []

    def test_summary_returns_dict(self):
        s = self._make()
        d = s.summary()
        assert isinstance(d, dict)
        assert "mode" in d
        assert "turn_count" in d

    def test_reset_clears_mode(self):
        s = self._make()
        s.set_mode(ConversationMode.CONFIRMING)
        s.reset()
        assert s.mode == ConversationMode.NORMAL

    def test_metadata(self):
        s = self._make()
        s.set_metadata("key", "value")
        assert s.get_metadata("key") == "value"
        assert s.has_metadata("key")


# ══════════════════════════════════════════════════════════════════
# ConversationState — Genesis-043 new fields
# ══════════════════════════════════════════════════════════════════

class TestConversationStateGenesis043:

    def _make(self): return ConversationState()

    def test_ctx_turn_starts_zero(self):
        assert self._make().current_turn == 0

    def test_increment_turn(self):
        s = self._make()
        s.increment_turn()
        s.increment_turn()
        assert s.current_turn == 2

    def test_active_person_none_by_default(self):
        assert self._make().active_person is None

    def test_set_person(self):
        s = self._make()
        s.set_person("Rex", confidence=0.9)
        assert s.active_person is not None
        assert s.active_person.value == "Rex"

    def test_set_person_records_turn(self):
        s = self._make()
        s.increment_turn()
        s.set_person("Rex")
        assert s.active_person.turn == 1

    def test_set_active_topic(self):
        s = self._make()
        s.set_active_topic("dogs", confidence=0.9)
        assert s.active_topic is not None
        assert s.active_topic.value == "dogs"

    def test_set_project(self):
        s = self._make()
        s.set_project("Jarvis-OS")
        assert s.active_project.value == "Jarvis-OS"

    def test_set_task(self):
        s = self._make()
        s.set_task("Genesis-043")
        assert s.active_task.value == "Genesis-043"

    def test_set_milestone(self):
        s = self._make()
        s.set_milestone("Sprint-001")
        assert s.active_milestone.value == "Sprint-001"

    def test_is_usable_fresh_slot(self):
        s = self._make()
        s.set_person("Rex")
        assert s.is_usable(s.active_person)

    def test_is_usable_stale_slot(self):
        s = self._make()
        s.set_person("Rex")
        for _ in range(DECAY_TURNS + 5):
            s.increment_turn()
        assert not s.is_usable(s.active_person)

    def test_fresh_returns_slot_if_usable(self):
        s = self._make()
        s.set_person("Rex")
        assert s.fresh(s.active_person) is not None

    def test_fresh_returns_none_if_stale(self):
        s = self._make()
        s.set_person("Rex")
        for _ in range(DECAY_TURNS + 5):
            s.increment_turn()
        assert s.fresh(s.active_person) is None

    def test_effective_confidence(self):
        s = self._make()
        s.set_person("Rex", confidence=1.0)
        assert s.effective_confidence(s.active_person) == pytest.approx(1.0)

    def test_last_intent_none_by_default(self):
        assert self._make().last_intent is None

    def test_set_last_turn(self):
        s = self._make()
        s.set_last_turn("greeting", "Hello sir.", "general")
        assert s.last_intent   == "greeting"
        assert s.last_response == "Hello sir."
        assert s.last_topic    == "general"

    def test_recent_entities_empty_by_default(self):
        assert self._make().recent_entities == []

    def test_add_recent_entity(self):
        s = self._make()
        s.add_recent_entity("Rex")
        s.add_recent_entity("Tom")
        assert "Rex" in s.recent_entities
        assert "Tom" in s.recent_entities

    def test_recent_entities_no_duplicates(self):
        s = self._make()
        s.add_recent_entity("Rex")
        s.add_recent_entity("Rex")
        assert s.recent_entities.count("Rex") == 1

    def test_recent_entities_capped(self):
        s = self._make()
        for i in range(10):
            s.add_recent_entity(f"Entity{i}")
        assert len(s.recent_entities) <= ConversationState.DEFAULT_MAX_RECENT_ENTS

    def test_dialogue_act_default(self):
        assert self._make().dialogue_act == "inform"

    def test_set_dialogue_act(self):
        s = self._make()
        s.set_dialogue_act("clarify")
        assert s.dialogue_act == "clarify"

    def test_session_summary_empty_by_default(self):
        assert self._make().session_summary == ""

    def test_set_session_summary(self):
        s = self._make()
        s.set_session_summary("Session was about dogs.")
        assert s.session_summary == "Session was about dogs."

    def test_reset_clears_genesis043_fields(self):
        s = self._make()
        s.set_person("Rex")
        s.set_active_topic("dogs")
        s.set_last_turn("memory", "Rex is a dog.", "dogs")
        s.add_recent_entity("Rex")
        s.set_dialogue_act("clarify")
        s.set_session_summary("About dogs.")
        s.reset()
        assert s.active_person    is None
        assert s.active_topic     is None
        assert s.last_intent      is None
        assert s.last_response    is None
        assert s.recent_entities  == []
        assert s.dialogue_act     == "inform"
        assert s.session_summary  == ""
        assert s.current_turn     == 0

    def test_summary_includes_genesis043_fields(self):
        s = self._make()
        s.set_person("Rex")
        d = s.summary()
        assert "active_person" in d
        assert "dialogue_act"  in d
        assert "ctx_turn"      in d
        assert d["active_person"]["value"] == "Rex"


# ══════════════════════════════════════════════════════════════════
# SessionContextAdapter
# ══════════════════════════════════════════════════════════════════

class TestSessionContextAdapter:

    def _make(self):
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        return state, adapter

    def test_adapter_reads_active_person(self):
        state, adapter = self._make()
        state.set_person("Rex")
        assert adapter.active_person is not None
        assert adapter.active_person.value == "Rex"

    def test_adapter_writes_active_person(self):
        state, adapter = self._make()
        adapter.set_person("Tom", confidence=0.9)
        assert state.active_person.value == "Tom"

    def test_adapter_reads_active_topic(self):
        state, adapter = self._make()
        state.set_active_topic("dogs")
        assert adapter.active_topic.value == "dogs"

    def test_adapter_writes_active_topic(self):
        state, adapter = self._make()
        adapter.set_topic("cats")
        assert state.active_topic.value == "cats"

    def test_adapter_reads_active_project(self):
        state, adapter = self._make()
        state.set_project("Jarvis-OS")
        assert adapter.active_project.value == "Jarvis-OS"

    def test_adapter_writes_active_project(self):
        state, adapter = self._make()
        adapter.set_project("JRI")
        assert state.active_project.value == "JRI"

    def test_adapter_reads_active_task(self):
        state, adapter = self._make()
        state.set_task("Genesis-043")
        assert adapter.active_task.value == "Genesis-043"

    def test_adapter_writes_active_task(self):
        state, adapter = self._make()
        adapter.set_task("Sprint-001")
        assert state.active_task.value == "Sprint-001"

    def test_adapter_reads_milestone(self):
        state, adapter = self._make()
        state.set_milestone("Sprint-001")
        assert adapter.active_milestone.value == "Sprint-001"

    def test_adapter_current_turn(self):
        state, adapter = self._make()
        state.increment_turn()
        assert adapter.current_turn == 1

    def test_adapter_increment_turn(self):
        state, adapter = self._make()
        adapter.increment_turn()
        assert state.current_turn == 1

    def test_adapter_is_usable(self):
        state, adapter = self._make()
        state.set_person("Rex")
        assert adapter.is_usable(adapter.active_person)

    def test_adapter_fresh(self):
        state, adapter = self._make()
        state.set_person("Rex")
        assert adapter.fresh(adapter.active_person) is not None

    def test_adapter_last_intent(self):
        state, adapter = self._make()
        adapter.set_last_turn("greeting", "Hello.", "general")
        assert adapter.last_intent   == "greeting"
        assert adapter.last_response == "Hello."
        assert adapter.last_topic    == "general"

    def test_adapter_last_intent_read(self):
        state, adapter = self._make()
        state.set_last_turn("memory", "Rex is a dog.", "dogs")
        assert adapter.last_intent   == "memory"
        assert adapter.last_response == "Rex is a dog."

    def test_adapter_reset_clears_slots(self):
        state, adapter = self._make()
        adapter.set_person("Rex")
        adapter.set_topic("dogs")
        adapter.reset()
        assert state.active_person is None
        assert state.active_topic  is None
        assert state.current_turn  == 0

    def test_adapter_summary_returns_dict(self):
        state, adapter = self._make()
        d = adapter.summary()
        assert isinstance(d, dict)
        assert "person" in d
        assert "topic"  in d

    def test_state_and_adapter_share_same_data(self):
        """Writing via adapter is visible on state and vice versa."""
        state, adapter = self._make()
        adapter.set_person("Rex")
        assert state.active_person.value == "Rex"
        state.set_active_topic("dogs")
        assert adapter.active_topic.value == "dogs"

    def test_no_business_logic_in_adapter(self):
        """Adapter must be thin — no methods not on SessionContext interface."""
        state, adapter = self._make()
        # These are the only methods that should exist
        expected = {
            "active_person", "active_topic", "active_project",
            "active_task", "active_milestone", "current_turn",
            "increment_turn", "is_usable", "fresh", "effective_confidence",
            "set_person", "set_topic", "set_project", "set_task",
            "set_milestone", "last_intent", "last_response", "last_topic",
            "set_last_turn", "reset", "summary",
        }
        public = {m for m in dir(adapter) if not m.startswith("_")}
        unexpected = public - expected
        assert not unexpected, f"Unexpected methods on adapter: {unexpected}"
