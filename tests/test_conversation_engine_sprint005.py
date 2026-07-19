"""
Genesis-022 Sprint-005 — Recovery Handler & Conversation Pipeline Tests
Completely self-contained. No dependency on other test files.

Coverage:
  RecoveryAction:
    - all actions exist, labels, is_recovery property

  RecoveryResult:
    - immutable, fields, no_recovery() factory, str

  RecoveryHandler.is_recovery():
    - all pattern categories detected
    - normal input / empty input

  RecoveryHandler.check() — full reset:
    - "never mind", "start over", "forget it", "scratch that"
    - clears pending, topic, references
    - should_continue=False
    - state already clear

  RecoveryHandler.check() — pending cancel:
    - "cancel", "skip it", "not now"
    - pending cancelled → should_continue=False
    - no pending → ACKNOWLEDGED, continues

  RecoveryHandler.check() — topic revert:
    - "go back", "return to"
    - topic popped from history
    - no history → ACKNOWLEDGED

  RecoveryHandler.check() — soft recovery:
    - "actually,", "wait,"
    - ACKNOWLEDGED, continues, no state change

  ProcessingStep:
    - immutable, fields, str

  PipelineContext:
    - defaults, effective_input, append_step, stage_names, summary
    - current_input defaults to original

  ConversationPipeline:
    - stage ordering (Recovery → Resolution → Dialogue)
    - all stages run for normal input
    - stage skipping after terminal recovery
    - context enrichment (all results set)
    - processing trace populated
    - empty input
    - malformed input handling
    - full reset stops pipeline
    - resolution feeds dialogue
    - deterministic repeated runs

  Backwards compatibility
"""

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_recovery import (
    RecoveryAction, RecoveryResult, RecoveryHandler,
)
from core.conversation.conversation_pipeline import (
    ProcessingStep, PipelineContext, ConversationPipeline,
    RecoveryStage, ResolutionStage, DialogueStage,
)
from core.conversation.conversation_state import ConversationState
from core.conversation.conversation_policy import ConversationPolicy
from core.conversation.conversation_models import Slot, Topic
from core.conversation.conversation_dialogue import DialogueType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_handler() -> RecoveryHandler:
    return RecoveryHandler()


def make_state() -> ConversationState:
    return ConversationState()


def make_policy(**kwargs) -> ConversationPolicy:
    return ConversationPolicy(**kwargs)


def make_pipeline() -> ConversationPipeline:
    return ConversationPipeline()


def state_with_pending(name="colour", question="What colour?") -> ConversationState:
    s = ConversationState()
    s.set_pending(Slot(name=name, question=question))
    return s


def state_with_topic(name="planning") -> ConversationState:
    s = ConversationState()
    s.set_topic(Topic(name=name))
    return s


def state_with_topic_history() -> ConversationState:
    s = ConversationState()
    s.set_topic(Topic(name="first"))
    s.push_topic(Topic(name="second"))
    return s


DEFAULT_POLICY = make_policy()


# ===========================================================================
# 1. RECOVERY ACTION
# ===========================================================================

class TestRecoveryAction:

    def test_all_actions_exist(self):
        for name in ["NONE", "PENDING_CANCELLED", "TOPIC_REVERTED",
                     "STATE_RESET", "ACKNOWLEDGED"]:
            assert hasattr(RecoveryAction, name)

    def test_values_unique(self):
        values = [a.value for a in RecoveryAction]
        assert len(values) == len(set(values))

    def test_labels(self):
        assert RecoveryAction.NONE.label() == "None"
        assert RecoveryAction.PENDING_CANCELLED.label() == "Pending Cancelled"
        assert RecoveryAction.TOPIC_REVERTED.label() == "Topic Reverted"
        assert RecoveryAction.STATE_RESET.label() == "State Reset"
        assert RecoveryAction.ACKNOWLEDGED.label() == "Acknowledged"

    def test_is_recovery_none_false(self):
        assert not RecoveryAction.NONE.is_recovery

    def test_is_recovery_others_true(self):
        for a in [RecoveryAction.PENDING_CANCELLED, RecoveryAction.TOPIC_REVERTED,
                  RecoveryAction.STATE_RESET, RecoveryAction.ACKNOWLEDGED]:
            assert a.is_recovery


