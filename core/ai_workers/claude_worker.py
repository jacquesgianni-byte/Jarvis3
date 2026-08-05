"""
AI Collaboration Framework -- Claude AI Worker
Genesis-040 Sprint-001
"""

from __future__ import annotations
import logging
from typing import Optional
from core.ai_workers.base import ExternalAIWorker

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a specialist engineering worker in the Jarvis engineering system. "
    "You have been assigned a specific task by the Planning Engine. "
    "Provide a precise, structured response. "
    "Do not add preamble or caveats -- respond directly to the task. "
    "Your output will be reviewed by a human before any action is taken."
)

# Capability-specific scope framing.
# Keeps responses bounded so the model does not exhaust its token budget.
_CAPABILITY_FRAMING = {
    "implement_feature": (
        "Produce a concise implementation plan only. "
        "List the key files to create or modify, the primary design decisions, "
        "and any risks. Maximum 200 words. Do not write code."
    ),
    "review_architecture": (
        "Produce a concise architecture review. "
        "Identify strengths, weaknesses, and up to three recommendations. "
        "Maximum 200 words."
    ),
    "write_tests": (
        "Produce a concise test plan. "
        "List the key test cases, their purpose, and expected outcomes. "
        "Maximum 200 words. Do not write code."
    ),
    "explain_code": (
        "Produce a concise explanation. "
        "Cover purpose, key components, and notable patterns. "
        "Maximum 200 words."
    ),
}


class ClaudeAIWorker(ExternalAIWorker):
    """
    External AI worker backed by the Jarvis AI client.
    Capabilities: implement_feature, review_architecture, write_tests, explain_code.
    All outputs require human approval.
    """

    def __init__(self, ai_client=None) -> None:
        super().__init__()
        self._ai = ai_client

    def execute(self, task) -> "WorkerResult":
        """Stamp the requested capability into the payload before delegating."""
        task_type = task.task_type or ""
        _prefix = "ai_collab_"
        if task_type.startswith(_prefix):
            cap = task_type[len(_prefix):]
            if cap in self.capabilities:
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
        """Call the AI client. Falls back to placeholder on failure."""
        if self._ai is None:
            logger.warning("[CLAUDE_AI_WORKER] No AI client -- returning placeholder.")
            return self._placeholder_response(prompt, context)
        try:
            capability = context.get("capability_used", "implement_feature")
            framing = _CAPABILITY_FRAMING.get(capability, _CAPABILITY_FRAMING["implement_feature"])
            full_prompt = _SYSTEM_PROMPT + "\n\n" + framing + "\n\n" + prompt
            response = self._ai.ask(full_prompt)
            if not getattr(response, "success", True):
                logger.warning("[CLAUDE_AI_WORKER] AI failure (cap=%s) -- placeholder.", capability)
                return self._placeholder_response(prompt, context)
            message = getattr(response, "message", "") or ""
            if not message.strip():
                logger.warning("[CLAUDE_AI_WORKER] Empty message (cap=%s) -- placeholder.", capability)
                return self._placeholder_response(prompt, context)
            return message
        except Exception as exc:
            logger.exception("[CLAUDE_AI_WORKER] AI call failed.")
            return "AI call failed: " + str(exc)

    def _placeholder_response(self, prompt: str, context: dict) -> str:
        """Structured placeholder when AI is unavailable or returns empty."""
        capability = context.get("capability_used", "implement_feature")
        description = context.get("description", prompt[:100])
        return (
            "[ClaudeAIWorker -- " + capability + "]\n\n"
            "Task: " + description + "\n\n"
            "Status: AI response unavailable. "
            "This worker is registered and operational. "
            "The engineering review gate will still execute.\n\n"
            "Requires human approval before any action is taken."
        )
