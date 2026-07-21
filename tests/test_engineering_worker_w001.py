"""
Genesis-W001 Sprint-001 — Engineering Worker Tests

Coverage:
  - EngineeringModels: Severity, Category, EngineeringIssue, EngineeringReport
  - EngineeringWorker: log parsing, issue detection, health score, successes
  - Routing checks: UNKNOWN rate, memory statements to AI, recall to AI
  - Memory checks: raw value responses, memory misses
  - Performance checks: slow AI, slow local
  - Exception checks: traceback detection
  - Health score computation
  - formatted() output
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.engineering_models import (
    Category, EngineeringIssue, EngineeringReport, Severity,
)
from core.workers.session_analysis_worker import SessionAnalysisWorker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_turn_lines(
    request: str,
    intent: str = "UNKNOWN",
    decision: str = "Ai Fallback",
    ai_ms: int = 0,
    total_ms: float = 15.0,
    speech_chars: int = 28,
    memory_store: bool = False,
) -> list[str]:
    """Build minimal log lines for a single conversation turn."""
    lines = [
        f"INFO | Jarvis | Request received: {request}",
        f"INFO | core.conversation.conversation_router | [ROUTER] Intent={intent} → DecisionType={decision}",
    ]
    if ai_ms > 0:
        lines += [
            "INFO | Jarvis | TIMING | req=1 | stage=openai_request | provider=openai | model=gpt-5 | 0.0 ms",
            f"INFO | Jarvis | USAGE | req=1 | model=gpt-5 | ai_ms={ai_ms} | prompt=38 | completion=100 | finish=stop",
        ]
    if memory_store:
        lines.append(
            "INFO | Jarvis | TIMING | req=1 | stage=skill_manager | skill=memory_store | 9.0 ms"
        )
    lines += [
        f"INFO | Jarvis | TIMING | req=1 | stage=total_end_to_end | {total_ms} ms",
        f"INFO | core.voice.providers.system_tts | SystemTTSProvider: speech started (1 chunk(s), {speech_chars} chars).",
    ]
    return lines


# ===========================================================================
# 1. Models
# ===========================================================================

class TestEngineeringModels:

    def test_severity_values(self):
        assert Severity.HIGH.value   == "HIGH"
        assert Severity.MEDIUM.value == "MEDIUM"
        assert Severity.LOW.value    == "LOW"
        assert Severity.INFO.value   == "INFO"

    def test_category_values(self):
        assert Category.ROUTING.value     == "ROUTING"
        assert Category.MEMORY.value      == "MEMORY"
        assert Category.PERFORMANCE.value == "PERFORMANCE"
        assert Category.EXCEPTION.value   == "EXCEPTION"

    def test_issue_frozen(self):
        issue = EngineeringIssue(
            severity=Severity.HIGH,
            category=Category.ROUTING,
            title="Test",
            description="Test description",
        )
        with pytest.raises((AttributeError, TypeError)):
            issue.title = "changed"

    def test_issue_defaults(self):
        issue = EngineeringIssue(
            severity=Severity.LOW,
            category=Category.MEMORY,
            title="Test",
            description="Desc",
        )
        assert issue.evidence == []
        assert issue.confidence == 0.0
        assert issue.likely_files == []
        assert issue.recommendation == ""

    def test_report_issues_by_severity(self):
        report = EngineeringReport(
            health_score=80,
            session_turns=5,
            issues=[
                EngineeringIssue(Severity.HIGH,   Category.ROUTING, "H1", "d"),
                EngineeringIssue(Severity.MEDIUM, Category.MEMORY,  "M1", "d"),
                EngineeringIssue(Severity.HIGH,   Category.ROUTING, "H2", "d"),
            ],
        )
        assert len(report.issues_by_severity(Severity.HIGH))   == 2
        assert len(report.issues_by_severity(Severity.MEDIUM)) == 1
        assert len(report.issues_by_severity(Severity.LOW))    == 0

    def test_report_has_issues(self):
        empty = EngineeringReport(health_score=100, session_turns=0)
        assert not empty.has_issues()
        with_issue = EngineeringReport(
            health_score=80,
            session_turns=1,
            issues=[EngineeringIssue(Severity.LOW, Category.MEMORY, "T", "d")],
        )
        assert with_issue.has_issues()

    def test_report_formatted_contains_health(self):
        report = EngineeringReport(health_score=92, session_turns=5)
        output = report.formatted()
        assert "92" in output
        assert "Engineering Worker Report" in output


# ===========================================================================
# 2. Worker — empty / trivial sessions
# ===========================================================================

class TestEngineeringWorkerEmpty:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_empty_log_returns_report(self):
        report = self.worker.analyse_session([])
        assert isinstance(report, EngineeringReport)
        assert report.session_turns == 0
        assert report.health_score == 100

    def test_single_greeting_no_issues(self):
        lines = make_turn_lines("hello", intent="GREETING", decision="Answer Directly", total_ms=12.0, speech_chars=32)
        report = self.worker.analyse_session(lines)
        assert report.session_turns == 1
        high = report.issues_by_severity(Severity.HIGH)
        assert len(high) == 0


# ===========================================================================
# 3. Worker — routing checks
# ===========================================================================

class TestEngineeringWorkerRouting:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_detects_memory_statement_to_ai(self):
        lines = make_turn_lines("I have 2 dogs.", ai_ms=6000, total_ms=6200, speech_chars=250)
        report = self.worker.analyse_session(lines)
        routing_issues = [i for i in report.issues if i.category == Category.ROUTING]
        assert any("memory statement" in i.title.lower() or "Memory statement" in i.title
                   for i in routing_issues)

    def test_detects_recall_query_to_ai(self):
        lines = make_turn_lines("Who are Rex and Tom?", ai_ms=5000, total_ms=5200, speech_chars=200)
        report = self.worker.analyse_session(lines)
        routing_issues = [i for i in report.issues if i.category == Category.ROUTING]
        assert any("recall" in i.title.lower() for i in routing_issues)

    def test_high_unknown_rate_flagged(self):
        lines = []
        for i in range(8):
            lines += make_turn_lines(f"question {i}", intent="UNKNOWN", ai_ms=5000)
        lines += make_turn_lines("hello", intent="GREETING", decision="Answer Directly")
        lines += make_turn_lines("hello", intent="GREETING", decision="Answer Directly")
        report = self.worker.analyse_session(lines)
        routing_issues = [i for i in report.issues if i.category == Category.ROUTING]
        assert any("UNKNOWN" in i.title for i in routing_issues)

    def test_local_routing_no_routing_issue(self):
        lines = make_turn_lines(
            "I have 2 dogs.",
            intent="UNKNOWN",
            decision="Ai Fallback",
            ai_ms=0,
            total_ms=22.0,
            speech_chars=41,
            memory_store=True,
        )
        report = self.worker.analyse_session(lines)
        # Memory store happened locally — memory statement issue should NOT fire
        mem_stmt_issues = [
            i for i in report.issues
            if "memory statement" in i.title.lower()
        ]
        assert len(mem_stmt_issues) == 0


# ===========================================================================
# 4. Worker — memory checks
# ===========================================================================

class TestEngineeringWorkerMemory:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_detects_raw_value_response(self):
        lines = make_turn_lines("Who is Alex?", total_ms=18.0, speech_chars=4)
        report = self.worker.analyse_session(lines)
        memory_issues = [i for i in report.issues if i.category == Category.MEMORY]
        assert any("raw" in i.title.lower() for i in memory_issues)

    def test_no_raw_value_when_long_response(self):
        lines = make_turn_lines("Who is Alex?", total_ms=18.0, speech_chars=45)
        report = self.worker.analyse_session(lines)
        memory_issues = [i for i in report.issues if i.category == Category.MEMORY]
        raw_issues = [i for i in memory_issues if "raw" in i.title.lower()]
        assert len(raw_issues) == 0

    def test_detects_memory_miss(self):
        lines = make_turn_lines("what is my lucky number?", intent="MEMORY", decision="Invoke Memory")
        lines.append("INFO | Jarvis | TIMING | req=1 | stage=knowledge_lookup | result=miss | 5.0 ms")
        report = self.worker.analyse_session(lines)
        memory_issues = [i for i in report.issues if i.category == Category.MEMORY]
        assert any("miss" in i.title.lower() for i in memory_issues)


# ===========================================================================
# 5. Worker — performance checks
# ===========================================================================

class TestEngineeringWorkerPerformance:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_slow_ai_flagged(self):
        lines = make_turn_lines("explain black holes", ai_ms=13000, total_ms=13200, speech_chars=400)
        report = self.worker.analyse_session(lines)
        perf_issues = [i for i in report.issues if i.category == Category.PERFORMANCE]
        assert any("slow ai" in i.title.lower() for i in perf_issues)

    def test_fast_ai_not_flagged(self):
        lines = make_turn_lines("hello", intent="GREETING", ai_ms=1000, total_ms=1200, speech_chars=32)
        report = self.worker.analyse_session(lines)
        perf_issues = [i for i in report.issues if i.category == Category.PERFORMANCE]
        slow_ai = [i for i in perf_issues if "slow ai" in i.title.lower()]
        assert len(slow_ai) == 0

    def test_slow_local_flagged(self):
        lines = make_turn_lines("My son is Alex.", memory_store=True, total_ms=350.0, speech_chars=46)
        report = self.worker.analyse_session(lines)
        perf_issues = [i for i in report.issues if i.category == Category.PERFORMANCE]
        assert any("slow local" in i.title.lower() for i in perf_issues)


# ===========================================================================
# 6. Worker — exception checks
# ===========================================================================

class TestEngineeringWorkerExceptions:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_detects_traceback(self):
        lines = [
            "INFO | Jarvis | Request received: Who are Rex and Tom?",
            "ERROR | Traceback (most recent call last):",
            '  File "core/conversation/conversation_recall.py", line 212, in _recall_person',
            "    logger.info(...)",
            "UnboundLocalError: cannot access local variable 'animal'",
            "    where it is not associated with a value",
            "ERROR | Jarvis | Agent error",
            "INFO | Something else",
            "INFO | continuing",
            "INFO | still going",
            "INFO | almost done",
            "INFO | last line",
        ]
        report = self.worker.analyse_session(lines)
        exc_issues = [i for i in report.issues if i.category == Category.EXCEPTION]
        assert len(exc_issues) >= 1
        assert exc_issues[0].severity == Severity.HIGH

    def test_no_exception_clean_session(self):
        lines = make_turn_lines("hello", intent="GREETING", decision="Answer Directly")
        report = self.worker.analyse_session(lines)
        exc_issues = [i for i in report.issues if i.category == Category.EXCEPTION]
        assert len(exc_issues) == 0


# ===========================================================================
# 7. Worker — health score
# ===========================================================================

class TestEngineeringWorkerHealthScore:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_perfect_session_high_health(self):
        lines = []
        for req in ["hello", "My name is Gianni.", "What is my name?"]:
            lines += make_turn_lines(req, intent="GREETING", decision="Answer Directly",
                                     total_ms=15.0, speech_chars=30)
        report = self.worker.analyse_session(lines)
        assert report.health_score >= 80

    def test_all_ai_lowers_health(self):
        lines = []
        for i in range(10):
            lines += make_turn_lines(f"question {i}", ai_ms=5000, total_ms=5200, speech_chars=200)
        report = self.worker.analyse_session(lines)
        assert report.health_score < 80

    def test_health_score_bounded(self):
        lines = make_turn_lines("hello")
        report = self.worker.analyse_session(lines)
        assert 0 <= report.health_score <= 100


# ===========================================================================
# 8. Worker — successes
# ===========================================================================

class TestEngineeringWorkerSuccesses:

    def setup_method(self):
        self.worker = SessionAnalysisWorker()

    def test_local_turns_reported_as_success(self):
        lines = make_turn_lines("I have 2 dogs.", memory_store=True, total_ms=22.0, speech_chars=41)
        report = self.worker.analyse_session(lines)
        assert any("local" in s.lower() for s in report.successes)

    def test_memory_stored_reported_as_success(self):
        lines = make_turn_lines("My name is Gianni.", memory_store=True, total_ms=20.0, speech_chars=45)
        report = self.worker.analyse_session(lines)
        assert any("memory" in s.lower() or "stored" in s.lower() for s in report.successes)

    def test_no_crashes_reported_as_success(self):
        lines = make_turn_lines("hello", intent="GREETING", decision="Answer Directly")
        report = self.worker.analyse_session(lines)
        assert any("crash" in s.lower() or "exception" in s.lower() for s in report.successes)


# ===========================================================================
# 9. Worker — issues sorted by severity
# ===========================================================================

class TestEngineeringWorkerIssueSorting:

    def test_issues_sorted_high_first(self):
        worker = SessionAnalysisWorker()
        lines = []
        # Trigger both a memory statement AI call (HIGH) and a slow local (LOW)
        lines += make_turn_lines("I have 2 dogs.", ai_ms=6000, total_ms=6200, speech_chars=250)
        lines += make_turn_lines("My son is Alex.", memory_store=True, total_ms=350.0, speech_chars=46)
        report = worker.analyse_session(lines)
        if len(report.issues) >= 2:
            severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
            for i in range(len(report.issues) - 1):
                assert (severity_order[report.issues[i].severity.value]
                        <= severity_order[report.issues[i + 1].severity.value])