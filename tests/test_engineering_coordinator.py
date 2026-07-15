"""
Genesis-018 Sprint 001 — Engineering Coordinator Test Suite
Deterministic validation: ~130 checks.

Run:
    python tests/test_engineering_coordinator.py
    python -m pytest tests/test_engineering_coordinator.py -v
"""

from __future__ import annotations

import sys
import os
import time

# Ensure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.engineering.coordinator import (
    CoordinatorConfig,
    CoordinatorEvent,
    EngineeringCoordinator,
    EngineeringRequest,
    EngineeringResult,
    EngineeringStatus,
)


# ===========================================================================
# Stub subsystems (deterministic, no AI, no I/O)
# ===========================================================================

class _StubPlanner:
    """Always returns a fixed plan string."""
    def plan(self, request: str, *, context: str = "") -> str:
        return f"Plan for: {request}"


class _FailingPlanner:
    """Always raises."""
    def plan(self, request: str, **kwargs) -> str:
        raise RuntimeError("Planner internal error")


class _StubGuardrails:
    """Always passes."""
    def check(self, request: str, *, plan=None) -> bool:
        return True


class _BlockingGuardrails:
    """Always blocks."""
    def check(self, request: str, **kwargs) -> bool:
        return False


class _FailingGuardrails:
    """Always raises."""
    def check(self, request: str, **kwargs) -> bool:
        raise RuntimeError("Guardrails internal error")


class _PassingTestRunner:
    """Always reports validation as passed."""
    class _Result:
        passed = True
        def __str__(self): return "All tests passed"
    def run(self, request: str, **kwargs):
        return self._Result()


class _FailingTestRunner:
    """Always reports validation as failed."""
    class _Result:
        passed = False
        def __str__(self): return "Tests failed: assertion error"
    def run(self, request: str, **kwargs):
        return self._Result()


class _RaisingTestRunner:
    """Always raises."""
    def run(self, request: str, **kwargs):
        raise RuntimeError("Test runner crashed")


class _StubDebugger:
    """Returns a stub debug result with report and repair_plan attributes."""
    class _Result:
        report      = "Debug complete: issue identified"
        repair_plan = "Repair plan: apply patch A"
        def __str__(self): return "Debug complete: issue identified"
    def debug(self, request: str, **kwargs):
        return self._Result()


class _FailingDebugger:
    """Always raises."""
    def debug(self, request: str, **kwargs):
        raise RuntimeError("Debugger crashed")


# ===========================================================================
# Test runner helpers
# ===========================================================================

_PASSED = 0
_FAILED = 0
_ERRORS: list[str] = []


def _assert(condition: bool, name: str) -> None:
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
    else:
        _FAILED += 1
        _ERRORS.append(f"FAIL: {name}")
        print(f"  ✗ {name}")


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ===========================================================================
# SECTION 1 — EngineeringStatus
# ===========================================================================

def test_status() -> None:
    _section("EngineeringStatus")

    # All values exist
    _assert(EngineeringStatus.PENDING.value    == "PENDING",    "PENDING value")
    _assert(EngineeringStatus.PLANNING.value   == "PLANNING",   "PLANNING value")
    _assert(EngineeringStatus.VALIDATING.value == "VALIDATING", "VALIDATING value")
    _assert(EngineeringStatus.DEBUGGING.value  == "DEBUGGING",  "DEBUGGING value")
    _assert(EngineeringStatus.COMPLETE.value   == "COMPLETE",   "COMPLETE value")
    _assert(EngineeringStatus.FAILED.value     == "FAILED",     "FAILED value")

    # is_terminal
    _assert(EngineeringStatus.COMPLETE.is_terminal(),    "COMPLETE is terminal")
    _assert(EngineeringStatus.FAILED.is_terminal(),      "FAILED is terminal")
    _assert(not EngineeringStatus.PENDING.is_terminal(), "PENDING not terminal")
    _assert(not EngineeringStatus.PLANNING.is_terminal(),"PLANNING not terminal")
    _assert(not EngineeringStatus.VALIDATING.is_terminal(),"VALIDATING not terminal")
    _assert(not EngineeringStatus.DEBUGGING.is_terminal(), "DEBUGGING not terminal")

    # is_active
    _assert(EngineeringStatus.PENDING.is_active(),        "PENDING is active")
    _assert(EngineeringStatus.PLANNING.is_active(),       "PLANNING is active")
    _assert(EngineeringStatus.VALIDATING.is_active(),     "VALIDATING is active")
    _assert(EngineeringStatus.DEBUGGING.is_active(),      "DEBUGGING is active")
    _assert(not EngineeringStatus.COMPLETE.is_active(),   "COMPLETE not active")
    _assert(not EngineeringStatus.FAILED.is_active(),     "FAILED not active")

    # Enum identity
    _assert(len(EngineeringStatus) == 6, "Exactly 6 status values")
    _assert(EngineeringStatus("COMPLETE") is EngineeringStatus.COMPLETE, "Lookup by value")


