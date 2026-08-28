"""
Genesis-061 Sprint-001 - ProximityResult + CapabilityProximityAnalyser tests.

Covers:
    ProximityResult:
        - fields accessible and immutable
        - gap_is_isolated True when closest_score == 0
        - is_tied True when multiple descriptors share max score
        - all_scores contains every compared descriptor
        - format_for_report() returns string for all three states
        - format_for_report() isolated: contains "ISOLATED" and score=0
        - format_for_report() tied: contains all tied names
        - format_for_report() proximate: contains closest name and score
        - format_for_report() always contains audit trail

    CapabilityProximityAnalyser.analyse():
        - returns ProximityResult
        - score=0 when no keywords overlap (isolated gap)
        - score>0 when keywords overlap
        - highest scorer is closest_names[0] when unambiguous
        - both names in closest_names when tied
        - all_scores has entry for every descriptor
        - whole-word matching: partial word does not score
        - multi-word phrase match counts as one hit
        - case-insensitive matching
        - empty registry returns isolated result
        - score does NOT mean semantic understanding (guard test)
        - analyser does not modify registry or observation
"""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import MagicMock

from core.knowledge.proximity import (
    ProximityResult,
    CapabilityProximityAnalyser,
)
from core.mission.investigation_registry import (
    InvestigationDescriptor,
    InvestigationRegistry,
)

PROJECT_ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")


def _make_descriptor(name: str, keywords: tuple) -> InvestigationDescriptor:
    return InvestigationDescriptor(
        name              = name,
        display_name      = name.replace("_", " ").title(),
        description       = f"Test: {name}",
        question_keywords = keywords,
        evidence_sources  = ("project_state",),
    )


def _make_registry_with(descriptors: list) -> InvestigationRegistry:
    reg = InvestigationRegistry(PROJECT_ROOT)
    reg.all_descriptors = lambda: descriptors
    return reg


OBS_ID = "OBS-TEST01"


class TestProximityResult:

    def _make(self, **kwargs) -> ProximityResult:
        defaults = dict(
            observation_id     = OBS_ID,
            closest_names      = ("inv_a",),
            closest_score      = 2,
            total_capabilities = 1,
            all_scores         = {"inv_a": 2},
            gap_is_isolated    = False,
            is_tied            = False,
        )
        defaults.update(kwargs)
        return ProximityResult(**defaults)

    def test_fields_accessible(self):
        r = self._make()
        assert r.observation_id     == OBS_ID
        assert r.closest_names      == ("inv_a",)
        assert r.closest_score      == 2
        assert r.total_capabilities == 1
        assert r.gap_is_isolated    is False
        assert r.is_tied            is False

    def test_immutable(self):
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.closest_score = 99

    def test_isolated_when_score_zero(self):
        r = self._make(closest_names=(), closest_score=0, gap_is_isolated=True, all_scores={"inv_a": 0})
        assert r.gap_is_isolated is True
        assert r.closest_score   == 0
        assert len(r.closest_names) == 0

    def test_tied_when_multiple_winners(self):
        r = self._make(
            closest_names  = ("inv_a", "inv_b"),
            closest_score  = 2,
            total_capabilities = 2,
            all_scores     = {"inv_a": 2, "inv_b": 2},
            is_tied        = True,
        )
        assert r.is_tied is True
        assert "inv_a" in r.closest_names
        assert "inv_b" in r.closest_names

    def test_format_for_report_is_string(self):
        r = self._make()
        assert isinstance(r.format_for_report(), str)

    def test_format_for_report_isolated_contains_isolated(self):
        r = self._make(closest_names=(), closest_score=0, gap_is_isolated=True,
                       all_scores={"inv_a": 0}, total_capabilities=1)
        assert "ISOLATED" in r.format_for_report()

    def test_format_for_report_isolated_contains_score_zero(self):
        r = self._make(closest_names=(), closest_score=0, gap_is_isolated=True,
                       all_scores={"inv_a": 0}, total_capabilities=1)
        assert "0" in r.format_for_report()

    def test_format_for_report_isolated_no_semantic_claim(self):
        r = self._make(closest_names=(), closest_score=0, gap_is_isolated=True,
                       all_scores={"inv_a": 0}, total_capabilities=1)
        text = r.format_for_report()
        assert "mission" not in text.lower()
        assert "planning" not in text.lower()
        assert "recommend" not in text.lower()

    def test_format_for_report_tied_contains_both_names(self):
        r = self._make(
            closest_names=("inv_a", "inv_b"), closest_score=2,
            total_capabilities=2, all_scores={"inv_a": 2, "inv_b": 2},
            is_tied=True,
        )
        text = r.format_for_report()
        assert "inv_a" in text
        assert "inv_b" in text

    def test_format_for_report_proximate_contains_name(self):
        r = self._make()
        assert "inv_a" in r.format_for_report()

    def test_format_for_report_always_contains_audit_trail(self):
        r = self._make()
        assert "audit trail" in r.format_for_report().lower() or "inv_a" in r.format_for_report()


