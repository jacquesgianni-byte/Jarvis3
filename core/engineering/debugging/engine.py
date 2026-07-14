"""
Failure Correlation Engine (Genesis-017 Sprint 004)

Deterministic correlation of the current failure against a history
of previously observed failures.

Responsibility: correlate evidence → produce one CorrelationRecord.
    * Compare current failure against failure history.
    * Detect shared files, modules, exceptions, root causes, commits.
    * Identify repeated patterns.
    * Return an immutable CorrelationRecord.

Constitutional constraints — this module MUST NEVER:
    * Suggest fixes or repairs.
    * Generate code.
    * Modify files.
    * Call AI or LLM providers.
    * Guess when evidence is absent → UNKNOWN, confidence=0.0.
    * Execute any command.

Design philosophy:
    A senior engineer asks:
        "Have we seen this before?"
        "What changed?"
        "Did this start after a recent commit?"
        "Is this isolated or systemic?"

    This engine answers those questions from observable evidence alone.

Pipeline position:
    FailureEvidence + RootCause + FailureType + history
    → FailureCorrelationEngine
    → CorrelationRecord
    → DebugReport
"""

import logging
import re
from core.engineering.debugging.models import FailureEvidence, FailureType
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory
from core.engineering.debugging.correlation import CorrelationRecord, CorrelationType

logger = logging.getLogger(__name__)

# Minimum number of shared items to claim a correlation
_MIN_SHARED_FILES   = 1
_MIN_SHARED_MODULES = 1

# Confidence levels by correlation strength
_CONFIDENCE = {
    CorrelationType.REPEATED_FAILURE: 0.97,
    CorrelationType.SAME_COMMIT:      0.95,
    CorrelationType.SAME_ROOT_CAUSE:  0.90,
    CorrelationType.SAME_EXCEPTION:   0.88,
    CorrelationType.SAME_FILE:        0.85,
    CorrelationType.SAME_MODULE:      0.80,
}


class FailureRecord:
    """
    Lightweight snapshot of a past failure for correlation input.

    Not a dataclass — callers build these to represent history entries.
    All fields are optional; omit what is unknown.
    """

    def __init__(
        self,
        failure_type: FailureType = FailureType.UNKNOWN,
        root_cause_category: RootCauseCategory = RootCauseCategory.UNKNOWN,
        error_type: str = "",
        failing_files: tuple = (),
        commit: str = "",
        timestamp: str = "",
        description: str = "",
    ):
        self.failure_type        = failure_type
        self.root_cause_category = root_cause_category
        self.error_type          = error_type
        self.failing_files       = tuple(failing_files)
        self.commit              = commit
        self.timestamp           = timestamp
        self.description         = description


