"""
Genesis-043 Sprint-004 — ConversationSummariser tests.
"""

import pytest
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from core.conversation.conversation_summariser import (
    ConversationSummariser, TurnSummary, SummarySnapshot,
    DEFAULT_VERBATIM_TURNS, DEFAULT_COMPRESSED_MAX,
)
from core.conversation.conversation_state import ConversationState


# ══════════════════════════════════════════════════════════════════
# TurnSummary
# ══════════════════════════════════════════════════════════════════

class TestTurnSummary:

    def test_to_line_basic(self):
        ts = TurnSummary(turn_number=3, user_intent="Hello", jarvis_brief="Hi sir.")
        line = ts.to_line()
        assert "Turn 3" in line
        assert "Hello" in line
        assert "Hi sir." in line

    def test_to_line_with_topic(self):
        ts = TurnSummary(turn_number=3, user_intent="Hello", jarvis_brief="Hi.", topic="greeting")
        line = ts.to_line()
        assert "[greeting]" in line

    def test_to_line_no_response(self):
        ts = TurnSummary(turn_number=1, user_intent="Hello", jarvis_brief="")
        line = ts.to_line()
        assert "→" not in line


# ══════════════════════════════════════════════════════════════════
# SummarySnapshot
# ══════════════════════════════════════════════════════════════════

class TestSummarySnapshot:

    def _snap(self, verbatim=None, compressed=None, abstract=""):
        return SummarySnapshot(
            verbatim_turns   = verbatim or [],
            compressed_lines = compressed or [],
            session_abstract = abstract,
            total_turns      = 10,
            verbatim_count   = len(verbatim or []),
            compressed_count = len(compressed or []),
        )

    def test_is_empty_when_no_turns(self):
        assert self._snap().is_empty()

    def test_not_empty_with_verbatim(self):
        assert not self._snap(verbatim=[("hello", "hi")]).is_empty()

    def test_to_context_string_verbatim_only(self):
        snap = self._snap(verbatim=[("What time is it?", "It is 3pm.")])
        ctx = snap.to_context_string()
        assert "What time is it?" in ctx
        assert "It is 3pm." in ctx

    def test_to_context_string_with_abstract(self):
        snap = self._snap(
            verbatim=[("Hello", "Hi.")],
            abstract="Topics: greeting. Entities: Gianni."
        )
        ctx = snap.to_context_string()
        assert "Session context" in ctx
        assert "Topics: greeting" in ctx

    def test_to_context_string_with_compressed(self):
        snap = self._snap(
            verbatim=[("Hello", "Hi.")],
            compressed=["Turn 1 [dogs] — User: I have dogs → Jarvis: Got it."],
        )
        ctx = snap.to_context_string()
        assert "Earlier in this conversation" in ctx
        assert "Recent conversation" in ctx

    def test_to_context_string_empty(self):
        snap = self._snap()
        assert snap.to_context_string() == ""

    def test_to_context_string_abstract_only(self):
        snap = self._snap(abstract="Topics: dogs.")
        ctx = snap.to_context_string()
        assert "Session context" in ctx


# ══════════════════════════════════════════════════════════════════
# ConversationSummariser
# ══════════════════════════════════════════════════════════════════