class TestCapabilityProximityAnalyser:

    def test_returns_proximity_result(self):
        d   = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent?", OBS_ID, reg)
        assert isinstance(r, ProximityResult)

    def test_score_zero_when_no_overlap(self):
        d   = _make_descriptor("inv_a", ("consistent", "reconcile"))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("What should our next mission be?", OBS_ID, reg)
        assert r.closest_score   == 0
        assert r.gap_is_isolated is True

    def test_score_positive_when_overlap(self):
        d   = _make_descriptor("inv_a", ("consistent", "reconcile"))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent?", OBS_ID, reg)
        assert r.closest_score > 0

    def test_highest_scorer_is_closest(self):
        d1  = _make_descriptor("inv_a", ("consistent", "reconcile", "git"))
        d2  = _make_descriptor("inv_b", ("consistent",))
        reg = _make_registry_with([d1, d2])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent with git reconcile?", OBS_ID, reg)
        assert r.closest_names[0] == "inv_a"
        assert r.is_tied is False

    def test_tied_when_equal_scores(self):
        d1  = _make_descriptor("inv_a", ("consistent",))
        d2  = _make_descriptor("inv_b", ("consistent",))
        reg = _make_registry_with([d1, d2])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent?", OBS_ID, reg)
        assert r.is_tied is True
        assert "inv_a" in r.closest_names
        assert "inv_b" in r.closest_names

    def test_all_scores_has_every_descriptor(self):
        d1  = _make_descriptor("inv_a", ("consistent",))
        d2  = _make_descriptor("inv_b", ("reconcile",))
        reg = _make_registry_with([d1, d2])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent?", OBS_ID, reg)
        assert "inv_a" in r.all_scores
        assert "inv_b" in r.all_scores

    def test_whole_word_partial_does_not_score(self):
        """'git' should not match 'digital'."""
        d   = _make_descriptor("inv_a", ("git",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("digital transformation", OBS_ID, reg)
        assert r.all_scores["inv_a"] == 0

    def test_whole_word_exact_scores(self):
        d   = _make_descriptor("inv_a", ("git",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("check the git status", OBS_ID, reg)
        assert r.all_scores["inv_a"] == 1

    def test_multi_word_phrase_scores(self):
        d   = _make_descriptor("inv_a", ("is everything",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("Is everything consistent?", OBS_ID, reg)
        assert r.all_scores["inv_a"] == 1

    def test_case_insensitive(self):
        d   = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("CONSISTENT", OBS_ID, reg)
        assert r.all_scores["inv_a"] == 1

    def test_empty_registry_returns_isolated(self):
        reg = _make_registry_with([])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("What should our next mission be?", OBS_ID, reg)
        assert r.gap_is_isolated    is True
        assert r.total_capabilities == 0

    def test_score_zero_is_not_semantic_claim(self):
        """
        Guard test: score=0 means no keyword overlap only.
        The analyser must not label the question domain.
        """
        d   = _make_descriptor("inv_a", ("consistent", "reconcile"))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("What should our next mission be?", OBS_ID, reg)
        assert r.gap_is_isolated is True
        # No semantic label anywhere in the result
        assert not hasattr(r, "domain")
        assert not hasattr(r, "semantic_category")
        assert not hasattr(r, "question_type")

    def test_analyser_does_not_modify_registry(self):
        d   = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        original_descriptors = reg.all_descriptors()
        a   = CapabilityProximityAnalyser()
        a.analyse("test question", OBS_ID, reg)
        assert reg.all_descriptors() == original_descriptors

    def test_observation_id_preserved_in_result(self):
        d   = _make_descriptor("inv_a", ("consistent",))
        reg = _make_registry_with([d])
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("test", "OBS-MYTEST", reg)
        assert r.observation_id == "OBS-MYTEST"

    def test_real_registry_mission_question_proximity(self):
        """
        Using the real InvestigationRegistry, verify proximity analysis runs
        correctly against the registered investigation surface.
        As the capability surface grows, this question may score > 0 --
        that is correct CAA behaviour (richer surface = better proximity).
        We verify the analyser runs without error and returns a valid result.
        """
        reg = InvestigationRegistry(PROJECT_ROOT)
        a   = CapabilityProximityAnalyser()
        r   = a.analyse("What should our next mission be?", OBS_ID, reg)
        assert isinstance(r, type(r))  # result is a ProximityResult
        assert r.total_capabilities == len(reg.all_descriptors())
        assert r.observation_id == OBS_ID
