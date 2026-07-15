"""
Genesis-018 Sprint 002 — Engineering Coordinator Test Suite
Deterministic validation: ~290 checks.

Covers Sprint 001 (backwards compatibility) + Sprint 002 (workflow & state).

Run:
    python tests/test_engineering_coordinator.py
    python -m pytest tests/test_engineering_coordinator.py -v
"""

from __future__ import annotations

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.engineering.coordinator import (
    CoordinatorConfig,
    CoordinatorEvent,
    CoordinatorEventLog,
    EngineeringCoordinator,
    EngineeringRequest,
    EngineeringResult,
    EngineeringSession,
    EngineeringStage,
    EngineeringStatus,
    SessionEvent,
)


# ===========================================================================
# Stub subsystems
# ===========================================================================

class _StubPlanner:
    def plan(self, request: str, *, context: str = "") -> str:
        return f"Plan for: {request}"

class _FailingPlanner:
    def plan(self, request: str, **kwargs) -> str:
        raise RuntimeError("Planner internal error")

class _StubGuardrails:
    def check(self, request: str, *, plan=None) -> bool:
        return True

class _BlockingGuardrails:
    def check(self, request: str, **kwargs) -> bool:
        return False

class _FailingGuardrails:
    def check(self, request: str, **kwargs) -> bool:
        raise RuntimeError("Guardrails internal error")

class _PassingTestRunner:
    class _Result:
        passed = True
        def __str__(self): return "All tests passed"
    def run(self, request: str, **kwargs):
        return self._Result()

class _FailingTestRunner:
    class _Result:
        passed = False
        def __str__(self): return "Tests failed: assertion error"
    def run(self, request: str, **kwargs):
        return self._Result()

class _RaisingTestRunner:
    def run(self, request: str, **kwargs):
        raise RuntimeError("Test runner crashed")

class _StubDebugger:
    class _Result:
        report      = "Debug complete: issue identified"
        repair_plan = "Repair plan: apply patch A"
        def __str__(self): return "Debug complete: issue identified"
    def debug(self, request: str, **kwargs):
        return self._Result()

class _FailingDebugger:
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
# ── SPRINT 001 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_status() -> None:
    _section("[S001] EngineeringStatus")
    _assert(EngineeringStatus.PENDING.value    == "PENDING",    "PENDING value")
    _assert(EngineeringStatus.PLANNING.value   == "PLANNING",   "PLANNING value")
    _assert(EngineeringStatus.VALIDATING.value == "VALIDATING", "VALIDATING value")
    _assert(EngineeringStatus.DEBUGGING.value  == "DEBUGGING",  "DEBUGGING value")
    _assert(EngineeringStatus.COMPLETE.value   == "COMPLETE",   "COMPLETE value")
    _assert(EngineeringStatus.FAILED.value     == "FAILED",     "FAILED value")
    _assert(EngineeringStatus.COMPLETE.is_terminal(),           "COMPLETE is terminal")
    _assert(EngineeringStatus.FAILED.is_terminal(),             "FAILED is terminal")
    _assert(not EngineeringStatus.PENDING.is_terminal(),        "PENDING not terminal")
    _assert(EngineeringStatus.PENDING.is_active(),              "PENDING is active")
    _assert(not EngineeringStatus.COMPLETE.is_active(),         "COMPLETE not active")
    _assert(len(EngineeringStatus) == 6,                        "Exactly 6 status values")


