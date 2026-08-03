"""
Engineering Intelligence — Engineering Review Worker
Genesis-033 Sprint-001

Orchestrates the full engineering review pipeline:
  Collect Evidence → Build Review → Validate → Build R&D Evidence
  → Extract Improvements → Build Report → Persist (JSON first, Markdown second)

This worker never calls an AI model.
All output is derived from evidence explicitly provided.
No field is inferred or hallucinated.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import date, datetime

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

logger = logging.getLogger(__name__)


class EngineeringReviewWorker:
    """
    Produces structured engineering artefacts at the conclusion of a Genesis.

    Pipeline (in order):
      1. Build structured EngineeringReview from evidence
      2. Validate the review (raises on critical errors)
      3. Build RDEvidenceRecord
      4. Extract FutureImprovement objects
      5. Assemble GenesisReport
      6. Persist JSON (always first), then Markdown
      7. Return GenesisReport

    This worker never calls an AI model.
    """

    def __init__(self, output_dir: str = "engineering_reviews") -> None:
        self._output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self._renderer = MarkdownRenderer()

    # ── Public ─────────────────────────────────────────────────────────────────

    def run(self, evidence: dict) -> GenesisReport:
        """
        Execute the full pipeline and return a GenesisReport.

        Args:
            evidence: A dict containing all engineering evidence for this sprint.

        Returns:
            A fully populated and persisted GenesisReport.
        """
        review      = self._build_review(evidence)
        self._validate(review)
        rd          = self._build_rd_evidence(evidence, review)
        improvements = self._extract_improvements(evidence, review)
        rendered_at = datetime.now().isoformat()
        report      = GenesisReport(
            review=review,
            rd_evidence=rd,
            improvements=improvements,
            rendered_at=rendered_at,
        )
        self._persist(report)
        return report

    # ── Pipeline steps ─────────────────────────────────────────────────────────

    def _build_review(self, evidence: dict) -> EngineeringReview:
        """Map evidence dict fields onto EngineeringReview dataclass."""

        # Status — default to IN_PROGRESS if not recognised
        raw_status = evidence.get("status", "in_progress")
        try:
            status = GenesisStatus(raw_status.lower())
        except ValueError:
            logger.warning("Unknown genesis status %r — defaulting to IN_PROGRESS", raw_status)
            status = GenesisStatus.IN_PROGRESS

        # Recommendation
        raw_rec = evidence.get("recommendation", "CONTINUE_GENESIS")
        try:
            recommendation = Recommendation(raw_rec.upper())
        except ValueError:
            logger.warning("Unknown recommendation %r — defaulting to CONTINUE_GENESIS", raw_rec)
            recommendation = Recommendation.CONTINUE_GENESIS

        # TestResults
        tr_raw = evidence.get("test_results", {})
        test_results = TestResults(
            passed=int(tr_raw.get("passed", 0)),
            skipped=int(tr_raw.get("skipped", 0)),
            failed=int(tr_raw.get("failed", 0)),
            warnings=int(tr_raw.get("warnings", 0)),
        )

        # DesktopValidation
        dv_raw = evidence.get("desktop_validation", {})
        desktop_validation = DesktopValidation(
            status=dv_raw.get("status", "unknown"),
            scenarios=list(dv_raw.get("scenarios", [])),
            notes=dv_raw.get("notes"),
        )

        # ArchitectureDecisions
        architecture_decisions: list[ArchitectureDecision] = []
        for ad in evidence.get("architecture_decisions", []):
            architecture_decisions.append(
                ArchitectureDecision(
                    decision=ad.get("decision", ""),
                    rationale=ad.get("rationale", ""),
                    alternatives=list(ad.get("alternatives", [])),
                )
            )

        # completed_at — today if not supplied
        completed_at = evidence.get("completed_at") or date.today().isoformat()

        return EngineeringReview(
            genesis=str(evidence.get("genesis", "")),
            sprint=str(evidence.get("sprint", "")),
            status=status,
            completed_at=completed_at,
            commits=list(evidence.get("commits", [])),
            files_added=list(evidence.get("files_added", [])),
            files_modified=list(evidence.get("files_modified", [])),
            architecture_decisions=architecture_decisions,
            tests_added=int(evidence.get("tests_added", 0)),
            test_results=test_results,
            desktop_validation=desktop_validation,
            technical_debt=list(evidence.get("technical_debt", [])),
            risks=list(evidence.get("risks", [])),
            future_improvements=[
                fi.get("title", "") if isinstance(fi, dict) else str(fi)
                for fi in evidence.get("future_improvements", [])
            ],
            recommendation=recommendation,
            recommendation_reason=str(evidence.get("recommendation_reason", "")),
        )

    def _validate(self, review: EngineeringReview) -> None:
        """
        Validate the review. Raises ValueError on critical errors.
        Logs warnings for non-critical issues.
        """
        if not review.genesis:
            raise ValueError("EngineeringReview.genesis must not be empty.")

        if review.recommendation_reason == "":
            raise ValueError(
                "EngineeringReview.recommendation_reason must not be empty."
            )

        if (
            review.test_results.failed > 0
            and review.status == GenesisStatus.COMPLETE
        ):
            raise ValueError(
                f"Cannot mark Genesis {review.genesis} as COMPLETE with "
                f"{review.test_results.failed} failed test(s)."
            )

        if not review.files_added:
            logger.warning(
                "Genesis %s Sprint %s: no files_added recorded.",
                review.genesis,
                review.sprint,
            )

        if not review.commits:
            logger.warning(
                "Genesis %s Sprint %s: no commits recorded.",
                review.genesis,
                review.sprint,
            )

    def _build_rd_evidence(
        self, evidence: dict, review: EngineeringReview
    ) -> RDEvidenceRecord:
        """
        Map evidence dict onto RDEvidenceRecord.
        Never infers or hallucinates — only maps explicitly provided fields.
        Missing fields default to empty string / empty list.
        """
        return RDEvidenceRecord(
            genesis=review.genesis,
            technical_problem=str(evidence.get("technical_problem", "")),
            technical_uncertainty=str(evidence.get("technical_uncertainty", "")),
            hypothesis=str(evidence.get("hypothesis", "")),
            approach=str(evidence.get("approach", "")),
            experiments=list(evidence.get("experiments", [])),
            results=str(evidence.get("results", "")),
            validation=str(evidence.get("validation", "")),
            remaining_unknowns=list(evidence.get("remaining_unknowns", [])),
        )

    def _extract_improvements(
        self, evidence: dict, review: EngineeringReview
    ) -> list[FutureImprovement]:
        """
        Map future_improvements list from evidence into FutureImprovement objects.
        Sets genesis from review.genesis.
        Defaults: priority="medium", category="general".
        """
        result: list[FutureImprovement] = []
        for item in evidence.get("future_improvements", []):
            if isinstance(item, dict):
                result.append(
                    FutureImprovement(
                        genesis=review.genesis,
                        title=str(item.get("title", "")),
                        description=str(item.get("description", "")),
                        priority=str(item.get("priority", "medium")),
                        category=str(item.get("category", "general")),
                    )
                )
            else:
                # Plain string fallback
                result.append(
                    FutureImprovement(
                        genesis=review.genesis,
                        title=str(item),
                        description="",
                        priority="medium",
                        category="general",
                    )
                )
        return result

    def _persist(self, report: GenesisReport) -> None:
        """
        Write JSON (always first) then Markdown to output_dir.

        Files:
          genesis_{N}_sprint_{M}_review.json
          genesis_{N}_sprint_{M}_report.md
        """
        review = report.review
        base   = f"genesis_{review.genesis}_sprint_{review.sprint}"
        json_path = os.path.join(self._output_dir, f"{base}_review.json")
        md_path   = os.path.join(self._output_dir, f"{base}_report.md")

        # JSON first — always
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(dataclasses.asdict(report), fh, indent=2, default=str)
        logger.info("Persisted JSON: %s", json_path)

        # Markdown second
        markdown = self._renderer.render(report)
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
        logger.info("Persisted Markdown: %s", md_path)
