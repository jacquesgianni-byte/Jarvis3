"""
Jarvis Worker Factory (Genesis-027 Sprint-002)

Single entry point for constructing Worker instances.

Responsibilities:
    - Create workers by name
    - Inject dependencies into workers that need them
    - Apply common configuration
    - Return fully initialised Worker instances

Does NOT:
    - Register workers (WorkerManager owns that)
    - Execute workers (WorkerManager owns that)
    - Route tasks (WorkerOrchestrator owns that)
    - Manage lifecycle (WorkerManager owns that)

Design:
    Workers are registered as factory functions (callables).
    Each factory function receives the requested dependencies
    and returns a fully constructed Worker instance.
    No worker-specific branches in the factory core.
    No isinstance() checks.
    No if/elif worker name chains.

Usage:
    factory = WorkerFactory()
    factory.register_builder("debug_worker", lambda deps: DebugWorker())
    factory.register_builder("coding_worker", lambda deps: CodingWorker(deps["ai"]))

    worker = factory.create("coding_worker", deps={"ai": ai_provider})

Genesis-027 Sprint-001: stub.
Genesis-027 Sprint-002: full implementation.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from core.workers.base import Worker

logger = logging.getLogger(__name__)

WorkerBuilder = Callable[[dict[str, Any]], Worker]


class WorkerFactory:
    """
    Creates Worker instances from registered builder functions.

    Each worker type is associated with a builder - a callable that
    receives a dependency dict and returns a fully initialised Worker.

    No worker-specific logic lives here. Adding Worker #100 is identical
    to adding Worker #3.

    Public API:
        register_builder(name, builder)   - register a worker builder
        create(name, deps)                - create a worker instance
        can_create(name)                  - True if builder registered
        available_worker_names()          - list of buildable worker names
        summary()                         - debug dict
    """

    def __init__(self) -> None:
        self._builders: dict[str, WorkerBuilder] = {}
        logger.info("[WORKER_FACTORY] Initialised.")

    def register_builder(self, name: str, builder: WorkerBuilder) -> None:
        """
        Register a builder function for a named worker type.

        Args:
            name:    The worker name this builder creates.
            builder: Callable receiving deps dict, returning Worker instance.

        Raises:
            ValueError: If a builder for this name is already registered.
        """
        if name in self._builders:
            raise ValueError(
                f"WorkerFactory: builder for {name!r} already registered. "
                f"Use replace_builder() to replace it."
            )
        self._builders[name] = builder
        logger.info("[WORKER_FACTORY] Registered builder for %r.", name)

    def replace_builder(self, name: str, builder: WorkerBuilder) -> None:
        """Replace an existing builder (or register if not present)."""
        self._builders[name] = builder
        logger.info("[WORKER_FACTORY] Replaced builder for %r.", name)

    def create(self, name: str, deps: Optional[dict[str, Any]] = None) -> Worker:
        """
        Create and return a fully initialised Worker instance.

        Args:
            name: The registered worker name.
            deps: Optional dependency dict passed to the builder.

        Returns:
            A fully initialised Worker instance.

        Raises:
            KeyError: If no builder is registered for this name.
        """
        if name not in self._builders:
            available = list(self._builders.keys())
            raise KeyError(
                f"WorkerFactory: no builder registered for {name!r}. "
                f"Available: {available}"
            )
        resolved_deps = deps or {}
        logger.info(
            "[WORKER_FACTORY] Creating worker %r with deps=%s.",
            name, list(resolved_deps.keys()),
        )
        worker = self._builders[name](resolved_deps)
        logger.info(
            "[WORKER_FACTORY] Created %r (class=%s).",
            name, type(worker).__name__,
        )
        return worker

    def can_create(self, name: str) -> bool:
        """Return True if a builder is registered for this worker name."""
        return name in self._builders

    def available_worker_names(self) -> list[str]:
        """Return the names of all registered worker builders."""
        return list(self._builders.keys())

    def generate_scaffold(self, blueprint: "WorkerBlueprint") -> str:
        """
        Generate Python source code for a new Worker from a blueprint.

        NOT YET IMPLEMENTED. Scheduled for Genesis-027 Sprint-003.

        Raises:
            NotImplementedError: Always, until Sprint-003.
        """
        raise NotImplementedError(
            "WorkerFactory.generate_scaffold() is not yet implemented. "
            "Scheduled for Genesis-027 Sprint-003."
        )

    def summary(self) -> dict:
        """Human-readable factory summary for debugging."""
        return {
            "status":                 "active",
            "registered_builders":    len(self._builders),
            "available_worker_names": self.available_worker_names(),
        }


# ---------------------------------------------------------------------------
# WorkerBlueprint — retained for Sprint-001 tests and future template engine
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as _field


@dataclass
class WorkerBlueprint:
    """
    Specification for generating a new Worker from a template.

    Used by the future template engine (Genesis-027 Sprint-003+).
    Retained here so Sprint-001 tests and future code can import it
    from the same module as WorkerFactory.

    Attributes:
        name:          Unique worker name (e.g. "coding_worker")
        description:   Human-readable description
        capabilities:  List of task_type strings
        permissions:   What the worker is allowed to do
        dependencies:  Other workers or services required
        version:       Semantic version string
        author:        Who/what created this worker
        metadata:      Additional configuration
    """
    name:         str
    description:  str                      = ""
    capabilities: list                     = _field(default_factory=list)
    permissions:  list                     = _field(default_factory=list)
    dependencies: list                     = _field(default_factory=list)
    version:      str                      = "0.1.0"
    author:       str                      = "jarvis"
    metadata:     dict                     = _field(default_factory=dict)