"""
Repair Planner (Genesis-017 Sprint 006)

Produces a deterministic RepairPlan by consuming the full output of
the engineering investigation pipeline.

Responsibility: evidence + root cause + correlation + recommendations
               → one structured RepairPlan.

Constitutional constraints — this module MUST NEVER:
    * Edit files or generate code.
    * Apply patches or execute repairs.
    * Call AI or LLM providers.
    * Modify any repository.
    * Execute any plan step.

Design philosophy:
    A RepairPlan resembles what a senior engineer would prepare
    before touching production code:
        1. Understand the failure.
        2. Identify the affected area.
        3. Plan the fix.
        4. Validate the fix.
        5. Await approval.

    The planner reasons from evidence. It does not invent steps.
    Every step is justified by prior investigation findings.

Pipeline position:
    FailureEvidence + RootCause + CorrelationRecord + Recommendations
    → RepairPlanner
    → RepairPlan
    → DebugReport

    Execution belongs to a future Genesis.
"""

import logging
from core.engineering.debugging.models import FailureEvidence, FailureType
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory
from core.engineering.debugging.correlation import CorrelationRecord, CorrelationType
from core.engineering.debugging.recommendation import (
    Recommendation, RecommendationCategory, RecommendationPriority
)
from core.engineering.debugging.repair import (
    RepairPlan, RepairStep, RepairRisk, RepairEffort
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validation steps always appended to any actionable repair plan
# ---------------------------------------------------------------------------

_BASE_VALIDATION = (
    "Run: python -m compileall core/ (confirm no compile errors)",
    "Run: python -m pytest tests/ (confirm no regressions)",
    "Review DebugReport and confirm failure no longer reproduces",
)

# ---------------------------------------------------------------------------
# Risk mapping — root cause + correlation → risk level
# ---------------------------------------------------------------------------

_BASE_RISK: dict[RootCauseCategory, RepairRisk] = {
    RootCauseCategory.SYNTAX_ERROR:      RepairRisk.LOW,
    RootCauseCategory.MISSING_MODULE:    RepairRisk.MEDIUM,
    RootCauseCategory.IMPORT_DEPENDENCY: RepairRisk.MEDIUM,
    RootCauseCategory.CONFIGURATION:     RepairRisk.HIGH,
    RootCauseCategory.TEST_REGRESSION:   RepairRisk.MEDIUM,
    RootCauseCategory.INVALID_API:       RepairRisk.HIGH,
    RootCauseCategory.MISSING_FILE:      RepairRisk.MEDIUM,
    RootCauseCategory.PERMISSION:        RepairRisk.MEDIUM,
    RootCauseCategory.TIMEOUT:           RepairRisk.MEDIUM,
    RootCauseCategory.UNKNOWN:           RepairRisk.HIGH,
}

# Correlation escalates risk
_CORRELATION_RISK_ESCALATION: dict[CorrelationType, RepairRisk] = {
    CorrelationType.REPEATED_FAILURE: RepairRisk.CRITICAL,
    CorrelationType.SAME_COMMIT:      RepairRisk.HIGH,
    CorrelationType.SAME_ROOT_CAUSE:  RepairRisk.HIGH,
}


class RepairPlanner:
    """
    Deterministic repair planner.

    Consumes investigation results to produce one RepairPlan.
    Read-only — no files modified, no code generated, no plans executed.
    """

    def plan(
        self,
        evidence: FailureEvidence,
        failure_type: FailureType,
        root_cause: RootCause,
        correlation: CorrelationRecord,
        recommendations: tuple,
    ) -> RepairPlan:
        """
        Produce a deterministic RepairPlan from investigation results.

        Args:
            evidence:         FailureEvidence from EvidenceExtractor.
            failure_type:     FailureType from FailureClassifier.
            root_cause:       RootCause from RootCauseAnalyzer.
            correlation:      CorrelationRecord from FailureCorrelationEngine.
            recommendations:  Tuple of Recommendation from RecommendationEngine.

        Returns:
            Immutable RepairPlan. Never raises.
            Returns an empty plan when evidence is insufficient.
        """
        # No failure — no repair plan needed
        if evidence.exit_code == 0:
            return self._empty_plan("Process completed successfully — no repair needed.")

        # Build steps from root cause + correlation + recommendations
        steps = self._build_steps(
            evidence, root_cause, correlation, recommendations
        )

        if not steps:
            return self._empty_plan(
                "Insufficient evidence to produce a deterministic repair plan."
            )

        # Estimate risk and effort
        risk    = self._estimate_risk(root_cause, correlation)
        effort  = self._estimate_effort(steps, correlation)

        # Build title and summary
        title   = self._build_title(root_cause, failure_type)
        summary = self._build_summary(
            root_cause, correlation, recommendations, risk
        )

        # Confidence derived from root cause + recommendation confidence
        confidence = self._estimate_confidence(root_cause, recommendations)

        # Supporting recommendation titles
        rec_titles = tuple(r.title for r in recommendations)

        plan = RepairPlan(
            title=title,
            summary=summary,
            confidence=confidence,
            steps=tuple(steps),
            validation_steps=_BASE_VALIDATION,
            estimated_risk=risk,
            estimated_effort=effort,
            supporting_recommendations=rec_titles,
        )

        logger.info(
            "RepairPlanner: plan produced | steps=%d | risk=%s | effort=%s",
            len(steps), risk.value, effort.value,
        )
        return plan

    # ------------------------------------------------------------------
    # Step builders
    # ------------------------------------------------------------------

    def _build_steps(
        self,
        evidence: FailureEvidence,
        root_cause: RootCause,
        correlation: CorrelationRecord,
        recommendations: tuple,
    ) -> list[RepairStep]:
        """Build ordered repair steps from investigation results."""
        steps: list[RepairStep] = []
        order = 1

        # Step 1: Investigate commit history if correlation detected
        if (correlation.is_correlated and
                correlation.correlation_type in (
                    CorrelationType.SAME_COMMIT,
                    CorrelationType.REPEATED_FAILURE,
                )):
            commits = (f" (commits: {', '.join(correlation.related_commits)})"
                       if correlation.related_commits else "")
            steps.append(RepairStep(
                order=order,
                title="Review recent commit history",
                description=(
                    f"Examine recent commits for changes that may have "
                    f"introduced the failure{commits}. Focus on files "
                    f"affected: {', '.join(correlation.related_files) or 'see evidence'}."
                ),
                depends_on=(),
            ))
            order += 1

        # Step 2: Root-cause specific investigation step
        rc_step = self._root_cause_step(order, evidence, root_cause)
        if rc_step:
            steps.append(rc_step)
            order += 1

        # Step 3: Address the specific failure
        fix_step = self._fix_step(order, evidence, root_cause, steps)
        if fix_step:
            steps.append(fix_step)
            order += 1

        # Step 4: Additional steps from CRITICAL recommendations
        for rec in recommendations:
            if (rec.priority == RecommendationPriority.CRITICAL and
                    rec.category == RecommendationCategory.MONITOR_REPEATED_FAILURES
                    and order <= 4):
                steps.append(RepairStep(
                    order=order,
                    title="Document recurring failure pattern",
                    description=(
                        "Record this failure in the engineering log. "
                        "After repair, review whether a systemic fix is needed "
                        "to prevent recurrence."
                    ),
                    depends_on=tuple(range(1, order)),
                ))
                order += 1
                break

        # Final step: only add validation when substantive steps exist
        if order > 1:
            steps.append(RepairStep(
                order=order,
                title="Validate the repair",
                description=(
                    "Run the full validation sequence: "
                    "python -m compileall core/ && python -m pytest tests/. "
                    "Confirm the failure no longer reproduces before requesting "
                    "Chief approval."
                ),
                depends_on=tuple(range(1, order)),
            ))

        return steps

    def _root_cause_step(
        self,
        order: int,
        evidence: FailureEvidence,
        root_cause: RootCause,
    ) -> RepairStep | None:
        """Produce the investigation step for the root cause."""
        cat = root_cause.category

        file_hint = (f" in {evidence.failing_files[0]}"
                     if evidence.failing_files else "")
        line_hint = (f" at line {evidence.line_numbers[0]}"
                     if evidence.line_numbers else "")

        descriptions = {
            RootCauseCategory.SYNTAX_ERROR: (
                "Investigate syntax",
                f"Locate and review the syntax error{file_hint}{line_hint}. "
                f"Confirm the exact location using the evidence above."
            ),
            RootCauseCategory.MISSING_MODULE: (
                "Verify module availability",
                f"Confirm the required module is installed and accessible. "
                f"Check requirements.txt and the Python environment."
            ),
            RootCauseCategory.IMPORT_DEPENDENCY: (
                "Verify import paths",
                f"Confirm the import path is correct{file_hint}. "
                f"Check for circular imports or missing __init__.py files."
            ),
            RootCauseCategory.CONFIGURATION: (
                "Review configuration",
                "Check .env, Settings, and environment variables. "
                "Verify all required keys are present and correctly set."
            ),
            RootCauseCategory.TEST_REGRESSION: (
                "Analyse failing tests",
                f"Review test output to understand what assertion failed{file_hint}. "
                "Determine whether the code or the test expectation needs updating."
            ),
            RootCauseCategory.INVALID_API: (
                "Review API usage",
                f"Inspect the AttributeError or TypeError context{file_hint}{line_hint}. "
                "Confirm the object type and available attributes/methods."
            ),
            RootCauseCategory.MISSING_FILE: (
                "Locate missing file",
                "Confirm whether the file was deleted, renamed, or never created. "
                "Check git status for recent file changes."
            ),
            RootCauseCategory.TIMEOUT: (
                "Investigate timeout cause",
                "Determine whether the process is hanging or genuinely slow. "
                "Check for infinite loops, deadlocks, or network dependencies."
            ),
        }

        if cat not in descriptions:
            return None

        title, description = descriptions[cat]
        return RepairStep(
            order=order,
            title=title,
            description=description,
            depends_on=(),
        )

    def _fix_step(
        self,
        order: int,
        evidence: FailureEvidence,
        root_cause: RootCause,
        prior_steps: list[RepairStep],
    ) -> RepairStep | None:
        """Produce the corrective action step."""
        cat = root_cause.category
        prior = tuple(s.order for s in prior_steps)

        file_hint = (f" in {evidence.failing_files[0]}"
                     if evidence.failing_files else "")
        line_hint = (f" at line {evidence.line_numbers[0]}"
                     if evidence.line_numbers else "")

        fix_descriptions = {
            RootCauseCategory.SYNTAX_ERROR: (
                "Correct the syntax error",
                f"Apply the minimal change needed to fix the syntax{file_hint}"
                f"{line_hint}. Do not refactor beyond the immediate fix."
            ),
            RootCauseCategory.MISSING_MODULE: (
                "Install or restore the missing module",
                "Run pip install <module> or restore the missing dependency. "
                "Update requirements.txt to reflect the change."
            ),
            RootCauseCategory.IMPORT_DEPENDENCY: (
                "Fix the import path",
                f"Correct the import statement{file_hint}. "
                "Ensure the module is reachable from the project root."
            ),
            RootCauseCategory.CONFIGURATION: (
                "Update configuration",
                "Add the missing key to .env or Settings. "
                "Do not commit secrets — use environment variable references."
            ),
            RootCauseCategory.TEST_REGRESSION: (
                "Address the test failure",
                "If the behaviour changed intentionally, update the test. "
                "If unintentionally, restore the original behaviour."
            ),
            RootCauseCategory.INVALID_API: (
                "Fix the API usage",
                f"Correct the attribute or method call{file_hint}{line_hint}. "
                "Verify the object type before accessing attributes."
            ),
            RootCauseCategory.MISSING_FILE: (
                "Restore or create the missing file",
                "Recreate the file from version control or create it fresh. "
                "Confirm it is referenced correctly in all import paths."
            ),
            RootCauseCategory.TIMEOUT: (
                "Resolve the timeout condition",
                "Address the root cause of the slow/hanging process. "
                "Consider increasing the timeout only as a temporary measure."
            ),
        }

        if cat not in fix_descriptions:
            return None

        title, description = fix_descriptions[cat]
        return RepairStep(
            order=order,
            title=title,
            description=description,
            depends_on=prior,
        )

    # ------------------------------------------------------------------
    # Estimators
    # ------------------------------------------------------------------

    def _estimate_risk(
        self,
        root_cause: RootCause,
        correlation: CorrelationRecord,
    ) -> RepairRisk:
        base = _BASE_RISK.get(root_cause.category, RepairRisk.HIGH)

        # Escalate if correlation indicates systemic issue
        escalated = _CORRELATION_RISK_ESCALATION.get(
            correlation.correlation_type
        )
        if escalated:
            risk_order = [
                RepairRisk.LOW, RepairRisk.MEDIUM,
                RepairRisk.HIGH, RepairRisk.CRITICAL
            ]
            if risk_order.index(escalated) > risk_order.index(base):
                return escalated

        return base

    def _estimate_effort(
        self,
        steps: list[RepairStep],
        correlation: CorrelationRecord,
    ) -> RepairEffort:
        n = len(steps)
        if correlation.correlation_type == CorrelationType.REPEATED_FAILURE:
            # Systemic issues take more effort
            if n <= 3: return RepairEffort.MODERATE
            return RepairEffort.LARGE
        if n <= 2: return RepairEffort.MINOR
        if n <= 3: return RepairEffort.SMALL
        if n <= 4: return RepairEffort.MODERATE
        return RepairEffort.LARGE

    def _estimate_confidence(
        self,
        root_cause: RootCause,
        recommendations: tuple,
    ) -> float:
        base = root_cause.confidence
        if recommendations:
            avg_rec = sum(r.confidence for r in recommendations) / len(recommendations)
            return round((base + avg_rec) / 2, 2)
        return round(base, 2)

    def _build_title(
        self,
        root_cause: RootCause,
        failure_type: FailureType,
    ) -> str:
        if root_cause.category != RootCauseCategory.UNKNOWN:
            return f"Repair Plan: {root_cause.category.value}"
        return f"Repair Plan: {failure_type.value}"

    def _build_summary(
        self,
        root_cause: RootCause,
        correlation: CorrelationRecord,
        recommendations: tuple,
        risk: RepairRisk,
    ) -> str:
        parts = [
            f"Root cause: {root_cause.category.value}.",
        ]
        if correlation.is_correlated:
            parts.append(
                f"Correlation: {correlation.correlation_type.value} detected."
            )
        if recommendations:
            high = [r for r in recommendations
                    if r.priority in (RecommendationPriority.CRITICAL,
                                      RecommendationPriority.HIGH)]
            if high:
                parts.append(
                    f"Priority actions: {', '.join(r.title for r in high[:2])}."
                )
        parts.append(
            f"Estimated risk: {risk.value}. "
            "Awaiting Chief approval before execution."
        )
        return " ".join(parts)

    def _empty_plan(self, reason: str) -> RepairPlan:
        return RepairPlan(
            title="No Repair Plan",
            summary=reason,
            confidence=0.0,
            steps=(),
            validation_steps=(),
            estimated_risk=RepairRisk.LOW,
            estimated_effort=RepairEffort.MINOR,
            supporting_recommendations=(),
        )