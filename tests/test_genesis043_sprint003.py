"""
Genesis-043 Sprint-003 — TopicTracker tests.
"""

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.topic_tracker import (
    TopicTracker, TopicRecord,
    EXPLICIT_TOPIC_CONFIDENCE, IMPLICIT_TOPIC_CONFIDENCE,
    MIN_TOPIC_CONFIDENCE, ENTITY_OVERLAP_THRESHOLD,
)
from core.conversation.conversation_state import ConversationState
from core.conversation.conversation_state_engine import ConversationStateEngine
from core.conversation.session_context_adapter import SessionContextAdapter


# ══════════════════════════════════════════════════════════════════
# TopicRecord
# ══════════════════════════════════════════════════════════════════

class TestTopicRecord:

    def _make(self, name="dogs", entities=None):
        eset = frozenset(entities) if entities is not None else frozenset({"rex", "tom"})
        return TopicRecord(
            name=name, display=name.title(),
            confidence=0.9, turn=0, explicit=True,
            entity_set=eset,
        )

    def test_is_confident(self):
        r = self._make()
        assert r.is_confident

    def test_not_confident_below_threshold(self):
        r = TopicRecord(name="x", display="X", confidence=0.1, turn=0)
        assert not r.is_confident

    def test_overlap_identical(self):
        r = self._make(entities={"rex", "tom"})
        assert r.overlap_with({"rex", "tom"}) == pytest.approx(1.0)

    def test_overlap_disjoint(self):
        r = self._make(entities={"rex", "tom"})
        assert r.overlap_with({"leo", "max"}) == pytest.approx(0.0)

    def test_overlap_partial(self):
        r = self._make(entities={"rex", "tom"})
        assert 0.0 < r.overlap_with({"rex", "leo"}) < 1.0

    def test_overlap_empty_entities(self):
        r = self._make(entities=set())
        assert r.overlap_with({"rex"}) == pytest.approx(0.0)


# ══════════════════════════════════════════════════════════════════
# TopicTracker
# ══════════════════════════════════════════════════════════════════

