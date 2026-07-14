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
report = DebugReport(failure_type=FailureType.COMPILE, summary="SyntaxError on line 42",
                     confidence=0.95, clues=("SyntaxError: invalid syntax", "line 42"),
                     evidence=_ev)
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
_rep_mut = DebugReport(failure_type=FailureType.COMPILE, summary="t",
                       confidence=0.9, clues=(), evidence=_ev_mut)
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