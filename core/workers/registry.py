"""
Jarvis Worker Registry (Genesis-021 Sprint-001)

The registry is the source of truth for which workers exist.
WorkerManager uses it to discover and look up workers by name or capability.

Design:
    - Single registry per application (owned by WorkerManager).
    - Workers register by name — names must be unique.
    - Registry is read-heavy: lookups are O(1).
    - Registry never executes workers — that is WorkerManager's job.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.workers.exceptions import WorkerAlreadyRegisteredError, WorkerNotFoundError

if TYPE_CHECKING:
    from core.workers.base import Worker

logger = logging.getLogger(__name__)


class WorkerRegistry:
    """
    Maintains the catalogue of registered Workers.

    Workers register by name. The registry provides lookup by name
    and discovery by capability (task_type).

    Public API:
        register(worker)           — add a worker
        unregister(name)           — remove a worker
        get(name)                  — fetch by name (raises if missing)
        find(name)                 — fetch by name (returns None if missing)
        workers_for(task_type)     — find workers that handle a task type
        all_workers()              — all registered workers
        names()                    — all registered worker names
        has(name)                  — True if worker is registered
        count()                    — number of registered workers
    """

    def __init__(self) -> None:
        self._workers: dict[str, "Worker"] = {}

    def register(self, worker: "Worker") -> None:
        """
        Register a worker.

        Args:
            worker: The Worker instance to register.

        Raises:
            WorkerAlreadyRegisteredError: If a worker with the same
                name is already registered.
        """
        if worker.name in self._workers:
            raise WorkerAlreadyRegisteredError(
                f"Worker {worker.name!r} is already registered. "
                f"Use unregister() first to replace it."
            )
        self._workers[worker.name] = worker
        logger.info(
            "[REGISTRY] Registered worker: %r (capabilities: %s)",
            worker.name, worker.capabilities,
        )

    def unregister(self, name: str) -> None:
        """
        Remove a worker from the registry.

        Args:
            name: The worker name to remove.

        Raises:
            WorkerNotFoundError: If no worker with that name exists.
        """
        if name not in self._workers:
            raise WorkerNotFoundError(f"Worker {name!r} is not registered.")
        del self._workers[name]
        logger.info("[REGISTRY] Unregistered worker: %r", name)

    def get(self, name: str) -> "Worker":
        """
        Fetch a worker by name.

        Raises:
            WorkerNotFoundError: If no worker with that name exists.
        """
        if name not in self._workers:
            raise WorkerNotFoundError(
                f"Worker {name!r} is not registered. "
                f"Available: {list(self._workers)}"
            )
        return self._workers[name]

    def find(self, name: str) -> "Worker | None":
        """
        Fetch a worker by name, returning None if not found.
        """
        return self._workers.get(name)

    def workers_for(self, task_type: str) -> list["Worker"]:
        """
        Return all workers that declare capability for a task_type.

        Args:
            task_type: The task type string to match against
                       worker.capabilities lists.

        Returns:
            List of matching Worker instances (may be empty).
        """
        return [
            w for w in self._workers.values()
            if task_type in w.capabilities
        ]

    def all_workers(self) -> list["Worker"]:
        """Return all registered workers in registration order."""
        return list(self._workers.values())

    def names(self) -> list[str]:
        """Return all registered worker names."""
        return list(self._workers.keys())

    def has(self, name: str) -> bool:
        """True if a worker with this name is registered."""
        return name in self._workers

    def count(self) -> int:
        """Number of registered workers."""
        return len(self._workers)

    def clear(self) -> None:
        """Remove all workers. Used in tests."""
        self._workers.clear()

    def summary(self) -> dict:
        """Human-readable registry summary for debugging."""
        return {
            "count": self.count(),
            "workers": [
                {
                    "name": w.name,
                    "description": w.description,
                    "capabilities": w.capabilities,
                    "status": w.status().label(),
                }
                for w in self._workers.values()
            ],
        }