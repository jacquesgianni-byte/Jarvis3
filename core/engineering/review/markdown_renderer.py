"""
Engineering Intelligence — Markdown Renderer
Genesis-033 Sprint-001

Renders a human-readable Markdown report from a GenesisReport.
Markdown is a presentation layer only — never the source of truth.
This class never accepts raw dicts.
"""

from __future__ import annotations

from core.engineering.review.models import GenesisReport


class MarkdownRenderer:
    """Renders GenesisReport → Markdown string."""

    def render(self, report: GenesisReport) -> str:
        """
        Render a complete Markdown report from a GenesisReport.

        Args:
            report: A fully populated GenesisReport.

        Returns:
            A non-empty Markdown string.
        """
        review = report.review
        rd     = report.rd_evidence
        improv = report.improvements

        lines: list[str] = []

        # ── Title ──────────────────────────────────────────────────────────────
        lines.append(
            f"# Genesis {review.genesis} Sprint {review.sprint} — Engineering Review"
        )
        lines.append("")

        # ── Status ─────────────────────────────────────────────────────────────
        lines.append("## Status")
        lines.append(
            f"{review.status.value.upper()} | Completed: {review.completed_at}"
        )
        lines.append("")

        # ── Commits ────────────────────────────────────────────────────────────
        lines.append("## Commits")
        if review.commits:
            for c in review.commits:
                lines.append(f"- {c}")
        else:
            lines.append("- *(none recorded)*")
        lines.append("")

        # ── Files Added ────────────────────────────────────────────────────────
        lines.append("## Files Added")
        if review.files_added:
            for f in review.files_added:
                lines.append(f"- {f}")
        else:
            lines.append("- *(none)*")
        lines.append("")

        # ── Files Modified ─────────────────────────────────────────────────────
        lines.append("## Files Modified")
        if review.files_modified:
            for f in review.files_modified:
                lines.append(f"- {f}")
        else:
            lines.append("- *(none)*")
        lines.append("")

        # ── Architecture Decisions ─────────────────────────────────────────────
        lines.append("## Architecture Decisions")
        if review.architecture_decisions:
            for ad in review.architecture_decisions:
                lines.append(f"### {ad.decision}")
                lines.append(f"**Rationale:** {ad.rationale}")
                alts = ", ".join(ad.alternatives) if ad.alternatives else "None"
                lines.append(f"**Alternatives considered:** {alts}")
                lines.append("")
        else:
            lines.append("*(none recorded)*")
            lines.append("")

        # ── Test Results ───────────────────────────────────────────────────────
        tr = review.test_results
        lines.append("## Test Results")
        lines.append(
            f"✅ Passed: {tr.passed} | ⏭ Skipped: {tr.skipped} | "
            f"❌ Failed: {tr.failed}"
        )
        if tr.warnings:
            lines.append(f"⚠️ Warnings: {tr.warnings}")
        lines.append("")

        # ── Desktop Validation ─────────────────────────────────────────────────
        dv = review.desktop_validation
        lines.append("## Desktop Validation")
        lines.append(f"**Status:** {dv.status}")
        lines.append("**Scenarios:**")
        if dv.scenarios:
            for s in dv.scenarios:
                lines.append(f"- {s}")
        else:
            lines.append("- *(none recorded)*")
        if dv.notes:
            lines.append(f"**Notes:** {dv.notes}")
        lines.append("")

        # ── Technical Debt ─────────────────────────────────────────────────────
        lines.append("## Technical Debt")
        if review.technical_debt:
            for item in review.technical_debt:
                lines.append(f"- {item}")
        else:
            lines.append("None identified.")
        lines.append("")

        # ── Risks ──────────────────────────────────────────────────────────────
        lines.append("## Risks")
        if review.risks:
            for item in review.risks:
                lines.append(f"- {item}")
        else:
            lines.append("None identified.")
        lines.append("")

        # ── Future Improvements ────────────────────────────────────────────────
        lines.append("## Future Improvements")
        if improv:
            for fi in improv:
                lines.append(
                    f"- [{fi.priority}] **{fi.title}** — {fi.description}"
                )
        else:
            lines.append("*(none deferred)*")
        lines.append("")

        # ── R&D Evidence Summary ───────────────────────────────────────────────
        lines.append("## R&D Evidence Summary")
        lines.append(f"**Problem:** {rd.technical_problem}")
        lines.append(f"**Uncertainty:** {rd.technical_uncertainty}")
        lines.append(f"**Hypothesis:** {rd.hypothesis}")
        lines.append(f"**Approach:** {rd.approach}")
        if rd.experiments:
            lines.append("**Experiments:**")
            for exp in rd.experiments:
                lines.append(f"- {exp}")
        lines.append(f"**Results:** {rd.results}")
        lines.append(f"**Validation:** {rd.validation}")
        if rd.remaining_unknowns:
            lines.append("**Remaining Unknowns:**")
            for u in rd.remaining_unknowns:
                lines.append(f"- {u}")
        lines.append("")

        # ── Recommendation ─────────────────────────────────────────────────────
        lines.append("## Recommendation")
        lines.append(f"**{review.recommendation.value}**")
        lines.append(review.recommendation_reason)
        lines.append("")

        return "\n".join(lines)
