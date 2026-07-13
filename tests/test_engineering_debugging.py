"""
Genesis-017 Sprint 001 — Engineering Debugging Foundation test battery.

Tests that Jarvis can analyse engineering failures forensically:
classify them, collect evidence, and produce immutable reports —
without modifying files, guessing, or proposing fixes.

Runs standalone: python tests/test_engineering_debugging.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.debugging.models import DebugReport, FailureEvidence, FailureType
from core.engineering.debugging.classifier import FailureClassifier
from core.engineering.debugging.debugger import EngineeringDebugger

passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


# ---------------------------------------------------------------------------
print("\n[1] FailureType enum")
# ---------------------------------------------------------------------------
check("COMPILE exists",       FailureType.COMPILE.value == "Compile Error")
check("IMPORT exists",        FailureType.IMPORT.value == "Import Error")
check("TEST exists",          FailureType.TEST.value == "Test Failure")
check("TIMEOUT exists",       FailureType.TIMEOUT.value == "Timeout")
check("CONFIGURATION exists", FailureType.CONFIGURATION.value == "Configuration Error")
check("UNKNOWN exists",       FailureType.UNKNOWN.value == "Unknown")
check("exactly 6 failure types", len(FailureType) == 6)


# ---------------------------------------------------------------------------
print("\n[2] DebugReport — immutable model")
# ---------------------------------------------------------------------------
_ev = FailureEvidence(
    command="python -m compileall core/",
    exit_code=1,
    stdout=(),
    stderr=("SyntaxError: invalid syntax",),
    timestamp=datetime.now(timezone.utc).isoformat(),
)
report = DebugReport(
    failure_type=FailureType.COMPILE,
    summary="SyntaxError on line 42",
    confidence=0.95,
    clues=("SyntaxError: invalid syntax", "line 42"),
    evidence=_ev,
)
check("DebugReport instantiates", report is not None)
check("DebugReport is frozen", report.__dataclass_params__.frozen)
check("evidence is a FailureEvidence", isinstance(report.evidence, FailureEvidence))
check("clues is a tuple", isinstance(report.clues, tuple))
check("evidence.stdout is a tuple", isinstance(report.evidence.stdout, tuple))
check("evidence.stderr is a tuple", isinstance(report.evidence.stderr, tuple))
check("failure_type is FailureType", isinstance(report.failure_type, FailureType))
check("confidence is a float", isinstance(report.confidence, float))
check("evidence.timestamp is non-empty", bool(report.evidence.timestamp))

# Verify public API contract: normal attribute assignment must raise.
# Tests the frozen=True contract as user code would encounter it.
_ev_mut = FailureEvidence(command="cmd", exit_code=1, stdout=(), stderr=(),
                          timestamp=datetime.now(timezone.utc).isoformat())
_report_mut = DebugReport(failure_type=FailureType.COMPILE, summary="test",
                          confidence=0.9, clues=(), evidence=_ev_mut)
try:
    _report_mut.failure_type = FailureType.UNKNOWN
    check("DebugReport fields are immutable", False)
except (AttributeError, TypeError):
    check("DebugReport fields are immutable (raises on assignment)", True)

try:
    _ev_mut.exit_code = 0
    check("FailureEvidence fields are immutable", False)
except (AttributeError, TypeError):
    check("FailureEvidence fields are immutable (raises on assignment)", True)


# ---------------------------------------------------------------------------
print("\n[3] DebugReport.report() — human-readable output")
# ---------------------------------------------------------------------------
text = report.report()
check("report() is non-empty", len(text) > 50)
check("report contains 'Engineering Debug Report'",
      "Engineering Debug Report" in text)
check("report contains failure type", "Compile Error" in text)
check("report contains summary", "SyntaxError" in text)
check("report contains exit code", "1" in text)
check("report contains forensic note",
      "What happened" in text or "evidence before assumption" in text.lower()
      or "describes what happened" in text)


# ---------------------------------------------------------------------------
print("\n[4] FailureClassifier — deterministic classification")
# ---------------------------------------------------------------------------
clf = FailureClassifier()
check("classifier instantiates", clf is not None)

# Success exit code → UNKNOWN
ft, conf, ev = clf.classify("all good", "", 0)
check("exit_code=0 → UNKNOWN", ft == FailureType.UNKNOWN)
check("exit_code=0 → confidence=0.0", conf == 0.0)

# Compile error
ft, conf, ev = clf.classify(
    "", "SyntaxError: invalid syntax\n  File 'core/router.py', line 42", 1
)
check("SyntaxError → COMPILE", ft == FailureType.COMPILE)
check("COMPILE confidence >= 0.9", conf >= 0.9)
check("evidence contains SyntaxError line",
      any("SyntaxError" in e for e in ev))

# Import error
ft, conf, ev = clf.classify(
    "", "ModuleNotFoundError: No module named 'openai'", 1
)
check("ModuleNotFoundError → IMPORT", ft == FailureType.IMPORT)
check("IMPORT confidence >= 0.9", conf >= 0.9)

# Test failure
ft, conf, ev = clf.classify(
    "FAILED tests/test_edge_cases.py::test_store\n3 failed, 50 passed", "", 1
)
check("pytest FAILED → TEST", ft == FailureType.TEST)
check("TEST confidence >= 0.85", conf >= 0.85)

# Timeout
ft, conf, ev = clf.classify("", "TimeoutExpired: Command timed out after 120s", 1)
check("TimeoutExpired → TIMEOUT", ft == FailureType.TIMEOUT)
check("TIMEOUT confidence = 1.0", conf == 1.0)

# Timeout by exit code
ft, conf, ev = clf.classify("", "", 124)
check("exit_code=124 → TIMEOUT", ft == FailureType.TIMEOUT)

# Configuration error
ft, conf, ev = clf.classify(
    "", "KeyError: 'OPENAI_API_KEY'\nSettings not configured", 1
)
check("KeyError API → CONFIGURATION", ft == FailureType.CONFIGURATION)

# Unknown — no recognisable pattern
ft, conf, ev = clf.classify("", "something went wrong", 1)
check("unrecognised output → UNKNOWN", ft == FailureType.UNKNOWN)
check("UNKNOWN confidence = 0.0", conf == 0.0)


# ---------------------------------------------------------------------------
print("\n[5] Deterministic classification")
# ---------------------------------------------------------------------------
stderr = "SyntaxError: invalid syntax\n  line 15"
results = set()
for _ in range(20):
    ft, conf, ev = clf.classify("", stderr, 1)
    results.add((ft, conf))
check("classification is deterministic (20 runs, 1 result)", len(results) == 1)


# ---------------------------------------------------------------------------
print("\n[6] EngineeringDebugger — analyse()")
# ---------------------------------------------------------------------------
debugger = EngineeringDebugger()
check("debugger instantiates", debugger is not None)

# Compile failure
rep = debugger.analyse(
    command="python -m compileall core/",
    exit_code=1,
    stdout="",
    stderr="SyntaxError: invalid syntax\n  File 'core/router.py', line 15",
)
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

# Import failure
rep2 = debugger.analyse(
    command="python tests/test_reasoning_engine.py",
    exit_code=1,
    stdout="",
    stderr="ModuleNotFoundError: No module named 'core.reasoning'",
)
check("import failure classified as IMPORT", rep2.failure_type == FailureType.IMPORT)

# Test failure
rep3 = debugger.analyse(
    command="python -m pytest tests/ -q",
    exit_code=1,
    stdout="FAILED tests/test_edge_cases.py::test_store\n3 failed",
    stderr="",
)
check("test failure classified as TEST", rep3.failure_type == FailureType.TEST)

# Timeout
rep4 = debugger.analyse(
    command="python -m pytest tests/",
    exit_code=1,
    stdout="",
    stderr="subprocess.TimeoutExpired: Command timed out after 120s",
)
check("timeout classified as TIMEOUT", rep4.failure_type == FailureType.TIMEOUT)

# Unknown — honest answer
rep5 = debugger.analyse(
    command="python main.py",
    exit_code=1,
    stdout="",
    stderr="something went wrong",
)
check("unknown failure → UNKNOWN", rep5.failure_type == FailureType.UNKNOWN)
check("UNKNOWN confidence = 0.0", rep5.confidence == 0.0)

# Success — not a failure
rep6 = debugger.analyse(
    command="python -m compileall core/",
    exit_code=0,
    stdout="Listing 'core'...",
    stderr="",
)
check("exit_code=0 → UNKNOWN (not a failure)", rep6.failure_type == FailureType.UNKNOWN)
check("exit_code=0 → confidence=0.0", rep6.confidence == 0.0)


# ---------------------------------------------------------------------------
print("\n[7] Output truncation")
# ---------------------------------------------------------------------------
long_output = "x" * 10000
rep_long = debugger.analyse("cmd", 1, long_output, long_output)
check("stdout stored in evidence, lines <= 3000 chars total",
      sum(len(l) for l in rep_long.evidence.stdout) <= 3000)
check("stderr stored in evidence, lines <= 3000 chars total",
      sum(len(l) for l in rep_long.evidence.stderr) <= 3000)
check("clues capped at 20 lines", len(rep_long.clues) <= 20)


# ---------------------------------------------------------------------------
print("\n[8] analyse_step() convenience method")
# ---------------------------------------------------------------------------
class FakeStep:
    command = "python tests/test_edge_cases.py"
    passed  = False
    output  = "FAILED tests/test_edge_cases.py\n3 failed"
    error   = "AssertionError: expected True"

step_report = debugger.analyse_step(FakeStep())
check("analyse_step() returns DebugReport", isinstance(step_report, DebugReport))
check("analyse_step() classifies TEST failure",
      step_report.failure_type == FailureType.TEST)
check("analyse_step() captures command", bool(step_report.evidence.command))


# ---------------------------------------------------------------------------
print("\n[9] Read-only guarantee — behavioural")
# ---------------------------------------------------------------------------
write_methods = [
    "write", "modify", "patch", "apply", "execute",
    "commit", "add", "push", "checkout", "delete",
]
for method in write_methods:
    check(f"EngineeringDebugger has no .{method}() method",
          not hasattr(debugger, method))

for method in write_methods:
    check(f"FailureClassifier has no .{method}() method",
          not hasattr(clf, method))


# ---------------------------------------------------------------------------
print("\n[10] Full report output")
# ---------------------------------------------------------------------------
full_report = rep.report()
check("full report contains 'Engineering Debug Report'",
      "Engineering Debug Report" in full_report)
check("full report contains failure type", "Compile Error" in full_report)
check("full report contains timestamp", rep.evidence.timestamp in full_report)
check("full report contains evidence", len(full_report) > 100)
print(f"    Report length: {len(full_report)} chars")
print(f"    Failure type:  {rep.failure_type.value}")
print(f"    Confidence:    {rep.confidence:.0%}")
print(f"    Summary:       {rep.summary[:60]}")


# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"GENESIS-017 SPRINT 001: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'What happened during this engineering failure?'")
print(f"\nFailure types classified:")
for ft in FailureType:
    print(f"  {ft.value}")
print(f"\nDesign principle:")
print(f"  'What happened?' — not — 'How should I fix it?'")
print(f"\nDeferred to later sprints:")
print(f"  Fix suggestion, patch generation, autonomous repair")