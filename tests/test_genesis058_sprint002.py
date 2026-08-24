"""
Genesis-058 Sprint-002 - InvestigationSelector tests.

Covers:
    - SelectionResult states (matched, ambiguous, no_match)
    - SelectionResult invariants (matched+ambiguous mutually exclusive)
    - SelectionResult.format_for_mission() - all three states
    - InvestigationSelector.select() - known match
    - InvestigationSelector.select() - unknown question (no match)
    - InvestigationSelector.select() - whole-word matching correctness
    - InvestigationSelector.select() - tie returns ambiguous, not a guess
    - InvestigationSelector.select() - empty registry returns no_match
    - InvestigationSelector.select() - unavailable sources excluded
    - InvestigationSelector with real registry + real project root
"""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import patch

from core.mission.investigation_registry import (
    InvestigationDescriptor,
    InvestigationRegistry,
)
from core.mission.investigation_selector import (
    InvestigationSelector,
    SelectionResult,
)

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")
FAKE_ROOT    = pathlib.Path(r"C:\\nonexistent\\path\\that\\does\\not\\exist")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_descriptor(name: str, keywords: tuple, sources=("project_state",)) -> InvestigationDescriptor:
    return InvestigationDescriptor(
        name              = name,
        display_name      = name.replace("_", " ").title(),
        description       = f"Test descriptor: {name}.",
        question_keywords = keywords,
        evidence_sources  = sources,
    )


def _make_registry_with(descriptors: list, root=PROJECT_ROOT) -> InvestigationRegistry:
    """Return a registry whose available() returns only the given descriptors."""
    reg = InvestigationRegistry(root)
    reg.available = lambda: descriptors
    return reg


# ---------------------------------------------------------------------------
# SelectionResult ? state invariants
# ---------------------------------------------------------------------------

class TestSelectionResultInvariants:

    def test_matched_state(self):
        d = _make_descriptor("inv_a", ("alpha",))
        r = SelectionResult(matched=True, ambiguous=False, descriptor=d, question="alpha", match_count=1)
        assert r.matched is True
        assert r.ambiguous is False
        assert r.no_match is False
        assert r.descriptor is d

    def test_no_match_state(self):
        r = SelectionResult(matched=False, ambiguous=False, question="unknown", match_count=0)
        assert r.matched is False
        assert r.ambiguous is False
        assert r.no_match is True
        assert r.descriptor is None

    def test_ambiguous_state(self):
        d1 = _make_descriptor("inv_a", ("alpha",))
        d2 = _make_descriptor("inv_b", ("alpha",))
        r = SelectionResult(
            matched=False, ambiguous=True,
            candidates=(d1, d2), question="alpha", match_count=1,
        )
        assert r.matched is False
        assert r.ambiguous is True
        assert r.no_match is False
        assert len(r.candidates) == 2

    def test_matched_and_ambiguous_raises(self):
        with pytest.raises(ValueError):
            SelectionResult(matched=True, ambiguous=True)

    def test_descriptor_without_matched_raises(self):
        d = _make_descriptor("inv_a", ("alpha",))
        with pytest.raises(ValueError):
            SelectionResult(matched=False, ambiguous=False, descriptor=d)

    def test_candidates_without_ambiguous_raises(self):
        d = _make_descriptor("inv_a", ("alpha",))
        with pytest.raises(ValueError):
            SelectionResult(matched=False, ambiguous=False, candidates=(d,))

    def test_immutable(self):
        r = SelectionResult(matched=False, ambiguous=False, question="q", match_count=0)
        with pytest.raises((AttributeError, TypeError)):
            r.matched = True


# ---------------------------------------------------------------------------
# SelectionResult.format_for_mission()
# ---------------------------------------------------------------------------

class TestSelectionResultFormat:

    def test_matched_format_contains_display_name(self):
        d = _make_descriptor("inv_a", ("alpha",))
        r = SelectionResult(matched=True, ambiguous=False, descriptor=d, question="alpha", match_count=1)
        text = r.format_for_mission()
        assert d.display_name in text

    def test_ambiguous_format_contains_cannot_determine(self):
        d1 = _make_descriptor("inv_a", ("alpha",))
        d2 = _make_descriptor("inv_b", ("alpha",))
        r = SelectionResult(
            matched=False, ambiguous=True,
            candidates=(d1, d2), question="alpha", match_count=1,
        )
        text = r.format_for_mission()
        assert "cannot determine" in text.lower() or "multiple" in text.lower()

    def test_no_match_format_contains_dont_have(self):
        r = SelectionResult(matched=False, ambiguous=False, question="q", match_count=0)
        # Patch _available to avoid AttributeError on bare result
        r.__dict__["_available"] = []
        text = r.format_for_mission()
        assert "don't have" in text.lower() or "no investigation" in text.lower() or "cannot" in text.lower()


