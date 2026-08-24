"""
Genesis-058 Sprint-003 - Wire InvestigationSelector into ReadOnlyInvestigator.

Covers:
    - InvestigationReport.investigation_name field exists with default
    - investigate() no-match returns correct conclusion, no proposal
    - investigate() ambiguous returns correct conclusion, no proposal
    - investigate() matched sets investigation_name from descriptor
    - investigate() matched dispatches to correct method
    - investigate() matched result has investigation_name from registry
    - No proposal ever emerges from selector uncertainty
    - End-to-end: real registry, real question routes to project_state_vs_git
    - End-to-end: unknown question returns no-match report
    - end-to-end: format_for_mission() works for all three selector outcomes
"""
from __future__ import annotations

import pathlib
import pytest
from unittest.mock import MagicMock, patch

from core.mission.authorised_sources import AuthorisedSourceRegistry
from core.mission.investigation import (
    InvestigationReport,
    InvestigationStatus,
    ReadOnlyInvestigator,
)
from core.mission.investigation_registry import InvestigationDescriptor, InvestigationRegistry
from core.mission.investigation_selector import InvestigationSelector, SelectionResult

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")
FAKE_ROOT    = pathlib.Path(r"C:\\nonexistent\\path\\that\\does\\not\\exist")


def _make_investigator(root=PROJECT_ROOT) -> ReadOnlyInvestigator:
    reg = AuthorisedSourceRegistry(root)
    return ReadOnlyInvestigator(reg, root)


# ---------------------------------------------------------------------------
# InvestigationReport.investigation_name
# ---------------------------------------------------------------------------

class TestInvestigationReportName:

    def test_investigation_name_default_is_empty_string(self):
        report = InvestigationReport(
            investigation_id  = "INV-TEST-000001",
            question          = "test",
            sources_inspected = [],
            findings          = [],
            conclusion        = "test conclusion",
            proposed_action   = None,
            approval_required = False,
        )
        assert report.investigation_name == ""

    def test_investigation_name_can_be_set(self):
        report = InvestigationReport(
            investigation_id   = "INV-TEST-000002",
            question           = "test",
            sources_inspected  = [],
            findings           = [],
            conclusion         = "test conclusion",
            proposed_action    = None,
            approval_required  = False,
            investigation_name = "project_state_vs_git",
        )
        assert report.investigation_name == "project_state_vs_git"


# ---------------------------------------------------------------------------
# investigate() - no match
# ---------------------------------------------------------------------------

class TestInvestigateNoMatch:

    def _make_with_no_match_selector(self) -> ReadOnlyInvestigator:
        inv = _make_investigator()
        no_match = SelectionResult(matched=False, ambiguous=False, question="q", match_count=0)
        inv._selector = MagicMock()
        inv._selector.select.return_value = no_match
        return inv

    def test_no_match_returns_report(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert isinstance(report, InvestigationReport)

    def test_no_match_conclusion(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert "No available investigation matches this question" in report.conclusion

    def test_no_match_no_proposal(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert report.bound_proposal is None

    def test_no_match_approval_not_required(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert report.approval_required is False

    def test_no_match_investigation_name_empty(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert report.investigation_name == ""

    def test_no_match_no_sources_inspected(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert report.sources_inspected == []

    def test_no_match_no_findings(self):
        inv = self._make_with_no_match_selector()
        report = inv.investigate("What is the weather?")
        assert report.findings == []


# ---------------------------------------------------------------------------
# investigate() - ambiguous
# ---------------------------------------------------------------------------

class TestInvestigateAmbiguous:

    def _make_with_ambiguous_selector(self) -> ReadOnlyInvestigator:
        inv = _make_investigator()
        d1 = InvestigationDescriptor(
            name="inv_a", display_name="Inv A", description="A.",
            question_keywords=("alpha",), evidence_sources=("project_state",),
        )
        d2 = InvestigationDescriptor(
            name="inv_b", display_name="Inv B", description="B.",
            question_keywords=("alpha",), evidence_sources=("project_state",),
        )
        ambiguous = SelectionResult(
            matched=False, ambiguous=True,
            candidates=(d1, d2), question="alpha", match_count=1,
        )
        inv._selector = MagicMock()
        inv._selector.select.return_value = ambiguous
        return inv

    def test_ambiguous_returns_report(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert isinstance(report, InvestigationReport)

    def test_ambiguous_conclusion(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert "cannot safely choose" in report.conclusion

    def test_ambiguous_no_proposal(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert report.bound_proposal is None

    def test_ambiguous_approval_not_required(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert report.approval_required is False

    def test_ambiguous_investigation_name_empty(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert report.investigation_name == ""

    def test_ambiguous_no_sources_inspected(self):
        inv = self._make_with_ambiguous_selector()
        report = inv.investigate("alpha")
        assert report.sources_inspected == []


# ---------------------------------------------------------------------------
# investigate() - matched
# ---------------------------------------------------------------------------

class TestInvestigateMatched:

    def test_matched_dispatches_to_correct_method(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert isinstance(report, InvestigationReport)

    def test_matched_investigation_name_from_descriptor(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert report.investigation_name == "project_state_vs_git"

    def test_matched_investigation_name_not_from_question(self):
        """investigation_name must come from the descriptor, not the question text."""
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert "consistent" not in report.investigation_name
        assert "question" not in report.investigation_name

    def test_matched_has_sources_inspected(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert len(report.sources_inspected) > 0

    def test_matched_has_findings(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert len(report.findings) > 0

    def test_matched_has_conclusion(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert len(report.conclusion) > 0

    def test_matched_status_is_no_changes_made(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert report.status == InvestigationStatus.NO_CHANGES_MADE


# ---------------------------------------------------------------------------
# End-to-end: real registry, real questions
# ---------------------------------------------------------------------------

class TestInvestigateEndToEnd:

    def test_known_question_routes_to_project_state_vs_git(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        assert report.investigation_name == "project_state_vs_git"

    def test_reconcile_question_routes_correctly(self):
        inv = _make_investigator()
        report = inv.investigate("Can you reconcile the project state with git?")
        assert report.investigation_name == "project_state_vs_git"

    def test_unknown_question_no_match_report(self):
        inv = _make_investigator()
        report = inv.investigate("What is the capital of France?")
        assert "No available investigation matches" in report.conclusion
        assert report.bound_proposal is None
        assert report.approval_required is False

    def test_format_for_mission_no_match(self):
        inv = _make_investigator()
        report = inv.investigate("What is the capital of France?")
        text = report.format_for_mission()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_format_for_mission_matched(self):
        inv = _make_investigator()
        report = inv.investigate("Is everything consistent?")
        text = report.format_for_mission()
        assert isinstance(text, str)
        assert "INVESTIGATION" in text

    def test_fake_root_no_match(self):
        """With fake root, no sources available, so no-match report returned."""
        reg = AuthorisedSourceRegistry(FAKE_ROOT)
        inv = ReadOnlyInvestigator(reg, FAKE_ROOT)
        report = inv.investigate("Is everything consistent?")
        assert "No available investigation matches" in report.conclusion
        assert report.bound_proposal is None