def test_request_construction() -> None:
    _section("[S001] EngineeringRequest — construction")
    r = EngineeringRequest(request="Refactor auth module")
    _assert(r.request  == "Refactor auth module", "request stored")
    _assert(r.context  == "",                     "default context")
    _assert(r.priority == 0,                      "default priority")
    _assert(r.metadata == {},                     "default metadata")
    try:
        r.request = "mutated"  # type: ignore
        _assert(False, "Request should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "Request is immutable")


def test_request_validation() -> None:
    _section("[S001] EngineeringRequest — validation errors")
    for label, kwargs, exc in [
        ("blank request",    {"request": "   "},         ValueError),
        ("non-str request",  {"request": 123},           TypeError),
        ("non-int priority", {"request": "x", "priority": "high"}, TypeError),
        ("non-dict metadata",{"request": "x", "metadata": "bad"},  TypeError),
        ("non-str context",  {"request": "x", "context": 42},      TypeError),
    ]:
        try:
            EngineeringRequest(**kwargs)  # type: ignore
            _assert(False, f"{label} should raise {exc.__name__}")
        except exc:
            _assert(True, f"{label} raises {exc.__name__}")


def test_request_properties() -> None:
    _section("[S001] EngineeringRequest — properties")
    _assert(not EngineeringRequest(request="A").has_context,               "no context")
    _assert(EngineeringRequest(request="A", context="ctx").has_context,    "has context")
    _assert(not EngineeringRequest(request="A", priority=0).is_high_priority, "prio 0")
    _assert(EngineeringRequest(request="A", priority=1).is_high_priority,      "prio 1")
    r  = EngineeringRequest(request="A", metadata={"a": 1})
    r2 = r.with_metadata(b=2)
    _assert(r.metadata == {"a": 1},         "original metadata unchanged")
    _assert(r2.metadata == {"a": 1, "b": 2}, "metadata merged")


def test_result_construction() -> None:
    _section("[S001] EngineeringResult — construction & properties")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.status    == EngineeringStatus.COMPLETE, "status stored")
    _assert(res.succeeded,                               "succeeded")
    _assert(not res.failed,                              "not failed")
    _assert(not res.has_errors,                          "no errors")

    failed = EngineeringResult(
        status=EngineeringStatus.FAILED, errors=["oops"]
    )
    _assert(failed.failed,       "failed flag")
    _assert(failed.has_errors,   "has errors")
    _assert(failed.error_count == 1, "error count")

    # Immutability
    try:
        res.status = EngineeringStatus.FAILED  # type: ignore
        _assert(False, "Result should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "Result is immutable")

    # Duration validation
    try:
        EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=-1)
        _assert(False, "Negative duration should raise")
    except ValueError:
        _assert(True, "Negative duration raises ValueError")


def test_coordinator_config() -> None:
    _section("[S001] CoordinatorConfig")
    cfg = CoordinatorConfig()
    _assert(cfg.enable_planning,   "planning default on")
    _assert(cfg.enable_guardrails, "guardrails default on")
    _assert(cfg.enable_validation, "validation default on")
    _assert(cfg.enable_debugging,  "debugging default on")
    _assert(cfg.max_debug_cycles == 1, "default max_debug_cycles")
    try:
        CoordinatorConfig(max_debug_cycles=-1)
        _assert(False, "Negative cycles should raise")
    except ValueError:
        _assert(True, "Negative cycles raises ValueError")


def test_coordinator_construction() -> None:
    _section("[S001] EngineeringCoordinator — construction")
    c = EngineeringCoordinator()
    _assert(not c.has_planner,     "no planner")
    _assert(not c.has_guardrails,  "no guardrails")
    _assert(not c.has_test_runner, "no test runner")
    _assert(not c.has_debugger,    "no debugger")
    _assert(c.observer_count == 0, "no observers")
    _assert("018.002" in c.VERSION, "version contains sprint")

    c2 = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(), debugger=_StubDebugger(),
    )
    _assert(c2.has_planner,     "planner registered")
    _assert(c2.has_guardrails,  "guardrails registered")
    _assert(c2.has_test_runner, "test runner registered")
    _assert(c2.has_debugger,    "debugger registered")


def test_coordinator_observers() -> None:
    _section("[S001] Observer system")
    events = []
    def capture(e): events.append(e)

    c = EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    c.add_observer(capture)
    _assert(c.observer_count == 1, "observer count 1")
    c.add_observer(capture)
    _assert(c.observer_count == 1, "duplicate not added")

    c.coordinate(EngineeringRequest(request="Observe"))
    _assert(len(events) > 0, "events emitted")
    _assert(all(isinstance(e, CoordinatorEvent) for e in events), "all CoordinatorEvent")

    c.remove_observer(capture)
    _assert(c.observer_count == 0, "observer removed")

    try:
        c.add_observer("not callable")  # type: ignore
        _assert(False, "Non-callable should raise")
    except TypeError:
        _assert(True, "Non-callable raises TypeError")


def test_pipeline_full_pass_s001() -> None:
    _section("[S001] Pipeline — full pass")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(), debugger=_StubDebugger(),
    )
    result = c.coordinate(EngineeringRequest(request="Build auth service"))
    _assert(result.status    == EngineeringStatus.COMPLETE, "COMPLETE")
    _assert(result.completed,                               "completed")
    _assert(result.succeeded,                               "succeeded")
    _assert(result.plan is not None,                        "plan populated")
    _assert(result.debug_report is None,                    "no debug on pass")
    _assert(result.duration_ms is not None,                 "duration set")
    _assert(result.duration_ms >= 0,                        "duration non-negative")


