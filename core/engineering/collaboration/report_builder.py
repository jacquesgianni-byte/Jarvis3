"""
Engineering Collaboration Framework — Report Builder
Genesis-040 Sprint-002

Assembles EngineeringCollaborationReport and renders it as Markdown.

Design principle:
  JSON is the source of truth.
  Markdown is a derived presentation layer — never stored as primary data.

The report is part of engineering history:
  every collaboration produces one, regardless of outcome.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.collaboration.models import (
    EngineeringApprovalRequest,
    EngineeringCollaborationReport,
    EngineeringCollaborationSession,
)

logger = logging.getLogger(__name__)


class CollaborationReportBuilder:
    """
    Builds EngineeringCollaborationReport from a completed session
    and renders it as a Markdown string.

    Public API:
        build(session)  -> EngineeringCollaborationReport
        render(report)  -> str (Markdown)
        build_approval(report) -> EngineeringApprovalRequest
    """

    def build(
        self,
        session: EngineeringCollaborationSession,
    ) -> EngineeringCollaborationReport:
        """Build a structured report from a completed session."""
        report = EngineeringCollaborationReport.from_session(session)
        logger.info(
            "[REPORT_BUILDER] Built report %s — ready=%s",
            report.report_id[:8], report.ready_for_approval,
        )
        return report

    def build_approval(
        self,
        report: EngineeringCollaborationReport,
    ) -> EngineeringApprovalRequest:
        """Build an approval request from a completed report."""
        return EngineeringApprovalRequest.from_report(report)

    def render(self, report: EngineeringCollaborationReport) -> str:
        """Render the report as a Markdown string."""
        sep = "─" * 56
        lines = [
            "# Engineering Collaboration Report",
            "",
            f"**Worker:** {report.worker}",
            f"**Capability:** {report.capability}",
            f"**Status:** {report.status.upper()}",
        ]

        if report.duration_seconds is not None:
            lines.append(f"**Duration:** {report.duration_seconds:.1f}s")

        lines += ["", sep, ""]

        # Worker response section
        lines += [
            "## Worker Response",
            "",
            report.worker_response if report.worker_response else "_No response recorded._",
            "",
        ]

        # Engineering review summary
        lines += ["## Engineering Gates", ""]

        review_icon = "✅" if report.review_passed else "❌"
        tests_icon  = "✅" if report.tests_passed  else "❌"
        lines += [
            f"{review_icon} Engineering review: {'passed' if report.review_passed else 'FAILED'}",
            f"{tests_icon} Regression tests:   {'passed' if report.tests_passed else 'FAILED'}",
        ]

        if report.tests_executed > 0:
            lines.append(f"   Tests executed: {report.tests_executed}")

        if report.files_changed:
            lines += [
                "",
                f"**Files changed ({len(report.files_changed)}):**",
            ]
            for f in report.files_changed:
                lines.append(f"  - `{f}`")

        if report.warnings:
            lines += ["", "**Warnings:**"]
            for w in report.warnings:
                lines.append(f"  ⚠️  {w}")

        lines += [""]

        # Blocked reason
        if report.blocked_reason:
            lines += [
                "## Blocked",
                "",
                f"🚫 {report.blocked_reason}",
                "",
            ]

        # Recommendation
        if report.recommendation:
            lines += [
                "## Recommendation",
                "",
                report.recommendation,
                "",
            ]

        # Approval gate
        lines += [sep, ""]
        if report.ready_for_approval:
            lines += [
                "✅ **Ready for human approval.**",
                "",
                "⚠️  Jarvis never installs automatically.",
                "Human approval is required before any changes are applied.",
            ]
        else:
            lines += [
                "🚫 **Installation blocked.**",
                "Not ready for approval until all engineering gates pass.",
            ]

        return "\n".join(lines)

    def render_full(
        self,
        report: EngineeringCollaborationReport,
        approval: EngineeringApprovalRequest,
    ) -> str:
        """Render report + approval request as a single Markdown string."""
        return self.render(report) + "\n\n" + approval.to_text()
