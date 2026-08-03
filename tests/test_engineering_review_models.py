"""
Tests — Engineering Data Models
Genesis-033 Sprint-001
"""

import pytest
from core.engineering.review.models import (
    ArchitectureDecision,
    DesktopValidation,
    EngineeringReview,
    FutureImprovement,
    GenesisReport,
    GenesisStatus,
    RDEvidenceRecord,
    Recommendation,
    TestResults,
)


# ── TestResults ────────────────────────────────────────────────────────────────

class TestTestResults:
    def test_is_green_true_when_no_failures(self):
        tr = TestResults(passed=100, skipped=5, failed=0)
        assert tr.is_green is True

    def test_is_green_false_when_failures_exist(self):
        tr = TestResults(passed=100, skipped=5, failed=3)
        assert tr.is_green is False

    def test_is_green_false_when_all_failed(self):
        tr = TestResults(passed=0, skipped=0, failed=10)
        assert tr.is_green is False

    def test_warnings_default_zero(self):
        tr = TestResults(passed=1, skipped=0, failed=0)
        assert tr.warnings == 0


# ── FutureImprovement defaults ─────────────────────────────────────────────────

class TestFutureImprovementDefaults:
    def test_priority_default(self):
        fi = FutureImprovement(genesis="033", title="Test", description="Desc")
        assert fi.priority == "medium"

    def test_category_default(self):
        fi = FutureImprovement(genesis="033", title="Test", description="Desc")
        assert fi.category == "general"

    def test_explicit_priority(self):
        fi = FutureImprovement(
            genesis="033", title="Test", description="Desc", priority="high"
        )
        assert fi.priority == "high"

    def test_explicit_category(self):
        fi = FutureImprovement(
            genesis="033", title="Test", description="Desc", category="memory"
        )
        assert fi.category == "memory"


# ── GenesisReport ──────────────────────────────────────────────────────────────

class TestGenesisReport:
    def _make_report(self):
        review = EngineeringReview(
            genesis="033",
            sprint="001",
            status=GenesisStatus.COMPLETE,
            completed_at="2026-08-03",
            recommendation=Recommendation.BEGIN_NEXT_GENESIS,
            recommendation_reason="All done.",
        )
        rd = RDEvidenceRecord(genesis="033")
        improvements = [
            FutureImprovement(genesis="033", title="X", description="Y")
        ]
        return GenesisReport(
            review=review,
            rd_evidence=rd,
            improvements=improvements,
            rendered_at="2026-08-03T12:00:00",
        )

    def test_has_review(self):
        report = self._make_report()
        assert report.review is not None

    def test_has_rd_evidence(self):
        report = self._make_report()
        assert report.rd_evidence is not None

    def test_has_improvements(self):
        report = self._make_report()
        assert isinstance(report.improvements, list)

    def test_has_rendered_at(self):
        report = self._make_report()
        assert report.rendered_at != ""

    def test_four_required_fields_present(self):
        report = self._make_report()
        assert hasattr(report, "review")
        assert hasattr(report, "rd_evidence")
        assert hasattr(report, "improvements")
        assert hasattr(report, "rendered_at")


# ── GenesisStatus enum ─────────────────────────────────────────────────────────

class TestGenesisStatusEnum:
    def test_complete_value(self):
        assert GenesisStatus.COMPLETE.value == "complete"

    def test_in_progress_value(self):
        assert GenesisStatus.IN_PROGRESS.value == "in_progress"

    def test_abandoned_value(self):
        assert GenesisStatus.ABANDONED.value == "abandoned"

    def test_stabilising_value(self):
        assert GenesisStatus.STABILISING.value == "stabilising"


# ── Recommendation enum ────────────────────────────────────────────────────────

class TestRecommendationEnum:
    def test_begin_next_genesis(self):
        assert Recommendation.BEGIN_NEXT_GENESIS.value == "BEGIN_NEXT_GENESIS"

    def test_enter_stabilisation(self):
        assert Recommendation.ENTER_STABILISATION.value == "ENTER_STABILISATION"
