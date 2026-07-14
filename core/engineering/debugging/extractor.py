"""
Evidence Extractor (Genesis-017 Sprint 002)

Extracts structured forensic evidence from raw process output.

Responsibility: extract and structure — nothing else.
    * Parse stack traces into frames.
    * Extract file paths and line numbers.
    * Identify the exception/error type.
    * Collect compiler diagnostics.

Constitutional constraints — this module MUST NEVER:
    * Classify failures (that is FailureClassifier's job).
    * Recommend fixes.
    * Modify files.
    * Call AI or LLM.
    * Guess when evidence is absent — return empty tuples.

Design philosophy:
    A forensic extractor collects facts.
    It does not interpret them.
    Interpretation belongs to the classifier and the Chief.
"""

import re
from typing import NamedTuple

# Maximum items to extract per category — keeps reports focused
_MAX_FRAMES      = 15
_MAX_FILES       = 10
_MAX_LINE_NUMS   = 10
_MAX_DIAGNOSTICS = 20

# ---------------------------------------------------------------------------
# Stack frame — one entry in a Python traceback
# ---------------------------------------------------------------------------

class StackFrame(NamedTuple):
    """One frame from a Python traceback."""
    filepath:  str
    line_no:   int
    context:   str    # the source line text, if present

    def __str__(self) -> str:
        return f"{self.filepath}:{self.line_no} — {self.context}"


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Python traceback frame:  File "path/to/file.py", line 42, in function_name
_FRAME_RE = re.compile(
    r'File "([^"]+)", line (\d+)(?:, in .+)?'
)

# Source context line (the line after a frame in a traceback)
_CONTEXT_RE = re.compile(r'^\s{4}(.+)$')

# Exception type at the end of a traceback: ExceptionName: message
_ERROR_TYPE_RE = re.compile(
    r'^([A-Z][a-zA-Z]*(?:Error|Exception|Warning|Expired|Interrupted'
    r'|Fault|Failure|NotFound|NotImplemented|Stop|Exit))\s*[:\s]',
    re.MULTILINE,
)

# File paths in output (Windows and Unix)
_FILE_PATH_RE = re.compile(
    r'(?:File\s+"([^"]+\.py)"'           # Python traceback style
    r'|"([^"]+\.py)"'                    # quoted path
    r'|([A-Za-z]?[:/\\][^\s"\'<>|]+\.py))'  # bare path
)

# Line numbers from various formats:
#   line 42 | :42 | (line 42) | ,42
_LINE_NO_RE = re.compile(
    r'(?:line\s+(\d+)|:(\d+)|,\s*line\s+(\d+))',
    re.IGNORECASE,
)

# Compiler/linter diagnostic patterns
_DIAGNOSTIC_RE = re.compile(
    r'(?:'
    r'SyntaxError|IndentationError|TabError'          # Python compile
    r'|error:|warning:|note:'                         # generic compiler
    r'|E\d{3,4}|W\d{3,4}'                            # pylint/flake8 codes
    r'|^\s*\^+\s*$'                                   # caret indicator
    r')',
    re.IGNORECASE | re.MULTILINE,
)


class EvidenceExtractor:
    """
    Extracts structured forensic evidence from raw process output.

    Read-only. No files modified. No AI calls. No fix suggestions.
    Empty evidence is returned honestly when patterns don't match —
    never fabricated.
    """

    def extract(
        self,
        stdout: str,
        stderr: str,
    ) -> dict:
        """
        Extract structured evidence from process output.

        Args:
            stdout: Captured standard output.
            stderr: Captured standard error.

        Returns:
            dict with keys: stack_trace, failing_files, line_numbers,
                            error_type, diagnostics.
            All values are tuples. Never raises.
        """
        combined = stdout + "\n" + stderr

        stack_trace   = self._extract_stack_trace(combined)
        failing_files = self._extract_files(combined)
        line_numbers  = self._extract_line_numbers(combined)
        error_type    = self._extract_error_type(combined)
        diagnostics   = self._extract_diagnostics(combined)

        return {
            "stack_trace":   tuple(str(f) for f in stack_trace),
            "failing_files": tuple(failing_files),
            "line_numbers":  tuple(line_numbers),
            "error_type":    error_type,
            "diagnostics":   tuple(diagnostics),
        }

    # ------------------------------------------------------------------
    # Extractors — each returns a list, never raises
    # ------------------------------------------------------------------

    def _extract_stack_trace(self, text: str) -> list[StackFrame]:
        """Parse Python tracebacks into structured StackFrame objects."""
        frames: list[StackFrame] = []
        lines  = text.splitlines()

        i = 0
        while i < len(lines) and len(frames) < _MAX_FRAMES:
            line = lines[i]
            m = _FRAME_RE.search(line)
            if m:
                filepath = m.group(1)
                line_no  = int(m.group(2))
                # Next line is often the source context
                context = ""
                if i + 1 < len(lines):
                    ctx_m = _CONTEXT_RE.match(lines[i + 1])
                    if ctx_m and not _FRAME_RE.search(lines[i + 1]):
                        context = ctx_m.group(1).strip()
                        i += 1   # skip the context line
                frames.append(StackFrame(filepath, line_no, context))
            i += 1

        return frames

    def _extract_files(self, text: str) -> list[str]:
        """Extract unique file paths mentioned in the output."""
        seen: set[str] = set()
        files: list[str] = []

        for m in _FILE_PATH_RE.finditer(text):
            path = m.group(1) or m.group(2) or m.group(3)
            if path and path not in seen:
                seen.add(path)
                files.append(path)
                if len(files) >= _MAX_FILES:
                    break

        return files

    def _extract_line_numbers(self, text: str) -> list[int]:
        """Extract unique line numbers from tracebacks and diagnostics."""
        seen: set[int] = set()
        numbers: list[int] = []

        for m in _LINE_NO_RE.finditer(text):
            raw = m.group(1) or m.group(2) or m.group(3)
            if raw:
                n = int(raw)
                if n not in seen:
                    seen.add(n)
                    numbers.append(n)
                    if len(numbers) >= _MAX_LINE_NUMS:
                        break

        return numbers

    def _extract_error_type(self, text: str) -> str:
        """
        Extract the exception/error class name.

        Returns the first match, or empty string if none found.
        """
        m = _ERROR_TYPE_RE.search(text)
        return m.group(1).strip() if m else ""

    def _extract_diagnostics(self, text: str) -> list[str]:
        """Extract compiler/linter diagnostic lines."""
        seen: set[str] = set()
        diags: list[str] = []

        for line in text.splitlines():
            if _DIAGNOSTIC_RE.search(line):
                clean = line.strip()
                if clean and clean not in seen:
                    seen.add(clean)
                    diags.append(clean[:200])
                    if len(diags) >= _MAX_DIAGNOSTICS:
                        break

        return diags