# ===========================================================================
# SECTION 2 — EngineeringRequest
# ===========================================================================

def test_request_construction() -> None:
    _section("EngineeringRequest — construction")

    r = EngineeringRequest(request="Refactor auth module")
    _assert(r.request  == "Refactor auth module", "request stored")
    _assert(r.context  == "",                     "default context")
    _assert(r.priority == 0,                      "default priority")
    _assert(r.metadata == {},                     "default metadata")

    r2 = EngineeringRequest(
        request="Fix login bug",
        context="Affects production",
        priority=5,
        metadata={"ticket": "JRV-42"},
    )
    _assert(r2.context  == "Affects production",   "context stored")
    _assert(r2.priority == 5,                      "priority stored")
    _assert(r2.metadata == {"ticket": "JRV-42"},   "metadata stored")

    # Immutability
    try:
        r.request = "mutated"  # type: ignore
        _assert(False, "Request should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "Request is immutable")


def test_request_properties() -> None:
    _section("EngineeringRequest — properties")

    r_no_ctx   = EngineeringRequest(request="Task A")
    r_with_ctx = EngineeringRequest(request="Task B", context="some context")
    r_lo_prio  = EngineeringRequest(request="Task C", priority=0)
    r_hi_prio  = EngineeringRequest(request="Task D", priority=3)

    _assert(not r_no_ctx.has_context,   "has_context False when empty")
    _assert(r_with_ctx.has_context,     "has_context True when set")
    _assert(not r_lo_prio.is_high_priority, "priority 0 not high")
    _assert(r_hi_prio.is_high_priority,     "priority >0 is high")


def test_request_with_metadata() -> None:
    _section("EngineeringRequest — with_metadata")

    r  = EngineeringRequest(request="Build feature X", metadata={"a": 1})
    r2 = r.with_metadata(b=2, c=3)

    _assert(r.metadata  == {"a": 1},          "original unchanged")
    _assert(r2.metadata == {"a": 1, "b": 2, "c": 3}, "merged correctly")
    _assert(r2.request  == r.request,          "request preserved")
    _assert(r2.priority == r.priority,         "priority preserved")

    # Override key
    r3 = r.with_metadata(a=99)
    _assert(r3.metadata["a"] == 99, "override key wins")


def test_request_validation_errors() -> None:
    _section("EngineeringRequest — validation errors")

    # blank request
    try:
        EngineeringRequest(request="   ")
        _assert(False, "Blank request should raise ValueError")
    except ValueError:
        _assert(True, "Blank request raises ValueError")

    # wrong type for request
    try:
        EngineeringRequest(request=123)  # type: ignore
        _assert(False, "Non-str request should raise TypeError")
    except TypeError:
        _assert(True, "Non-str request raises TypeError")

    # wrong type for priority
    try:
        EngineeringRequest(request="ok", priority="high")  # type: ignore
        _assert(False, "Non-int priority should raise TypeError")
    except TypeError:
        _assert(True, "Non-int priority raises TypeError")

    # wrong type for metadata
    try:
        EngineeringRequest(request="ok", metadata="bad")  # type: ignore
        _assert(False, "Non-dict metadata should raise TypeError")
    except TypeError:
        _assert(True, "Non-dict metadata raises TypeError")

    # wrong type for context
    try:
        EngineeringRequest(request="ok", context=42)  # type: ignore
        _assert(False, "Non-str context should raise TypeError")
    except TypeError:
        _assert(True, "Non-str context raises TypeError")


def test_request_repr() -> None:
    _section("EngineeringRequest — repr")

    r = EngineeringRequest(request="short")
    _assert("EngineeringRequest" in repr(r), "repr contains class name")

    long_req = "A" * 100
    r_long   = EngineeringRequest(request=long_req)
    _assert("…" in repr(r_long), "long request is truncated in repr")


# ===========================================================================
# SECTION 3 — EngineeringResult
# ===========================================================================

def test_result_construction() -> None:
    _section("EngineeringResult — construction")

    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.status    == EngineeringStatus.COMPLETE, "status stored")
    _assert(res.completed == True,                        "completed stored")
    _assert(res.plan      is None,                        "plan defaults None")
    _assert(res.errors    == [],                          "errors defaults empty")
    _assert(res.warnings  == [],                          "warnings defaults empty")

    # Immutability
    try:
        res.status = EngineeringStatus.FAILED  # type: ignore
        _assert(False, "Result should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "Result is immutable")


def test_result_properties() -> None:
    _section("EngineeringResult — properties")

    complete = EngineeringResult(
        status=EngineeringStatus.COMPLETE, completed=True
    )
    failed   = EngineeringResult(
        status=EngineeringStatus.FAILED, completed=False,
        errors=["something broke"]
    )
    debugged = EngineeringResult(
        status=EngineeringStatus.FAILED,
        debug_report="found root cause",
        repair_plan="apply fix",
        completed=False,
    )

    _assert(complete.succeeded,         "COMPLETE+completed=True → succeeded")
    _assert(not failed.succeeded,       "FAILED → not succeeded")
    _assert(failed.failed,              "FAILED → failed property True")
    _assert(not complete.failed,        "COMPLETE → failed property False")
    _assert(debugged.required_debugging,"debug_report set → required_debugging")
    _assert(not complete.required_debugging, "no debug_report → not required_debugging")
    _assert(debugged.has_repair_plan,   "repair_plan set → has_repair_plan")
    _assert(not complete.has_repair_plan, "no repair_plan → not has_repair_plan")
    _assert(failed.has_errors,          "has_errors True")
    _assert(not complete.has_errors,    "has_errors False")
    _assert(failed.error_count == 1,    "error_count correct")


def test_result_duration_validation() -> None:
    _section("EngineeringResult — duration validation")

    # valid
    res = EngineeringResult(
        status=EngineeringStatus.COMPLETE,
        completed=True,
        duration_ms=250,
    )
    _assert(res.duration_ms == 250, "duration stored")

    # zero is fine
    res0 = EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=0)
    _assert(res0.duration_ms == 0, "zero duration allowed")

    # negative should raise
    try:
        EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=-1)
        _assert(False, "Negative duration should raise ValueError")
    except ValueError:
        _assert(True, "Negative duration raises ValueError")

    # wrong type should raise
    try:
        EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms="fast")  # type: ignore
        _assert(False, "Non-int duration should raise TypeError")
    except TypeError:
        _assert(True, "Non-int duration raises TypeError")


