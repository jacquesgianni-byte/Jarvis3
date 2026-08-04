"""
Multi-Worker Collaboration — Engine
Genesis-038 Sprint-001

WorkerCollaborationEngine sits between PlanningEngine and WorkerCoordinator.

Responsibilities:
  - Resolve WorkPackage capabilities to available workers
  - Build WorkerPlan (ordered WorkerAssignments)
  - Execute WorkerPlan via WorkerCoordinator (never directly)
  - Handle parallel groups by running multiple coordinator calls
  - Handle worker unavailability gracefully

Does NOT:
  - Modify WorkerCoordinator or WorkerManager
  - Know anything about AI vs internal workers
  - Store state
  - Call AI

Genesis-040 proof:
  When an external AI worker registers capability "implement_feature",
  resolve_capability() finds it automatically.
  WorkerCoordinator executes it identically to any internal worker.
  This engine requires zero changes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from core.collaboration.models import (
    AssignmentStatus,
    CollaborationResult,
    WorkerAssignment,
    WorkerCapability,
    WorkerPlan,
    make_assignment,
)

logger = logging.getLogger(__name__)

_COLLABORATION_TRIGGERS: frozenset[str] = frozenset({
    "assign workers",
    "collaborate",
    "run collaboration",
    "execute work plan",
    "assign work",
    "worker collaboration",
    "run worker plan",
    "execute plan",
    "dispatch workers",
})


class WorkerCollaborationEngine:
    """
    Capability-based multi-worker collaboration layer.

    Sits above WorkerCoordinator — never replaces it.
    WorkerCoordinator remains the single orchestration point.

    Public API:
        can_handle(utterance)            -> bool
        handle(utterance, work_package)  -> str
        resolve_capability(name)         -> WorkerCapability
        plan(work_package)               -> WorkerPlan
        execute(worker_plan)             -> CollaborationResult
        available_capabilities()         -> list[WorkerCapability]
    """

    def __init__(self, worker_manager, worker_coordinator) -> None:
        self._manager     = worker_manager
        self._coordinator = worker_coordinator

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        return utterance.strip().lower().rstrip("?!.") in _COLLABORATION_TRIGGERS

    def handle(self, utterance: str, work_package=None) -> str:
        if work_package is None:
            return "No work package provided. Use the Planning Engine first."
        plan   = self.plan(work_package)
        result = self.execute(plan)
        return plan.to_text() + "\n" + result.to_text()

    def resolve_capability(self, capability_name: str) -> WorkerCapability:
        """
        Resolve a capability name to an available worker.

        Genesis-040: external AI workers register capabilities identically
        to internal workers. This method finds them automatically.
        No special-casing for internal vs external.
        """
        try:
            workers = self._manager.workers_for(capability_name)
            available = [w for w in workers if w.is_available]
            if available:
                w = available[0]
                return WorkerCapability(
                    name=capability_name,
                    worker_name=w.name,
                    description=w.description,
                    available=True,
                )
            if workers:
                # Registered but busy
                return WorkerCapability(
                    name=capability_name,
                    worker_name=workers[0].name,
                    description=workers[0].description,
                    available=False,
                )
        except Exception:
            logger.debug("[COLLAB] resolve_capability failed for %r", capability_name)

        return WorkerCapability(
            name=capability_name,
            worker_name="",
            description="",
            available=False,
        )

    def available_capabilities(self) -> list[WorkerCapability]:
        """Return all capabilities exposed by registered workers."""
        seen: set[str] = set()
        result: list[WorkerCapability] = []
        try:
            for worker in self._manager.all_workers():
                for cap in worker.capabilities:
                    if cap not in seen:
                        seen.add(cap)
                        result.append(self.resolve_capability(cap))
        except Exception:
            logger.debug("[COLLAB] available_capabilities failed.")
        return result

    def plan(self, work_package) -> WorkerPlan:
        """
        Convert a WorkPackage into an ordered WorkerPlan.

        Resolves capability_required to an available worker.
        If the worker is unavailable, the assignment is still created
        with status=SKIPPED so the plan is complete and traceable.
        """
        pkg_id = getattr(work_package, "id", str(uuid4()))
        genesis = getattr(work_package, "genesis", "")
        capability = getattr(work_package, "capability_required", "")
        pkg_payload = {
            "description": getattr(work_package, "objective", ""),
            "work_package_id": pkg_id,
        }

        assignments: list[WorkerAssignment] = []

        resolved = self.resolve_capability(capability)

        if resolved.available:
            assignment = make_assignment(
                worker_id=resolved.worker_name,
                required_capability=capability,
                work_package_id=pkg_id,
                priority=getattr(work_package, "priority", 5),
                estimated_scope=getattr(work_package, "estimated_scope", "medium"),
                can_parallelise=False,
                review_required=bool(getattr(work_package, "review_requirements", ())),
                payload=pkg_payload,
            )
            assignments.append(assignment)
        else:
            # Unavailable — create skipped assignment for traceability
            assignment = make_assignment(
                worker_id=resolved.worker_name or f"<no worker for {capability}>",
                required_capability=capability,
                work_package_id=pkg_id,
                priority=getattr(work_package, "priority", 5),
                estimated_scope=getattr(work_package, "estimated_scope", "medium"),
                can_parallelise=False,
                review_required=False,
                payload=pkg_payload,
            )
            # Mark as skipped — capability unavailable
            assignments.append(assignment.with_status(AssignmentStatus.SKIPPED))
            logger.warning(
                "[COLLAB] Capability %r not available — assignment skipped.", capability
            )

        return WorkerPlan(
            id=str(uuid4()),
            assignments=tuple(assignments),
            genesis=genesis,
            work_package_id=pkg_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def execute(self, worker_plan: WorkerPlan) -> CollaborationResult:
        """
        Execute a WorkerPlan via WorkerCoordinator.

        Sequential groups run in order.
        Within a group, parallelisable assignments run via separate
        coordinator calls (coordinator is still the single executor).
        Never raises — always returns CollaborationResult.
        """
        all_results: dict[str, object] = {}
        completed = 0
        failed    = 0
        skipped   = 0
        error     = ""

        groups = worker_plan.sequential_groups()

        for group in groups:
            group_failed = False

            for assignment in group:
                # Skip pre-skipped assignments (unavailable workers)
                if assignment.status == AssignmentStatus.SKIPPED:
                    skipped += 1
                    all_results[assignment.id] = {
                        "status": AssignmentStatus.SKIPPED,
                        "reason": f"No worker available for capability: {assignment.required_capability}",
                    }
                    continue

                # Execute via WorkerCoordinator
                result = self._execute_assignment(assignment)
                all_results[assignment.id] = result.data if hasattr(result, "data") else {}

                if hasattr(result, "success") and result.success:
                    completed += 1
                else:
                    failed += 1
                    err = getattr(result, "error", "Unknown error")
                    error = error or err
                    group_failed = True
                    logger.warning(
                        "[COLLAB] Assignment %s failed: %s", assignment.id[:8], err
                    )

            # Stop sequential execution on group failure
            if group_failed:
                # Skip remaining groups
                remaining = sum(
                    len(g) for g in groups[groups.index(group) + 1:]
                    if groups.index(group) + 1 < len(groups)
                )
                skipped += remaining
                break

        success = failed == 0 and skipped == 0 or (failed == 0 and completed > 0)

        return CollaborationResult(
            plan=worker_plan,
            results=all_results,
            success=success,
            completed=completed,
            failed=failed,
            skipped=skipped,
            error=error,
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    def _execute_assignment(self, assignment: WorkerAssignment):
        """Execute a single assignment via WorkerCoordinator."""
        from core.workers.models import WorkerTask

        # Register a single-worker workflow for this assignment
        workflow_name = f"collab_{assignment.id[:8]}"
        try:
            self._coordinator.register_workflow(
                workflow_name, [assignment.worker_id]
            )
        except Exception:
            pass  # May already be registered

        task = WorkerTask(
            task_type=workflow_name,
            payload=dict(assignment.payload),
            requester="collaboration_engine",
        )

        try:
            return self._coordinator.run(task)
        except Exception as exc:
            logger.exception("[COLLAB] Assignment execution raised.")
            from core.workers.models import WorkerResult
            return WorkerResult.failure(task.task_id, "collaboration_engine", str(exc))