class TestConversationSummariser:

    def _s(self, verbatim=3, compressed=6):
        return ConversationSummariser(verbatim_turns=verbatim, compressed_max=compressed)

    def test_empty_on_creation(self):
        s = self._s()
        assert s.turn_count() == 0
        assert s.stored_count() == 0

    def test_add_turn(self):
        s = self._s()
        s.add_turn("Hello", "Hi sir.", turn_number=1)
        assert s.turn_count() == 1
        assert s.stored_count() == 1

    def test_snapshot_empty(self):
        snap = self._s().snapshot()
        assert snap.is_empty()
        assert snap.total_turns == 0

    def test_snapshot_verbatim_only(self):
        s = self._s(verbatim=3)
        s.add_turn("Turn 1", "R1", turn_number=1)
        s.add_turn("Turn 2", "R2", turn_number=2)
        snap = s.snapshot()
        assert snap.verbatim_count   == 2
        assert snap.compressed_count == 0
        assert len(snap.verbatim_turns) == 2

    def test_snapshot_splits_at_verbatim_boundary(self):
        s = self._s(verbatim=3)
        for i in range(6):
            s.add_turn(f"User {i}", f"Jarvis {i}", turn_number=i)
        snap = s.snapshot()
        assert snap.verbatim_count   == 3
        assert snap.compressed_count == 3

    def test_verbatim_contains_last_n(self):
        s = self._s(verbatim=2)
        s.add_turn("First", "R1", turn_number=1)
        s.add_turn("Second", "R2", turn_number=2)
        s.add_turn("Third", "R3", turn_number=3)
        snap = s.snapshot()
        # Last 2 verbatim
        verbatim_users = [u for u, _ in snap.verbatim_turns]
        assert "Second" in verbatim_users
        assert "Third"  in verbatim_users
        assert "First"  not in verbatim_users

    def test_compressed_contains_earlier_turns(self):
        s = self._s(verbatim=2)
        s.add_turn("First", "R1", turn_number=1)
        s.add_turn("Second", "R2", turn_number=2)
        s.add_turn("Third", "R3", turn_number=3)
        snap = s.snapshot()
        assert len(snap.compressed_lines) == 1
        assert "First" in snap.compressed_lines[0]

    def test_compressed_line_format(self):
        s = self._s(verbatim=1)
        s.add_turn("What time is it?", "It is 3pm.", topic="time", turn_number=1)
        s.add_turn("Tell me a joke", "Why did...", turn_number=2)
        snap = s.snapshot()
        assert len(snap.compressed_lines) == 1
        line = snap.compressed_lines[0]
        assert "Turn 1" in line
        assert "[time]" in line
        assert "What time is it?" in line

    def test_total_cap_drops_oldest(self):
        s = self._s(verbatim=2, compressed=3)
        # max_stored = 5
        for i in range(8):
            s.add_turn(f"User {i}", f"Jarvis {i}", turn_number=i)
        assert s.stored_count() == 5   # capped
        assert s.turn_count()   == 8   # all counted

    def test_set_session_abstract(self):
        s = self._s()
        s.set_session_abstract("Topics: dogs. Entities: Rex.")
        snap = s.snapshot()
        assert snap.session_abstract == "Topics: dogs. Entities: Rex."

    def test_to_context_string(self):
        s = self._s(verbatim=2)
        s.add_turn("Hello", "Hi.", turn_number=1)
        s.add_turn("Tell me about dogs", "Dogs are great.", turn_number=2)
        s.add_turn("What about Rex?", "Rex is your dog.", turn_number=3)
        ctx = s.to_context_string()
        assert "Tell me about dogs" in ctx or "What about Rex?" in ctx

    def test_reset_clears_all(self):
        s = self._s()
        s.add_turn("Hello", "Hi.", turn_number=1)
        s.set_session_abstract("Some abstract.")
        s.reset()
        assert s.turn_count()    == 0
        assert s.stored_count()  == 0
        snap = s.snapshot()
        assert snap.session_abstract == ""

    def test_summary_dict(self):
        s = self._s()
        s.add_turn("Hello", "Hi.", turn_number=1)
        d = s.summary()
        assert "total_turns_seen" in d
        assert "verbatim_count"   in d
        assert "compressed_count" in d
        assert d["total_turns_seen"] == 1

    def test_build_abstract_from_state(self):
        state = ConversationState()
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.entity_registry.mention("Rex", turn=0)
        state.entity_registry.mention("Rex", turn=1)
        s = state.summariser
        abstract = s.build_abstract_from_state(state)
        assert "dogs" in abstract.lower() or "Rex" in abstract


# ══════════════════════════════════════════════════════════════════
# ConversationSummariser on ConversationState
# ══════════════════════════════════════════════════════════════════

class TestSummariserOnConversationState:

    def test_summariser_exists(self):
        state = ConversationState()
        assert hasattr(state, "summariser")
        assert isinstance(state.summariser, ConversationSummariser)

    def test_summariser_reset_on_state_reset(self):
        state = ConversationState()
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        state.reset()
        assert state.summariser.turn_count() == 0

    def test_summariser_in_summary(self):
        state = ConversationState()
        state.summariser.add_turn("Hello", "Hi.", turn_number=1)
        d = state.summary()
        assert "summariser" in d
        assert d["summariser"]["total_turns_seen"] == 1

    def test_full_pipeline(self):
        """End-to-end: add turns, build abstract from state, get context string."""
        state = ConversationState()

        # Add some context
        state.topic_tracker.set("dogs", 0.9, turn=0)
        state.entity_registry.mention("Rex", turn=0)
        state.entity_registry.mention("Tom", turn=1)

        # Add turns to summariser
        for i in range(8):
            state.summariser.add_turn(
                f"User message {i}",
                f"Jarvis response {i}",
                topic="dogs",
                turn_number=i,
            )

        # Build abstract
        state.summariser.build_abstract_from_state(state)

        # Get context string
        ctx = state.summariser.to_context_string()
        assert len(ctx) > 0

        # Check structure
        snap = state.summariser.snapshot()
        assert snap.verbatim_count   == DEFAULT_VERBATIM_TURNS
        assert snap.compressed_count == 3   # 8 - 5
        assert snap.session_abstract != ""
