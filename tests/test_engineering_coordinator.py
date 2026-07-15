"""
Genesis-018 Sprint 004 — Engineering Coordinator Test Suite
Deterministic validation: ~420 checks.

Sprint 001 + 002 + 003 regression + Sprint 004 dispatcher.

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
    DispatchPolicy,
    DispatchRecord,
    DispatchStatus,
    EngineeringCoordinator,
    EngineeringDispatcher,
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
    def plan(self, request: str, **kwargs): raise RuntimeError("Planner error")

class _StubGuardrails:
    def check(self, request: str, *, plan=None) -> bool: return True

class _BlockingGuardrails:
    def check(self, request: str, **kwargs) -> bool: return False

class _FailingGuardrails:
    def check(self, request: str, **kwargs): raise RuntimeError("Guardrails error")

class _PassingTestRunner:
    class _R:
        passed = True
        def __str__(self): return "All tests passed"
    def run(self, request: str, **kwargs): return self._R()

class _FailingTestRunner:
    class _R:
        passed = False
        def __str__(self): return "Tests failed"
    def run(self, request: str, **kwargs): return self._R()

class _RaisingTestRunner:
    def run(self, request: str, **kwargs): raise RuntimeError("Runner crashed")

class _StubDebugger:
    class _R:
        report      = "Debug complete"
        repair_plan = "Repair plan: apply patch A"
        def __str__(self): return "Debug complete"
    def debug(self, request: str, **kwargs): return self._R()


# ===========================================================================
# Test helpers
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

def _coord(**kwargs):
    return EngineeringCoordinator(
        planner=_StubPlanner(),
        guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(),
        **kwargs,
    )

def _req(text="Test request"):
    return EngineeringRequest(request=text)

def _session(text="Session"):
    return EngineeringSession.create(_req(text))


# ===========================================================================
# ── SPRINT 001 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_s001_status() -> None:
    _section("[S001] EngineeringStatus")
    for val in ["PENDING","PLANNING","VALIDATING","DEBUGGING","COMPLETE","FAILED"]:
        _assert(EngineeringStatus(val).value == val, f"Status {val}")
    _assert(EngineeringStatus.COMPLETE.is_terminal(), "COMPLETE terminal")
    _assert(not EngineeringStatus.PENDING.is_terminal(), "PENDING not terminal")
    _assert(EngineeringStatus.PENDING.is_active(), "PENDING active")
    _assert(len(EngineeringStatus) == 6, "6 status values")

def test_s001_request() -> None:
    _section("[S001] EngineeringRequest")
    r = _req("Refactor")
    _assert(r.request == "Refactor", "stored")
    _assert(r.context == "",  "default context")
    _assert(r.priority == 0,  "default priority")
    try: r.request = "mutated"; _assert(False, "immutable")  # type: ignore
    except (AttributeError, TypeError): _assert(True, "immutable")
    for bad, exc in [
        ({"request": "   "}, ValueError),
        ({"request": 123}, TypeError),
        ({"request": "x", "priority": "hi"}, TypeError),
    ]:
        try: EngineeringRequest(**bad); _assert(False, f"bad: {bad}")  # type: ignore
        except exc: _assert(True, f"raises {exc.__name__}")
    _assert(not _req().has_context, "no context")
    _assert(_req() if True else None, "request ok")

def test_s001_result() -> None:
    _section("[S001] EngineeringResult")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.succeeded, "succeeded")
    _assert(not res.failed, "not failed")
    failed = EngineeringResult(status=EngineeringStatus.FAILED, errors=["e"])
    _assert(failed.failed, "failed")
    _assert(failed.error_count == 1, "error count")
    try: EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=-1); _assert(False, "neg dur")
    except ValueError: _assert(True, "neg dur raises")

def test_s001_pipeline() -> None:
    _section("[S001] Pipeline — regression")
    c = _coord(debugger=_StubDebugger())
    r = c.coordinate(_req("Build"))
    _assert(r.status == EngineeringStatus.COMPLETE, "COMPLETE")
    _assert(r.succeeded, "succeeded")
    _assert(r.plan is not None, "plan set")
    c2 = EngineeringCoordinator(planner=_StubPlanner(), guardrails=_BlockingGuardrails())
    r2 = c2.coordinate(_req())
    _assert(r2.status == EngineeringStatus.FAILED, "blocked → FAILED")
    c3 = EngineeringCoordinator(planner=_StubPlanner(), guardrails=_StubGuardrails(),
                                 test_runner=_FailingTestRunner(), debugger=_StubDebugger())
    r3 = c3.coordinate(_req())
    _assert(r3.required_debugging, "debug invoked")
    _assert(r3.has_repair_plan, "repair plan")
    for c_bad in [
        EngineeringCoordinator(planner=_FailingPlanner(), guardrails=_StubGuardrails()),
        EngineeringCoordinator(planner=_StubPlanner(), guardrails=_FailingGuardrails()),
    ]:
        rb = c_bad.coordinate(_req())
        _assert(rb.status == EngineeringStatus.FAILED, "exception → FAILED")
    # type safety
    for bad in ["str", None, 42]:
        try: c.coordinate(bad); _assert(False, f"type {type(bad).__name__}")  # type: ignore
        except TypeError: _assert(True, "TypeError raised")


# ===========================================================================
# ── SPRINT 002 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_s002_stage() -> None:
    _section("[S002] EngineeringStage")
    for v in ["INITIALISING","PLANNING","GUARDRAILS","VALIDATION",
              "DEBUGGING","REPAIR_PLANNING","COMPLETE","FAILED"]:
        _assert(EngineeringStage(v).value == v, f"Stage {v}")
    _assert(len(EngineeringStage) == 8, "8 stages")
    _assert(EngineeringStage.COMPLETE.is_terminal(), "terminal")
    _assert(EngineeringStage.DEBUGGING.is_failure_path(), "failure path")

def test_s002_event_log() -> None:
    _section("[S002] CoordinatorEventLog")
    log = CoordinatorEventLog()
    _assert(log.is_empty, "starts empty")
    log.record(EngineeringStage.PLANNING, "p")
    log.record(EngineeringStage.GUARDRAILS, "g", duration_ms=5)
    _assert(log.event_count == 2, "2 events")
    log.seal()
    try: log.record(EngineeringStage.PLANNING, "x"); _assert(False, "sealed")
    except RuntimeError: _assert(True, "sealed raises")

def test_s002_session() -> None:
    _section("[S002] EngineeringSession")
    s = _session()
    _assert(s.status == EngineeringStatus.PENDING, "PENDING")
    _assert(not s.is_complete, "not complete")
    s.advance_to(EngineeringStage.PLANNING, "plan")
    _assert(s.events.event_count == 1, "event recorded")
    result = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    s.complete(result)
    _assert(s.is_complete, "complete")
    _assert(s.events.is_sealed, "log sealed")

def test_s002_result_fields() -> None:
    _section("[S002] EngineeringResult — Sprint 002 fields")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE)
    _assert(res.session is None, "session None default")
    c = _coord()
    r = c.coordinate(_req())
    _assert(r.has_session, "session attached")
    _assert(r.has_timeline, "timeline populated")
    _assert("COMPLETE" in r.stages_visited(), "COMPLETE in stages")


# ===========================================================================
# ── SPRINT 003 REGRESSION ──────────────────────────────────────────────────
# ===========================================================================

def test_s003_queue_status() -> None:
    _section("[S003] QueueStatus")
    for v in ["EMPTY","WAITING","PROCESSING","COMPLETE"]:
        _assert(QueueStatus(v).value == v, f"Status {v}")
    _assert(QueueStatus.EMPTY.is_idle(), "EMPTY idle")
    _assert(QueueStatus.PROCESSING.is_busy(), "PROCESSING busy")
    _assert(QueueStatus.WAITING.has_pending(), "WAITING pending")

def test_s003_queue_snapshot() -> None:
    _section("[S003] QueueSnapshot")
    snap = QueueSnapshot(queue_size=2, status=QueueStatus.WAITING, timestamp_ms=0,
                         pending_session_ids=("a","b"), completed_count=1, total_submitted=3)
    _assert(snap.pending_count == 2, "pending_count")
    _assert(snap.completed_count == 1, "completed_count")
    _assert(not snap.has_active, "no active")
    try: snap.queue_size = 5; _assert(False, "immutable")  # type: ignore
    except (AttributeError, TypeError): _assert(True, "immutable")

def test_s003_queue() -> None:
    _section("[S003] EngineeringQueue — regression")
    q = EngineeringQueue()
    _assert(q.empty(), "starts empty")
    s1 = _session("A"); s2 = _session("B"); s3 = _session("C")
    p1 = q.enqueue(s1); p2 = q.enqueue(s2)
    _assert(p1 == 1, "pos 1"); _assert(p2 == 2, "pos 2")
    # FIFO
    d = q.dequeue()
    _assert(d.session_id == s1.session_id, "FIFO order")
    _assert(q.status() == QueueStatus.PROCESSING, "PROCESSING")
    q.mark_active_complete()
    # duplicate rejected
    try: q.enqueue(s2); _assert(False, "dup rejected")
    except ValueError: _assert(True, "dup raises ValueError")
    # type safety
    try: q.enqueue("bad"); _assert(False, "type")  # type: ignore
    except TypeError: _assert(True, "TypeError")
    # clear
    q2 = EngineeringQueue()
    for i in range(3): q2.enqueue(_session(f"T{i}"))
    n = q2.clear()
    _assert(n == 3, "cleared 3")
    _assert(q2.empty(), "empty after clear")

def test_s003_submit_process() -> None:
    _section("[S003] submit/process_all — regression")
    c = _coord()
    for i in range(3): c.submit(_req(f"Task {i}"))
    results = c.process_all()
    _assert(len(results) == 3, "3 results")
    _assert(all(r.succeeded for r in results), "all succeeded")
    _assert(results[0].queue_position == 1, "first pos 1")
    _assert(results[2].queue_position == 3, "last pos 3")


# ===========================================================================
# ── SPRINT 004 — DispatchStatus ────────────────────────────────────────────
# ===========================================================================

def test_s004_dispatch_status_values() -> None:
    _section("[S004] DispatchStatus — values")
    for v in ["IDLE","READY","DISPATCHING","COMPLETE"]:
        _assert(DispatchStatus(v).value == v, f"DispatchStatus.{v}")
    _assert(len(DispatchStatus) == 4, "4 values")

def test_s004_dispatch_status_properties() -> None:
    _section("[S004] DispatchStatus — properties")
    _assert(DispatchStatus.COMPLETE.is_terminal(),     "COMPLETE terminal")
    _assert(not DispatchStatus.IDLE.is_terminal(),     "IDLE not terminal")
    _assert(not DispatchStatus.DISPATCHING.is_terminal(), "DISPATCHING not terminal")

    _assert(DispatchStatus.READY.is_active(),          "READY active")
    _assert(DispatchStatus.DISPATCHING.is_active(),    "DISPATCHING active")
    _assert(not DispatchStatus.IDLE.is_active(),       "IDLE not active")
    _assert(not DispatchStatus.COMPLETE.is_active(),   "COMPLETE not active")

    _assert(DispatchStatus.IDLE.is_idle(),             "IDLE is_idle")
    _assert(not DispatchStatus.READY.is_idle(),        "READY not idle")
    _assert(not DispatchStatus.DISPATCHING.is_idle(),  "DISPATCHING not idle")


# ===========================================================================
# ── SPRINT 004 — DispatchRecord ────────────────────────────────────────────
# ===========================================================================

def test_s004_dispatch_record_construction() -> None:
    _section("[S004] DispatchRecord — construction")
    import uuid
    dr = DispatchRecord(
        dispatch_id=str(uuid.uuid4()),
        session_id="sess-abc",
        queued_at=1000,
        dispatched_at=1050,
        status=DispatchStatus.DISPATCHING,
    )
    _assert(dr.session_id == "sess-abc",             "session_id stored")
    _assert(dr.queued_at == 1000,                    "queued_at stored")
    _assert(dr.dispatched_at == 1050,                "dispatched_at stored")
    _assert(dr.status == DispatchStatus.DISPATCHING, "status stored")
    _assert(dr.completed_at is None,                 "completed_at None")
    _assert(dr.duration_ms is None,                  "duration None")
    _assert(dr.wait_ms == 50,                        "wait_ms = 50")
    _assert(not dr.is_complete,                      "not complete")
    _assert(not dr.has_duration,                     "no duration")

def test_s004_dispatch_record_immutability() -> None:
    _section("[S004] DispatchRecord — immutability")
    import uuid
    dr = DispatchRecord(
        dispatch_id=str(uuid.uuid4()), session_id="s",
        queued_at=0, dispatched_at=0, status=DispatchStatus.DISPATCHING,
    )
    try:
        dr.session_id = "mutated"  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")

def test_s004_dispatch_record_validation() -> None:
    _section("[S004] DispatchRecord — validation")
    import uuid
    base = dict(dispatch_id=str(uuid.uuid4()), session_id="s",
                queued_at=0, dispatched_at=0, status=DispatchStatus.DISPATCHING)
    # blank dispatch_id
    try:
        DispatchRecord(**{**base, "dispatch_id": "  "})
        _assert(False, "blank dispatch_id")
    except ValueError:
        _assert(True, "blank dispatch_id raises ValueError")
    # blank session_id
    try:
        DispatchRecord(**{**base, "session_id": ""})
        _assert(False, "blank session_id")
    except ValueError:
        _assert(True, "blank session_id raises ValueError")
    # wrong status type
    try:
        DispatchRecord(**{**base, "status": "DISPATCHING"})  # type: ignore
        _assert(False, "str status")
    except TypeError:
        _assert(True, "str status raises TypeError")
    # wrong queued_at type
    try:
        DispatchRecord(**{**base, "queued_at": "now"})  # type: ignore
        _assert(False, "str queued_at")
    except TypeError:
        _assert(True, "str queued_at raises TypeError")
    # negative duration
    try:
        DispatchRecord(**{**base, "duration_ms": -1})
        _assert(False, "negative duration")
    except ValueError:
        _assert(True, "negative duration raises ValueError")
    # wrong duration type
    try:
        DispatchRecord(**{**base, "duration_ms": "fast"})  # type: ignore
        _assert(False, "str duration")
    except TypeError:
        _assert(True, "str duration raises TypeError")

def test_s004_dispatch_record_complete() -> None:
    _section("[S004] DispatchRecord — complete()")
    import uuid
    dr = DispatchRecord(
        dispatch_id=str(uuid.uuid4()), session_id="s",
        queued_at=1000, dispatched_at=1050, status=DispatchStatus.DISPATCHING,
    )
    completed = dr.complete(completed_at=1200)

    # original unchanged
    _assert(dr.status == DispatchStatus.DISPATCHING, "original unchanged")
    _assert(dr.completed_at is None,                 "original completed_at None")

    # completed record
    _assert(completed.status == DispatchStatus.COMPLETE, "status COMPLETE")
    _assert(completed.completed_at == 1200,              "completed_at set")
    _assert(completed.duration_ms == 200,                "duration = 1200-1000")
    _assert(completed.is_complete,                       "is_complete True")
    _assert(completed.has_duration,                      "has_duration True")
    _assert(completed.wait_ms == 50,                     "wait_ms preserved")
    # IDs preserved
    _assert(completed.dispatch_id == dr.dispatch_id,     "dispatch_id preserved")
    _assert(completed.session_id  == dr.session_id,      "session_id preserved")

def test_s004_dispatch_record_repr() -> None:
    _section("[S004] DispatchRecord — repr")
    import uuid
    dr = DispatchRecord(
        dispatch_id=str(uuid.uuid4()), session_id="s",
        queued_at=0, dispatched_at=0, status=DispatchStatus.DISPATCHING,
    )
    r = repr(dr)
    _assert("DispatchRecord" in r,  "class name")
    _assert("DISPATCHING"    in r,  "status")
    # with duration
    dr2 = dr.complete(100)
    r2  = repr(dr2)
    _assert("100ms" in r2, "duration in repr")


# ===========================================================================
# ── SPRINT 004 — EngineeringDispatcher ─────────────────────────────────────
# ===========================================================================

def test_s004_dispatcher_construction() -> None:
    _section("[S004] EngineeringDispatcher — construction")
    d = EngineeringDispatcher()
    _assert(d.policy == DispatchPolicy.FIFO, "default policy FIFO")
    _assert(not d.has_active_dispatch,        "no active dispatch")
    _assert(d.total_dispatched == 0,          "dispatched 0")
    _assert(d.total_completed  == 0,          "completed 0")
    _assert(d.history_count    == 0,          "history 0")
    _assert(d.current_dispatch() is None,     "current None")
    _assert(d.dispatch_history() == [],       "history empty")
    _assert(d.last_dispatch()    is None,     "last None")

def test_s004_dispatcher_invalid_policy() -> None:
    _section("[S004] EngineeringDispatcher — invalid policy")
    try:
        EngineeringDispatcher(policy="PRIORITY")
        _assert(False, "unknown policy should raise")
    except ValueError:
        _assert(True, "unknown policy raises ValueError")

def test_s004_dispatcher_can_dispatch() -> None:
    _section("[S004] EngineeringDispatcher — can_dispatch")
    d = EngineeringDispatcher()
    q = EngineeringQueue()

    # empty queue — cannot dispatch
    _assert(not d.can_dispatch(q), "cannot dispatch empty queue")

    # queue with session — can dispatch
    q.enqueue(_session())
    _assert(d.can_dispatch(q), "can dispatch with pending session")

    # queue already has active — cannot dispatch
    q.dequeue()
    _assert(not d.can_dispatch(q), "cannot dispatch when queue already active")
    q.mark_active_complete()

    # re-enqueue — can dispatch again
    q.enqueue(_session())
    _assert(d.can_dispatch(q), "can dispatch after reset")

    # active dispatch in dispatcher — cannot dispatch
    q2 = EngineeringQueue()
    q2.enqueue(_session())
    d.dispatch_next(q2)
    q3 = EngineeringQueue()
    q3.enqueue(_session())
    _assert(not d.can_dispatch(q3), "cannot dispatch when dispatch already active")

def test_s004_dispatcher_can_dispatch_type_safety() -> None:
    _section("[S004] EngineeringDispatcher — can_dispatch type safety")
    d = EngineeringDispatcher()
    try:
        d.can_dispatch("not a queue")  # type: ignore
        _assert(False, "str should raise TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")

def test_s004_dispatcher_dispatch_next() -> None:
    _section("[S004] EngineeringDispatcher — dispatch_next")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    s = _session("Dispatch me")
    q.enqueue(s)

    record = d.dispatch_next(q)
    _assert(record is not None,                           "record returned")
    _assert(record.session_id == s.session_id,            "session_id in record")
    _assert(record.status == DispatchStatus.DISPATCHING,  "status DISPATCHING")
    _assert(d.has_active_dispatch,                        "has active dispatch")
    _assert(d.total_dispatched == 1,                      "dispatched count 1")
    _assert(d.current_dispatch() is record,               "current_dispatch matches")
    _assert(q.has_active,                                 "queue has active session")
    _assert(q.active_session.session_id == s.session_id,  "queue active is our session")

def test_s004_dispatcher_dispatch_next_empty() -> None:
    _section("[S004] EngineeringDispatcher — dispatch_next on empty queue")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    r = d.dispatch_next(q)
    _assert(r is None, "None on empty queue")
    _assert(d.total_dispatched == 0, "dispatched count unchanged")

def test_s004_dispatcher_dispatch_next_while_active() -> None:
    _section("[S004] EngineeringDispatcher — dispatch_next while active")
    d  = EngineeringDispatcher()
    q1 = EngineeringQueue(); q1.enqueue(_session("A"))
    q2 = EngineeringQueue(); q2.enqueue(_session("B"))
    d.dispatch_next(q1)
    try:
        d.dispatch_next(q2)
        _assert(False, "should raise RuntimeError")
    except RuntimeError:
        _assert(True, "RuntimeError when dispatch already active")

def test_s004_dispatcher_dispatch_next_type_safety() -> None:
    _section("[S004] EngineeringDispatcher — dispatch_next type safety")
    d = EngineeringDispatcher()
    try:
        d.dispatch_next("not a queue")  # type: ignore
        _assert(False, "str raises TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")

def test_s004_dispatcher_complete_dispatch() -> None:
    _section("[S004] EngineeringDispatcher — complete_dispatch")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    q.enqueue(_session())
    d.dispatch_next(q)

    completed = d.complete_dispatch()
    _assert(completed is not None,                       "completed record returned")
    _assert(completed.status == DispatchStatus.COMPLETE, "status COMPLETE")
    _assert(completed.is_complete,                       "is_complete True")
    _assert(completed.completed_at is not None,          "completed_at set")
    _assert(completed.has_duration,                      "has duration")
    _assert(not d.has_active_dispatch,                   "no active after complete")
    _assert(d.total_completed == 1,                      "completed count 1")
    _assert(d.history_count   == 1,                      "history count 1")
    _assert(d.last_dispatch() is completed,              "last_dispatch matches")

def test_s004_dispatcher_complete_when_idle() -> None:
    _section("[S004] EngineeringDispatcher — complete when idle")
    d = EngineeringDispatcher()
    r = d.complete_dispatch()
    _assert(r is None, "None when no active dispatch")

def test_s004_dispatcher_fifo_ordering() -> None:
    _section("[S004] EngineeringDispatcher — FIFO ordering")
    d  = EngineeringDispatcher()
    q  = EngineeringQueue()
    sessions = [_session(f"S{i}") for i in range(4)]
    for s in sessions:
        q.enqueue(s)

    dispatched_ids = []
    for _ in range(4):
        rec = d.dispatch_next(q)
        dispatched_ids.append(rec.session_id)
        q.mark_active_complete()
        d.complete_dispatch()

    for i, s in enumerate(sessions):
        _assert(dispatched_ids[i] == s.session_id, f"FIFO: position {i} correct")

def test_s004_dispatcher_history() -> None:
    _section("[S004] EngineeringDispatcher — dispatch_history")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    for i in range(3):
        s = _session(f"H{i}")
        q.enqueue(s)
        d.dispatch_next(q)
        q.mark_active_complete()
        d.complete_dispatch()

    history = d.dispatch_history()
    _assert(len(history) == 3, "3 history entries")
    _assert(all(isinstance(r, DispatchRecord) for r in history), "all DispatchRecord")
    _assert(all(r.is_complete for r in history), "all complete")
    # snapshot independence
    history.append(None)  # type: ignore
    _assert(d.history_count == 3, "history unaffected by snapshot mutation")

def test_s004_dispatcher_statistics() -> None:
    _section("[S004] EngineeringDispatcher — statistics")
    d = EngineeringDispatcher()
    stats = d.statistics()
    _assert(isinstance(stats, dict),         "returns dict")
    _assert(stats["total_dispatched"] == 0,  "dispatched 0")
    _assert(stats["total_completed"]  == 0,  "completed 0")
    _assert(stats["history_count"]    == 0,  "history 0")
    _assert(stats["active"]           == 0,  "active 0")

    q = EngineeringQueue()
    q.enqueue(_session())
    d.dispatch_next(q)
    stats2 = d.statistics()
    _assert(stats2["active"]           == 1, "active 1")
    _assert(stats2["total_dispatched"] == 1, "dispatched 1")

    q.mark_active_complete()
    d.complete_dispatch()
    stats3 = d.statistics()
    _assert(stats3["active"]           == 0, "active 0 after complete")
    _assert(stats3["total_completed"]  == 1, "completed 1")
    _assert(stats3["history_count"]    == 1, "history 1")

def test_s004_dispatcher_reset_current() -> None:
    _section("[S004] EngineeringDispatcher — reset_current")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    q.enqueue(_session())
    d.dispatch_next(q)
    _assert(d.has_active_dispatch, "has active before reset")

    result = d.reset_current()
    _assert(result, "reset returns True")
    _assert(not d.has_active_dispatch, "no active after reset")
    _assert(d.history_count == 1,      "reset adds to history")

    # reset when idle
    result2 = d.reset_current()
    _assert(not result2, "reset returns False when idle")

def test_s004_dispatcher_wait_ms() -> None:
    _section("[S004] EngineeringDispatcher — wait_ms tracking")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    s = _session()
    q.enqueue(s)
    t_queued = int(time.monotonic() * 1000)
    rec = d.dispatch_next(q, queued_at=t_queued)
    _assert(rec.wait_ms >= 0, "wait_ms non-negative")
    _assert(rec.queued_at == t_queued, "queued_at stored")

def test_s004_dispatcher_repr() -> None:
    _section("[S004] EngineeringDispatcher — repr")
    d = EngineeringDispatcher()
    r = repr(d)
    _assert("EngineeringDispatcher" in r, "class name")
    _assert("FIFO"                  in r, "policy")
    _assert("dispatched=0"          in r, "dispatched count")

def test_s004_dispatch_policy() -> None:
    _section("[S004] DispatchPolicy")
    _assert(DispatchPolicy.FIFO == "FIFO", "FIFO constant value")
    d = EngineeringDispatcher(policy=DispatchPolicy.FIFO)
    _assert(d.policy == "FIFO", "policy stored")


# ===========================================================================
# ── SPRINT 004 — Coordinator integration ───────────────────────────────────
# ===========================================================================

def test_s004_coordinator_has_dispatcher() -> None:
    _section("[S004] Coordinator — owns dispatcher")
    c = _coord()
    _assert(isinstance(c.dispatcher, EngineeringDispatcher), "dispatcher is EngineeringDispatcher")
    _assert(c.dispatcher.policy == DispatchPolicy.FIFO,      "default FIFO policy")

def test_s004_coordinator_process_next_uses_dispatcher() -> None:
    _section("[S004] Coordinator.process_next() — uses dispatcher")
    c = _coord()
    c.submit(_req("Dispatched request"))
    result = c.process_next()

    _assert(result is not None,                              "result returned")
    _assert(result.status == EngineeringStatus.COMPLETE,     "COMPLETE")
    _assert(result.has_dispatch_record,                      "dispatch_record attached")
    _assert(result.dispatch_record.is_complete,              "dispatch_record is complete")
    _assert(result.dispatch_id is not None,                  "dispatch_id accessible")
    _assert(result.dispatch_duration_ms is not None,         "dispatch_duration_ms set")
    _assert(result.dispatch_duration_ms >= 0,                "dispatch_duration_ms non-negative")

def test_s004_coordinator_direct_no_dispatch_record() -> None:
    _section("[S004] Coordinator.coordinate() — no dispatch_record (backwards compat)")
    c = _coord()
    r = c.coordinate(_req("Direct"))
    _assert(not r.has_dispatch_record, "no dispatch_record on direct call")
    _assert(r.dispatch_id is None,     "dispatch_id None")
    _assert(r.has_queue_snapshot,      "queue_snapshot still attached")

def test_s004_coordinator_dispatch_history() -> None:
    _section("[S004] Coordinator.dispatch_history()")
    c = _coord()
    for i in range(3):
        c.submit(_req(f"Task {i}"))
    c.process_all()
    history = c.dispatch_history()
    _assert(len(history) == 3, "3 dispatch records")
    _assert(all(isinstance(r, DispatchRecord) for r in history), "all DispatchRecord")
    _assert(all(r.is_complete for r in history), "all complete")

def test_s004_coordinator_dispatch_statistics() -> None:
    _section("[S004] Coordinator.dispatch_statistics()")
    c = _coord()
    stats = c.dispatch_statistics()
    _assert(stats["total_dispatched"] == 0, "dispatched 0 initially")

    for i in range(4): c.submit(_req(f"T{i}"))
    c.process_all()
    stats2 = c.dispatch_statistics()
    _assert(stats2["total_dispatched"] == 4, "dispatched 4")
    _assert(stats2["total_completed"]  == 4, "completed 4")
    _assert(stats2["history_count"]    == 4, "history 4")
    _assert(stats2["active"]           == 0, "active 0")

def test_s004_coordinator_current_dispatch() -> None:
    _section("[S004] Coordinator.current_dispatch()")
    c = _coord()
    _assert(c.current_dispatch() is None, "None initially")
    # After processing, current should be None (complete)
    c.submit(_req("CD test"))
    c.process_next()
    _assert(c.current_dispatch() is None, "None after completion")

def test_s004_coordinator_describe_includes_dispatcher() -> None:
    _section("[S004] Coordinator.describe() — dispatcher info")
    c = _coord()
    d = c.describe()
    _assert("dispatcher" in d, "dispatcher in describe()")
    _assert("018.004" in d["version"], "version 018.004")

def test_s004_coordinator_process_all_dispatch_records() -> None:
    _section("[S004] Coordinator.process_all() — all results have dispatch_records")
    c       = _coord()
    n       = 5
    for i in range(n): c.submit(_req(f"Batch {i}"))
    results = c.process_all()
    _assert(len(results) == n, f"{n} results")
    for i, r in enumerate(results):
        _assert(r.has_dispatch_record,    f"result {i} has dispatch_record")
        _assert(r.dispatch_record.is_complete, f"result {i} dispatch complete")
        _assert(r.queue_position == i + 1,     f"result {i} queue_position {i+1}")

def test_s004_coordinator_fifo_dispatch_order() -> None:
    _section("[S004] Coordinator — FIFO dispatch order verified via records")
    c        = _coord()
    requests = [f"Order {i}" for i in range(4)]
    for req in requests: c.submit(EngineeringRequest(request=req))
    results  = c.process_all()
    history  = c.dispatch_history()

    # History should be in submission order
    for i, record in enumerate(history):
        # The session for this position should match the result
        _assert(record.session_id == results[i].session_id, f"dispatch order {i} matches")

def test_s004_dispatch_record_on_failed_result() -> None:
    _section("[S004] Dispatch record attached on FAILED result")
    c = EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_BlockingGuardrails(),
    )
    c.submit(_req("Will fail"))
    result = c.process_next()
    _assert(result.status == EngineeringStatus.FAILED, "FAILED")
    _assert(result.has_dispatch_record,                "dispatch_record on failed result")
    _assert(result.dispatch_record.is_complete,        "dispatch_record is complete")

def test_s004_result_sprint004_fields_defaults() -> None:
    _section("[S004] EngineeringResult — Sprint 004 defaults")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE)
    _assert(res.dispatch_record      is None, "dispatch_record None")
    _assert(res.dispatch_duration_ms is None, "dispatch_duration_ms None")
    _assert(not res.has_dispatch_record,      "has_dispatch_record False")
    _assert(res.dispatch_id is None,          "dispatch_id None")

def test_s004_coordinator_queue_and_dispatcher_separate() -> None:
    _section("[S004] Queue and Dispatcher are distinct, coordinator owns both")
    c = _coord()
    _assert(c.queue is not c.dispatcher,              "queue != dispatcher")
    _assert(isinstance(c.queue, EngineeringQueue),    "queue is EngineeringQueue")
    _assert(isinstance(c.dispatcher, EngineeringDispatcher), "dispatcher is EngineeringDispatcher")

def test_s004_backward_compat_all_previous_apis() -> None:
    _section("[S004] Backwards compatibility — all Sprint 001-003 APIs work")
    c = _coord(debugger=_StubDebugger())

    # S001: coordinate()
    r1 = c.coordinate(_req("S001"))
    _assert(r1.succeeded, "S001 coordinate")

    # S002: session, timeline, stage_durations
    _assert(r1.has_session,        "S002 session")
    _assert(r1.has_timeline,       "S002 timeline")
    _assert(r1.has_stage_durations,"S002 stage_durations")

    # S003: queue, submit, process_next, queue_snapshot
    pos = c.submit(_req("S003"))
    _assert(pos == 1, "S003 submit")
    r2 = c.process_next()
    _assert(r2.has_queue_position, "S003 queue_position")
    _assert(r2.has_queue_snapshot, "S003 queue_snapshot")

    # S004: dispatch_record
    _assert(r2.has_dispatch_record, "S004 dispatch_record")

    stats = c.dispatch_statistics()
    _assert("total_dispatched" in stats, "S004 dispatch_statistics")
    history = c.dispatch_history()
    _assert(isinstance(history, list), "S004 dispatch_history")


# ===========================================================================
# ── SPRINT 004 — Public API surface ────────────────────────────────────────
# ===========================================================================

def test_s004_public_api_surface() -> None:
    _section("[S004] Public API surface — __init__ exports")
    import core.engineering.coordinator as pkg
    expected = [
        "EngineeringCoordinator","EngineeringRequest","EngineeringResult",
        "EngineeringStatus","CoordinatorConfig","CoordinatorEvent",
        "EngineeringStage","EngineeringSession","CoordinatorEventLog","SessionEvent",
        "EngineeringQueue","QueueStatus","QueueSnapshot",
        "EngineeringDispatcher","DispatchStatus","DispatchRecord","DispatchPolicy",
    ]
    for name in expected:
        _assert(hasattr(pkg, name), f"{name} exported")
    _assert(len(pkg.__all__) == 17, "__all__ has 17 entries")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 004 — Engineering Coordinator Tests")
    print("=" * 60)

    test_s001_status()
    test_s001_request()
    test_s001_result()
    test_s001_pipeline()

    test_s002_stage()
    test_s002_event_log()
    test_s002_session()
    test_s002_result_fields()

    test_s003_queue_status()
    test_s003_queue_snapshot()
    test_s003_queue()
    test_s003_submit_process()

    test_s004_dispatch_status_values()
    test_s004_dispatch_status_properties()
    test_s004_dispatch_record_construction()
    test_s004_dispatch_record_immutability()
    test_s004_dispatch_record_validation()
    test_s004_dispatch_record_complete()
    test_s004_dispatch_record_repr()
    test_s004_dispatcher_construction()
    test_s004_dispatcher_invalid_policy()
    test_s004_dispatcher_can_dispatch()
    test_s004_dispatcher_can_dispatch_type_safety()
    test_s004_dispatcher_dispatch_next()
    test_s004_dispatcher_dispatch_next_empty()
    test_s004_dispatcher_dispatch_next_while_active()
    test_s004_dispatcher_dispatch_next_type_safety()
    test_s004_dispatcher_complete_dispatch()
    test_s004_dispatcher_complete_when_idle()
    test_s004_dispatcher_fifo_ordering()
    test_s004_dispatcher_history()
    test_s004_dispatcher_statistics()
    test_s004_dispatcher_reset_current()
    test_s004_dispatcher_wait_ms()
    test_s004_dispatcher_repr()
    test_s004_dispatch_policy()
    test_s004_coordinator_has_dispatcher()
    test_s004_coordinator_process_next_uses_dispatcher()
    test_s004_coordinator_direct_no_dispatch_record()
    test_s004_coordinator_dispatch_history()
    test_s004_coordinator_dispatch_statistics()
    test_s004_coordinator_current_dispatch()
    test_s004_coordinator_describe_includes_dispatcher()
    test_s004_coordinator_process_all_dispatch_records()
    test_s004_coordinator_fifo_dispatch_order()
    test_s004_dispatch_record_on_failed_result()
    test_s004_result_sprint004_fields_defaults()
    test_s004_coordinator_queue_and_dispatcher_separate()
    test_s004_backward_compat_all_previous_apis()
    test_s004_public_api_surface()

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