# ===========================================================================
# 2. RECOVERY RESULT
# ===========================================================================

class TestRecoveryResult:

    def test_is_frozen(self):
        r = RecoveryResult.no_recovery("Hello.")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.recovered = True

    def test_no_recovery_factory(self):
        r = RecoveryResult.no_recovery("Hello.")
        assert r.action == RecoveryAction.NONE
        assert not r.recovered
        assert r.should_continue
        assert r.original_input == "Hello."

    def test_str_recovered(self):
        r = RecoveryResult(
            action=RecoveryAction.STATE_RESET,
            original_input="never mind",
            recovered=True,
            pattern_matched="never mind",
        )
        assert "State Reset" in str(r)

    def test_str_not_recovered(self):
        r = RecoveryResult.no_recovery("Hi.")
        assert "no recovery" in str(r)

    def test_default_should_continue_true(self):
        r = RecoveryResult(
            action=RecoveryAction.ACKNOWLEDGED,
            original_input="actually,",
        )
        assert r.should_continue


# ===========================================================================
# 3. RECOVERY HANDLER — is_recovery pre-check
# ===========================================================================

class TestIsRecovery:

    def setup_method(self):
        self.h = make_handler()

    def test_never_mind(self):    assert self.h.is_recovery("never mind")
    def test_start_over(self):    assert self.h.is_recovery("start over")
    def test_forget_it(self):     assert self.h.is_recovery("forget it")
    def test_cancel(self):        assert self.h.is_recovery("cancel")
    def test_skip_it(self):       assert self.h.is_recovery("skip it")
    def test_go_back(self):       assert self.h.is_recovery("go back")
    def test_actually(self):      assert self.h.is_recovery("actually, do this")
    def test_wait(self):          assert self.h.is_recovery("wait, one moment")

    def test_normal_input_not_recovery(self):
        assert not self.h.is_recovery("Fix the login bug.")

    def test_empty_not_recovery(self):
        assert not self.h.is_recovery("")

    def test_whitespace_not_recovery(self):
        assert not self.h.is_recovery("   ")


# ===========================================================================
# 4. RECOVERY HANDLER — full reset
# ===========================================================================

