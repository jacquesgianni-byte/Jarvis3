"""
Genesis-018 Sprint 003 — Engineering Coordinator Test Suite
Deterministic validation: ~390 checks.

Sprint 001 regression + Sprint 002 regression + Sprint 003 queue & scheduling.

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
    EngineeringQueue,
    EngineeringRequest,
    EngineeringResult,
    EngineeringSession,
    EngineeringStage,
    EngineeringStatus,
    QueueSnapshot,
    QueueStatus,
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
        def __str__(self): return "Tests failed"
    def run(self, request: str, **kwargs):
        return self._Result()

class _RaisingTestRunner:
    def run(self, request: str, **kwargs):
        raise RuntimeError("Test runner crashed")

class _StubDebugger:
    class _Result:
        report      = "Debug complete"
        repair_plan = "Repair plan: apply patch A"
        def __str__(self): return "Debug complete"
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


def _make_coordinator(**kwargs):
    return EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        **kwargs,
    )

def _req(text="Test request"):
    return EngineeringRequest(request=text)


# ===========================================================================
# ── SPRINT 001 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_s001_status() -> None:
    _section("[S001] EngineeringStatus")
    for val in ["PENDING","PLANNING","VALIDATING","DEBUGGING","COMPLETE","FAILED"]:
        _assert(EngineeringStatus(val).value == val, f"Status {val} exists")
    _assert(EngineeringStatus.COMPLETE.is_terminal(),      "COMPLETE terminal")
    _assert(EngineeringStatus.FAILED.is_terminal(),        "FAILED terminal")
    _assert(not EngineeringStatus.PENDING.is_terminal(),   "PENDING not terminal")
    _assert(EngineeringStatus.PENDING.is_active(),         "PENDING active")
    _assert(not EngineeringStatus.COMPLETE.is_active(),    "COMPLETE not active")
    _assert(len(EngineeringStatus) == 6,                   "Exactly 6 status values")


def test_s001_request() -> None:
    _section("[S001] EngineeringRequest")
    r = EngineeringRequest(request="Refactor")
    _assert(r.request == "Refactor", "request stored")
    _assert(r.context == "",         "default context")
    _assert(r.priority == 0,         "default priority")
    _assert(r.metadata == {},        "default metadata")
    # immutability
    try:
        r.request = "mutated"  # type: ignore
        _assert(False, "should be immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")
    # validation
    for bad, exc in [
        ({"request": "   "}, ValueError),
        ({"request": 123}, TypeError),
        ({"request": "x", "priority": "hi"}, TypeError),
        ({"request": "x", "metadata": "bad"}, TypeError),
    ]:
        try:
            EngineeringRequest(**bad)  # type: ignore
            _assert(False, f"bad input should raise {exc.__name__}")
        except exc:
            _assert(True, f"bad input raises {exc.__name__}")
    # properties
    _assert(not EngineeringRequest(request="A").has_context, "no context")
    _assert(EngineeringRequest(request="A", context="x").has_context, "has context")
    _assert(not EngineeringRequest(request="A").is_high_priority, "prio 0")
    _assert(EngineeringRequest(request="A", priority=1).is_high_priority, "prio 1")


def test_s001_result() -> None:
    _section("[S001] EngineeringResult")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.succeeded,    "succeeded")
    _assert(not res.failed,   "not failed")
    _assert(not res.has_errors, "no errors")
    failed = EngineeringResult(status=EngineeringStatus.FAILED, errors=["oops"])
    _assert(failed.failed,       "failed flag")
    _assert(failed.error_count == 1, "error count")
    try:
        res.status = EngineeringStatus.FAILED  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")
    try:
        EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=-1)
        _assert(False, "negative duration")
    except ValueError:
        _assert(True, "negative duration raises")


def test_s001_coordinator_config() -> None:
    _section("[S001] CoordinatorConfig")
    cfg = CoordinatorConfig()
    _assert(cfg.enable_planning,   "planning on")
    _assert(cfg.enable_guardrails, "guardrails on")
    _assert(cfg.enable_validation, "validation on")
    _assert(cfg.max_debug_cycles == 1, "default cycles")
    try:
        CoordinatorConfig(max_debug_cycles=-1)
        _assert(False, "negative cycles")
    except ValueError:
        _assert(True, "negative cycles raises")


def test_s001_pipeline_pass() -> None:
    _section("[S001] Pipeline — full pass")
    c = _make_coordinator(debugger=_StubDebugger())
    r = c.coordinate(_req("Build auth"))
    _assert(r.status == EngineeringStatus.COMPLETE, "COMPLETE")
    _assert(r.succeeded,              "succeeded")
    _assert(r.plan is not None,       "plan populated")
    _assert(r.debug_report is None,   "no debug")
    _assert(r.duration_ms is not None, "duration set")


def test_s001_pipeline_guardrails_block() -> None:
    _section("[S001] Pipeline — guardrails block")
    c = EngineeringCoordinator(planner=_StubPlanner(), guardrails=_BlockingGuardrails())
    r = c.coordinate(_req())
    _assert(r.status == EngineeringStatus.FAILED, "FAILED on block")
    _assert(r.has_errors, "errors set")


def test_s001_pipeline_validation_fail() -> None:
    _section("[S001] Pipeline — validation fail → debug")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_FailingTestRunner(), debugger=_StubDebugger(),
    )
    r = c.coordinate(_req())
    _assert(r.status == EngineeringStatus.FAILED, "FAILED")
    _assert(r.required_debugging, "debugger invoked")
    _assert(r.has_repair_plan,    "repair plan")


def test_s001_exception_handling() -> None:
    _section("[S001] Pipeline — exception handling")
    cases = [
        EngineeringCoordinator(planner=_FailingPlanner(), guardrails=_StubGuardrails()),
        EngineeringCoordinator(planner=_StubPlanner(), guardrails=_FailingGuardrails()),
        EngineeringCoordinator(planner=_StubPlanner(), guardrails=_StubGuardrails(), test_runner=_RaisingTestRunner()),
    ]
    for c in cases:
        r = c.coordinate(_req())
        _assert(r.status == EngineeringStatus.FAILED, "exception → FAILED")
        _assert(r.has_errors, "errors recorded")


def test_s001_type_safety() -> None:
    _section("[S001] coordinate() — type safety")
    c = EngineeringCoordinator()
    for bad in ["string", None, 42]:
        try:
            c.coordinate(bad)  # type: ignore
            _assert(False, f"TypeError for {type(bad).__name__}")
        except TypeError:
            _assert(True, f"TypeError for {type(bad).__name__}")


# ===========================================================================
# ── SPRINT 002 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_s002_stage_enum() -> None:
    _section("[S002] EngineeringStage")
    expected = ["INITIALISING","PLANNING","GUARDRAILS","VALIDATION",
                "DEBUGGING","REPAIR_PLANNING","COMPLETE","FAILED"]
    for v in expected:
        _assert(EngineeringStage(v).value == v, f"Stage {v} exists")
    _assert(len(EngineeringStage) == 8, "Exactly 8 stages")
    _assert(EngineeringStage.COMPLETE.is_terminal(),      "COMPLETE terminal")
    _assert(EngineeringStage.FAILED.is_terminal(),        "FAILED terminal")
    _assert(not EngineeringStage.PLANNING.is_terminal(),  "PLANNING not terminal")
    _assert(EngineeringStage.DEBUGGING.is_failure_path(), "DEBUGGING failure path")
    _assert(not EngineeringStage.PLANNING.is_failure_path(), "PLANNING not failure path")


def test_s002_session_event() -> None:
    _section("[S002] SessionEvent")
    e = SessionEvent(stage=EngineeringStage.PLANNING, description="p", timestamp_ms=100)
    _assert(e.stage == EngineeringStage.PLANNING, "stage stored")
    _assert(e.description == "p",                 "description stored")
    _assert(not e.has_duration,                   "no duration")
    e2 = SessionEvent(stage=EngineeringStage.PLANNING, description="q", timestamp_ms=200, duration_ms=50)
    _assert(e2.has_duration,        "has duration")
    _assert(e2.duration_ms == 50,   "duration value")
    # immutability
    try:
        e.description = "mutated"  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")


def test_s002_event_log() -> None:
    _section("[S002] CoordinatorEventLog")
    log = CoordinatorEventLog()
    _assert(log.is_empty,         "starts empty")
    _assert(not log.is_sealed,    "not sealed")
    log.record(EngineeringStage.PLANNING, "plan")
    log.record(EngineeringStage.GUARDRAILS, "guard", duration_ms=5)
    _assert(log.event_count == 2, "2 events")
    log.seal()
    _assert(log.is_sealed, "sealed")
    try:
        log.record(EngineeringStage.PLANNING, "post-seal")
        _assert(False, "sealed raises")
    except RuntimeError:
        _assert(True, "sealed raises RuntimeError")
    # snapshot independence
    snap = log.events()
    snap.append(None)  # type: ignore
    _assert(log.event_count == 2, "snapshot mutation doesn't affect log")
    # stages_visited
    log2 = CoordinatorEventLog()
    log2.record(EngineeringStage.PLANNING, "a")
    log2.record(EngineeringStage.PLANNING, "b")
    log2.record(EngineeringStage.COMPLETE, "c")
    stages = log2.stages_visited()
    _assert(len(stages) == 2, "2 unique stages")


def test_s002_session_lifecycle() -> None:
    _section("[S002] EngineeringSession — lifecycle")
    req = EngineeringRequest(request="Test session")
    s   = EngineeringSession.create(req)
    _assert(s.status == EngineeringStatus.PENDING,             "initial PENDING")
    _assert(s.current_stage == EngineeringStage.INITIALISING,  "initial INITIALISING")
    _assert(not s.is_complete,                                 "not complete")
    _assert(s.duration_ms is None,                             "no duration yet")

    s.advance_to(EngineeringStage.PLANNING, "Planning")
    _assert(s.current_stage == EngineeringStage.PLANNING, "stage advanced")
    _assert(s.events.event_count == 1,                    "event recorded")

    result = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    s.complete(result)
    _assert(s.is_complete,          "is_complete True")
    _assert(s.events.is_sealed,     "log sealed")
    _assert(s.duration_ms is not None, "duration set")


def test_s002_session_replay() -> None:
    _section("[S002] EngineeringSession — replay")
    c   = _make_coordinator()
    res = c.coordinate(_req("Replay me"))
    lines = res.session.replay()
    text  = "\n".join(lines)
    _assert(len(lines) > 3,           "multi-line replay")
    _assert("Replay me" in text,      "request in replay")
    _assert("COMPLETE"  in text,      "outcome in replay")


def test_s002_result_sprint002_fields() -> None:
    _section("[S002] EngineeringResult — Sprint 002 fields")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE)
    _assert(res.session is None,          "session defaults None")
    _assert(res.timeline == [],           "timeline defaults empty")
    _assert(res.stage_durations == {},    "stage_durations defaults empty")

    c   = _make_coordinator()
    r   = c.coordinate(_req())
    _assert(r.has_session,               "session attached")
    _assert(r.has_timeline,              "timeline populated")
    _assert(r.has_stage_durations,       "stage_durations populated")
    _assert(r.session_id is not None,    "session_id accessible")
    _assert("COMPLETE" in r.stages_visited(), "COMPLETE in stages_visited")


# ===========================================================================
# ── SPRINT 003 — QueueStatus ───────────────────────────────────────────────
# ===========================================================================

def test_s003_queue_status_values() -> None:
    _section("[S003] QueueStatus — values")
    for val in ["EMPTY", "WAITING", "PROCESSING", "COMPLETE"]:
        _assert(QueueStatus(val).value == val, f"QueueStatus.{val} exists")
    _assert(len(QueueStatus) == 4, "Exactly 4 QueueStatus values")


def test_s003_queue_status_properties() -> None:
    _section("[S003] QueueStatus — properties")
    _assert(QueueStatus.EMPTY.is_idle(),       "EMPTY is idle")
    _assert(QueueStatus.COMPLETE.is_idle(),    "COMPLETE is idle")
    _assert(not QueueStatus.WAITING.is_idle(), "WAITING not idle")
    _assert(not QueueStatus.PROCESSING.is_idle(), "PROCESSING not idle")

    _assert(QueueStatus.WAITING.is_busy(),    "WAITING is busy")
    _assert(QueueStatus.PROCESSING.is_busy(), "PROCESSING is busy")
    _assert(not QueueStatus.EMPTY.is_busy(),  "EMPTY not busy")
    _assert(not QueueStatus.COMPLETE.is_busy(), "COMPLETE not busy")

    _assert(QueueStatus.WAITING.has_pending(),    "WAITING has pending")
    _assert(QueueStatus.PROCESSING.has_pending(), "PROCESSING has pending")
    _assert(not QueueStatus.EMPTY.has_pending(),  "EMPTY no pending")
    _assert(not QueueStatus.COMPLETE.has_pending(), "COMPLETE no pending")


# ===========================================================================
# ── SPRINT 003 — QueueSnapshot ─────────────────────────────────────────────
# ===========================================================================

def test_s003_queue_snapshot_construction() -> None:
    _section("[S003] QueueSnapshot — construction")
    snap = QueueSnapshot(
        queue_size=2,
        status=QueueStatus.WAITING,
        timestamp_ms=1000,
        pending_session_ids=("a", "b"),
        completed_count=3,
        total_submitted=5,
    )
    _assert(snap.queue_size        == 2,              "queue_size stored")
    _assert(snap.status            == QueueStatus.WAITING, "status stored")
    _assert(snap.timestamp_ms      == 1000,           "timestamp stored")
    _assert(snap.pending_count     == 2,              "pending_count")
    _assert(snap.completed_count   == 3,              "completed_count")
    _assert(snap.total_submitted   == 5,              "total_submitted")
    _assert(not snap.is_empty,                        "not empty")
    _assert(not snap.has_active,                      "no active")

    # with active
    snap2 = QueueSnapshot(
        queue_size=0, status=QueueStatus.PROCESSING,
        timestamp_ms=2000, active_session_id="sess-1",
    )
    _assert(snap2.has_active,                          "has active")
    _assert(snap2.active_session_id == "sess-1",       "active_session_id stored")
    _assert(snap2.is_empty,                            "is_empty (pending=0)")
    _assert(snap2.remaining == 1,                      "remaining = 1 (active only)")


def test_s003_queue_snapshot_immutability() -> None:
    _section("[S003] QueueSnapshot — immutability")
    snap = QueueSnapshot(queue_size=0, status=QueueStatus.EMPTY, timestamp_ms=0)
    try:
        snap.queue_size = 5  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")


def test_s003_queue_snapshot_validation() -> None:
    _section("[S003] QueueSnapshot — validation")
    # negative queue_size
    try:
        QueueSnapshot(queue_size=-1, status=QueueStatus.EMPTY, timestamp_ms=0)
        _assert(False, "negative queue_size")
    except ValueError:
        _assert(True, "negative queue_size raises ValueError")
    # wrong status type
    try:
        QueueSnapshot(queue_size=0, status="EMPTY", timestamp_ms=0)  # type: ignore
        _assert(False, "str status")
    except TypeError:
        _assert(True, "str status raises TypeError")
    # negative completed_count
    try:
        QueueSnapshot(queue_size=0, status=QueueStatus.EMPTY, timestamp_ms=0, completed_count=-1)
        _assert(False, "negative completed_count")
    except ValueError:
        _assert(True, "negative completed_count raises ValueError")


def test_s003_queue_snapshot_repr() -> None:
    _section("[S003] QueueSnapshot — repr")
    snap = QueueSnapshot(queue_size=3, status=QueueStatus.WAITING, timestamp_ms=0)
    r = repr(snap)
    _assert("QueueSnapshot" in r, "repr has class name")
    _assert("WAITING"       in r, "repr has status")
    _assert("3"             in r, "repr has size")


def test_s003_queue_snapshot_remaining() -> None:
    _section("[S003] QueueSnapshot — remaining property")
    snap_both = QueueSnapshot(
        queue_size=2, status=QueueStatus.PROCESSING,
        timestamp_ms=0, active_session_id="x",
        pending_session_ids=("a", "b"),
    )
    _assert(snap_both.remaining == 3, "active(1) + pending(2) = 3")

    snap_none = QueueSnapshot(queue_size=0, status=QueueStatus.COMPLETE, timestamp_ms=0)
    _assert(snap_none.remaining == 0, "no remaining when complete")


# ===========================================================================
# ── SPRINT 003 — EngineeringQueue ──────────────────────────────────────────
# ===========================================================================

def test_s003_queue_initial_state() -> None:
    _section("[S003] EngineeringQueue — initial state")
    q = EngineeringQueue()
    _assert(q.empty(),                    "starts empty")
    _assert(q.size() == 0,                "size 0")
    _assert(not q.has_active,             "no active")
    _assert(q.active_session is None,     "active_session None")
    _assert(q.completed_count == 0,       "completed 0")
    _assert(q.total_submitted == 0,       "submitted 0")
    _assert(q.status() == QueueStatus.EMPTY, "status EMPTY")
    _assert(q.peek() is None,             "peek returns None")
    _assert(q.dequeue() is None,          "dequeue returns None when empty")


def test_s003_queue_enqueue() -> None:
    _section("[S003] EngineeringQueue — enqueue")
    q   = EngineeringQueue()
    req = EngineeringRequest(request="Task A")
    s   = EngineeringSession.create(req)
    pos = q.enqueue(s)

    _assert(pos == 1,                "position 1")
    _assert(q.size() == 1,           "size 1")
    _assert(not q.empty(),           "not empty")
    _assert(q.total_submitted == 1,  "submitted 1")
    _assert(q.status() == QueueStatus.WAITING, "status WAITING")
    _assert(q.position_of(s.session_id) == 1,  "position_of correct")

    # second
    s2   = EngineeringSession.create(EngineeringRequest(request="Task B"))
    pos2 = q.enqueue(s2)
    _assert(pos2 == 2,   "second position 2")
    _assert(q.size() == 2, "size 2")


def test_s003_queue_enqueue_type_safety() -> None:
    _section("[S003] EngineeringQueue — enqueue type safety")
    q = EngineeringQueue()
    try:
        q.enqueue("not a session")  # type: ignore
        _assert(False, "str should raise TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")
    try:
        q.enqueue(None)  # type: ignore
        _assert(False, "None should raise TypeError")
    except TypeError:
        _assert(True, "None raises TypeError")


def test_s003_queue_enqueue_duplicate() -> None:
    _section("[S003] EngineeringQueue — duplicate session_id rejected")
    q = EngineeringQueue()
    s = EngineeringSession.create(EngineeringRequest(request="Once"))
    q.enqueue(s)
    try:
        q.enqueue(s)
        _assert(False, "duplicate should raise ValueError")
    except ValueError:
        _assert(True, "duplicate raises ValueError")


def test_s003_queue_dequeue_fifo() -> None:
    _section("[S003] EngineeringQueue — FIFO dequeue order")
    q  = EngineeringQueue()
    s1 = EngineeringSession.create(EngineeringRequest(request="First"))
    s2 = EngineeringSession.create(EngineeringRequest(request="Second"))
    s3 = EngineeringSession.create(EngineeringRequest(request="Third"))
    q.enqueue(s1)
    q.enqueue(s2)
    q.enqueue(s3)

    d1 = q.dequeue()
    _assert(d1.session_id == s1.session_id, "first dequeued is s1")
    _assert(q.has_active,                   "has active after dequeue")
    _assert(q.active_session.session_id == s1.session_id, "active is s1")
    _assert(q.status() == QueueStatus.PROCESSING, "status PROCESSING")
    _assert(q.size() == 2,                  "2 remaining in queue")

    q.mark_active_complete()
    d2 = q.dequeue()
    _assert(d2.session_id == s2.session_id, "second dequeued is s2")

    q.mark_active_complete()
    d3 = q.dequeue()
    _assert(d3.session_id == s3.session_id, "third dequeued is s3")


def test_s003_queue_dequeue_blocks_when_active() -> None:
    _section("[S003] EngineeringQueue — dequeue raises when active")
    q = EngineeringQueue()
    q.enqueue(EngineeringSession.create(EngineeringRequest(request="A")))
    q.enqueue(EngineeringSession.create(EngineeringRequest(request="B")))
    q.dequeue()  # set active
    try:
        q.dequeue()  # should raise
        _assert(False, "dequeue while active should raise")
    except RuntimeError:
        _assert(True, "dequeue while active raises RuntimeError")


def test_s003_queue_peek() -> None:
    _section("[S003] EngineeringQueue — peek")
    q  = EngineeringQueue()
    s1 = EngineeringSession.create(EngineeringRequest(request="Peek A"))
    s2 = EngineeringSession.create(EngineeringRequest(request="Peek B"))
    q.enqueue(s1)
    q.enqueue(s2)

    p1 = q.peek()
    p2 = q.peek()
    _assert(p1.session_id == s1.session_id, "peek returns first")
    _assert(p2.session_id == s1.session_id, "peek is non-destructive")
    _assert(q.size() == 2,                  "size unchanged after peek")


def test_s003_queue_remove() -> None:
    _section("[S003] EngineeringQueue — remove")
    q  = EngineeringQueue()
    s1 = EngineeringSession.create(EngineeringRequest(request="Remove A"))
    s2 = EngineeringSession.create(EngineeringRequest(request="Remove B"))
    s3 = EngineeringSession.create(EngineeringRequest(request="Remove C"))
    q.enqueue(s1)
    q.enqueue(s2)
    q.enqueue(s3)

    removed = q.remove(s2.session_id)
    _assert(removed,           "remove returns True")
    _assert(q.size() == 2,     "size reduced")
    ids = q.pending_session_ids()
    _assert(s2.session_id not in ids, "removed session not in pending")
    _assert(s1.session_id in ids,     "s1 still in pending")
    _assert(s3.session_id in ids,     "s3 still in pending")

    # remove non-existent
    not_removed = q.remove("nonexistent-id")
    _assert(not not_removed, "remove returns False for unknown id")


def test_s003_queue_clear() -> None:
    _section("[S003] EngineeringQueue — clear")
    q = EngineeringQueue()
    for i in range(5):
        q.enqueue(EngineeringSession.create(EngineeringRequest(request=f"Task {i}")))
    count = q.clear()
    _assert(count == 5,    "cleared 5")
    _assert(q.empty(),     "queue empty after clear")
    _assert(q.size() == 0, "size 0")


def test_s003_queue_mark_active_complete() -> None:
    _section("[S003] EngineeringQueue — mark_active_complete")
    q = EngineeringQueue()
    s = EngineeringSession.create(EngineeringRequest(request="Complete me"))
    q.enqueue(s)
    q.dequeue()

    _assert(q.has_active,           "active before complete")
    completed = q.mark_active_complete()
    _assert(completed.session_id == s.session_id, "correct session completed")
    _assert(not q.has_active,       "no active after complete")
    _assert(q.completed_count == 1, "completed count 1")
    _assert(q.status() == QueueStatus.COMPLETE, "status COMPLETE")

    # calling on None active is safe
    result = q.mark_active_complete()
    _assert(result is None,         "None when no active")


def test_s003_queue_statistics() -> None:
    _section("[S003] EngineeringQueue — statistics")
    q = EngineeringQueue()
    stats = q.statistics()
    _assert(isinstance(stats, dict),      "returns dict")
    _assert(stats["total_submitted"] == 0, "submitted 0")
    _assert(stats["pending"]         == 0, "pending 0")
    _assert(stats["active"]          == 0, "active 0")
    _assert(stats["completed"]       == 0, "completed 0")
    _assert(stats["remaining"]       == 0, "remaining 0")

    s = EngineeringSession.create(EngineeringRequest(request="Stat test"))
    q.enqueue(s)
    q.dequeue()
    stats2 = q.statistics()
    _assert(stats2["total_submitted"] == 1, "submitted 1")
    _assert(stats2["active"]          == 1, "active 1")
    _assert(stats2["remaining"]       == 1, "remaining 1")


def test_s003_queue_pending_session_ids() -> None:
    _section("[S003] EngineeringQueue — pending_session_ids")
    q  = EngineeringQueue()
    s1 = EngineeringSession.create(EngineeringRequest(request="A"))
    s2 = EngineeringSession.create(EngineeringRequest(request="B"))
    q.enqueue(s1)
    q.enqueue(s2)
    ids = q.pending_session_ids()
    _assert(isinstance(ids, list),              "returns list")
    _assert(len(ids) == 2,                      "2 pending")
    _assert(ids[0] == s1.session_id,            "s1 first")
    _assert(ids[1] == s2.session_id,            "s2 second")
    # mutation doesn't affect queue
    ids.append("fake")
    _assert(q.size() == 2,                      "queue unaffected")


def test_s003_queue_repr() -> None:
    _section("[S003] EngineeringQueue — repr")
    q = EngineeringQueue()
    r = repr(q)
    _assert("EngineeringQueue" in r, "repr has class name")
    _assert("EMPTY"            in r, "repr has status")


# ===========================================================================
# ── SPRINT 003 — Queue Snapshot from queue ─────────────────────────────────
# ===========================================================================

def test_s003_queue_snapshot_from_queue() -> None:
    _section("[S003] EngineeringQueue.snapshot() — from queue")
    q    = EngineeringQueue()
    snap = q.snapshot()
    _assert(snap.status   == QueueStatus.EMPTY, "empty snap status")
    _assert(snap.queue_size == 0,               "empty snap size")
    _assert(not snap.has_active,                "empty snap no active")

    s1 = EngineeringSession.create(EngineeringRequest(request="Snap A"))
    s2 = EngineeringSession.create(EngineeringRequest(request="Snap B"))
    q.enqueue(s1)
    q.enqueue(s2)
    snap2 = q.snapshot()
    _assert(snap2.status == QueueStatus.WAITING, "WAITING snap")
    _assert(snap2.queue_size == 2,               "size 2")
    _assert(snap2.total_submitted == 2,          "submitted 2")

    q.dequeue()
    snap3 = q.snapshot()
    _assert(snap3.status == QueueStatus.PROCESSING,          "PROCESSING snap")
    _assert(snap3.active_session_id == s1.session_id,        "active in snap")
    _assert(s2.session_id in snap3.pending_session_ids,      "s2 pending in snap")


def test_s003_queue_snapshot_independence() -> None:
    _section("[S003] QueueSnapshot — independence from queue")
    q  = EngineeringQueue()
    s1 = EngineeringSession.create(EngineeringRequest(request="Before"))
    q.enqueue(s1)
    snap = q.snapshot()
    _assert(snap.queue_size == 1, "snap size 1 before mutation")

    # mutate the queue
    s2 = EngineeringSession.create(EngineeringRequest(request="After"))
    q.enqueue(s2)

    # snapshot is unaffected
    _assert(snap.queue_size == 1, "snap size still 1 after queue mutation")
    _assert(q.size() == 2,        "queue size is 2")


# ===========================================================================
# ── SPRINT 003 — Coordinator submit / process_next / process_all ───────────
# ===========================================================================

def test_s003_coordinator_submit() -> None:
    _section("[S003] Coordinator.submit()")
    c   = _make_coordinator()
    pos = c.submit(_req("Submit A"))
    _assert(pos == 1, "first submission is position 1")

    pos2 = c.submit(_req("Submit B"))
    _assert(pos2 == 2, "second submission is position 2")

    stats = c.queue_statistics()
    _assert(stats["pending"] == 2, "2 pending after 2 submits")
    _assert(stats["total_submitted"] == 2, "total_submitted 2")


def test_s003_coordinator_submit_type_safety() -> None:
    _section("[S003] Coordinator.submit() — type safety")
    c = _make_coordinator()
    try:
        c.submit("not a request")  # type: ignore
        _assert(False, "str raises TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")


def test_s003_coordinator_process_next() -> None:
    _section("[S003] Coordinator.process_next()")
    c = _make_coordinator()
    c.submit(_req("Process me"))
    result = c.process_next()

    _assert(result is not None,                         "result returned")
    _assert(result.status == EngineeringStatus.COMPLETE, "COMPLETE")
    _assert(result.succeeded,                            "succeeded")
    _assert(result.has_queue_snapshot,                   "queue_snapshot attached")
    _assert(result.queue_position == 1,                  "queue_position 1")


def test_s003_coordinator_process_next_empty() -> None:
    _section("[S003] Coordinator.process_next() — empty queue")
    c      = _make_coordinator()
    result = c.process_next()
    _assert(result is None, "None when queue empty")


def test_s003_coordinator_process_all_fifo() -> None:
    _section("[S003] Coordinator.process_all() — FIFO order")
    c = _make_coordinator()
    for i in range(5):
        c.submit(_req(f"Task {i}"))

    results = c.process_all()
    _assert(len(results) == 5,             "5 results")
    _assert(all(r.status == EngineeringStatus.COMPLETE for r in results), "all COMPLETE")
    _assert(results[0].queue_position == 1, "first result position 1")
    _assert(results[4].queue_position == 5, "last result position 5")
    # FIFO: plan text reflects original request
    for i, r in enumerate(results):
        _assert(f"Task {i}" in r.plan, f"Task {i} in plan")


def test_s003_coordinator_process_all_empty() -> None:
    _section("[S003] Coordinator.process_all() — empty queue")
    c       = _make_coordinator()
    results = c.process_all()
    _assert(results == [], "empty list when queue empty")


def test_s003_coordinator_queue_stats() -> None:
    _section("[S003] Coordinator — queue statistics across lifecycle")
    c = _make_coordinator()

    stats0 = c.queue_statistics()
    _assert(stats0["total_submitted"] == 0, "submitted 0 initially")

    c.submit(_req("A"))
    c.submit(_req("B"))
    c.submit(_req("C"))

    stats1 = c.queue_statistics()
    _assert(stats1["pending"] == 3,          "3 pending")
    _assert(stats1["total_submitted"] == 3,  "submitted 3")

    c.process_next()
    stats2 = c.queue_statistics()
    _assert(stats2["pending"]   == 2, "2 pending after 1 processed")
    _assert(stats2["completed"] == 1, "1 completed")

    c.process_all()
    stats3 = c.queue_statistics()
    _assert(stats3["pending"]   == 0, "0 pending when all done")
    _assert(stats3["completed"] == 3, "3 completed")


def test_s003_coordinator_queue_snapshot() -> None:
    _section("[S003] Coordinator.queue_snapshot()")
    c    = _make_coordinator()
    snap = c.queue_snapshot()
    _assert(isinstance(snap, QueueSnapshot),    "returns QueueSnapshot")
    _assert(snap.status == QueueStatus.EMPTY,   "EMPTY initially")

    c.submit(_req("Snap"))
    snap2 = c.queue_snapshot()
    _assert(snap2.status == QueueStatus.WAITING, "WAITING after submit")
    _assert(snap2.queue_size == 1,               "size 1")

    c.process_next()
    snap3 = c.queue_snapshot()
    _assert(snap3.status == QueueStatus.COMPLETE, "COMPLETE after process")


def test_s003_result_queue_fields() -> None:
    _section("[S003] EngineeringResult — queue fields")
    # coordinate() doesn't set queue_position (backwards compatible)
    c   = _make_coordinator()
    r1  = c.coordinate(_req("Direct"))
    _assert(not r1.has_queue_position, "coordinate() has no queue_position")
    _assert(r1.has_queue_snapshot,     "coordinate() still attaches snapshot")

    # submit/process sets queue_position
    c.submit(_req("Queued"))
    r2 = c.process_next()
    _assert(r2.has_queue_position,      "process_next() sets queue_position")
    _assert(r2.queue_position == 1,     "queue_position is 1")
    _assert(r2.has_queue_snapshot,      "queue_snapshot attached")


def test_s003_coordinator_describe_includes_queue() -> None:
    _section("[S003] Coordinator.describe() — queue info")
    c = _make_coordinator()
    d = c.describe()
    _assert("queue" in d, "queue key in describe()")
    _assert("018.003" in d["version"], "version is Sprint 003")


def test_s003_backward_compat_coordinate() -> None:
    _section("[S003] Backwards compatibility — coordinate() unchanged")
    c = _make_coordinator(debugger=_StubDebugger())
    r = c.coordinate(_req("Backwards compat"))
    _assert(r.status    == EngineeringStatus.COMPLETE, "COMPLETE")
    _assert(r.succeeded,                               "succeeded")
    _assert(r.plan is not None,                        "plan")
    _assert(r.has_session,                             "session attached")
    _assert(r.has_timeline,                            "timeline attached")
    # Sprint 003 snapshot always attached (even for direct calls)
    _assert(r.has_queue_snapshot,                      "snapshot attached")


def test_s003_queue_and_direct_interleaved() -> None:
    _section("[S003] Queue and direct coordinate() can interleave")
    c = _make_coordinator()
    r_direct = c.coordinate(_req("Direct call"))
    _assert(r_direct.succeeded, "direct call succeeds")

    c.submit(_req("Queued call"))
    r_queued = c.process_next()
    _assert(r_queued.succeeded, "queued call succeeds")

    # Queue should be empty and complete
    snap = c.queue_snapshot()
    _assert(snap.status == QueueStatus.COMPLETE, "queue COMPLETE after processing")


# ===========================================================================
# ── SPRINT 003 — Public API surface ────────────────────────────────────────
# ===========================================================================

def test_s003_public_api_surface() -> None:
    _section("[S003] Public API surface — __init__ exports")
    import core.engineering.coordinator as pkg

    expected = [
        # Sprint 001
        "EngineeringCoordinator", "EngineeringRequest", "EngineeringResult",
        "EngineeringStatus", "CoordinatorConfig", "CoordinatorEvent",
        # Sprint 002
        "EngineeringStage", "EngineeringSession", "CoordinatorEventLog", "SessionEvent",
        # Sprint 003
        "EngineeringQueue", "QueueStatus", "QueueSnapshot",
    ]
    for name in expected:
        _assert(hasattr(pkg, name), f"{name} exported")
    _assert(len(pkg.__all__) == 13, "__all__ has 13 entries")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 003 — Engineering Coordinator Tests")
    print("=" * 60)

    # Sprint 001 regression
    test_s001_status()
    test_s001_request()
    test_s001_result()
    test_s001_coordinator_config()
    test_s001_pipeline_pass()
    test_s001_pipeline_guardrails_block()
    test_s001_pipeline_validation_fail()
    test_s001_exception_handling()
    test_s001_type_safety()

    # Sprint 002 regression
    test_s002_stage_enum()
    test_s002_session_event()
    test_s002_event_log()
    test_s002_session_lifecycle()
    test_s002_session_replay()
    test_s002_result_sprint002_fields()

    # Sprint 003
    test_s003_queue_status_values()
    test_s003_queue_status_properties()
    test_s003_queue_snapshot_construction()
    test_s003_queue_snapshot_immutability()
    test_s003_queue_snapshot_validation()
    test_s003_queue_snapshot_repr()
    test_s003_queue_snapshot_remaining()
    test_s003_queue_initial_state()
    test_s003_queue_enqueue()
    test_s003_queue_enqueue_type_safety()
    test_s003_queue_enqueue_duplicate()
    test_s003_queue_dequeue_fifo()
    test_s003_queue_dequeue_blocks_when_active()
    test_s003_queue_peek()
    test_s003_queue_remove()
    test_s003_queue_clear()
    test_s003_queue_mark_active_complete()
    test_s003_queue_statistics()
    test_s003_queue_pending_session_ids()
    test_s003_queue_repr()
    test_s003_queue_snapshot_from_queue()
    test_s003_queue_snapshot_independence()
    test_s003_coordinator_submit()
    test_s003_coordinator_submit_type_safety()
    test_s003_coordinator_process_next()
    test_s003_coordinator_process_next_empty()
    test_s003_coordinator_process_all_fifo()
    test_s003_coordinator_process_all_empty()
    test_s003_coordinator_queue_stats()
    test_s003_coordinator_queue_snapshot()
    test_s003_result_queue_fields()
    test_s003_coordinator_describe_includes_queue()
    test_s003_backward_compat_coordinate()
    test_s003_queue_and_direct_interleaved()
    test_s003_public_api_surface()

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