class TestTopicTracker:

    def _tracker(self): return TopicTracker()

    def test_current_none_by_default(self):
        assert self._tracker().current is None

    def test_set_topic(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        assert t.current is not None
        assert t.current.name == "dogs"

    def test_set_normalises_to_lowercase(self):
        t = self._tracker()
        t.set("Dogs", confidence=0.9, turn=0)
        assert t.current.name == "dogs"

    def test_set_preserves_display(self):
        t = self._tracker()
        t.set("Dogs", confidence=0.9, turn=0)
        assert t.current.display == "Dogs"

    def test_history_empty_on_first_topic(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        assert t.history == []

    def test_history_grows_on_topic_change(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("cats", confidence=0.9, turn=1)
        assert len(t.history) == 1
        assert t.history[0].name == "dogs"

    def test_same_topic_does_not_push_history(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("dogs", confidence=0.95, turn=1)
        assert len(t.history) == 0

    def test_confidence_updated_on_same_topic(self):
        t = self._tracker()
        t.set("dogs", confidence=0.7, turn=0)
        t.set("dogs", confidence=0.95, turn=1)
        assert t.current_confidence == pytest.approx(0.95)

    def test_current_name(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        assert t.current_name == "dogs"

    def test_history_names(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("cats", confidence=0.9, turn=1)
        t.set("birds", confidence=0.9, turn=2)
        assert t.history_names == ["dogs", "cats"]

    def test_previous(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("cats", confidence=0.9, turn=1)
        assert t.previous().name == "dogs"

    def test_count(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("cats", confidence=0.9, turn=1)
        assert t.count() == 2

    def test_reset(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        t.set("cats", confidence=0.9, turn=1)
        t.reset()
        assert t.current is None
        assert t.history == []
        assert t.count() == 0

    def test_summary_returns_dict(self):
        t = self._tracker()
        t.set("dogs", confidence=0.9, turn=0)
        d = t.summary()
        assert "current"    in d
        assert "confidence" in d
        assert "history"    in d
        assert "total"      in d
        assert d["current"] == "dogs"

    def test_explicit_flag(self):
        t = self._tracker()
        t.set("dogs", confidence=EXPLICIT_TOPIC_CONFIDENCE, turn=0, explicit=True)
        assert t.current.explicit is True

    def test_implicit_flag(self):
        t = self._tracker()
        t.set("dogs", confidence=IMPLICIT_TOPIC_CONFIDENCE, turn=0, explicit=False)
        assert t.current.explicit is False


# ══════════════════════════════════════════════════════════════════
# TopicTracker — shift detection
# ══════════════════════════════════════════════════════════════════

class TestTopicTrackerShiftDetection:

    def test_no_shift_when_no_current_topic(self):
        t = TopicTracker()
        assert not t.detect_shift({"rex"}, current_turn=1)

    def test_no_shift_same_entities(self):
        t = TopicTracker()
        t.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        assert not t.detect_shift({"rex", "tom"}, current_turn=3)

    def test_shift_detected_disjoint_entities(self):
        t = TopicTracker()
        t.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        assert t.detect_shift({"genesis", "sprint"}, current_turn=3)

    def test_no_shift_on_same_turn(self):
        t = TopicTracker()
        t.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        # current_turn - topic.turn < 2 → no shift
        assert not t.detect_shift({"genesis"}, current_turn=1)

    def test_no_shift_when_no_entities(self):
        t = TopicTracker()
        t.set("dogs", 0.9, turn=0, entity_set={"rex"})
        assert not t.detect_shift(set(), current_turn=3)


# ══════════════════════════════════════════════════════════════════
# TopicTracker on ConversationState
# ══════════════════════════════════════════════════════════════════

class TestTopicTrackerOnConversationState:

    def test_topic_tracker_exists(self):
        state = ConversationState()
        assert hasattr(state, "topic_tracker")
        assert isinstance(state.topic_tracker, TopicTracker)

    def test_topic_tracker_reset_on_state_reset(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.reset()
        assert state.topic_tracker.current is None

    def test_topic_tracker_in_summary(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        d = state.summary()
        assert "topic_tracker" in d
        assert d["topic_tracker"]["current"] == "dogs"


# ══════════════════════════════════════════════════════════════════
# ConversationStateEngine.update_topic
# ══════════════════════════════════════════════════════════════════

class TestConversationStateEngineTopicUpdate:

    def _setup(self):
        state   = ConversationState()
        adapter = SessionContextAdapter(state)
        engine  = ConversationStateEngine()
        return state, adapter, engine

    def test_update_topic_sets_tracker(self):
        state, adapter, engine = self._setup()
        engine.update_topic("dogs", adapter, confidence=0.9, explicit=True)
        assert state.topic_tracker.current is not None
        assert state.topic_tracker.current.name == "dogs"

    def test_update_topic_explicit_flag(self):
        state, adapter, engine = self._setup()
        engine.update_topic("dogs", adapter, confidence=EXPLICIT_TOPIC_CONFIDENCE, explicit=True)
        assert state.topic_tracker.current.explicit is True

    def test_update_topic_implicit_flag(self):
        state, adapter, engine = self._setup()
        engine.update_topic("dogs", adapter, confidence=IMPLICIT_TOPIC_CONFIDENCE, explicit=False)
        assert state.topic_tracker.current.explicit is False

    def test_update_topic_history_grows(self):
        state, adapter, engine = self._setup()
        engine.update_topic("dogs", adapter, confidence=0.9, explicit=True)
        engine.update_topic("cats", adapter, confidence=0.9, explicit=True)
        assert len(state.topic_tracker.history) == 1
        assert state.topic_tracker.history[0].name == "dogs"

    def test_update_topic_empty_name_ignored(self):
        state, adapter, engine = self._setup()
        engine.update_topic("", adapter, confidence=0.9)
        assert state.topic_tracker.current is None

    def test_apply_focus_change_updates_topic_tracker(self):
        from core.conversation.conversation_state_engine import FocusChange
        state, adapter, engine = self._setup()
        change = FocusChange(detected=True, entity="dogs", is_group=True, confidence=0.92)
        engine.apply_focus_change(change, adapter)
        assert state.topic_tracker.current is not None
        assert state.topic_tracker.current.name == "dogs"
        assert state.topic_tracker.current.explicit is True

    def test_detect_implicit_shift(self):
        state, adapter, engine = self._setup()
        # Set topic at turn 0 with entity set
        state.topic_tracker.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        # At turn 3, completely different entities
        state.increment_turn(); state.increment_turn(); state.increment_turn()
        result = engine.detect_implicit_topic_shift(adapter, {"genesis", "sprint"})
        assert result is True

    def test_no_implicit_shift_same_entities(self):
        state, adapter, engine = self._setup()
        state.topic_tracker.set("dogs", 0.9, turn=0, entity_set={"rex", "tom"})
        state.increment_turn(); state.increment_turn(); state.increment_turn()
        result = engine.detect_implicit_topic_shift(adapter, {"rex", "tom"})
        assert result is False
