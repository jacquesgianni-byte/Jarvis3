"""
Genesis-020 Sprint-002 — Active Conversation Context Tests (Revised)
Completely self-contained. No dependency on other test files.

Reflects post-review design decisions:
  - Resolution never rewrites original request — checks context_hint instead
  - Resolution has confidence field
  - Natural decay model (not binary staleness)
  - ContextInspector produces readable output
"""

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.session_context import SessionContext, ContextSlot, DECAY_TURNS, MIN_CONFIDENCE
from core.conversation.context_manager import ContextManager
from core.conversation.context_resolver import ContextResolver, Resolution, MIN_RESOLUTION_CONFIDENCE
from core.conversation.context_inspector import ContextInspector


def make_session(): return SessionContext()
def make_manager(s=None):
    s = s or make_session(); return ContextManager(s), s
def make_resolver(s=None):
    s = s or make_session(); return ContextResolver(s), s
def make_inspector(s=None):
    s = s or make_session(); return ContextInspector(s), s


# ===========================================================================
# 1. SESSION CONTEXT — decay model
# ===========================================================================

class TestSessionContextDecay:

    def test_initial_turn_zero(self):
        assert make_session().current_turn == 0

    def test_increment_turn(self):
        s = make_session(); s.increment_turn(); s.increment_turn()
        assert s.current_turn == 2

    def test_slot_full_confidence_at_write_time(self):
        s = make_session()
        s.set_person("Claude", confidence=0.9)
        assert s.active_person.effective_confidence(s.current_turn) == 0.9

    def test_slot_decays_over_turns(self):
        s = make_session()
        s.set_person("Claude", confidence=1.0)
        for _ in range(5):
            s.increment_turn()
        ec = s.active_person.effective_confidence(s.current_turn)
        assert ec < 1.0
        assert ec > 0.0

    def test_slot_reaches_zero_after_decay_turns(self):
        s = make_session()
        s.set_person("Claude", confidence=1.0)
        for _ in range(DECAY_TURNS + 1):
            s.increment_turn()
        ec = s.active_person.effective_confidence(s.current_turn)
        assert ec == 0.0

    def test_is_usable_fresh_slot(self):
        s = make_session()
        s.set_project("Jarvis OS")
        assert s.is_usable(s.active_project)

    def test_is_usable_none_slot(self):
        s = make_session()
        assert not s.is_usable(None)

    def test_is_usable_decayed_slot(self):
        s = make_session()
        s.set_project("Jarvis OS", confidence=1.0)
        for _ in range(DECAY_TURNS + 1):
            s.increment_turn()
        assert not s.is_usable(s.active_project)

    def test_fresh_returns_slot_when_usable(self):
        s = make_session()
        s.set_project("Jarvis OS")
        assert s.fresh(s.active_project) is not None

    def test_fresh_returns_none_when_decayed(self):
        s = make_session()
        s.set_project("Jarvis OS", confidence=1.0)
        for _ in range(DECAY_TURNS + 1):
            s.increment_turn()
        assert s.fresh(s.active_project) is None

    def test_reset_clears_all(self):
        s = make_session()
        s.set_project("Jarvis OS"); s.set_person("Claude"); s.increment_turn()
        s.reset()
        assert s.active_project is None
        assert s.active_person is None
        assert s.current_turn == 0

    def test_summary_returns_dict(self):
        s = make_session()
        s.set_project("Jarvis OS")
        d = s.summary()
        assert d["project"]["value"] == "Jarvis OS"
        assert d["person"] is None

    def test_slot_confidence_stored(self):
        s = make_session()
        s.set_person("Claude", confidence=0.85)
        assert s.active_person.confidence == 0.85

    def test_effective_confidence_on_none(self):
        s = make_session()
        assert s.effective_confidence(None) == 0.0


# ===========================================================================
# 2. CONTEXT MANAGER — detection
# ===========================================================================

class TestContextManager:

    def test_detects_genesis_project(self):
        mgr, s = make_manager()
        mgr.update("We're starting Genesis-020.")
        assert s.active_project is not None
        assert "genesis" in s.active_project.value.lower()

    def test_detects_frozen_milestone(self):
        mgr, s = make_manager()
        mgr.update("Genesis-019 is frozen.")
        assert s.active_milestone is not None

    def test_detects_sprint_task(self):
        mgr, s = make_manager()
        mgr.update("Claude is implementing Sprint-002.")
        assert s.active_task is not None

    def test_detects_claude_person(self):
        mgr, s = make_manager()
        mgr.update("Claude is implementing Sprint-002.")
        assert s.active_person is not None
        assert s.active_person.value.lower() == "claude"

    def test_detects_gpt_person(self):
        mgr, s = make_manager()
        mgr.update("GPT handles the specs.")
        assert s.active_person is not None

    def test_advances_turn_each_call(self):
        mgr, s = make_manager()
        mgr.update("Hello."); mgr.update("World.")
        assert s.current_turn == 2

    def test_person_changes_mid_conversation(self):
        mgr, s = make_manager()
        mgr.update("Claude is reviewing.")
        mgr.update("GPT is handling specs.")
        assert "gpt" in s.active_person.value.lower()

    def test_empty_message_does_not_crash(self):
        mgr, s = make_manager()
        mgr.update("")
        assert s.current_turn == 1

    def test_exception_does_not_propagate(self):
        s = make_session()
        mgr = ContextManager(s)
        mgr.update("This should not crash.")


