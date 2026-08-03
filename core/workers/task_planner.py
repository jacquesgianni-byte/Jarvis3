"""
Jarvis Task Planner (Genesis-027 Sprint-004)

Analyses engineering requests and produces ordered WorkerPlans.

Responsibilities:
    - Analyse a natural language engineering request
    - Determine which capabilities are required
    - Resolve capabilities to available workers via WorkerManager
    - Produce an ordered WorkerPlan

Does NOT:
    - Execute workers (WorkerCoordinator owns that)
    - Route tasks (WorkerOrchestrator owns that)
    - Manage worker lifecycle (WorkerManager owns that)
    - Make architectural decisions

Design principle:
    The planner plans using CAPABILITIES, not worker names.
    WorkerManager resolves capabilities to actual workers.
    If two debugging workers exist tomorrow, the planner needs no changes.

Capability keywords:
    Each capability is associated with natural language trigger phrases.
    Data-driven — no if/elif chains for specific request types.
    Adding a new capability = adding one entry to _CAPABILITY_PATTERNS.

Genesis-027 Sprint-004.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from core.workers.manager import WorkerManager
from core.workers.models import WorkerTask

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WorkerPlan — immutable ordered execution plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkerPlan:
    """
    Immutable ordered list of WorkerTasks to be executed sequentially.

    Produced by TaskPlanner. Consumed by WorkerCoordinator.
    The coordinator executes the plan — it never decides what the plan is.

    Attributes:
        tasks:       Ordered list of WorkerTasks to execute.
        capabilities: The capability sequence that was planned.
        request:     The original engineering request (for traceability).
        confidence:  Planning confidence (0.0-1.0).
    """
    tasks:        tuple[WorkerTask, ...]
    capabilities: tuple[str, ...]
    request:      str
    confidence:   float = 0.85

    @property
    def worker_names(self) -> list[str]:
        """Return the worker names in execution order."""
        return [t.requester for t in self.tasks]

    @property
    def is_empty(self) -> bool:
        """True if no tasks were planned."""
        return len(self.tasks) == 0

    def summary(self) -> dict:
        """Human-readable plan summary."""
        return {
            "request":      self.request[:80],
            "capabilities": list(self.capabilities),
            "task_count":   len(self.tasks),
            "confidence":   self.confidence,
        }


# ---------------------------------------------------------------------------
# Capability patterns
#
# Maps capability name -> trigger patterns.
# Data-driven: no if/elif chains.
# Adding a new capability = one new entry here.
#
# Capability names must match task_type strings used by workers.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapabilitySignal:
    """A capability with its trigger patterns and execution order hint."""
    name:     str          # capability name (matches worker task_type)
    patterns: tuple[str, ...]  # regex patterns that suggest this capability
    order:    int          # preferred execution order (lower = earlier)


_CAPABILITY_SIGNALS: list[CapabilitySignal] = [
    CapabilitySignal(
        name="run_engineering_review",
        patterns=(
            r"\\breview\\s+genesis\\b",
            r"\\breview\\s+the\\s+latest\\b",
            r"\\bengineering\\s+review\\b",
            r"\\brun\\s+(?:an?\\s+)?(?:engineering\\s+)?review\\b",
            r"\\bgenerate\\s+(?:genesis\\s+)?review\\b",
            r"\\breview\\s+genesis[-\\s]\\d+\\b",
        ),
        order=0,
    ),

    CapabilitySignal(
        name="plan_implementation",
        patterns=(
            r"\b(?:implement|add|create|build|write|develop|introduce|extend)\b",
            r"\b(?:fix|patch|resolve|correct|repair)\b",
            r"\b(?:refactor|improve|optimise|optimize|clean)\b",
            r"\b(?:feature|functionality|capability|support)\b",
        ),
        order=1,
    ),
    CapabilitySignal(
        name="analyse_session",
        patterns=(
            r"\b(?:debug|diagnose|investigate|analyse|analyze|inspect)\b",
            r"\b(?:bug|error|issue|problem|failure|crash|broken)\b",
            r"\b(?:log|trace|stack|exception|traceback)\b",
            r"\b(?:why|what.s wrong|not working|failing)\b",
        ),
        order=2,
    ),
    CapabilitySignal(
        name="run_tests",
        patterns=(
            r"\b(?:test|tests|suite|pytest|validate|verify|check)\b",
            r"\b(?:passing|failing|green|regression)\b",
            r"\b(?:make sure|ensure|confirm)\b",
        ),
        order=3,
    ),
]

# Compile all patterns once at module load
_COMPILED_SIGNALS: list[tuple[CapabilitySignal, list[re.Pattern]]] = [
    (sig, [re.compile(p, re.IGNORECASE) for p in sig.patterns])
    for sig in _CAPABILITY_SIGNALS
]


class TaskPlanner:
    """
    Analyses engineering requests and produces ordered WorkerPlans.

    Uses data-driven capability signals to determine which workers
    are needed. Resolves capabilities to workers via WorkerManager.
    Never contains worker-specific branches.

    Public API:
        plan(request, payload)  -> WorkerPlan
        capabilities_for(request) -> list[str]  (for inspection/testing)
    """

    def __init__(self, manager: WorkerManager) -> None:
        self._manager = manager

    def plan(
        self,
        request: str,
        payload: Optional[dict] = None,
    ) -> WorkerPlan:
        """
        Analyse a request and produce an ordered WorkerPlan.

        Args:
            request: Natural language engineering request.
            payload: Optional base payload to include in all tasks.

        Returns:
            WorkerPlan with ordered tasks, or empty plan if no
            capabilities matched or no workers are available.
        """
        if not request or not request.strip():
            return WorkerPlan(
                tasks=(),
                capabilities=(),
                request=request,
                confidence=0.0,
            )

        capabilities = self.capabilities_for(request)

        if not capabilities:
            logger.info(
                "[TASK_PLANNER] No capabilities matched for: %r", request[:60]
            )
            return WorkerPlan(
                tasks=(),
                capabilities=(),
                request=request,
                confidence=0.0,
            )

        base_payload = dict(payload or {})
        base_payload["planning_request"] = request

        tasks = []
        resolved_capabilities = []

        for capability in capabilities:
            workers = self._manager.workers_for(capability)
            if not workers:
                logger.debug(
                    "[TASK_PLANNER] No worker available for capability %r — skipping.",
                    capability,
                )
                continue

            # Use the first available worker for this capability
            worker = workers[0]
            task = WorkerTask(
                task_type=capability,
                payload=dict(base_payload),
                requester=worker.name,
            )
            tasks.append(task)
            resolved_capabilities.append(capability)
            logger.debug(
                "[TASK_PLANNER] Capability %r -> worker %r",
                capability, worker.name,
            )

        confidence = len(tasks) / max(len(capabilities), 1)

        logger.info(
            "[TASK_PLANNER] Plan: %d tasks for request %r (confidence=%.2f)",
            len(tasks), request[:60], confidence,
        )

        return WorkerPlan(
            tasks=tuple(tasks),
            capabilities=tuple(resolved_capabilities),
            request=request,
            confidence=confidence,
        )

    def capabilities_for(self, request: str) -> list[str]:
        """
        Determine which capabilities are needed for a request.

        Returns capability names in execution order.
        Data-driven — no worker-specific logic.

        Args:
            request: Natural language engineering request.

        Returns:
            Ordered list of capability names.
        """
        matched: list[CapabilitySignal] = []

        for signal, patterns in _COMPILED_SIGNALS:
            for pattern in patterns:
                if pattern.search(request):
                    matched.append(signal)
                    break  # one pattern match per signal is enough

        # Sort by preferred execution order
        matched.sort(key=lambda s: s.order)

        return [s.name for s in matched]