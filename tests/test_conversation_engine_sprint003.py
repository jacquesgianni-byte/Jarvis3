"""
Genesis-022 Sprint-003 — Reference Resolver Tests
Completely self-contained. No dependency on other test files.

Coverage:
  ReferenceType:
    - all types exist, labels correct, unique values

  ResolutionResult:
    - immutable, fields, str, no_resolution() factory
    - resolved=True / resolved=False variants

  ReferenceResolver.has_reference():
    - detects all pronoun categories
    - empty/whitespace/clean input

  ReferenceResolver.detect_references():
    - returns all matched pronouns
    - deduplication, ordering

  ReferenceResolver.resolve() — successful resolutions:
    - "it" → current_it
    - "this" / "that" → current_it
    - "him" / "her" / "he" / "she" → current_person
    - "them" / "they" → current_person or last_entity
    - "the project" → current_project
    - "the file" → last_entity
    - "the worker" → last_entity
    - "the last one" → last_entity
    - case-insensitive matching
    - preserves surrounding text
    - repeated resolution calls deterministic

  ReferenceResolver.resolve() — no resolution:
    - empty input
    - whitespace only
    - no reference in input
    - reference detected but no context available
    - confidence below policy threshold

  Boundary testing:
    - threshold exactly at policy boundary
    - multiple references (first resolved)
    - punctuation around pronouns
    - mixed casing
    - very long input
    - reference at start / end of sentence

  Policy integration:
    - policy.resolution_threshold gates resolution
    - custom threshold changes behaviour
    - resolver never hard-codes thresholds

  State read-only guarantee:
    - resolve() never modifies state

  Backwards compatibility
"""

import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.conversation.conversation_resolver import (
    ReferenceType, ResolutionResult, ReferenceResolver,
)
from core.conversation.conversation_state import ConversationState, ReferenceContext
from core.conversation.conversation_policy import ConversationPolicy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_resolver() -> ReferenceResolver:
    return ReferenceResolver()


def make_policy(**kwargs) -> ConversationPolicy:
    return ConversationPolicy(**kwargs)


def make_state() -> ConversationState:
    return ConversationState()


def state_with(
    it=None, person=None, project=None, task=None, entity=None
) -> ConversationState:
    s = ConversationState()
    kwargs = {}
    if it:      kwargs["current_it"]      = it
    if person:  kwargs["current_person"]  = person
    if project: kwargs["current_project"] = project
    if task:    kwargs["current_task"]    = task
    if entity:  kwargs["last_entity"]     = entity
    if kwargs:
        s.update_reference(**kwargs)
    return s


DEFAULT_POLICY = make_policy()


# ===========================================================================
# 1. REFERENCE TYPE
# ===========================================================================

class TestReferenceType:

    def test_all_types_exist(self):
        for name in ["OBJECT", "PERSON", "FILE", "PROJECT", "WORKER", "TOPIC", "UNKNOWN"]:
            assert hasattr(ReferenceType, name)

    def test_values_unique(self):
        values = [r.value for r in ReferenceType]
        assert len(values) == len(set(values))

    def test_labels_human_readable(self):
        assert ReferenceType.OBJECT.label()  == "Object"
        assert ReferenceType.PERSON.label()  == "Person"
        assert ReferenceType.FILE.label()    == "File"
        assert ReferenceType.PROJECT.label() == "Project"
        assert ReferenceType.WORKER.label()  == "Worker"
        assert ReferenceType.TOPIC.label()   == "Topic"
        assert ReferenceType.UNKNOWN.label() == "Unknown"


# ===========================================================================
# 2. RESOLUTION RESULT
# ===========================================================================