class FailureCorrelationEngine:
    """
    Correlates the current failure against a history of past failures.

    Read-only. No files modified. No AI calls. No fix suggestions.
    UNKNOWN is returned honestly when no correlation is found.
    """

    def correlate(
        self,
        evidence: FailureEvidence,
        root_cause: RootCause,
        failure_type: FailureType,
        history: list[FailureRecord] | None = None,
    ) -> CorrelationRecord:
        """
        Correlate the current failure against optional history.

        Args:
            evidence:     FailureEvidence from EvidenceExtractor.
            root_cause:   RootCause from RootCauseAnalyzer.
            failure_type: FailureType from FailureClassifier.
            history:      Optional list of past FailureRecords.
                          Pass None or [] when no history is available.

        Returns:
            Immutable CorrelationRecord. Never raises.
            Returns UNKNOWN when no history or no correlation found.
        """
        if not history:
            return self._no_correlation("No failure history available for comparison.")

        # Not a failure — nothing to correlate
        if evidence.exit_code == 0:
            return self._no_correlation("Process completed successfully — no failure to correlate.")

        # Run correlation checks in priority order (strongest first)
        checks = [
            self._check_repeated_failure,
            self._check_same_commit,
            self._check_same_root_cause,
            self._check_same_exception,
            self._check_same_file,
            self._check_same_module,
        ]

        for check in checks:
            result = check(evidence, root_cause, failure_type, history)
            if result is not None:
                logger.info(
                    "FailureCorrelationEngine: %s (%.0f%%)",
                    result.correlation_type.value,
                    result.confidence * 100,
                )
                return result

        return self._no_correlation(
            "No significant correlation detected with previous failures."
        )

    # ------------------------------------------------------------------
    # Correlation checks — each returns CorrelationRecord or None
    # ------------------------------------------------------------------

    def _check_repeated_failure(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect repeated failures with same type and root cause."""
        matches = [
            h for h in history
            if h.failure_type == failure_type
            and h.root_cause_category == root_cause.category
            and root_cause.category != RootCauseCategory.UNKNOWN
        ]
        if len(matches) >= 1:
            descriptions = tuple(
                h.description or f"{h.failure_type.value} / {h.root_cause_category.value}"
                for h in matches
            )
            timeline = self._build_timeline(matches, evidence)
            return CorrelationRecord(
                correlation_type=CorrelationType.REPEATED_FAILURE,
                confidence=_CONFIDENCE[CorrelationType.REPEATED_FAILURE],
                description=(
                    f"This {root_cause.category.value} failure has occurred "
                    f"{len(matches) + 1} time(s) — it is a recurring pattern."
                ),
                related_failures=descriptions,
                related_files=self._shared_files(evidence, matches),
                related_modules=self._shared_modules(evidence, matches),
                related_commits=self._commits(matches),
                timeline=timeline,
            )
        return None

    def _check_same_commit(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect failures sharing a commit reference in diagnostics."""
        current_commits = self._extract_commits(evidence)
        if not current_commits:
            return None

        matches = [
            h for h in history
            if h.commit and h.commit in current_commits
        ]
        if matches:
            return CorrelationRecord(
                correlation_type=CorrelationType.SAME_COMMIT,
                confidence=_CONFIDENCE[CorrelationType.SAME_COMMIT],
                description=(
                    f"This failure shares commit reference(s) "
                    f"{', '.join(current_commits)} with {len(matches)} "
                    f"previous failure(s)."
                ),
                related_failures=tuple(
                    h.description for h in matches if h.description
                ),
                related_files=self._shared_files(evidence, matches),
                related_modules=self._shared_modules(evidence, matches),
                related_commits=tuple(current_commits),
                timeline=self._build_timeline(matches, evidence),
            )
        return None

    def _check_same_root_cause(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect failures sharing the same root cause category."""
        if root_cause.category == RootCauseCategory.UNKNOWN:
            return None
        matches = [
            h for h in history
            if h.root_cause_category == root_cause.category
        ]
        if matches:
            return CorrelationRecord(
                correlation_type=CorrelationType.SAME_ROOT_CAUSE,
                confidence=_CONFIDENCE[CorrelationType.SAME_ROOT_CAUSE],
                description=(
                    f"{len(matches) + 1} failure(s) share the root cause: "
                    f"{root_cause.category.value}."
                ),
                related_failures=tuple(
                    h.description for h in matches if h.description
                ),
                related_files=self._shared_files(evidence, matches),
                related_modules=self._shared_modules(evidence, matches),
                related_commits=self._commits(matches),
                timeline=self._build_timeline(matches, evidence),
            )
        return None

    def _check_same_exception(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect failures sharing the same exception type."""
        if not evidence.error_type:
            return None
        matches = [
            h for h in history
            if h.error_type == evidence.error_type
        ]
        if matches:
            return CorrelationRecord(
                correlation_type=CorrelationType.SAME_EXCEPTION,
                confidence=_CONFIDENCE[CorrelationType.SAME_EXCEPTION],
                description=(
                    f"{evidence.error_type} has appeared in "
                    f"{len(matches) + 1} failure(s)."
                ),
                related_failures=tuple(
                    h.description for h in matches if h.description
                ),
                related_files=self._shared_files(evidence, matches),
                related_modules=self._shared_modules(evidence, matches),
                related_commits=self._commits(matches),
                timeline=self._build_timeline(matches, evidence),
            )
        return None

    def _check_same_file(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect failures affecting the same source files."""
        if not evidence.failing_files:
            return None
        current = set(evidence.failing_files)
        matches = [
            h for h in history
            if current & set(h.failing_files)
        ]
        if matches:
            shared = tuple(sorted(
                f for f in current
                if any(f in set(h.failing_files) for h in matches)
            ))
            return CorrelationRecord(
                correlation_type=CorrelationType.SAME_FILE,
                confidence=_CONFIDENCE[CorrelationType.SAME_FILE],
                description=(
                    f"File(s) {', '.join(shared)} appeared in "
                    f"{len(matches) + 1} failure(s)."
                ),
                related_failures=tuple(
                    h.description for h in matches if h.description
                ),
                related_files=shared,
                related_modules=self._shared_modules(evidence, matches),
                related_commits=self._commits(matches),
                timeline=self._build_timeline(matches, evidence),
            )
        return None

    def _check_same_module(
        self, evidence, root_cause, failure_type, history
    ) -> CorrelationRecord | None:
        """Detect failures affecting the same Python modules."""
        current_modules = self._modules_from_files(evidence.failing_files)
        if not current_modules:
            return None
        matches = [
            h for h in history
            if current_modules & self._modules_from_files(h.failing_files)
        ]
        if matches:
            shared = tuple(sorted(
                current_modules &
                set().union(*(self._modules_from_files(h.failing_files) for h in matches))
            ))
            return CorrelationRecord(
                correlation_type=CorrelationType.SAME_MODULE,
                confidence=_CONFIDENCE[CorrelationType.SAME_MODULE],
                description=(
                    f"Module(s) {', '.join(shared)} affected in "
                    f"{len(matches) + 1} failure(s)."
                ),
                related_failures=tuple(
                    h.description for h in matches if h.description
                ),
                related_files=self._shared_files(evidence, matches),
                related_modules=shared,
                related_commits=self._commits(matches),
                timeline=self._build_timeline(matches, evidence),
            )
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _modules_from_files(self, files: tuple) -> set[str]:
        """Extract module names (top-level package) from file paths."""
        modules: set[str] = set()
        for f in files:
            # core/skills/memory.py → core.skills
            parts = f.replace("\\", "/").split("/")
            if len(parts) >= 2:
                modules.add(".".join(parts[:-1]))
        return modules

    def _shared_files(self, evidence, matches) -> tuple:
        current = set(evidence.failing_files)
        shared = current & set().union(*(set(h.failing_files) for h in matches))
        return tuple(sorted(shared))

    def _shared_modules(self, evidence, matches) -> tuple:
        current = self._modules_from_files(evidence.failing_files)
        past = set().union(*(
            self._modules_from_files(h.failing_files) for h in matches
        ))
        return tuple(sorted(current & past))

    def _commits(self, matches) -> tuple:
        seen: set[str] = set()
        result = []
        for h in matches:
            if h.commit and h.commit not in seen:
                seen.add(h.commit)
                result.append(h.commit)
        return tuple(result)

    def _extract_commits(self, evidence: FailureEvidence) -> list[str]:
        """Extract git commit hashes from stderr/stdout."""
        combined = "\n".join(list(evidence.stderr) + list(evidence.stdout))
        return re.findall(r'\b([0-9a-f]{7,40})\b', combined)

    def _build_timeline(self, matches, evidence) -> tuple:
        """Build a chronological timeline of related failures."""
        entries = []
        for h in matches:
            if h.timestamp:
                entries.append(f"{h.timestamp}: {h.description or h.failure_type.value}")
        if evidence.timestamp:
            entries.append(f"{evidence.timestamp}: Current failure")
        return tuple(entries)

    def _no_correlation(self, description: str) -> CorrelationRecord:
        return CorrelationRecord(
            correlation_type=CorrelationType.UNKNOWN,
            confidence=0.0,
            description=description,
            related_failures=(),
            related_files=(),
            related_modules=(),
            related_commits=(),
            timeline=(),
        )