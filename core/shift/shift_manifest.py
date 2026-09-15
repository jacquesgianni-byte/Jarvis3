"""
Jarvis ShiftController — Shift Manifest & Finding Records (Sprint A)

ShiftManifest is the authoritative record of an autonomous shift.
It is written to data/shift_manifests/<shift_id>.json (runtime data path).
It never enters an engineering commit.

FindingRecord tracks one discovered defect from discovery through resolution.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from core.shift.evidence import DiagnosisHypothesis, EvidenceBundle
from core.shift.risk_classifier import RiskTier

# Runtime output path — must match RUNTIME_DATA_PATHS entry
MANIFEST_DIR = Path("data/shift_manifests")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FindingStatus(Enum):
    OPEN        = auto()   # discovered, not yet attempted
    IN_REPAIR   = auto()   # repair sprint in progress
    RESOLVED    = auto()   # repair succeeded, post-commit check passed
    ABANDONED   = auto()   # max repair attempts exhausted
    DEFERRED    = auto()   # Chief declined / MEDIUM/HIGH awaiting manual sprint

    def label(self) -> str:
        return self.name


class RepairOutcome(Enum):
    SUCCESS          = auto()   # repair committed, validation passed
    ROLLBACK         = auto()   # validation failed, rollback succeeded
    ROLLBACK_FAILED  = auto()   # validation failed, rollback also failed → HARD STOP
    ABANDONED        = auto()   # max attempts exhausted
    SKIPPED          = auto()   # not attempted (protected / deferred)

    def label(self) -> str:
        return self.name


class ShiftTrajectory(Enum):
    """
    Overall shift health after each repair cycle.
    Two consecutive DEGRADED → HARD STOP.
    """
    IMPROVING  = auto()   # fewer failures than previous cycle
    STABLE     = auto()   # same failure count
    DEGRADED   = auto()   # more failures than previous cycle

    def label(self) -> str:
        return self.name


class ShiftStopReason(Enum):
    COMPLETED              = auto()   # natural completion
    HARD_STOP_SOURCE_DIRTY = auto()   # unexpected source-dirty file
    HARD_STOP_PATH_TRAVERSAL = auto()
    HARD_STOP_PROTECTED_COMPONENT = auto()
    HARD_STOP_RUNTIME_PATH_EXPANSION = auto()
    HARD_STOP_COMMIT_BOUNDARY = auto()
    HARD_STOP_ROLLBACK_FAILED = auto()
    HARD_STOP_CONSECUTIVE_DEGRADED = auto()
    HARD_STOP_SERVER_UNRESPONSIVE = auto()
    HARD_STOP_MANIFEST_WRITE_FAILED = auto()
    HARD_STOP_REMOTE_STOP = auto()   # Chief issued STOP from Android
    CLEAN_NO_FINDINGS      = auto()   # suite green, nothing to repair

    def label(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# SuiteResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SuiteResult:
    passed:  int
    skipped: int
    failed:  int
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_green(self) -> bool:
        return self.failed == 0

    def regressed_from(self, baseline: "SuiteResult") -> bool:
        """True if this result has more failures than baseline."""
        return self.failed > baseline.failed

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "skipped": self.skipped,
            "failed": self.failed,
            "captured_at": self.captured_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# FindingRecord
# ---------------------------------------------------------------------------

@dataclass
class FindingRecord:
    """
    Tracks one discovered defect through its full lifecycle.

    Generative expansion rules (enforced by ShiftManifest):
        - Children may only be created from a RESOLVED parent.
        - Maximum 3 children per parent.
        - Same defect class and file path as parent.
        - Children are low priority.
    """
    finding_id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    shift_id:             str = ""
    discovered_at:        datetime = field(default_factory=lambda: datetime.now(UTC))
    test_id:              str = ""
    evidence:             Optional[EvidenceBundle] = None
    risk:                 Optional[RiskTier] = None
    status:               FindingStatus = FindingStatus.OPEN
    diagnosis_hypothesis: Optional[DiagnosisHypothesis] = None  # advisory only
    parent_finding_id:    Optional[str] = None
    child_finding_ids:    list[str] = field(default_factory=list)
    repair_attempts:      int = 0
    pre_repair_sha:       Optional[str] = None
    repair_sha:           Optional[str] = None
    outcome:              Optional[RepairOutcome] = None
    outcome_note:         str = ""

    MAX_REPAIR_ATTEMPTS: int = 3
    MAX_CHILDREN:        int = 3

    @property
    def attempts_exhausted(self) -> bool:
        return self.repair_attempts >= self.MAX_REPAIR_ATTEMPTS

    @property
    def can_expand(self) -> bool:
        return (
            self.status == FindingStatus.RESOLVED
            and len(self.child_finding_ids) < self.MAX_CHILDREN
        )

    def record_repair_start(self, pre_repair_sha: str) -> None:
        self.repair_attempts += 1
        self.pre_repair_sha = pre_repair_sha
        self.status = FindingStatus.IN_REPAIR

    def record_repair_commit(self, repair_sha: str) -> None:
        self.repair_sha = repair_sha

    def record_outcome(self, outcome: RepairOutcome, note: str = "") -> None:
        self.outcome = outcome
        self.outcome_note = note
        if outcome == RepairOutcome.SUCCESS:
            self.status = FindingStatus.RESOLVED
        elif outcome == RepairOutcome.ABANDONED:
            self.status = FindingStatus.ABANDONED
        elif outcome == RepairOutcome.SKIPPED:
            self.status = FindingStatus.DEFERRED

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "shift_id": self.shift_id,
            "discovered_at": self.discovered_at.isoformat(),
            "test_id": self.test_id,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "risk": self.risk.name if self.risk else None,
            "status": self.status.label(),
            "diagnosis_hypothesis": (
                self.diagnosis_hypothesis.to_dict()
                if self.diagnosis_hypothesis else None
            ),
            "parent_finding_id": self.parent_finding_id,
            "child_finding_ids": self.child_finding_ids,
            "repair_attempts": self.repair_attempts,
            "pre_repair_sha": self.pre_repair_sha,
            "repair_sha": self.repair_sha,
            "outcome": self.outcome.label() if self.outcome else None,
            "outcome_note": self.outcome_note,
        }


# ---------------------------------------------------------------------------
# ShiftManifest
# ---------------------------------------------------------------------------

@dataclass
class ShiftManifest:
    """
    Authoritative record of one autonomous shift.

    Written to data/shift_manifests/<shift_id>.json after every
    state change. Never enters an engineering commit.
    """
    shift_id:                  str = field(default_factory=lambda: str(uuid.uuid4()))
    stage:                     int = 1
    start_time:                datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time:                  Optional[datetime] = None
    stop_reason:               Optional[ShiftStopReason] = None
    stop_detail:               str = ""
    baseline_suite:            Optional[SuiteResult] = None
    current_suite:             Optional[SuiteResult] = None
    findings:                  list[FindingRecord] = field(default_factory=list)
    repair_cycles_total:       int = 0
    primary_findings_resolved: int = 0
    corrective_cycles:         int = 0
    consecutive_degraded:      int = 0
    trajectory:                Optional[ShiftTrajectory] = None
    shift_report:              Optional[str] = None

    QUEUE_CAP: int = 10
    MAX_REPAIR_CYCLES: int = 20
    MAX_CONSECUTIVE_DEGRADED: int = 2

    # ------------------------------------------------------------------
    # Finding management
    # ------------------------------------------------------------------

    def add_finding(self, finding: FindingRecord) -> None:
        finding.shift_id = self.shift_id
        self.findings.append(finding)

    def open_findings(self) -> list[FindingRecord]:
        return [f for f in self.findings if f.status == FindingStatus.OPEN]

    def finding_by_id(self, finding_id: str) -> Optional[FindingRecord]:
        return next((f for f in self.findings if f.finding_id == finding_id), None)

    def queue_is_capped(self) -> bool:
        return len(self.open_findings()) >= self.QUEUE_CAP

    def can_expand(self, parent_finding_id: str) -> bool:
        """True if generative expansion is allowed from this parent."""
        if self.queue_is_capped():
            return False
        parent = self.finding_by_id(parent_finding_id)
        return parent is not None and parent.can_expand

    def create_child_finding(
        self,
        parent_finding_id: str,
        test_id: str,
        evidence: EvidenceBundle,
    ) -> Optional[FindingRecord]:
        """
        Create a child finding from a resolved parent.
        Returns None if expansion is not permitted.
        """
        if not self.can_expand(parent_finding_id):
            return None
        parent = self.finding_by_id(parent_finding_id)
        child = FindingRecord(
            shift_id=self.shift_id,
            test_id=test_id,
            evidence=evidence,
            parent_finding_id=parent_finding_id,
        )
        parent.child_finding_ids.append(child.finding_id)
        self.findings.append(child)
        return child

    # ------------------------------------------------------------------
    # Cycle tracking
    # ------------------------------------------------------------------

    def record_cycle(self, outcome: RepairOutcome) -> None:
        self.repair_cycles_total += 1
        if outcome == RepairOutcome.SUCCESS:
            self.primary_findings_resolved += 1
        elif outcome == RepairOutcome.ROLLBACK:
            self.corrective_cycles += 1

    def update_trajectory(self, previous_suite: SuiteResult) -> ShiftTrajectory:
        """
        Compare current suite against previous to derive trajectory.
        Updates consecutive_degraded counter.
        Two consecutive DEGRADED is a hard stop condition (checked by caller).
        """
        if self.current_suite is None or previous_suite is None:
            self.trajectory = ShiftTrajectory.STABLE
            return self.trajectory

        if self.current_suite.failed < previous_suite.failed:
            self.trajectory = ShiftTrajectory.IMPROVING
            self.consecutive_degraded = 0
        elif self.current_suite.failed == previous_suite.failed:
            self.trajectory = ShiftTrajectory.STABLE
            self.consecutive_degraded = 0
        else:
            self.trajectory = ShiftTrajectory.DEGRADED
            self.consecutive_degraded += 1

        return self.trajectory

    @property
    def consecutive_degraded_stop(self) -> bool:
        return self.consecutive_degraded >= self.MAX_CONSECUTIVE_DEGRADED

    @property
    def cycle_limit_reached(self) -> bool:
        return self.repair_cycles_total >= self.MAX_REPAIR_CYCLES

    @property
    def corrective_cycle_ratio(self) -> float:
        if self.repair_cycles_total == 0:
            return 0.0
        return self.corrective_cycles / self.repair_cycles_total

    # ------------------------------------------------------------------
    # Serialisation & persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "shift_id": self.shift_id,
            "stage": self.stage,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "stop_reason": self.stop_reason.label() if self.stop_reason else None,
            "stop_detail": self.stop_detail,
            "baseline_suite": self.baseline_suite.to_dict() if self.baseline_suite else None,
            "current_suite": self.current_suite.to_dict() if self.current_suite else None,
            "findings": [f.to_dict() for f in self.findings],
            "repair_cycles_total": self.repair_cycles_total,
            "primary_findings_resolved": self.primary_findings_resolved,
            "corrective_cycles": self.corrective_cycles,
            "corrective_cycle_ratio": round(self.corrective_cycle_ratio, 3),
            "consecutive_degraded": self.consecutive_degraded,
            "trajectory": self.trajectory.label() if self.trajectory else None,
            "shift_report": self.shift_report,
        }

    def save(self, repo_root: Path) -> bool:
        """
        Persist manifest to data/shift_manifests/<shift_id>.json.
        Returns True on success, False on failure (caller should HARD STOP).
        """
        try:
            manifest_dir = repo_root / MANIFEST_DIR
            manifest_dir.mkdir(parents=True, exist_ok=True)
            out_path = manifest_dir / f"{self.shift_id}.json"
            out_path.write_text(
                json.dumps(self.to_dict(), indent=2),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def finalise(
        self,
        stop_reason: ShiftStopReason,
        stop_detail: str = "",
        shift_report: Optional[str] = None,
    ) -> None:
        self.end_time = datetime.now(UTC)
        self.stop_reason = stop_reason
        self.stop_detail = stop_detail
        if shift_report:
            self.shift_report = shift_report
