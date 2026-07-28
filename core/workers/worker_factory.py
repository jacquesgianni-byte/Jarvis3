"""
Jarvis Worker Factory (Genesis-027 Sprint-001)

Architecture stub for future worker generation from templates.

Current state:
    STUB ONLY — no implementation yet.
    The interface and template structure are defined here.
    Implementation follows in Genesis-027 Sprint-002+.

Long-term vision:
    Jarvis can say "I don't have a Robotics Worker — shall I create one?"
    and generate a new worker from a standard blueprint automatically.

Worker Template Blueprint:
    Every generated worker includes:
        - Identity (name, description, version)
        - Capabilities (task_type list)
        - Permissions (what the worker is allowed to do)
        - Dependencies (other workers or services required)
        - Tests (auto-generated test scaffold)
        - Documentation (docstring template)
        - Configuration (default settings)
        - Logging (standardised log prefixes)
        - Telemetry (timing and health metrics)

    Nothing hand-crafted. Everything consistent.

Genesis-027 Sprint-001: stub only.
Genesis-027 Sprint-002+: full template engine implementation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Worker blueprint dataclass
# ---------------------------------------------------------------------------

@dataclass
class WorkerBlueprint:
    """
    Specification for generating a new Worker from a template.

    Passed to WorkerFactory.create() in future sprints.

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
    description:  str
    capabilities: list[str]                = field(default_factory=list)
    permissions:  list[str]                = field(default_factory=list)
    dependencies: list[str]                = field(default_factory=list)
    version:      str                      = "0.1.0"
    author:       str                      = "jarvis"
    metadata:     dict                     = field(default_factory=dict)


# ---------------------------------------------------------------------------
# WorkerFactory stub
# ---------------------------------------------------------------------------

class WorkerFactory:
    """
    Generates new Worker implementations from standard blueprints.

    STUB — not yet implemented.

    Future public API:
        create(blueprint)          -> Worker instance
        generate_scaffold(blueprint) -> str (Python source)
        register_template(name, fn)  -> None
        available_templates()        -> list[str]

    Genesis-027 Sprint-002+.
    """

    def __init__(self) -> None:
        self._templates: dict[str, object] = {}
        logger.info("[WORKER_FACTORY] Initialised (stub).")

    def create(self, blueprint: WorkerBlueprint) -> None:
        """
        Generate and return a Worker instance from a blueprint.

        NOT YET IMPLEMENTED.

        Args:
            blueprint: WorkerBlueprint describing the desired worker.

        Raises:
            NotImplementedError: Always, until Sprint-002.
        """
        raise NotImplementedError(
            "WorkerFactory.create() is not yet implemented. "
            "Scheduled for Genesis-027 Sprint-002."
        )

    def generate_scaffold(self, blueprint: WorkerBlueprint) -> str:
        """
        Generate Python source code for a new Worker from a blueprint.

        NOT YET IMPLEMENTED.

        Returns:
            Python source string for the new Worker class.
        """
        raise NotImplementedError(
            "WorkerFactory.generate_scaffold() is not yet implemented. "
            "Scheduled for Genesis-027 Sprint-002."
        )

    def available_templates(self) -> list[str]:
        """Return the names of available worker templates."""
        return list(self._templates.keys())

    def summary(self) -> dict:
        """Human-readable factory summary."""
        return {
            "status":             "stub",
            "available_templates": self.available_templates(),
            "scheduled_sprint":   "Genesis-027 Sprint-002",
        }