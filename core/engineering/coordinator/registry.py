"""
Genesis-018 Sprint 006 — Engineering Worker Registry
Authoritative source of all engineering workers known to the Coordinator.

Responsibilities:
    - register(worker)              — add a worker to the registry
    - unregister(worker_id)         — remove a worker by ID
    - get(worker_id)                — retrieve a specific worker
    - all_workers()                 — all registered workers (snapshot list)
    - available_workers()           — workers that can currently accept work
    - workers_by_capability(cap)    — filter workers by declared capability
    - status()                      — current registry operational status
    - snapshot()                    — immutable point-in-time registry state

Design principles:
    - Single source of truth for worker identity
    - Registry does NOT execute work — it only stores and exposes workers
    - Deterministic — same registry state always produces same queries
    - Snapshot independence — snapshots are decoupled from live registry

Long-term vision:
    Genesis-020 adds workers via registry.register(new_worker).
    The Dispatcher queries the registry for available workers.
    The Coordinator and Dispatcher require zero modification.

Design constraints (Sprint 006):
    - Single-threaded, no concurrency
    - Registry does not own worker lifecycle
    - Workers must implement EngineeringWorker interface
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set

from .models import RegistrySnapshot, RegistryStatus, WorkerStatus
from .worker import EngineeringWorker


class EngineeringWorkerRegistry:
    """
    Authoritative, single source of truth for all engineering workers.

    The registry stores workers by their stable worker_id().
    It provides filtered views (available, by capability) and immutable
    snapshots for telemetry and logging.

    The registry does not manage worker lifecycle — it only knows about
    workers that have been explicitly registered.
    """

    def __init__(self) -> None:
        self._workers:    Dict[str, EngineeringWorker] = {}   # worker_id → worker
        self._registered_order: List[str]              = []   # insertion order

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, worker: EngineeringWorker) -> str:
        """
        Register a worker with the registry.

        Args:
            worker: Any object implementing EngineeringWorker.

        Returns:
            The worker's stable worker_id().

        Raises:
            TypeError:  if worker does not implement EngineeringWorker.
            ValueError: if a worker with the same worker_id is already registered.
        """
        if not isinstance(worker, EngineeringWorker):
            raise TypeError(
                f"register() expects EngineeringWorker, "
                f"got {type(worker).__name__}"
            )
        wid = worker.worker_id()
        if wid in self._workers:
            raise ValueError(
                f"Worker {wid!r} is already registered. "
                f"Call unregister() first to replace it."
            )
        self._workers[wid]         = worker
        self._registered_order.append(wid)
        return wid

    def unregister(self, worker_id: str) -> bool:
        """
        Remove a worker from the registry by its stable ID.

        Args:
            worker_id: The stable ID of the worker to remove.

        Returns:
            True if the worker was found and removed, False otherwise.
        """
        if not isinstance(worker_id, str):
            raise TypeError(
                f"unregister() expects str worker_id, "
                f"got {type(worker_id).__name__}"
            )
        if worker_id not in self._workers:
            return False
        del self._workers[worker_id]
        self._registered_order = [
            wid for wid in self._registered_order if wid != worker_id
        ]
        return True

    def replace(self, worker: EngineeringWorker) -> bool:
        """
        Replace an existing worker with a new one sharing the same worker_id.

        Equivalent to unregister() + register() in one atomic step.

        Returns:
            True if a previous worker was replaced, False if it was a new registration.
        """
        if not isinstance(worker, EngineeringWorker):
            raise TypeError(
                f"replace() expects EngineeringWorker, "
                f"got {type(worker).__name__}"
            )
        wid       = worker.worker_id()
        replaced  = wid in self._workers
        if not replaced:
            self._registered_order.append(wid)
        self._workers[wid] = worker
        return replaced

    def clear(self) -> int:
        """
        Remove all workers from the registry.

        Returns:
            The number of workers that were cleared.
        """
        count = len(self._workers)
        self._workers.clear()
        self._registered_order.clear()
        return count

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, worker_id: str) -> Optional[EngineeringWorker]:
        """
        Retrieve a worker by its stable ID.

        Returns:
            The EngineeringWorker, or None if not found.
        """
        if not isinstance(worker_id, str):
            raise TypeError(
                f"get() expects str worker_id, "
                f"got {type(worker_id).__name__}"
            )
        return self._workers.get(worker_id)

    def contains(self, worker_id: str) -> bool:
        """Return True if a worker with the given ID is registered."""
        return worker_id in self._workers

    # ------------------------------------------------------------------
    # Filtered views (return copies — registry state cannot be mutated externally)
    # ------------------------------------------------------------------

    def all_workers(self) -> List[EngineeringWorker]:
        """
        Return all registered workers in registration order.
        Returns a snapshot list — mutations do not affect the registry.
        """
        return [self._workers[wid] for wid in self._registered_order if wid in self._workers]

    def available_workers(self) -> List[EngineeringWorker]:
        """
        Return workers that can currently accept a new session.
        Preserves registration order.
        """
        return [
            self._workers[wid]
            for wid in self._registered_order
            if wid in self._workers and self._workers[wid].can_accept()
        ]

    def busy_workers(self) -> List[EngineeringWorker]:
        """Return workers that are currently executing a session."""
        return [
            self._workers[wid]
            for wid in self._registered_order
            if wid in self._workers and self._workers[wid].status().is_busy()
        ]

    def unavailable_workers(self) -> List[EngineeringWorker]:
        """Return workers whose status is UNAVAILABLE."""
        return [
            self._workers[wid]
            for wid in self._registered_order
            if wid in self._workers
            and self._workers[wid].status() == WorkerStatus.UNAVAILABLE
        ]

    def workers_by_capability(self, capability: str) -> List[EngineeringWorker]:
        """
        Return all registered workers that declare the given capability.
        Preserves registration order.

        Args:
            capability: Capability string, e.g. "engineering", "testing".
        """
        if not isinstance(capability, str):
            raise TypeError(
                f"workers_by_capability() expects str, "
                f"got {type(capability).__name__}"
            )
        return [
            self._workers[wid]
            for wid in self._registered_order
            if wid in self._workers
            and capability in self._workers[wid].capabilities()
        ]

    def available_workers_by_capability(self, capability: str) -> List[EngineeringWorker]:
        """
        Return workers that both declare the given capability AND can accept work.
        The Dispatcher will use this for capability-based routing in future sprints.
        """
        return [w for w in self.workers_by_capability(capability) if w.can_accept()]

    def first_available(self) -> Optional[EngineeringWorker]:
        """
        Return the first available worker in registration order, or None.
        The default dispatch strategy for the Dispatcher.
        """
        available = self.available_workers()
        return available[0] if available else None

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Total number of registered workers."""
        return len(self._workers)

    @property
    def is_empty(self) -> bool:
        return len(self._workers) == 0

    @property
    def available_count(self) -> int:
        return len(self.available_workers())

    @property
    def busy_count(self) -> int:
        return len(self.busy_workers())

    @property
    def unavailable_count(self) -> int:
        return len(self.unavailable_workers())

    def registered_ids(self) -> List[str]:
        """Return worker IDs in registration order (snapshot list)."""
        return list(self._registered_order)

    def all_capabilities(self) -> List[str]:
        """
        Return the deduplicated, sorted list of all capabilities across
        all registered workers.
        """
        caps: Set[str] = set()
        for wid in self._registered_order:
            if wid in self._workers:
                caps.update(self._workers[wid].capabilities())
        return sorted(caps)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> RegistryStatus:
        """Return the current operational status of the registry."""
        if not self._workers:
            return RegistryStatus.EMPTY
        if self.available_count > 0:
            return RegistryStatus.ACTIVE
        if self.busy_count > 0:
            return RegistryStatus.FULL
        return RegistryStatus.DEGRADED

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> RegistrySnapshot:
        """
        Produce an immutable point-in-time snapshot of the registry state.

        The snapshot is fully independent of the live registry — subsequent
        registry mutations do not affect previously produced snapshots.
        """
        all_caps = tuple(self.all_capabilities())
        return RegistrySnapshot(
            status=self.status(),
            timestamp_ms=int(time.monotonic() * 1000),
            total_registered=self.size,
            available_count=self.available_count,
            busy_count=self.busy_count,
            unavailable_count=self.unavailable_count,
            worker_ids=tuple(self._registered_order),
            capabilities=all_caps,
        )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def statistics(self) -> dict:
        """Return a dict of registry statistics."""
        return {
            "total_registered":  self.size,
            "available":         self.available_count,
            "busy":              self.busy_count,
            "unavailable":       self.unavailable_count,
            "capability_count":  len(self.all_capabilities()),
        }

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"EngineeringWorkerRegistry("
            f"status={self.status().value}, "
            f"total={self.size}, "
            f"available={self.available_count}, "
            f"busy={self.busy_count}"
            f")"
        )