def test_result_summary() -> None:
    _section("EngineeringResult — summary")

    res = EngineeringResult(
        status=EngineeringStatus.COMPLETE,
        completed=True,
        duration_ms=100,
    )
    s = res.summary()
    _assert("COMPLETE" in s,  "summary contains status")
    _assert("100ms"    in s,  "summary contains duration")
    _assert("EngineeringResult" in s, "summary contains class name")


# ===========================================================================
# SECTION 4 — CoordinatorConfig
# ===========================================================================

def test_coordinator_config() -> None:
    _section("CoordinatorConfig")

    cfg = CoordinatorConfig()
    _assert(cfg.enable_planning,   "planning enabled by default")
    _assert(cfg.enable_guardrails, "guardrails enabled by default")
    _assert(cfg.enable_validation, "validation enabled by default")
    _assert(cfg.enable_debugging,  "debugging enabled by default")
    _assert(cfg.enable_repair,     "repair enabled by default")
    _assert(cfg.max_debug_cycles == 1, "max_debug_cycles default 1")

    cfg2 = CoordinatorConfig(enable_planning=False, max_debug_cycles=3)
    _assert(not cfg2.enable_planning,  "planning disabled")
    _assert(cfg2.max_debug_cycles == 3, "max_debug_cycles set")

    # invalid max_debug_cycles
    try:
        CoordinatorConfig(max_debug_cycles=-1)
        _assert(False, "Negative max_debug_cycles should raise")
    except ValueError:
        _assert(True, "Negative max_debug_cycles raises ValueError")

    _assert("CoordinatorConfig" in repr(cfg), "repr contains class name")


# ===========================================================================
# SECTION 5 — EngineeringCoordinator construction
# ===========================================================================