class TestResolutionResult:

    def test_is_frozen(self):
        r = ResolutionResult.no_resolution("Hello.")
        with pytest.raises((AttributeError, TypeError, FrozenInstanceError)):
            r.resolved = True

    def test_no_resolution_factory(self):
        r = ResolutionResult.no_resolution("Hello.")
        assert not r.resolved
        assert r.original_input == "Hello."
        assert r.resolved_input == "Hello."
        assert r.confidence == 0.0

    def test_no_resolution_preserves_original(self):
        r = ResolutionResult.no_resolution("Fix it.")
        assert r.original_input == "Fix it."
        assert r.resolved_input == "Fix it."

    def test_no_resolution_custom_reason(self):
        r = ResolutionResult.no_resolution("Hello.", "custom reason")
        assert r.reason == "custom reason"

    def test_no_resolution_default_reason(self):
        r = ResolutionResult.no_resolution("Hello.")
        assert r.reason  # non-empty

    def test_resolved_result_str(self):
        r = ResolutionResult(
            original_input="Close it.",
            resolved_input="Close Visual Studio.",
            resolved=True,
            confidence=0.80,
            pronoun="it",
            replacement="Visual Studio",
            reference_type=ReferenceType.OBJECT,
            reason="resolved",
        )
        assert "it" in str(r)
        assert "Visual Studio" in str(r)

    def test_unresolved_result_str(self):
        r = ResolutionResult.no_resolution("Hello.")
        assert "unresolved" in str(r).lower()

    def test_resolved_true_fields(self):
        r = ResolutionResult(
            original_input="Ask him.",
            resolved_input="Ask Claude.",
            resolved=True,
            confidence=0.95,
            pronoun="him",
            replacement="Claude",
            reference_type=ReferenceType.PERSON,
            reason="Resolved him → Claude",
        )
        assert r.resolved
        assert r.pronoun == "him"
        assert r.replacement == "Claude"
        assert r.reference_type == ReferenceType.PERSON


# ===========================================================================
# 3. HAS_REFERENCE
# ===========================================================================

class TestHasReference:

    def setup_method(self):
        self.r = make_resolver()

    def test_it(self):
        assert self.r.has_reference("Close it.")

    def test_this(self):
        assert self.r.has_reference("Explain this.")

    def test_that(self):
        assert self.r.has_reference("Summarise that.")

    def test_him(self):
        assert self.r.has_reference("Ask him.")

    def test_her(self):
        assert self.r.has_reference("Tell her.")

    def test_he(self):
        assert self.r.has_reference("What did he say?")

    def test_she(self):
        assert self.r.has_reference("What did she say?")

    def test_them(self):
        assert self.r.has_reference("Ask them.")

    def test_the_project(self):
        assert self.r.has_reference("Open the project.")

    def test_the_file(self):
        assert self.r.has_reference("Explain the file.")

    def test_the_worker(self):
        assert self.r.has_reference("Run the worker.")

    def test_the_last_one(self):
        assert self.r.has_reference("Open the last one.")

    def test_no_reference_clean_sentence(self):
        assert not self.r.has_reference("Open Visual Studio.")

    def test_no_reference_empty(self):
        assert not self.r.has_reference("")

    def test_no_reference_whitespace(self):
        assert not self.r.has_reference("   ")

    def test_no_reference_none_string(self):
        assert not self.r.has_reference("")

    def test_case_insensitive(self):
        assert self.r.has_reference("Close IT.")
        assert self.r.has_reference("Ask HIM.")


# ===========================================================================
# 4. DETECT_REFERENCES
# ===========================================================================

class TestDetectReferences:

    def setup_method(self):
        self.r = make_resolver()

    def test_detects_single_pronoun(self):
        refs = self.r.detect_references("Close it.")
        assert any("it" in r.lower() for r in refs)

    def test_detects_multiple_pronouns(self):
        refs = self.r.detect_references("Ask him and close it.")
        assert len(refs) >= 2

    def test_empty_returns_empty(self):
        assert self.r.detect_references("") == []

    def test_whitespace_returns_empty(self):
        assert self.r.detect_references("   ") == []

    def test_no_reference_returns_empty(self):
        assert self.r.detect_references("Open Visual Studio.") == []

    def test_detects_person_pronoun(self):
        refs = self.r.detect_references("What did he say?")
        assert any("he" in r.lower() for r in refs)


# ===========================================================================
# 5. RESOLVE — successful person references
# ===========================================================================

