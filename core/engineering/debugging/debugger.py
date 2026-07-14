"""
Engineering Debugger (Genesis-017 Sprint 001)

Analyses engineering failures by inspecting process output,
classifying the failure type, and collecting evidence into
an immutable DebugReport.

Constitutional constraints — this module MUST NEVER:
    * Modify any file.
    * Generate or apply code fixes.
    * Execute any command.
    * Make Git write operations.
    * Call any AI or LLM.
    * Guess when evidence is insufficient.

Design philosophy:
    "What happened?" — not — "How should I fix it?"

    The debugger behaves like a forensic investigator, not a programmer.
    It collects evidence and classifies failures. Autonomous repair
    capabilities belong to future milestones that will earn authority
    by building on trustworthy diagnostic evidence.

Pipeline position:
    EngineeringTestResult → EngineeringDebugger → DebugReport
    → (future) Repair Planner → Chief Approval → Execution
"""

import logging
from datetime import datetime, timezone

from core.engineering.debugging.models import DebugReport, FailureEvidence, FailureType
from core.engineering.debugging.extractor import EvidenceExtractor
from core.engineering.debugging.analyzer import RootCauseAnalyzer
from core.engineering.debugging.engine import FailureCorrelationEngine, FailureRecord
from core.engineering.debugging.classifier import FailureClassifier

logger = logging.getLogger(__name__)

# Maximum characters stored from stdout/stderr in the report
_MAX_OUTPUT = 3000


class EngineeringDebugger:
    """
    Forensic analyser for engineering failures.

    Accepts raw process output and produces an immutable DebugReport.
    Orchestrates: EvidenceExtractor → FailureClassifier → RootCauseAnalyzer.
    Read-only — no files created, no code modified, no commands run.
    """

    def __init__(
        self,
        classifier: FailureClassifier | None = None,
        extractor: EvidenceExtractor | None = None,
        analyzer: RootCauseAnalyzer | None = None,
        history: list | None = None,
    ):
        self._classifier = classifier or FailureClassifier()
        self._extractor  = extractor  or EvidenceExtractor()
        self._analyzer   = analyzer   or RootCauseAnalyzer()
        self._correlator = FailureCorrelationEngine()
        self._history: list[FailureRecord] = list(history) if history else []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        command: str,
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> DebugReport:
        """
        Analyse a process failure and return an immutable DebugReport.

        Args:
            command:   The command string that was executed.
            exit_code: Process exit code (non-zero indicates failure).
            stdout:    Captured standard output.
            stderr:    Captured standard error.

        Returns:
            DebugReport — immutable, timestamped, ready for review.
            Never raises.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Classify the failure
        failure_type, confidence, clues = self._classifier.classify(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
        )

        # Build the summary
        summary = self._build_summary(
            failure_type, exit_code, tuple(clues), stderr
        )

        # Extract structured forensic evidence (Sprint 002)
        extracted = self._extractor.extract(stdout, stderr)

        # Build the immutable evidence container
        raw_evidence = FailureEvidence(
            command=command,
            exit_code=exit_code,
            stdout=tuple(stdout.strip()[:_MAX_OUTPUT].splitlines()),
            stderr=tuple(stderr.strip()[:_MAX_OUTPUT].splitlines()),
            timestamp=timestamp,
            stack_trace=extracted["stack_trace"],
            failing_files=extracted["failing_files"],
            line_numbers=extracted["line_numbers"],
            error_type=extracted["error_type"],
            diagnostics=extracted["diagnostics"],
        )

        # Determine root cause from evidence (Sprint 003)
        root_cause = self._analyzer.analyse(raw_evidence, failure_type)

        # Correlate against failure history (Sprint 004)
        correlation = self._correlator.correlate(
            evidence=raw_evidence,
            root_cause=root_cause,
            failure_type=failure_type,
            history=self._history,
        )

        report = DebugReport(
            failure_type=failure_type,
            summary=summary,
            confidence=confidence,
            clues=tuple(clues),
            evidence=raw_evidence,
            root_cause=root_cause,
            correlation=correlation,
        )

        logger.info(
            "EngineeringDebugger: analysed | type=%s | confidence=%.0f%% | "
            "command=%s",
            failure_type.value,
            confidence * 100,
            command[:60],
        )
        return report

    def analyse_step(self, step) -> DebugReport:
        """
        Convenience method: analyse a StepResult from the TestRunner.

        Args:
            step: A StepResult (from core.engineering.testing.models).

        Returns:
            DebugReport for the failed step.
        """
        return self.analyse(
            command=step.command,
            exit_code=0 if step.passed else 1,
            stdout=step.output or "",
            stderr=step.error or "",
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        failure_type: FailureType,
        exit_code: int,
        clues: tuple,
        stderr: str,
    ) -> str:
        """Build a concise one-line summary of the failure."""
        if failure_type == FailureType.UNKNOWN:
            return (
                f"Process exited with code {exit_code}. "
                "Insufficient evidence to classify the failure."
            )

        if failure_type == FailureType.TIMEOUT:
            return "Process exceeded the configured time limit and was terminated."

        if failure_type == FailureType.COMPILE:
            # Try to extract the specific syntax error line
            for line in clues:
                if "SyntaxError" in line or "IndentationError" in line:
                    return f"Compile error: {line.strip()[:120]}"
            return "Compilation failed — syntax or indentation error detected."

        if failure_type == FailureType.IMPORT:
            for line in clues:
                if "No module named" in line or "ModuleNotFoundError" in line:
                    return f"Import error: {line.strip()[:120]}"
            return "Import failed — a required module could not be found."

        if failure_type == FailureType.TEST:
            # Count failures if visible
            for line in clues:
                if "failed" in line.lower() and any(c.isdigit() for c in line):
                    return f"Test failure: {line.strip()[:120]}"
            return "One or more tests failed."

        if failure_type == FailureType.CONFIGURATION:
            return (
                "Configuration error — a required setting, key, or file "
                "is missing or invalid."
            )

        return f"Failure classified as {failure_type.value} (exit code {exit_code})."