def test_coordinator_construction() -> None:
    _section("EngineeringCoordinator — construction")

    c = EngineeringCoordinator()
    _assert(not c.has_planner,     "no planner by default")
    _assert(not c.has_guardrails,  "no guardrails by default")
    _assert(not c.has_test_runner, "no test runner by default")
    _assert(not c.has_debugger,    "no debugger by default")
    _assert(c.observer_count == 0, "no observers by default")
    _assert(c.VERSION == "018.001", "version correct")

    # With all subsystems
    c2 = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        debugger=_StubDebugger(),
    )
    _assert(c2.has_planner,     "planner registered")
    _assert(c2.has_guardrails,  "guardrails registered")
    _assert(c2.has_test_runner, "test runner registered")
    _assert(c2.has_debugger,    "debugger registered")


def test_coordinator_describe() -> None:
    _section("EngineeringCoordinator — describe")

    c = EngineeringCoordinator(planner=_StubPlanner())
    d = c.describe()
    _assert(isinstance(d, dict),  "describe returns dict")
    _assert("version" in d,       "version in describe")
    _assert(d["has_planner"],     "has_planner True")
    _assert(not d["has_debugger"], "has_debugger False")


def test_coordinator_repr() -> None:
    _section("EngineeringCoordinator — repr")

    c = EngineeringCoordinator()
    _assert("EngineeringCoordinator" in repr(c), "repr contains class name")
    _assert("018.001" in repr(c),                "repr contains version")


# ===========================================================================
# SECTION 6 — Observer system
# ===========================================================================

def test_coordinator_observers() -> None:
    _section("EngineeringCoordinator — observer system")

    events: list[CoordinatorEvent] = []

    def capture(e: CoordinatorEvent) -> None:
        events.append(e)

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    c.add_observer(capture)
    _assert(c.observer_count == 1, "observer count 1")

    # Duplicate add is idempotent
    c.add_observer(capture)
    _assert(c.observer_count == 1, "duplicate observer not added twice")

    req = EngineeringRequest(request="Observe this")
    c.coordinate(req)

    _assert(len(events) > 0, "events emitted")
    _assert(all(isinstance(e, CoordinatorEvent) for e in events), "all events are CoordinatorEvent")
    _assert(any(e.status == EngineeringStatus.PENDING  for e in events), "PENDING event emitted")
    _assert(any(e.status == EngineeringStatus.COMPLETE for e in events), "COMPLETE event emitted")

    # Remove observer
    c.remove_observer(capture)
    _assert(c.observer_count == 0, "observer removed")

    # Non-callable observer should raise
    try:
        c.add_observer("not callable")  # type: ignore
        _assert(False, "Non-callable observer should raise TypeError")
    except TypeError:
        _assert(True, "Non-callable observer raises TypeError")

    # Crashing observer must not break pipeline
    def bad_observer(e):
        raise RuntimeError("Observer crash")

    c.add_observer(bad_observer)
    result = c.coordinate(req)   # Must not raise
    _assert(result.status == EngineeringStatus.COMPLETE, "Pipeline continues after observer crash")


# ===========================================================================
# SECTION 7 — Pipeline: happy path (all subsystems)
# ===========================================================================

def test_pipeline_full_pass() -> None:
    _section("Pipeline — full pass (all subsystems)")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        debugger=_StubDebugger(),
    )
    req    = EngineeringRequest(request="Build auth service", priority=1)
    result = c.coordinate(req)

    _assert(result.status    == EngineeringStatus.COMPLETE, "status COMPLETE")
    _assert(result.completed == True,                        "completed True")
    _assert(result.succeeded,                                "succeeded True")
    _assert(not result.failed,                               "not failed")
    _assert(result.plan is not None,                         "plan populated")
    _assert("Build auth service" in result.plan,             "plan contains request")
    _assert(result.debug_report is None,                     "no debug report on pass")
    _assert(result.repair_plan  is None,                     "no repair plan on pass")
    _assert(result.duration_ms  is not None,                 "duration set")
    _assert(result.duration_ms  >= 0,                        "duration non-negative")
    _assert(not result.has_errors,                           "no errors on pass")


# ===========================================================================
# SECTION 8 — Pipeline: no subsystems (graceful degradation)
# ===========================================================================

