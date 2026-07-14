"""
Root Cause Analyzer (Genesis-017 Sprint 003)

Deterministic root cause analysis from structured failure evidence.

Responsibility: analyse evidence → produce one RootCause.
    * Inspect FailureType from FailureClassifier.
    * Inspect error_type from EvidenceExtractor.
    * Inspect diagnostics, stack trace, failing files.
    * Map observations to a RootCauseCategory.
    * Return an immutable RootCause.

Constitutional constraints — this module MUST NEVER:
    * Suggest fixes or repairs.
    * Generate code.
    * Modify files.
    * Call AI or LLM providers.
    * Guess when evidence is absent → UNKNOWN, confidence=0.0.
    * Execute any command.

Design philosophy:
    "Why did this happen?" — answered from evidence alone.

    The analyser reasons from what it can observe.
    It does not invent explanations.
    UNKNOWN is a valid and honest answer.

Pipeline position:
    FailureEvidence + FailureType
    → RootCauseAnalyzer
    → RootCause
    → DebugReport
"""

import re
import logging
from core.engineering.debugging.models import FailureType, FailureEvidence
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deterministic mapping rules — ordered by specificity.
# Each rule: (condition_fn, category, description_template, confidence)
# The first matching rule wins.
# ---------------------------------------------------------------------------

# Error type patterns → root cause category
_ERROR_TYPE_RULES: list[tuple[str, RootCauseCategory, str, float]] = [
    # Syntax / compile errors
    ("SyntaxError",           RootCauseCategory.SYNTAX_ERROR,
     "A syntax error prevents Python from parsing the source file.",     0.97),
    ("IndentationError",      RootCauseCategory.SYNTAX_ERROR,
     "An indentation error prevents Python from parsing the source.",    0.97),
    ("TabError",              RootCauseCategory.SYNTAX_ERROR,
     "Mixed tabs and spaces prevent Python from parsing the source.",    0.97),

    # Import / module errors
    ("ModuleNotFoundError",   RootCauseCategory.MISSING_MODULE,
     "A required Python module could not be found on sys.path.",         0.97),
    ("ImportError",           RootCauseCategory.IMPORT_DEPENDENCY,
     "A module was found but could not be imported successfully.",       0.92),

    # File / permission errors
    ("FileNotFoundError",     RootCauseCategory.MISSING_FILE,
     "A required file or path does not exist.",                          0.95),
    ("PermissionError",       RootCauseCategory.PERMISSION,
     "Insufficient permissions to access a file or resource.",           0.95),

    # Timeout
    ("TimeoutExpired",        RootCauseCategory.TIMEOUT,
     "The process exceeded the configured time limit.",                  1.00),
    ("TimeoutError",          RootCauseCategory.TIMEOUT,
     "The process exceeded the configured time limit.",                  1.00),

    # Assertion / test failures
    ("AssertionError",        RootCauseCategory.TEST_REGRESSION,
     "A test assertion failed — expected behaviour has changed.",        0.90),

    # API / attribute errors
    ("AttributeError",        RootCauseCategory.INVALID_API,
     "An object does not have the expected attribute or method.",        0.85),
    ("TypeError",             RootCauseCategory.INVALID_API,
     "A function was called with incorrect argument types.",             0.85),

    # Configuration errors
    ("KeyError",              RootCauseCategory.CONFIGURATION,
     "A required configuration key is missing.",                        0.87),
    ("ValueError",            RootCauseCategory.CONFIGURATION,
     "A configuration value is invalid or out of expected range.",       0.80),
]

# FailureType → fallback category when error_type yields no match
_FAILURE_TYPE_FALLBACKS: dict[FailureType, tuple[RootCauseCategory, str, float]] = {
    FailureType.COMPILE:       (RootCauseCategory.SYNTAX_ERROR,
                                "Compilation failed — likely a syntax or indentation error.", 0.80),
    FailureType.IMPORT:        (RootCauseCategory.IMPORT_DEPENDENCY,
                                "An import failed — a module or dependency is unavailable.", 0.80),
    FailureType.TEST:          (RootCauseCategory.TEST_REGRESSION,
                                "One or more tests failed — a regression may have been introduced.", 0.80),
    FailureType.TIMEOUT:       (RootCauseCategory.TIMEOUT,
                                "The process timed out before completing.", 1.00),
    FailureType.CONFIGURATION: (RootCauseCategory.CONFIGURATION,
                                "A configuration setting is missing or invalid.", 0.80),
}

# Diagnostic line patterns → contributing factor descriptions
_DIAGNOSTIC_PATTERNS: list[tuple[str, str]] = [
    (r"line\s+(\d+)",            "Error occurs at line {0}"),
    (r"No module named '([^']+)'", "Missing module: {0}"),
    (r"cannot import name '([^']+)'", "Cannot import: {0}"),
    (r"File \"([^\"]+)\"",        "In file: {0}"),
]


