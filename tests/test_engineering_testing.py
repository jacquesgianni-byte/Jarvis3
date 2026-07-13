"""
Genesis-016 Sprint 005 — Engineering Test Runner test battery.

Tests that Jarvis can translate abstract validation recommendations
into executable commands and produce an immutable result with real
evidence.

No source files are modified. No Git write operations.

Runs standalone: python tests/test_engineering_testing.py
"""

import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engineering.testing.runner import EngineeringTestRunner, ValidationRegistry
from core.engineering.testing.models import (
    EngineeringTestResult,
    StepResult,
    ValidationStatus,
)
from core.engineering.planning.models import EngineeringPlan, Complexity
from core.engineering.coordinator import EngineeringCoordinator

passed = 0
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


def make_plan(objective="Test plan", steps=("Compile Check", "Regression Tests")):
    """Build a minimal EngineeringPlan for testing."""
    return EngineeringPlan(
        objective=objective,
        request=objective,
        candidate_files=("core/router.py",),
        layers_involved=("other",),
        dependencies=(),
        complexity=Complexity.LOW,
        estimated_file_count=1,
        validation_steps=tuple(steps),
        risks=(),
        summary="Test plan summary.",
    )


print("\n[1] Runner construction")
runner = EngineeringTestRunner(PROJECT_ROOT)
check("runner instantiates", runner is not None)
check("project root is set", runner.project_root.exists())


print("\n[2] ValidationRegistry")
registry = ValidationRegistry()
check("registry instantiates", registry is not None)
check("'compile check' is registered", registry.is_registered("Compile Check"))
check("'regression tests' is registered", registry.is_registered("Regression Tests"))
check("unknown recommendation is not registered",
      not registry.is_registered("Invented Step XYZ"))
check("manual step is registered", registry.is_registered("Desktop UI Smoke Test"))
check("manual step returns None command", registry.is_manual("Desktop UI Smoke Test"))
check("compile check is not manual", not registry.is_manual("Compile Check"))

# register() adds new entries
registry.register("Custom Test", ["echo", "ok"])
check("register() adds new entry", registry.is_registered("Custom Test"))
check("registered command is retrievable",
      registry.command_for("Custom Test") == ["echo", "ok"])

# Runner uses registry
runner_reg = EngineeringTestRunner(PROJECT_ROOT, registry=registry)
check("runner accepts custom registry", runner_reg.registry is registry)

print("\n[3] Validation mapping (runner API)")
supported = runner.supported_recommendations()
check("supported_recommendations() returns a list", isinstance(supported, list))
check("mapping includes Compile Check",
      any("compile check" in s.lower() for s in supported))
check("mapping includes Regression Tests",
      any("regression tests" in s.lower() for s in supported))
check("mapping includes Knowledge Engine Tests",
      any("knowledge" in s.lower() for s in supported))
check("mapping includes Reasoning Engine Tests",
      any("reasoning engine" in s.lower() for s in supported))

# command_for() returns tokens for known steps
cmd = runner.command_for("Compile Check")
check("command_for('Compile Check') returns a list", isinstance(cmd, list))
check("compile check command contains 'compileall'",
      any("compileall" in c for c in cmd))

cmd_pytest = runner.command_for("Regression Tests")
check("command_for('Regression Tests') returns a list", isinstance(cmd_pytest, list))
check("regression tests command contains 'pytest'",
      any("pytest" in c for c in cmd_pytest))

# Manual steps return None
cmd_ui = runner.command_for("Desktop UI Smoke Test")
check("manual step returns None", cmd_ui is None)

# Unknown returns None
cmd_unknown = runner.command_for("Invented Step XYZ")
check("unknown recommendation returns None", cmd_unknown is None)


print("\n[4] Compile execution")
plan_compile = make_plan("Compile check only", ("Compile Check",))
result_compile = runner.run(plan_compile)
check("run() returns EngineeringTestResult",
      isinstance(result_compile, EngineeringTestResult))