class TestResolvePersonReferences:

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_him_resolves_to_person(self):
        s = state_with(person="Claude")
        result = self.r.resolve("Ask him to review it.", s, self.p)
        assert result.resolved
        assert result.replacement == "Claude"
        assert "Claude" in result.resolved_input
        assert result.reference_type == ReferenceType.PERSON

    def test_her_resolves_to_person(self):
        s = state_with(person="Sarah")
        result = self.r.resolve("Tell her about the plan.", s, self.p)
        assert result.resolved
        assert result.replacement == "Sarah"

    def test_he_resolves_to_person(self):
        s = state_with(person="Claude")
        result = self.r.resolve("What did he say?", s, self.p)
        assert result.resolved
        assert "Claude" in result.resolved_input

    def test_she_resolves_to_person(self):
        s = state_with(person="Alice")
        result = self.r.resolve("What did she build?", s, self.p)
        assert result.resolved
        assert "Alice" in result.resolved_input

    def test_person_confidence_is_high(self):
        s = state_with(person="Claude")
        result = self.r.resolve("Ask him.", s, self.p)
        assert result.confidence == 0.95

    def test_original_input_preserved(self):
        s = state_with(person="Claude")
        result = self.r.resolve("Ask him to fix it.", s, self.p)
        assert result.original_input == "Ask him to fix it."

    def test_pronoun_recorded(self):
        s = state_with(person="Claude")
        result = self.r.resolve("Ask him.", s, self.p)
        assert result.pronoun.lower() == "him"


# ===========================================================================
# 6. RESOLVE — successful object references
# ===========================================================================