class TestFullReset:

    def setup_method(self):
        self.h = make_handler()

    def test_never_mind_resets(self):
        s = state_with_pending()
        r = self.h.check("never mind", s)
        assert r.action == RecoveryAction.STATE_RESET
        assert r.recovered

    def test_never_mind_clears_pending(self):
        s = state_with_pending()
        self.h.check("never mind", s)
        assert not s.has_pending()

    def test_never_mind_clears_topic(self):
        s = state_with_topic()
        self.h.check("Never mind.", s)
        assert s.current_topic is None

    def test_never_mind_clears_references(self):
        s = make_state()
        s.update_reference(current_person="Claude")
        self.h.check("never mind", s)
        assert s.references.current_person is None

    def test_full_reset_stops_pipeline(self):
        s = state_with_pending()
        r = self.h.check("never mind", s)
        assert not r.should_continue

    def test_start_over_resets(self):
        s = state_with_topic()
        r = self.h.check("start over", s)
        assert r.action == RecoveryAction.STATE_RESET

    def test_forget_it_resets(self):
        r = self.h.check("forget it", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_forget_everything_resets(self):
        r = self.h.check("forget everything", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_scratch_that_resets(self):
        r = self.h.check("scratch that", state_with_topic())
        assert r.action == RecoveryAction.STATE_RESET

    def test_ignore_that_resets(self):
        r = self.h.check("ignore that", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_cancel_that_resets(self):
        r = self.h.check("cancel that", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_reset_on_clear_state(self):
        s = make_state()  # nothing to reset
        r = self.h.check("never mind", s)
        assert r.action == RecoveryAction.STATE_RESET
        assert "already clear" in r.reason

    def test_case_insensitive(self):
        r = self.h.check("NEVER MIND", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_with_punctuation(self):
        r = self.h.check("never mind!", state_with_pending())
        assert r.action == RecoveryAction.STATE_RESET

    def test_pattern_recorded(self):
        r = self.h.check("never mind", state_with_pending())
        assert "never mind" in r.pattern_matched.lower()

    def test_reset_mid_sentence_not_matched(self):
        """Full reset patterns are anchored — mid-sentence mentions don't reset."""
        s = state_with_pending()
        r = self.h.check("I would never mind helping you.", s)
        assert r.action != RecoveryAction.STATE_RESET
        assert s.has_pending()  # state untouched


# ===========================================================================
# 5. RECOVERY HANDLER — pending cancel
# ===========================================================================

class TestPendingCancel:

    def setup_method(self):
        self.h = make_handler()

    def test_cancel_cancels_pending(self):
        s = state_with_pending()
        r = self.h.check("cancel", s)
        assert r.action == RecoveryAction.PENDING_CANCELLED
        assert not s.has_pending()

    def test_cancel_stops_pipeline(self):
        s = state_with_pending()
        r = self.h.check("cancel", s)
        assert not r.should_continue

    def test_cancel_keeps_topic(self):
        s = state_with_pending()
        s.set_topic(Topic(name="planning"))
        self.h.check("cancel", s)
        assert s.current_topic is not None

    def test_skip_it_cancels(self):
        s = state_with_pending()
        r = self.h.check("skip it", s)
        assert r.action == RecoveryAction.PENDING_CANCELLED

    def test_not_now_cancels(self):
        s = state_with_pending()
        r = self.h.check("not now", s)
        assert r.action == RecoveryAction.PENDING_CANCELLED

    def test_no_thanks_cancels(self):
        s = state_with_pending()
        r = self.h.check("no thanks", s)
        assert r.action == RecoveryAction.PENDING_CANCELLED

    def test_cancel_with_no_pending_acknowledged(self):
        s = make_state()
        r = self.h.check("cancel", s)
        assert r.action == RecoveryAction.ACKNOWLEDGED
        assert r.should_continue

    def test_stop_cancels_pending(self):
        s = state_with_pending()
        r = self.h.check("stop", s)
        assert r.action == RecoveryAction.PENDING_CANCELLED


# ===========================================================================
# 6. RECOVERY HANDLER — topic revert
# ===========================================================================

class TestTopicRevert:

    def setup_method(self):
        self.h = make_handler()

    def test_go_back_reverts_topic(self):
        s = state_with_topic_history()
        r = self.h.check("go back", s)
        assert r.action == RecoveryAction.TOPIC_REVERTED
        assert s.current_topic.name == "first"

    def test_lets_go_back_reverts(self):
        s = state_with_topic_history()
        r = self.h.check("let's go back", s)
        assert r.action == RecoveryAction.TOPIC_REVERTED

    def test_return_to_reverts(self):
        s = state_with_topic_history()
        r = self.h.check("return to what we were discussing", s)
        assert r.action == RecoveryAction.TOPIC_REVERTED

    def test_revert_continues_pipeline(self):
        s = state_with_topic_history()
        r = self.h.check("go back", s)
        assert r.should_continue

    def test_revert_with_no_history_acknowledged(self):
        s = state_with_topic()  # topic but no history
        r = self.h.check("go back", s)
        assert r.action == RecoveryAction.ACKNOWLEDGED

    def test_revert_with_empty_state_acknowledged(self):
        s = make_state()
        r = self.h.check("go back", s)
        assert r.action == RecoveryAction.ACKNOWLEDGED

    def test_reason_names_reverted_topic(self):
        s = state_with_topic_history()
        r = self.h.check("go back", s)
        assert "first" in r.reason


# ===========================================================================
# 7. RECOVERY HANDLER — soft recovery
# ===========================================================================

class TestSoftRecovery:

    def setup_method(self):
        self.h = make_handler()

    def test_actually_acknowledged(self):
        r = self.h.check("actually, let's fix the bug", make_state())
        assert r.action == RecoveryAction.ACKNOWLEDGED
        assert r.recovered

    def test_actually_continues(self):
        r = self.h.check("actually, do this instead", make_state())
        assert r.should_continue

    def test_wait_acknowledged(self):
        r = self.h.check("wait, one second", make_state())
        assert r.action == RecoveryAction.ACKNOWLEDGED

    def test_hold_on_acknowledged(self):
        r = self.h.check("hold on, let me think", make_state())
        assert r.action == RecoveryAction.ACKNOWLEDGED

    def test_soft_recovery_no_state_change(self):
        s = state_with_pending()
        self.h.check("actually, use blue", s)
        assert s.has_pending()  # pending untouched

    def test_actually_without_comma_not_matched(self):
        """'actually' must be a leading marker — bare word mid-input not soft recovery."""
        r = self.h.check("That is actually correct.", make_state())
        assert r.action == RecoveryAction.NONE


# ===========================================================================
# 8. RECOVERY HANDLER — no recovery / edge cases
# ===========================================================================

class TestNoRecovery:

    def setup_method(self):
        self.h = make_handler()

    def test_normal_input(self):
        r = self.h.check("Fix the login bug.", make_state())
        assert r.action == RecoveryAction.NONE
        assert not r.recovered
        assert r.should_continue

    def test_empty_input(self):
        r = self.h.check("", make_state())
        assert r.action == RecoveryAction.NONE

    def test_whitespace_input(self):
        r = self.h.check("   ", make_state())
        assert r.action == RecoveryAction.NONE

    def test_repeated_recovery(self):
        """Recovery twice in a row is safe."""
        s = state_with_pending()
        r1 = self.h.check("never mind", s)
        r2 = self.h.check("never mind", s)
        assert r1.action == RecoveryAction.STATE_RESET
        assert r2.action == RecoveryAction.STATE_RESET
        assert "already clear" in r2.reason

    def test_question_not_recovery(self):
        r = self.h.check("What is the Repository Pattern?", make_state())
        assert r.action == RecoveryAction.NONE


# ===========================================================================
# 9. PROCESSING STEP
# ===========================================================================

class TestProcessingStep:

    def test_is_frozen(self):
        s = ProcessingStep(stage="Test", executed=True)
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            s.executed = False

    def test_fields(self):
        s = ProcessingStep(
            stage="RecoveryStage", executed=True,
            duration_ms=1.5, outcome="no recovery",
        )
        assert s.stage == "RecoveryStage"
        assert s.executed
        assert s.duration_ms == 1.5
        assert s.outcome == "no recovery"

    def test_str_executed(self):
        s = ProcessingStep(stage="Test", executed=True, outcome="done")
        assert "✓" in str(s)
        assert "Test" in str(s)

    def test_str_skipped(self):
        s = ProcessingStep(stage="Test", executed=False, outcome="skipped")
        assert "–" in str(s)

    def test_default_metadata_empty(self):
        assert ProcessingStep(stage="T", executed=True).metadata == {}


# ===========================================================================
# 10. PIPELINE CONTEXT
# ===========================================================================

class TestPipelineContext:

    def _ctx(self, raw="Hello.") -> PipelineContext:
        return PipelineContext(
            original_input=raw, state=make_state(), policy=DEFAULT_POLICY,
        )

    def test_current_input_defaults_to_original(self):
        ctx = self._ctx("Hello.")
        assert ctx.current_input == "Hello."

    def test_original_never_modified(self):
        ctx = self._ctx("Fix it.")
        ctx.current_input = "Fix the bug."
        assert ctx.original_input == "Fix it."

    def test_effective_input_falls_back_to_current(self):
        ctx = self._ctx("Hello.")
        assert ctx.effective_input() == "Hello."

    def test_effective_input_uses_resolution(self):
        from core.conversation.conversation_resolver import ResolutionResult, ReferenceType
        ctx = self._ctx("Close it.")
        ctx.resolution_result = ResolutionResult(
            original_input="Close it.",
            resolved_input="Close Visual Studio.",
            resolved=True,
            confidence=0.8,
            reference_type=ReferenceType.OBJECT,
        )
        assert ctx.effective_input() == "Close Visual Studio."

    def test_append_step(self):
        ctx = self._ctx()
        ctx.append_step(ProcessingStep(stage="A", executed=True))
        assert len(ctx.history) == 1

    def test_stage_names_only_executed(self):
        ctx = self._ctx()
        ctx.append_step(ProcessingStep(stage="A", executed=True))
        ctx.append_step(ProcessingStep(stage="B", executed=False))
        assert ctx.stage_names() == ["A"]

    def test_default_not_terminal(self):
        assert not self._ctx().is_terminal

    def test_summary_dict(self):
        ctx = self._ctx("Hello.")
        s = ctx.summary()
        assert isinstance(s, dict)
        assert s["original_input"] == "Hello."
        assert not s["is_terminal"]

    def test_total_duration_positive(self):
        assert self._ctx().total_duration_ms() >= 0


# ===========================================================================
# 11. CONVERSATION PIPELINE — stage ordering and execution
# ===========================================================================

class TestPipelineExecution:

    def setup_method(self):
        self.pipeline = make_pipeline()
        self.p = DEFAULT_POLICY

    def test_stage_count(self):
        assert self.pipeline.stage_count == 3

    def test_stage_names_in_order(self):
        assert self.pipeline.stage_names == [
            "RecoveryStage", "ResolutionStage", "DialogueStage",
        ]

    def test_all_stages_run_for_normal_input(self):
        s = state_with_topic()
        ctx = self.pipeline.run("Fix the login bug.", s, self.p)
        assert ctx.stage_names() == ["RecoveryStage", "ResolutionStage", "DialogueStage"]

    def test_history_has_all_stages(self):
        ctx = self.pipeline.run("Hello.", make_state(), self.p)
        assert len(ctx.history) == 3

    def test_recovery_result_set(self):
        ctx = self.pipeline.run("Hello.", make_state(), self.p)
        assert ctx.recovery_result is not None

    def test_resolution_result_set(self):
        ctx = self.pipeline.run("Hello.", state_with_topic(), self.p)
        assert ctx.resolution_result is not None

    def test_dialogue_result_set(self):
        ctx = self.pipeline.run("Hello.", state_with_topic(), self.p)
        assert ctx.dialogue_result is not None

    def test_steps_have_durations(self):
        ctx = self.pipeline.run("Hello.", make_state(), self.p)
        for step in ctx.history:
            if step.executed:
                assert step.duration_ms >= 0

    def test_steps_have_outcomes(self):
        ctx = self.pipeline.run("Hello.", make_state(), self.p)
        for step in ctx.history:
            assert step.outcome


# ===========================================================================
# 12. CONVERSATION PIPELINE — terminal recovery skips stages
# ===========================================================================

class TestPipelineTerminalRecovery:

    def setup_method(self):
        self.pipeline = make_pipeline()
        self.p = DEFAULT_POLICY

    def test_never_mind_marks_terminal(self):
        s = state_with_pending()
        ctx = self.pipeline.run("never mind", s, self.p)
        assert ctx.is_terminal

    def test_terminal_skips_resolution(self):
        s = state_with_pending()
        ctx = self.pipeline.run("never mind", s, self.p)
        resolution_step = next(st for st in ctx.history if st.stage == "ResolutionStage")
        assert not resolution_step.executed

    def test_terminal_skips_dialogue(self):
        s = state_with_pending()
        ctx = self.pipeline.run("never mind", s, self.p)
        dialogue_step = next(st for st in ctx.history if st.stage == "DialogueStage")
        assert not dialogue_step.executed

    def test_terminal_history_shows_skipped(self):
        s = state_with_pending()
        ctx = self.pipeline.run("never mind", s, self.p)
        skipped = [st for st in ctx.history if not st.executed]
        assert len(skipped) == 2

    def test_cancel_with_pending_is_terminal(self):
        s = state_with_pending()
        ctx = self.pipeline.run("cancel", s, self.p)
        assert ctx.is_terminal

    def test_state_actually_reset(self):
        s = state_with_pending()
        s.set_topic(Topic(name="planning"))
        self.pipeline.run("never mind", s, self.p)
        assert not s.has_pending()
        assert s.current_topic is None

    def test_soft_recovery_continues(self):
        s = state_with_topic()
        ctx = self.pipeline.run("actually, fix the bug", s, self.p)
        assert not ctx.is_terminal
        assert len(ctx.stage_names()) == 3


# ===========================================================================
# 13. CONVERSATION PIPELINE — resolution feeds dialogue
# ===========================================================================

class TestPipelineIntegration:

    def setup_method(self):
        self.pipeline = make_pipeline()
        self.p = DEFAULT_POLICY

    def test_resolution_updates_current_input(self):
        s = state_with_topic()
        s.update_reference(current_it="Visual Studio")
        ctx = self.pipeline.run("Close it.", s, self.p)
        assert ctx.current_input == "Close Visual Studio."

    def test_effective_input_is_resolved(self):
        s = state_with_topic()
        s.update_reference(current_it="Visual Studio")
        ctx = self.pipeline.run("Close it.", s, self.p)
        assert ctx.effective_input() == "Close Visual Studio."

    def test_original_preserved_after_resolution(self):
        s = state_with_topic()
        s.update_reference(current_it="Visual Studio")
        ctx = self.pipeline.run("Close it.", s, self.p)
        assert ctx.original_input == "Close it."

    def test_pending_answer_flows_through(self):
        s = state_with_pending("colour", "What colour?")
        ctx = self.pipeline.run("Blue.", s, self.p)
        assert ctx.dialogue_result is not None
        assert ctx.dialogue_result.dialogue_type == DialogueType.ANSWER_PENDING
        assert ctx.dialogue_result.slot_value == "Blue"

    def test_ack_flows_through(self):
        s = state_with_topic()
        ctx = self.pipeline.run("ok", s, self.p)
        assert ctx.dialogue_result.dialogue_type == DialogueType.ACKNOWLEDGEMENT

    def test_deterministic_repeated_runs(self):
        s1 = state_with_topic()
        s1.update_reference(current_it="the plan")
        s2 = state_with_topic()
        s2.update_reference(current_it="the plan")
        ctx1 = self.pipeline.run("Review it.", s1, self.p)
        ctx2 = self.pipeline.run("Review it.", s2, self.p)
        assert ctx1.effective_input() == ctx2.effective_input()
        assert ctx1.stage_names() == ctx2.stage_names()


# ===========================================================================
# 14. CONVERSATION PIPELINE — edge cases
# ===========================================================================

class TestPipelineEdgeCases:

    def setup_method(self):
        self.pipeline = make_pipeline()
        self.p = DEFAULT_POLICY

    def test_empty_input(self):
        ctx = self.pipeline.run("", make_state(), self.p)
        assert ctx.original_input == ""
        assert len(ctx.history) == 3  # all stages record themselves

    def test_whitespace_input(self):
        ctx = self.pipeline.run("   ", make_state(), self.p)
        assert not ctx.is_terminal

    def test_very_long_input(self):
        long = "Please " + "really " * 100 + "help me."
        ctx = self.pipeline.run(long, state_with_topic(), self.p)
        assert ctx.original_input == long

    def test_punctuation_only(self):
        ctx = self.pipeline.run("...", make_state(), self.p)
        assert ctx.dialogue_result is not None

    def test_summary_after_run(self):
        ctx = self.pipeline.run("Hello.", make_state(), self.p)
        s = ctx.summary()
        assert s["stages_run"] == ["RecoveryStage", "ResolutionStage", "DialogueStage"]
        assert s["total_ms"] >= 0


# ===========================================================================
# 15. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_sprint002_state_unchanged(self):
        s = ConversationState()
        s.update_reference(current_person="Claude")
        assert s.references.current_person == "Claude"

    def test_sprint003_resolver_unchanged(self):
        from core.conversation.conversation_resolver import ReferenceResolver
        s = ConversationState()
        s.update_reference(current_it="Visual Studio")
        r = ReferenceResolver()
        result = r.resolve("Close it.", s, ConversationPolicy())
        assert result.resolved

    def test_sprint004_dialogue_unchanged(self):
        from core.conversation.conversation_dialogue import DialogueManager
        m = DialogueManager()
        assert m.is_acknowledgement("ok")

    def test_recovery_importable(self):
        from core.conversation.conversation_recovery import (
            RecoveryHandler, RecoveryResult, RecoveryAction,
        )
        assert RecoveryHandler is not None

    def test_pipeline_importable(self):
        from core.conversation.conversation_pipeline import (
            ConversationPipeline, PipelineContext, ProcessingStep,
        )
        assert ConversationPipeline is not None

    def test_genesis_020_session_context_unchanged(self):
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_project("Jarvis OS")
        assert s.active_project.value == "Jarvis OS"