# Genesis-021 — Worker Architecture

**Frozen:** Genesis-021 Sprint-006  
**Total tests:** 1,652 passing, 33 skipped  
**Package:** `core/workers/`

---

## Overview

The Worker subsystem is the operating system for Jarvis autonomous agents.
It provides a modular, extensible framework for delegating engineering tasks
to specialised workers that inspect, plan, and recommend — but never act
without human approval.

### Core principles

- **Read-only by default.** Workers observe and recommend. They never modify
  the repository, write to memory, or call external services.
- **Human approval required.** Every `WorkerResult` carries `requires_approval=True`
  unless explicitly overridden.
- **No AI calls.** All workers in Genesis-021 are fully deterministic.
  AI-powered workers are a future capability that plugs into the same framework.
- **Workers are independent.** Workers never reference each other directly.
  Communication happens only through `WorkerTask` payloads and `WorkerResult` data.
- **Plug-and-play.** Registering a new worker requires implementing one class
  and calling `manager.register()`. No framework changes needed.

---

## Package structure

```
core/workers/
    __init__.py          — package entry point
    exceptions.py        — WorkerError hierarchy
    models.py            — WorkerTask, WorkerResult, WorkerStatus
    base.py              — Worker ABC (the interface every worker implements)
    registry.py          — WorkerRegistry (catalogue of registered workers)
    manager.py           — WorkerManager (execution, discovery, lifecycle)
    orchestrator.py      — WorkerOrchestrator (routes tasks, never raises)
    coordinator.py       — WorkerCoordinator (multi-worker workflows)
    worker_context.py    — WorkerContext (shared state, TTL-based reuse)
    engineering_worker.py — EngineeringWorker (repository analysis)
    planning_worker.py   — PlanningWorker (goal-aware plan generation)
```

---

## Component relationships

```
┌─────────────────────────────────────────────────────────┐
│                    External callers                      │
│              (Agent, Desktop, future APIs)               │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────▼────────────┐
          │   WorkerOrchestrator   │  Single task → single worker
          │   WorkerCoordinator    │  Single task → multi-worker workflow
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │     WorkerManager      │  Owns registry, executes, tracks status
          │     WorkerContext      │  Shared state, TTL reuse, invalidation
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │    WorkerRegistry      │  Catalogue of registered Worker instances
          └───────────┬────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  EngineeringWorker  PlanningWorker  [future workers]
  (inspect)          (plan)          (debug, review, test...)
```

---

## Sequence diagrams

### Single task via Orchestrator

```
Caller          Orchestrator       Manager          Worker
  │                  │                │                │
  │─── run(task) ───►│                │                │
  │                  │─ select_worker(task) ──────────►│
  │                  │◄── Worker ─────────────────────-│
  │                  │─ execute(name, task) ──────────►│
  │                  │                │─── validate() ►│
  │                  │                │◄── True ───────│
  │                  │                │─── execute() ──►│
  │                  │                │◄── WorkerResult─│
  │                  │◄── WorkerResult────────────────-│
  │◄── WorkerResult ─│                │                │
```

### Multi-worker workflow via Coordinator

```
Caller       Coordinator      Context       Manager      Worker1    Worker2
  │               │               │             │            │          │
  │── run(task) ──►│               │             │            │          │
  │               │─ workflow_for(type) ──────────────────────────────►│
  │               │◄── ["worker1","worker2"] ──────────────────────────│
  │               │               │             │            │          │
  │               │─ context.get("worker1") ──►│            │          │
  │               │◄── None (no cache) ────────│            │          │
  │               │─────────────────── execute("worker1", task) ──────►│
  │               │◄────────────────── WorkerResult ───────────────────│
  │               │─ context.store("worker1", result) ────►│            │
  │               │─ merge_context(result, task) ──────────────────────►│
  │               │               │             │            │          │
  │               │─ context.get("worker2") ──►│            │          │
  │               │◄── None (no cache) ────────│            │          │
  │               │─────────────────── execute("worker2", task) ───────────────►│
  │               │◄────────────────── WorkerResult ────────────────────────────│
  │               │─ context.store("worker2", result) ────►│            │          │
  │               │─ _aggregate(all results) ──────────────────────────│          │
  │◄── WorkerResult (coordinator) ─────────────────────────────────────│          │
```