def test_pipeline_guardrails_block_s001() -> None:
    _section("[S001] Pipeline — guardrails block")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_BlockingGuardrails(),
    )
    result = c.coordinate(EngineeringRequest(request="Dangerous op"))
    _assert(result.status == EngineeringStatus.FAILED, "FAILED on block")
    _assert(not result.completed, "not completed")
    _assert(result.has_errors,    "errors populated")


def test_pipeline_validation_failure_s001() -> None:
    _section("[S001] Pipeline — validation fail → debugger")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(), debugger=_StubDebugger(),
    )
    result = c.coordinate(EngineeringRequest(request="Buggy feature"))
    _assert(result.status == EngineeringStatus.FAILED, "FAILED")
    _assert(result.required_debugging,  "debugger invoked")
    _assert(result.has_repair_plan,     "repair plan populated")


def test_pipeline_exception_handling_s001() -> None:
    _section("[S001] Pipeline — exception handling")
    for label, kwargs in [
        ("planner exc",    {"planner": _FailingPlanner(), "guardrails": _StubGuardrails()}),
        ("guardrails exc", {"planner": _StubPlanner(), "guardrails": _FailingGuardrails()}),
        ("testrunner exc", {"planner": _StubPlanner(), "guardrails": _StubGuardrails(), "test_runner": _RaisingTestRunner()}),
        ("debugger exc",   {"planner": _StubPlanner(), "guardrails": _StubGuardrails(), "test_runner": _FailingTestRunner(), "debugger": _FailingDebugger()}),
    ]:
        c = EngineeringCoordinator(**kwargs)
        result = c.coordinate(EngineeringRequest(request="Test exception"))
        _assert(result.status == EngineeringStatus.FAILED, f"{label} → FAILED")
        _assert(result.has_errors, f"{label} → errors recorded")


def test_pipeline_config_toggles_s001() -> None:
    _section("[S001] Pipeline — config toggles")
    # planning disabled
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        config=CoordinatorConfig(enable_planning=False),
    )
    result = c.coordinate(EngineeringRequest(request="Skip plan"))
    _assert(result.status == EngineeringStatus.COMPLETE, "COMPLETE no planning")
    _assert(result.plan is None, "no plan when disabled")

    # debugging disabled
    c2 = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(), debugger=_StubDebugger(),
        config=CoordinatorConfig(enable_debugging=False),
    )
    result2 = c2.coordinate(EngineeringRequest(request="No debug"))
    _assert(result2.status == EngineeringStatus.FAILED, "FAILED no debug")
    _assert(not result2.required_debugging, "debugger not invoked")


def test_coordinate_type_safety_s001() -> None:
    _section("[S001] coordinate() — type safety")
    c = EngineeringCoordinator()
    for bad_input in ["not a request", None, 42]:
        try:
            c.coordinate(bad_input)  # type: ignore
            _assert(False, f"Should raise TypeError for {type(bad_input).__name__}")
        except TypeError:
            _assert(True, f"TypeError for {type(bad_input).__name__}")


# ===========================================================================
# ── SPRINT 002 — EngineeringStage ──────────────────────────────────────────
# ===========================================================================

def test_engineering_stage() -> None:
    _section("[S002] EngineeringStage — enum values")
    expected = [
        "INITIALISING", "PLANNING", "GUARDRAILS", "VALIDATION",
        "DEBUGGING", "REPAIR_PLANNING", "COMPLETE", "FAILED",
    ]
    for val in expected:
        _assert(EngineeringStage(val).value == val, f"Stage {val} exists")

    _assert(len(EngineeringStage) == 8, "Exactly 8 stage values")


def test_engineering_stage_properties() -> None:
    _section("[S002] EngineeringStage — properties")
    _assert(EngineeringStage.COMPLETE.is_terminal(),        "COMPLETE terminal")
    _assert(EngineeringStage.FAILED.is_terminal(),          "FAILED terminal")
    _assert(not EngineeringStage.PLANNING.is_terminal(),    "PLANNING not terminal")
    _assert(not EngineeringStage.INITIALISING.is_terminal(),"INITIALISING not terminal")

    _assert(EngineeringStage.PLANNING.is_active(),          "PLANNING active")
    _assert(EngineeringStage.GUARDRAILS.is_active(),        "GUARDRAILS active")
    _assert(not EngineeringStage.COMPLETE.is_active(),      "COMPLETE not active")
    _assert(not EngineeringStage.FAILED.is_active(),        "FAILED not active")

    _assert(EngineeringStage.DEBUGGING.is_failure_path(),       "DEBUGGING failure path")
    _assert(EngineeringStage.REPAIR_PLANNING.is_failure_path(), "REPAIR_PLANNING failure path")
    _assert(not EngineeringStage.PLANNING.is_failure_path(),    "PLANNING not failure path")
    _assert(not EngineeringStage.COMPLETE.is_failure_path(),    "COMPLETE not failure path")