class RootCauseAnalyzer:
    """
    Deterministic root cause analyser.

    Analyses FailureEvidence and FailureType to produce a single
    immutable RootCause. All mappings are explicit — no AI, no
    guessing, no randomness.
    """

    def analyse(
        self,
        evidence: FailureEvidence,
        failure_type: FailureType,
    ) -> RootCause:
        """
        Determine the most likely root cause from observed evidence.

        Args:
            evidence:     FailureEvidence from EvidenceExtractor.
            failure_type: FailureType from FailureClassifier.

        Returns:
            Immutable RootCause. Never raises.
            Returns UNKNOWN with confidence=0.0 when evidence
            is insufficient for a determination.
        """
        # Not a failure — no root cause to determine
        if evidence.exit_code == 0:
            return self._unknown("Process completed successfully — no failure to analyse.")

        # Step 1: try error_type first (highest specificity)
        if evidence.error_type:
            result = self._from_error_type(evidence)
            if result is not None:
                logger.info(
                    "RootCauseAnalyzer: determined via error_type=%r → %s (%.0f%%)",
                    evidence.error_type, result.category.value, result.confidence * 100,
                )
                return result

        # Step 2: fall back to FailureType (lower specificity)
        if failure_type in _FAILURE_TYPE_FALLBACKS:
            category, description, confidence = _FAILURE_TYPE_FALLBACKS[failure_type]
            supporting = self._collect_supporting(evidence)
            factors = self._extract_factors(evidence)
            logger.info(
                "RootCauseAnalyzer: determined via failure_type=%s → %s (%.0f%%)",
                failure_type.value, category.value, confidence * 100,
            )
            return RootCause(
                category=category,
                description=description,
                confidence=confidence,
                supporting_evidence=tuple(supporting),
                contributing_factors=tuple(factors),
            )

        # Step 3: honest UNKNOWN
        logger.info("RootCauseAnalyzer: insufficient evidence → UNKNOWN")
        return self._unknown(
            f"Insufficient evidence to determine root cause "
            f"(exit_code={evidence.exit_code})."
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _from_error_type(self, evidence: FailureEvidence) -> RootCause | None:
        """Match error_type against the rule table."""
        error = evidence.error_type

        for pattern, category, description, confidence in _ERROR_TYPE_RULES:
            if pattern in error:
                supporting = self._collect_supporting(evidence)
                factors    = self._extract_factors(evidence)

                # Enrich description with specific module name if available
                if category == RootCauseCategory.MISSING_MODULE:
                    module = self._extract_module_name(evidence)
                    if module:
                        description = (
                            f"Module '{module}' could not be found on sys.path."
                        )
                elif category == RootCauseCategory.SYNTAX_ERROR:
                    if evidence.failing_files:
                        description = (
                            f"Syntax error in {evidence.failing_files[0]}."
                        )
                elif category == RootCauseCategory.MISSING_FILE:
                    missing = self._extract_missing_path(evidence)
                    if missing:
                        description = f"Required file not found: {missing}"

                return RootCause(
                    category=category,
                    description=description,
                    confidence=confidence,
                    supporting_evidence=tuple(supporting),
                    contributing_factors=tuple(factors),
                )
        return None

    def _collect_supporting(self, evidence: FailureEvidence) -> list[str]:
        """Collect the most relevant evidence lines to support the conclusion."""
        lines: list[str] = []

        # Diagnostics are the most direct support
        lines.extend(evidence.diagnostics[:5])

        # Stack trace frames
        lines.extend(evidence.stack_trace[:3])

        # Stderr tail if no diagnostics
        if not lines:
            lines.extend(list(evidence.stderr)[-5:])

        # Deduplicate, preserve order
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            if line and line not in seen:
                seen.add(line)
                result.append(line)

        return result[:10]

    def _extract_factors(self, evidence: FailureEvidence) -> list[str]:
        """Extract contributing factors from diagnostics and stack trace."""
        factors: list[str] = []
        combined = "\n".join(list(evidence.stderr) + list(evidence.stdout))

        for pattern, template in _DIAGNOSTIC_PATTERNS:
            m = re.search(pattern, combined, re.IGNORECASE)
            if m:
                try:
                    factor = template.format(*m.groups())
                    if factor not in factors:
                        factors.append(factor)
                except IndexError:
                    pass

        if evidence.failing_files:
            for f in evidence.failing_files[:3]:
                factor = f"Affected file: {f}"
                if factor not in factors:
                    factors.append(factor)

        if evidence.line_numbers:
            nums = ", ".join(str(n) for n in evidence.line_numbers[:3])
            factors.append(f"Line(s) involved: {nums}")

        return factors[:8]

    def _extract_module_name(self, evidence: FailureEvidence) -> str:
        """Extract the missing module name from stderr."""
        combined = "\n".join(evidence.stderr)
        m = re.search(r"No module named '([^']+)'", combined)
        return m.group(1) if m else ""

    def _extract_missing_path(self, evidence: FailureEvidence) -> str:
        """Extract a missing file path from stderr."""
        combined = "\n".join(evidence.stderr)
        m = re.search(r"No such file or directory: '([^']+)'", combined)
        return m.group(1) if m else ""

    def _unknown(self, description: str) -> RootCause:
        return RootCause(
            category=RootCauseCategory.UNKNOWN,
            description=description,
            confidence=0.0,
            supporting_evidence=(),
            contributing_factors=(),
        )