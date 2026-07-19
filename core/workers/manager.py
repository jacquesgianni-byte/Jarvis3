"""
Jarvis Worker Manager (Genesis-021 Sprint-001)

Orchestrates worker registration, discovery, execution, and lifecycle.

The WorkerManager is the single entry point for the Worker subsystem.
It owns a WorkerRegistry and coordinates task routing.

Design constraints:
    - Manager contains NO worker-specific logic.
    - Manager never modifies the repository.
    - Manager never calls AI directly.
    - Human approval is always required for recommendations.
    - Workers are plug-and-play via the registry.

Owned by the Agent (future sprints) alongside SessionContext, Timeline, etc.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.workers.base import Worker
from core.workers.exceptions import (
    InvalidTaskError,
    WorkerAlreadyRegisteredError,
    WorkerNotFoundError,
    WorkerNotReadyError,
)
from core.workers.models import WorkerResult, WorkerStatus, WorkerTask
from core.workers.registry import WorkerRegistry

logger = logging.getLogger(__name__)


class WorkerManager:
    """
    Orchestrates the Worker subsystem.

    Responsibilities:
        - Register and unregister workers
        - Discover workers by name or capability
        - Validate and execute tasks
        - Track worker status
        - Cancel running workers
        - Expose available workers

    Does NOT contain:
        - Worker-specific logic
        - AI calls
        - Repository modifications
        - Memory writes

    Public API:
        register(worker)               — add a worker to the registry
        unregister(name)               — remove a worker
        execute(name, task)            — run a task on a named worker
        execute_for_type(type, task)   — run on first capable worker
        cancel(name)                   — cancel a running worker
        status(name)                   — get worker status
        get_worker(name)               — fetch worker by name
        available_workers()            — workers ready to accept tasks
        workers_for(task_type)         — workers that handle a task type
        all_workers()                  — all registered workers
        has_worker(name)               — True if worker is registered
        worker_count()                 — number of registered workers
        summary()                      — debug dict
    """

    def __init__(self) -> None:
        self._registry = WorkerRegistry()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, worker: Worker) -> None:
        """
        Register a worker.

        Args:
            worker: Worker instance to register.

        Raises:
            WorkerAlreadyRegisteredError: If name already registered.
        """
        self._registry.register(worker)
        logger.info("[WORKERS] Registered: %s", worker.name)

    def unregister(self, name: str) -> None:
        """
        Remove a worker from the registry.

        Raises:
            WorkerNotFoundError: If worker not registered.
        """
        self._registry.unregister(name)
        logger.info("[WORKERS] Unregistered: %s", name)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, name: str, task: WorkerTask) -> WorkerResult:
        """
        Execute a task on a named worker.

        Validates the task first. If validation fails, raises
        InvalidTaskError without executing.

        Args:
            name: The registered worker name.
            task: The WorkerTask to execute.

        Returns:
            WorkerResult from the worker.

        Raises:
            WorkerNotFoundError:  If worker not registered.
            WorkerNotReadyError:  If worker is already running.
            InvalidTaskError:     If task fails validation.
        """
        worker = self._registry.get(name)

        if not worker.is_available:
            raise WorkerNotReadyError(
                f"Worker {name!r} is {worker.status().label()} "
                f"and cannot accept new tasks."
            )

        if not worker.validate(task):
            raise InvalidTaskError(
                f"Worker {name!r} rejected task: {task}"
            )

        logger.info("[WORKERS] Executing %r on worker %r", task.task_type, name)
        try:
            result = worker.execute(task)
            logger.info(
                "[WORKERS] %r completed: success=%s requires_approval=%s",
                name, result.success, result.requires_approval,
            )
            return result
        except Exception as exc:
            logger.exception("[WORKERS] %r raised during execute().", name)
            return WorkerResult.failure(task.task_id, name, str(exc))

    def execute_for_type(self, task_type: str, task: WorkerTask) -> WorkerResult:
        """
        Execute a task on the first available worker that handles task_type.

        Args:
            task_type: The task type to route.
            task:      The WorkerTask to execute.

        Returns:
            WorkerResult from the matched worker.

        Raises:
            WorkerNotFoundError: If no capable worker is registered.
            WorkerNotReadyError: If all capable workers are busy.
        """
        candidates = self._registry.workers_for(task_type)
        if not candidates:
            raise WorkerNotFoundError(
                f"No worker registered for task_type={task_type!r}."
            )

        for worker in candidates:
            if worker.is_available:
                return self.execute(worker.name, task)

        raise WorkerNotReadyError(
            f"All workers for task_type={task_type!r} are currently busy."
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def cancel(self, name: str) -> None:
        """
        Cancel a running worker.

        Args:
            name: The worker to cancel.

        Raises:
            WorkerNotFoundError: If worker not registered.
        """
        worker = self._registry.get(name)
        worker.cancel()
        logger.info("[WORKERS] Cancelled: %s", name)

    def status(self, name: str) -> WorkerStatus:
        """
        Return the current status of a worker.

        Raises:
            WorkerNotFoundError: If worker not registered.
        """
        return self._registry.get(name).status()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def get_worker(self, name: str) -> Worker:
        """Fetch a worker by name. Raises WorkerNotFoundError if missing."""
        return self._registry.get(name)

    def available_workers(self) -> list[Worker]:
        """Return all workers that are ready to accept tasks."""
        return [w for w in self._registry.all_workers() if w.is_available]

    def workers_for(self, task_type: str) -> list[Worker]:
        """Return workers that declare capability for a task_type."""
        return self._registry.workers_for(task_type)

    def all_workers(self) -> list[Worker]:
        """Return all registered workers."""
        return self._registry.all_workers()

    def has_worker(self, name: str) -> bool:
        """True if a worker with this name is registered."""
        return self._registry.has(name)

    def worker_count(self) -> int:
        """Number of registered workers."""
        return self._registry.count()

    def summary(self) -> dict:
        """Human-readable manager summary for debugging."""
        return {
            "worker_count": self._registry.count(),
            "available":    len(self.available_workers()),
            "registry":     self._registry.summary(),
        }