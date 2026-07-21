"""
Jarvis Session Analysis Worker (Genesis-W001 Sprint-001)

Analyses completed Jarvis desktop session logs and produces a structured
EngineeringReport. Does not modify code, call AI, or make any changes.

Responsibilities:
    - Parse session log lines (passed in as a list of strings)
    - Detect routing problems, memory issues, performance problems, exceptions
    - Assign severity and confidence to each issue
    - Identify likely source files
    - Return an EngineeringReport

Design constraints:
    - No AI calls
    - No file I/O (caller supplies log lines)
    - No code modification
    - Deterministic — same log → same report
    - Read-only analysis only

Usage (library):
    worker = SessionAnalysisWorker()
    with open("session.log") as f:
        lines = f.readlines()
    report = worker.analyse_session(lines)
    print(report.formatted())

Usage (CLI):
    python -m core.workers.session_analysis_worker session.log
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core.workers.engineering_models import (
    Category, EngineeringIssue, EngineeringReport, Severity,
)


# ---------------------------------------------------------------------------
# Log line patterns
# ---------------------------------------------------------------------------

_RE_REQUEST       = re.compile(r"Request received: (.+)")
_RE_INTENT        = re.compile(r"\[ROUTER\] Intent=(\w+) → DecisionType=(\w[\w ]+)")
_RE_AI_REQUEST    = re.compile(r"stage=openai_request")
_RE_AI_RESPONSE   = re.compile(r"stage=openai_response .+ (\d+\.\d+) ms")
_RE_AI_MS         = re.compile(r"ai_ms=(\d+)")
_RE_TOTAL_MS      = re.compile(r"stage=total_end_to_end \| ([\d.]+) ms")
_RE_MEMORY_HIT    = re.compile(r"result=hit")
_RE_MEMORY_MISS   = re.compile(r"result=miss")
_RE_STORE         = re.compile(r"store_memory: stored subject='(\w+)' attribute='(.+?)' value='(.+?)'")
_RE_UPDATE        = re.compile(r"update_memory: updated subject='(\w+)' attribute='(.+?)' value='(.+?)'")
_RE_TRACEBACK     = re.compile(r"Traceback \(most recent call last\)")
_RE_EXCEPTION     = re.compile(r"(Error|Exception|Traceback).*:", re.IGNORECASE)
_RE_SPEECH        = re.compile(r"speech started \((\d+) chunk\(s\), (\d+) chars\)")
_RE_RECALL_ANSWER = re.compile(r"\[RECALL\] .+answer='(.+?)'")
_RE_MEMORY_STORE  = re.compile(r"skill=memory_store")
_RE_SKILL         = re.compile(r"stage=skill_manager \| skill=(\w+)")

# Thresholds
_AI_LATENCY_WARN_MS   = 5000   # AI response above this is flagged
_LOCAL_LATENCY_WARN_MS = 200   # Local operation above this is flagged
_RAW_VALUE_CHAR_LIMIT  = 30    # Short speech responses that may be raw values


@dataclass
class _Turn:
    """Internal representation of one conversation turn."""
    number:       int
    request:      str        = ""
    intent:       str        = ""
    decision:     str        = ""
    ai_called:    bool       = False
    ai_ms:        int        = 0
    total_ms:     float      = 0.0
    speech_chars: int        = 0
    memory_stored: bool      = False
    memory_hit:   bool       = False
    memory_miss:  bool       = False
    has_error:    bool       = False
    error_lines:  list[str]  = field(default_factory=list)


class SessionAnalysisWorker:
    """
    Analyses a Jarvis desktop session log and produces an EngineeringReport.

    The worker is stateless — create one instance and call analyse_session()
    as many times as needed.

    Public API:
        analyse_session(log_lines) -> EngineeringReport
    """

    def analyse_session(self, log_lines: list[str]) -> EngineeringReport:
        """
        Analyse a list of log lines from a Jarvis desktop session.

        Args:
            log_lines: Raw log lines (strings). Newlines are stripped.

        Returns:
            EngineeringReport with health score, successes, and issues.
        """
        lines = [l.rstrip("\n") for l in log_lines]
        turns = self._parse_turns(lines)
        issues = self._detect_issues(turns, lines)
        successes = self._detect_successes(turns, lines)
        health_score = self._compute_health(turns, issues)
        summary = self._build_summary(turns, issues, health_score)

        return EngineeringReport(
            health_score=health_score,
            session_turns=len(turns),
            successes=successes,
            issues=sorted(issues, key=lambda i: (
                {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}[i.severity.value]
            )),
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_turns(self, lines: list[str]) -> list[_Turn]:
        """Group log lines into per-turn _Turn objects."""
        turns: list[_Turn] = []
        current: Optional[_Turn] = None

        for line in lines:
            # New turn starts when a request is received
            m = _RE_REQUEST.search(line)
            if m:
                if current:
                    turns.append(current)
                current = _Turn(
                    number=len(turns) + 1,
                    request=m.group(1).strip(),
                )
                continue

            if current is None:
                continue

            # Intent and decision
            m = _RE_INTENT.search(line)
            if m:
                current.intent   = m.group(1)
                current.decision = m.group(2).strip()

            # AI called
            if _RE_AI_REQUEST.search(line):
                current.ai_called = True

            # AI latency
            m = _RE_AI_MS.search(line)
            if m:
                current.ai_ms = int(m.group(1))

            # Total latency
            m = _RE_TOTAL_MS.search(line)
            if m:
                current.total_ms = float(m.group(1))

            # Speech length
            m = _RE_SPEECH.search(line)
            if m:
                current.speech_chars = int(m.group(2))

            # Memory store
            if _RE_MEMORY_STORE.search(line):
                current.memory_stored = True

            # Memory hit/miss
            if _RE_MEMORY_HIT.search(line):
                current.memory_hit = True
            if _RE_MEMORY_MISS.search(line):
                current.memory_miss = True

            # Errors
            if _RE_TRACEBACK.search(line) or ("ERROR" in line and "Exception" in line):
                current.has_error = True
                current.error_lines.append(line)

        if current:
            turns.append(current)

        return turns

    # ------------------------------------------------------------------
    # Issue detection
    # ------------------------------------------------------------------

    def _detect_issues(self, turns: list[_Turn], lines: list[str]) -> list[EngineeringIssue]:
        issues: list[EngineeringIssue] = []
        issues.extend(self._check_routing(turns))
        issues.extend(self._check_memory(turns))
        issues.extend(self._check_performance(turns))
        issues.extend(self._check_exceptions(lines))
        return issues

    def _check_routing(self, turns: list[_Turn]) -> list[EngineeringIssue]:
        issues = []

        # Memory statements routed to AI
        memory_statement_ai: list[str] = []
        for t in turns:
            if t.ai_called and t.intent == "UNKNOWN":
                req_lower = t.request.lower()
                if any(kw in req_lower for kw in [
                    "i have", "their names", "my son", "my daughter",
                    "my manager", "i work at", "i work for",
                    "my wife", "my husband", "my friend",
                ]):
                    memory_statement_ai.append(t.request)

        if memory_statement_ai:
            issues.append(EngineeringIssue(
                severity=Severity.HIGH,
                category=Category.ROUTING,
                title="Memory statements routed to AI instead of local storage",
                description=(
                    f"{len(memory_statement_ai)} personal statement(s) were sent to AI "
                    "despite being extractable locally."
                ),
                evidence=memory_statement_ai[:3],
                confidence=0.95,
                likely_files=["core/conversation/memory_detector.py", "core/router.py"],
                recommendation="Add patterns to MemoryDetector for these statement types.",
            ))

        # Recall queries routed to AI
        recall_ai: list[str] = []
        for t in turns:
            if t.ai_called and t.intent == "UNKNOWN":
                req_lower = t.request.lower()
                if any(kw in req_lower for kw in [
                    "who is", "who are", "where do i work",
                    "what is my", "where am i",
                ]):
                    recall_ai.append(t.request)

        if recall_ai:
            issues.append(EngineeringIssue(
                severity=Severity.HIGH,
                category=Category.ROUTING,
                title="Recall queries routed to AI instead of local recall",
                description=(
                    f"{len(recall_ai)} recall question(s) fell through to AI "
                    "despite potential local answers."
                ),
                evidence=recall_ai[:3],
                confidence=0.90,
                likely_files=["core/conversation/conversation_recall.py", "core/router.py"],
                recommendation="Extend conversation_recall.can_answer() and ensure MEMORY intent covers these patterns.",
            ))

        # High UNKNOWN rate
        unknown_turns = [t for t in turns if t.intent == "UNKNOWN"]
        if len(turns) > 0 and len(unknown_turns) / len(turns) > 0.5:
            issues.append(EngineeringIssue(
                severity=Severity.MEDIUM,
                category=Category.ROUTING,
                title="High UNKNOWN intent rate",
                description=(
                    f"{len(unknown_turns)}/{len(turns)} turns classified as UNKNOWN "
                    f"({100 * len(unknown_turns) // len(turns)}%)."
                ),
                evidence=[t.request for t in unknown_turns[:3]],
                confidence=0.85,
                likely_files=["core/router.py"],
                recommendation="Review IntentRouter patterns to reduce UNKNOWN fallthrough.",
            ))

        return issues

    def _check_memory(self, turns: list[_Turn]) -> list[EngineeringIssue]:
        issues = []

        # Raw value responses — short local answers that likely returned bare values
        raw_value_turns: list[_Turn] = []
        for t in turns:
            if (not t.ai_called
                    and t.speech_chars > 0
                    and t.speech_chars <= _RAW_VALUE_CHAR_LIMIT
                    and t.intent == "UNKNOWN"
                    and any(kw in t.request.lower() for kw in [
                        "who is", "who are", "where do i", "what is my",
                    ])):
                raw_value_turns.append(t)

        if raw_value_turns:
            issues.append(EngineeringIssue(
                severity=Severity.MEDIUM,
                category=Category.MEMORY,
                title="Recall responses may be returning raw stored values",
                description=(
                    f"{len(raw_value_turns)} recall response(s) were very short "
                    f"(<= {_RAW_VALUE_CHAR_LIMIT} chars), suggesting bare values "
                    "rather than natural sentences."
                ),
                evidence=[f"{t.request!r} → {t.speech_chars} chars" for t in raw_value_turns[:3]],
                confidence=0.80,
                likely_files=["core/conversation/conversation_recall.py"],
                recommendation="Ensure _recall_person() and _recall_attribute() return composed sentences.",
            ))

        # Memory misses
        miss_turns = [t for t in turns if t.memory_miss]
        if miss_turns:
            issues.append(EngineeringIssue(
                severity=Severity.LOW,
                category=Category.MEMORY,
                title="Memory lookup misses detected",
                description=f"{len(miss_turns)} turn(s) had knowledge engine lookup misses.",
                evidence=[t.request for t in miss_turns[:3]],
                confidence=0.75,
                likely_files=["core/conversation/conversation_recall.py", "core/skills/memory.py"],
                recommendation="Check whether the memory was stored under a different attribute name.",
            ))

        return issues

    def _check_performance(self, turns: list[_Turn]) -> list[EngineeringIssue]:
        issues = []

        # Slow AI responses
        slow_ai = [t for t in turns if t.ai_called and t.ai_ms > _AI_LATENCY_WARN_MS]
        if slow_ai:
            avg_ms = sum(t.ai_ms for t in slow_ai) // len(slow_ai)
            issues.append(EngineeringIssue(
                severity=Severity.LOW,
                category=Category.PERFORMANCE,
                title="Slow AI responses detected",
                description=(
                    f"{len(slow_ai)} AI call(s) exceeded {_AI_LATENCY_WARN_MS}ms. "
                    f"Average: {avg_ms}ms."
                ),
                evidence=[f"{t.request!r} → {t.ai_ms}ms" for t in slow_ai[:3]],
                confidence=0.99,
                likely_files=["core/ai/"],
                recommendation="Consider caching or routing these queries locally if possible.",
            ))

        # Slow local operations
        slow_local = [
            t for t in turns
            if not t.ai_called and t.total_ms > _LOCAL_LATENCY_WARN_MS
        ]
        if slow_local:
            issues.append(EngineeringIssue(
                severity=Severity.LOW,
                category=Category.PERFORMANCE,
                title="Slow local operations detected",
                description=(
                    f"{len(slow_local)} local turn(s) exceeded {_LOCAL_LATENCY_WARN_MS}ms."
                ),
                evidence=[f"{t.request!r} → {t.total_ms:.0f}ms" for t in slow_local[:3]],
                confidence=0.90,
                likely_files=["core/knowledge_engine/", "core/conversation/"],
                recommendation="Profile the knowledge engine lookup and storage path.",
            ))

        return issues

    def _check_exceptions(self, lines: list[str]) -> list[EngineeringIssue]:
        issues = []
        tb_lines: list[str] = []
        in_tb = False

        for line in lines:
            if _RE_TRACEBACK.search(line):
                in_tb = True
                tb_lines = [line]
            elif in_tb:
                tb_lines.append(line)
                if len(tb_lines) > 10:
                    in_tb = False
                    issues.append(EngineeringIssue(
                        severity=Severity.HIGH,
                        category=Category.EXCEPTION,
                        title="Traceback detected in session log",
                        description="An unhandled exception occurred during the session.",
                        evidence=tb_lines[:5],
                        confidence=0.99,
                        likely_files=[],
                        recommendation="Reproduce the crash and add error handling at the failing call site.",
                    ))
                    tb_lines = []

        return issues

    # ------------------------------------------------------------------
    # Successes
    # ------------------------------------------------------------------

    def _detect_successes(self, turns: list[_Turn], lines: list[str]) -> list[str]:
        successes = []

        local_turns = [t for t in turns if not t.ai_called]
        if local_turns:
            successes.append(
                f"{len(local_turns)}/{len(turns)} turns answered locally without AI"
            )

        memory_stored = [t for t in turns if t.memory_stored]
        if memory_stored:
            successes.append(
                f"{len(memory_stored)} memory statement(s) stored locally"
            )

        memory_hits = [t for t in turns if t.memory_hit]
        if memory_hits:
            successes.append(
                f"{len(memory_hits)} knowledge engine lookup hit(s)"
            )

        no_errors = not any(t.has_error for t in turns)
        if no_errors:
            successes.append("No crashes or exceptions detected")

        fast_local = [t for t in turns if not t.ai_called and t.total_ms < 50]
        if fast_local:
            avg = sum(t.total_ms for t in fast_local) / len(fast_local)
            successes.append(
                f"{len(fast_local)} local turn(s) completed under 50ms (avg {avg:.1f}ms)"
            )

        return successes

    # ------------------------------------------------------------------
    # Health score
    # ------------------------------------------------------------------

    def _compute_health(self, turns: list[_Turn], issues: list[EngineeringIssue]) -> int:
        if not turns:
            return 100

        score = 100

        # Deduct for high-severity issues
        high   = sum(1 for i in issues if i.severity == Severity.HIGH)
        medium = sum(1 for i in issues if i.severity == Severity.MEDIUM)
        low    = sum(1 for i in issues if i.severity == Severity.LOW)

        score -= high   * 15
        score -= medium * 7
        score -= low    * 3

        # Deduct for AI call rate
        ai_turns = [t for t in turns if t.ai_called]
        ai_rate  = len(ai_turns) / len(turns)
        if ai_rate > 0.3:
            score -= int((ai_rate - 0.3) * 30)

        return max(0, min(100, score))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self, turns: list[_Turn], issues: list[EngineeringIssue], health_score: int
    ) -> str:
        ai_count    = sum(1 for t in turns if t.ai_called)
        local_count = len(turns) - ai_count
        high_count  = sum(1 for i in issues if i.severity == Severity.HIGH)

        parts = [
            f"Session: {len(turns)} turn(s), {local_count} local, {ai_count} AI.",
        ]
        if high_count:
            parts.append(f"{high_count} HIGH severity issue(s) require attention.")
        if health_score >= 90:
            parts.append("Overall session health is excellent.")
        elif health_score >= 70:
            parts.append("Overall session health is good with minor issues.")
        else:
            parts.append("Session health needs improvement.")

        return " ".join(parts)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m core.workers.session_analysis_worker <path/to/session.log>")
        print("")
        print("  Analyses a Jarvis desktop session log and prints a structured")
        print("  engineering report with health score, successes, and issues.")
        sys.exit(1)

    log_path = sys.argv[1]

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"Error: log file not found: {log_path}")
        sys.exit(1)

    worker = SessionAnalysisWorker()
    report = worker.analyse_session(lines)
    print(report.formatted())