"""
Failure Classifier (Genesis-017 Sprint 001)

Deterministic, pattern-based classification of engineering failures.

Constitutional constraints:
    * No AI or LLM calls.
    * No filesystem reads or writes.
    * No network calls.
    * Classification is purely based on observed output text and exit code.
    * When evidence is insufficient → FailureType.UNKNOWN, confidence=0.0.

Design philosophy:
    A classifier that admits uncertainty is more trustworthy than one
    that always produces an answer. Evidence before assumption.
"""

import re
from core.engineering.debugging.models import FailureType

# ---------------------------------------------------------------------------
# Pattern definitions — ordered by specificity.
# Each entry: (FailureType, confidence, list of regex patterns)
# First match wins. Patterns are checked against combined stdout+stderr.
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[FailureType, float, list[str]]] = [

    # Timeout — checked first, exit code alone is sufficient
    (FailureType.TIMEOUT, 1.0, [
        r"TimeoutExpired",
        r"timed out after",
        r"subprocess\.TimeoutExpired",
    ]),

    # Import errors — Python-specific, high confidence
    (FailureType.IMPORT, 0.95, [
        r"ModuleNotFoundError",
        r"ImportError",
        r"No module named",
        r"cannot import name",
    ]),

    # Compile errors — syntax and compilation failures
    (FailureType.COMPILE, 0.95, [
        r"SyntaxError",
        r"IndentationError",
        r"TabError",
        r"compileall.*error",
        r"invalid syntax",
        r"EOFError.*unexpected",
        r"ERROR.*compile",
    ]),

    # Test failures — pytest and unittest output patterns
    (FailureType.TEST, 0.90, [
        r"FAILED tests/",
        r"AssertionError",
        r"assert .* ==",
        r"\d+ failed",
        r"FAIL:",
        r"test.*FAILED",
        r"pytest.*error",
        r"ERROR collecting",
    ]),

    # Configuration errors — settings, env, missing keys
    (FailureType.CONFIGURATION, 0.85, [
        r"KeyError.*API",
        r"missing.*key",
        r"not configured",
        r"\.env",
        r"Settings.*error",
        r"configuration.*invalid",
        r"FileNotFoundError.*\.json",
        r"PermissionError",
    ]),
]

# Maximum evidence lines to extract
_MAX_EVIDENCE = 20
# Maximum characters from a single evidence line
_MAX_LINE = 200


class FailureClassifier:
    """
    Classifies engineering failures from process output.

    Deterministic — same inputs always produce the same output.
    No AI, no network, no filesystem access.
    """

    def classify(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> tuple[FailureType, float, tuple]:
        """
        Classify a failure from process output.

        Args:
            stdout:    Captured standard output.
            stderr:    Captured standard error.
            exit_code: Process exit code.

        Returns:
            (FailureType, confidence, evidence_lines)

        If exit_code is 0, returns (UNKNOWN, 0.0, ()) — not a failure.
        If no pattern matches, returns (UNKNOWN, 0.0, evidence).
        """
        # Not a failure
        if exit_code == 0:
            return FailureType.UNKNOWN, 0.0, ()

        combined = (stdout + "\n" + stderr).strip()

        # Timeout: check exit code 124 (Unix timeout) in addition to patterns
        if exit_code == 124:
            evidence = self._extract_evidence(combined, [r".*"])
            return FailureType.TIMEOUT, 1.0, evidence

        # Pattern matching
        for failure_type, confidence, patterns in _PATTERNS:
            matched_lines = self._match_patterns(combined, patterns)
            if matched_lines:
                evidence = self._extract_evidence(combined, patterns)
                return failure_type, confidence, tuple(evidence)

        # No pattern matched — honest UNKNOWN
        evidence = self._extract_evidence(combined, [r".+"])
        return FailureType.UNKNOWN, 0.0, tuple(evidence[:5])

    def _match_patterns(self, text: str, patterns: list[str]) -> list[str]:
        """Return lines that match any of the given patterns."""
        matched = []
        for line in text.splitlines():
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    matched.append(line.strip()[:_MAX_LINE])
                    break
        return matched

    def _extract_evidence(
        self, text: str, patterns: list[str]
    ) -> list[str]:
        """
        Extract the most relevant lines as evidence.

        Prioritises lines matching the patterns, then falls back to
        the last few lines of output (where errors typically appear).
        """
        matching = self._match_patterns(text, patterns)

        # Deduplicate while preserving order
        seen: set[str] = set()
        evidence: list[str] = []
        for line in matching:
            if line not in seen and line.strip():
                seen.add(line)
                evidence.append(line)
                if len(evidence) >= _MAX_EVIDENCE:
                    break

        # If we have few matches, pad with tail lines
        if len(evidence) < 5:
            tail = [
                line.strip()[:_MAX_LINE]
                for line in text.splitlines()[-10:]
                if line.strip() and line.strip() not in seen
            ]
            evidence.extend(tail[:_MAX_EVIDENCE - len(evidence)])

        return evidence[:_MAX_EVIDENCE]