def test_pipeline_no_subsystems() -> None:
    _section("Pipeline — no subsystems (graceful degradation)")

    c = EngineeringCoordinator()
    req    = EngineeringRequest(request="Standalone request")
    result = c.coordinate(req)

    # With no subsystems all stages are skipped with warnings → COMPLETE
    _assert(result.status == EngineeringStatus.COMPLETE, "COMPLETE without subsystems")
    _assert(result.completed, "completed True")
    _assert(result.has_warnings, "warnings emitted for missing subsystems")


# ===========================================================================
# SECTION 9 — Pipeline: guardrails blocking
# ===========================================================================

def test_pipeline_guardrails_block() -> None:
    _section("Pipeline — guardrails block")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_BlockingGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    req    = EngineeringRequest(request="Dangerous operation")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED, "status FAILED")
    _assert(not result.completed, "not completed")
    _assert(result.has_errors,    "errors populated")
    _assert(result.plan is not None, "plan was produced before block")


# ===========================================================================
# SECTION 10 — Pipeline: validation fail triggers debugger
# ===========================================================================

def test_pipeline_validation_failure_with_debugger() -> None:
    _section("Pipeline — validation fail → debugger invoked")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(),
        debugger=_StubDebugger(),
    )
    req    = EngineeringRequest(request="Buggy feature")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED,  "status FAILED after val fail")
    _assert(not result.completed,                        "not completed")
    _assert(result.required_debugging,                   "debugger was invoked")
    _assert(result.debug_report is not None,             "debug report populated")
    _assert(result.has_repair_plan,                      "repair plan populated")
    _assert(result.validation is not None,               "validation output captured")


def test_pipeline_validation_failure_no_debugger() -> None:
    _section("Pipeline — validation fail → no debugger")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(),
    )
    req    = EngineeringRequest(request="Buggy feature no debug")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED, "status FAILED")
    _assert(not result.required_debugging,             "debugger not invoked")
    _assert(result.debug_report is None,               "no debug report")
    _assert(result.has_errors,                         "error recorded for missing debugger")


# ===========================================================================
# SECTION 11 — Pipeline: subsystem exception handling
# ===========================================================================

def test_pipeline_planner_exception() -> None:
    _section("Pipeline — planner exception handled")

    c = EngineeringCoordinator(
        planner=_FailingPlanner(),
        guardrails=_StubGuardrails(),
    )
    req    = EngineeringRequest(request="Plan this")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED, "planner exception → FAILED")
    _assert(result.has_errors,                          "errors recorded")


def test_pipeline_guardrails_exception() -> None:
    _section("Pipeline — guardrails exception handled")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_FailingGuardrails(),
    )
    req    = EngineeringRequest(request="Guard this")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED, "guardrails exception → FAILED")
    _assert(result.has_errors,                          "errors recorded")


def test_pipeline_test_runner_exception() -> None:
    _section("Pipeline — test runner exception handled")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_RaisingTestRunner(),
    )
    req    = EngineeringRequest(request="Run tests")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED, "test runner exception → FAILED")
    _assert(result.has_errors,                          "errors recorded")


def test_pipeline_debugger_exception() -> None:
    _section("Pipeline — debugger exception handled")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(),
        debugger=_FailingDebugger(),
    )
    req    = EngineeringRequest(request="Debug crash")
    result = c.coordinate(req)

    # Debugger exception should not propagate — pipeline records error and returns FAILED
    _assert(result.status == EngineeringStatus.FAILED, "debugger exception → FAILED")
    _assert(result.has_errors,                          "errors recorded")


# ===========================================================================
# SECTION 12 — Pipeline: config toggles
# ===========================================================================

def test_pipeline_planning_disabled() -> None:
    _section("Pipeline — planning disabled by config")

    cfg = CoordinatorConfig(enable_planning=False)
    c   = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        config=cfg,
    )
    req    = EngineeringRequest(request="Skip planning")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.COMPLETE, "COMPLETE without planning")
    _assert(result.plan   is None,                        "no plan when disabled")
    _assert(result.has_warnings,                          "warning about disabled stage")


def test_pipeline_validation_disabled() -> None:
    _section("Pipeline — validation disabled by config")

    cfg = CoordinatorConfig(enable_validation=False)
    c   = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(),   # Would normally fail
        config=cfg,
    )
    req    = EngineeringRequest(request="Skip validation")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.COMPLETE, "COMPLETE when validation disabled")
    _assert(result.has_warnings,                          "warning about disabled stage")