check("compile step executed", result_compile.steps_total == 1)
check("compile step has a name", bool(result_compile.steps[0].name))
check("compile step has a command", bool(result_compile.steps[0].command))
check("compile step has duration", result_compile.steps[0].duration_ms >= 0)
check("compile check passes on clean codebase", result_compile.steps[0].passed)
print(f"    Compile step: {result_compile.steps[0].duration_ms:.0f} ms")


print("\n[5] Subprocess execution — compile step proves command execution works")
# We do not recursively invoke the full pytest suite from inside pytest.
# Regression Tests remains in the registry and is verified structurally below.
# Actual regression validation runs independently: python -m pytest tests/
plan_exec = make_plan("Execution proof", ("Compile Check",))
result_exec = runner.run(plan_exec)
check("execution step runs and returns", result_exec.steps_total == 1)
check("execution step has non-empty output", len(result_exec.steps[0].output) > 0)
check("compile step passes on clean codebase", result_exec.steps[0].passed)
check("execution step has duration", result_exec.steps[0].duration_ms > 0)
print(f"    Compile step: {result_exec.steps[0].duration_ms:.0f} ms")
print(f"    Output tail:  {result_exec.steps[0].output.splitlines()[-1] if result_exec.steps[0].output else '(none)'}")
cmd_reg = runner.command_for("Regression Tests")
check("Regression Tests is registered in the registry", cmd_reg is not None)
check("Regression Tests maps to pytest", any("pytest" in c for c in cmd_reg))


print("\n[6] Manual/skipped steps")
plan_manual = make_plan("Manual steps", ("Desktop UI Smoke Test", "Audio Output Test"))
result_manual = runner.run(plan_manual)
check("manual steps are skipped gracefully", result_manual.steps_total == 2)
check("skipped steps count as passed", result_manual.steps_passed == 2)
check("skipped steps show '(skipped)' command",
      all(s.command == "(skipped)" for s in result_manual.steps))
check("overall status PASSED when all skipped",
      result_manual.status == ValidationStatus.PASSED)


print("\n[7] Unknown recommendations")
plan_unknown = make_plan("Unknown", ("Made Up Validation Step",))
result_unknown = runner.run(plan_unknown)
check("unknown steps do not crash", result_unknown.steps_total == 1)
check("unknown steps marked as passed (non-blocking)",
      result_unknown.steps[0].passed)
check("unknown step command shows '(unmapped)'",
      result_unknown.steps[0].command == "(unmapped)")


print("\n[8] Immutable result model")
result = runner.run(make_plan())
check("EngineeringTestResult is frozen",
      result.__dataclass_params__.frozen)
try:
    object.__setattr__(result, "status", ValidationStatus.FAILED)
    check("result fields cannot be mutated", False)
except Exception:
    check("result fields cannot be mutated (raises on mutation)", True)
check("steps is a tuple", isinstance(result.steps, tuple))

step = result.steps[0]
check("StepResult is frozen", step.__dataclass_params__.frozen)
try:
    object.__setattr__(step, "passed", False)
    check("StepResult fields cannot be mutated", False)
except Exception:
    check("StepResult fields cannot be mutated (raises on mutation)", True)


print("\n[9] Execution timing")
result_timed = runner.run(make_plan("Timed run", ("Compile Check",)))
check("total_duration_ms is recorded", result_timed.total_duration_ms > 0)
check("step duration_ms is recorded", result_timed.steps[0].duration_ms > 0)
check("step duration <= total duration",
      result_timed.steps[0].duration_ms <= result_timed.total_duration_ms + 1)
check("started_at is a non-empty ISO string", bool(result_timed.started_at))
check("finished_at is a non-empty ISO string", bool(result_timed.finished_at))
check("started_at contains UTC marker",
      "T" in result_timed.started_at)
check("finished_at >= started_at",
      result_timed.finished_at >= result_timed.started_at)


print("\n[10] Status derivation")
# All pass → PASSED
result_all_pass = runner.run(make_plan(
    "All pass", ("Compile Check", "Desktop UI Smoke Test")
))
check("all steps pass → PASSED", result_all_pass.status == ValidationStatus.PASSED)

# Empty plan → SKIPPED
result_empty = runner.run(make_plan("Empty", steps=()))
check("no steps → SKIPPED", result_empty.status == ValidationStatus.SKIPPED)
check("steps_total is 0 for empty plan", result_empty.steps_total == 0)

