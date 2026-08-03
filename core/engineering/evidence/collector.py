"""
Engineering Evidence Manager — Collector
Genesis-034 Sprint-002

Collects evidence automatically from existing Jarvis subsystems:
  - GitReader    → commits, files added/modified
  - WorkerResult → test results (from SuiteRunnerWorker)

The collector is passive — it observes and records.
It never modifies the repository or calls AI.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.evidence.store import EvidenceStore

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """
    Collects engineering evidence from Jarvis subsystems.

    Called by:
      - LifecycleManager.open_genesis() → initialise
      - Agent post-turn hook → collect_from_git() after commits
      - WorkerCoordinator result handler → collect_from_worker_result()

    Never constructs workers or calls AI.
    """

    def __init__(self, store: EvidenceStore) -> None:
        self._store = store

    # ── Git collection ─────────────────────────────────────────────────────────

    def collect_from_git(self, genesis: str, repo_root=None) -> None:
        """
        Collect current git state: last commit and modified files.
        Safe to call repeatedly — deduplicates commits automatically.
        """
        try:
            from core.engineering.git.reader import GitReader
            reader = GitReader(repo_root)
            status = reader.status()

            if not status.available:
                logger.debug("[EVIDENCE] Git unavailable: %s", status.error)
                return

            # Append last commit if not already recorded
            commit = status.last_commit
            if commit.short_hash and commit.short_hash != "unknown":
                self._store.append_commit(genesis, commit.short_hash)

            # Update files (overwrite — git status is always current)
            if status.modified:
                self._store.set_files(
                    genesis,
                    files_added=[],
                    files_modified=list(status.modified),
                )

        except Exception:
            logger.exception("[EVIDENCE] Git collection failed — skipping.")

    def collect_from_worker_result(
        self, genesis: str, worker_result
    ) -> None:
        """
        Extract evidence from a WorkerResult produced by SuiteRunnerWorker.
        Safe to call with any WorkerResult — ignores non-test results.
        """
        try:
            if not hasattr(worker_result, "data"):
                return

            data = worker_result.data or {}

            # SuiteRunnerWorker result
            if "passed" in data and "failed" in data:
                self._store.set_test_results(
                    genesis,
                    passed=int(data.get("passed", 0)),
                    skipped=int(data.get("skipped", 0)),
                    failed=int(data.get("failed", 0)),
                    warnings=int(data.get("warnings", 0)),
                )
                logger.info(
                    "[EVIDENCE] Test results recorded from WorkerResult: "
                    "passed=%d failed=%d",
                    data.get("passed", 0), data.get("failed", 0),
                )

            # Coordinator aggregate result containing suite_runner_worker
            results = data.get("results", {})
            suite_data = results.get("suite_runner_worker", {})
            if "passed" in suite_data:
                self._store.set_test_results(
                    genesis,
                    passed=int(suite_data.get("passed", 0)),
                    skipped=int(suite_data.get("skipped", 0)),
                    failed=int(suite_data.get("failed", 0)),
                )

        except Exception:
            logger.exception("[EVIDENCE] Worker result collection failed — skipping.")

    # ── Manual evidence entry ──────────────────────────────────────────────────

    def record_desktop_validation(
        self,
        genesis: str,
        status: str,
        scenarios: list[str],
        notes: Optional[str] = None,
    ) -> None:
        """Record desktop validation results manually."""
        self._store.set_desktop_validation(genesis, status, scenarios, notes)
        logger.info("[EVIDENCE] Desktop validation recorded: %s", status)

    def record_recommendation(
        self, genesis: str, recommendation: str, reason: str
    ) -> None:
        """Record the final recommendation."""
        self._store.set_recommendation(genesis, recommendation, reason)

    def record_field(self, genesis: str, field_name: str, value) -> None:
        """Record any evidence field by name."""
        self._store.set_field(genesis, field_name, value)
