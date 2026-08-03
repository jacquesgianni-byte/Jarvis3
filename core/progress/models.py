"""
Executive Intelligence — Progress Engine Models
Genesis-035 Sprint-001

Structured models for progress tracking.
ProgressState is separate from WorkStatus (Goal Intelligence's concern).
No duplicate storage — progress state augments existing records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ProgressState(str, Enum):
    """
    Progress states for any trackable engineering entity.
    Treated as data — no hardcoded state-machine logic.
    """
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    WAITING     = "waiting"
    BLOCKED     = "blocked"
    COMPLETED   = "completed"
    CANCELLED   = "cancelled"

    def label(self) -> str:
        return self.value.replace("_", " ").title()

    @property
    def is_terminal(self) -> bool:
        return self in (ProgressState.COMPLETED, ProgressState.CANCELLED)

    @property
    def is_open(self) -> bool:
        return not self.is_terminal


@dataclass
class ProgressRecord:
    """
    Progress state for a named entity (genesis, project, task).
    Stored by ProgressStore. Entity data lives in existing subsystems.
    """
    entity_id:   str            # e.g. "genesis_035", "task_parser"
    entity_type: str            # "genesis" | "project" | "task" | "goal"
    entity_name: str            # human-readable name
    state:       ProgressState
    blocker:     str = ""       # non-empty if BLOCKED or WAITING
    updated_at:  str = ""       # ISO datetime string


@dataclass
class ProgressSummary:
    """
    Aggregated progress view for a genesis or project.
    Assembled by ProgressEngine from multiple subsystems.
    No duplicate storage — built at query time.
    """
    entity_name:      str
    entity_type:      str
    state:            ProgressState
    blocker:          str = ""

    # From GoalTracker / ProjectTracker / TaskTracker
    active_goal:      str = ""
    active_project:   str = ""
    active_task:      str = ""
    completed_tasks:  list[str] = field(default_factory=list)
    open_tasks:       list[str] = field(default_factory=list)

    # From EvidenceStore
    test_passed:      int = 0
    test_failed:      int = 0
    desktop_status:   str = ""

    # From LifecycleStore
    lifecycle_status: str = ""
    opened_at:        str = ""
    closed_at:        str = ""

    def to_text(self) -> str:
        """Render a deterministic human-readable progress summary."""
        lines: list[str] = []

        lines.append(f"Progress: {self.entity_name}")
        lines.append(f"Status:   {self.state.label()}")

        if self.blocker:
            lines.append(f"Blocker:  {self.blocker}")

        if self.lifecycle_status:
            lines.append(f"Lifecycle: {self.lifecycle_status.title()}")

        if self.active_goal:
            lines.append(f"Goal:     {self.active_goal}")
        if self.active_project:
            lines.append(f"Project:  {self.active_project}")
        if self.active_task:
            lines.append(f"Task:     {self.active_task}")

        if self.completed_tasks:
            lines.append(f"Completed tasks ({len(self.completed_tasks)}):")
            for t in self.completed_tasks:
                lines.append(f"  ✓ {t}")

        if self.open_tasks:
            lines.append(f"Open tasks ({len(self.open_tasks)}):")
            for t in self.open_tasks:
                lines.append(f"  · {t}")

        if self.test_passed or self.test_failed:
            status = "✅" if self.test_failed == 0 else "❌"
            lines.append(
                f"Tests:    {status} {self.test_passed} passed, "
                f"{self.test_failed} failed"
            )

        if self.desktop_status:
            lines.append(f"Desktop:  {self.desktop_status.title()}")

        return "\n".join(lines)
