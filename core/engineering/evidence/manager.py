"""
Engineering Evidence Manager — Public Facade
Genesis-034 Sprint-002

EvidenceManager is the single entry point for all evidence operations.
The agent and LifecycleManager import only this class.

Responsibilities:
  - Initialise evidence collection when a Genesis opens
  - Collect evidence from GitReader and WorkerResults automatically
  - Expose snapshot() for EngineeringReviewOSWorker consumption
  - Accept manual evidence additions for fields without auto-sources

Does NOT:
  - Instantiate workers directly
  - Call AI
  - Modify the repository
  - Own lifecycle state (LifecycleManager owns that)
"""

from __future__ import annotations

import logging
from typing import Optional

from core.engineering.evidence.collector import EvidenceCollector
from core.engineering.evidence.models import EvidenceSnapshot
from core.engineering.evidence.store import EvidenceStore

logger = logging.getLogger(__name__)


class EvidenceManager:
    """
    Public facade for Genesis evidence management.

    Public API (called by LifecycleManager and Agent):
        open(genesis, sprint)              — initialise for a new Genesis
        collect_git(genesis, repo_root)    — collect from GitReader
        collect_worker_result(genesis, r)  — collect from WorkerResult
        record(genesis, field, value)      — manual field entry
        record_desktop_validation(...)     — manual DV entry
        record_recommendation(...)         — set recommendation
        snapshot(genesis)                  — assemble EvidenceSnapshot
        has_evidence(genesis)              — True if evidence exists
    """

    def __init__(self, knowledge_engine) -> None:
        self._store     = EvidenceStore(knowledge_engine)
        self._collector = EvidenceCollector(self._store)

    # ── Lifecycle integration ──────────────────────────────────────────────────

    def open(self, genesis: str, sprint: str = "") -> None:
        """
        Initialise evidence collection for a new Genesis.
        Called by LifecycleManager when a Genesis is opened.
        Also collects initial git state automatically.
        """
        self._store.initialise(genesis, sprint)
        self._collector.collect_from_git(genesis)
        logger.info("[EVIDENCE] Evidence collection opened for Genesis-%s", genesis)

    # ── Automatic collection ───────────────────────────────────────────────────

    def collect_git(self, genesis: str, repo_root=None) -> None:
        """Collect current git state (commit, files). Safe to call repeatedly."""
        self._collector.collect_from_git(genesis, repo_root)

    def collect_worker_result(self, genesis: str, worker_result) -> None:
        """Collect evidence from a WorkerResult (e.g. SuiteRunnerWorker output)."""
        self._collector.collect_from_worker_result(genesis, worker_result)

    # ── Manual evidence entry ──────────────────────────────────────────────────

    def record(self, genesis: str, field_name: str, value) -> None:
        """
        Record any evidence field by name.
        Value may be str, list, dict, or int.
        """
        self._collector.record_field(genesis, field_name, value)

    def record_desktop_validation(
        self,
        genesis: str,
        status: str,
        scenarios: list[str],
        notes: Optional[str] = None,
    ) -> None:
        """Record desktop validation results."""
        self._collector.record_desktop_validation(genesis, status, scenarios, notes)

    def record_recommendation(
        self, genesis: str, recommendation: str, reason: str
    ) -> None:
        """Set the final recommendation and justification."""
        self._collector.record_recommendation(genesis, recommendation, reason)

    def mark_complete(self, genesis: str) -> None:
        """Mark evidence status as complete (called before closing)."""
        self._store.set_status(genesis, "complete")

    # ── Snapshot ───────────────────────────────────────────────────────────────

    def snapshot(self, genesis: str) -> EvidenceSnapshot:
        """
        Assemble all collected evidence into an EvidenceSnapshot.
        The snapshot's to_dict() is passed directly to EngineeringReviewOSWorker.
        """
        return self._store.snapshot(genesis)

    def has_evidence(self, genesis: str) -> bool:
        """True if any evidence has been stored for this genesis."""
        return self._store.has_evidence(genesis)
