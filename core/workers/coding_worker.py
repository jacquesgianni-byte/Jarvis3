"""
Jarvis Coding Worker (Genesis-027 Sprint-002)

Version 1 - Produces implementation plans from task descriptions.

This is the first production worker that demonstrates real multi-worker
coordination potential. It receives a coding task, reasons about it
using the AI provider, and returns a structured implementation plan.

Version 1 deliberately does NOT:
    - Write files
    - Modify code
    - Make architectural decisions autonomously
    - Execute shell commands

It produces a plan that a human (or future worker) can review and act on.
That keeps Sprint-002 focused on proving the plumbing, not building
autonomous software engineering.

Task payload:
    {
        "description": str   # what needs to be implemented
        "context":     str   # optional extra context (file names, constraints)
    }

Result data:
    {
        "plan":        list[str]   # ordered implementation steps
        "files":       list[str]   # likely files to modify
        "complexity":  str         # "low" | "medium" | "high"
        "summary":     str         # one-line summary
    }

Dependencies:
    {"ai": AIProvider}   # injected by WorkerFactory

Genesis-027 Sprint-002.
"""

from __future__ import annotations

import logging
from typing import Any

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)

_PLAN_PROMPT = """You are a senior software engineer reviewing a coding task for the Jarvis AI assistant project.

Your job is to produce a clear, structured implementation plan.

Task description:
{description}

Additional context:
{context}

Respond ONLY with a JSON object in this exact format (no markdown, no preamble):
{{
    "summary": "one-line description of what needs to be done",
    "complexity": "low|medium|high",
    "files": ["list", "of", "likely", "files", "to", "modify"],
    "plan": [
        "Step 1: ...",
        "Step 2: ...",
        "Step 3: ..."
    ]
}}"""


class CodingWorker(Worker):
    """
    Produces structured implementation plans for coding tasks.

    Version 1: Plan generation only. No file modification.
    Requires an AI provider injected via WorkerFactory.

    Capabilities:
        plan_implementation - analyse a coding task and return a plan
    """

    def __init__(self, ai: Any) -> None:
        super().__init__()
        self._ai = ai

    # ------------------------------------------------------------------
    # Worker contract
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "coding_worker"

    @property
    def description(self) -> str:
        return (
            "Analyses coding tasks and produces structured implementation plans. "
            "Version 1: planning only — does not write or modify files."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["plan_implementation"]

    def validate(self, task: WorkerTask) -> bool:
        """Validate the task has a description in its payload."""
        if task.task_type != "plan_implementation":
            return False
        if not task.payload.get("description", "").strip():
            logger.warning("[CODING_WORKER] Task missing description.")
            return False
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Analyse a coding task and return a structured implementation plan.

        Args:
            task: WorkerTask with payload["description"] and optional payload["context"]

        Returns:
            WorkerResult with plan, files, complexity, and summary in data.
        """
        self._begin(task)

        try:
            description = task.payload["description"].strip()
            context     = task.payload.get("context", "None provided").strip()

            prompt = _PLAN_PROMPT.format(
                description=description,
                context=context,
            )

            logger.info(
                "[CODING_WORKER] Requesting implementation plan for: %r",
                description[:60],
            )

            # Call AI provider
            response = self._ai.ask(prompt)
            raw_text = response.message if response.success else ""

            if not raw_text:
                return self._fail(task.task_id, "AI provider returned empty response.")

            # Parse JSON response
            import json
            import re

            # Strip any accidental markdown fences
            clean = re.sub(r"```(?:json)?|```", "", raw_text).strip()

            try:
                plan_data = json.loads(clean)
            except json.JSONDecodeError as e:
                logger.warning(
                    "[CODING_WORKER] JSON parse failed: %s. Raw: %r", e, clean[:200]
                )
                # Graceful fallback — return raw text as single step
                plan_data = {
                    "summary":    description[:80],
                    "complexity": "unknown",
                    "files":      [],
                    "plan":       [raw_text],
                }

            plan  = plan_data.get("plan", [])
            files = plan_data.get("files", [])
            complexity = plan_data.get("complexity", "unknown")
            summary    = plan_data.get("summary", description[:80])

            observations = [
                f"Task: {description[:80]}",
                f"Complexity: {complexity}",
                f"Plan steps: {len(plan)}",
                f"Likely files: {len(files)}",
            ]

            recommendations = list(plan)

            logger.info(
                "[CODING_WORKER] Plan produced: %d steps, complexity=%r",
                len(plan), complexity,
            )

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(observations),
                recommendations=tuple(recommendations),
                requires_approval=True,  # Human reviews before implementation
                data={
                    "plan":       plan,
                    "files":      files,
                    "complexity": complexity,
                    "summary":    summary,
                },
            ))

        except Exception as exc:
            logger.exception("[CODING_WORKER] Plan generation failed.")
            return self._fail(task.task_id, str(exc))