# ===========================================================================
# ── SPRINT 002 — SessionEvent ───────────────────────────────────────────────
# ===========================================================================

def test_session_event_construction() -> None:
    _section("[S002] SessionEvent — construction")
    e = SessionEvent(
        stage=EngineeringStage.PLANNING,
        description="Planning started",
        timestamp_ms=1000,
    )
    _assert(e.stage       == EngineeringStage.PLANNING, "stage stored")
    _assert(e.description == "Planning started",        "description stored")
    _assert(e.timestamp_ms == 1000,                     "timestamp stored")
    _assert(e.detail      == "",                        "default detail")
    _assert(e.duration_ms is None,                      "default duration None")
    _assert(not e.has_duration,                         "has_duration False")

    e2 = SessionEvent(
        stage=EngineeringStage.PLANNING,
        description="Planning complete",
        timestamp_ms=2000,
        detail="took 50ms",
        duration_ms=50,
    )
    _assert(e2.has_duration,        "has_duration True")
    _assert(e2.duration_ms == 50,   "duration stored")
    _assert(e2.detail == "took 50ms", "detail stored")


def test_session_event_immutability() -> None:
    _section("[S002] SessionEvent — immutability")
    e = SessionEvent(
        stage=EngineeringStage.PLANNING,
        description="Test",
        timestamp_ms=100,
    )
    try:
        e.description = "mutated"  # type: ignore
        _assert(False, "SessionEvent should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "SessionEvent is immutable")


def test_session_event_validation() -> None:
    _section("[S002] SessionEvent — validation errors")
    # wrong stage type
    try:
        SessionEvent(stage="PLANNING", description="x", timestamp_ms=0)  # type: ignore
        _assert(False, "str stage should raise TypeError")
    except TypeError:
        _assert(True, "str stage raises TypeError")
    # blank description
    try:
        SessionEvent(stage=EngineeringStage.PLANNING, description="   ", timestamp_ms=0)
        _assert(False, "blank description should raise ValueError")
    except ValueError:
        _assert(True, "blank description raises ValueError")
    # wrong timestamp type
    try:
        SessionEvent(stage=EngineeringStage.PLANNING, description="x", timestamp_ms="now")  # type: ignore
        _assert(False, "str timestamp should raise TypeError")
    except TypeError:
        _assert(True, "str timestamp raises TypeError")


def test_session_event_repr() -> None:
    _section("[S002] SessionEvent — repr")
    e = SessionEvent(
        stage=EngineeringStage.PLANNING,
        description="Test event",
        timestamp_ms=0,
        duration_ms=25,
    )
    r = repr(e)
    _assert("SessionEvent" in r, "repr has class name")
    _assert("PLANNING"    in r,  "repr has stage")
    _assert("25ms"        in r,  "repr has duration")


# ===========================================================================
# ── SPRINT 002 — CoordinatorEventLog ───────────────────────────────────────
# ===========================================================================

def test_event_log_basic() -> None:
    _section("[S002] CoordinatorEventLog — basic recording")
    log = CoordinatorEventLog()
    _assert(log.is_empty,             "starts empty")
    _assert(log.event_count == 0,     "event count 0")
    _assert(not log.is_sealed,        "not sealed initially")

    e = log.record(EngineeringStage.PLANNING, "Planning started")
    _assert(isinstance(e, SessionEvent),  "record returns SessionEvent")
    _assert(log.event_count == 1,         "event count 1")
    _assert(not log.is_empty,             "not empty")

    log.record(EngineeringStage.GUARDRAILS, "Guardrails checked", duration_ms=10)
    _assert(log.event_count == 2, "event count 2")


def test_event_log_seal() -> None:
    _section("[S002] CoordinatorEventLog — seal")
    log = CoordinatorEventLog()
    log.record(EngineeringStage.PLANNING, "event")
    log.seal()
    _assert(log.is_sealed, "sealed after seal()")

    try:
        log.record(EngineeringStage.GUARDRAILS, "post-seal event")
        _assert(False, "Recording after seal should raise RuntimeError")
    except RuntimeError:
        _assert(True, "RuntimeError on sealed log")


def test_event_log_events_copy() -> None:
    _section("[S002] CoordinatorEventLog — events() returns copy")
    log = CoordinatorEventLog()
    log.record(EngineeringStage.PLANNING, "event 1")
    snapshot = log.events()
    snapshot.append(None)  # type: ignore  # mutate copy
    _assert(log.event_count == 1, "original log unaffected by snapshot mutation")


def test_event_log_events_for_stage() -> None:
    _section("[S002] CoordinatorEventLog — events_for_stage")
    log = CoordinatorEventLog()
    log.record(EngineeringStage.PLANNING,   "plan start")
    log.record(EngineeringStage.PLANNING,   "plan end")
    log.record(EngineeringStage.GUARDRAILS, "guardrails")

    plan_events = log.events_for_stage(EngineeringStage.PLANNING)
    guard_events = log.events_for_stage(EngineeringStage.GUARDRAILS)
    debug_events = log.events_for_stage(EngineeringStage.DEBUGGING)

    _assert(len(plan_events)  == 2, "2 planning events")
    _assert(len(guard_events) == 1, "1 guardrails event")
    _assert(len(debug_events) == 0, "0 debugging events")


def test_event_log_stages_visited() -> None:
    _section("[S002] CoordinatorEventLog — stages_visited")
    log = CoordinatorEventLog()
    log.record(EngineeringStage.PLANNING,   "p1")
    log.record(EngineeringStage.PLANNING,   "p2")
    log.record(EngineeringStage.GUARDRAILS, "g1")
    log.record(EngineeringStage.COMPLETE,   "done")

    stages = log.stages_visited()
    _assert(len(stages) == 3, "3 unique stages")
    _assert(stages[0] == EngineeringStage.PLANNING,   "first stage PLANNING")
    _assert(stages[1] == EngineeringStage.GUARDRAILS, "second stage GUARDRAILS")
    _assert(stages[2] == EngineeringStage.COMPLETE,   "third stage COMPLETE")


def test_event_log_total_duration() -> None:
    _section("[S002] CoordinatorEventLog — total_duration_ms")
    log = CoordinatorEventLog()
    _assert(log.total_duration_ms() is None, "None with <2 events")

    log.record(EngineeringStage.PLANNING,   "start")
    _assert(log.total_duration_ms() is None, "None with exactly 1 event")

    log.record(EngineeringStage.GUARDRAILS, "end")
    dur = log.total_duration_ms()
    _assert(dur is not None, "duration set with 2 events")
    _assert(dur >= 0,        "duration non-negative")


def test_event_log_timeline() -> None:
    _section("[S002] CoordinatorEventLog — timeline()")
    log = CoordinatorEventLog()
    log.record(EngineeringStage.PLANNING,   "Planning started")
    log.record(EngineeringStage.GUARDRAILS, "Guardrails passed", duration_ms=5)

    lines = log.timeline()
    _assert(isinstance(lines, list),      "timeline returns list")
    _assert(len(lines) == 2,              "2 timeline entries")
    _assert("PLANNING" in lines[0],       "first entry has PLANNING")
    _assert("GUARDRAILS" in lines[1],     "second entry has GUARDRAILS")
    _assert("5ms" in lines[1],            "duration in timeline entry")


def test_event_log_repr() -> None:
    _section("[S002] CoordinatorEventLog — repr")
    log = CoordinatorEventLog()
    _assert("CoordinatorEventLog" in repr(log), "repr has class name")
    _assert("sealed=False" in repr(log),        "sealed=False in repr")
    log.seal()
    _assert("sealed=True" in repr(log),         "sealed=True after seal")


# ===========================================================================
# ── SPRINT 002 — EngineeringSession ────────────────────────────────────────
# ===========================================================================

def test_session_creation() -> None:
    _section("[S002] EngineeringSession — creation")
    req = EngineeringRequest(request="Test session")
    s   = EngineeringSession.create(req)

    _assert(isinstance(s.session_id, str),          "session_id is str")
    _assert(len(s.session_id) > 0,                  "session_id non-empty")
    _assert(s.request is req,                        "request stored")
    _assert(s.status == EngineeringStatus.PENDING,   "initial status PENDING")
    _assert(s.current_stage == EngineeringStage.INITIALISING, "initial stage INITIALISING")
    _assert(s.started_at > 0,                        "started_at set")
    _assert(s.completed_at is None,                  "not yet completed")
    _assert(not s.is_complete,                       "is_complete False")
    _assert(s.duration_ms is None,                   "duration None before completion")
    _assert(s.result is None,                        "no result yet")


def test_session_uniqueness() -> None:
    _section("[S002] EngineeringSession — unique session IDs")
    req = EngineeringRequest(request="Unique")
    ids = {EngineeringSession.create(req).session_id for _ in range(10)}
    _assert(len(ids) == 10, "All 10 session IDs are unique")


def test_session_advance_to() -> None:
    _section("[S002] EngineeringSession — advance_to")
    req = EngineeringRequest(request="Advance test")
    s   = EngineeringSession.create(req)

    s.advance_to(EngineeringStage.PLANNING, "Planning started")
    _assert(s.current_stage == EngineeringStage.PLANNING, "stage advanced to PLANNING")
    _assert(s.events.event_count == 1,                    "one event recorded")

    s.advance_to(EngineeringStage.GUARDRAILS, "Guardrails started", duration_ms=10)
    _assert(s.current_stage == EngineeringStage.GUARDRAILS, "stage advanced to GUARDRAILS")
    _assert(s.events.event_count == 2,                      "two events recorded")


def test_session_complete() -> None:
    _section("[S002] EngineeringSession — complete")
    req  = EngineeringRequest(request="Complete me")
    s    = EngineeringSession.create(req)
    s.advance_to(EngineeringStage.PLANNING, "Planning")
    s.advance_to(EngineeringStage.COMPLETE, "Done")

    result = EngineeringResult(
        status=EngineeringStatus.COMPLETE, completed=True, duration_ms=50
    )
    s.complete(result)

    _assert(s.is_complete,                            "is_complete True")
    _assert(s.completed_at is not None,               "completed_at set")
    _assert(s.duration_ms is not None,                "duration_ms set")
    _assert(s.duration_ms >= 0,                       "duration_ms non-negative")
    _assert(s.status == EngineeringStatus.COMPLETE,   "status from result")
    _assert(s.result is result,                       "result stored")
    _assert(s.events.is_sealed,                       "log sealed on complete")

    # Sealed — no more events
    try:
        s.events.record(EngineeringStage.PLANNING, "post-complete")
        _assert(False, "Should not record after complete")
    except RuntimeError:
        _assert(True, "RuntimeError after complete")


def test_session_stages_visited() -> None:
    _section("[S002] EngineeringSession — stages_visited")
    req = EngineeringRequest(request="Stage tracking")
    s   = EngineeringSession.create(req)
    s.advance_to(EngineeringStage.PLANNING,   "p")
    s.advance_to(EngineeringStage.GUARDRAILS, "g")
    s.advance_to(EngineeringStage.VALIDATION, "v")

    stages = s.stages_visited
    _assert(EngineeringStage.PLANNING   in stages, "PLANNING visited")
    _assert(EngineeringStage.GUARDRAILS in stages, "GUARDRAILS visited")
    _assert(EngineeringStage.VALIDATION in stages, "VALIDATION visited")
    _assert(s.stage_count == 3,                    "stage_count 3")


def test_session_stage_durations() -> None:
    _section("[S002] EngineeringSession — stage_durations")
    req = EngineeringRequest(request="Duration tracking")
    s   = EngineeringSession.create(req)
    s.advance_to(EngineeringStage.PLANNING,   "plan start")
    s.advance_to(EngineeringStage.PLANNING,   "plan end",   duration_ms=30)
    s.advance_to(EngineeringStage.GUARDRAILS, "guard",      duration_ms=10)

    durations = s.stage_durations()
    _assert(isinstance(durations, dict),             "returns dict")
    _assert("PLANNING"   in durations,               "PLANNING in durations")
    _assert("GUARDRAILS" in durations,               "GUARDRAILS in durations")
    _assert(durations["PLANNING"]   == 30,           "PLANNING duration 30ms")
    _assert(durations["GUARDRAILS"] == 10,           "GUARDRAILS duration 10ms")


def test_session_replay() -> None:
    _section("[S002] EngineeringSession — replay")
    req = EngineeringRequest(request="Replay test", priority=2)
    s   = EngineeringSession.create(req)
    s.advance_to(EngineeringStage.PLANNING,   "Planning started")
    s.advance_to(EngineeringStage.GUARDRAILS, "Guardrails passed")
    s.advance_to(EngineeringStage.COMPLETE,   "Done")
    result = EngineeringResult(
        status=EngineeringStatus.COMPLETE, completed=True, duration_ms=100
    )
    s.complete(result)

    lines = s.replay()
    _assert(isinstance(lines, list),         "replay returns list")
    _assert(len(lines) > 0,                  "replay non-empty")
    replay_text = "\n".join(lines)
    _assert(s.session_id in replay_text,     "session_id in replay")
    _assert("Replay test" in replay_text,    "request in replay")
    _assert("COMPLETE" in replay_text,       "outcome in replay")
    _assert("PLANNING" in replay_text,       "PLANNING stage in replay")
    _assert("GUARDRAILS" in replay_text,     "GUARDRAILS stage in replay")


def test_session_repr() -> None:
    _section("[S002] EngineeringSession — repr")
    req = EngineeringRequest(request="Repr test")
    s   = EngineeringSession.create(req)
    r   = repr(s)
    _assert("EngineeringSession" in r, "repr has class name")
    _assert("PENDING"            in r, "repr has status")


# ===========================================================================
# ── SPRINT 002 — EngineeringResult expanded ────────────────────────────────
# ===========================================================================

def test_result_sprint002_fields() -> None:
    _section("[S002] EngineeringResult — Sprint 002 fields")
    # Default — no sprint 002 fields
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.session         is None, "session defaults None")
    _assert(res.timeline        == [],   "timeline defaults empty")
    _assert(res.stage_durations == {},   "stage_durations defaults empty")
    _assert(not res.has_session,         "has_session False")
    _assert(not res.has_timeline,        "has_timeline False")
    _assert(res.session_id is None,      "session_id None without session")
    _assert(res.stages_visited() == [],  "stages_visited empty without session")


