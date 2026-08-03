"""
Executive Intelligence — Progress Engine
Genesis-035 Sprint-001

Orchestrates progress tracking across the engineering system.
Reads from Goal Intelligence, Lifecycle, Evidence — never duplicates their data.
Owns only: progress state and blocker records.

Public API (called by Agent):
    can_handle(utterance) -> bool
    handle(utterance)     -> str
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from core.progress.detector import ProgressCommandKind, ProgressDetector
from core.progress.models import ProgressState, ProgressSummary
from core.progress.store import ProgressStore

logger = logging.getLogger(__name__)

# Genesis number extraction
_GENESIS_RE = re.compile(r"genesis[-\s]?(\d+)", re.IGNORECASE)


class ProgressEngine:
    """
    Executive Intelligence — Progress Engine.

    Reads from:
      - ProgressStore (owns: state, blockers)
      - GoalTracker, ProjectTracker, TaskTracker (via knowledge_engine)
      - LifecycleStore (via knowledge_engine)
      - EvidenceStore (via knowledge_engine)

    Never stores goal/project/task data — reads from existing subsystems only.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke       = knowledge_engine
        self._detector = ProgressDetector()
        self._store    = ProgressStore(knowledge_engine)

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        return self._detector.detect(utterance) is not None

    def handle(self, utterance: str) -> str:
        command = self._detector.detect(utterance)
        if command is None:
            return ""

        if command.kind == ProgressCommandKind.UPDATE_STATE:
            return self._update_state(command)

        if command.kind == ProgressCommandKind.QUERY_PROGRESS:
            return self._query_progress(command.subject)

        return ""

    # ── Update state ───────────────────────────────────────────────────────────

    def _update_state(self, command) -> str:
        subject = command.subject
        state   = command.state
        blocker = command.blocker

        # Determine entity type
        genesis_m = _GENESIS_RE.search(subject)
        if genesis_m:
            entity_type = "genesis"
            entity_id   = genesis_m.group(1).zfill(3)
            entity_name = f"Genesis-{entity_id}"
        else:
            # Assume task if no genesis number
            entity_type = "task"
            # Strip "the X task/project" -> just "X"
            cleaned = re.sub(r"^the\s+", "", subject, flags=re.IGNORECASE)
            cleaned = re.sub(
                r"\s+(?:task|project|feature|sprint)$", "", cleaned,
                flags=re.IGNORECASE
            ).strip()
            entity_id   = re.sub(r"[^a-z0-9]+", "_", cleaned.lower()).strip("_")
            entity_name = cleaned.title()

        self._store.set_state(entity_type, entity_id, entity_name, state, blocker)

        if state == ProgressState.BLOCKED:
            return (
                f"Understood, sir. {entity_name} is now blocked"
                + (f" — waiting for {blocker}." if blocker else ".")
            )
        if state == ProgressState.WAITING:
            return (
                f"Noted, sir. {entity_name} is waiting"
                + (f" for {blocker}." if blocker else ".")
            )
        if state == ProgressState.COMPLETED:
            return f"Marked as complete: {entity_name}."
        if state == ProgressState.IN_PROGRESS:
            return f"{entity_name} is now in progress, sir."
        if state == ProgressState.CANCELLED:
            return f"{entity_name} has been cancelled."

        return f"Progress state updated: {entity_name} → {state.label()}."

    # ── Query progress ─────────────────────────────────────────────────────────

    def _query_progress(self, subject: str) -> str:
        """Assemble a deterministic ProgressSummary from all subsystems."""
        genesis_m = _GENESIS_RE.search(subject)

        if genesis_m:
            genesis = genesis_m.group(1).zfill(3)
            summary = self._assemble_genesis_summary(genesis)
        else:
            summary = self._assemble_entity_summary(subject)

        return summary.to_text()

    def _assemble_genesis_summary(self, genesis: str) -> ProgressSummary:
        """Assemble progress summary for a genesis from all subsystems."""
        entity_name = f"Genesis-{genesis}"

        # Progress state (from ProgressStore)
        pr = self._store.get_state("genesis", genesis)
        state   = pr.state   if pr else ProgressState.NOT_STARTED
        blocker = pr.blocker if pr else ""

        # Lifecycle state (from LifecycleStore)
        lifecycle_status = ""
        opened_at        = ""
        closed_at        = ""
        try:
            from core.engineering.lifecycle.store import LifecycleStore
            lc_store = LifecycleStore(self._ke)
            lc_rec   = lc_store.get(genesis)
            if lc_rec:
                lifecycle_status = lc_rec.status.value
                opened_at        = lc_rec.opened_at
                closed_at        = lc_rec.closed_at
                # Sync: if lifecycle says closed, progress is completed
                if lifecycle_status == "closed" and state == ProgressState.NOT_STARTED:
                    state = ProgressState.COMPLETED
        except Exception:
            logger.debug("[PROGRESS] LifecycleStore not available.")

        # Evidence (from EvidenceStore)
        test_passed    = 0
        test_failed    = 0
        desktop_status = ""
        try:
            from core.engineering.evidence.store import EvidenceStore
            ev_store = EvidenceStore(self._ke)
            snap     = ev_store.snapshot(genesis)
            test_passed    = snap.test_results.get("passed", 0)
            test_failed    = snap.test_results.get("failed", 0)
            desktop_status = snap.desktop_validation.get("status", "")
        except Exception:
            logger.debug("[PROGRESS] EvidenceStore not available.")

        # Goal/Project/Task (from Goal Intelligence)
        active_goal    = ""
        active_project = ""
        active_task    = ""
        completed_tasks: list[str] = []
        open_tasks:      list[str] = []
        try:
            from core.goal_intelligence.goal_tracker import GoalTracker
            from core.goal_intelligence.project_tracker import ProjectTracker
            from core.goal_intelligence.task_tracker import TaskTracker
            from core.goal_intelligence.models import WorkStatus

            gt = GoalTracker(self._ke)
            pt = ProjectTracker(self._ke)
            tt = TaskTracker(self._ke)

            ag = gt.active_goal()
            if ag:
                active_goal = ag.title

            ap = pt.active_project()
            if ap:
                active_project = ap.title

            at = tt.active_task()
            if at:
                active_task = at.title

            all_tasks = tt.all_tasks()
            completed_tasks = [t.title for t in all_tasks if t.status == WorkStatus.COMPLETED]
            open_tasks      = [t.title for t in all_tasks if t.status == WorkStatus.ACTIVE]

        except Exception:
            logger.debug("[PROGRESS] Goal Intelligence not available.")

        return ProgressSummary(
            entity_name=entity_name,
            entity_type="genesis",
            state=state,
            blocker=blocker,
            active_goal=active_goal,
            active_project=active_project,
            active_task=active_task,
            completed_tasks=completed_tasks,
            open_tasks=open_tasks,
            test_passed=test_passed,
            test_failed=test_failed,
            desktop_status=desktop_status,
            lifecycle_status=lifecycle_status,
            opened_at=opened_at,
            closed_at=closed_at,
        )

    def _assemble_entity_summary(self, subject: str) -> ProgressSummary:
        """Assemble progress summary for a non-genesis entity (task/project)."""
        entity_id   = re.sub(r"[^a-z0-9]+", "_", subject.lower()).strip("_")
        entity_name = subject.title()

        pr    = self._store.get_state("task", entity_id)
        state = pr.state if pr else ProgressState.NOT_STARTED
        blocker = pr.blocker if pr else ""

        return ProgressSummary(
            entity_name=entity_name,
            entity_type="task",
            state=state,
            blocker=blocker,
        )