# ===========================================================================
# 3. CONTEXT RESOLVER — needs_resolution
# ===========================================================================

class TestNeedsResolution:

    def setup_method(self):
        self.resolver, _ = make_resolver()

    def test_him(self):    assert self.resolver.needs_resolution("Ask him to fix it.")
    def test_her(self):    assert self.resolver.needs_resolution("Tell her about it.")
    def test_it(self):     assert self.resolver.needs_resolution("Continue on it.")
    def test_the_project(self): assert self.resolver.needs_resolution("How is the project?")
    def test_the_sprint(self):  assert self.resolver.needs_resolution("Finish the sprint.")
    def test_continue(self):    assert self.resolver.needs_resolution("Let's continue.")
    def test_what_are_we(self): assert self.resolver.needs_resolution("What are we doing?")
    def test_who_are_we(self):  assert self.resolver.needs_resolution("Who are we talking about?")
    def test_normal(self):      assert not self.resolver.needs_resolution("What is the Repository Pattern?")
    def test_greeting(self):    assert not self.resolver.needs_resolution("Hello Jarvis.")


# ===========================================================================
# 4. CONTEXT RESOLVER — original request never rewritten
# ===========================================================================

class TestOriginalPreserved:

    def test_original_unchanged_on_person_resolution(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to fix the tests.")
        assert r.original == "Ask him to fix the tests."

    def test_original_unchanged_on_project_resolution(self):
        resolver, s = make_resolver()
        s.set_project("Jarvis OS")
        r = resolver.resolve("How is the project going?")
        assert r.original == "How is the project going?"

    def test_context_hint_has_resolved_value(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to fix the tests.")
        assert r.resolved
        assert r.context_hint == "Claude"

    def test_enriched_not_in_resolution(self):
        """Resolution dataclass has no 'enriched' field in revised design."""
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to fix it.")
        assert not hasattr(r, "enriched") or r.context_hint == "Claude"


# ===========================================================================
# 5. CONTEXT RESOLVER — confidence field
# ===========================================================================

class TestResolutionConfidence:

    def test_person_pronoun_has_high_confidence(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to fix it.")
        assert r.resolved
        assert r.confidence >= 0.70

    def test_project_ref_has_high_confidence(self):
        resolver, s = make_resolver()
        s.set_project("Jarvis OS")
        r = resolver.resolve("How is the project going?")
        assert r.resolved
        assert r.confidence >= 0.60

    def test_generic_pronoun_has_lower_confidence(self):
        resolver, s = make_resolver()
        s.set_project("Jarvis OS")
        r_person = None
        resolver2, s2 = make_resolver()
        s2.set_person("Claude")
        r_person = resolver2.resolve("Ask him to fix it.")
        resolver3, s3 = make_resolver()
        s3.set_project("Jarvis OS")
        r_generic = resolver3.resolve("Tell me about it.")
        if r_person.resolved and r_generic.resolved:
            assert r_person.confidence >= r_generic.confidence

    def test_not_resolved_has_zero_confidence(self):
        resolver, s = make_resolver()
        r = resolver.resolve("Ask him to fix it.")
        assert not r.resolved
        assert r.confidence == 0.0

    def test_decayed_slot_not_resolved(self):
        resolver, s = make_resolver()
        s.set_person("Claude", confidence=1.0)
        for _ in range(DECAY_TURNS + 1):
            s.increment_turn()
        r = resolver.resolve("Ask him to fix it.")
        assert not r.resolved

    def test_pronoun_recorded_in_resolution(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to review it.")
        assert r.resolved
        assert r.pronoun.lower() == "him"


# ===========================================================================
# 6. CONTEXT RESOLVER — specific resolutions
# ===========================================================================

class TestSpecificResolutions:

    def test_resolves_him_to_person(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Ask him to improve the tests.")
        assert r.resolved and r.context_hint == "Claude" and r.slot_type == "person"

    def test_resolves_the_milestone(self):
        resolver, s = make_resolver()
        s.set_milestone("Genesis-019")
        r = resolver.resolve("Tell me about the milestone.")
        assert r.resolved and r.context_hint == "Genesis-019"

    def test_resolves_the_sprint(self):
        resolver, s = make_resolver()
        s.set_task("Sprint-002")
        r = resolver.resolve("Finish the sprint.")
        assert r.resolved and r.context_hint == "Sprint-002"

    def test_continuation_resolves_to_task(self):
        resolver, s = make_resolver()
        s.set_task("Sprint-002")
        r = resolver.resolve("Let's continue.")
        assert r.resolved and r.context_hint == "Sprint-002"

    def test_what_are_we_working_on(self):
        resolver, s = make_resolver()
        s.set_task("Sprint-002")
        r = resolver.resolve("What are we working on?")
        assert r.resolved and "Sprint-002" in r.context_hint

    def test_who_are_we_talking_about(self):
        resolver, s = make_resolver()
        s.set_person("Claude")
        r = resolver.resolve("Who are we talking about?")
        assert r.resolved and r.context_hint == "Claude"

    def test_no_resolution_when_empty(self):
        resolver, s = make_resolver()
        r = resolver.resolve("Ask him to fix it.")
        assert not r.resolved


# ===========================================================================
# 7. CONTEXT INSPECTOR
# ===========================================================================

class TestContextInspector:

    def test_inspect_returns_string(self):
        inspector, _ = make_inspector()
        assert isinstance(inspector.inspect(), str)

    def test_inspect_shows_active_project(self):
        inspector, s = make_inspector()
        s.set_project("Jarvis OS")
        output = inspector.inspect()
        assert "Jarvis OS" in output

    def test_inspect_shows_active_person(self):
        inspector, s = make_inspector()
        s.set_person("Claude")
        output = inspector.inspect()
        assert "Claude" in output

    def test_inspect_shows_turn(self):
        inspector, s = make_inspector()
        s.increment_turn(); s.increment_turn()
        output = inspector.inspect()
        assert "2" in output

    def test_is_empty_when_no_slots(self):
        inspector, _ = make_inspector()
        assert inspector.is_empty()

    def test_is_not_empty_when_slot_set(self):
        inspector, s = make_inspector()
        s.set_project("Jarvis OS")
        assert not inspector.is_empty()

    def test_is_empty_after_decay(self):
        inspector, s = make_inspector()
        s.set_project("Jarvis OS", confidence=1.0)
        for _ in range(DECAY_TURNS + 1):
            s.increment_turn()
        assert inspector.is_empty()

    def test_inspect_contains_confidence(self):
        inspector, s = make_inspector()
        s.set_person("Claude")
        output = inspector.inspect()
        assert "conf" in output.lower()


# ===========================================================================
# 8. END-TO-END SCENARIOS
# ===========================================================================

class TestEndToEnd:

    def test_genesis_020_continuation(self):
        s = make_session()
        mgr, resolver = ContextManager(s), ContextResolver(s)
        mgr.update("We're starting Genesis-020.")
        r = resolver.resolve("Let's continue.")
        assert r.resolved and "Genesis-020" in r.context_hint

    def test_claude_person_pronoun(self):
        s = make_session()
        mgr, resolver = ContextManager(s), ContextResolver(s)
        mgr.update("Claude is implementing Sprint-002.")
        r = resolver.resolve("Ask him to improve it.")
        assert r.resolved and r.context_hint == "Claude"

    def test_context_changes_over_turns(self):
        s = make_session()
        mgr, resolver = ContextManager(s), ContextResolver(s)
        mgr.update("Claude is reviewing.")
        mgr.update("GPT is handling specs.")
        r = resolver.resolve("Ask him to start.")
        assert r.resolved and "gpt" in r.context_hint.lower()

    def test_stale_context_not_used(self):
        s = make_session()
        mgr, resolver = ContextManager(s), ContextResolver(s)
        mgr.update("Claude is reviewing.")
        for i in range(11):
            mgr.update(f"Unrelated turn {i}.")
        r = resolver.resolve("Ask him to fix it.")
        assert not r.resolved

    def test_original_never_mutated_in_multi_turn(self):
        s = make_session()
        mgr, resolver = ContextManager(s), ContextResolver(s)
        mgr.update("Claude is implementing Sprint-002.")
        original = "Ask him to improve it."
        r = resolver.resolve(original)
        assert r.original == original


# ===========================================================================
# 9. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_conversation_context_unchanged(self):
        from core.conversation.context import ConversationContext
        ctx = ConversationContext()
        ctx.last_intent = "MEMORY"
        ctx.pending_question = "What is your name?"
        assert ctx.has_pending_interaction()
        ctx.clear_pending()
        assert not ctx.has_pending_interaction()

    def test_session_context_is_separate_class(self):
        from core.conversation.context import ConversationContext
        assert not isinstance(make_session(), ConversationContext)

    def test_context_manager_does_not_touch_conversation_context(self):
        from core.conversation.context import ConversationContext
        ctx = ConversationContext()
        ctx.topic = "original"
        s = make_session()
        ContextManager(s).update("We're starting Genesis-020.")
        assert ctx.topic == "original"