class TestResolveObjectReferences:

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_it_resolves_to_current_it(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Close it.", s, self.p)
        assert result.resolved
        assert "Visual Studio" in result.resolved_input
        assert result.reference_type == ReferenceType.OBJECT

    def test_this_resolves_to_current_it(self):
        s = state_with(it="the README")
        result = self.r.resolve("Explain this.", s, self.p)
        assert result.resolved
        assert "the README" in result.resolved_input

    def test_that_resolves_to_current_it(self):
        s = state_with(it="Worker Architecture")
        result = self.r.resolve("Summarise that.", s, self.p)
        assert result.resolved
        assert "Worker Architecture" in result.resolved_input

    def test_it_falls_back_to_task(self):
        s = state_with(task="Sprint-003")
        result = self.r.resolve("Continue it.", s, self.p)
        assert result.resolved
        assert "Sprint-003" in result.resolved_input

    def test_it_falls_back_to_project(self):
        s = state_with(project="Jarvis OS")
        result = self.r.resolve("Open it.", s, self.p)
        assert result.resolved
        assert "Jarvis OS" in result.resolved_input

    def test_it_falls_back_to_entity(self):
        s = state_with(entity="the config file")
        result = self.r.resolve("Edit it.", s, self.p)
        assert result.resolved
        assert "the config file" in result.resolved_input

    def test_object_confidence(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Close it.", s, self.p)
        assert result.confidence == 0.80


# ===========================================================================
# 7. RESOLVE — named references
# ===========================================================================

class TestResolveNamedReferences:

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_the_project(self):
        s = state_with(project="Jarvis OS")
        result = self.r.resolve("Open the project.", s, self.p)
        assert result.resolved
        assert "Jarvis OS" in result.resolved_input
        assert result.reference_type == ReferenceType.PROJECT

    def test_this_project(self):
        s = state_with(project="Genesis-022")
        result = self.r.resolve("Continue this project.", s, self.p)
        assert result.resolved
        assert "Genesis-022" in result.resolved_input

    def test_the_file(self):
        s = state_with(entity="README.md")
        result = self.r.resolve("Explain the file.", s, self.p)
        assert result.resolved
        assert "README.md" in result.resolved_input
        assert result.reference_type == ReferenceType.FILE

    def test_the_worker(self):
        s = state_with(entity="EngineeringWorker")
        result = self.r.resolve("Run the worker.", s, self.p)
        assert result.resolved
        assert "EngineeringWorker" in result.resolved_input
        assert result.reference_type == ReferenceType.WORKER

    def test_the_last_one(self):
        # "the last one" confidence is 0.65 — below default threshold 0.75
        # Use a permissive policy to allow resolution
        p = ConversationPolicy(resolution_threshold=0.60)
        s = state_with(entity="Sprint-003 plan")
        result = self.r.resolve("Open the last one.", s, p)
        assert result.resolved
        assert "Sprint-003 plan" in result.resolved_input

    def test_named_ref_confidence(self):
        s = state_with(project="Jarvis OS")
        result = self.r.resolve("Open the project.", s, self.p)
        assert result.confidence == 0.90


# ===========================================================================
# 8. RESOLVE — no resolution cases
# ===========================================================================

class TestResolveNoResolution:

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_empty_input(self):
        s = make_state()
        result = self.r.resolve("", s, self.p)
        assert not result.resolved
        assert result.resolved_input == ""

    def test_whitespace_input(self):
        s = make_state()
        result = self.r.resolve("   ", s, self.p)
        assert not result.resolved

    def test_no_reference_in_input(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Open Visual Studio.", s, self.p)
        assert not result.resolved

    def test_reference_but_no_context(self):
        s = make_state()  # empty context
        result = self.r.resolve("Close it.", s, self.p)
        assert not result.resolved
        assert result.original_input == "Close it."
        assert result.resolved_input == "Close it."

    def test_person_reference_no_person_context(self):
        s = make_state()
        result = self.r.resolve("Ask him.", s, self.p)
        assert not result.resolved

    def test_project_reference_no_project_context(self):
        s = make_state()
        result = self.r.resolve("Open the project.", s, self.p)
        assert not result.resolved

    def test_no_resolution_preserves_original(self):
        s = make_state()
        result = self.r.resolve("Fix it.", s, self.p)
        assert result.resolved_input == "Fix it."

    def test_no_resolution_has_reason(self):
        s = make_state()
        result = self.r.resolve("Fix it.", s, self.p)
        assert result.reason  # non-empty explanation


# ===========================================================================
# 9. POLICY INTEGRATION — threshold gating
# ===========================================================================

class TestResolverPolicyIntegration:

    def test_below_threshold_no_resolution(self):
        # "the last one" has confidence 0.65 — set threshold above that
        p = ConversationPolicy(resolution_threshold=0.70)
        s = state_with(entity="Sprint-003")
        r = make_resolver()
        result = r.resolve("Open the last one.", s, p)
        assert not result.resolved
        assert result.confidence == 0.65

    def test_at_threshold_resolves(self):
        # "it" has confidence 0.80 — set threshold exactly at 0.80
        p = ConversationPolicy(resolution_threshold=0.80)
        s = state_with(it="Visual Studio")
        r = make_resolver()
        result = r.resolve("Close it.", s, p)
        assert result.resolved

    def test_above_threshold_resolves(self):
        p = ConversationPolicy(resolution_threshold=0.75)
        s = state_with(it="Visual Studio")
        r = make_resolver()
        result = r.resolve("Close it.", s, p)
        assert result.resolved

    def test_strict_threshold_blocks_low_confidence(self):
        # Block everything below 0.95
        p = ConversationPolicy(
            resolution_threshold=0.95,
            ambiguity_threshold=0.70,
            clarification_threshold=0.50,
        )
        s = state_with(it="Visual Studio", project="Jarvis")
        r = make_resolver()
        # "it" is 0.80 — below 0.95 threshold
        result = r.resolve("Close it.", s, p)
        assert not result.resolved

    def test_resolver_never_hard_codes_threshold(self):
        """Changing policy threshold changes resolver behaviour."""
        s = state_with(entity="old plan")
        r = make_resolver()
        # "the last one" → confidence 0.65
        p_strict = ConversationPolicy(resolution_threshold=0.70)
        p_loose  = ConversationPolicy(resolution_threshold=0.60)
        assert not r.resolve("Use the last one.", s, p_strict).resolved
        assert r.resolve("Use the last one.", s, p_loose).resolved

    def test_confidence_returned_even_when_not_resolved(self):
        p = ConversationPolicy(resolution_threshold=0.90)
        s = state_with(it="Visual Studio")
        r = make_resolver()
        result = r.resolve("Close it.", s, p)
        # "it" confidence is 0.80 — below 0.90, not resolved but confidence returned
        assert not result.resolved
        assert result.confidence == 0.80

    def test_reason_mentions_threshold_when_blocked(self):
        p = ConversationPolicy(resolution_threshold=0.90)
        s = state_with(it="Visual Studio")
        r = make_resolver()
        result = r.resolve("Close it.", s, p)
        assert "threshold" in result.reason.lower() or "0.9" in result.reason


# ===========================================================================
# 10. BOUNDARY AND EDGE CASES
# ===========================================================================

class TestResolverBoundaries:

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_case_insensitive_it(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Close IT.", s, self.p)
        assert result.resolved

    def test_case_insensitive_him(self):
        s = state_with(person="Claude")
        result = self.r.resolve("Ask HIM.", s, self.p)
        assert result.resolved

    def test_punctuation_around_pronoun(self):
        s = state_with(it="the plan")
        result = self.r.resolve("Review it, please.", s, self.p)
        assert result.resolved
        assert "the plan" in result.resolved_input

    def test_pronoun_at_start(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("It should be closed.", s, self.p)
        assert result.resolved

    def test_pronoun_at_end(self):
        s = state_with(it="the config")
        result = self.r.resolve("Please edit it", s, self.p)
        assert result.resolved

    def test_only_first_pronoun_replaced(self):
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Close it and then reopen it.", s, self.p)
        # Only first occurrence replaced
        assert result.resolved
        assert result.resolved_input.count("it") == 1

    def test_very_long_input(self):
        s = state_with(it="Visual Studio")
        long_input = "Please " + "really " * 50 + "close it."
        result = self.r.resolve(long_input, s, self.p)
        assert result.resolved

    def test_multiple_reference_types_person_wins(self):
        """Person pronouns have highest priority."""
        s = state_with(person="Claude", it="the plan")
        result = self.r.resolve("Ask him about it.", s, self.p)
        # "him" detected first (higher priority)
        assert result.resolved
        assert result.reference_type == ReferenceType.PERSON
        assert result.replacement == "Claude"

    def test_deterministic_repeated_calls(self):
        s = state_with(it="Visual Studio")
        r1 = self.r.resolve("Close it.", s, self.p)
        r2 = self.r.resolve("Close it.", s, self.p)
        assert r1.resolved_input == r2.resolved_input
        assert r1.confidence == r2.confidence

    def test_state_not_modified_by_resolve(self):
        s = state_with(it="Visual Studio")
        original_it = s.references.current_it
        self.r.resolve("Close it.", s, self.p)
        assert s.references.current_it == original_it  # unchanged


# ===========================================================================
# 11. SUCCESS CRITERIA FROM SPEC
# ===========================================================================

class TestSpecSuccessCriteria:
    """Tests directly from the spec examples."""

    def setup_method(self):
        self.r = make_resolver()
        self.p = DEFAULT_POLICY

    def test_open_then_close_it(self):
        """
        Open Visual Studio.
        → Close it. → Close Visual Studio.
        """
        s = state_with(it="Visual Studio")
        result = self.r.resolve("Close it.", s, self.p)
        assert result.resolved
        assert result.resolved_input == "Close Visual Studio."

    def test_review_then_summarise_that(self):
        """
        Review the Worker Architecture.
        → Summarise that. → Summarise the Worker Architecture.
        """
        s = state_with(it="the Worker Architecture")
        result = self.r.resolve("Summarise that.", s, self.p)
        assert result.resolved
        assert "the Worker Architecture" in result.resolved_input

    def test_ask_claude_then_what_did_he_say(self):
        """
        Ask Claude.
        → What did he say? → What did Claude say?
        """
        s = state_with(person="Claude")
        result = self.r.resolve("What did he say?", s, self.p)
        assert result.resolved
        assert "Claude" in result.resolved_input

    def test_open_readme_then_explain_this_file(self):
        """
        Open the README.
        → Explain this file. → Explain the README.
        """
        s = state_with(entity="the README")
        result = self.r.resolve("Explain this file.", s, self.p)
        assert result.resolved
        assert "the README" in result.resolved_input


# ===========================================================================
# 12. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_existing_context_resolver_unchanged(self):
        """Genesis-020 ContextResolver is separate and unaffected."""
        from core.conversation.context_resolver import ContextResolver
        from core.conversation.session_context import SessionContext
        s = SessionContext()
        s.set_person("Claude")
        resolver = ContextResolver(s)
        assert resolver is not None

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_conversation_state_unchanged(self):
        from core.conversation.conversation_state import ConversationState
        s = ConversationState()
        s.update_reference(current_person="Claude")
        assert s.references.current_person == "Claude"

    def test_resolver_importable(self):
        from core.conversation.conversation_resolver import (
            ReferenceResolver, ResolutionResult, ReferenceType,
        )
        assert ReferenceResolver is not None

    def test_sprint001_models_unchanged(self):
        from core.conversation.conversation_models import DecisionType, Decision
        d = Decision(
            decision_type=DecisionType.INVOKE_WORKER,
            resolved_input="Plan it.",
        )
        assert d.decision_type == DecisionType.INVOKE_WORKER