def test_result_with_session() -> None:
    _section("[S002] EngineeringResult — with session attached")
    req = EngineeringRequest(request="With session")
    s   = EngineeringSession.create(req)
    s.advance_to(EngineeringStage.COMPLETE, "Done")

    res = EngineeringResult(
        status=EngineeringStatus.COMPLETE,
        completed=True,
        session=s,
        timeline=["[COMPLETE] Done"],
        stage_durations={"COMPLETE": None},
    )
    _assert(res.has_session,                           "has_session True")
    _assert(res.session_id == s.session_id,            "session_id matches")
    _assert(res.has_timeline,                          "has_timeline True")
    _assert(res.has_stage_durations,                   "has_stage_durations True")
    _assert("COMPLETE" in res.stages_visited(),        "COMPLETE in stages_visited")
    _assert("session=" in res.summary(),               "session in summary")


# ===========================================================================
# ── SPRINT 002 — Pipeline integration (session lifecycle) ──────────────────
# ===========================================================================

def test_pipeline_session_created() -> None:
    _section("[S002] Pipeline — session created on every coordinate()")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    result = c.coordinate(EngineeringRequest(request="Session check"))
    _assert(result.has_session,       "session attached to result")
    _assert(result.session_id is not None, "session_id present")
    _assert(result.session.is_complete,    "session is complete")
    _assert(result.session.events.is_sealed, "event log is sealed")