# ---------------------------------------------------------------------------
# InvestigationSelector ? core selection logic
# ---------------------------------------------------------------------------

class TestInvestigationSelectorSelection:

    def test_known_question_matches(self):
        d = _make_descriptor("inv_a", ("consistent", "reconcile"))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent?")
        assert result.matched is True
        assert result.descriptor.name == "inv_a"

    def test_unknown_question_no_match(self):
        d = _make_descriptor("inv_a", ("consistent", "reconcile"))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("What is the weather like today?")
        assert result.no_match is True
        assert result.matched is False
        assert result.ambiguous is False

    def test_empty_registry_no_match(self):
        reg = _make_registry_with([])
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent?")
        assert result.no_match is True

    def test_tie_returns_ambiguous_not_guess(self):
        """Two descriptors with identical keyword hits must return ambiguous."""
        d1 = _make_descriptor("inv_a", ("alpha", "beta"))
        d2 = _make_descriptor("inv_b", ("alpha", "beta"))
        reg = _make_registry_with([d1, d2])
        sel = InvestigationSelector(reg)
        result = sel.select("alpha beta")
        assert result.ambiguous is True
        assert result.matched is False
        assert len(result.candidates) == 2

    def test_higher_score_wins(self):
        """Descriptor with more keyword hits wins over one with fewer."""
        d1 = _make_descriptor("inv_a", ("consistent", "reconcile", "git"))
        d2 = _make_descriptor("inv_b", ("consistent",))
        reg = _make_registry_with([d1, d2])
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent with git reconcile?")
        assert result.matched is True
        assert result.descriptor.name == "inv_a"

    def test_single_keyword_match(self):
        d = _make_descriptor("inv_a", ("investigate",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("Please investigate this.")
        assert result.matched is True

    def test_match_count_is_correct(self):
        d = _make_descriptor("inv_a", ("consistent", "reconcile", "git"))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("consistent reconcile git")
        assert result.match_count == 3

    def test_question_stored_in_result(self):
        d = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        q = "Is everything consistent?"
        result = sel.select(q)
        assert result.question == q


# ---------------------------------------------------------------------------
# InvestigationSelector ? whole-word matching
# ---------------------------------------------------------------------------

class TestInvestigationSelectorWholeWord:

    def test_partial_word_does_not_match(self):
        """'git' should not match 'digital'."""
        d = _make_descriptor("inv_a", ("git",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("digital transformation")
        assert result.no_match is True

    def test_exact_word_matches(self):
        d = _make_descriptor("inv_a", ("git",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("check the git status")
        assert result.matched is True

    def test_multi_word_phrase_matches(self):
        d = _make_descriptor("inv_a", ("is everything",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent?")
        assert result.matched is True

    def test_multi_word_phrase_partial_does_not_match(self):
        """'is everything' should not match 'is this consistent'."""
        d = _make_descriptor("inv_a", ("is everything",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("is this consistent")
        assert result.no_match is True

    def test_case_insensitive(self):
        d = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        sel = InvestigationSelector(reg)
        result = sel.select("CONSISTENT")
        assert result.matched is True


# ---------------------------------------------------------------------------
# InvestigationSelector ? real registry integration
# ---------------------------------------------------------------------------

class TestInvestigationSelectorRealRegistry:

    def test_real_registry_investigate_routes_to_project_state_vs_git(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent?")
        assert result.matched is True
        assert result.descriptor.name == "project_state_vs_git"

    def test_real_registry_reconcile_routes_correctly(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        sel = InvestigationSelector(reg)
        result = sel.select("Can you reconcile the project state?")
        assert result.matched is True
        assert result.descriptor.name == "project_state_vs_git"

    def test_real_registry_unknown_question_no_match(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        sel = InvestigationSelector(reg)
        result = sel.select("What is the capital of France?")
        assert result.no_match is True

    def test_real_registry_fake_root_no_match(self):
        """With fake root, no sources exist, so no investigations available."""
        reg = InvestigationRegistry(FAKE_ROOT)
        sel = InvestigationSelector(reg)
        result = sel.select("Is everything consistent?")
        assert result.no_match is True