### Context hit (second run skips re-execution)

```
Coordinator      Context       Manager      Worker
     │               │             │            │
     │─ context.get("worker1") ──►│            │
     │◄── WorkerResult (cached) ──│            │
     │                             │            │
     │         [Worker never called — result reused]
     │
     │─ context.store() skipped (already stored)
```

---

## Public API

### WorkerTask

```python
WorkerTask(
    task_type: str,              # "analyse_repository", "plan_implementation"
    payload:   dict = {},        # task-specific data
    task_id:   str  = uuid4(),   # auto-generated
    requester: str  = "system",
    priority:  int  = 5,         # 1 = highest
    metadata:  dict = {},
)
```

### WorkerResult

```python
WorkerResult(
    task_id:           str,
    worker_name:       str,
    success:           bool,
    observations:      tuple[str, ...] = (),    # human-readable findings
    recommendations:   tuple[str, ...] = (),    # what to do next
    requires_approval: bool            = True,  # ALWAYS True for safe workers
    error:             str             = "",
    data:              dict            = {},    # structured, machine-readable
)

WorkerResult.failure(task_id, worker_name, error)  # convenience constructor
```

### WorkerStatus

```python
WorkerStatus.IDLE       # ready
WorkerStatus.RUNNING    # executing
WorkerStatus.COMPLETED  # last task succeeded
WorkerStatus.FAILED     # last task failed
WorkerStatus.CANCELLED  # cancelled mid-run

status.is_busy       # True only when RUNNING
status.is_available  # True when can accept new tasks
```

### WorkerManager

```python
manager = WorkerManager()

manager.register(worker)                          # add worker
manager.unregister(name)                          # remove worker
manager.execute(name, task)       → WorkerResult  # run by name
manager.execute_for_type(type, task) → WorkerResult # run first capable
manager.cancel(name)                              # cancel running
manager.status(name)              → WorkerStatus
manager.get_worker(name)          → Worker
manager.available_workers()       → list[Worker]
manager.workers_for(task_type)    → list[Worker]
manager.has_worker(name)          → bool
manager.worker_count()            → int
manager.summary()                 → dict
```

### WorkerOrchestrator

```python
orch = WorkerOrchestrator(manager)

orch.run(task)                    → WorkerResult  # never raises
orch.run_named(name, task)        → WorkerResult  # never raises
orch.available_for(task_type)     → bool
orch.select_worker(task)          → Worker | None
orch.registered_task_types()      → list[str]
orch.summary()                    → dict
```

### WorkerCoordinator

```python
coord = WorkerCoordinator(manager)

coord.run(task)                              → WorkerResult  # never raises
coord.register_workflow(task_type, [names])  # add/replace workflow
coord.has_workflow(task_type)                → bool
coord.workflow_for(task_type)                → list[str]
coord.available_workflows()                  → list[str]
coord.merge_context(result, task)            → WorkerTask
coord.context                                → WorkerContext
coord.summary()                              → dict
```

### WorkerContext

```python
ctx = WorkerContext(default_ttl=300)

ctx.store(worker_name, payload, result, ttl_seconds=None)
ctx.get(worker_name, payload)         → WorkerResult | None
ctx.has(worker_name, payload)         → bool
ctx.invalidate(worker_name)           → int  # entries removed
ctx.invalidate_all()                  → int
ctx.get_data(worker_name, payload)    → dict
ctx.set_shared(key, value)
ctx.get_shared(key, default=None)     → Any
ctx.has_shared(key)                   → bool
ctx.entry_count()                     → int
ctx.valid_entry_count()               → int
ctx.summary()                         → dict
```

---

## Default workflows (WorkerCoordinator)

| task_type | Workers executed (in order) |
|---|---|
| `engineering_plan` | `planning` → `engineering` |
| `plan_implementation` | `planning` |
| `analyse_repository` | `engineering` |

