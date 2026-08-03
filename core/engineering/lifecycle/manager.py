"""
Engineering Lifecycle Manager — Manager
Genesis-034 Sprint-001

Orchestrates the Genesis lifecycle.
Open Genesis → track state.
Close Genesis → invoke EngineeringReviewOSWorker via Worker OS → persist → mark closed.

Responsibilities:
  - Accept lifecycle commands
  - Delegate state persistence to LifecycleStore
  - Delegate review execution to WorkerCoordinator (never direct worker construction)
  - Return human-readable responses

Does NOT:
  - Instantiate EngineeringReviewOSWorker directly
  - Modify KnowledgeEngine beyond lifecycle state
  - Make architectural decisions
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.lifecycle.detector import LifecycleDetector
from core.engineering.lifecycle.models import (
    GenesisLifecycleStatus,
    LifecycleCommand,
    LifecycleCommandKind,
)
from core.engineering.lifecycle.store import LifecycleStore
from core.engineering.evidence.manager import EvidenceManager  # Genesis-034 S2

logger = logging.getLogger(__name__)


class LifecycleManager:
    """
    Manages the Genesis engineering lifecycle.

    Public API (called by Agent):
        can_handle(utterance) -> bool
        handle(utterance, worker_coordinator, task_planner) -> str
    """

    def __init__(self, knowledge_engine) -> None:
        self._detector = LifecycleDetector()
        self._store    = LifecycleStore(knowledge_engine)
        self._evidence = EvidenceManager(knowledge_engine)  # Genesis-034 S2

    # ── Public ─────────────────────────────────────────────────────────────────

    def can_handle(self, utterance: str) -> bool:
        """Return True if this utterance is a lifecycle command."""
        return self._detector.detect(utterance) is not None

    def handle(
        self,
        utterance: str,
        worker_coordinator=None,
        task_planner=None,
    ) -> str:
        """
        Process a lifecycle command and return a response string.

        Args:
            utterance:          The user's raw message.
            worker_coordinator: WorkerCoordinator instance (required for close).
            task_planner:       TaskPlanner instance (required for close).

        Returns:
            Human-readable response string.
        """
        command = self._detector.detect(utterance)
        if command is None:
            return ""

        if command.kind == LifecycleCommandKind.OPEN_GENESIS:
            return self._open(command)

        if command.kind == LifecycleCommandKind.CLOSE_GENESIS:
            return self._close(command, worker_coordinator, task_planner)

        return ""

    # ── Open ───────────────────────────────────────────────────────────────────

    def _open(self, command: LifecycleCommand) -> str:
        genesis = command.genesis

        # Check for already-active genesis
        active = self._store.active_genesis()
        if active and active.genesis != genesis:
            return (
                f"Genesis-{active.genesis} is currently active. "
                f"Close it first with 'Close Genesis-{active.genesis}' "
                f"before opening Genesis-{genesis}."
            )

        # Check if this genesis is already open
        existing = self._store.get(genesis)
        if existing and existing.status == GenesisLifecycleStatus.ACTIVE:
            return f"Genesis-{genesis} is already active, sir."

        # Open it
        record = self._store.open_genesis(genesis)
        self._evidence.open(genesis)  # begin collecting evidence
        logger.info("[LIFECYCLE] Opened Genesis-%s at %s", genesis, record.opened_at)

        return (
            f"Genesis-{genesis} is now active, sir. "
            f"Engineering session opened at {record.opened_at[:10]}. "
            f"When development is complete, say 'Close Genesis-{genesis}' "
            f"to run the engineering review and archive the session."
        )

    # ── Close ──────────────────────────────────────────────────────────────────

    def _close(
        self,
        command: LifecycleCommand,
        worker_coordinator,
        task_planner,
    ) -> str:
        genesis = command.genesis

        # Check if already closed
        existing = self._store.get(genesis)
        if existing and existing.status == GenesisLifecycleStatus.CLOSED:
            return (
                f"Genesis-{genesis} is already closed, sir. "
                f"It was closed on {existing.closed_at[:10]}."
            )

        # Run Engineering Review via Worker OS
        self._evidence.mark_complete(genesis)
        self._evidence.collect_git(genesis)
        review_result = self._run_review(genesis, worker_coordinator, task_planner, self._evidence.snapshot(genesis))

        if not review_result["success"]:
            return (
                f"Engineering review failed for Genesis-{genesis}: "
                f"{review_result['error']}. "
                f"Genesis remains open — please resolve the issue and try again."
            )

        # Mark as closed
        record = self._store.close_genesis(genesis)

        # Build response
        json_path = review_result.get("json_path", "")
        md_path   = review_result.get("md_path", "")
        next_genesis = str(int(genesis) + 1).zfill(3)

        lines = [
            f"Genesis-{genesis} successfully closed, sir.",
            "",
            "Engineering review completed.",
            f"  JSON:     {json_path}",
            f"  Markdown: {md_path}",
            "",
            f"Genesis-{genesis} is now archived.",
            f"Ready to begin Genesis-{next_genesis}.",
        ]
        return "\n".join(lines)

    def _run_review(
        self,
        genesis: str,
        worker_coordinator,
        task_planner,
        evidence_snapshot=None,
    ) -> dict:
        """
        Run the EngineeringReviewOSWorker via the Worker OS pipeline.
        Never instantiates the worker directly.

        Returns a dict with: success, json_path, md_path, error.
        """
        if worker_coordinator is None or task_planner is None:
            return {"success": False, "error": "Worker OS not available."}

        from core.workers.models import WorkerTask

        # Dispatch via coordinator — exactly as proven in Genesis-033
        task = WorkerTask(
            task_type="run_engineering_review",
            payload={
                "description": f"Close Genesis-{genesis}",
                "genesis":     genesis,
                "evidence":    evidence_snapshot.to_dict() if evidence_snapshot and evidence_snapshot.is_reviewable() else None,
            },
            requester="lifecycle_manager",
        )

        try:
            result = worker_coordinator.run(task)
        except Exception as exc:
            logger.exception("[LIFECYCLE] Review worker raised.")
            return {"success": False, "error": str(exc)}

        if not result.success:
            return {"success": False, "error": result.error}

        worker_data = (
            result.data
            .get("results", {})
            .get("engineering_review_worker", {})
        )

        return {
            "success":   True,
            "json_path": worker_data.get("json_path", ""),
            "md_path":   worker_data.get("md_path", ""),
            "markdown":  worker_data.get("markdown", ""),
        }
