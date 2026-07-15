"""
Genesis-018 Sprint 006 — Engineering Coordinator Test Suite
Deterministic validation: ~460 checks.

Sprints 001-005 regression + Sprint 006 Worker Registry.

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
    EngineeringWorkerRegistry,
    LocalEngineeringWorker,
    QueueSnapshot,
    QueueStatus,
    RegistrySnapshot,
    RegistryStatus,
    SessionEvent,
    WorkerRecord,
    WorkerStatus,
)


# ===========================================================================
# Stubs
# ===========================================================================

class _StubPlanner:
    def plan(self, r, *, context=""): return f"Plan: {r}"

class _StubGuardrails:
    def check(self, r, *, plan=None): return True

class _BlockingGuardrails:
    def check(self, r, **k): return False

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

def _worker(name="W", wid=None, caps=None):
    kwargs = {"name": name}
    if wid:  kwargs["worker_id"]    = wid
    if caps: kwargs["capabilities"] = caps
    return LocalEngineeringWorker(**kwargs)


# ===========================================================================
# ── SPRINTS 001-005 REGRESSION (condensed) ────────────────────────────────
# ===========================================================================

def test_regression_s001_s005() -> None:
    _section("[S001-S005] Full regression")

    # Status enum
    for v in ["PENDING","PLANNING","VALIDATING","DEBUGGING","COMPLETE","FAILED"]:
        _assert(EngineeringStatus(v).value == v, f"Status {v}")
    _assert(len(EngineeringStatus) == 6, "6 statuses")

    # Request
    r = _req("X")
    _assert(r.request == "X", "request stored")
    try: r.request = "y"; _assert(False, "immutable")  # type: ignore
    except (AttributeError, TypeError): _assert(True, "immutable")

    # Result
    res = EngineeringResult(status=EngineeringStatus.COMPLETE, completed=True)
    _assert(res.succeeded, "succeeded")
    _assert(not res.failed, "not failed")

    # Pipeline: coordinate
    c = _coord(debugger=_StubDebugger())
    _assert(c.coordinate(_req()).succeeded, "direct coordinate")
    c2 = EngineeringCoordinator(planner=_StubPlanner(), guardrails=_BlockingGuardrails())
    _assert(c2.coordinate(_req()).failed, "blocked → FAILED")

    # Stage enum
    for v in ["INITIALISING","PLANNING","GUARDRAILS","VALIDATION",
              "DEBUGGING","REPAIR_PLANNING","COMPLETE","FAILED"]:
        _assert(EngineeringStage(v).value == v, f"Stage {v}")

    # Queue
    q = EngineeringQueue()
    s1 = _sess("A"); s2 = _sess("B")
    _assert(q.enqueue(s1) == 1, "pos 1")
    _assert(q.enqueue(s2) == 2, "pos 2")
    d = q.dequeue()
    _assert(d.session_id == s1.session_id, "FIFO")
    q.mark_active_complete()

    # QueueStatus / QueueSnapshot
    for v in ["EMPTY","WAITING","PROCESSING","COMPLETE"]:
        _assert(QueueStatus(v).value == v, f"QueueStatus {v}")

    # Dispatcher
    d2 = EngineeringDispatcher()
    q2 = EngineeringQueue(); q2.enqueue(_sess())
    rec = d2.dispatch_next(q2)
    _assert(rec is not None, "dispatch_next")
    comp = d2.complete_dispatch()
    _assert(comp.is_complete, "dispatch completed")

    # WorkerStatus
    for v in ["IDLE","READY","BUSY","COMPLETED","UNAVAILABLE"]:
        _assert(WorkerStatus(v).value == v, f"WorkerStatus {v}")

    # LocalEngineeringWorker
    w = LocalEngineeringWorker(name="Reg", worker_id="worker-local-reg")
    _assert(w.worker_id() == "worker-local-reg", "stable ID")
    _assert(w.capabilities() == ("engineering",), "default caps")
    _assert(w.can_accept(), "can accept")
    w.accept_session(_sess())
    _assert(w.status() == WorkerStatus.BUSY, "BUSY")
    w.complete_session()
    _assert(w.status() == WorkerStatus.COMPLETED, "COMPLETED")
    w.clear()
    _assert(w.status() == WorkerStatus.IDLE, "IDLE after clear")

    # DefaultEngineeringWorker alias
    _assert(DefaultEngineeringWorker is LocalEngineeringWorker, "alias correct")

    # WorkerRecord capabilities
    rec2 = w.record()
    _assert(rec2.has_capability("engineering"), "has capability")
    _assert(isinstance(rec2.capabilities, tuple), "caps is tuple")

    # submit / process_all
    c3 = _coord()
    for i in range(3): c3.submit(_req(f"T{i}"))
    results = c3.process_all()
    _assert(len(results) == 3, "3 results")
    _assert(all(r.succeeded for r in results), "all succeeded")
    _assert(all(r.has_dispatch_record for r in results), "all have dispatch records")
    _assert(all(r.has_worker_id for r in results), "all have worker IDs")


# ===========================================================================
# ── SPRINT 006 — RegistryStatus ────────────────────────────────────────────
# ===========================================================================

def test_s006_registry_status_values() -> None:
    _section("[S006] RegistryStatus — values")
    for v in ["EMPTY","ACTIVE","FULL","DEGRADED"]:
        _assert(RegistryStatus(v).value == v, f"RegistryStatus.{v}")
    _assert(len(RegistryStatus) == 4, "4 values")

def test_s006_registry_status_properties() -> None:
    _section("[S006] RegistryStatus — properties")
    _assert(not RegistryStatus.EMPTY.has_workers(),    "EMPTY no workers")
    _assert(RegistryStatus.ACTIVE.has_workers(),       "ACTIVE has workers")
    _assert(RegistryStatus.FULL.has_workers(),         "FULL has workers")
    _assert(RegistryStatus.DEGRADED.has_workers(),     "DEGRADED has workers")

    _assert(RegistryStatus.ACTIVE.is_available(),      "ACTIVE is available")
    _assert(not RegistryStatus.EMPTY.is_available(),   "EMPTY not available")
    _assert(not RegistryStatus.FULL.is_available(),    "FULL not available")
    _assert(not RegistryStatus.DEGRADED.is_available(), "DEGRADED not available")

    _assert(RegistryStatus.EMPTY.is_healthy(),         "EMPTY is healthy")
    _assert(RegistryStatus.ACTIVE.is_healthy(),        "ACTIVE is healthy")
    _assert(not RegistryStatus.FULL.is_healthy(),      "FULL not healthy")
    _assert(not RegistryStatus.DEGRADED.is_healthy(),  "DEGRADED not healthy")


# ===========================================================================
# ── SPRINT 006 — RegistrySnapshot ──────────────────────────────────────────
# ===========================================================================

def test_s006_registry_snapshot_construction() -> None:
    _section("[S006] RegistrySnapshot — construction")
    snap = RegistrySnapshot(
        status=RegistryStatus.ACTIVE,
        timestamp_ms=1000,
        total_registered=3,
        available_count=2,
        busy_count=1,
        worker_ids=("w-1","w-2","w-3"),
        capabilities=("engineering","testing"),
    )
    _assert(snap.status           == RegistryStatus.ACTIVE, "status")
    _assert(snap.timestamp_ms     == 1000,                  "timestamp")
    _assert(snap.total_registered == 3,                     "total")
    _assert(snap.available_count  == 2,                     "available")
    _assert(snap.busy_count       == 1,                     "busy")
    _assert(snap.worker_ids       == ("w-1","w-2","w-3"),   "worker_ids")
    _assert(snap.capabilities     == ("engineering","testing"), "capabilities")
    _assert(snap.has_available,                              "has_available")
    _assert(not snap.is_empty,                              "not empty")
    _assert(not snap.all_busy,                              "not all busy")
    _assert(snap.unique_capability_count == 2,              "2 unique caps")

def test_s006_registry_snapshot_empty() -> None:
    _section("[S006] RegistrySnapshot — empty state")
    snap = RegistrySnapshot(status=RegistryStatus.EMPTY, timestamp_ms=0)
    _assert(snap.is_empty,         "is_empty")
    _assert(not snap.has_available,"not has_available")
    _assert(not snap.all_busy,     "not all_busy")
    _assert(snap.total_registered == 0, "total 0")

def test_s006_registry_snapshot_all_busy() -> None:
    _section("[S006] RegistrySnapshot — all busy state")
    snap = RegistrySnapshot(
        status=RegistryStatus.FULL, timestamp_ms=0,
        total_registered=2, available_count=0, busy_count=2,
    )
    _assert(snap.all_busy,          "all_busy True")
    _assert(not snap.has_available, "not has_available")

def test_s006_registry_snapshot_immutability() -> None:
    _section("[S006] RegistrySnapshot — immutability")
    snap = RegistrySnapshot(status=RegistryStatus.EMPTY, timestamp_ms=0)
    try:
        snap.status = RegistryStatus.ACTIVE  # type: ignore
        _assert(False, "immutable")
    except (AttributeError, TypeError):
        _assert(True, "immutable")

def test_s006_registry_snapshot_validation() -> None:
    _section("[S006] RegistrySnapshot — validation")
    base = dict(status=RegistryStatus.EMPTY, timestamp_ms=0)
    for bad, exc, label in [
        ({**base, "status": "EMPTY"}, TypeError, "str status"),
        ({**base, "timestamp_ms": "now"}, TypeError, "str timestamp"),
        ({**base, "total_registered": -1}, ValueError, "negative total"),
        ({**base, "available_count": -1}, ValueError, "negative available"),
        ({**base, "worker_ids": ["w1"]}, TypeError, "list worker_ids"),
        ({**base, "capabilities": ["eng"]}, TypeError, "list capabilities"),
    ]:
        try:
            RegistrySnapshot(**bad)  # type: ignore
            _assert(False, f"{label} should raise")
        except exc:
            _assert(True, f"{label} raises {exc.__name__}")

def test_s006_registry_snapshot_repr() -> None:
    _section("[S006] RegistrySnapshot — repr")
    snap = RegistrySnapshot(
        status=RegistryStatus.ACTIVE, timestamp_ms=0,
        total_registered=2, available_count=1, busy_count=1,
    )
    r = repr(snap)
    _assert("RegistrySnapshot" in r, "class name")
    _assert("ACTIVE"           in r, "status")
    _assert("total=2"          in r, "total")


# ===========================================================================
# ── SPRINT 006 — EngineeringWorkerRegistry ─────────────────────────────────
# ===========================================================================

def test_s006_registry_initial_state() -> None:
    _section("[S006] EngineeringWorkerRegistry — initial state")
    reg = EngineeringWorkerRegistry()
    _assert(reg.is_empty,                         "starts empty")
    _assert(reg.size == 0,                        "size 0")
    _assert(reg.available_count == 0,             "available 0")
    _assert(reg.busy_count == 0,                  "busy 0")
    _assert(reg.unavailable_count == 0,           "unavailable 0")
    _assert(reg.status() == RegistryStatus.EMPTY, "status EMPTY")
    _assert(reg.all_workers() == [],              "all_workers empty")
    _assert(reg.available_workers() == [],        "available_workers empty")
    _assert(reg.registered_ids() == [],           "registered_ids empty")
    _assert(reg.all_capabilities() == [],         "no capabilities")
    _assert(reg.first_available() is None,        "first_available None")

def test_s006_registry_register() -> None:
    _section("[S006] EngineeringWorkerRegistry — register")
    reg = EngineeringWorkerRegistry()
    w   = _worker("W1", "worker-local-r01")
    wid = reg.register(w)
    _assert(wid == "worker-local-r01",            "returns worker_id")
    _assert(reg.size == 1,                        "size 1")
    _assert(not reg.is_empty,                     "not empty")
    _assert(reg.status() == RegistryStatus.ACTIVE, "status ACTIVE")
    _assert(reg.contains("worker-local-r01"),     "contains worker")

def test_s006_registry_register_multiple() -> None:
    _section("[S006] EngineeringWorkerRegistry — register multiple")
    reg = EngineeringWorkerRegistry()
    w1 = _worker("W1", "worker-local-r01")
    w2 = _worker("W2", "worker-local-r02")
    w3 = _worker("W3", "worker-local-r03")
    reg.register(w1)
    reg.register(w2)
    reg.register(w3)
    _assert(reg.size == 3,                        "size 3")
    ids = reg.registered_ids()
    _assert(ids == ["worker-local-r01","worker-local-r02","worker-local-r03"], "order preserved")

def test_s006_registry_register_type_safety() -> None:
    _section("[S006] EngineeringWorkerRegistry — register type safety")
    reg = EngineeringWorkerRegistry()
    for bad in ["not a worker", None, 42]:
        try:
            reg.register(bad)  # type: ignore
            _assert(False, f"bad type {type(bad).__name__}")
        except TypeError:
            _assert(True, f"{type(bad).__name__} raises TypeError")

def test_s006_registry_register_duplicate() -> None:
    _section("[S006] EngineeringWorkerRegistry — duplicate rejected")
    reg = EngineeringWorkerRegistry()
    w = _worker("W", "worker-local-dup")
    reg.register(w)
    try:
        reg.register(w)
        _assert(False, "duplicate should raise ValueError")
    except ValueError:
        _assert(True, "duplicate raises ValueError")
    _assert(reg.size == 1, "size still 1")

def test_s006_registry_unregister() -> None:
    _section("[S006] EngineeringWorkerRegistry — unregister")
    reg = EngineeringWorkerRegistry()
    w1 = _worker("W1", "worker-local-u01")
    w2 = _worker("W2", "worker-local-u02")
    reg.register(w1); reg.register(w2)

    removed = reg.unregister("worker-local-u01")
    _assert(removed,                               "returns True")
    _assert(reg.size == 1,                        "size 1")
    _assert(not reg.contains("worker-local-u01"), "w1 gone")
    _assert(reg.contains("worker-local-u02"),     "w2 still there")
    _assert(reg.registered_ids() == ["worker-local-u02"], "order updated")

    # unregister unknown
    removed2 = reg.unregister("nonexistent")
    _assert(not removed2, "False for unknown id")

def test_s006_registry_unregister_type_safety() -> None:
    _section("[S006] EngineeringWorkerRegistry — unregister type safety")
    reg = EngineeringWorkerRegistry()
    try:
        reg.unregister(123)  # type: ignore
        _assert(False, "int raises TypeError")
    except TypeError:
        _assert(True, "int raises TypeError")

def test_s006_registry_replace() -> None:
    _section("[S006] EngineeringWorkerRegistry — replace")
    reg = EngineeringWorkerRegistry()
    w1 = _worker("Original", "worker-local-rep")
    reg.register(w1)

    w2 = LocalEngineeringWorker(name="Replacement", worker_id="worker-local-rep")
    replaced = reg.replace(w2)
    _assert(replaced,                              "returns True (was replaced)")
    _assert(reg.size == 1,                        "size still 1")
    _assert(reg.get("worker-local-rep") is w2,    "new worker stored")

    # replace non-existent (acts as register)
    w3 = _worker("New", "worker-local-new")
    replaced2 = reg.replace(w3)
    _assert(not replaced2,                        "returns False (new registration)")
    _assert(reg.size == 2,                        "size now 2")

def test_s006_registry_clear() -> None:
    _section("[S006] EngineeringWorkerRegistry — clear")
    reg = EngineeringWorkerRegistry()
    for i in range(4):
        reg.register(_worker(f"W{i}", f"worker-local-c{i:02d}"))
    count = reg.clear()
    _assert(count == 4,                           "cleared 4")
    _assert(reg.is_empty,                         "empty after clear")
    _assert(reg.size == 0,                        "size 0")

def test_s006_registry_get() -> None:
    _section("[S006] EngineeringWorkerRegistry — get")
    reg = EngineeringWorkerRegistry()
    w   = _worker("W", "worker-local-g01")
    reg.register(w)

    found = reg.get("worker-local-g01")
    _assert(found is w,                           "get returns worker")
    _assert(reg.get("nonexistent") is None,       "None for unknown id")

def test_s006_registry_get_type_safety() -> None:
    _section("[S006] EngineeringWorkerRegistry — get type safety")
    reg = EngineeringWorkerRegistry()
    try:
        reg.get(42)  # type: ignore
        _assert(False, "int raises TypeError")
    except TypeError:
        _assert(True, "int raises TypeError")

def test_s006_registry_all_workers_order() -> None:
    _section("[S006] EngineeringWorkerRegistry — all_workers insertion order")
    reg = EngineeringWorkerRegistry()
    workers = [_worker(f"W{i}", f"worker-local-o{i:02d}") for i in range(5)]
    for w in workers:
        reg.register(w)
    all_w = reg.all_workers()
    _assert(len(all_w) == 5, "5 workers")
    for i, w in enumerate(all_w):
        _assert(w.worker_id() == workers[i].worker_id(), f"order {i}")

def test_s006_registry_all_workers_snapshot_independence() -> None:
    _section("[S006] EngineeringWorkerRegistry — all_workers snapshot independence")
    reg = EngineeringWorkerRegistry()
    reg.register(_worker("W", "worker-local-si01"))
    snapshot = reg.all_workers()
    snapshot.append(None)  # type: ignore
    _assert(reg.size == 1, "registry unaffected")

def test_s006_registry_available_workers() -> None:
    _section("[S006] EngineeringWorkerRegistry — available_workers")
    reg = EngineeringWorkerRegistry()
    w1  = _worker("W1", "worker-local-av01")
    w2  = _worker("W2", "worker-local-av02")
    w3  = _worker("W3", "worker-local-av03")
    reg.register(w1); reg.register(w2); reg.register(w3)

    _assert(len(reg.available_workers()) == 3, "3 available initially")

    w1.accept_session(_sess("busy"))
    _assert(len(reg.available_workers()) == 2, "2 available when w1 busy")
    _assert(w1 not in reg.available_workers(), "w1 not available")

    w2.mark_unavailable()
    _assert(len(reg.available_workers()) == 1, "1 available when w2 unavailable")

def test_s006_registry_busy_workers() -> None:
    _section("[S006] EngineeringWorkerRegistry — busy_workers")
    reg = EngineeringWorkerRegistry()
    w1  = _worker("W1", "worker-local-bw01")
    w2  = _worker("W2", "worker-local-bw02")
    reg.register(w1); reg.register(w2)
    _assert(len(reg.busy_workers()) == 0, "none busy initially")

    w1.accept_session(_sess())
    _assert(len(reg.busy_workers()) == 1, "1 busy")
    _assert(reg.busy_workers()[0] is w1,  "w1 is busy")

def test_s006_registry_unavailable_workers() -> None:
    _section("[S006] EngineeringWorkerRegistry — unavailable_workers")
    reg = EngineeringWorkerRegistry()
    w   = _worker("W", "worker-local-un01")
    reg.register(w)
    _assert(len(reg.unavailable_workers()) == 0, "none unavailable initially")
    w.mark_unavailable()
    _assert(len(reg.unavailable_workers()) == 1, "1 unavailable")
    _assert(reg.status() == RegistryStatus.DEGRADED, "status DEGRADED")

def test_s006_registry_workers_by_capability() -> None:
    _section("[S006] EngineeringWorkerRegistry — workers_by_capability")
    reg = EngineeringWorkerRegistry()
    w1  = _worker("W1", "worker-local-cb01", caps=("engineering",))
    w2  = _worker("W2", "worker-local-cb02", caps=("testing",))
    w3  = _worker("W3", "worker-local-cb03", caps=("engineering","planning"))
    reg.register(w1); reg.register(w2); reg.register(w3)

    eng = reg.workers_by_capability("engineering")
    tst = reg.workers_by_capability("testing")
    pln = reg.workers_by_capability("planning")
    sec = reg.workers_by_capability("security")

    _assert(len(eng) == 2, "2 engineering workers")
    _assert(len(tst) == 1, "1 testing worker")
    _assert(len(pln) == 1, "1 planning worker")
    _assert(len(sec) == 0, "0 security workers")
    _assert(w1 in eng,     "w1 in engineering")
    _assert(w3 in eng,     "w3 in engineering")
    _assert(w2 in tst,     "w2 in testing")

def test_s006_registry_workers_by_capability_type_safety() -> None:
    _section("[S006] EngineeringWorkerRegistry — workers_by_capability type safety")
    reg = EngineeringWorkerRegistry()
    try:
        reg.workers_by_capability(42)  # type: ignore
        _assert(False, "int raises TypeError")
    except TypeError:
        _assert(True, "int raises TypeError")

def test_s006_registry_available_by_capability() -> None:
    _section("[S006] EngineeringWorkerRegistry — available_workers_by_capability")
    reg = EngineeringWorkerRegistry()
    w1  = _worker("W1", "worker-local-abc01", caps=("engineering",))
    w2  = _worker("W2", "worker-local-abc02", caps=("engineering",))
    reg.register(w1); reg.register(w2)

    _assert(len(reg.available_workers_by_capability("engineering")) == 2, "2 available eng")
    w1.accept_session(_sess())
    _assert(len(reg.available_workers_by_capability("engineering")) == 1, "1 after w1 busy")
    _assert(reg.available_workers_by_capability("engineering")[0] is w2, "w2 available")

def test_s006_registry_first_available() -> None:
    _section("[S006] EngineeringWorkerRegistry — first_available")
    reg = EngineeringWorkerRegistry()
    _assert(reg.first_available() is None, "None when empty")

    w1 = _worker("W1", "worker-local-fa01")
    w2 = _worker("W2", "worker-local-fa02")
    reg.register(w1); reg.register(w2)
    _assert(reg.first_available() is w1, "first is w1 (insertion order)")

    w1.accept_session(_sess())
    _assert(reg.first_available() is w2, "first is w2 after w1 busy")

    w2.accept_session(_sess())
    _assert(reg.first_available() is None, "None when all busy")

def test_s006_registry_status_transitions() -> None:
    _section("[S006] EngineeringWorkerRegistry — status transitions")
    reg = EngineeringWorkerRegistry()
    _assert(reg.status() == RegistryStatus.EMPTY,    "EMPTY initially")

    w = _worker("W", "worker-local-st01")
    reg.register(w)
    _assert(reg.status() == RegistryStatus.ACTIVE,   "ACTIVE after register")

    w.accept_session(_sess())
    _assert(reg.status() == RegistryStatus.FULL,     "FULL when all busy")

    w.complete_session(); w.clear()
    _assert(reg.status() == RegistryStatus.ACTIVE,   "ACTIVE after clear")

    w.mark_unavailable()
    _assert(reg.status() == RegistryStatus.DEGRADED, "DEGRADED when unavailable")

    reg.unregister("worker-local-st01")
    _assert(reg.status() == RegistryStatus.EMPTY,    "EMPTY after unregister all")

def test_s006_registry_all_capabilities() -> None:
    _section("[S006] EngineeringWorkerRegistry — all_capabilities")
    reg = EngineeringWorkerRegistry()
    _assert(reg.all_capabilities() == [], "empty initially")

    reg.register(_worker("W1", "w1", caps=("engineering","planning")))
    reg.register(_worker("W2", "w2", caps=("testing",)))
    reg.register(_worker("W3", "w3", caps=("engineering",)))  # duplicate cap
    caps = reg.all_capabilities()
    _assert("engineering" in caps, "engineering in caps")
    _assert("planning"    in caps, "planning in caps")
    _assert("testing"     in caps, "testing in caps")
    _assert(len(caps) == 3,        "3 unique caps")
    _assert(caps == sorted(caps),  "caps are sorted")

def test_s006_registry_statistics() -> None:
    _section("[S006] EngineeringWorkerRegistry — statistics")
    reg = EngineeringWorkerRegistry()
    s   = reg.statistics()
    _assert(s["total_registered"] == 0, "total 0")
    _assert(s["available"]        == 0, "available 0")
    _assert(s["busy"]             == 0, "busy 0")
    _assert(s["unavailable"]      == 0, "unavailable 0")
    _assert(s["capability_count"] == 0, "caps 0")

    w = _worker("W", "worker-local-stat01")
    reg.register(w)
    s2 = reg.statistics()
    _assert(s2["total_registered"] == 1, "total 1")
    _assert(s2["available"]        == 1, "available 1")

def test_s006_registry_snapshot_from_registry() -> None:
    _section("[S006] EngineeringWorkerRegistry.snapshot()")
    reg = EngineeringWorkerRegistry()
    snap = reg.snapshot()
    _assert(isinstance(snap, RegistrySnapshot),      "returns RegistrySnapshot")
    _assert(snap.status == RegistryStatus.EMPTY,     "EMPTY snap")
    _assert(snap.total_registered == 0,              "total 0")

    w1 = _worker("W1", "worker-local-sn01", caps=("engineering",))
    w2 = _worker("W2", "worker-local-sn02", caps=("testing",))
    reg.register(w1); reg.register(w2)
    w1.accept_session(_sess())
    snap2 = reg.snapshot()
    _assert(snap2.status == RegistryStatus.ACTIVE,   "ACTIVE snap")
    _assert(snap2.total_registered == 2,             "total 2")
    _assert(snap2.available_count  == 1,             "available 1")
    _assert(snap2.busy_count       == 1,             "busy 1")
    _assert("worker-local-sn01" in snap2.worker_ids, "sn01 in worker_ids")
    _assert("worker-local-sn02" in snap2.worker_ids, "sn02 in worker_ids")
    _assert("engineering" in snap2.capabilities,     "engineering in caps")
    _assert("testing"     in snap2.capabilities,     "testing in caps")

def test_s006_registry_snapshot_independence() -> None:
    _section("[S006] EngineeringWorkerRegistry — snapshot independence")
    reg  = EngineeringWorkerRegistry()
    w    = _worker("W", "worker-local-si99")
    reg.register(w)
    snap = reg.snapshot()
    _assert(snap.total_registered == 1, "snap total 1 before mutation")

    # Mutate registry
    reg.register(_worker("W2", "worker-local-si98"))
    _assert(snap.total_registered == 1, "snap unaffected after registry mutation")
    _assert(reg.size == 2,             "registry is now 2")

def test_s006_registry_repr() -> None:
    _section("[S006] EngineeringWorkerRegistry — repr")
    reg = EngineeringWorkerRegistry()
    r   = repr(reg)
    _assert("EngineeringWorkerRegistry" in r, "class name")
    _assert("EMPTY"                     in r, "status")
    _assert("total=0"                   in r, "total")


# ===========================================================================
# ── SPRINT 006 — Coordinator integration ───────────────────────────────────
# ===========================================================================

def test_s006_coordinator_owns_registry() -> None:
    _section("[S006] Coordinator — owns registry")
    c = _coord()
    _assert(isinstance(c.registry, EngineeringWorkerRegistry), "registry type")
    _assert(c.registry is not c.queue,      "registry ≠ queue")
    _assert(c.registry is not c.dispatcher, "registry ≠ dispatcher")
    _assert(c.registry is not c.worker,     "registry ≠ worker")

def test_s006_coordinator_default_worker_registered() -> None:
    _section("[S006] Coordinator — default worker auto-registered")
    c = _coord()
    _assert(c.registry.size == 1,                    "1 worker registered on init")
    _assert(c.registry.status() == RegistryStatus.ACTIVE, "registry ACTIVE")
    _assert(c.registry.contains(c.worker.worker_id()), "default worker in registry")

def test_s006_coordinator_registry_snapshot() -> None:
    _section("[S006] Coordinator.registry_snapshot()")
    c    = _coord()
    snap = c.registry_snapshot()
    _assert(isinstance(snap, RegistrySnapshot),    "returns RegistrySnapshot")
    _assert(snap.status == RegistryStatus.ACTIVE,  "ACTIVE")
    _assert(snap.total_registered == 1,            "1 worker")
    _assert(snap.available_count  == 1,            "1 available")

def test_s006_coordinator_registry_statistics() -> None:
    _section("[S006] Coordinator.registry_statistics()")
    c     = _coord()
    stats = c.registry_statistics()
    _assert(isinstance(stats, dict),          "returns dict")
    _assert(stats["total_registered"] == 1,   "total 1")
    _assert(stats["available"]        == 1,   "available 1")
    _assert(stats["busy"]             == 0,   "busy 0")

def test_s006_coordinator_register_worker() -> None:
    _section("[S006] Coordinator.register_worker()")
    c  = _coord()
    w2 = _worker("Extra", "worker-local-extra01")
    wid = c.register_worker(w2)
    _assert(wid == "worker-local-extra01",  "returns worker_id")
    _assert(c.registry.size == 2,           "registry has 2 workers")
    _assert(c.registry.contains(wid),       "extra worker in registry")

def test_s006_coordinator_unregister_worker() -> None:
    _section("[S006] Coordinator.unregister_worker()")
    c  = _coord()
    w2 = _worker("Extra", "worker-local-unreg01")
    c.register_worker(w2)
    _assert(c.registry.size == 2, "2 workers before unregister")
    removed = c.unregister_worker("worker-local-unreg01")
    _assert(removed,              "returns True")
    _assert(c.registry.size == 1, "1 worker after unregister")

def test_s006_coordinator_registry_reflects_worker_state() -> None:
    _section("[S006] Coordinator registry reflects live worker state")
    c = _coord()
    _assert(c.registry.available_count == 1, "1 available before process")
    c.submit(_req("State check"))
    c.process_next()
    # After processing, worker should be COMPLETED then auto-cleared
    _assert(c.registry.available_count == 1, "1 available after process")

def test_s006_coordinator_registry_capabilities() -> None:
    _section("[S006] Coordinator registry — capabilities")
    c = _coord()
    caps = c.registry.all_capabilities()
    _assert("engineering" in caps, "engineering capability registered")

def test_s006_coordinator_describe_includes_registry() -> None:
    _section("[S006] Coordinator.describe() — registry info")
    c = _coord()
    d = c.describe()
    _assert("registry"  in d,      "registry in describe()")
    _assert("018.006"   in d["version"], "version 018.006")

def test_s006_coordinator_registry_workers_by_capability() -> None:
    _section("[S006] Coordinator registry — workers_by_capability")
    c      = _coord()
    result = c.registry.workers_by_capability("engineering")
    _assert(len(result) == 1,                           "1 engineering worker")
    _assert(result[0].worker_id() == c.worker.worker_id(), "it's the coordinator's worker")

def test_s006_coordinator_process_all_registry_consistent() -> None:
    _section("[S006] Coordinator — registry consistent across process_all")
    c = _coord()
    for i in range(5): c.submit(_req(f"Batch {i}"))
    results = c.process_all()
    _assert(len(results) == 5,                          "5 results")
    _assert(all(r.succeeded for r in results),          "all succeeded")
    # Registry should still have 1 worker, available
    _assert(c.registry.size == 1,                       "registry size unchanged")
    _assert(c.registry.available_count == 1,            "worker available after batch")


# ===========================================================================
# ── SPRINT 006 — Public API surface ────────────────────────────────────────
# ===========================================================================

def test_s006_public_api_surface() -> None:
    _section("[S006] Public API surface — __init__ exports")
    import core.engineering.coordinator as pkg
    expected = [
        "EngineeringCoordinator","EngineeringRequest","EngineeringResult",
        "EngineeringStatus","CoordinatorConfig","CoordinatorEvent",
        "EngineeringStage","EngineeringSession","CoordinatorEventLog","SessionEvent",
        "EngineeringQueue","QueueStatus","QueueSnapshot",
        "EngineeringDispatcher","DispatchStatus","DispatchRecord","DispatchPolicy",
        "EngineeringWorker","LocalEngineeringWorker","DefaultEngineeringWorker",
        "WorkerStatus","WorkerRecord",
        "EngineeringWorkerRegistry","RegistryStatus","RegistrySnapshot",
    ]
    for name in expected:
        _assert(hasattr(pkg, name), f"{name} exported")
    _assert(len(pkg.__all__) == 25, "__all__ has 25 entries")

def test_s006_backward_compat_full() -> None:
    _section("[S006] Backwards compatibility — all Sprint 001-005 APIs work")
    c = _coord(debugger=_StubDebugger())

    # S001: coordinate
    r1 = c.coordinate(_req("S001"))
    _assert(r1.succeeded, "S001 coordinate")

    # S002: session, timeline
    _assert(r1.has_session,         "S002 session")
    _assert(r1.has_timeline,        "S002 timeline")
    _assert(r1.has_stage_durations, "S002 stage_durations")

    # S003: queue
    pos = c.submit(_req("S003"))
    _assert(pos >= 1, "S003 submit")
    r2 = c.process_next()
    _assert(r2.has_queue_position, "S003 queue_position")
    _assert(r2.has_queue_snapshot, "S003 queue_snapshot")

    # S004: dispatch
    _assert(r2.has_dispatch_record, "S004 dispatch_record")

    # S005: worker
    _assert(r2.has_worker_id,     "S005 worker_id")
    _assert(r2.has_worker_status, "S005 worker_status")
    _assert(isinstance(c.worker_record(), WorkerRecord), "S005 worker_record")

    # S006: registry
    _assert(isinstance(c.registry, EngineeringWorkerRegistry), "S006 registry")
    _assert(isinstance(c.registry_snapshot(), RegistrySnapshot), "S006 snapshot")
    _assert("total_registered" in c.registry_statistics(),       "S006 statistics")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("\n" + "=" * 60)
    print("  Genesis-018 Sprint 006 — Engineering Coordinator Tests")
    print("=" * 60)

    test_regression_s001_s005()

    test_s006_registry_status_values()
    test_s006_registry_status_properties()
    test_s006_registry_snapshot_construction()
    test_s006_registry_snapshot_empty()
    test_s006_registry_snapshot_all_busy()
    test_s006_registry_snapshot_immutability()
    test_s006_registry_snapshot_validation()
    test_s006_registry_snapshot_repr()
    test_s006_registry_initial_state()
    test_s006_registry_register()
    test_s006_registry_register_multiple()
    test_s006_registry_register_type_safety()
    test_s006_registry_register_duplicate()
    test_s006_registry_unregister()
    test_s006_registry_unregister_type_safety()
    test_s006_registry_replace()
    test_s006_registry_clear()
    test_s006_registry_get()
    test_s006_registry_get_type_safety()
    test_s006_registry_all_workers_order()
    test_s006_registry_all_workers_snapshot_independence()
    test_s006_registry_available_workers()
    test_s006_registry_busy_workers()
    test_s006_registry_unavailable_workers()
    test_s006_registry_workers_by_capability()
    test_s006_registry_workers_by_capability_type_safety()
    test_s006_registry_available_by_capability()
    test_s006_registry_first_available()
    test_s006_registry_status_transitions()
    test_s006_registry_all_capabilities()
    test_s006_registry_statistics()
    test_s006_registry_snapshot_from_registry()
    test_s006_registry_snapshot_independence()
    test_s006_registry_repr()
    test_s006_coordinator_owns_registry()
    test_s006_coordinator_default_worker_registered()
    test_s006_coordinator_registry_snapshot()
    test_s006_coordinator_registry_statistics()
    test_s006_coordinator_register_worker()
    test_s006_coordinator_unregister_worker()
    test_s006_coordinator_registry_reflects_worker_state()
    test_s006_coordinator_registry_capabilities()
    test_s006_coordinator_describe_includes_registry()
    test_s006_coordinator_registry_workers_by_capability()
    test_s006_coordinator_process_all_registry_consistent()
    test_s006_public_api_surface()
    test_s006_backward_compat_full()

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