"""
Genesis-018 Sprint 005 — Engineering Coordinator Test Suite
Deterministic validation: ~460 checks.

Sprints 001-004 regression + Sprint 005 worker interface.

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
    DefaultEngineeringWorker,
    DispatchPolicy,
    LocalEngineeringWorker,
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
    EngineeringWorker,
    QueueSnapshot,
    QueueStatus,
    SessionEvent,
    WorkerRecord,
    WorkerStatus,
)


# ===========================================================================
# Stubs
# ===========================================================================

class _StubPlanner:
    def plan(self, r, *, context=""): return f"Plan for: {r}"

class _FailingPlanner:
    def plan(self, r, **k): raise RuntimeError("planner error")

class _StubGuardrails:
    def check(self, r, *, plan=None): return True

class _BlockingGuardrails:
    def check(self, r, **k): return False

class _FailingGuardrails:
    def check(self, r, **k): raise RuntimeError("guardrails error")

class _PassingTestRunner:
    class _R:
        passed = True
        def __str__(self): return "passed"
    def run(self, r, **k): return self._R()

class _FailingTestRunner:
    class _R:
        passed = False
        def __str__(self): return "failed"
    def run(self, r, **k): return self._R()

class _RaisingTestRunner:
    def run(self, r, **k): raise RuntimeError("runner crash")

class _StubDebugger:
    class _R:
        report      = "debug done"
        repair_plan = "apply patch"
        def __str__(self): return "debug done"
    def debug(self, r, **k): return self._R()


# ===========================================================================
# Helpers
# ===========================================================================

_PASSED = 0
_FAILED = 0
_ERRORS: list[str] = []

def _assert(c: bool, n: str) -> None:
    global _PASSED, _FAILED
    if c: _PASSED += 1
    else:
        _FAILED += 1; _ERRORS.append(f"FAIL: {n}"); print(f"  ✗ {n}")

def _section(t: str) -> None:
    print(f"\n{'─'*60}\n  {t}\n{'─'*60}")

def _coord(**kw):
    return EngineeringCoordinator(
        planner=_StubPlanner(), guardrails=_StubGuardrails(),
        test_runner=_PassingTestRunner(), **kw
    )

def _req(t="Test"): return EngineeringRequest(request=t)
def _sess(t="S"):   return EngineeringSession.create(_req(t))


# ===========================================================================
# ── SPRINTS 001-004 REGRESSION (condensed) ────────────────────────────────
# ===========================================================================

def test_s001_regression() -> None:
    _section("[S001-S004] Full regression")
    # Status
    for v in ["PENDING","PLANNING","VALIDATING","DEBUGGING","COMPLETE","FAILED"]:
        _assert(EngineeringStatus(v).value == v, f"Status {v}")
    _assert(EngineeringStatus.COMPLETE.is_terminal(), "terminal")
    _assert(len(EngineeringStatus) == 6, "6 statuses")

    # Request
    r = _req("X")
    _assert(r.request == "X", "request stored")
    try: r.request = "y"; _assert(False, "immutable")  # type: ignore
    except (AttributeError, TypeError): _assert(True, "immutable")
    for bad, exc in [({"request":""},ValueError),({"request":1},TypeError)]:
        try: EngineeringRequest(**bad); _assert(False,"bad")  # type: ignore
        except exc: _assert(True, f"{exc.__name__}")

    # Result
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.succeeded, "succeeded")
    _assert(not res.failed, "not failed")
    try: EngineeringResult(status=EngineeringStatus.COMPLETE, duration_ms=-1); _assert(False,"neg")
    except ValueError: _assert(True,"neg raises")

    # Pipeline
    c = _coord(debugger=_StubDebugger())
    _assert(c.coordinate(_req()).succeeded, "direct coordinate")
    c2 = EngineeringCoordinator(planner=_StubPlanner(), guardrails=_BlockingGuardrails())
    _assert(c2.coordinate(_req()).failed, "blocked → FAILED")

    # Stage
    for v in ["INITIALISING","PLANNING","GUARDRAILS","VALIDATION",
              "DEBUGGING","REPAIR_PLANNING","COMPLETE","FAILED"]:
        _assert(EngineeringStage(v).value == v, f"Stage {v}")
    _assert(len(EngineeringStage) == 8, "8 stages")

    # Session
    s = _sess()
    _assert(not s.is_complete, "not complete")
    res2 = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    s.complete(res2)
    _assert(s.is_complete, "complete")

    # Queue
    q = EngineeringQueue()
    _assert(q.empty(), "empty")
    s1 = _sess("A"); s2 = _sess("B")
    _assert(q.enqueue(s1) == 1, "pos 1")
    _assert(q.enqueue(s2) == 2, "pos 2")
    d = q.dequeue()
    _assert(d.session_id == s1.session_id, "FIFO")
    q.mark_active_complete()

    # QueueStatus / QueueSnapshot
    for v in ["EMPTY","WAITING","PROCESSING","COMPLETE"]:
        _assert(QueueStatus(v).value == v, f"QueueStatus {v}")
    snap = QueueSnapshot(queue_size=1, status=QueueStatus.WAITING, timestamp_ms=0)
    _assert(snap.queue_size == 1, "snap size")

    # Dispatcher
    d2 = EngineeringDispatcher()
    q2 = EngineeringQueue(); q2.enqueue(_sess())
    rec = d2.dispatch_next(q2)
    _assert(rec is not None, "dispatch_next")
    _assert(rec.status == DispatchStatus.DISPATCHING, "DISPATCHING")
    comp = d2.complete_dispatch()
    _assert(comp.is_complete, "completed")

    # DispatchStatus / DispatchRecord
    for v in ["IDLE","READY","DISPATCHING","COMPLETE"]:
        _assert(DispatchStatus(v).value == v, f"DispatchStatus {v}")

    # submit / process
    c3 = _coord()
    for i in range(3): c3.submit(_req(f"T{i}"))
    results = c3.process_all()
    _assert(len(results) == 3, "3 results")
    _assert(all(r.succeeded for r in results), "all succeeded")
    _assert(results[0].queue_position == 1, "pos 1")
    # dispatch records from sprint 004
    _assert(all(r.has_dispatch_record for r in results), "all have dispatch records")


# ===========================================================================
# ── SPRINT 005 — WorkerStatus ──────────────────────────────────────────────
# ===========================================================================

def test_s005_worker_status_values() -> None:
    _section("[S005] WorkerStatus — values")
    for v in ["IDLE","READY","BUSY","COMPLETED","UNAVAILABLE"]:
        _assert(WorkerStatus(v).value == v, f"WorkerStatus.{v}")
    _assert(len(WorkerStatus) == 5, "Exactly 5 values")

def test_s005_worker_status_properties() -> None:
    _section("[S005] WorkerStatus — properties")
    _assert(WorkerStatus.IDLE.can_accept(),         "IDLE can_accept")
    _assert(WorkerStatus.COMPLETED.can_accept(),    "COMPLETED can_accept")
    _assert(not WorkerStatus.BUSY.can_accept(),     "BUSY cannot accept")
    _assert(not WorkerStatus.READY.can_accept(),    "READY cannot accept")
    _assert(not WorkerStatus.UNAVAILABLE.can_accept(), "UNAVAILABLE cannot accept")

    _assert(WorkerStatus.READY.is_busy(),           "READY is_busy")
    _assert(WorkerStatus.BUSY.is_busy(),            "BUSY is_busy")
    _assert(not WorkerStatus.IDLE.is_busy(),        "IDLE not busy")
    _assert(not WorkerStatus.COMPLETED.is_busy(),   "COMPLETED not busy")
    _assert(not WorkerStatus.UNAVAILABLE.is_busy(), "UNAVAILABLE not busy")

    _assert(WorkerStatus.IDLE.is_available(),        "IDLE available")
    _assert(WorkerStatus.BUSY.is_available(),        "BUSY available")
    _assert(WorkerStatus.READY.is_available(),       "READY available")
    _assert(WorkerStatus.COMPLETED.is_available(),   "COMPLETED available")
    _assert(not WorkerStatus.UNAVAILABLE.is_available(), "UNAVAILABLE not available")


# ===========================================================================
# ── SPRINT 005 — WorkerRecord ──────────────────────────────────────────────
# ===========================================================================

def test_s005_worker_record_construction() -> None:
    _section("[S005] WorkerRecord — construction")
    rec = WorkerRecord(
        worker_id="wid-001", worker_name="TestWorker",
        status=WorkerStatus.IDLE, created_at=1000,
    )
    _assert(rec.worker_id   == "wid-001",       "worker_id")
    _assert(rec.worker_name == "TestWorker",    "worker_name")
    _assert(rec.status      == WorkerStatus.IDLE, "status")
    _assert(rec.created_at  == 1000,            "created_at")
    _assert(rec.completed_sessions == 0,        "completed_sessions default 0")
    _assert(rec.current_session_id is None,     "current_session_id None")
    _assert(rec.last_activity_ms   is None,     "last_activity_ms None")
    _assert(not rec.has_current_session,        "has_current_session False")
    _assert(rec.can_accept,                     "can_accept True for IDLE")
    _assert(not rec.is_busy,                    "is_busy False for IDLE")
    # capabilities default
    _assert(rec.capabilities == (),             "capabilities default empty tuple")
    _assert(not rec.has_capabilities,           "has_capabilities False when empty")

def test_s005_worker_record_capabilities() -> None:
    _section("[S005] WorkerRecord — capabilities")
    rec = WorkerRecord(
        worker_id="w", worker_name="W", status=WorkerStatus.IDLE,
        created_at=0, capabilities=("engineering", "planning"),
    )
    _assert(rec.capabilities == ("engineering", "planning"), "capabilities stored")
    _assert(rec.has_capabilities,                            "has_capabilities True")
    _assert(rec.has_capability("engineering"),               "has engineering")
    _assert(rec.has_capability("planning"),                  "has planning")
    _assert(not rec.has_capability("testing"),               "no testing")
    _assert("caps=" in repr(rec),                           "caps in repr")
    # immutability of tuple
    try:
        rec.capabilities = ("testing",)  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "capabilities immutable")

def test_s005_worker_record_capabilities_validation() -> None:
    _section("[S005] WorkerRecord — capabilities validation")
    base = dict(worker_id="w", worker_name="W", status=WorkerStatus.IDLE, created_at=0)
    try:
        WorkerRecord(**{**base, "capabilities": ["engineering"]})  # type: ignore
        _assert(False, "list should raise TypeError")
    except TypeError:
        _assert(True, "list raises TypeError")

def test_s005_worker_record_with_session() -> None:
    _section("[S005] WorkerRecord — with active session")
    rec = WorkerRecord(
        worker_id="w", worker_name="W", status=WorkerStatus.BUSY,
        created_at=0, current_session_id="sess-xyz", completed_sessions=2,
    )
    _assert(rec.has_current_session,               "has_current_session True")
    _assert(rec.current_session_id == "sess-xyz",  "session_id stored")
    _assert(rec.completed_sessions == 2,           "completed 2")
    _assert(rec.is_busy,                           "is_busy True for BUSY")
    _assert(not rec.can_accept,                    "cannot accept when BUSY")

def test_s005_worker_record_immutability() -> None:
    _section("[S005] WorkerRecord — immutability")
    rec = WorkerRecord(worker_id="w", worker_name="W",
                       status=WorkerStatus.IDLE, created_at=0)
    try:
        rec.status = WorkerStatus.BUSY  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")

def test_s005_worker_record_validation() -> None:
    _section("[S005] WorkerRecord — validation")
    base = dict(worker_id="w", worker_name="W", status=WorkerStatus.IDLE, created_at=0)
    for bad, exc, label in [
        ({**base, "worker_id": "  "}, ValueError, "blank worker_id"),
        ({**base, "worker_name": ""}, ValueError, "blank worker_name"),
        ({**base, "status": "IDLE"}, TypeError, "str status"),
        ({**base, "created_at": "now"}, TypeError, "str created_at"),
        ({**base, "completed_sessions": -1}, ValueError, "negative completed"),
    ]:
        try:
            WorkerRecord(**bad)  # type: ignore
            _assert(False, f"{label} should raise")
        except exc:
            _assert(True, f"{label} raises {exc.__name__}")

def test_s005_worker_record_repr() -> None:
    _section("[S005] WorkerRecord — repr")
    rec = WorkerRecord(worker_id="wid-001", worker_name="W",
                       status=WorkerStatus.IDLE, created_at=0)
    r = repr(rec)
    _assert("WorkerRecord" in r, "class name")
    _assert("IDLE"         in r, "status")
    _assert("'W'"          in r, "worker_name")


# ===========================================================================
# ── SPRINT 005 — EngineeringWorker (ABC contract) ──────────────────────────
# ===========================================================================

def test_s005_worker_is_abstract() -> None:
    _section("[S005] EngineeringWorker — is abstract")
    import inspect
    _assert(inspect.isabstract(EngineeringWorker), "EngineeringWorker is abstract")
    # Cannot instantiate directly
    try:
        EngineeringWorker()  # type: ignore
        _assert(False, "cannot instantiate ABC")
    except TypeError:
        _assert(True, "TypeError on direct instantiation")

def test_s005_worker_abstract_methods() -> None:
    _section("[S005] EngineeringWorker — abstract method signatures")
    abstract_methods = {
        "worker_id", "worker_name", "can_accept", "accept_session",
        "status", "current_session", "complete_session", "clear", "record",
    }
    for method in abstract_methods:
        _assert(hasattr(EngineeringWorker, method), f"ABC has {method}")


# ===========================================================================
# ── SPRINT 005 — DefaultEngineeringWorker ──────────────────────────────────
# ===========================================================================

def test_s005_default_worker_construction() -> None:
    _section("[S005] LocalEngineeringWorker — construction")
    w = LocalEngineeringWorker()
    _assert(w.status()         == WorkerStatus.IDLE, "initial IDLE")
    _assert(w.can_accept(),                           "can accept initially")
    _assert(w.current_session() is None,              "no current session")
    _assert(w.completed_count   == 0,                 "completed 0")
    _assert(not w.is_busy,                            "not busy")
    _assert(w.is_idle,                                "is_idle True")

    # Custom name
    w2 = LocalEngineeringWorker(name="MyWorker")
    _assert(w2.worker_name() == "MyWorker", "custom name")

    # Custom ID
    w3 = LocalEngineeringWorker(worker_id="fixed-id-001")
    _assert(w3.worker_id() == "fixed-id-001", "custom id")

def test_s005_default_worker_name_validation() -> None:
    _section("[S005] LocalEngineeringWorker — name validation")
    try:
        LocalEngineeringWorker(name="  ")
        _assert(False, "blank name should raise")
    except ValueError:
        _assert(True, "blank name raises ValueError")
    try:
        LocalEngineeringWorker(name="")
        _assert(False, "empty name should raise")
    except ValueError:
        _assert(True, "empty name raises ValueError")

def test_s005_default_worker_implements_abc() -> None:
    _section("[S005] LocalEngineeringWorker — implements ABC")
    w = LocalEngineeringWorker()
    _assert(isinstance(w, EngineeringWorker), "isinstance EngineeringWorker")

def test_s005_default_worker_accept_session() -> None:
    _section("[S005] LocalEngineeringWorker — accept_session")
    w = LocalEngineeringWorker()
    s = _sess("Accept me")

    accepted = w.accept_session(s)
    _assert(accepted,                               "accepted returns True")
    _assert(w.status() == WorkerStatus.BUSY,        "status BUSY after accept")
    _assert(w.current_session() is s,               "current_session is s")
    _assert(not w.can_accept(),                     "cannot accept when BUSY")
    _assert(not w.is_idle,                          "not idle")
    _assert(w.is_busy,                              "is_busy True")

def test_s005_default_worker_accept_session_type_safety() -> None:
    _section("[S005] LocalEngineeringWorker — accept_session type safety")
    w = LocalEngineeringWorker()
    try:
        w.accept_session("not a session")  # type: ignore
        _assert(False, "str raises TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")
    try:
        w.accept_session(None)  # type: ignore
        _assert(False, "None raises TypeError")
    except TypeError:
        _assert(True, "None raises TypeError")

def test_s005_default_worker_accept_when_busy() -> None:
    _section("[S005] LocalEngineeringWorker — accept_session when busy")
    w  = LocalEngineeringWorker()
    s1 = _sess("First")
    s2 = _sess("Second")
    w.accept_session(s1)
    accepted2 = w.accept_session(s2)
    _assert(not accepted2, "second accept returns False")
    _assert(w.current_session() is s1, "first session unchanged")

def test_s005_default_worker_complete_session() -> None:
    _section("[S005] LocalEngineeringWorker — complete_session")
    w = LocalEngineeringWorker()
    s = _sess("Complete me")
    w.accept_session(s)
    completed = w.complete_session()

    _assert(completed is s,                           "returned completed session")
    _assert(w.status() == WorkerStatus.COMPLETED,     "status COMPLETED")
    _assert(w.current_session() is None,              "no current session")
    _assert(w.completed_count == 1,                   "completed count 1")
    _assert(w.can_accept(),                           "can accept after complete")
    _assert(not w.is_busy,                            "not busy")

def test_s005_default_worker_complete_when_idle() -> None:
    _section("[S005] LocalEngineeringWorker — complete when idle")
    w = LocalEngineeringWorker()
    result = w.complete_session()
    _assert(result is None, "None when idle")

def test_s005_default_worker_clear() -> None:
    _section("[S005] LocalEngineeringWorker — clear")
    w = LocalEngineeringWorker()
    s = _sess()
    w.accept_session(s)
    w.clear()

    _assert(w.status() == WorkerStatus.IDLE, "IDLE after clear")
    _assert(w.can_accept(),                  "can accept after clear")
    _assert(w.current_session() is None,     "no session after clear")
    # completed_count preserved
    _assert(w.completed_count == 0,          "completed_count unchanged by clear")

def test_s005_default_worker_record() -> None:
    _section("[S005] LocalEngineeringWorker — record()")
    w = LocalEngineeringWorker(name="RecordWorker")
    rec = w.record()

    _assert(isinstance(rec, WorkerRecord),       "returns WorkerRecord")
    _assert(rec.worker_name == "RecordWorker",   "name in record")
    _assert(rec.worker_id   == w.worker_id(),    "id in record")
    _assert(rec.status      == WorkerStatus.IDLE, "status IDLE")
    _assert(rec.completed_sessions == 0,         "completed 0")
    _assert(not rec.has_current_session,         "no current session")

    # After accepting session
    s = _sess()
    w.accept_session(s)
    rec2 = w.record()
    _assert(rec2.status == WorkerStatus.BUSY,      "status BUSY")
    _assert(rec2.has_current_session,              "has session")
    _assert(rec2.current_session_id == s.session_id, "session_id correct")

def test_s005_default_worker_record_independence() -> None:
    _section("[S005] LocalEngineeringWorker — record independence")
    w   = LocalEngineeringWorker()
    rec = w.record()
    _assert(rec.status == WorkerStatus.IDLE, "record IDLE before change")

    # Mutate worker state — record must not change
    w.accept_session(_sess())
    _assert(rec.status == WorkerStatus.IDLE, "old record unchanged after state change")
    _assert(w.status() == WorkerStatus.BUSY, "worker now BUSY")

def test_s005_default_worker_lifecycle() -> None:
    _section("[S005] LocalEngineeringWorker — full lifecycle")
    w = LocalEngineeringWorker()
    for i in range(3):
        _assert(w.can_accept(), f"cycle {i}: can accept")
        s = _sess(f"Cycle {i}")
        accepted = w.accept_session(s)
        _assert(accepted,                     f"cycle {i}: accepted")
        _assert(w.status() == WorkerStatus.BUSY, f"cycle {i}: BUSY")
        w.complete_session()
        _assert(w.status() == WorkerStatus.COMPLETED, f"cycle {i}: COMPLETED")
        w.clear()
        _assert(w.status() == WorkerStatus.IDLE, f"cycle {i}: back to IDLE")
    _assert(w.completed_count == 3, "3 completed across lifecycle")

def test_s005_default_worker_completed_ids() -> None:
    _section("[S005] LocalEngineeringWorker — completed session IDs")
    w = LocalEngineeringWorker()
    sessions = [_sess(f"S{i}") for i in range(3)]
    for s in sessions:
        w.accept_session(s)
        w.complete_session()
        w.clear()

    ids = w.completed_session_ids
    _assert(len(ids) == 3, "3 completed IDs")
    for s in sessions:
        _assert(s.session_id in ids, f"{s.session_id[:8]} in ids")
    # snapshot independence
    ids.append("fake")
    _assert(w.completed_count == 3, "worker count unaffected")

def test_s005_default_worker_mark_unavailable() -> None:
    _section("[S005] LocalEngineeringWorker — mark_unavailable")
    w = LocalEngineeringWorker()
    w.mark_unavailable()
    _assert(w.status() == WorkerStatus.UNAVAILABLE, "UNAVAILABLE")
    _assert(not w.can_accept(),                     "cannot accept")
    _assert(not w.status().is_available(),          "not available")
    # clear recovers
    w.clear()
    _assert(w.status() == WorkerStatus.IDLE,        "IDLE after clear")

def test_s005_default_worker_repr() -> None:
    _section("[S005] LocalEngineeringWorker — repr")
    w = LocalEngineeringWorker(name="ReprWorker")
    r = repr(w)
    _assert("LocalEngineeringWorker" in r, "class name")
    _assert("ReprWorker"              in r, "worker name")
    _assert("IDLE"                    in r, "status")


# ===========================================================================
# ── SPRINT 005 — Dispatcher + Worker integration ───────────────────────────
# ===========================================================================

def test_s005_dispatcher_can_dispatch_to_worker() -> None:
    _section("[S005] Dispatcher.can_dispatch_to_worker()")
    d = EngineeringDispatcher()
    w = DefaultEngineeringWorker()
    q = EngineeringQueue()

    # empty queue
    _assert(not d.can_dispatch_to_worker(q, w), "False: empty queue")

    q.enqueue(_sess())
    _assert(d.can_dispatch_to_worker(q, w), "True: queue has work, worker idle")

    # worker busy
    w2 = DefaultEngineeringWorker()
    w2.accept_session(_sess("busy"))
    _assert(not d.can_dispatch_to_worker(q, w2), "False: worker busy")

    # worker unavailable
    w3 = DefaultEngineeringWorker()
    w3.mark_unavailable()
    _assert(not d.can_dispatch_to_worker(q, w3), "False: worker unavailable")

def test_s005_dispatcher_can_dispatch_to_worker_type_safety() -> None:
    _section("[S005] Dispatcher.can_dispatch_to_worker() — type safety")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    try:
        d.can_dispatch_to_worker(q, "not a worker")  # type: ignore
        _assert(False, "str raises TypeError")
    except TypeError:
        _assert(True, "str raises TypeError")

def test_s005_dispatcher_dispatch_to_worker() -> None:
    _section("[S005] Dispatcher.dispatch_next(worker=...)")
    d = EngineeringDispatcher()
    w = DefaultEngineeringWorker()
    q = EngineeringQueue()
    s = _sess("Worker dispatch")
    q.enqueue(s)

    rec = d.dispatch_next(q, worker=w)
    _assert(rec is not None,                         "record returned")
    _assert(w.status() == WorkerStatus.BUSY,         "worker BUSY after dispatch")
    _assert(w.current_session() is not None,         "worker has session")
    _assert(w.current_session().session_id == s.session_id, "correct session assigned")

def test_s005_dispatcher_dispatch_to_busy_worker_raises() -> None:
    _section("[S005] Dispatcher — dispatch to busy worker raises")
    d = EngineeringDispatcher()
    w = DefaultEngineeringWorker()
    w.accept_session(_sess("already busy"))

    q = EngineeringQueue()
    q.enqueue(_sess("New work"))

    # can_dispatch_to_worker returns False, so dispatch_next with busy worker raises
    try:
        d.dispatch_next(q, worker=w)
        _assert(False, "busy worker should raise RuntimeError")
    except RuntimeError:
        _assert(True, "busy worker raises RuntimeError")

def test_s005_dispatcher_dispatch_next_type_safety_worker() -> None:
    _section("[S005] Dispatcher.dispatch_next() — worker type safety")
    d = EngineeringDispatcher()
    q = EngineeringQueue()
    q.enqueue(_sess())
    try:
        d.dispatch_next(q, worker="not a worker")  # type: ignore
        _assert(False, "str worker raises TypeError")
    except TypeError:
        _assert(True, "str worker raises TypeError")


# ===========================================================================
# ── SPRINT 005 — Coordinator + Worker integration ──────────────────────────
# ===========================================================================

def test_s005_coordinator_owns_worker() -> None:
    _section("[S005] Coordinator — owns worker")
    c = _coord()
    _assert(isinstance(c.worker, EngineeringWorker),          "worker is EngineeringWorker")
    _assert(isinstance(c.worker, LocalEngineeringWorker),   "worker is LocalEngineeringWorker")

def test_s005_coordinator_worker_record() -> None:
    _section("[S005] Coordinator.worker_record()")
    c   = _coord()
    rec = c.worker_record()
    _assert(isinstance(rec, WorkerRecord),    "returns WorkerRecord")
    _assert(rec.status == WorkerStatus.IDLE,  "IDLE initially")

def test_s005_coordinator_worker_statistics() -> None:
    _section("[S005] Coordinator.worker_statistics()")
    c     = _coord()
    stats = c.worker_statistics()
    _assert(isinstance(stats, dict),          "returns dict")
    _assert(stats["completed_sessions"] == 0, "completed 0")
    _assert(stats["is_busy"]            == 0, "not busy")
    _assert(stats["can_accept"]         == 1, "can accept")

    c.submit(_req("W-Stats"))
    c.process_next()
    stats2 = c.worker_statistics()
    _assert(stats2["completed_sessions"] == 1, "completed 1")
    _assert(stats2["is_busy"]            == 0, "not busy after complete")
    _assert(stats2["can_accept"]         == 1, "can accept again")

def test_s005_coordinator_process_next_worker_id_on_result() -> None:
    _section("[S005] Coordinator.process_next() — worker_id on result")
    c = _coord()
    c.submit(_req("Worker result"))
    result = c.process_next()

    _assert(result is not None,                                "result returned")
    _assert(result.has_worker_id,                              "has_worker_id True")
    _assert(result.worker_id is not None,                      "worker_id set")
    _assert(result.has_worker_status,                          "has_worker_status True")
    _assert(result.worker_status == WorkerStatus.COMPLETED,    "worker_status COMPLETED")
    _assert(result.worker_id == c.worker.worker_id(),          "worker_id matches coordinator's worker")

def test_s005_coordinator_direct_no_worker_id() -> None:
    _section("[S005] Coordinator.coordinate() — no worker_id (backwards compat)")
    c = _coord()
    r = c.coordinate(_req("Direct"))
    _assert(not r.has_worker_id,     "no worker_id on direct call")
    _assert(not r.has_worker_status, "no worker_status on direct call")
    _assert(r.worker_id is None,     "worker_id None")

def test_s005_coordinator_process_all_worker_ids() -> None:
    _section("[S005] Coordinator.process_all() — all results have worker_id")
    c = _coord()
    for i in range(4): c.submit(_req(f"W{i}"))
    results = c.process_all()
    _assert(len(results) == 4, "4 results")
    for i, r in enumerate(results):
        _assert(r.has_worker_id,                           f"result {i} has worker_id")
        _assert(r.worker_status == WorkerStatus.COMPLETED, f"result {i} COMPLETED")

def test_s005_coordinator_worker_reused_across_requests() -> None:
    _section("[S005] Coordinator — same worker reused across requests")
    c = _coord()
    for i in range(5): c.submit(_req(f"Reuse {i}"))
    results = c.process_all()
    worker_ids = {r.worker_id for r in results}
    _assert(len(worker_ids) == 1, "same worker_id across all results")
    _assert(c.worker_statistics()["completed_sessions"] == 5, "5 sessions completed")

def test_s005_coordinator_describe_includes_worker() -> None:
    _section("[S005] Coordinator.describe() — worker info")
    c = _coord()
    d = c.describe()
    _assert("worker" in d,   "worker in describe()")
    _assert("018.005" in d["version"], "version 018.005")

def test_s005_coordinator_worker_queue_dispatcher_separate() -> None:
    _section("[S005] Coordinator — queue, dispatcher, worker are distinct objects")
    c = _coord()
    _assert(c.queue is not c.dispatcher,  "queue ≠ dispatcher")
    _assert(c.queue is not c.worker,      "queue ≠ worker")
    _assert(c.dispatcher is not c.worker, "dispatcher ≠ worker")
    _assert(isinstance(c.queue,      EngineeringQueue),           "queue type")
    _assert(isinstance(c.dispatcher, EngineeringDispatcher),      "dispatcher type")
    _assert(isinstance(c.worker,     DefaultEngineeringWorker),   "worker type")

def test_s005_worker_id_consistent_with_dispatch_record() -> None:
    _section("[S005] worker_id consistent with dispatch_record on result")
    c = _coord()
    c.submit(_req("Consistency check"))
    r = c.process_next()
    _assert(r.has_dispatch_record,  "has dispatch_record")
    _assert(r.has_worker_id,        "has worker_id")
    # Both should refer to the same execution unit
    _assert(r.dispatch_record.session_id == r.session_id, "dispatch session matches result session")

def test_s005_result_sprint005_defaults() -> None:
    _section("[S005] EngineeringResult — Sprint 005 defaults")
    res = EngineeringResult(status=EngineeringStatus.COMPLETE)
    _assert(res.worker_id     is None,  "worker_id None default")
    _assert(res.worker_status is None,  "worker_status None default")
    _assert(not res.has_worker_id,      "has_worker_id False")
    _assert(not res.has_worker_status,  "has_worker_status False")

def test_s005_backward_compat_all_previous_apis() -> None:
    _section("[S005] Backwards compatibility — all Sprint 001-004 APIs work")
    c = _coord(debugger=_StubDebugger())

    # S001
    r1 = c.coordinate(_req("S001"))
    _assert(r1.succeeded, "S001 coordinate")

    # S002
    _assert(r1.has_session,         "S002 session")
    _assert(r1.has_timeline,        "S002 timeline")
    _assert(r1.has_stage_durations, "S002 stage_durations")

    # S003
    pos = c.submit(_req("S003"))
    _assert(pos == 1, "S003 submit")
    r2 = c.process_next()
    _assert(r2.has_queue_position, "S003 queue_position")
    _assert(r2.has_queue_snapshot, "S003 queue_snapshot")

    # S004
    _assert(r2.has_dispatch_record, "S004 dispatch_record")
    _assert("total_dispatched" in c.dispatch_statistics(), "S004 dispatch_statistics")

    # S005
    _assert(r2.has_worker_id,     "S005 worker_id")
    _assert(r2.has_worker_status, "S005 worker_status")
    _assert(isinstance(c.worker_record(), WorkerRecord), "S005 worker_record")


# ===========================================================================
# ── SPRINT 005 — Public API surface ────────────────────────────────────────
# ===========================================================================

def test_s005_local_worker_stable_id() -> None:
    _section("[S005] LocalEngineeringWorker — stable worker_id")
    # Default ID follows convention
    w1 = LocalEngineeringWorker()
    _assert(w1.worker_id().startswith("worker-local-"), "ID starts with worker-local-")
    # Different instances get different IDs
    w2 = LocalEngineeringWorker()
    _assert(w1.worker_id() != w2.worker_id(), "unique IDs per instance")
    # Custom stable ID
    w3 = LocalEngineeringWorker(worker_id="worker-local-001")
    _assert(w3.worker_id() == "worker-local-001", "custom ID stored")
    # ID in record
    rec = w3.record()
    _assert(rec.worker_id == "worker-local-001", "ID in WorkerRecord")

def test_s005_local_worker_capabilities() -> None:
    _section("[S005] LocalEngineeringWorker — capabilities")
    # Default capabilities
    w = LocalEngineeringWorker()
    _assert(w.capabilities() == ("engineering",), "default capabilities")
    # Custom capabilities
    w2 = LocalEngineeringWorker(capabilities=("engineering", "planning"))
    _assert(w2.capabilities() == ("engineering", "planning"), "custom capabilities")
    # Capabilities immutable (tuple)
    caps = w.capabilities()
    _assert(isinstance(caps, tuple), "capabilities is tuple")
    # In WorkerRecord
    rec = w.record()
    _assert(rec.capabilities == ("engineering",), "capabilities in record")
    _assert(rec.has_capability("engineering"),     "has engineering")
    _assert(not rec.has_capability("testing"),     "no testing by default")

def test_s005_default_worker_alias() -> None:
    _section("[S005] DefaultEngineeringWorker — backwards-compat alias")
    # DefaultEngineeringWorker is an alias for LocalEngineeringWorker
    _assert(DefaultEngineeringWorker is LocalEngineeringWorker, "alias is same class")
    w = DefaultEngineeringWorker()
    _assert(isinstance(w, LocalEngineeringWorker),  "isinstance LocalEngineeringWorker")
    _assert(isinstance(w, EngineeringWorker),        "isinstance EngineeringWorker")

def test_s005_worker_id_on_coordinator_result() -> None:
    _section("[S005] worker_id on coordinator result follows convention")
    c = _coord()
    c.submit(_req("ID convention"))
    r = c.process_next()
    _assert(r.worker_id is not None,                       "worker_id set")
    _assert(r.worker_id.startswith("worker-local-"),       "follows convention")
    _assert(r.worker_id == c.worker.worker_id(),           "matches coordinator worker")

def test_s005_worker_record_capabilities_in_coordinator() -> None:
    _section("[S005] WorkerRecord capabilities via coordinator")
    c   = _coord()
    rec = c.worker_record()
    _assert(rec.has_capabilities,                          "has capabilities")
    _assert(rec.has_capability("engineering"),             "has engineering")
    _assert(isinstance(rec.capabilities, tuple),          "capabilities is tuple")

def test_s005_local_worker_name_and_id_in_repr() -> None:
    _section("[S005] LocalEngineeringWorker — repr includes id and capabilities")
    w = LocalEngineeringWorker(name="ReprCheck", worker_id="worker-local-999")
    r = repr(w)
    _assert("LocalEngineeringWorker" in r,    "class name in repr")
    _assert("worker-local-999"       in r,    "worker_id in repr")
    _assert("ReprCheck"              in r,    "name in repr")
    _assert("engineering"            in r,    "capabilities in repr")


def test_s005_public_api_surface() -> None:
    _section("[S005] Public API surface — __init__ exports")
    import core.engineering.coordinator as pkg
    expected = [
        "EngineeringCoordinator","EngineeringRequest","EngineeringResult",
        "EngineeringStatus","CoordinatorConfig","CoordinatorEvent",
        "EngineeringStage","EngineeringSession","CoordinatorEventLog","SessionEvent",
        "EngineeringQueue","QueueStatus","QueueSnapshot",
        "EngineeringDispatcher","DispatchStatus","DispatchRecord","DispatchPolicy",
        "EngineeringWorker","DefaultEngineeringWorker","WorkerStatus","WorkerRecord",
    ]
    for name in expected:
        _assert(hasattr(pkg, name), f"{name} exported")
    _assert(len(pkg.__all__) == 22, "__all__ has 22 entries")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 005 — Engineering Coordinator Tests")
    print("=" * 60)

    test_s001_regression()

    test_s005_worker_status_values()
    test_s005_worker_status_properties()
    test_s005_worker_record_construction()
    test_s005_worker_record_with_session()
    test_s005_worker_record_immutability()
    test_s005_worker_record_validation()
    test_s005_worker_record_repr()
    test_s005_worker_is_abstract()
    test_s005_worker_abstract_methods()
    test_s005_default_worker_construction()
    test_s005_default_worker_name_validation()
    test_s005_default_worker_implements_abc()
    test_s005_default_worker_accept_session()
    test_s005_default_worker_accept_session_type_safety()
    test_s005_default_worker_accept_when_busy()
    test_s005_default_worker_complete_session()
    test_s005_default_worker_complete_when_idle()
    test_s005_default_worker_clear()
    test_s005_default_worker_record()
    test_s005_default_worker_record_independence()
    test_s005_default_worker_lifecycle()
    test_s005_default_worker_completed_ids()
    test_s005_default_worker_mark_unavailable()
    test_s005_default_worker_repr()
    test_s005_dispatcher_can_dispatch_to_worker()
    test_s005_dispatcher_can_dispatch_to_worker_type_safety()
    test_s005_dispatcher_dispatch_to_worker()
    test_s005_dispatcher_dispatch_to_busy_worker_raises()
    test_s005_dispatcher_dispatch_next_type_safety_worker()
    test_s005_coordinator_owns_worker()
    test_s005_coordinator_worker_record()
    test_s005_coordinator_worker_statistics()
    test_s005_coordinator_process_next_worker_id_on_result()
    test_s005_coordinator_direct_no_worker_id()
    test_s005_coordinator_process_all_worker_ids()
    test_s005_coordinator_worker_reused_across_requests()
    test_s005_coordinator_describe_includes_worker()
    test_s005_coordinator_worker_queue_dispatcher_separate()
    test_s005_worker_id_consistent_with_dispatch_record()
    test_s005_result_sprint005_defaults()
    test_s005_backward_compat_all_previous_apis()
    test_s005_local_worker_stable_id()
    test_s005_local_worker_capabilities()
    test_s005_default_worker_alias()
    test_s005_worker_id_on_coordinator_result()
    test_s005_worker_record_capabilities_in_coordinator()
    test_s005_local_worker_name_and_id_in_repr()
    test_s005_worker_record_capabilities()
    test_s005_worker_record_capabilities_validation()
    test_s005_public_api_surface()

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