"""
AI Collaboration Framework — External AI Worker Base
Genesis-040 Sprint-001

ExternalAIWorker is the base class for all external AI workers.
It extends the Worker base class with AI-specific behaviour:
  - requires_approval is always True (no autonomous code changes)
  - AI response is wrapped in a structured WorkerResult
  - Capability registration is identical to internal workers

Design principle:
  Jarvis knows capabilities, never model names.
  ClaudeAIWorker is just a worker with capabilities.
  If a better model replaces Claude, only this file changes.
  Nothing else in the system needs to know.

Genesis-040 is complete when an external AI worker can be registered,
discovered, assigned, executed, and observed — identically to any
internal worker — with zero changes to Worker OS, Coordinator, or
CollaborationEngine.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, Optional

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)


class ExternalAIWorker(Worker):
    """
    Base class for all external AI workers.

    Subclasses must implement:
        name:          str property
        description:   str property
        capabilities:  list[str] property
        _call_ai(prompt, context) -> str

    Contract:
        - requires_approval is always True
        - AI response is always presented for human review before acting
        - No autonomous code modifications
        - WorkerResult.data["response"] contains the raw AI response
        - WorkerResult.data["capability_used"] records which capability was invoked
    """

    def validate(self, task: WorkerTask) -> bool:
        """Accept any task whose task_type matches a registered capability."""
        return any(cap in task.task_type for cap in self.capabilities)

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Execute the task by calling the external AI.
        Always requires human approval — never acts autonomously.
        """
        self._begin(task)

        try:
            prompt   = self._build_prompt(task)
            response = self._call_ai(prompt, task.payload)

            if not response:
                return self._fail(task.task_id, "AI returned empty response.")

            capability_used = self._resolve_capability(task)

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=(
                    f"AI worker {self.name} completed task.",
                    f"Capability: {capability_used}",
                ),
                recommendations=(
                    "Review AI response before applying any changes.",
                ),
                requires_approval=True,   # always — permanent design principle
                data={
                    "response":         response,
                    "capability_used":  capability_used,
                    "worker_name":      self.name,
                    "task_description": task.payload.get("description", ""),
                },
            ))

        except Exception as exc:
            logger.exception("[AI_WORKER:%s] Execution failed.", self.name)
            return self._fail(task.task_id, str(exc))

    # ── Subclass interface ─────────────────────────────────────────────────────

    @abstractmethod
    def _call_ai(self, prompt: str, context: dict) -> str:
        """
        Call the external AI model and return its response as a string.
        Subclasses implement the actual API call here.
        """
        ...

    def _build_prompt(self, task: WorkerTask) -> str:
        """Build the prompt to send to the AI from the task payload."""
        description = task.payload.get("description", "")
        objective   = task.payload.get("objective", "")
        context     = task.payload.get("context", "")

        parts = []
        if objective:
            parts.append(f"Objective: {objective}")
        if description:
            parts.append(f"Task: {description}")
        if context:
            parts.append(f"Context: {context}")

        return "\n\n".join(parts) if parts else description

    def _resolve_capability(self, task: WorkerTask) -> str:
        """Determine which capability this task is using."""
        for cap in self.capabilities:
            if cap in task.task_type or cap in task.payload.get("description", ""):
                return cap
        return self.capabilities[0] if self.capabilities else task.task_type
