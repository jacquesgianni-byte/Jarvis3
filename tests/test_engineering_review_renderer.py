"""
Tests — MarkdownRenderer
Genesis-033 Sprint-001
"""

import pytest
from core.engineering.review.markdown_renderer import MarkdownRenderer
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


def _make_full_report() -> GenesisReport:
    """Build a representative GenesisReport for renderer tests."""
    review = EngineeringReview(
        genesis="032",
        sprint="003",
        status=GenesisStatus.COMPLETE,
        completed_at="2026-08-03",
        commits=["abc1234", "def5678"],
        files_added=["jarvis/core/episodic_memory_engine.py"],
        files_modified=["jarvis/core/agent.py"],
        architecture_decisions=[
            ArchitectureDecision(
                decision="Provider architecture for recall engines",
                rationale="Extensible without modifying core engine",
                alternatives=["Monolithic recall handler"],
            )
        ],
        tests_added=49,
        test_results=TestResults(passed=3387, skipped=33, failed=0, warnings=0),
        desktop_validation=DesktopValidation(
            status="passed",
            scenarios=["Semantic recall", "Episodic recall — labeled"],
            notes=None,
        ),
        technical_debt=[],
        risks=[],
        future_improvements=["Day-name episodic recall"],
        recommendation=Recommendation.BEGIN_NEXT_GENESIS,
        recommendation_reason="Memory trilogy complete. No failed tests.",
    )
    rd = RDEvidenceRecord(
        genesis="032",
        technical_problem="No episodic recall capability.",
        technical_uncertainty="Whether deterministic grouping would work.",
        hypothesis="Provider pattern can assemble episodes from existing tags.",
        approach="Three layered recall engines over KnowledgeEngine.",
        experiments=["SemanticRecallEngine validated", "EpisodicMemoryEngine validated"],
        results="All engines passed desktop validation.",
        validation="3387 tests passing.",
        remaining_unknowns=["Behaviour at scale"],
    )
    improvements = [
        FutureImprovement(
            genesis="032",
            title="Day-name episodic recall",
            description="Recall episodes by day name",
            priority="medium",
            category="memory",
        ),
        FutureImprovement(
            genesis="032",
            title="Contradiction detection",
            description="Detect contradictory facts",
            priority="high",
            category="memory",
        ),
    ]
    return GenesisReport(
        review=review,
        rd_evidence=rd,
        improvements=improvements,
        rendered_at="2026-08-03T10:00:00",
    )


class TestMarkdownRenderer:
    def setup_method(self):
        self.renderer = MarkdownRenderer()
        self.report = _make_full_report()
        self.output = self.renderer.render(self.report)

    def test_returns_non_empty_string(self):
        assert isinstance(self.output, str)
        assert len(self.output) > 0

    def test_includes_genesis_number(self):
        assert "032" in self.output

    def test_includes_sprint_number(self):
        assert "003" in self.output

    def test_includes_passed_count(self):
        assert "3387" in self.output

    def test_includes_skipped_count(self):
        assert "33" in self.output

    def test_includes_failed_count(self):
        assert "0" in self.output

    def test_includes_recommendation_text(self):
        assert "BEGIN_NEXT_GENESIS" in self.output

    def test_includes_recommendation_reason(self):
        assert "Memory trilogy complete" in self.output

    def test_includes_all_future_improvements(self):
        assert "Day-name episodic recall" in self.output
        assert "Contradiction detection" in self.output

    def test_includes_rd_problem(self):
        assert "No episodic recall capability" in self.output

    def test_includes_rd_uncertainty(self):
        assert "deterministic grouping" in self.output

    def test_includes_rd_hypothesis(self):
        assert "Provider pattern" in self.output

    def test_includes_rd_approach(self):
        assert "Three layered recall engines" in self.output

    def test_includes_rd_results(self):
        assert "All engines passed" in self.output

    def test_includes_rd_validation(self):
        assert "3387 tests passing" in self.output

    def test_includes_status_section(self):
        assert "## Status" in self.output

    def test_includes_commits_section(self):
        assert "## Commits" in self.output
        assert "abc1234" in self.output

    def test_includes_architecture_decisions(self):
        assert "Provider architecture for recall engines" in self.output

    def test_technical_debt_none_identified(self):
        assert "None identified" in self.output

    def test_desktop_validation_status(self):
        assert "passed" in self.output

    def test_future_improvement_priority_tag(self):
        assert "[medium]" in self.output
        assert "[high]" in self.output

    def test_rd_evidence_section_present(self):
        assert "## R&D Evidence Summary" in self.output

    def test_recommendation_section_present(self):
        assert "## Recommendation" in self.output


class TestMarkdownRendererEmptyLists:
    """Edge cases — empty collections render gracefully."""

    def test_no_commits_renders_placeholder(self):
        renderer = MarkdownRenderer()
        review = EngineeringReview(
            genesis="001",
            sprint="001",
            status=GenesisStatus.IN_PROGRESS,
            completed_at="2026-01-01",
            recommendation=Recommendation.CONTINUE_GENESIS,
            recommendation_reason="Still building.",
        )
        rd = RDEvidenceRecord(genesis="001")
        report = GenesisReport(
            review=review,
            rd_evidence=rd,
            improvements=[],
            rendered_at="2026-01-01T00:00:00",
        )
        output = renderer.render(report)
        assert "*(none recorded)*" in output

    def test_no_improvements_renders_placeholder(self):
        renderer = MarkdownRenderer()
        review = EngineeringReview(
            genesis="001",
            sprint="001",
            status=GenesisStatus.IN_PROGRESS,
            completed_at="2026-01-01",
            recommendation=Recommendation.CONTINUE_GENESIS,
            recommendation_reason="Still building.",
        )
        rd = RDEvidenceRecord(genesis="001")
        report = GenesisReport(
            review=review,
            rd_evidence=rd,
            improvements=[],
            rendered_at="2026-01-01T00:00:00",
        )
        output = renderer.render(report)
        assert "*(none deferred)*" in output
