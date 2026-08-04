"""
Multi-Worker Collaboration — Models
Genesis-038 Sprint-001

Immutable structured models for worker collaboration.
WorkerAssignment is capability-based — never worker-name-based.
This ensures Genesis-040 external AI workers slot in without
any changes to the orchestration pipeline.

Design principle:
  WorkerCoordinator speaks worker NAMES.
  WorkPackage speaks CAPABILITIES.
  WorkCollaborationEngine bridges them.
  External AI workers register with capabilities — they're invisible
  to everything above WorkerManager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


class AssignmentStatus:
    PENDING  = "pending"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"
    SKIPPED  = "skipped"


@dataclass(frozen=True)
class WorkerCapability:
    """
    A resolved capability — maps a capability name to an available worker.

    Produced by WorkCollaborationEngine.resolve_capability().
    If no worker is registered for this capability, available=False.

    Genesis-040: external AI workers register capabilities identically
    to internal workers. resolve_capability() finds them automatically.
    """
    name:        str    # capability string e.g. "run_tests"
    worker_name: str    # resolved worker name, or "" if unavailable
    description: str    = ""
    available:   bool   = False


@dataclass(frozen=True)
class WorkerAssignment:
    """
    A single unit of work assigned to a specific worker.

    Assignments are capability-resolved — worker_id is the resolved
    worker name, not the capability string.

    can_parallelise: True if this assignment can run concurrently
    with other parallelisable assignments in the same plan group.
    """
    id:                  str
    worker_id:           str              # resolved worker name
    required_capability: str              # original capability string
    priority:            int              # 1 = highest
    dependencies:        tuple[str, ...]  # other assignment ids
    estimated_scope:     str              # "small"|"medium"|"large"
    status:              str              # AssignmentStatus constant
    work_package_id:     str
    can_parallelise:     bool
    review_required:     bool
    payload:             dict[str, Any]   = field(default_factory=dict)

    def with_status(self, status: str) -> "WorkerAssignment":
        """Return a new assignment with updated status (immutable update)."""
        return WorkerAssignment(
            id=self.id,
            worker_id=self.worker_id,
            required_capability=self.required_capability,
            priority=self.priority,
            dependencies=self.dependencies,
            estimated_scope=self.estimated_scope,
            status=status,
            work_package_id=self.work_package_id,
            can_parallelise=self.can_parallelise,
            review_required=self.review_required,
            payload=self.payload,
        )


@dataclass(frozen=True)
class WorkerPlan:
    """
    An ordered execution plan derived from a WorkPackage.
    Contains one or more WorkerAssignments.

    sequential_groups() partitions assignments into execution groups:
      - Assignments with no unresolved dependencies form group 0
      - Subsequent groups depend on prior groups completing
      - Within a group, parallelisable assignments can run concurrently
    """
    id:              str
    assignments:     tuple[WorkerAssignment, ...]
    genesis:         str
    work_package_id: str
    created_at:      str

    def sequential_groups(self) -> list[list[WorkerAssignment]]:
        """
        Partition assignments into ordered execution groups.
        Each group can begin only after the previous group completes.
        Within a group, can_parallelise=True assignments may run concurrently.
        """
        if not self.assignments:
            return []

        remaining     = list(self.assignments)
        completed_ids: set[str] = set()
        groups: list[list[WorkerAssignment]] = []

        while remaining:
            # Assignments whose dependencies are all completed
            ready = [
                a for a in remaining
                if all(dep in completed_ids for dep in a.dependencies)
            ]
            if not ready:
                # Dependency cycle or unresolvable — add rest as final group
                groups.append(remaining)
                break
            groups.append(ready)
            for a in ready:
                completed_ids.add(a.id)
                remaining.remove(a)

        return groups

    def to_text(self) -> str:
        sep   = "─" * 48
        lines = [
            f"Worker Plan: {self.id[:8]}",
            f"Genesis:     {self.genesis}",
            f"Assignments: {len(self.assignments)}",
            "",
        ]
        groups = self.sequential_groups()
        for gi, group in enumerate(groups, 1):
            parallel = any(a.can_parallelise for a in group)
            mode     = "parallel" if parallel and len(group) > 1 else "sequential"
            lines.append(f"Group {gi} [{mode}]:")
            for a in group:
                dep_note = f" (depends: {', '.join(a.dependencies[:2])})" if a.dependencies else ""
                lines.append(
                    f"  {a.priority}. {a.worker_id} "
                    f"← {a.required_capability}{dep_note}"
                )
            lines.append("")
        return "\n".join(lines)


@dataclass(frozen=True)
class CollaborationResult:
    """
    The outcome of executing a WorkerPlan.
    Aggregates results from all assignments.
    """
    plan:        WorkerPlan
    results:     dict[str, Any]   # assignment_id → WorkerResult data
    success:     bool
    completed:   int
    failed:      int
    skipped:     int
    error:       str = ""

    def to_text(self) -> str:
        status = "✅ Success" if self.success else "❌ Failed"
        lines = [
            f"Collaboration Result: {status}",
            f"Completed: {self.completed}  "
            f"Failed: {self.failed}  "
            f"Skipped: {self.skipped}",
        ]
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


def make_assignment(
    worker_id:           str,
    required_capability: str,
    work_package_id:     str = "",
    priority:            int = 5,
    dependencies:        tuple[str, ...] = (),
    estimated_scope:     str = "medium",
    can_parallelise:     bool = False,
    review_required:     bool = False,
    payload:             Optional[dict] = None,
) -> WorkerAssignment:
    """Factory for creating WorkerAssignment instances."""
    return WorkerAssignment(
        id=str(uuid4()),
        worker_id=worker_id,
        required_capability=required_capability,
        priority=priority,
        dependencies=dependencies,
        estimated_scope=estimated_scope,
        status=AssignmentStatus.PENDING,
        work_package_id=work_package_id,
        can_parallelise=can_parallelise,
        review_required=review_required,
        payload=payload or {},
    )
