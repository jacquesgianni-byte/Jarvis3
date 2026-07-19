"""
Jarvis Worker Base Interface (Genesis-021 Sprint-001)

Every Worker must implement this interface.

Design constraints:
    - Workers are read-only — they observe and recommend, never act.
    - Workers never modify the repository directly.
    - Workers never call the AI provider directly (Sprint-002+).
    - Workers never write to the KnowledgeEngine directly.
    - Human approval is always required before any recommendation
      is executed.
    - Workers must be independently registerable (plug-and-play).

Lifecycle:
    IDLE → execute(task) → RUNNING → COMPLETED / FAILED
    RUNNING → cancel() → CANCELLED → IDLE (via reset)

Future workers:
    EngineeringWorker, PlanningWorker, DebugWorker, ReviewWorker,
    DocumentationWorker, ResearchWorker, TestingWorker, GitWorker
    All inherit from Worker and plug into WorkerRegistry.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from core.workers.exceptions import WorkerNotReadyError
from core.workers.models import WorkerResult, WorkerStatus, WorkerTask

logger = logging.getLogger(__name__)


class Worker(ABC):
    """
    Abstract base class for all Jarvis Workers.

    Subclasses must implement:
        name          — unique worker identifier
        description   — human-readable description
        capabilities  — list of task_type strings this worker handles
        execute(task) — perform the task, return WorkerResult
        validate(task)— check task is valid before execution

    Subclasses may override:
        cancel()      — interrupt a running task
        on_reset()    — hook called when worker resets to IDLE
    """

    def __init__(self) -> None:
        self._status: WorkerStatus = WorkerStatus.IDLE
        self._current_task: Optional[WorkerTask] = None
        self._last_result: Optional[WorkerResult] = None
        self._cancelled: bool = False

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique worker name. Used as registry key."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this worker does."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """
        List of task_type strings this worker can handle.
        Used by WorkerManager to route tasks to the right worker.
        """
        ...

    @abstractmethod
    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Execute a task and return a WorkerResult.

        Implementations must:
            - Set _status to RUNNING at the start.
            - Set _status to COMPLETED or FAILED at the end.
            - Never modify the repository directly.
            - Return a WorkerResult with requires_approval=True
              for any recommendation that would change state.

        Args:
            task: The WorkerTask to execute.

        Returns:
            WorkerResult with observations and recommendations.
        """
        ...

    @abstractmethod
    def validate(self, task: WorkerTask) -> bool:
        """
        Check that a task is valid for this worker.

        Called by WorkerManager before execute(). If this returns
        False, the manager raises InvalidTaskError.

        Args:
            task: The WorkerTask to validate.

        Returns:
            True if the task is valid, False otherwise.
        """
        ...

    # ------------------------------------------------------------------
    # Concrete methods — shared across all workers
    # ------------------------------------------------------------------

    def cancel(self) -> None:
        """
        Request cancellation of the current task.

        Sets the cancellation flag. Workers should check
        self._cancelled periodically during long-running tasks.
        """
        if self._status == WorkerStatus.RUNNING:
            self._cancelled = True
            self._status = WorkerStatus.CANCELLED
            logger.info("[WORKER:%s] Cancelled.", self.name)
        else:
            logger.debug(
                "[WORKER:%s] cancel() called but status is %s.",
                self.name, self._status.label()
            )

    def status(self) -> WorkerStatus:
        """Return the current WorkerStatus."""
        return self._status

    def reset(self) -> None:
        """
        Reset the worker to IDLE state.

        Called by WorkerManager after a task completes or fails
        so the worker can accept new tasks.
        """
        self._status = WorkerStatus.IDLE
        self._current_task = None
        self._cancelled = False
        self.on_reset()

    def on_reset(self) -> None:
        """
        Hook called when the worker resets to IDLE.
        Override in subclasses for cleanup logic.
        """
        pass

    @property
    def last_result(self) -> Optional[WorkerResult]:
        """The result of the most recently completed task."""
        return self._last_result

    @property
    def is_available(self) -> bool:
        """True if the worker can accept a new task."""
        return self._status.is_available

    # ------------------------------------------------------------------
    # Protected helpers for subclass use
    # ------------------------------------------------------------------

    def _begin(self, task: WorkerTask) -> None:
        """Call at the start of execute() to set RUNNING state."""
        if not self._status.is_available:
            raise WorkerNotReadyError(
                f"Worker {self.name!r} is {self._status.label()} "
                f"and cannot accept new tasks."
            )
        self._current_task = task
        self._cancelled = False
        self._status = WorkerStatus.RUNNING
        logger.info("[WORKER:%s] Started task: %s", self.name, task)

    def _succeed(self, result: WorkerResult) -> WorkerResult:
        """Call at the end of execute() to record success."""
        self._status = WorkerStatus.COMPLETED
        self._last_result = result
        logger.info("[WORKER:%s] Completed: %s", self.name, result)
        return result

    def _fail(self, task_id: str, error: str) -> WorkerResult:
        """Call to record a failure and return a failure result."""
        self._status = WorkerStatus.FAILED
        result = WorkerResult.failure(task_id, self.name, error)
        self._last_result = result
        logger.error("[WORKER:%s] Failed: %s", self.name, error)
        return result

    def __str__(self) -> str:
        return f"Worker(name={self.name!r}, status={self._status.label()})"

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.name!r} "
            f"status={self._status.label()}>"
        )