def test_pipeline_session_unique_per_request() -> None:
    _section("[S002] Pipeline — unique session per request")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    r1 = c.coordinate(EngineeringRequest(request="Request A"))
    r2 = c.coordinate(EngineeringRequest(request="Request B"))
    _assert(r1.session_id != r2.session_id, "unique session IDs")


def test_pipeline_session_stages_happy_path() -> None:
    _section("[S002] Pipeline — session stages on happy path")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    result = c.coordinate(EngineeringRequest(request="Happy path"))
    stages = result.stages_visited()
    _assert("INITIALISING" in stages, "INITIALISING visited")
    _assert("PLANNING"     in stages, "PLANNING visited")
    _assert("GUARDRAILS"   in stages, "GUARDRAILS visited")
    _assert("VALIDATION"   in stages, "VALIDATION visited")
    _assert("COMPLETE"     in stages, "COMPLETE visited")
    _assert("DEBUGGING"    not in stages, "DEBUGGING not on happy path")


def test_pipeline_session_stages_failure_path() -> None:
    _section("[S002] Pipeline — session stages on failure path")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(), debugger=_StubDebugger(),
    )
    result = c.coordinate(EngineeringRequest(request="Failure path"))
    stages = result.stages_visited()
    _assert("DEBUGGING"      in stages, "DEBUGGING visited on failure path")
    _assert("REPAIR_PLANNING" in stages, "REPAIR_PLANNING visited on failure path")
    _assert("FAILED"         in stages, "FAILED stage recorded")


