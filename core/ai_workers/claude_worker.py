"""
AI Collaboration Framework — Claude AI Worker
Genesis-040 Sprint-001

First concrete ExternalAIWorker implementation.
Uses Jarvis's existing AI client (same one Agent uses).

Capabilities:
  - implement_feature     (write new code/features)
  - review_architecture   (review design decisions)
  - write_tests           (generate test cases)
  - explain_code          (explain existing code)

Design principle:
  Jarvis knows "implement_feature" capability.
  Jarvis does NOT know "Claude" or "GPT".
  If another model outperforms Claude, swap _call_ai().
  Nothing else changes.

Requires human approval for all outputs — permanent principle.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.ai_workers.base import ExternalAIWorker

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a specialist engineering worker in the Jarvis engineering system.
You have been assigned a specific task by Jarvis's Planning Engine.
Provide a precise, structured response.
Do not add preamble or caveats — respond directly to the task.
Your output will be reviewed by a human before any action is taken.
"""


class ClaudeAIWorker(ExternalAIWorker):
    """
    External AI worker backed by Claude (via Jarvis's existing AI client).

    Registered as "claude_ai_worker" with capabilities:
      - implement_feature
      - review_architecture
      - write_tests
      - explain_code

    Jarvis routes to this worker by capability, never by name.
    """

    def __init__(self, ai_client=None) -> None:
        super().__init__()
        self._ai = ai_client   # Jarvis's existing AI client, injected via factory

    def execute(self, task) -> "WorkerResult":
        """
        Override to stamp the requested capability into the payload
        so _resolve_capability() returns the correct capability name.
        The coordinator sets task_type to the workflow name, not the capability,
        so we extract the capability from the workflow name here.
        """
        # Extract capability from workflow name e.g. "ai_collab_review_architecture"
        task_type = task.task_type or ""
        _prefix = "ai_collab_"
        if task_type.startswith(_prefix):
            cap = task_type[len(_prefix):]
            if cap in self.capabilities:
                # Rebuild task with capability stamped into payload
                from core.workers.models import WorkerTask
                payload = dict(task.payload)
                payload["capability_used"] = cap
                task = WorkerTask(
                    task_type=cap,
                    payload=payload,
                    requester=task.requester,
                )
        return super().execute(task)

    @property
    def name(self) -> str:
        return "claude_ai_worker"

    @property
    def description(self) -> str:
        return (
            "External AI worker for implementation, architecture review, "
            "test writing, and code explanation. All outputs require human approval."
        )

    @property
    def capabilities(self) -> list[str]:
        return [
            "implement_feature",
            "review_architecture",
            "write_tests",
            "explain_code",
        ]

    def _call_ai(self, prompt: str, context: dict) -> str:
        """
        Call Claude via Jarvis's existing AI client.
        Falls back to a structured placeholder if AI is unavailable.
        """
        if self._ai is None:
            logger.warning("[CLAUDE_AI_WORKER] No AI client configured — returning placeholder.")
            return self._placeholder_response(prompt, context)

        try:
            full_prompt = f"{_SYSTEM_PROMPT}\n\n{prompt}"
            response = self._ai.ask(full_prompt)
            if hasattr(response, "message"):
                return response.message or ""
            return str(response) if response else ""
        except Exception as exc:
            logger.exception("[CLAUDE_AI_WORKER] AI call failed.")
            return f"AI call failed: {exc}"

    def _placeholder_response(self, prompt: str, context: dict) -> str:
        """
        Structured placeholder used when AI client is unavailable.
        Allows the worker to be registered, discovered, and tested
        without a live AI connection.
        """
        capability = context.get("capability_used", "implement_feature")
        description = context.get("description", prompt[:100])
        return (
            f"[ClaudeAIWorker — {capability}]\n\n"
            f"Task: {description}\n\n"
            f"Status: AI client not configured. "
            f"This worker is registered and operational. "
            f"Connect an AI client via WorkerFactory to enable live responses.\n\n"
            f"Requires human approval before any action is taken."
        )
