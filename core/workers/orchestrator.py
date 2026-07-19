"""
Jarvis Worker Orchestrator (Genesis-021 Sprint-003)

A thin, safe routing layer over WorkerManager.

Responsibilities:
    - Accept a WorkerTask and route it to the right worker
    - Never raise exceptions — always return a WorkerResult
    - Select workers via an internal select_worker() method
      so future selection strategies (priority, load, capability
      scoring) can be added without changing the public interface

Constraints:
    - No AI calls
    - No repository modification
    - No memory integration
    - No desktop integration
    - Reuses existing Worker Framework unchanged

Public API:
    orchestrator.run(task)              — route and execute, never raises
    orchestrator.run_named(name, task)  — execute on a specific worker
    orchestrator.available_for(type)    — True if any worker can handle it
    orchestrator.select_worker(task)    — returns Worker or None
"""

from __future__ import annotations

import logging
from typing import Optional

from core.workers.base import Worker
from core.workers.manager import WorkerManager
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)


class WorkerOrchestrator:
    """
    Routes WorkerTasks to the appropriate registered worker.

    Always returns a WorkerResult — never raises. Structured failure
    results are returned when no worker is found or execution fails.

    Owns a reference to WorkerManager but does not replace it.
    The Manager remains the authoritative registry owner.
    """

    def __init__(self, manager: WorkerManager) -> None:
        self._manager = manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: WorkerTask) -> WorkerResult:
        """
        Route a task to the best available worker and execute it.

        Never raises. Returns WorkerResult.failure() if:
            - No worker is registered for the task type
            - All capable workers are busy
            - The worker raises an unexpected exception

        Args:
            task: The WorkerTask to execute.

        Returns:
            WorkerResult from the selected worker, or a failure result.
        """
        logger.info(
            "[ORCHESTRATOR] Routing task type=%r id=%s",
            task.task_type, task.task_id[:8],
        )

        worker = self.select_worker(task)

        if worker is None:
            candidates = self._manager.workers_for(task.task_type)
            if not candidates:
                reason = (
                    f"No worker registered for task_type={task.task_type!r}."
                )
            else:
                reason = (
                    f"All workers for task_type={task.task_type!r} "
                    f"are currently busy."
                )
            logger.warning("[ORCHESTRATOR] %s", reason)
            return WorkerResult.failure(task.task_id, "orchestrator", reason)

        logger.info(
            "[ORCHESTRATOR] Selected worker %r for task_type=%r",
            worker.name, task.task_type,
        )

        try:
            return self._manager.execute(worker.name, task)
        except Exception as exc:
            reason = f"Worker {worker.name!r} raised: {exc}"
            logger.exception("[ORCHESTRATOR] Execution error: %s", reason)
            return WorkerResult.failure(task.task_id, worker.name, reason)

    def run_named(self, name: str, task: WorkerTask) -> WorkerResult:
        """
        Execute a task on a specific named worker.

        Never raises. Returns WorkerResult.failure() if the worker
        does not exist, is busy, or raises during execution.

        Args:
            name: The registered worker name.
            task: The WorkerTask to execute.

        Returns:
            WorkerResult from the named worker, or a failure result.
        """
        logger.info(
            "[ORCHESTRATOR] Running named worker %r task=%r",
            name, task.task_type,
        )

        if not self._manager.has_worker(name):
            reason = f"Worker {name!r} is not registered."
            logger.warning("[ORCHESTRATOR] %s", reason)
            return WorkerResult.failure(task.task_id, name, reason)

        try:
            return self._manager.execute(name, task)
        except Exception as exc:
            reason = f"Worker {name!r} raised: {exc}"
            logger.exception("[ORCHESTRATOR] Named execution error: %s", reason)
            return WorkerResult.failure(task.task_id, name, reason)

    def available_for(self, task_type: str) -> bool:
        """
        Return True if at least one available worker handles task_type.

        Args:
            task_type: The task type string to check.
        """
        return any(
            w.is_available
            for w in self._manager.workers_for(task_type)
        )

    def select_worker(self, task: WorkerTask) -> Optional[Worker]:
        """
        Select the best available worker for a task.

        Current strategy: first available worker that declares the
        task_type in its capabilities, ordered by registration order.

        This method is intentionally separated from run() so future
        selection strategies (priority-based, load-aware, capability
        scoring) can be introduced here without changing the public
        interface.

        Args:
            task: The WorkerTask to find a worker for.

        Returns:
            A Worker instance, or None if no suitable worker is available.
        """
        candidates = self._manager.workers_for(task.task_type)
        for worker in candidates:
            if worker.is_available:
                return worker
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def registered_task_types(self) -> list[str]:
        """Return all task types covered by registered workers."""
        types: list[str] = []
        for worker in self._manager.all_workers():
            for cap in worker.capabilities:
                if cap not in types:
                    types.append(cap)
        return types

    def summary(self) -> dict:
        """Human-readable orchestrator summary for debugging."""
        return {
            "worker_count":       self._manager.worker_count(),
            "available_workers":  len(self._manager.available_workers()),
            "covered_task_types": self.registered_task_types(),
        }