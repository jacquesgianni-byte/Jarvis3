"""
Execution Plan Models — Genesis-041 Sprint-005

ExecutionPlan is the machine-readable contract between:
  ClaudeAIWorker (produces it) and ExecutionWorker (consumes it).

After human approval, execution is fully deterministic.
No AI calls. No natural-language parsing. No interpretation.
ExecutionWorker executes the plan exactly as specified.

Design:
  FileOperation — a single file operation (create/modify/delete)
  ExecutionPlan — an ordered list of FileOperations

The human-readable explanation and the machine-readable plan are
produced together by ClaudeAIWorker and stored in WorkerResult.data.
They travel together through the pipeline without ever being separated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class FileAction(Enum):
    CREATE = "create"
    MODIFY = "modify"
    DELETE = "delete"


@dataclass(frozen=True)
class FileOperation:
    """
    A single file operation in an execution plan.

    Immutable — produced by ClaudeAIWorker, consumed by ExecutionWorker.

    Fields:
        path     — relative path from repo root (e.g. "core/auth/jwt.py")
        action   — create | modify | delete
        content  — full file content for create/modify; empty for delete
        reason   — human-readable reason (for audit trail, not execution)
    """
    path:    str
    action:  FileAction
    content: str   # full content for create/modify; empty for delete
    reason:  str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path":    self.path,
            "action":  self.action.value,
            "content": self.content,
            "reason":  self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FileOperation":
        return cls(
            path=d["path"],
            action=FileAction(d["action"]),
            content=d.get("content", ""),
            reason=d.get("reason", ""),
        )


@dataclass(frozen=True)
class ExecutionPlan:
    """
    An ordered list of FileOperations produced by ClaudeAIWorker.

    Immutable — the plan is fixed at AI response time.
    After approval, ExecutionWorker executes it verbatim.

    No AI calls occur after the plan is approved.
    No natural-language parsing occurs at execution time.
    Execution is deterministic and auditable.
    """
    plan_id:      str
    capability:   str                       # e.g. "implement_feature"
    description:  str                       # human-readable task description
    operations:   tuple[FileOperation, ...]

    @classmethod
    def create(
        cls,
        capability: str,
        description: str,
        operations: list[FileOperation],
    ) -> "ExecutionPlan":
        return cls(
            plan_id=str(uuid4()),
            capability=capability,
            description=description,
            operations=tuple(operations),
        )

    @classmethod
    def empty(cls, capability: str = "", description: str = "") -> "ExecutionPlan":
        """An empty plan — used when AI produces no structured operations."""
        return cls(
            plan_id=str(uuid4()),
            capability=capability,
            description=description,
            operations=(),
        )

    @property
    def is_empty(self) -> bool:
        return len(self.operations) == 0

    @property
    def files_to_create(self) -> list[dict]:
        return [
            {"path": op.path, "content": op.content}
            for op in self.operations
            if op.action == FileAction.CREATE
        ]

    @property
    def files_to_modify(self) -> list[dict]:
        return [
            {"path": op.path, "content": op.content}
            for op in self.operations
            if op.action == FileAction.MODIFY
        ]

    @property
    def files_to_delete(self) -> list[str]:
        return [
            op.path
            for op in self.operations
            if op.action == FileAction.DELETE
        ]

    def to_worker_plan(self) -> dict:
        """
        Convert to the dict format consumed by ExecutionWorker / PlanValidator.
        This is the bridge between ExecutionPlan and the execution pipeline.
        """
        return {
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "files_to_delete": self.files_to_delete,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id":     self.plan_id,
            "capability":  self.capability,
            "description": self.description,
            "operations":  [op.to_dict() for op in self.operations],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExecutionPlan":
        return cls(
            plan_id=d.get("plan_id", str(uuid4())),
            capability=d.get("capability", ""),
            description=d.get("description", ""),
            operations=tuple(
                FileOperation.from_dict(op) for op in d.get("operations", [])
            ),
        )

    def summary(self) -> str:
        creates  = sum(1 for op in self.operations if op.action == FileAction.CREATE)
        modifies = sum(1 for op in self.operations if op.action == FileAction.MODIFY)
        deletes  = sum(1 for op in self.operations if op.action == FileAction.DELETE)
        parts = []
        if creates:
            parts.append(f"{creates} create")
        if modifies:
            parts.append(f"{modifies} modify")
        if deletes:
            parts.append(f"{deletes} delete")
        return f"ExecutionPlan({', '.join(parts) or 'empty'})"
