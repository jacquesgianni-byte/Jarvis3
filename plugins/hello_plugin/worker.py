"""
HelloWorker — Genesis-046 proof-of-concept plugin worker.
"""

from __future__ import annotations

from core.workers.base import Worker
from core.workers.models import WorkerTask, WorkerResult


class HelloWorker(Worker):
    """Proof-of-concept plugin worker. Says hello."""

    @property
    def name(self) -> str:
        return "hello_worker"

    @property
    def description(self) -> str:
        return "Proof-of-concept plugin worker (Genesis-046)."

    @property
    def capabilities(self) -> list[str]:
        return ["plugin_demo", "hello"]

    def validate(self, task: WorkerTask) -> bool:
        instruction = task.payload.get("instruction", "")
        return isinstance(instruction, str) and len(instruction.strip()) > 0

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        instruction = task.payload.get("instruction", "")
        result = WorkerResult(
            task_id=task.task_id,
            worker_name=self.name,
            success=True,
            observations=(f"Hello from HelloWorker! Instruction received: '{instruction}'",),
            requires_approval=True,
        )
        return self._succeed(result)