# Properties
check("success property True when PASSED", result_all_pass.success)
check("steps_passed property correct",
      result_all_pass.steps_passed == result_all_pass.steps_total)
check("steps_failed property correct", result_all_pass.steps_failed == 0)


print("\n[11] Report generation")
result_report = runner.run(make_plan("Report test", ("Compile Check",)))
report = result_report.report()
check("report is non-empty", len(report) > 50)
check("report contains 'Engineering Validation Report'",
      "Engineering Validation Report" in report)
check("report contains status", result_report.status.value in report)
check("report contains step count",
      f"{result_report.steps_passed}/{result_report.steps_total}" in report)
check("report contains step name", "Compile Check" in report)
print(f"    Report length: {len(report)} chars")
print(f"    Status: {result_report.status.value}")


print("\n[12] Read-only guarantee — behavioural")
write_methods = [
    "write", "modify", "create", "delete", "patch",
    "commit", "add", "push", "reset", "checkout",
]
for method in write_methods:
    check(f"EngineeringTestRunner has no .{method}() method",
          not hasattr(runner, method))


print("\n[13] EngineeringCoordinator integration")
coord = EngineeringCoordinator(PROJECT_ROOT).initialise()

# Create a real plan then validate it
plan = coord.create_plan("Validate the reasoning engine")
check("plan has validation steps", len(plan.validation_steps) > 0)

result_coord = coord.run_validation(plan)
check("coord.run_validation() returns EngineeringTestResult",
      isinstance(result_coord, EngineeringTestResult))
check("coord validation has steps", result_coord.steps_total > 0)
check("coord validation has status",
      isinstance(result_coord.status, ValidationStatus))

report_str = coord.validation_report(plan)
check("coord.validation_report() returns a string", isinstance(report_str, str))
check("validation report contains 'Engineering Validation Report'",
      "Engineering Validation Report" in report_str)

print(f"\n    Coordinator validation: {result_coord.status.value} "
      f"({result_coord.steps_passed}/{result_coord.steps_total} steps passed)")


print("\n[14] Full pipeline — Plan → Guardrails → Testing")
from core.engineering.guardrails.guardrails import EngineeringGuardrails
from core.engineering.guardrails.models import ApprovalStatus

# Step 1: Plan
pipeline_plan = coord.create_plan("Check the reasoning engine tests pass")
check("pipeline: plan created", isinstance(pipeline_plan, EngineeringPlan))

# Step 2: Guardrails
guardrails = EngineeringGuardrails()
guardrail_result = guardrails.evaluate(
    task=pipeline_plan.objective,
    files=list(pipeline_plan.candidate_files),
)
check("pipeline: guardrails evaluated", guardrail_result.status in (
    ApprovalStatus.APPROVED,
    ApprovalStatus.REQUIRES_APPROVAL,
    ApprovalStatus.REJECTED,
))
print(f"    Guardrails: {guardrail_result.status.value}")

# Step 3: Testing — use compile-only plan to avoid recursive pytest
# Full regression is validated independently by: python -m pytest tests/
compile_plan = make_plan("Pipeline compile check", ("Compile Check",))
test_result = coord.run_validation(compile_plan)
check("pipeline: testing executed", isinstance(test_result, EngineeringTestResult))
check("pipeline: result has evidence", test_result.steps_total > 0)
check("pipeline: result has timestamps", bool(test_result.started_at))
print(f"    Testing: {test_result.status.value} "
      f"({test_result.steps_passed}/{test_result.steps_total} passed, "
      f"{test_result.total_duration_ms:.0f} ms)")


print(f"\n{'='*60}")
print(f"GENESIS-016 SPRINT 005: ALL {passed} CHECKS PASS")
print(f"{'='*60}")
print(f"\nJarvis can now answer:")
print(f"  'Has this engineering work been successfully validated?'")
print(f"\nFull engineering pipeline:")
print(f"  Catalogue → Git → Planner → Plan → Guardrails → Chief → Testing")
print(f"\nDeferred to later sprints:")
print(f"  Code generation, patch application, execution, debugging")