def test_pipeline_session_stages_guardrails_block() -> None:
    _section("[S002] Pipeline — session stages on guardrails block")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_BlockingGuardrails(),
    )
    result = c.coordinate(EngineeringRequest(request="Blocked"))
    stages = result.stages_visited()
    _assert("INITIALISING" in stages, "INITIALISING visited")
    _assert("PLANNING"     in stages, "PLANNING visited")
    _assert("GUARDRAILS"   in stages, "GUARDRAILS visited")
    _assert("FAILED"       in stages, "FAILED recorded")
    _assert("VALIDATION"   not in stages, "VALIDATION not reached")


def test_pipeline_timeline_populated() -> None:
    _section("[S002] Pipeline — timeline populated on result")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    result = c.coordinate(EngineeringRequest(request="Timeline test"))
    _assert(result.has_timeline,          "timeline non-empty")
    _assert(len(result.timeline) > 0,     "timeline has entries")
    _assert(all(isinstance(l, str) for l in result.timeline), "all entries are str")


def test_pipeline_stage_durations_populated() -> None:
    _section("[S002] Pipeline — stage_durations on result")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    result = c.coordinate(EngineeringRequest(request="Duration test"))
    _assert(result.has_stage_durations, "stage_durations non-empty")
    _assert(isinstance(result.stage_durations, dict), "stage_durations is dict")


