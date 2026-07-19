"""
Jarvis Worker Coordinator (Genesis-021 Sprint-005)

Executes simple multi-worker workflows sequentially.

Responsibilities:
    - Accept a high-level WorkerTask
    - Look up the workflow for that task_type in the registry
    - Execute each worker in sequence via WorkerManager
    - Pass structured output between workers via merge_context()
    - Stop on first failure and return a structured failure result
    - Aggregate all outputs into a single WorkerResult

Constraints:
    - No AI calls
    - No repository modification
    - No memory integration
    - Sequential execution only (parallelism is future work)
    - requires_approval=True always
    - Never raises — always returns WorkerResult

Workflow registry:
    task_type → [worker_name_1, worker_name_2, ...]
    Add new workflows here without changing the public API.

Context passing:
    merge_context(previous_result, next_task) — generic helper
    Merges structured data from one result into the next task's payload.
    Workers remain completely independent; they never reference each other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from core.workers.manager import WorkerManager
from core.workers.models import WorkerResult, WorkerTask
from core.workers.worker_context import WorkerContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in workflow definitions
# task_type → ordered list of worker names
# ---------------------------------------------------------------------------

_DEFAULT_WORKFLOWS: dict[str, list[str]] = {
    # Plan the implementation then analyse the codebase
    "engineering_plan": ["planning", "engineering"],
    # Analyse only
    "analyse_repository": ["engineering"],
    # Plan only
    "plan_implementation": ["planning"],
}


# ---------------------------------------------------------------------------
# Workflow step result (internal)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepResult:
    """Internal record of a single workflow step outcome."""
    worker_name: str
    result:      WorkerResult
    step_index:  int


# ---------------------------------------------------------------------------
# WorkerCoordinator
# ---------------------------------------------------------------------------

class WorkerCoordinator:
    """
    Executes multi-worker workflows sequentially.

    Owns a workflow registry that maps task types to ordered lists of
    worker names. Executes each worker in order, passing context between
    them via merge_context(). Aggregates all outputs into one result.

    Workers remain completely independent — they communicate only through
    WorkerTask payloads and WorkerResult data, never directly.

    Public API:
        run(task)                            — execute workflow, never raises
        register_workflow(task_type, names)  — add/replace a workflow
        has_workflow(task_type)              — True if workflow registered
        workflow_for(task_type)              — worker name list or []
        available_workflows()                — all registered task types
        summary()                            — debug dict
    """

    def __init__(self, manager: WorkerManager) -> None:
        self._manager = manager
        self._workflows: dict[str, list[str]] = dict(_DEFAULT_WORKFLOWS)
        self.context = WorkerContext()

    # ------------------------------------------------------------------
    # Workflow registry
    # ------------------------------------------------------------------

    def register_workflow(
        self, task_type: str, worker_names: list[str]
    ) -> None:
        """
        Register or replace a workflow.

        Args:
            task_type:    The task_type that triggers this workflow.
            worker_names: Ordered list of worker names to execute.
        """
        if not task_type or not worker_names:
            raise ValueError(
                "task_type and worker_names must be non-empty."
            )
        self._workflows[task_type] = list(worker_names)
        logger.info(
            "[COORDINATOR] Registered workflow %r → %s",
            task_type, worker_names,
        )

    def has_workflow(self, task_type: str) -> bool:
        """True if a workflow is registered for this task_type."""
        return task_type in self._workflows

    def workflow_for(self, task_type: str) -> list[str]:
        """Return the ordered worker name list, or [] if not registered."""
        return list(self._workflows.get(task_type, []))

    def available_workflows(self) -> list[str]:
        """Return all registered workflow task types."""
        return list(self._workflows.keys())

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, task: WorkerTask) -> WorkerResult:
        """
        Execute a workflow for the given task.

        Never raises. Returns WorkerResult.failure() if:
            - No workflow is registered for the task_type
            - A required worker is not registered
            - Any worker returns success=False
            - An unexpected exception occurs

        Args:
            task: The high-level WorkerTask to coordinate.

        Returns:
            A single aggregated WorkerResult.
        """
        logger.info(
            "[COORDINATOR] Starting workflow for task_type=%r id=%s",
            task.task_type, task.task_id[:8],
        )
        # Fresh context per run() call unless the caller has pre-populated it.
        # Callers may reuse context across runs by calling run() without reset.

        workflow = self.workflow_for(task.task_type)
        if not workflow:
            reason = (
                f"No workflow registered for task_type={task.task_type!r}. "
                f"Available: {self.available_workflows()}"
            )
            logger.warning("[COORDINATOR] %s", reason)
            return WorkerResult.failure(task.task_id, "coordinator", reason)

        step_results: list[StepResult] = []
        current_task = task

        for index, worker_name in enumerate(workflow):
            if not self._manager.has_worker(worker_name):
                reason = (
                    f"Workflow step {index + 1}: worker {worker_name!r} "
                    f"is not registered."
                )
                logger.warning("[COORDINATOR] %s", reason)
                return self._failure(task, reason, step_results)

            logger.info(
                "[COORDINATOR] Step %d/%d: executing %r",
                index + 1, len(workflow), worker_name,
            )

            try:
                # Rewrite task_type to the worker's primary capability so
                # validate() passes. The workflow task_type is the
                # coordinator's concern; each worker sees its own type.
                worker = self._manager.get_worker(worker_name)
                step_task = WorkerTask(
                    task_type=worker.capabilities[0],
                    payload=current_task.payload,
                    task_id=current_task.task_id,
                    created_at=current_task.created_at,
                    requester=current_task.requester,
                    priority=current_task.priority,
                    metadata=current_task.metadata,
                )
                # Check context before executing — reuse if valid
                cached = self.context.get(worker_name, current_task.payload)
                if cached is not None:
                    logger.info(
                        "[COORDINATOR] Context hit for worker=%r — skipping execution.",
                        worker_name,
                    )
                    result = cached
                else:
                    result = self._manager.execute(worker_name, step_task)
                    if result.success:
                        self.context.store(worker_name, current_task.payload, result)
            except Exception as exc:
                reason = (
                    f"Workflow step {index + 1} ({worker_name!r}) "
                    f"raised: {exc}"
                )
                logger.exception("[COORDINATOR] %s", reason)
                return self._failure(task, reason, step_results)

            step_results.append(StepResult(
                worker_name=worker_name,
                result=result,
                step_index=index,
            ))

            if not result.success:
                reason = (
                    f"Workflow stopped at step {index + 1} "
                    f"({worker_name!r}): {result.error}"
                )
                logger.warning("[COORDINATOR] %s", reason)
                return self._failure(task, reason, step_results)

            # Merge context for the next step
            if index + 1 < len(workflow):
                current_task = self.merge_context(result, current_task)

        logger.info(
            "[COORDINATOR] Workflow complete: %d/%d steps succeeded.",
            len(step_results), len(workflow),
        )
        return self._aggregate(task, workflow, step_results)

    # ------------------------------------------------------------------
    # Context passing
    # ------------------------------------------------------------------

    def merge_context(
        self, previous_result: WorkerResult, next_task: WorkerTask
    ) -> WorkerTask:
        """
        Merge structured data from a completed result into the next task.

        Generic — no worker-specific logic. Copies the previous result's
        data dict into the next task's payload under the key
        "previous_result_data". Workers may read this at their discretion.

        Also preserves fields the next worker may already expect
        (e.g. root_path stays in payload if already set).

        Args:
            previous_result: The WorkerResult just completed.
            next_task:       The task to pass to the next worker.

        Returns:
            A new WorkerTask with enriched payload.
        """
        merged_payload = dict(next_task.payload)
        merged_payload["previous_result_data"] = previous_result.data
        merged_payload["previous_worker"] = previous_result.worker_name

        return WorkerTask(
            task_type=next_task.task_type,
            payload=merged_payload,
            task_id=next_task.task_id,
            created_at=next_task.created_at,
            requester=next_task.requester,
            priority=next_task.priority,
            metadata=next_task.metadata,
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        original_task: WorkerTask,
        workflow: list[str],
        step_results: list[StepResult],
    ) -> WorkerResult:
        """Combine all step results into a single WorkerResult."""
        all_observations: list[str] = []
        all_recommendations: list[str] = []
        combined_data: dict[str, Any] = {
            "workflow":        original_task.task_type,
            "workers_executed": [s.worker_name for s in step_results],
            "steps_completed": len(step_results),
            "steps_total":     len(workflow),
            "results":         {},
        }

        for step in step_results:
            header = f"=== {step.worker_name.title()} Worker ==="
            all_observations.append(header)
            all_observations.extend(step.result.observations)
            all_recommendations.extend(step.result.recommendations)
            combined_data["results"][step.worker_name] = step.result.data

        return WorkerResult(
            task_id=original_task.task_id,
            worker_name="coordinator",
            success=True,
            observations=tuple(all_observations),
            recommendations=tuple(all_recommendations),
            requires_approval=True,
            data=combined_data,
        )

    def _failure(
        self,
        original_task: WorkerTask,
        reason: str,
        step_results: list[StepResult],
    ) -> WorkerResult:
        """Return a structured failure result with partial progress."""
        completed = [s.worker_name for s in step_results]
        return WorkerResult(
            task_id=original_task.task_id,
            worker_name="coordinator",
            success=False,
            error=reason,
            requires_approval=False,
            data={
                "workflow":         original_task.task_type,
                "workers_executed": completed,
                "steps_completed":  len(step_results),
                "partial_results":  {
                    s.worker_name: s.result.data for s in step_results
                },
            },
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Human-readable coordinator summary for debugging."""
        return {
            "registered_workflows": self.available_workflows(),
            "worker_count":         self._manager.worker_count(),
            "available_workers":    [
                w.name for w in self._manager.available_workers()
            ],
        }