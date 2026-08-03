"""
Executive Intelligence — Dashboard Engine
Genesis-035 Sprint-002

Assembles the Executive Dashboard from all existing subsystems.
Read-only. No storage. One-way dependency direction.

Reads from (never modifies):
  - GoalTracker, ProjectTracker, TaskTracker  (Goal Intelligence)
  - ProgressStore                              (Progress Engine)
  - LifecycleStore                            (Engineering Lifecycle)
  - EvidenceStore                             (Evidence Manager)
  - GitReader                                  (Engineering Git)

Produces:
  - ExecutiveDashboard with deterministic sections and recommendation

No AI. No free-form text. Rule-based recommendations only.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.executive.models import ExecutiveDashboard, ExecutiveSection

logger = logging.getLogger(__name__)

# ── Trigger phrases ────────────────────────────────────────────────────────────
_TRIGGERS: frozenset[str] = frozenset({
    "engineering briefing",
    "engineering briefing.",
    "executive dashboard",
    "executive dashboard.",
    "project status",
    "project status.",
    "give me a briefing",
    "give me the briefing",
    "dashboard",
    "briefing",
    "show dashboard",
    "show briefing",
    "engineering status",
    "engineering status.",
})


class ExecutiveDashboardEngine:
    """
    Assembles the Executive Dashboard from existing subsystems.

    Public API (called by Agent):
        can_handle(utterance) -> bool
        handle(utterance)     -> str
        build()               -> ExecutiveDashboard
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        return utterance.strip().lower().rstrip("?!.") in _TRIGGERS or \
               utterance.strip().lower() in _TRIGGERS

    def handle(self, utterance: str) -> str:
        dashboard = self.build()
        return dashboard.to_text()

    def build(self) -> ExecutiveDashboard:
        """Assemble the full dashboard. Never raises — always returns something."""
        sections: list[ExecutiveSection] = []

        # ── Goal section ───────────────────────────────────────────────────────
        sections.append(self._goal_section())

        # ── Project section ────────────────────────────────────────────────────
        sections.append(self._project_section())

        # ── Task section ───────────────────────────────────────────────────────
        sections.append(self._task_section())

        # ── Progress section ───────────────────────────────────────────────────
        sections.append(self._progress_section())

        # ── Engineering section ────────────────────────────────────────────────
        sections.append(self._engineering_section())

        # ── Quality section ────────────────────────────────────────────────────
        sections.append(self._quality_section())

        # ── Recommendation ────────────────────────────────────────────────────
        recommendation = self._derive_recommendation(sections)

        return ExecutiveDashboard(
            sections=sections,
            recommendation=recommendation,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Section builders ───────────────────────────────────────────────────────

    def _goal_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            from core.goal_intelligence.goal_tracker import GoalTracker
            gt     = GoalTracker(self._ke)
            goal   = gt.active_goal()
            if goal:
                lines.append(f"Goal:   {goal.title}")
                lines.append(f"Status: {goal.status.value.title()}")
            else:
                return ExecutiveSection(title="GOAL", empty=True)
        except Exception:
            logger.debug("[DASHBOARD] Goal section unavailable.")
            return ExecutiveSection(title="GOAL", empty=True)
        return ExecutiveSection(title="GOAL", lines=lines)

    def _project_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            from core.goal_intelligence.project_tracker import ProjectTracker
            from core.engineering.lifecycle.store import LifecycleStore

            pt      = ProjectTracker(self._ke)
            project = pt.active_project()

            if project:
                lines.append(f"Project: {project.title}")
                lines.append(f"Status:  {project.status.value.title()}")

            # Lifecycle state
            lc_store = LifecycleStore(self._ke)
            active   = lc_store.active_genesis()
            if active:
                lines.append(f"Genesis: {active.genesis} (active)")
                if active.opened_at:
                    lines.append(f"Opened:  {active.opened_at[:10]}")
            else:
                # Check most recent closed genesis
                all_recs = lc_store.all_records()
                if all_recs:
                    latest = sorted(all_recs, key=lambda r: r.closed_at or r.opened_at, reverse=True)[0]
                    lines.append(f"Genesis: {latest.genesis} ({latest.status.value})")

            if not lines:
                return ExecutiveSection(title="PROJECT", empty=True)

        except Exception:
            logger.debug("[DASHBOARD] Project section unavailable.")
            return ExecutiveSection(title="PROJECT", empty=True)
        return ExecutiveSection(title="PROJECT", lines=lines)

    def _task_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            from core.goal_intelligence.task_tracker import TaskTracker
            from core.goal_intelligence.models import WorkStatus

            tt   = TaskTracker(self._ke)
            task = tt.active_task()
            all_tasks = tt.all_tasks()

            if task:
                lines.append(f"Current: {task.title}")
                lines.append(f"Status:  {task.status.value.title()}")

            completed = [t.title for t in all_tasks if t.status == WorkStatus.COMPLETED]
            if completed:
                lines.append(f"Done ({len(completed)}): {', '.join(completed[:3])}")

            open_tasks = [t.title for t in all_tasks if t.status == WorkStatus.ACTIVE and t != task]
            if open_tasks:
                lines.append(f"Open ({len(open_tasks)}): {', '.join(open_tasks[:3])}")

            if not lines:
                return ExecutiveSection(title="TASK", empty=True)

        except Exception:
            logger.debug("[DASHBOARD] Task section unavailable.")
            return ExecutiveSection(title="TASK", empty=True)
        return ExecutiveSection(title="TASK", lines=lines)

    def _progress_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            from core.progress.store import ProgressStore
            from core.progress.models import ProgressState

            ps       = ProgressStore(self._ke)
            all_recs = ps.all_records()

            if not all_recs:
                return ExecutiveSection(title="PROGRESS", empty=True)

            for rec in all_recs:
                label = f"{rec.entity_type.title()}: {rec.entity_name}"
                state = rec.state.label()
                lines.append(f"{label} — {state}")
                if rec.blocker:
                    lines.append(f"  ⚠ Blocker: {rec.blocker}")

        except Exception:
            logger.debug("[DASHBOARD] Progress section unavailable.")
            return ExecutiveSection(title="PROGRESS", empty=True)
        return ExecutiveSection(title="PROGRESS", lines=lines)

    def _engineering_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            # Latest commit from GitReader
            from core.engineering.git.reader import GitReader
            reader     = GitReader()
            git_status = reader.status()
            if git_status.available:
                commit = git_status.last_commit
                lines.append(f"Branch: {git_status.branch}")
                lines.append(f"Commit: {commit.short_hash} — {commit.message[:50]}")
                if git_status.dirty:
                    lines.append(f"Tree:   dirty ({len(git_status.modified)} modified)")
                else:
                    lines.append("Tree:   clean")
        except Exception:
            logger.debug("[DASHBOARD] Git section unavailable.")

        # Latest review recommendation
        try:
            import os, json
            review_dir = "engineering_reviews"
            if os.path.isdir(review_dir):
                files = sorted(
                    [f for f in os.listdir(review_dir) if f.endswith("_review.json")],
                    reverse=True,
                )
                if files:
                    with open(os.path.join(review_dir, files[0]), encoding="utf-8") as f:
                        data = json.load(f)
                    review   = data.get("review", {})
                    genesis  = review.get("genesis", "?")
                    sprint   = review.get("sprint",  "?")
                    rec_val  = review.get("recommendation", "")
                    lines.append(f"Review: Genesis-{genesis} Sprint-{sprint}")
                    if rec_val:
                        lines.append(f"  → {rec_val}")
        except Exception:
            logger.debug("[DASHBOARD] Review file unavailable.")

        if not lines:
            return ExecutiveSection(title="ENGINEERING", empty=True)
        return ExecutiveSection(title="ENGINEERING", lines=lines)

    def _quality_section(self) -> ExecutiveSection:
        lines: list[str] = []
        try:
            from core.engineering.lifecycle.store import LifecycleStore
            from core.engineering.evidence.store import EvidenceStore

            lc_store = LifecycleStore(self._ke)
            active   = lc_store.active_genesis()
            genesis  = active.genesis if active else None

            if genesis:
                ev_store = EvidenceStore(self._ke)
                snap     = ev_store.snapshot(genesis)

                tr = snap.test_results
                if tr.get("passed") or tr.get("failed"):
                    status = "✅" if tr.get("failed", 0) == 0 else "❌"
                    lines.append(
                        f"Tests:   {status} {tr.get('passed', 0)} passed, "
                        f"{tr.get('failed', 0)} failed, "
                        f"{tr.get('skipped', 0)} skipped"
                    )

                dv = snap.desktop_validation
                if dv.get("status") and dv["status"] != "pending":
                    dv_icon = "✅" if dv["status"] == "passed" else "⚠"
                    lines.append(f"Desktop: {dv_icon} {dv['status'].title()}")

        except Exception:
            logger.debug("[DASHBOARD] Quality section unavailable.")

        if not lines:
            return ExecutiveSection(title="QUALITY", empty=True)
        return ExecutiveSection(title="QUALITY", lines=lines)

    # ── Recommendation ─────────────────────────────────────────────────────────

    def _derive_recommendation(self, sections: list[ExecutiveSection]) -> str:
        """
        Derive a deterministic next-action recommendation from dashboard state.
        Rule-based only — no AI, no free-form text.
        """
        try:
            from core.progress.store import ProgressStore
            from core.progress.models import ProgressState

            ps       = ProgressStore(self._ke)
            all_recs = ps.all_records()

            # Rule 1: Blocked → resolve blocker
            blocked = [r for r in all_recs if r.state == ProgressState.BLOCKED]
            if blocked:
                blocker = blocked[0].blocker
                if blocker:
                    return f"Resolve blocker: {blocker}."
                return f"Resolve blocker on {blocked[0].entity_name}."

            # Rule 2: Waiting → complete what's being waited on
            waiting = [r for r in all_recs if r.state == ProgressState.WAITING]
            if waiting:
                w = waiting[0]
                if w.blocker:
                    return f"Complete: {w.blocker}."
                return "Complete pending dependency."

            # Rule 3: Check quality signals
            try:
                from core.engineering.lifecycle.store import LifecycleStore
                from core.engineering.evidence.store import EvidenceStore
                lc = LifecycleStore(self._ke)
                active = lc.active_genesis()
                if active:
                    ev = EvidenceStore(self._ke)
                    snap = ev.snapshot(active.genesis)
                    tr = snap.test_results
                    if tr.get("failed", 0) > 0:
                        return f"Fix {tr['failed']} failing test(s) before proceeding."
                    dv = snap.desktop_validation
                    if dv.get("status") == "pending" or not dv.get("status"):
                        return "Desktop validation should be completed."
            except Exception:
                pass

            # Rule 4: In progress → continue
            in_progress = [r for r in all_recs if r.state == ProgressState.IN_PROGRESS]
            if in_progress:
                return f"Continue {in_progress[0].entity_name}."

            # Rule 5: Nothing tracked
            return "Set Genesis status with: 'Genesis-0XX is in progress.'"

        except Exception:
            logger.debug("[DASHBOARD] Recommendation unavailable.")
            return "Check engineering status."