def test_pipeline_replay_replayable() -> None:
    _section("[S002] Pipeline — completed session is replayable")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    result  = c.coordinate(EngineeringRequest(request="Replay me"))
    session = result.session
    lines   = session.replay()
    replay  = "\n".join(lines)

    _assert(len(lines) > 3,           "replay has multiple lines")
    _assert("Replay me" in replay,    "request in replay")
    _assert("COMPLETE" in replay,     "COMPLETE outcome in replay")
    _assert(session.session_id in replay, "session_id in replay")


def test_pipeline_no_subsystems_session() -> None:
    _section("[S002] Pipeline — no subsystems still produces session")
    c      = EngineeringCoordinator()
    result = c.coordinate(EngineeringRequest(request="Bare request"))
    _assert(result.has_session, "session present with no subsystems")
    _assert(result.session.is_complete, "session complete")


def test_pipeline_duration_tracking_sprint002() -> None:
    _section("[S002] Pipeline — duration tracking")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
    )
    before = int(time.monotonic() * 1000)
    result = c.coordinate(EngineeringRequest(request="Timed"))
    after  = int(time.monotonic() * 1000)

    _assert(result.duration_ms is not None,          "duration_ms set")
    _assert(result.duration_ms >= 0,                 "duration_ms non-negative")
    _assert(result.duration_ms <= after - before + 5, "duration within wall time")
    _assert(result.session.duration_ms is not None,  "session duration_ms set")
    _assert(result.session.duration_ms >= 0,         "session duration_ms non-negative")


# ===========================================================================
# ── SPRINT 002 — Public API surface ────────────────────────────────────────
# ===========================================================================

def test_public_api_surface_sprint002() -> None:
    _section("[S002] Public API surface — __init__ exports")
    import core.engineering.coordinator as pkg

    expected = [
        "EngineeringCoordinator",
        "EngineeringRequest",
        "EngineeringResult",
        "EngineeringStatus",
        "CoordinatorConfig",
        "CoordinatorEvent",
        # Sprint 002
        "EngineeringStage",
        "EngineeringSession",
        "CoordinatorEventLog",
        "SessionEvent",
    ]
    for name in expected:
        _assert(hasattr(pkg, name), f"{name} exported")
    _assert(len(pkg.__all__) == 10, "__all__ has 10 entries")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 002 — Engineering Coordinator Tests")
    print("=" * 60)

    # Sprint 001 regression
    test_status()
    test_request_construction()
    test_request_validation()
    test_request_properties()
    test_result_construction()
    test_coordinator_config()
    test_coordinator_construction()
    test_coordinator_observers()
    test_pipeline_full_pass_s001()
    test_pipeline_guardrails_block_s001()
    test_pipeline_validation_failure_s001()
    test_pipeline_exception_handling_s001()
    test_pipeline_config_toggles_s001()
    test_coordinate_type_safety_s001()

    # Sprint 002
    test_engineering_stage()
    test_engineering_stage_properties()
    test_session_event_construction()
    test_session_event_immutability()
    test_session_event_validation()
    test_session_event_repr()
    test_event_log_basic()
    test_event_log_seal()
    test_event_log_events_copy()
    test_event_log_events_for_stage()
    test_event_log_stages_visited()
    test_event_log_total_duration()
    test_event_log_timeline()
    test_event_log_repr()
    test_session_creation()
    test_session_uniqueness()
    test_session_advance_to()
    test_session_complete()
    test_session_stages_visited()
    test_session_stage_durations()
    test_session_replay()
    test_session_repr()
    test_result_sprint002_fields()
    test_result_with_session()
    test_pipeline_session_created()
    test_pipeline_session_unique_per_request()
    test_pipeline_session_stages_happy_path()
    test_pipeline_session_stages_failure_path()
    test_pipeline_session_stages_guardrails_block()
    test_pipeline_timeline_populated()
    test_pipeline_stage_durations_populated()
    test_pipeline_replay_replayable()
    test_pipeline_no_subsystems_session()
    test_pipeline_duration_tracking_sprint002()
    test_public_api_surface_sprint002()

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