Add new workflows without changing the framework:
```python
coordinator.register_workflow("debug_and_plan", ["debug", "planning"])
```

---

## Built-in workers

### EngineeringWorker

**name:** `engineering`  
**capability:** `analyse_repository`  
**payload:** `{"root_path": "/optional/path"}` (defaults to cwd)

Recursively scans the repository. Skips `.git`, `__pycache__`, `.venv`, etc.

**Result data:**
```python
{
    "python_file_count":  int,
    "test_file_count":    int,
    "total_file_count":   int,
    "package_count":      int,
    "packages":           list[str],
    "files_by_package":   dict[str, int],
    "largest_package":    str,
    "largest_pkg_count":  int,
    "python_files":       list[str],
    "test_files":         list[str],
}
```

### PlanningWorker

**name:** `planning`  
**capability:** `plan_implementation`  
**payload:** `{"goal": str, "context": str, "tags": list}`

Selects a template based on keywords in `goal`. Templates: `bug_fix`,
`refactor`, `architecture`, `new_feature`, `testing`, `documentation`, `general`.

**Result data:**
```python
{
    "goal":         str,
    "template":     str,    # template name
    "complexity":   str,    # "Low" / "Medium" / "High"
    "steps":        list[str],
    "step_count":   int,
    "dependencies": list[str],
    "risks":        list[str],
    "context":      str,
    "tags":         list,
}
```

---

## Exception hierarchy

```
WorkerError
    ├── WorkerNotFoundError       # lookup by name failed
    ├── WorkerAlreadyRegisteredError  # duplicate registration
    ├── WorkerNotReadyError       # worker is RUNNING, cannot accept task
    ├── WorkerCancelledError      # task was cancelled
    └── InvalidTaskError          # validate() returned False
```

**WorkerOrchestrator and WorkerCoordinator catch all exceptions and return
`WorkerResult.failure()` — they never re-raise.**

---

## How to build a new worker

### 1. Create the worker file

```python
# core/workers/my_worker.py

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask


class MyWorker(Worker):

    @property
    def name(self) -> str:
        return "my_worker"          # unique name — used as registry key

    @property
    def description(self) -> str:
        return "Does something useful."

    @property
    def capabilities(self) -> list[str]:
        return ["my_task_type"]     # task types this worker handles

    def validate(self, task: WorkerTask) -> bool:
        # Return False to reject the task before execute() is called
        return bool(task.payload.get("required_field"))

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)           # sets status to RUNNING

        try:
            # Do read-only work here
            value = task.payload.get("required_field")

            result = WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=(f"Found value: {value}",),
                recommendations=("Review the findings before proceeding.",),
                requires_approval=True,   # ALWAYS True for safe workers
                data={"value": value},    # structured for downstream workers
            )
            return self._succeed(result)  # sets status to COMPLETED

        except Exception as exc:
            return self._fail(task.task_id, str(exc))  # sets status to FAILED
```

### 2. Register with the manager

```python
from core.workers.manager import WorkerManager
from core.workers.my_worker import MyWorker

manager = WorkerManager()
manager.register(MyWorker())
```

### 3. Execute via orchestrator

```python
from core.workers.orchestrator import WorkerOrchestrator
from core.workers.models import WorkerTask

orch = WorkerOrchestrator(manager)
result = orch.run(WorkerTask(
    task_type="my_task_type",
    payload={"required_field": "some value"},
))

print(result.success)          # True
print(result.observations)     # ("Found value: some value",)
print(result.data["value"])    # "some value"
```

### 4. Add to a workflow (optional)

```python
from core.workers.coordinator import WorkerCoordinator

coordinator = WorkerCoordinator(manager)
coordinator.register_workflow(
    "my_workflow",
    ["planning", "my_worker"]   # planning runs first, output flows in
)
```

### 5. Write tests