def test_pipeline_debugging_disabled() -> None:
    _section("Pipeline — debugging disabled by config")

    cfg = CoordinatorConfig(enable_debugging=False)
    c   = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(),
        debugger=_StubDebugger(),
        config=cfg,
    )
    req    = EngineeringRequest(request="No debug")
    result = c.coordinate(req)

    _assert(result.status == EngineeringStatus.FAILED,  "FAILED without debugging")
    _assert(not result.required_debugging,               "debugger not invoked when disabled")


# ===========================================================================
# SECTION 13 — Type safety on coordinate()
# ===========================================================================

def test_coordinate_type_safety() -> None:
    _section("coordinate() — type safety")

    c = EngineeringCoordinator()

    try:
        c.coordinate("not a request")  # type: ignore
        _assert(False, "str input should raise TypeError")
    except TypeError:
        _assert(True, "str input raises TypeError")

    try:
        c.coordinate(None)  # type: ignore
        _assert(False, "None input should raise TypeError")
    except TypeError:
        _assert(True, "None input raises TypeError")


# ===========================================================================
# SECTION 14 — Duration tracking
# ===========================================================================

def test_pipeline_duration_tracking() -> None:
    _section("Pipeline — duration tracking")

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    req    = EngineeringRequest(request="Timed request")
    before = int(time.monotonic() * 1000)
    result = c.coordinate(req)
    after  = int(time.monotonic() * 1000)

    _assert(result.duration_ms is not None,     "duration_ms set")
    _assert(result.duration_ms >= 0,            "duration_ms non-negative")
    _assert(result.duration_ms <= after - before + 5, "duration_ms within wall time")


# ===========================================================================
# SECTION 15 — CoordinatorEvent
# ===========================================================================

def test_coordinator_event() -> None:
    _section("CoordinatorEvent")

    e = CoordinatorEvent(stage="planning", status=EngineeringStatus.PLANNING, detail="test")
    _assert(e.stage  == "planning",                 "stage stored")
    _assert(e.status == EngineeringStatus.PLANNING, "status stored")
    _assert(e.detail == "test",                     "detail stored")
    _assert("CoordinatorEvent" in repr(e),          "repr correct")

    # Default detail is empty string
    e2 = CoordinatorEvent(stage="x", status=EngineeringStatus.PENDING)
    _assert(e2.detail == "", "default detail empty")


# ===========================================================================
# SECTION 16 — Public API surface
# ===========================================================================

def test_public_api_surface() -> None:
    _section("Public API surface — __init__ exports")

    import core.engineering.coordinator as pkg

    _assert(hasattr(pkg, "EngineeringCoordinator"), "EngineeringCoordinator exported")
    _assert(hasattr(pkg, "EngineeringRequest"),     "EngineeringRequest exported")
    _assert(hasattr(pkg, "EngineeringResult"),      "EngineeringResult exported")
    _assert(hasattr(pkg, "EngineeringStatus"),      "EngineeringStatus exported")
    _assert(hasattr(pkg, "CoordinatorConfig"),      "CoordinatorConfig exported")
    _assert(hasattr(pkg, "CoordinatorEvent"),       "CoordinatorEvent exported")
    _assert(len(pkg.__all__) == 6,                  "__all__ has 6 entries")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 001 — Engineering Coordinator Tests")
    print("=" * 60)

    test_status()
    test_request_construction()
    test_request_properties()
    test_request_with_metadata()
    test_request_validation_errors()
    test_request_repr()
    test_result_construction()
    test_result_properties()
    test_result_duration_validation()
    test_result_summary()
    test_coordinator_config()
    test_coordinator_construction()
    test_coordinator_describe()
    test_coordinator_repr()
    test_coordinator_observers()
    test_pipeline_full_pass()
    test_pipeline_no_subsystems()
    test_pipeline_guardrails_block()
    test_pipeline_validation_failure_with_debugger()
    test_pipeline_validation_failure_no_debugger()
    test_pipeline_planner_exception()
    test_pipeline_guardrails_exception()
    test_pipeline_test_runner_exception()
    test_pipeline_debugger_exception()
    test_pipeline_planning_disabled()
    test_pipeline_validation_disabled()
    test_pipeline_debugging_disabled()
    test_coordinate_type_safety()
    test_pipeline_duration_tracking()
    test_coordinator_event()
    test_public_api_surface()

    print("\n" + "=" * 60)
    print(f"  Results: {_PASSED} passed, {_FAILED} failed")
    if _ERRORS:
        print()
        for e in _ERRORS:
            print(f"  {e}")
    print("=" * 60)

    if _FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()