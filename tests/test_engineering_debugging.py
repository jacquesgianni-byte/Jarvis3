"""
Genesis-017 Sprint 002 — Evidence Collection test battery.

Sprint 001 checks [1]–[10] are reproduced for full regression compatibility.
Sprint 002 sections begin at [11].

Runs standalone: python tests/test_engineering_debugging.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.debugging.models import DebugReport, FailureEvidence, FailureType
from core.engineering.debugging.classifier import FailureClassifier
from core.engineering.debugging.extractor import EvidenceExtractor, StackFrame
from core.engineering.debugging.debugger import EngineeringDebugger

passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


def make_evidence(**kwargs) -> FailureEvidence:
    defaults = dict(
        command="cmd", exit_code=1, stdout=(), stderr=(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        stack_trace=(), failing_files=(), line_numbers=(),
        error_type="", diagnostics=(),
    )
    defaults.update(kwargs)
    return FailureEvidence(**defaults)


TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "core/agent.py", line 42, in process\n'
    "    response = self.skills.execute(request)\n"
    '  File "core/skills/manager.py", line 18, in execute\n'
    "    return skill.execute(request)\n"
    '  File "core/skills/reasoning.py", line 55, in execute\n'
    "    result = self.engine.infer(subject, attribute)\n"
    "AttributeError: 'NoneType' object has no attribute 'infer'\n"
)

SYNTAX_ERROR = (
    '  File "core/router.py", line 77\n'
    "    def detect(self, request: str) -> Intent\n"
    "                                            ^\n"
    "SyntaxError: expected ':'\n"
)

IMPORT_ERROR = (
    "Traceback (most recent call last):\n"
    '  File "tests/test_reasoning_engine.py", line 5, in <module>\n'
    "    from core.reasoning.engine import ReasoningEngine\n"
    "ModuleNotFoundError: No module named 'core.reasoning.engine'\n"
)


# ── Sprint 001 regression ─────────────────────────────────────────────────

print("\n[1] FailureType enum")
check("COMPILE exists",       FailureType.COMPILE.value == "Compile Error")
check("IMPORT exists",        FailureType.IMPORT.value == "Import Error")
check("TEST exists",          FailureType.TEST.value == "Test Failure")
check("TIMEOUT exists",       FailureType.TIMEOUT.value == "Timeout")
check("CONFIGURATION exists", FailureType.CONFIGURATION.value == "Configuration Error")
check("UNKNOWN exists",       FailureType.UNKNOWN.value == "Unknown")
check("exactly 6 failure types", len(FailureType) == 6)

print("\n[2] DebugReport — immutable model")
_ev = make_evidence(command="python -m compileall core/",
                    stderr=("SyntaxError: invalid syntax",))
from core.engineering.debugging.root_cause import RootCause, RootCauseCategory
from core.engineering.debugging.correlation import CorrelationRecord, CorrelationType
from core.engineering.debugging.recommendation import (
    Recommendation, RecommendationCategory, RecommendationPriority)
from core.engineering.debugging.repair import (
    RepairPlan, RepairStep, RepairRisk, RepairEffort)
_rc = RootCause(category=RootCauseCategory.SYNTAX_ERROR, description="Syntax error.",
                confidence=0.97, supporting_evidence=(), contributing_factors=())
_no_corr = CorrelationRecord(correlation_type=CorrelationType.UNKNOWN, confidence=0.0,
                  description="no history", related_failures=(), related_files=(),
                  related_modules=(), related_commits=(), timeline=())
_empty_plan = RepairPlan(title="No Repair Plan", summary="test", confidence=0.0,
           steps=(), validation_steps=(), estimated_risk=RepairRisk.LOW,
           estimated_effort=RepairEffort.MINOR, supporting_recommendations=())
report = DebugReport(failure_type=FailureType.COMPILE, summary="SyntaxError on line 42",
                     confidence=0.95, clues=("SyntaxError: invalid syntax", "line 42"),
                     evidence=_ev, root_cause=_rc, correlation=_no_corr,
                     recommendations=(), repair_plan=_empty_plan)
check("DebugReport instantiates", report is not None)
check("DebugReport is frozen", report.__dataclass_params__.frozen)
check("evidence is a FailureEvidence", isinstance(report.evidence, FailureEvidence))
check("clues is a tuple", isinstance(report.clues, tuple))
check("evidence.stdout is a tuple", isinstance(report.evidence.stdout, tuple))
check("evidence.stderr is a tuple", isinstance(report.evidence.stderr, tuple))
check("failure_type is FailureType", isinstance(report.failure_type, FailureType))
check("confidence is a float", isinstance(report.confidence, float))
check("evidence.timestamp is non-empty", bool(report.evidence.timestamp))
_ev_mut  = make_evidence()
_rc_mut = RootCause(category=RootCauseCategory.UNKNOWN, description="t",
                    confidence=0.0, supporting_evidence=(), contributing_factors=())
_rep_mut = DebugReport(failure_type=FailureType.COMPILE, summary="t",
                       confidence=0.9, clues=(), evidence=_ev_mut, root_cause=_rc_mut,
                       correlation=_no_corr, recommendations=(),
                       repair_plan=_empty_plan)
try:
    _rep_mut.failure_type = FailureType.UNKNOWN
    check("DebugReport fields are immutable", False)
except (AttributeError, TypeError):
    check("DebugReport fields are immutable (raises on assignment)", True)
try:
    _ev_mut.exit_code = 0
    check("FailureEvidence fields are immutable", False)
except (AttributeError, TypeError):
    check("FailureEvidence fields are immutable (raises on assignment)", True)

print("\n[3] DebugReport.report() — human-readable output")
text = report.report()
check("report() is non-empty", len(text) > 50)
check("report contains 'Engineering Debug Report'", "Engineering Debug Report" in text)
check("report contains failure type", "Compile Error" in text)
check("report contains summary", "SyntaxError" in text)
check("report contains exit code", "1" in text)
check("report contains forensic note", "describes what happened" in text)

print("\n[4] FailureClassifier — deterministic classification")
clf = FailureClassifier()
check("classifier instantiates", clf is not None)
ft, conf, ev = clf.classify("all good", "", 0)
check("exit_code=0 -> UNKNOWN", ft == FailureType.UNKNOWN)
check("exit_code=0 -> confidence=0.0", conf == 0.0)
ft, conf, ev = clf.classify("", "SyntaxError: invalid syntax", 1)
check("SyntaxError -> COMPILE", ft == FailureType.COMPILE)
check("COMPILE confidence >= 0.9", conf >= 0.9)
check("evidence contains SyntaxError line", any("SyntaxError" in e for e in ev))
ft, conf, ev = clf.classify("", "ModuleNotFoundError: No module named 'openai'", 1)
check("ModuleNotFoundError -> IMPORT", ft == FailureType.IMPORT)
check("IMPORT confidence >= 0.9", conf >= 0.9)
ft, conf, ev = clf.classify("FAILED tests/test_edge_cases.py\n3 failed", "", 1)
check("pytest FAILED -> TEST", ft == FailureType.TEST)
check("TEST confidence >= 0.85", conf >= 0.85)
ft, conf, ev = clf.classify("", "TimeoutExpired: Command timed out after 120s", 1)
check("TimeoutExpired -> TIMEOUT", ft == FailureType.TIMEOUT)
check("TIMEOUT confidence = 1.0", conf == 1.0)
ft, conf, ev = clf.classify("", "", 124)
check("exit_code=124 -> TIMEOUT", ft == FailureType.TIMEOUT)
ft, conf, ev = clf.classify("", "KeyError: 'OPENAI_API_KEY'\nSettings not configured", 1)
check("KeyError API -> CONFIGURATION", ft == FailureType.CONFIGURATION)
ft, conf, ev = clf.classify("", "something went wrong", 1)
check("unrecognised output -> UNKNOWN", ft == FailureType.UNKNOWN)
check("UNKNOWN confidence = 0.0", conf == 0.0)

print("\n[5] Deterministic classification")
results = set()
for _ in range(20):
    ft, conf, ev = clf.classify("", "SyntaxError: invalid syntax", 1)
    results.add((ft, conf))
check("classification is deterministic (20 runs, 1 result)", len(results) == 1)

print("\n[6] EngineeringDebugger — analyse()")
debugger = EngineeringDebugger()
check("debugger instantiates", debugger is not None)
rep = debugger.analyse("python -m compileall core/", 1, "",
                       "SyntaxError: invalid syntax\n  File 'core/router.py', line 15")
check("analyse() returns DebugReport", isinstance(rep, DebugReport))
check("compile failure classified as COMPILE", rep.failure_type == FailureType.COMPILE)
check("confidence is set", rep.confidence > 0.0)
check("summary is non-empty", bool(rep.summary))
check("evidence is a FailureEvidence", isinstance(rep.evidence, FailureEvidence))
check("evidence.command is preserved", rep.evidence.command == "python -m compileall core/")
check("evidence.exit_code is preserved", rep.evidence.exit_code == 1)
check("evidence.timestamp is set", bool(rep.evidence.timestamp))
check("evidence.stderr contains SyntaxError",
      any("SyntaxError" in s for s in rep.evidence.stderr))
rep2 = debugger.analyse("cmd", 1, "", "ModuleNotFoundError: No module named 'core.reasoning'")
check("import failure classified as IMPORT", rep2.failure_type == FailureType.IMPORT)
rep3 = debugger.analyse("cmd", 1, "FAILED tests/test_edge_cases.py\n3 failed", "")
check("test failure classified as TEST", rep3.failure_type == FailureType.TEST)
rep4 = debugger.analyse("cmd", 1, "", "subprocess.TimeoutExpired: Command timed out after 120s")
check("timeout classified as TIMEOUT", rep4.failure_type == FailureType.TIMEOUT)
rep5 = debugger.analyse("cmd", 1, "", "something went wrong")
check("unknown failure -> UNKNOWN", rep5.failure_type == FailureType.UNKNOWN)
check("UNKNOWN confidence = 0.0", rep5.confidence == 0.0)
rep6 = debugger.analyse("cmd", 0, "Listing 'core'...", "")
check("exit_code=0 -> UNKNOWN", rep6.failure_type == FailureType.UNKNOWN)
check("exit_code=0 -> confidence=0.0", rep6.confidence == 0.0)

print("\n[7] Output truncation")
long_output = "x" * 10000
rep_long = debugger.analyse("cmd", 1, long_output, long_output)
check("stdout stored as tuple of lines", isinstance(rep_long.evidence.stdout, tuple))
check("stderr stored as tuple of lines", isinstance(rep_long.evidence.stderr, tuple))
check("clues capped at 20 lines", len(rep_long.clues) <= 20)

print("\n[8] analyse_step() convenience method")
class FakeStep:
    command = "python tests/test_edge_cases.py"
    passed  = False
    output  = "FAILED tests/test_edge_cases.py\n3 failed"
    error   = "AssertionError: expected True"
step_report = debugger.analyse_step(FakeStep())
check("analyse_step() returns DebugReport", isinstance(step_report, DebugReport))
check("analyse_step() classifies TEST failure", step_report.failure_type == FailureType.TEST)
check("analyse_step() captures command", bool(step_report.evidence.command))

print("\n[9] Read-only guarantee")
write_methods = ["write","modify","patch","apply","execute","commit","add","push","checkout","delete"]
for method in write_methods:
    check(f"EngineeringDebugger has no .{method}()", not hasattr(debugger, method))
for method in write_methods:
    check(f"FailureClassifier has no .{method}()", not hasattr(clf, method))

print("\n[10] Full report output (Sprint 001 regression)")
full_report = rep.report()
check("report contains 'Engineering Debug Report'", "Engineering Debug Report" in full_report)
check("report contains failure type", "Compile Error" in full_report)
check("report contains timestamp", rep.evidence.timestamp in full_report)
check("report contains evidence", len(full_report) > 100)
print(f"    Failure type: {rep.failure_type.value} | Confidence: {rep.confidence:.0%}")

# ── Sprint 002 — Evidence Collection ──────────────────────────────────────

print("\n[11] EvidenceExtractor — construction and API")
extractor = EvidenceExtractor()
check("extractor instantiates", extractor is not None)
result = extractor.extract("", "")
check("extract() returns a dict", isinstance(result, dict))
check("dict has stack_trace key", "stack_trace" in result)
check("dict has failing_files key", "failing_files" in result)
check("dict has line_numbers key", "line_numbers" in result)
check("dict has error_type key", "error_type" in result)
check("dict has diagnostics key", "diagnostics" in result)
check("all collection values are tuples",
      all(isinstance(result[k], tuple)
          for k in ("stack_trace","failing_files","line_numbers","diagnostics")))
check("error_type is a string", isinstance(result["error_type"], str))

print("\n[12] Stack trace extraction")
result = extractor.extract("", TRACEBACK)
check("stack_trace non-empty for real traceback", len(result["stack_trace"]) > 0)
check("frames contain file paths",
      any("core/" in f for f in result["stack_trace"]))
check("frames contain line numbers",
      any("42" in f or "18" in f or "55" in f for f in result["stack_trace"]))
print(f"    Frames extracted: {len(result['stack_trace'])}")
for f in result["stack_trace"]: print(f"      {f}")

print("\n[13] Failing file extraction")
result = extractor.extract("", TRACEBACK)
check("failing_files non-empty", len(result["failing_files"]) > 0)
check("agent.py in failing files",
      any("agent.py" in f for f in result["failing_files"]))
check("manager.py in failing files",
      any("manager.py" in f for f in result["failing_files"]))
result_imp = extractor.extract("", IMPORT_ERROR)
check("import error finds test file",
      any("test_reasoning" in f for f in result_imp["failing_files"]))
print(f"    Files: {result['failing_files']}")

print("\n[14] Line number extraction")
result = extractor.extract("", TRACEBACK)
check("line_numbers non-empty", len(result["line_numbers"]) > 0)
check("line 42 extracted", 42 in result["line_numbers"])
check("line numbers are integers", all(isinstance(n, int) for n in result["line_numbers"]))
result_syn = extractor.extract("", SYNTAX_ERROR)
check("line 77 extracted from syntax error", 77 in result_syn["line_numbers"])
print(f"    Line numbers: {result['line_numbers']}")

print("\n[15] Error type extraction")
result = extractor.extract("", TRACEBACK)
check("error_type non-empty for real traceback", bool(result["error_type"]))
check("AttributeError identified", "AttributeError" in result["error_type"])
result_syn = extractor.extract("", SYNTAX_ERROR)
check("SyntaxError identified", "SyntaxError" in result_syn["error_type"])
result_imp = extractor.extract("", IMPORT_ERROR)
check("ModuleNotFoundError identified",
      "ModuleNotFoundError" in result_imp["error_type"])
result_empty = extractor.extract("", "something went wrong")
check("empty error_type when no pattern", result_empty["error_type"] == "")
print(f"    Error type (traceback): {result['error_type']!r}")

print("\n[16] Diagnostics extraction")
result = extractor.extract("", SYNTAX_ERROR)
check("diagnostics non-empty for syntax error", len(result["diagnostics"]) > 0)
check("SyntaxError line in diagnostics",
      any("SyntaxError" in d for d in result["diagnostics"]))
result_clean = extractor.extract("Listing 'core'...", "")
check("no false diagnostics from clean compile", len(result_clean["diagnostics"]) == 0)
print(f"    Diagnostics: {len(result['diagnostics'])} line(s)")

print("\n[17] Empty / clean output")
result = extractor.extract("", "")
check("empty -> empty stack_trace",    result["stack_trace"]   == ())
check("empty -> empty failing_files",  result["failing_files"] == ())
check("empty -> empty line_numbers",   result["line_numbers"]  == ())
check("empty -> empty error_type",     result["error_type"]    == "")
check("empty -> empty diagnostics",    result["diagnostics"]   == ())

print("\n[18] Extractor limits")
many_frames = "\n".join(
    f'  File "core/module_{i}.py", line {i}, in func' for i in range(50))
result = extractor.extract("", many_frames)
check("stack_trace capped at 15", len(result["stack_trace"]) <= 15)
many_files = "\n".join(
    f'  File "core/module_{i}.py", line 1' for i in range(50))
result = extractor.extract("", many_files)
check("failing_files capped at 10", len(result["failing_files"]) <= 10)

print("\n[19] Extractor read-only guarantee")
for method in ["write","modify","patch","apply","execute","commit"]:
    check(f"EvidenceExtractor has no .{method}()", not hasattr(extractor, method))

print("\n[20] EngineeringDebugger Sprint 002 integration")
rep_full = debugger.analyse("python -m compileall core/", 1, "", SYNTAX_ERROR)
check("evidence.stack_trace is tuple", isinstance(rep_full.evidence.stack_trace, tuple))
check("evidence.failing_files is tuple", isinstance(rep_full.evidence.failing_files, tuple))
check("evidence.line_numbers is tuple", isinstance(rep_full.evidence.line_numbers, tuple))
check("evidence.error_type is string", isinstance(rep_full.evidence.error_type, str))
check("evidence.diagnostics is tuple", isinstance(rep_full.evidence.diagnostics, tuple))
check("SyntaxError error_type extracted",
      "SyntaxError" in rep_full.evidence.error_type)
check("line 77 extracted", 77 in rep_full.evidence.line_numbers)
check("router.py in failing files",
      any("router.py" in f for f in rep_full.evidence.failing_files))
check("diagnostics extracted", len(rep_full.evidence.diagnostics) > 0)
report_text = rep_full.report()
check("Sprint 002 report includes structured fields",
      any(section in report_text
          for section in ("Failing files", "Diagnostics", "Stack trace")))
print(f"    error_type:    {rep_full.evidence.error_type!r}")
print(f"    line_numbers:  {rep_full.evidence.line_numbers}")
print(f"    failing_files: {rep_full.evidence.failing_files}")
print(f"    diagnostics:   {len(rep_full.evidence.diagnostics)} line(s)")

print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 002: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now extract:")
print(f"  Stack traces  -> structured frames (file + line + context)")
print(f"  Failing files -> paths mentioned in output")
print(f"  Line numbers  -> from tracebacks and diagnostics")
print(f"  Error type    -> exception class name")
print(f"  Diagnostics   -> compiler/linter lines")
print(f"\nDesign principle:")
print(f"  Extract facts. Do not interpret. Do not propose fixes.")


# ── Sprint 003 — Root Cause Analysis ──────────────────────────────────────

from core.engineering.debugging.analyzer import RootCauseAnalyzer


def make_ev_for_analysis(error_type="", stderr_lines=(), exit_code=1,
                         diagnostics=(), stack_trace=(), failing_files=(),
                         line_numbers=()):
    """Build a FailureEvidence for RootCauseAnalyzer tests."""
    return FailureEvidence(
        command="cmd", exit_code=exit_code,
        stdout=(), stderr=tuple(stderr_lines),
        timestamp="2026-01-01T00:00:00+00:00",
        stack_trace=tuple(stack_trace),
        failing_files=tuple(failing_files),
        line_numbers=tuple(line_numbers),
        error_type=error_type,
        diagnostics=tuple(diagnostics),
    )


print("\n[21] RootCauseCategory enum")
check("SYNTAX_ERROR exists",      RootCauseCategory.SYNTAX_ERROR.value == "Syntax Error")
check("IMPORT_DEPENDENCY exists",  RootCauseCategory.IMPORT_DEPENDENCY.value == "Import Dependency")
check("MISSING_MODULE exists",     RootCauseCategory.MISSING_MODULE.value == "Missing Module")
check("CONFIGURATION exists",      RootCauseCategory.CONFIGURATION.value == "Configuration Error")
check("TEST_REGRESSION exists",    RootCauseCategory.TEST_REGRESSION.value == "Test Regression")
check("INVALID_API exists",        RootCauseCategory.INVALID_API.value == "Invalid API Usage")
check("MISSING_FILE exists",       RootCauseCategory.MISSING_FILE.value == "Missing File")
check("PERMISSION exists",         RootCauseCategory.PERMISSION.value == "Permission Error")
check("TIMEOUT exists",            RootCauseCategory.TIMEOUT.value == "Timeout")
check("UNKNOWN exists",            RootCauseCategory.UNKNOWN.value == "Unknown")
check("exactly 10 categories",     len(RootCauseCategory) == 10)


print("\n[22] RootCause — immutable model")
rc = RootCause(
    category=RootCauseCategory.SYNTAX_ERROR,
    description="Syntax error in core/router.py.",
    confidence=0.97,
    supporting_evidence=("SyntaxError: expected ':'",),
    contributing_factors=("Affected file: core/router.py", "Line(s) involved: 77"),
)
check("RootCause instantiates", rc is not None)
check("RootCause is frozen", rc.__dataclass_params__.frozen)
check("category is RootCauseCategory", isinstance(rc.category, RootCauseCategory))
check("confidence is float", isinstance(rc.confidence, float))
check("supporting_evidence is tuple", isinstance(rc.supporting_evidence, tuple))
check("contributing_factors is tuple", isinstance(rc.contributing_factors, tuple))
check("description is non-empty", bool(rc.description))

try:
    rc.category = RootCauseCategory.UNKNOWN
    check("RootCause fields are immutable", False)
except (AttributeError, TypeError):
    check("RootCause fields are immutable (raises on assignment)", True)

summary = rc.summary_line()
check("summary_line() is non-empty", bool(summary))
check("summary_line() contains category", "Syntax Error" in summary)
check("summary_line() contains confidence", "97%" in summary)
print(f"    {summary}")


print("\n[23] RootCauseAnalyzer — construction")
analyzer = RootCauseAnalyzer()
check("analyzer instantiates", analyzer is not None)

# Read-only guarantee
for method in ["write","modify","patch","apply","execute","commit","fix","repair"]:
    check(f"RootCauseAnalyzer has no .{method}()", not hasattr(analyzer, method))


print("\n[24] Root cause — SyntaxError")
ev = make_ev_for_analysis(
    error_type="SyntaxError",
    stderr_lines=("SyntaxError: expected ':'", "  File 'core/router.py', line 77"),
    diagnostics=("SyntaxError: expected ':'",),
    failing_files=("core/router.py",),
    line_numbers=(77,),
)
rc = analyzer.analyse(ev, FailureType.COMPILE)
check("SyntaxError → SYNTAX_ERROR", rc.category == RootCauseCategory.SYNTAX_ERROR)
check("SyntaxError confidence >= 0.95", rc.confidence >= 0.95)
check("description mentions syntax", "syntax" in rc.description.lower()
      or "router.py" in rc.description)
check("supporting_evidence is non-empty", len(rc.supporting_evidence) > 0)
print(f"    {rc.summary_line()}")


print("\n[25] Root cause — IndentationError")
ev = make_ev_for_analysis(error_type="IndentationError",
    stderr_lines=("IndentationError: unexpected indent",))
rc = analyzer.analyse(ev, FailureType.COMPILE)
check("IndentationError → SYNTAX_ERROR", rc.category == RootCauseCategory.SYNTAX_ERROR)
check("confidence >= 0.95", rc.confidence >= 0.95)


print("\n[26] Root cause — ModuleNotFoundError")
ev = make_ev_for_analysis(
    error_type="ModuleNotFoundError",
    stderr_lines=("ModuleNotFoundError: No module named 'core.reasoning.engine'",),
)
rc = analyzer.analyse(ev, FailureType.IMPORT)
check("ModuleNotFoundError → MISSING_MODULE", rc.category == RootCauseCategory.MISSING_MODULE)
check("MISSING_MODULE confidence >= 0.95", rc.confidence >= 0.95)
check("description mentions module", "core.reasoning.engine" in rc.description
      or "module" in rc.description.lower())
print(f"    {rc.summary_line()}")


print("\n[27] Root cause — ImportError")
ev = make_ev_for_analysis(
    error_type="ImportError",
    stderr_lines=("ImportError: cannot import name 'Agent' from 'core.agent'",),
)
rc = analyzer.analyse(ev, FailureType.IMPORT)
check("ImportError → IMPORT_DEPENDENCY", rc.category == RootCauseCategory.IMPORT_DEPENDENCY)
check("IMPORT_DEPENDENCY confidence >= 0.90", rc.confidence >= 0.90)


print("\n[28] Root cause — AssertionError (test regression)")
ev = make_ev_for_analysis(
    error_type="AssertionError",
    stderr_lines=("AssertionError: expected True, got False",),
)
rc = analyzer.analyse(ev, FailureType.TEST)
check("AssertionError → TEST_REGRESSION", rc.category == RootCauseCategory.TEST_REGRESSION)
check("TEST_REGRESSION confidence >= 0.85", rc.confidence >= 0.85)


print("\n[29] Root cause — pytest TEST failure (no error_type)")
ev = make_ev_for_analysis(
    error_type="",
    stderr_lines=("3 failed, 50 passed",),
)
rc = analyzer.analyse(ev, FailureType.TEST)
check("pytest failure fallback → TEST_REGRESSION",
      rc.category == RootCauseCategory.TEST_REGRESSION)
check("fallback confidence >= 0.75", rc.confidence >= 0.75)


print("\n[30] Root cause — Timeout")
ev = make_ev_for_analysis(
    error_type="TimeoutExpired",
    stderr_lines=("subprocess.TimeoutExpired: Command timed out",),
    exit_code=1,
)
rc = analyzer.analyse(ev, FailureType.TIMEOUT)
check("TimeoutExpired → TIMEOUT", rc.category == RootCauseCategory.TIMEOUT)
check("TIMEOUT confidence = 1.0", rc.confidence == 1.0)


print("\n[31] Root cause — AttributeError (invalid API)")
ev = make_ev_for_analysis(
    error_type="AttributeError",
    stderr_lines=("AttributeError: 'NoneType' has no attribute 'infer'",),
)
rc = analyzer.analyse(ev, FailureType.UNKNOWN)
check("AttributeError → INVALID_API", rc.category == RootCauseCategory.INVALID_API)
check("INVALID_API confidence >= 0.80", rc.confidence >= 0.80)


print("\n[32] Root cause — KeyError (configuration)")
ev = make_ev_for_analysis(
    error_type="KeyError",
    stderr_lines=("KeyError: 'OPENAI_API_KEY'",),
)
rc = analyzer.analyse(ev, FailureType.CONFIGURATION)
check("KeyError → CONFIGURATION", rc.category == RootCauseCategory.CONFIGURATION)
check("CONFIGURATION confidence >= 0.80", rc.confidence >= 0.80)


print("\n[33] Root cause — UNKNOWN (insufficient evidence)")
ev = make_ev_for_analysis(error_type="", stderr_lines=("something went wrong",))
rc = analyzer.analyse(ev, FailureType.UNKNOWN)
check("no pattern → UNKNOWN", rc.category == RootCauseCategory.UNKNOWN)
check("UNKNOWN confidence = 0.0", rc.confidence == 0.0)
check("UNKNOWN supporting_evidence is empty", rc.supporting_evidence == ())


print("\n[34] Root cause — exit_code=0 (not a failure)")
ev = make_ev_for_analysis(error_type="", exit_code=0)
rc = analyzer.analyse(ev, FailureType.UNKNOWN)
check("exit_code=0 → UNKNOWN", rc.category == RootCauseCategory.UNKNOWN)
check("exit_code=0 confidence = 0.0", rc.confidence == 0.0)


print("\n[35] Contributing factors")
ev = make_ev_for_analysis(
    error_type="SyntaxError",
    stderr_lines=("SyntaxError: expected ':'",
                  "  File 'core/router.py', line 77"),
    failing_files=("core/router.py",),
    line_numbers=(77,),
)
rc = analyzer.analyse(ev, FailureType.COMPILE)
check("contributing_factors is a tuple", isinstance(rc.contributing_factors, tuple))
check("failing file appears in factors",
      any("router.py" in f for f in rc.contributing_factors))
check("line number appears in factors",
      any("77" in f for f in rc.contributing_factors))
print(f"    Factors: {rc.contributing_factors}")


print("\n[36] Determinism — same evidence always yields same result")
ev = make_ev_for_analysis(
    error_type="ModuleNotFoundError",
    stderr_lines=("ModuleNotFoundError: No module named 'openai'",),
)
results = set()
for _ in range(20):
    r = analyzer.analyse(ev, FailureType.IMPORT)
    results.add((r.category, r.confidence))
check("root cause analysis is deterministic (20 runs)", len(results) == 1)


print("\n[37] EngineeringDebugger — Sprint 003 integration")
debugger2 = EngineeringDebugger()

rep_s3 = debugger2.analyse(
    command="python -m compileall core/",
    exit_code=1,
    stdout="",
    stderr="SyntaxError: expected ':'\n  File \"core/router.py\", line 77",
)
check("DebugReport has root_cause field", hasattr(rep_s3, "root_cause"))
check("root_cause is a RootCause", isinstance(rep_s3.root_cause, RootCause))
check("root_cause.category is RootCauseCategory",
      isinstance(rep_s3.root_cause.category, RootCauseCategory))
check("SyntaxError → SYNTAX_ERROR via full pipeline",
      rep_s3.root_cause.category == RootCauseCategory.SYNTAX_ERROR)
check("root_cause.confidence > 0", rep_s3.root_cause.confidence > 0.0)

rep_import = debugger2.analyse(
    command="python tests/test_reasoning.py", exit_code=1, stdout="",
    stderr="ModuleNotFoundError: No module named 'core.reasoning.engine'",
)
check("ModuleNotFoundError → MISSING_MODULE via pipeline",
      rep_import.root_cause.category == RootCauseCategory.MISSING_MODULE)

rep_test = debugger2.analyse(
    command="python -m pytest tests/", exit_code=1,
    stdout="FAILED tests/test_edge_cases.py::test_store\n3 failed", stderr="",
)
check("pytest failure → TEST_REGRESSION via pipeline",
      rep_test.root_cause.category == RootCauseCategory.TEST_REGRESSION)

rep_unknown = debugger2.analyse("cmd", 1, "", "something went wrong")
check("unknown failure → UNKNOWN root cause",
      rep_unknown.root_cause.category == RootCauseCategory.UNKNOWN)
check("UNKNOWN root_cause.confidence = 0.0",
      rep_unknown.root_cause.confidence == 0.0)


print("\n[38] DebugReport.report() includes root cause")
report_text = rep_s3.report()
check("report contains 'Root Cause' section", "Root Cause" in report_text)
check("report contains category name", "Syntax Error" in report_text)
check("report contains confidence", "97%" in report_text or "95%" in report_text
      or str(int(rep_s3.root_cause.confidence * 100)) + "%" in report_text)
print(f"    Root cause line: {rep_s3.root_cause.summary_line()}")
print(f"    Full report length: {len(report_text)} chars")


print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 003: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'Why did this failure happen?'")
print(f"\nRoot cause categories:")
for cat in RootCauseCategory:
    print(f"  {cat.value}")
print(f"\nEngineering pipeline:")
print(f"  Evidence → Classification → Root Cause → Report")
print(f"\nDesign principle:")
print(f"  Evidence → Root Cause  (not: Failure → Guess)")
print(f"\nDeferred to later sprints:")
print(f"  Failure correlation, repair planning, autonomous fix")


# ── Sprint 004 — Failure Correlation ──────────────────────────────────────

from core.engineering.debugging.engine import FailureCorrelationEngine, FailureRecord


def make_record(**kwargs) -> FailureRecord:
    """Build a FailureRecord for history."""
    defaults = dict(
        failure_type=FailureType.UNKNOWN,
        root_cause_category=RootCauseCategory.UNKNOWN,
        error_type="", failing_files=(),
        commit="", timestamp="", description="",
    )
    defaults.update(kwargs)
    return FailureRecord(**defaults)


def make_ev_corr(error_type="", failing_files=(), exit_code=1,
                 stderr_lines=()) -> FailureEvidence:
    """Build minimal FailureEvidence for correlation tests."""
    return FailureEvidence(
        command="cmd", exit_code=exit_code,
        stdout=(), stderr=tuple(stderr_lines),
        timestamp="2026-01-15T10:00:00+00:00",
        stack_trace=(), failing_files=tuple(failing_files),
        line_numbers=(), error_type=error_type, diagnostics=(),
    )


def make_rc(category=RootCauseCategory.UNKNOWN) -> RootCause:
    return RootCause(category=category, description="test",
                     confidence=0.9, supporting_evidence=(),
                     contributing_factors=())


print("\n[39] CorrelationType enum")
check("SAME_FILE exists",        CorrelationType.SAME_FILE.value == "Same File")
check("SAME_MODULE exists",      CorrelationType.SAME_MODULE.value == "Same Module")
check("SAME_EXCEPTION exists",   CorrelationType.SAME_EXCEPTION.value == "Same Exception")
check("SAME_ROOT_CAUSE exists",  CorrelationType.SAME_ROOT_CAUSE.value == "Same Root Cause")
check("SAME_COMMIT exists",      CorrelationType.SAME_COMMIT.value == "Same Commit")
check("REPEATED_FAILURE exists", CorrelationType.REPEATED_FAILURE.value == "Repeated Failure")
check("UNKNOWN exists",          CorrelationType.UNKNOWN.value == "Unknown")
check("exactly 7 types",         len(CorrelationType) == 7)


print("\n[40] CorrelationRecord — immutable model")
cr = CorrelationRecord(
    correlation_type=CorrelationType.REPEATED_FAILURE,
    confidence=0.97,
    description="SyntaxError has occurred 3 times.",
    related_failures=("Sprint 001 SyntaxError", "Sprint 002 SyntaxError"),
    related_files=("core/router.py",),
    related_modules=("core",),
    related_commits=("abc1234",),
    timeline=("2026-01-01: First", "2026-01-15: Current"),
)
check("CorrelationRecord instantiates", cr is not None)
check("CorrelationRecord is frozen", cr.__dataclass_params__.frozen)
check("correlation_type is CorrelationType",
      isinstance(cr.correlation_type, CorrelationType))
check("confidence is float", isinstance(cr.confidence, float))
check("related_failures is tuple", isinstance(cr.related_failures, tuple))
check("related_files is tuple", isinstance(cr.related_files, tuple))
check("related_modules is tuple", isinstance(cr.related_modules, tuple))
check("related_commits is tuple", isinstance(cr.related_commits, tuple))
check("timeline is tuple", isinstance(cr.timeline, tuple))
check("is_correlated True for REPEATED_FAILURE", cr.is_correlated)

cr_unknown = CorrelationRecord(
    correlation_type=CorrelationType.UNKNOWN, confidence=0.0,
    description="none", related_failures=(), related_files=(),
    related_modules=(), related_commits=(), timeline=(),
)
check("is_correlated False for UNKNOWN", not cr_unknown.is_correlated)

try:
    cr.correlation_type = CorrelationType.UNKNOWN
    check("CorrelationRecord is immutable", False)
except (AttributeError, TypeError):
    check("CorrelationRecord is immutable (raises on assignment)", True)

summary = cr.summary_line()
check("summary_line() non-empty", bool(summary))
check("summary_line() contains type", "Repeated Failure" in summary)
check("summary_line() for UNKNOWN says no correlation",
      "No correlation" in cr_unknown.summary_line())
print(f"    {summary}")


print("\n[41] FailureCorrelationEngine — construction")
engine = FailureCorrelationEngine()
check("engine instantiates", engine is not None)
for method in ["write","modify","patch","fix","repair","execute","commit"]:
    check(f"engine has no .{method}()", not hasattr(engine, method))


print("\n[42] No history → UNKNOWN")
ev = make_ev_corr("SyntaxError", ("core/router.py",))
rc = make_rc(RootCauseCategory.SYNTAX_ERROR)
result = engine.correlate(ev, rc, FailureType.COMPILE, history=None)
check("no history → UNKNOWN", result.correlation_type == CorrelationType.UNKNOWN)
check("no history → confidence=0.0", result.confidence == 0.0)
check("no history → is_correlated False", not result.is_correlated)

result2 = engine.correlate(ev, rc, FailureType.COMPILE, history=[])
check("empty history → UNKNOWN", result2.correlation_type == CorrelationType.UNKNOWN)


print("\n[43] exit_code=0 → UNKNOWN")
ev_ok = make_ev_corr("SyntaxError", ("core/router.py",), exit_code=0)
history = [make_record(failure_type=FailureType.COMPILE,
                       root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                       error_type="SyntaxError")]
result = engine.correlate(ev_ok, rc, FailureType.COMPILE, history=history)
check("exit_code=0 → UNKNOWN", result.correlation_type == CorrelationType.UNKNOWN)


print("\n[44] REPEATED_FAILURE detection")
history = [
    make_record(failure_type=FailureType.COMPILE,
                root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                description="Router syntax error Jan 10"),
    make_record(failure_type=FailureType.COMPILE,
                root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                description="Router syntax error Jan 12"),
]
ev = make_ev_corr("SyntaxError", ("core/router.py",))
rc = make_rc(RootCauseCategory.SYNTAX_ERROR)
result = engine.correlate(ev, rc, FailureType.COMPILE, history=history)
check("repeated SyntaxError → REPEATED_FAILURE",
      result.correlation_type == CorrelationType.REPEATED_FAILURE)
check("REPEATED_FAILURE confidence >= 0.95", result.confidence >= 0.95)
check("related_failures contains history descriptions",
      "Router syntax error Jan 10" in result.related_failures)
check("description mentions count", "3" in result.description or "2" in result.description)
print(f"    {result.summary_line()}")


print("\n[45] SAME_COMMIT detection")
history = [
    make_record(commit="abc1234", description="Failure after abc1234"),
]
ev = make_ev_corr(stderr_lines=("Error in commit abc1234",))
rc = make_rc()
result = engine.correlate(ev, rc, FailureType.UNKNOWN, history=history)
check("shared commit → SAME_COMMIT",
      result.correlation_type == CorrelationType.SAME_COMMIT)
check("SAME_COMMIT confidence >= 0.93", result.confidence >= 0.93)
check("commit hash in related_commits", "abc1234" in result.related_commits)
print(f"    {result.summary_line()}")


print("\n[46] SAME_ROOT_CAUSE detection")
history = [
    make_record(root_cause_category=RootCauseCategory.MISSING_MODULE,
                description="Missing openai module"),
]
ev = make_ev_corr("ModuleNotFoundError", ("tests/test_ai.py",))
rc = make_rc(RootCauseCategory.MISSING_MODULE)
result = engine.correlate(ev, rc, FailureType.IMPORT, history=history)
check("same root cause → SAME_ROOT_CAUSE",
      result.correlation_type == CorrelationType.SAME_ROOT_CAUSE)
check("SAME_ROOT_CAUSE confidence >= 0.88", result.confidence >= 0.88)
print(f"    {result.summary_line()}")


print("\n[47] SAME_EXCEPTION detection")
history = [
    make_record(error_type="AttributeError",
                description="AttributeError in skills"),
]
ev = make_ev_corr("AttributeError", ("core/skills/reasoning.py",))
rc = make_rc(RootCauseCategory.INVALID_API)
result = engine.correlate(ev, rc, FailureType.UNKNOWN, history=history)
check("same exception → SAME_EXCEPTION",
      result.correlation_type == CorrelationType.SAME_EXCEPTION)
check("SAME_EXCEPTION confidence >= 0.85", result.confidence >= 0.85)
check("error type in description", "AttributeError" in result.description)
print(f"    {result.summary_line()}")


print("\n[48] SAME_FILE detection")
history = [
    make_record(failing_files=("core/router.py",),
                description="Router failure last week"),
]
ev = make_ev_corr(failing_files=("core/router.py", "core/agent.py"))
rc = make_rc()
result = engine.correlate(ev, rc, FailureType.UNKNOWN, history=history)
check("shared file → SAME_FILE",
      result.correlation_type == CorrelationType.SAME_FILE)
check("SAME_FILE confidence >= 0.83", result.confidence >= 0.83)
check("shared file in related_files", "core/router.py" in result.related_files)
print(f"    {result.summary_line()}")


print("\n[49] SAME_MODULE detection")
history = [
    make_record(failing_files=("core/skills/memory.py",),
                description="Memory skill failure"),
]
ev = make_ev_corr(failing_files=("core/skills/reasoning.py",))
rc = make_rc()
result = engine.correlate(ev, rc, FailureType.UNKNOWN, history=history)
check("same module → SAME_MODULE",
      result.correlation_type == CorrelationType.SAME_MODULE)
check("SAME_MODULE confidence >= 0.78", result.confidence >= 0.78)
check("shared module in related_modules",
      any("core.skills" in m for m in result.related_modules))
print(f"    {result.summary_line()}")


print("\n[50] Priority ordering — REPEATED_FAILURE beats SAME_FILE")
history = [
    make_record(failure_type=FailureType.COMPILE,
                root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                failing_files=("core/router.py",),
                description="Previous syntax error"),
]
ev = make_ev_corr("SyntaxError", ("core/router.py",))
rc = make_rc(RootCauseCategory.SYNTAX_ERROR)
result = engine.correlate(ev, rc, FailureType.COMPILE, history=history)
check("REPEATED_FAILURE takes priority over SAME_FILE",
      result.correlation_type == CorrelationType.REPEATED_FAILURE)


print("\n[51] No correlation — unrelated failure")
history = [
    make_record(failure_type=FailureType.COMPILE,
                root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                error_type="SyntaxError",
                failing_files=("core/router.py",),
                description="Unrelated syntax error"),
]
ev = make_ev_corr("", ("tests/test_knowledge_engine.py",))
rc = make_rc(RootCauseCategory.UNKNOWN)
result = engine.correlate(ev, rc, FailureType.UNKNOWN, history=history)
check("unrelated failure → UNKNOWN", result.correlation_type == CorrelationType.UNKNOWN)
check("no false correlation", not result.is_correlated)


print("\n[52] Determinism")
history = [make_record(failure_type=FailureType.COMPILE,
                       root_cause_category=RootCauseCategory.SYNTAX_ERROR,
                       description="Previous")]
ev = make_ev_corr("SyntaxError")
rc = make_rc(RootCauseCategory.SYNTAX_ERROR)
results = set()
for _ in range(20):
    r = engine.correlate(ev, rc, FailureType.COMPILE, history=history)
    results.add((r.correlation_type, r.confidence))
check("correlation is deterministic (20 runs)", len(results) == 1)


print("\n[53] EngineeringDebugger Sprint 004 integration")
from core.engineering.debugging.engine import FailureRecord as FR

history_s4 = [
    FR(failure_type=FailureType.COMPILE,
       root_cause_category=RootCauseCategory.SYNTAX_ERROR,
       error_type="SyntaxError",
       failing_files=("core/router.py",),
       description="Previous router syntax error",
       timestamp="2026-01-10T09:00:00+00:00"),
]
debugger_s4 = EngineeringDebugger(history=history_s4)

rep_s4 = debugger_s4.analyse(
    command="python -m compileall core/",
    exit_code=1, stdout="",
    stderr='SyntaxError: expected \':\'\n  File "core/router.py", line 77',
)
check("DebugReport has correlation field", hasattr(rep_s4, "correlation"))
check("correlation is a CorrelationRecord",
      isinstance(rep_s4.correlation, CorrelationRecord))
check("correlation_type is CorrelationType",
      isinstance(rep_s4.correlation.correlation_type, CorrelationType))
check("repeated syntax error detected",
      rep_s4.correlation.correlation_type == CorrelationType.REPEATED_FAILURE)
check("correlation confidence > 0", rep_s4.correlation.confidence > 0.0)
print(f"    {rep_s4.correlation.summary_line()}")

# No history → no correlation
debugger_no_hist = EngineeringDebugger()
rep_no_hist = debugger_no_hist.analyse("cmd", 1, "", "SyntaxError")
check("no history → UNKNOWN correlation",
      rep_no_hist.correlation.correlation_type == CorrelationType.UNKNOWN)


print("\n[54] DebugReport.report() includes correlation")
report_text = rep_s4.report()
check("report contains 'Correlation' section", "Correlation" in report_text)
check("report contains correlation type",
      "Repeated Failure" in report_text)
print(f"    Full report length: {len(report_text)} chars")
# Print the correlation section
for line in report_text.splitlines():
    if "Correlation" in line or "Repeated" in line:
        print(f"    {line.strip()}")


print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 004: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'Has this failure happened before?'")
print(f"  'Is it related to previous engineering activity?'")
print(f"\nCorrelation types:")
for ct in CorrelationType:
    print(f"  {ct.value}")
print(f"\nEngineering pipeline:")
print(f"  Evidence → Classification → Root Cause → Correlation → Report")
print(f"\nDesign principle:")
print(f"  Observe history. Detect patterns. Never guess. Never repair.")
print(f"\nDeferred to later sprints:")
print(f"  Engineering recommendations, repair planning, autonomous fix")


# ── Sprint 005 — Engineering Recommendations ───────────────────────────────

from core.engineering.debugging.rec_engine import RecommendationEngine
from core.engineering.debugging.engine import FailureRecord as FR2


def make_corr(ct=CorrelationType.UNKNOWN, confidence=0.0,
              related_files=(), related_commits=(),
              related_failures=()) -> CorrelationRecord:
    desc = "no correlation" if ct == CorrelationType.UNKNOWN else "correlated"
    return CorrelationRecord(
        correlation_type=ct, confidence=confidence,
        description=desc, related_failures=tuple(related_failures),
        related_files=tuple(related_files), related_modules=(),
        related_commits=tuple(related_commits), timeline=(),
    )


def make_ev_rec(error_type="", failing_files=(), line_numbers=(),
                exit_code=1, diagnostics=()) -> FailureEvidence:
    return FailureEvidence(
        command="cmd", exit_code=exit_code,
        stdout=(), stderr=(),
        timestamp="2026-01-15T10:00:00+00:00",
        stack_trace=(), failing_files=tuple(failing_files),
        line_numbers=tuple(line_numbers),
        error_type=error_type, diagnostics=tuple(diagnostics),
    )


def make_root(category=RootCauseCategory.UNKNOWN,
              supporting=()) -> RootCause:
    return RootCause(category=category, description="test",
                     confidence=0.9, supporting_evidence=tuple(supporting),
                     contributing_factors=())


print("\n[55] RecommendationCategory enum")
check("INVESTIGATE_SYNTAX exists",
      RecommendationCategory.INVESTIGATE_SYNTAX.value == "Investigate Syntax")
check("VERIFY_IMPORTS exists",
      RecommendationCategory.VERIFY_IMPORTS.value == "Verify Imports")
check("CHECK_CONFIGURATION exists",
      RecommendationCategory.CHECK_CONFIGURATION.value == "Check Configuration")
check("REVIEW_RECENT_COMMITS exists",
      RecommendationCategory.REVIEW_RECENT_COMMITS.value == "Review Recent Commits")
check("REVIEW_TEST_FAILURES exists",
      RecommendationCategory.REVIEW_TEST_FAILURES.value == "Review Test Failures")
check("VERIFY_DEPENDENCIES exists",
      RecommendationCategory.VERIFY_DEPENDENCIES.value == "Verify Dependencies")
check("CHECK_FILE_EXISTENCE exists",
      RecommendationCategory.CHECK_FILE_EXISTENCE.value == "Check File Existence")
check("REVIEW_API_USAGE exists",
      RecommendationCategory.REVIEW_API_USAGE.value == "Review API Usage")
check("MONITOR_REPEATED_FAILURES exists",
      RecommendationCategory.MONITOR_REPEATED_FAILURES.value == "Monitor Repeated Failures")
check("NO_RECOMMENDATION exists",
      RecommendationCategory.NO_RECOMMENDATION.value == "No Recommendation")
check("exactly 10 categories", len(RecommendationCategory) == 10)


print("\n[56] RecommendationPriority enum")
check("LOW exists",      RecommendationPriority.LOW.value == "Low")
check("MEDIUM exists",   RecommendationPriority.MEDIUM.value == "Medium")
check("HIGH exists",     RecommendationPriority.HIGH.value == "High")
check("CRITICAL exists", RecommendationPriority.CRITICAL.value == "Critical")
check("exactly 4 priorities", len(RecommendationPriority) == 4)


print("\n[57] Recommendation — immutable model")
rec = Recommendation(
    category=RecommendationCategory.INVESTIGATE_SYNTAX,
    priority=RecommendationPriority.HIGH,
    confidence=0.95,
    title="Investigate syntax error",
    description="A syntax error was detected in core/router.py at line 77.",
    supporting_evidence=("SyntaxError: expected ':'",),
    related_root_cause="Syntax Error",
    related_correlation="",
)
check("Recommendation instantiates", rec is not None)
check("Recommendation is frozen", rec.__dataclass_params__.frozen)
check("category is RecommendationCategory",
      isinstance(rec.category, RecommendationCategory))
check("priority is RecommendationPriority",
      isinstance(rec.priority, RecommendationPriority))
check("confidence is float", isinstance(rec.confidence, float))
check("supporting_evidence is tuple", isinstance(rec.supporting_evidence, tuple))
check("title is non-empty", bool(rec.title))
check("description is non-empty", bool(rec.description))

try:
    rec.category = RecommendationCategory.NO_RECOMMENDATION
    check("Recommendation is immutable", False)
except (AttributeError, TypeError):
    check("Recommendation is immutable (raises on assignment)", True)

summary = rec.summary_line()
check("summary_line() non-empty", bool(summary))
check("summary_line() contains priority", "HIGH" in summary)
check("summary_line() contains title", "syntax" in summary.lower())
print(f"    {summary}")


print("\n[58] RecommendationEngine — construction")
rec_engine = RecommendationEngine()
check("engine instantiates", rec_engine is not None)
for method in ["write","modify","patch","fix","repair","execute","generate"]:
    check(f"engine has no .{method}()", not hasattr(rec_engine, method))


print("\n[59] exit_code=0 → no recommendations")
ev = make_ev_rec(exit_code=0)
rc = make_root()
corr = make_corr()
recs = rec_engine.recommend(ev, FailureType.UNKNOWN, rc, corr)
check("exit_code=0 → empty recommendations", recs == ())


print("\n[60] SyntaxError → INVESTIGATE_SYNTAX")
ev = make_ev_rec("SyntaxError", ("core/router.py",), (77,))
rc = make_root(RootCauseCategory.SYNTAX_ERROR, ("SyntaxError: expected ':'",))
corr = make_corr()
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
check("SyntaxError produces recommendations", len(recs) > 0)
check("INVESTIGATE_SYNTAX recommended",
      any(r.category == RecommendationCategory.INVESTIGATE_SYNTAX for r in recs))
check("HIGH or CRITICAL priority for syntax",
      any(r.priority in (RecommendationPriority.HIGH, RecommendationPriority.CRITICAL)
          for r in recs))
check("supporting_evidence references error",
      any("SyntaxError" in e for r in recs for e in r.supporting_evidence))
check("related_root_cause set", any(r.related_root_cause for r in recs))
print(f"    {recs[0].summary_line()}")


print("\n[61] MissingModule → VERIFY_DEPENDENCIES")
ev = make_ev_rec("ModuleNotFoundError", ("tests/test_reasoning.py",))
rc = make_root(RootCauseCategory.MISSING_MODULE,
               ("ModuleNotFoundError: No module named 'core.reasoning'",))
recs = rec_engine.recommend(ev, FailureType.IMPORT, rc, make_corr())
check("MissingModule → VERIFY_DEPENDENCIES",
      any(r.category == RecommendationCategory.VERIFY_DEPENDENCIES for r in recs))
check("HIGH priority", any(r.priority == RecommendationPriority.HIGH for r in recs))
print(f"    {recs[0].summary_line()}")


print("\n[62] TestRegression → REVIEW_TEST_FAILURES")
ev = make_ev_rec("AssertionError")
rc = make_root(RootCauseCategory.TEST_REGRESSION)
recs = rec_engine.recommend(ev, FailureType.TEST, rc, make_corr())
check("TestRegression → REVIEW_TEST_FAILURES",
      any(r.category == RecommendationCategory.REVIEW_TEST_FAILURES for r in recs))
print(f"    {recs[0].summary_line()}")


print("\n[63] Configuration → CHECK_CONFIGURATION")
ev = make_ev_rec("KeyError")
rc = make_root(RootCauseCategory.CONFIGURATION)
recs = rec_engine.recommend(ev, FailureType.CONFIGURATION, rc, make_corr())
check("Configuration → CHECK_CONFIGURATION",
      any(r.category == RecommendationCategory.CHECK_CONFIGURATION for r in recs))
print(f"    {recs[0].summary_line()}")


print("\n[64] Correlation REPEATED_FAILURE → MONITOR + CRITICAL")
ev = make_ev_rec("SyntaxError", ("core/router.py",))
rc = make_root(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr(CorrelationType.REPEATED_FAILURE, 0.97,
                 related_files=("core/router.py",),
                 related_failures=("Previous syntax error",))
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
check("REPEATED_FAILURE → MONITOR_REPEATED_FAILURES recommendation",
      any(r.category == RecommendationCategory.MONITOR_REPEATED_FAILURES
          for r in recs))
check("CRITICAL priority for repeated failure",
      any(r.priority == RecommendationPriority.CRITICAL for r in recs))
check("related_correlation set",
      any(r.related_correlation for r in recs))
print(f"    {recs[0].summary_line()}")


print("\n[65] Correlation SAME_COMMIT → REVIEW_RECENT_COMMITS")
ev = make_ev_rec("SyntaxError")
rc = make_root(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr(CorrelationType.SAME_COMMIT, 0.95,
                 related_commits=("abc1234",))
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
check("SAME_COMMIT → REVIEW_RECENT_COMMITS",
      any(r.category == RecommendationCategory.REVIEW_RECENT_COMMITS for r in recs))
check("commit in supporting evidence",
      any("abc1234" in e for r in recs for e in r.supporting_evidence))
print(f"    Recommendations: {len(recs)}")
for r in recs:
    print(f"      {r.summary_line()}")


print("\n[66] Priority ordering — CRITICAL before HIGH")
ev = make_ev_rec("SyntaxError", ("core/router.py",))
rc = make_root(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr(CorrelationType.REPEATED_FAILURE, 0.97,
                 related_failures=("Previous",))
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
check("at least 2 recommendations", len(recs) >= 2)
priorities = [r.priority for r in recs]
priority_order = [RecommendationPriority.CRITICAL, RecommendationPriority.HIGH,
                  RecommendationPriority.MEDIUM, RecommendationPriority.LOW]
check("recommendations sorted by priority (CRITICAL first)",
      all(priority_order.index(priorities[i]) <=
          priority_order.index(priorities[i+1])
          for i in range(len(priorities)-1)))


print("\n[67] No duplicate categories")
ev = make_ev_rec("SyntaxError", ("core/router.py",))
rc = make_root(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr(CorrelationType.SAME_FILE, 0.85,
                 related_files=("core/router.py",))
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
categories = [r.category for r in recs]
check("no duplicate recommendation categories",
      len(categories) == len(set(categories)))


print("\n[68] UNKNOWN root cause with no correlation → empty")
ev = make_ev_rec("", exit_code=1)
rc = make_root(RootCauseCategory.UNKNOWN)
corr = make_corr()
recs = rec_engine.recommend(ev, FailureType.UNKNOWN, rc, corr)
check("UNKNOWN + no correlation → empty recommendations", recs == ())


print("\n[69] Determinism")
ev = make_ev_rec("ModuleNotFoundError", ("core/reasoning/engine.py",))
rc = make_root(RootCauseCategory.MISSING_MODULE,
               ("ModuleNotFoundError: No module named 'core.reasoning'",))
corr = make_corr()
results = set()
for _ in range(20):
    recs = rec_engine.recommend(ev, FailureType.IMPORT, rc, corr)
    results.add(tuple((r.category, r.priority, r.confidence) for r in recs))
check("recommendations are deterministic (20 runs)", len(results) == 1)


print("\n[70] All recommendations have supporting evidence")
ev = make_ev_rec("SyntaxError", ("core/router.py",), (77,))
rc = make_root(RootCauseCategory.SYNTAX_ERROR, ("SyntaxError: expected ':'",))
corr = make_corr(CorrelationType.REPEATED_FAILURE, 0.97,
                 related_failures=("Previous error",))
recs = rec_engine.recommend(ev, FailureType.COMPILE, rc, corr)
check("all recommendations have supporting_evidence",
      all(isinstance(r.supporting_evidence, tuple) for r in recs))
check("all recommendations have non-empty title",
      all(bool(r.title) for r in recs))
check("all recommendations have non-empty description",
      all(bool(r.description) for r in recs))
check("all recommendations reference root cause or correlation",
      all(r.related_root_cause or r.related_correlation for r in recs))


print("\n[71] EngineeringDebugger Sprint 005 integration")
history_s5 = [
    FR2(failure_type=FailureType.COMPILE,
        root_cause_category=RootCauseCategory.SYNTAX_ERROR,
        error_type="SyntaxError",
        failing_files=("core/router.py",),
        description="Previous router syntax error"),
]
debugger_s5 = EngineeringDebugger(history=history_s5)
rep_s5 = debugger_s5.analyse(
    command="python -m compileall core/",
    exit_code=1, stdout="",
    stderr='SyntaxError: expected \':\'\n  File "core/router.py", line 77',
)
check("DebugReport has recommendations field", hasattr(rep_s5, "recommendations"))
check("recommendations is a tuple", isinstance(rep_s5.recommendations, tuple))
check("recommendations non-empty for real failure",
      len(rep_s5.recommendations) > 0)
check("all items are Recommendation objects",
      all(isinstance(r, Recommendation) for r in rep_s5.recommendations))
check("INVESTIGATE_SYNTAX in recommendations",
      any(r.category == RecommendationCategory.INVESTIGATE_SYNTAX
          for r in rep_s5.recommendations))
print(f"    Recommendations produced: {len(rep_s5.recommendations)}")
for r in rep_s5.recommendations:
    print(f"      {r.summary_line()}")

debugger_no_fail = EngineeringDebugger()
rep_ok = debugger_no_fail.analyse("cmd", 0, "all good", "")
check("exit_code=0 → empty recommendations", rep_ok.recommendations == ())


print("\n[72] DebugReport.report() includes recommendations")
report_text = rep_s5.report()
check("report contains 'Recommendations' section",
      "Recommendations" in report_text)
check("report contains recommendation title",
      any(r.title.lower()[:10] in report_text.lower()
          for r in rep_s5.recommendations))
check("report note says Chief approval required",
      "Chief approval" in report_text or "advisory" in report_text.lower())
print(f"    Full report length: {len(report_text)} chars")
for line in report_text.splitlines():
    if "Recommendation" in line or "[HIGH]" in line or "[CRITICAL]" in line:
        print(f"    {line.strip()}")


print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 005: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'What engineering actions should be considered?'")
print(f"\nRecommendation categories:")
for cat in RecommendationCategory:
    if cat != RecommendationCategory.NO_RECOMMENDATION:
        print(f"  {cat.value}")
print(f"\nFull engineering pipeline:")
print(f"  Evidence → Classification → Root Cause → Correlation")
print(f"  → Recommendations → Report")
print(f"\nDesign principle:")
print(f"  Advisory only. Evidence-backed. Never repairs. Never guesses.")
print(f"\nDeferred to Sprint 006:")
print(f"  Repair Planning — consuming recommendations to plan fixes")


# ── Sprint 006 — Repair Planning ───────────────────────────────────────────

from core.engineering.debugging.planner import RepairPlanner
from core.engineering.debugging.engine import FailureRecord as FR3


def make_ev_plan(error_type="", failing_files=(), line_numbers=(),
                 exit_code=1) -> FailureEvidence:
    return FailureEvidence(
        command="cmd", exit_code=exit_code,
        stdout=(), stderr=(),
        timestamp="2026-01-15T10:00:00+00:00",
        stack_trace=(), failing_files=tuple(failing_files),
        line_numbers=tuple(line_numbers),
        error_type=error_type, diagnostics=(),
    )


def make_rc_plan(category=RootCauseCategory.UNKNOWN,
                 confidence=0.9) -> RootCause:
    return RootCause(category=category, description="test",
                     confidence=confidence, supporting_evidence=(),
                     contributing_factors=())


def make_corr_plan(ct=CorrelationType.UNKNOWN, files=(),
                   commits=(), failures=()) -> CorrelationRecord:
    return CorrelationRecord(
        correlation_type=ct,
        confidence=0.0 if ct == CorrelationType.UNKNOWN else 0.9,
        description="test",
        related_failures=tuple(failures),
        related_files=tuple(files),
        related_modules=(),
        related_commits=tuple(commits),
        timeline=(),
    )


def make_rec(category=RecommendationCategory.INVESTIGATE_SYNTAX,
             priority=RecommendationPriority.HIGH,
             confidence=0.95, title="Investigate") -> Recommendation:
    return Recommendation(
        category=category, priority=priority,
        confidence=confidence, title=title,
        description="test recommendation",
        supporting_evidence=(), related_root_cause="", related_correlation="",
    )


print("\n[73] RepairRisk enum")
check("LOW exists",      RepairRisk.LOW.value == "Low")
check("MEDIUM exists",   RepairRisk.MEDIUM.value == "Medium")
check("HIGH exists",     RepairRisk.HIGH.value == "High")
check("CRITICAL exists", RepairRisk.CRITICAL.value == "Critical")
check("exactly 4 risk levels", len(RepairRisk) == 4)


print("\n[74] RepairEffort enum")
check("MINOR exists",    RepairEffort.MINOR.value == "Minor")
check("SMALL exists",    RepairEffort.SMALL.value == "Small")
check("MODERATE exists", RepairEffort.MODERATE.value == "Moderate")
check("LARGE exists",    RepairEffort.LARGE.value == "Large")
check("MAJOR exists",    RepairEffort.MAJOR.value == "Major")
check("exactly 5 effort levels", len(RepairEffort) == 5)


print("\n[75] RepairStep — immutable model")
step = RepairStep(
    order=1, title="Review the syntax error",
    description="Locate and correct the syntax error in core/router.py at line 77.",
    depends_on=(),
)
check("RepairStep instantiates", step is not None)
check("RepairStep is frozen", step.__dataclass_params__.frozen)
check("order is int", isinstance(step.order, int))
check("title is non-empty", bool(step.title))
check("description is non-empty", bool(step.description))
check("depends_on is tuple", isinstance(step.depends_on, tuple))
try:
    step.order = 2
    check("RepairStep is immutable", False)
except (AttributeError, TypeError):
    check("RepairStep is immutable (raises on assignment)", True)


print("\n[76] RepairPlan — immutable model")
plan = RepairPlan(
    title="Repair Plan: Syntax Error",
    summary="Fix syntax error in core/router.py.",
    confidence=0.95,
    steps=(step,),
    validation_steps=("Run compileall", "Run pytest"),
    estimated_risk=RepairRisk.LOW,
    estimated_effort=RepairEffort.MINOR,
    supporting_recommendations=("Investigate syntax error",),
)
check("RepairPlan instantiates", plan is not None)
check("RepairPlan is frozen", plan.__dataclass_params__.frozen)
check("steps is tuple", isinstance(plan.steps, tuple))
check("validation_steps is tuple", isinstance(plan.validation_steps, tuple))
check("estimated_risk is RepairRisk", isinstance(plan.estimated_risk, RepairRisk))
check("estimated_effort is RepairEffort", isinstance(plan.estimated_effort, RepairEffort))
check("step_count correct", plan.step_count == 1)
check("has_plan True when steps present", plan.has_plan)
check("confidence is float", isinstance(plan.confidence, float))

empty_plan = RepairPlan(title="No Repair Plan", summary="none",
                        confidence=0.0, steps=(), validation_steps=(),
                        estimated_risk=RepairRisk.LOW,
                        estimated_effort=RepairEffort.MINOR,
                        supporting_recommendations=())
check("has_plan False when no steps", not empty_plan.has_plan)

try:
    plan.title = "hacked"
    check("RepairPlan is immutable", False)
except (AttributeError, TypeError):
    check("RepairPlan is immutable (raises on assignment)", True)


print("\n[77] RepairPlan.report() — human-readable")
report_text = plan.report()
check("report non-empty", len(report_text) > 50)
check("report contains 'Repair Plan'", "Repair Plan" in report_text)
check("report contains risk", "Low" in report_text)
check("report contains effort", "Minor" in report_text)
check("report contains step", "Review the syntax error" in report_text)
check("report contains Chief approval note", "Chief approval" in report_text)
check("report contains validation steps", "compileall" in report_text)
print(f"    Report length: {len(report_text)} chars")


print("\n[78] RepairPlanner — construction")
planner = RepairPlanner()
check("planner instantiates", planner is not None)
for method in ["write","modify","patch","fix","repair","execute","generate","apply"]:
    check(f"planner has no .{method}()", not hasattr(planner, method))


print("\n[79] exit_code=0 → empty plan")
ev = make_ev_plan(exit_code=0)
rc = make_rc_plan()
corr = make_corr_plan()
result = planner.plan(ev, FailureType.UNKNOWN, rc, corr, ())
check("exit_code=0 → no steps", not result.has_plan)
check("exit_code=0 → confidence=0.0", result.confidence == 0.0)


print("\n[80] SyntaxError → repair plan with steps")
ev = make_ev_plan("SyntaxError", ("core/router.py",), (77,))
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR, 0.97)
corr = make_corr_plan()
recs = (make_rec(RecommendationCategory.INVESTIGATE_SYNTAX,
                 RecommendationPriority.HIGH, 0.95, "Investigate syntax error"),)
result = planner.plan(ev, FailureType.COMPILE, rc, corr, recs)
check("SyntaxError produces steps", result.has_plan)
check("at least 2 steps", result.step_count >= 2)
check("title mentions Syntax Error", "Syntax Error" in result.title)
check("risk is LOW for single syntax error", result.estimated_risk == RepairRisk.LOW)
check("steps are ordered",
      all(result.steps[i].order == i+1 for i in range(len(result.steps))))
check("supporting_recommendations set",
      len(result.supporting_recommendations) > 0)
print(f"    Steps: {result.step_count} | Risk: {result.estimated_risk.value} | "
      f"Effort: {result.estimated_effort.value}")
for s in result.steps:
    print(f"      {s.order}. {s.title}")


print("\n[81] Repeated failure → CRITICAL risk")
ev = make_ev_plan("SyntaxError", ("core/router.py",))
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr_plan(CorrelationType.REPEATED_FAILURE,
                      files=("core/router.py",),
                      failures=("Previous error",))
recs = (make_rec(RecommendationCategory.MONITOR_REPEATED_FAILURES,
                 RecommendationPriority.CRITICAL, 0.97,
                 "Address recurring failure pattern"),)
result = planner.plan(ev, FailureType.COMPILE, rc, corr, recs)
check("repeated failure → CRITICAL risk", result.estimated_risk == RepairRisk.CRITICAL)
check("plan includes commit review step",
      any("commit" in s.title.lower() or "recurring" in s.description.lower()
          for s in result.steps))
check("effort MODERATE or higher for repeated",
      result.estimated_effort in (RepairEffort.MODERATE, RepairEffort.LARGE,
                                   RepairEffort.MAJOR))
print(f"    Risk: {result.estimated_risk.value} | Effort: {result.estimated_effort.value}")
for s in result.steps:
    print(f"      {s.order}. {s.title}")


print("\n[82] SAME_COMMIT → includes commit review step")
ev = make_ev_plan("SyntaxError")
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr_plan(CorrelationType.SAME_COMMIT, commits=("abc1234",))
recs = (make_rec(RecommendationCategory.REVIEW_RECENT_COMMITS,
                 RecommendationPriority.HIGH, 0.95, "Review associated commit"),)
result = planner.plan(ev, FailureType.COMPILE, rc, corr, recs)
check("SAME_COMMIT → commit review step",
      any("commit" in s.title.lower() for s in result.steps))
check("risk HIGH for SAME_COMMIT", result.estimated_risk == RepairRisk.HIGH)


print("\n[83] MissingModule → appropriate steps")
ev = make_ev_plan("ModuleNotFoundError")
rc = make_rc_plan(RootCauseCategory.MISSING_MODULE, 0.97)
corr = make_corr_plan()
recs = (make_rec(RecommendationCategory.VERIFY_DEPENDENCIES,
                 RecommendationPriority.HIGH, 0.95, "Verify module dependencies"),)
result = planner.plan(ev, FailureType.IMPORT, rc, corr, recs)
check("MissingModule plan has steps", result.has_plan)
check("plan includes module verification",
      any("module" in s.title.lower() or "install" in s.title.lower()
          for s in result.steps))
print(f"    Steps: {[s.title for s in result.steps]}")


print("\n[84] Validation steps always present")
ev = make_ev_plan("SyntaxError", ("core/router.py",))
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR)
corr = make_corr_plan()
recs = ()
result = planner.plan(ev, FailureType.COMPILE, rc, corr, recs)
check("validation_steps non-empty", len(result.validation_steps) > 0)
check("compileall in validation", any("compileall" in v for v in result.validation_steps))
check("pytest in validation", any("pytest" in v for v in result.validation_steps))


print("\n[85] Last step is always validation")
check("last step title mentions validation",
      "validat" in result.steps[-1].title.lower() or
      "validat" in result.steps[-1].description.lower())


print("\n[86] Steps have correct depends_on")
ev = make_ev_plan("SyntaxError", ("core/router.py",), (77,))
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR, 0.97)
corr = make_corr_plan()
recs = (make_rec(),)
result = planner.plan(ev, FailureType.COMPILE, rc, corr, recs)
check("first step has no dependencies", result.steps[0].depends_on == ())
if len(result.steps) > 1:
    check("later steps have dependencies",
          any(len(s.depends_on) > 0 for s in result.steps[1:]))


print("\n[87] Confidence derived from root cause + recommendations")
ev = make_ev_plan("SyntaxError")
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR, 0.97)
recs = (make_rec(confidence=0.95),)
result = planner.plan(ev, FailureType.COMPILE, rc, make_corr_plan(), recs)
check("confidence is float", isinstance(result.confidence, float))
check("confidence > 0 for known root cause", result.confidence > 0.0)
check("confidence <= 1.0", result.confidence <= 1.0)


print("\n[88] UNKNOWN root cause → empty plan")
ev = make_ev_plan(exit_code=1)
rc = make_rc_plan(RootCauseCategory.UNKNOWN, 0.0)
result = planner.plan(ev, FailureType.UNKNOWN, rc, make_corr_plan(), ())
check("UNKNOWN → no actionable plan", not result.has_plan)


print("\n[89] Determinism")
ev = make_ev_plan("SyntaxError", ("core/router.py",), (77,))
rc = make_rc_plan(RootCauseCategory.SYNTAX_ERROR, 0.97)
recs = (make_rec(),)
results = set()
for _ in range(20):
    p = planner.plan(ev, FailureType.COMPILE, rc, make_corr_plan(), recs)
    results.add(tuple((s.order, s.title) for s in p.steps))
check("repair planning is deterministic (20 runs)", len(results) == 1)


print("\n[90] EngineeringDebugger Sprint 006 integration")
history_s6 = [
    FR3(failure_type=FailureType.COMPILE,
        root_cause_category=RootCauseCategory.SYNTAX_ERROR,
        error_type="SyntaxError",
        failing_files=("core/router.py",),
        description="Previous router syntax error"),
]
debugger_s6 = EngineeringDebugger(history=history_s6)
rep_s6 = debugger_s6.analyse(
    command="python -m compileall core/",
    exit_code=1, stdout="",
    stderr='SyntaxError: expected \':\'\n  File "core/router.py", line 77',
)
check("DebugReport has repair_plan field", hasattr(rep_s6, "repair_plan"))
check("repair_plan is a RepairPlan", isinstance(rep_s6.repair_plan, RepairPlan))
check("repair_plan has steps for real failure", rep_s6.repair_plan.has_plan)
check("risk is set", isinstance(rep_s6.repair_plan.estimated_risk, RepairRisk))
check("effort is set", isinstance(rep_s6.repair_plan.estimated_effort, RepairEffort))
check("steps are ordered",
      all(rep_s6.repair_plan.steps[i].order == i+1
          for i in range(len(rep_s6.repair_plan.steps))))
print(f"    Plan: {rep_s6.repair_plan.title}")
print(f"    Risk: {rep_s6.repair_plan.estimated_risk.value} | "
      f"Effort: {rep_s6.repair_plan.estimated_effort.value} | "
      f"Steps: {rep_s6.repair_plan.step_count}")
for s in rep_s6.repair_plan.steps:
    print(f"      {s.order}. {s.title}")

debugger_ok = EngineeringDebugger()
rep_ok = debugger_ok.analyse("cmd", 0, "all good", "")
check("exit_code=0 → no repair plan steps", not rep_ok.repair_plan.has_plan)


print("\n[91] DebugReport.report() includes repair plan")
report_text = rep_s6.report()
check("report contains 'Repair Plan' section", "Repair Plan" in report_text)
check("report contains risk level",
      rep_s6.repair_plan.estimated_risk.value in report_text)
check("report contains step titles",
      any(s.title[:15] in report_text for s in rep_s6.repair_plan.steps))
check("report requires Chief approval", "Chief approval" in report_text)
print(f"    Full report length: {len(report_text)} chars")
for line in report_text.splitlines():
    if "Repair Plan" in line or "Risk:" in line or "Steps:" in line:
        print(f"    {line.strip()}")


print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 006: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nGenesis-017 COMPLETE.")
print(f"\nJarvis can now conduct a complete engineering investigation:")
print(f"  1. Collect evidence     (FailureEvidence)")
print(f"  2. Classify failure     (FailureType)")
print(f"  3. Determine root cause (RootCause)")
print(f"  4. Correlate history    (CorrelationRecord)")
print(f"  5. Recommend actions    (Recommendation)")
print(f"  6. Plan the repair      (RepairPlan)")
print(f"  7. Report to Chief      (DebugReport)")
print(f"\nThe pipeline stops before execution.")
print(f"Execution belongs to a future Genesis.")
print(f"\nAwaiting Chief approval. 🏁")