```python
def test_my_worker_registers():
    m = WorkerManager()
    m.register(MyWorker())
    assert m.has_worker("my_worker")

def test_my_worker_executes():
    task = WorkerTask("my_task_type", payload={"required_field": "x"})
    result = MyWorker().execute(task)
    assert result.success
    assert result.requires_approval

def test_my_worker_validate_rejects_empty():
    task = WorkerTask("my_task_type", payload={})
    assert not MyWorker().validate(task)
```

### Rules for new workers

| Rule | Why |
|---|---|
| `requires_approval=True` always | Human in the loop |
| Never call `os.system()`, `subprocess`, Git | Read-only constraint |
| Never import KnowledgeEngine | Workers are memory-agnostic |
| Never import other Workers | Workers are independent |
| Always implement `validate()` | Fail fast before expensive work |
| Use `_begin()` / `_succeed()` / `_fail()` | Consistent status tracking |
| Populate `data` dict as well as `observations` | Future workers need structured data |

---

## Developer notes

### Why WorkerOrchestrator AND WorkerCoordinator?

`WorkerOrchestrator` routes one task to one worker. It is a safe, never-raising
wrapper around `WorkerManager.execute_for_type()`.

`WorkerCoordinator` executes a sequence of workers for one high-level task.
It owns a `WorkerContext` for result reuse and cross-worker data sharing.

Use `WorkerOrchestrator` for simple single-worker calls.
Use `WorkerCoordinator` for multi-step engineering workflows.

### Why does Coordinator rewrite task_type per worker?

Each worker's `validate()` checks `task.task_type in self.capabilities`.
The workflow task_type (`"engineering_plan"`) is the coordinator's concern —
workers only understand their own types (`"plan_implementation"`, `"analyse_repository"`).
The coordinator rewrites `task_type` to `worker.capabilities[0]` per step.

### WorkerContext TTL

Default TTL is 300 seconds (5 minutes). A TTL of 0 means never expires.
Expired entries are lazily removed on `get()` / `has()` access.
Explicit invalidation via `context.invalidate(worker_name)` forces re-execution.

### WorkerContext key generation

Keys are `"{worker_name}:{sha256(sorted_json(payload))[:16]}"`.
Sort-keyed JSON serialisation means `{"a":1,"b":2}` and `{"b":2,"a":1}`
produce the same key. Payloads with non-serialisable values fall back to `str()`.

### Adding AI to workers (future)

The Worker ABC has no AI dependency. To build an AI-powered worker:

```python
class AIReviewWorker(Worker):
    def __init__(self, ai_provider):
        super().__init__()
        self._ai = ai_provider   # injected, not imported globally

    def execute(self, task):
        self._begin(task)
        response = self._ai.ask(task.payload.get("prompt"))
        result = WorkerResult(...)
        return self._succeed(result)
```

No framework changes needed. The Worker Framework is provider-agnostic.

---

## Genesis-021 sprint handover

| Sprint | Deliverable | Tests |
|---|---|---|
| 001 | Worker Framework (base, registry, manager, models, exceptions) | 102 |
| 002 | EngineeringWorker — read-only repository analysis | 56 |
| 003 | WorkerOrchestrator — safe task routing, never raises | 43 |
| 004 | PlanningWorker — goal-aware deterministic planning | 80 |
| 005 | WorkerCoordinator — multi-worker sequential workflows | 55 |
| 006 | WorkerContext — shared state, TTL reuse, invalidation | 56 |
| **Total** | | **392** |

**Full regression suite:** 1,652 passing, 33 skipped, 0 failed.

### What Genesis-022 should NOT start with

- Do not add AI to workers until the deterministic framework has been used in production.
- Do not add parallelism until sequential workflows prove insufficient.
- Do not add persistence to WorkerContext until in-memory proves insufficient.

### What Genesis-022 could productively add

- `DebugWorker` — analyses error messages and stack traces deterministically.
- `ReviewWorker` — checks code against Engineering Academy principles.
- `TestWorker` — runs the test suite and reports results.
- `GitWorker` — reads Git log and diff (read-only). Human approves any commit.
- AI-powered worker variant once the framework is proven stable.

---

*Genesis-021 frozen. Worker OS complete. Human approval always required.*