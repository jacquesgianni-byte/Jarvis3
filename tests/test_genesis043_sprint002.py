"""
Genesis-043 Sprint-002 — EntityRegistry tests.
"""

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.entity_registry import EntityRegistry, EntityRecord
from core.conversation.conversation_state import ConversationState


# ══════════════════════════════════════════════════════════════════
# EntityRecord
# ══════════════════════════════════════════════════════════════════

class TestEntityRecord:

    def _make(self, turn=0):
        return EntityRecord(
            name="rex", display_name="Rex",
            first_seen_turn=turn, last_mentioned_turn=turn
        )

    def test_effective_salience_at_creation(self):
        e = self._make(turn=0)
        assert e.effective_salience(0) == pytest.approx(1.0)

    def test_effective_salience_decays(self):
        e = self._make(turn=0)
        assert e.effective_salience(5) < 1.0

    def test_effective_salience_zero_at_decay_turns(self):
        from core.conversation.entity_registry import _DECAY_TURNS
        e = self._make(turn=0)
        assert e.effective_salience(_DECAY_TURNS) == 0.0

    def test_is_active_fresh(self):
        e = self._make(turn=0)
        assert e.is_active(0)

    def test_is_not_active_when_stale(self):
        from core.conversation.entity_registry import _DECAY_TURNS
        e = self._make(turn=0)
        assert not e.is_active(_DECAY_TURNS + 5)

    def test_mention_increments_count(self):
        e = self._make(turn=0)
        e.mention(turn=1)
        assert e.mention_count == 2

    def test_mention_resets_decay_clock(self):
        e = self._make(turn=0)
        e.mention(turn=5)
        assert e.last_mentioned_turn == 5

    def test_mention_boosts_salience(self):
        e = self._make(turn=0)
        original = e.salience
        e.mention(turn=1)
        assert e.salience >= original

    def test_salience_capped_at_one(self):
        e = self._make(turn=0)
        for i in range(20):
            e.mention(turn=i)
        assert e.salience <= 1.0


# ══════════════════════════════════════════════════════════════════
# EntityRegistry
# ══════════════════════════════════════════════════════════════════

class TestEntityRegistry:

    def _reg(self):
        return EntityRegistry()

    def test_mention_creates_record(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert reg.get("Rex") is not None

    def test_mention_case_insensitive_key(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert reg.get("rex") is not None
        assert reg.get("REX") is not None

    def test_mention_preserves_display_name(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert reg.get("rex").display_name == "Rex"

    def test_mention_twice_increments_count(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Rex", turn=1)
        assert reg.get("rex").mention_count == 2

    def test_mention_updates_last_mentioned_turn(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Rex", turn=5)
        assert reg.get("rex").last_mentioned_turn == 5

    def test_get_missing_returns_none(self):
        reg = self._reg()
        assert reg.get("NonExistent") is None

    def test_count(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        assert reg.count() == 2

    def test_most_salient_single(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert reg.most_salient(0) == "Rex"

    def test_most_salient_picks_highest(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        # Mention Rex again to boost salience
        reg.mention("Rex", turn=1)
        result = reg.most_salient(2)
        assert result == "Rex"

    def test_most_salient_none_when_empty(self):
        assert self._reg().most_salient(0) is None

    def test_most_salient_none_when_all_stale(self):
        from core.conversation.entity_registry import _DECAY_TURNS
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert reg.most_salient(_DECAY_TURNS + 5) is None

    def test_most_salient_excluding(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        reg.mention("Rex", turn=1)
        # Rex has higher salience but is excluded
        result = reg.most_salient_excluding(2, "rex")
        assert result == "Tom"

    def test_recent_returns_names(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=1)
        reg.mention("Leo", turn=2)
        recent = reg.recent(2, current_turn=3)
        assert len(recent) == 2
        assert "Leo" in recent

    def test_recent_ordered_by_recency(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=1)
        reg.mention("Leo", turn=2)
        recent = reg.recent(3, current_turn=3)
        assert recent[0] == "Leo"   # most recent first

    def test_active_returns_fresh_only(self):
        from core.conversation.entity_registry import _DECAY_TURNS
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        current = _DECAY_TURNS + 5
        assert len(reg.active(current)) == 0

    def test_active_count(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        assert len(reg.active(1)) == 2

    def test_all_names_includes_stale(self):
        from core.conversation.entity_registry import _DECAY_TURNS
        reg = self._reg()
        reg.mention("Rex", turn=0)
        assert "Rex" in reg.all_names()
        # Even after stale
        assert "Rex" in reg.all_names()

    def test_resolve_pronoun_singular(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        result = reg.resolve_pronoun("he", current_turn=1, is_plural=False)
        assert result == "Rex"

    def test_resolve_pronoun_returns_none_when_empty(self):
        reg = self._reg()
        assert reg.resolve_pronoun("he", current_turn=0) is None

    def test_resolve_pronoun_plural_returns_most_recent(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("dogs", turn=1)
        result = reg.resolve_pronoun("they", current_turn=2, is_plural=True)
        assert result == "dogs"

    def test_reset_clears_all(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        reg.mention("Tom", turn=0)
        reg.reset()
        assert reg.count() == 0

    def test_summary_returns_dict(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        d = reg.summary(0)
        assert "total" in d
        assert "active" in d
        assert "entities" in d
        assert d["total"] == 1

    def test_summary_entity_fields(self):
        reg = self._reg()
        reg.mention("Rex", turn=0)
        entity = reg.summary(0)["entities"][0]
        assert "name"     in entity
        assert "salience" in entity
        assert "mentions" in entity
        assert "last_turn" in entity

    def test_empty_name_raises(self):
        reg = self._reg()
        with pytest.raises(ValueError):
            reg.mention("", turn=0)

    def test_whitespace_name_raises(self):
        reg = self._reg()
        with pytest.raises(ValueError):
            reg.mention("   ", turn=0)


# ══════════════════════════════════════════════════════════════════
# EntityRegistry on ConversationState
# ══════════════════════════════════════════════════════════════════

class TestEntityRegistryOnConversationState:

    def test_entity_registry_exists_on_state(self):
        state = ConversationState()
        assert hasattr(state, "entity_registry")
        assert isinstance(state.entity_registry, EntityRegistry)

    def test_entity_registry_mention_via_state(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        assert state.entity_registry.get("Rex") is not None

    def test_entity_registry_reset_on_state_reset(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.reset()
        assert state.entity_registry.count() == 0

    def test_entity_registry_in_summary(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        d = state.summary()
        assert "entity_registry" in d
        assert d["entity_registry"]["total"] == 1

    def test_entity_registry_tracks_multiple_entities(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.entity_registry.mention("Tom", turn=1)
        state.entity_registry.mention("Leo", turn=2)
        assert state.entity_registry.count() == 3

    def test_most_salient_after_re_mention(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        state.entity_registry.mention("Tom", turn=1)
        state.entity_registry.mention("Rex", turn=2)
        assert state.entity_registry.most_salient(3) == "Rex"

    def test_pronoun_resolution_via_state(self):
        state = ConversationState()
        state.entity_registry.mention("Rex", turn=0)
        result = state.entity_registry.resolve_pronoun("he", current_turn=1)
        assert result == "Rex"
