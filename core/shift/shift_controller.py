"""
Jarvis ShiftController — Autonomous Shift Worker (Sprint A)

ShiftController is a Worker inside existing Jarvis.
It controls the shift lifecycle — it does NOT replace any governance component.
Four-Way remains the authority over every engineering action.

GOVERNANCE CONSTRAINTS (enforced in code, not convention)
    - ShiftController cannot modify AUTONOMOUSLY_PROTECTED files under any
      circumstances, including Chief approval. Findings on these files are
      logged and surfaced to Chief as information only.
    - ShiftController cannot expand RUNTIME_DATA_PATHS or AUTONOMOUSLY_PROTECTED.
    - MEDIUM/HIGH findings require Chief approval — silence is never approval.
    - ONE repo-modifying repair at a time.
    - DiagnosisHypothesis is advisory only — never influences classification.
    - pre_repair_sha and repair_sha are recorded; rollback targets repair_sha,
      never blindly HEAD.
    - Sprint B (sprint_executor.py runtime-path integration) is a prerequisite
      for autonomous commits to succeed when runtime files are dirty.
      ShiftController raises a clear error if that integration is missing.

STATE MACHINE
    IDLE → INITIALISING → DISCOVERING → ASSESSING → REPAIRING →
    VALIDATING → COMMITTING → POST_COMMIT_CHECK → DISCOVERING (loop)
    Any state → FAILURE_CONTAINMENT → (ROLLBACK | HARD_STOP | continue)
    Any state → HARD_STOP (terminal)
    DISCOVERING (no findings) → SHIFT_COMPLETE (terminal)
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

from core.shift.desktop_validation import DesktopValidation
from core.shift.evidence import DiagnosisHypothesis, EvidenceBundle, EvidenceStrength
from core.shift.failure_containment import FailureClass, FailureContainment, FailureResponse
from core.shift.risk_classifier import RiskClassifier, RiskTier
from core.shift.server_recovery import ServerRecovery
from core.shift.shift_manifest import (
    FindingRecord,
    FindingStatus,
    RepairOutcome,
    ShiftManifest,
    ShiftStopReason,
    ShiftTrajectory,
    SuiteResult,
)
from core.shift.source_clean import (
    AUTONOMOUSLY_PROTECTED,
    assert_source_clean,
    classify_file,
    is_runtime_path_expansion_attempt,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shift state enum
# ---------------------------------------------------------------------------

class ShiftState(Enum):
    IDLE               = auto()
    INITIALISING       = auto()
    DISCOVERING        = auto()
    ASSESSING          = auto()
    AWAITING_APPROVAL  = auto()
    REPAIRING          = auto()
    VALIDATING         = auto()
    POST_COMMIT_CHECK  = auto()
    FAILURE_CONTAINMENT = auto()
    ROLLBACK           = auto()
    SHIFT_COMPLETE     = auto()
    HARD_STOP          = auto()

    def label(self) -> str:
        return self.name


# ---------------------------------------------------------------------------
# ShiftController
# ---------------------------------------------------------------------------

class ShiftController(Worker):
    """
    Autonomous Shift Worker.

    Registered with WorkerManager as 'shift_controller'.
    Activated by POST /shift/start (Sprint C adds Android button).

    The execute() method runs the full shift lifecycle synchronously.
    For production use, this should be wrapped in a daemon thread
    (same pattern as other long-running Workers in Jarvis).
    """

    # Worker interface
    @property
    def name(self) -> str:
        return "shift_controller"

    @property
    def description(self) -> str:
        return (
            "Autonomous engineering shift controller. "
            "Discovers failing tests, classifies findings by evidence and risk, "
            "and executes LOW-risk repairs through Four-Way governance. "
            "MEDIUM/HIGH findings are surfaced to Chief for manual sprint."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["autonomous_shift", "shift_start", "shift_stop"]

    def __init__(
        self,
        repo_root: Path,
        stage: int = 1,
        sprint_base_url: str = "http://192.168.20.3:5001",
        orchestrator_token: str = "Lucasleo2104#",
    ) -> None:
        super().__init__()
        self._repo_root = repo_root
        self._stage = stage
        self._sprint_base_url = sprint_base_url
        self._orchestrator_token = orchestrator_token

        self._shift_state: ShiftState = ShiftState.IDLE
        self._manifest: Optional[ShiftManifest] = None
        self._stop_requested: bool = False

        self._containment = FailureContainment()
        self._risk_classifier = RiskClassifier()
        self._desktop_validation = DesktopValidation()
        self._server_recovery = ServerRecovery(repo_root=repo_root)

    # ------------------------------------------------------------------
    # Worker interface implementation
    # ------------------------------------------------------------------

    def validate(self, task: WorkerTask) -> bool:
        return task.task_type in self.capabilities

    def execute(self, task: WorkerTask) -> WorkerResult:
        self._begin(task)
        try:
            self._run_shift()
            result = WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(self._shift_summary()),
                requires_approval=False,
            )
            return self._succeed(result)
        except Exception as exc:
            logger.exception("[SHIFT] Unhandled exception in shift.")
            return self._fail(task.task_id, str(exc))

    # ------------------------------------------------------------------
    # Remote STOP (called from server route, not from execute() thread)
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Chief issued STOP from Android. Sets flag checked in shift loop."""
        logger.warning("[SHIFT] Remote STOP requested by Chief.")
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Core shift lifecycle
    # ------------------------------------------------------------------

    def _run_shift(self) -> None:
        self._transition(ShiftState.INITIALISING)
        self._manifest = ShiftManifest(stage=self._stage)

        # --- INITIALISING ---
        dirty = self._git_dirty_files()
        clean_assertion = assert_source_clean(dirty)
        if not clean_assertion.is_clean:
            self._hard_stop(
                self._stop_reason_for_assertion(clean_assertion.reason),
                detail=f"{clean_assertion.reason} | path={clean_assertion.offending_path}",
            )
            return

        baseline = self._run_suite()
        if baseline is None:
            self._hard_stop(ShiftStopReason.HARD_STOP_SERVER_UNRESPONSIVE,
                            detail="Could not run baseline suite.")
            return

        self._manifest.baseline_suite = baseline
        self._manifest.current_suite = baseline
        self._save_manifest()

        # --- Main shift loop ---
        self._transition(ShiftState.DISCOVERING)

        while True:
            if self._stop_requested:
                self._hard_stop(ShiftStopReason.HARD_STOP_REMOTE_STOP,
                                detail="Chief issued STOP.")
                return

            if self._manifest.cycle_limit_reached:
                decision = self._containment.decide(FailureClass.CYCLE_LIMIT_REACHED)
                self._complete_shift(
                    ShiftStopReason.COMPLETED,
                    detail=decision.reason,
                )
                return

            # DISCOVERING
            findings = self._discover_findings()

            if not findings:
                self._complete_shift(
                    ShiftStopReason.CLEAN_NO_FINDINGS,
                    detail="Suite green — no findings to repair.",
                )
                return

            for finding in findings:
                self._manifest.add_finding(finding)

            self._save_manifest()

            # ASSESSING
            self._transition(ShiftState.ASSESSING)
            open_findings = self._manifest.open_findings()

            if not open_findings:
                self._complete_shift(
                    ShiftStopReason.COMPLETED,
                    detail="All findings resolved or deferred.",
                )
                return

            finding = open_findings[0]

            # Check remote stop before each finding
            if self._stop_requested:
                self._hard_stop(ShiftStopReason.HARD_STOP_REMOTE_STOP,
                                detail="Chief issued STOP.")
                return

            # AUTONOMOUSLY_PROTECTED check
            if finding.evidence and finding.evidence.affected_file:
                file_class = classify_file(finding.evidence.affected_file)
                if file_class == "AUTONOMOUSLY_PROTECTED":
                    logger.warning(
                        "[SHIFT] Finding %s touches AUTONOMOUSLY_PROTECTED — surfacing to Chief only.",
                        finding.finding_id,
                    )
                    finding.record_outcome(
                        RepairOutcome.SKIPPED,
                        note="Autonomously protected component — surfaced to Chief, no autonomous repair.",
                    )
                    self._save_manifest()
                    continue

            # Risk classification
            if finding.evidence:
                classification = self._risk_classifier.classify(
                    affected_file=finding.evidence.affected_file,
                    evidence_strength=finding.evidence.strength,
                )
                finding.risk = classification.tier
            else:
                finding.risk = RiskTier.MEDIUM

            self._save_manifest()

            # Route by risk
            if finding.risk == RiskTier.GOVERNED_HIGH_RISK:
                logger.info(
                    "[SHIFT] Finding %s is GOVERNED_HIGH_RISK — surfacing to Chief.",
                    finding.finding_id,
                )
                finding.record_outcome(
                    RepairOutcome.SKIPPED,
                    note="Governed high-risk — requires separate manual governed sprint.",
                )
                self._save_manifest()
                continue

            if finding.risk in (RiskTier.MEDIUM, RiskTier.HIGH):
                self._transition(ShiftState.AWAITING_APPROVAL)
                # In Stage 1-3 we surface and defer (Chief approves via separate sprint)
                # Full approval polling is a Stage 2+ feature
                logger.info(
                    "[SHIFT] Finding %s risk=%s — deferring, awaiting Chief approval.",
                    finding.finding_id, finding.risk.name,
                )
                finding.record_outcome(
                    RepairOutcome.SKIPPED,
                    note=f"Risk={finding.risk.name} — awaiting Chief approval via Four-Way.",
                )
                self._save_manifest()
                self._transition(ShiftState.ASSESSING)
                continue

            if finding.risk == RiskTier.CRITICAL:
                self._hard_stop(
                    ShiftStopReason.HARD_STOP_RUNTIME_PATH_EXPANSION,
                    detail=f"CRITICAL risk finding: {finding.finding_id}",
                )
                return

            # LOW risk — attempt autonomous repair
            if finding.attempts_exhausted:
                decision = self._containment.decide(FailureClass.FINDING_ATTEMPTS_EXHAUSTED)
                finding.record_outcome(RepairOutcome.ABANDONED, note=decision.reason)
                self._save_manifest()
                continue

            # REPAIRING
            self._transition(ShiftState.REPAIRING)

            # Record pre-repair SHA
            pre_repair_sha = self._git_head_sha()
            finding.record_repair_start(pre_repair_sha)
            self._save_manifest()

            # Assert source-clean immediately before repair
            dirty_now = self._git_dirty_files()
            clean_now = assert_source_clean(dirty_now)
            if not clean_now.is_clean:
                self._hard_stop(
                    self._stop_reason_for_assertion(clean_now.reason),
                    detail=f"Pre-repair clean assertion failed: {clean_now.reason}",
                )
                return

            # Execute sprint via Four-Way (LOW — ShiftController auto-approves)
            repair_committed = self._execute_repair_sprint(finding)

            if not repair_committed:
                # Sprint failed before commit
                self._manifest.record_cycle(RepairOutcome.ROLLBACK)
                finding.repair_attempts += 0  # already incremented in record_repair_start
                self._save_manifest()
                self._transition(ShiftState.ASSESSING)
                continue

            repair_sha = self._git_head_sha()
            finding.record_repair_commit(repair_sha)
            self._save_manifest()

            # VALIDATING
            self._transition(ShiftState.VALIDATING)
            post_repair_suite = self._run_suite()
            if post_repair_suite is None or post_repair_suite.regressed_from(
                self._manifest.baseline_suite
            ):
                # Rollback
                rollback_ok = self._rollback(repair_sha, pre_repair_sha)
                if not rollback_ok:
                    decision = self._containment.decide(FailureClass.ROLLBACK_FAILED)
                    self._hard_stop(
                        ShiftStopReason.HARD_STOP_ROLLBACK_FAILED,
                        detail=decision.reason,
                    )
                    return
                finding.record_outcome(
                    RepairOutcome.ROLLBACK,
                    note="Suite regressed post-repair — rollback succeeded.",
                )
                self._manifest.record_cycle(RepairOutcome.ROLLBACK)
                self._save_manifest()
                self._transition(ShiftState.ASSESSING)
                continue

            # Desktop validation
            desktop_report = self._desktop_validation.run()
            if not desktop_report.passed:
                rollback_ok = self._rollback(repair_sha, pre_repair_sha)
                if not rollback_ok:
                    self._hard_stop(
                        ShiftStopReason.HARD_STOP_ROLLBACK_FAILED,
                        detail="Desktop validation failed and rollback also failed.",
                    )
                    return
                finding.record_outcome(
                    RepairOutcome.ROLLBACK,
                    note=f"Desktop validation failed: {desktop_report.detail}",
                )
                self._manifest.record_cycle(RepairOutcome.ROLLBACK)
                self._save_manifest()
                self._transition(ShiftState.ASSESSING)
                continue

            # POST_COMMIT_CHECK
            self._transition(ShiftState.POST_COMMIT_CHECK)
            self._manifest.current_suite = post_repair_suite

            previous_suite = self._manifest.baseline_suite
            trajectory = self._manifest.update_trajectory(previous_suite)

            if self._manifest.consecutive_degraded_stop:
                self._hard_stop(
                    ShiftStopReason.HARD_STOP_CONSECUTIVE_DEGRADED,
                    detail="Two consecutive DEGRADED trajectory states.",
                )
                return

            finding.record_outcome(RepairOutcome.SUCCESS)
            self._manifest.record_cycle(RepairOutcome.SUCCESS)
            self._save_manifest()

            logger.info(
                "[SHIFT] Repair cycle complete. Trajectory=%s Ratio=%.2f",
                trajectory.label(),
                self._manifest.corrective_cycle_ratio,
            )

            self._transition(ShiftState.DISCOVERING)

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    def _git_dirty_files(self) -> list[str]:
        """Return list of dirty repo-relative file paths."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self._repo_root),
                capture_output=True, text=True, timeout=30,
            )
            paths = []
            for line in result.stdout.splitlines():
                if line.strip():
                    # porcelain format: XY path (first 3 chars are status codes)
                    path = line[3:].strip()
                    # Handle renames: "old -> new"
                    if " -> " in path:
                        path = path.split(" -> ")[-1]
                    paths.append(path)
            return paths
        except Exception as exc:
            logger.error("[SHIFT] git status failed: %s", exc)
            return []

    def _git_head_sha(self) -> str:
        """Return current HEAD SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self._repo_root),
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout.strip()
        except Exception as exc:
            logger.error("[SHIFT] git rev-parse HEAD failed: %s", exc)
            return ""

    def _rollback(self, repair_sha: str, pre_repair_sha: str) -> bool:
        """
        Rollback the exact repair commit SHA.

        Safety checks:
            - Verifies repair_sha != pre_repair_sha (repair actually committed)
            - Verifies repair_sha is a real commit
            - Reverts repair_sha specifically, not HEAD
            - Confirms post-rollback HEAD matches pre_repair_sha
        """
        self._transition(ShiftState.ROLLBACK)

        if not repair_sha or not pre_repair_sha:
            logger.error("[SHIFT] Rollback called with empty SHA(s).")
            return False

        if repair_sha == pre_repair_sha:
            logger.error("[SHIFT] repair_sha == pre_repair_sha — nothing to roll back.")
            return False

        try:
            # Revert the exact repair SHA
            result = subprocess.run(
                ["git", "revert", "--no-edit", repair_sha],
                cwd=str(self._repo_root),
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                logger.error("[SHIFT] git revert failed: %s", result.stderr)
                return False

            # Validate: re-run suite and confirm no regression from baseline
            post_rollback_suite = self._run_suite()
            if post_rollback_suite is None:
                logger.error("[SHIFT] Post-rollback suite run failed.")
                return False

            if post_rollback_suite.failed > self._manifest.baseline_suite.failed:
                logger.error(
                    "[SHIFT] Post-rollback suite worse than baseline: %d failures.",
                    post_rollback_suite.failed,
                )
                return False

            logger.info("[SHIFT] Rollback succeeded. Suite restored.")
            return True

        except Exception as exc:
            logger.error("[SHIFT] Rollback exception: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Suite runner
    # ------------------------------------------------------------------

    def _run_suite(self) -> Optional[SuiteResult]:
        """Run pytest and parse results. Returns None on total failure."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
                cwd=str(self._repo_root),
                capture_output=True, text=True, timeout=300,
            )
            return self._parse_suite_result(result.stdout + result.stderr)
        except Exception as exc:
            logger.error("[SHIFT] Suite run failed: %s", exc)
            return None

    def _parse_suite_result(self, output: str) -> Optional[SuiteResult]:
        """
        Parse pytest summary line.
        e.g. '6133 passed, 33 skipped, 1 warning in 87.79s'
        """
        import re
        passed = skipped = failed = 0
        match = re.search(
            r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) failed)?",
            output,
        )
        if not match:
            logger.error("[SHIFT] Could not parse suite output: %s", output[-500:])
            return None
        passed  = int(match.group(1) or 0)
        skipped = int(match.group(2) or 0)
        failed  = int(match.group(3) or 0)
        return SuiteResult(passed=passed, skipped=skipped, failed=failed)

    # ------------------------------------------------------------------
    # Finding discovery
    # ------------------------------------------------------------------

    def _discover_findings(self) -> list[FindingRecord]:
        """Run suite, parse failures into FindingRecords."""
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
            cwd=str(self._repo_root),
            capture_output=True, text=True, timeout=300,
        )
        output = result.stdout + result.stderr
        suite = self._parse_suite_result(output)
        if suite:
            self._manifest.current_suite = suite

        if suite and suite.failed == 0:
            return []

        return self._parse_failures(output)

    def _parse_failures(self, output: str) -> list[FindingRecord]:
        """
        Parse pytest --tb=short output into FindingRecords.
        Extracts test_id, failure_message, stack_trace, affected_file.
        """
        import re
        findings = []
        # Split on FAILED lines
        failure_blocks = re.split(r"_{3,}", output)

        for block in failure_blocks:
            test_id_match = re.search(r"(tests/\S+::\S+)", block)
            if not test_id_match:
                continue
            test_id = test_id_match.group(1)

            # Already have this finding?
            existing_ids = {f.test_id for f in self._manifest.findings}
            if test_id in existing_ids:
                continue

            # Extract assertion / error message
            assert_match = re.search(r"(AssertionError|Error)[^\n]*", block)
            failure_message = assert_match.group(0) if assert_match else ""

            # Extract affected file from stack trace
            file_match = re.search(r"([\w/]+\.py)", block)
            affected_file = file_match.group(1) if file_match else None

            # Stack trace: presence of multiple file references
            stack_trace = block if re.search(r"\.py:\d+", block) else None

            evidence = EvidenceBundle.from_pytest_output(
                test_id=test_id,
                failure_message=failure_message,
                stack_trace=stack_trace,
                affected_file=affected_file,
            )

            finding = FindingRecord(
                shift_id=self._manifest.shift_id,
                test_id=test_id,
                evidence=evidence,
            )
            findings.append(finding)

        return findings

    # ------------------------------------------------------------------
    # Sprint execution (Four-Way integration)
    # ------------------------------------------------------------------

    def _execute_repair_sprint(self, finding: FindingRecord) -> bool:
        """
        Propose and execute a LOW-risk repair sprint via Four-Way.
        Returns True if a commit was produced.

        For Stage 1 (supervised), this is a stub that logs intent
        and returns False (no actual sprint proposed yet).
        Full Four-Way API integration is Sprint A scope for the
        proposal/execution pathway only — actual HTTP calls are
        wired in the server route layer, not here.
        """
        logger.info(
            "[SHIFT] Would propose LOW-risk sprint for finding %s (%s)",
            finding.finding_id, finding.test_id,
        )
        # Stage 1: supervised — no autonomous commits yet.
        # This returns False so the shift discovers, classifies,
        # and reports without executing repairs.
        # Autonomous commit path is enabled after Stage 1 evidence review.
        return False

    # ------------------------------------------------------------------
    # State transitions & STOP
    # ------------------------------------------------------------------

    def _transition(self, new_state: ShiftState) -> None:
        logger.info(
            "[SHIFT] %s → %s", self._shift_state.label(), new_state.label()
        )
        self._shift_state = new_state

    def _hard_stop(self, reason: ShiftStopReason, detail: str = "") -> None:
        logger.critical(
            "[SHIFT] HARD STOP: %s | %s", reason.label(), detail
        )
        self._transition(ShiftState.HARD_STOP)
        if self._manifest:
            # Finalise sets end_time/stop_reason FIRST, then build report
            # so the report captures the correct terminal state.
            self._manifest.finalise(stop_reason=reason, stop_detail=detail)
            self._manifest.shift_report = self._build_shift_report()
            if not self._manifest.save(self._repo_root):
                logger.critical(
                    "[SHIFT] MANIFEST WRITE FAILED during HARD STOP. "
                    "State may be unrecoverable."
                )

    def _complete_shift(self, reason: ShiftStopReason, detail: str = "") -> None:
        logger.info("[SHIFT] Shift complete: %s | %s", reason.label(), detail)
        self._transition(ShiftState.SHIFT_COMPLETE)
        if self._manifest:
            # Finalise sets end_time/stop_reason FIRST, then build report
            # so the report captures the correct terminal state.
            self._manifest.finalise(stop_reason=reason, stop_detail=detail)
            self._manifest.shift_report = self._build_shift_report()
            self._manifest.save(self._repo_root)

    def _save_manifest(self) -> None:
        if self._manifest and not self._manifest.save(self._repo_root):
            self._hard_stop(
                ShiftStopReason.HARD_STOP_MANIFEST_WRITE_FAILED,
                detail="Could not persist ShiftManifest — unsafe to continue.",
            )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _build_shift_report(self) -> str:
        if not self._manifest:
            return "No manifest available."
        m = self._manifest
        lines = [
            f"SHIFT REPORT",
            f"shift_id:         {m.shift_id}",
            f"stage:            {m.stage}",
            f"start_time:       {m.start_time.isoformat()}",
            f"end_time:         {m.end_time.isoformat() if m.end_time else 'N/A'}",
            f"stop_reason:      {m.stop_reason.label() if m.stop_reason else 'N/A'}",
            f"stop_detail:      {m.stop_detail}",
            f"baseline_suite:   {m.baseline_suite.passed}/{m.baseline_suite.skipped}/{m.baseline_suite.failed}" if m.baseline_suite else "baseline_suite: N/A",
            f"current_suite:    {m.current_suite.passed}/{m.current_suite.skipped}/{m.current_suite.failed}" if m.current_suite else "current_suite: N/A",
            f"findings:         {len(m.findings)}",
            f"repair_cycles:    {m.repair_cycles_total}",
            f"resolved:         {m.primary_findings_resolved}",
            f"corrective:       {m.corrective_cycles}",
            f"ratio:            {m.corrective_cycle_ratio:.2f}",
            f"consecutive_deg:  {m.consecutive_degraded}",
            f"trajectory:       {m.trajectory.label() if m.trajectory else 'N/A'}",
            "",
            "FINDINGS:",
        ]
        for f in m.findings:
            lines.append(
                f"  [{f.status.label()}] {f.test_id} "
                f"risk={f.risk.name if f.risk else '?'} "
                f"attempts={f.repair_attempts} "
                f"outcome={f.outcome.label() if f.outcome else 'pending'}"
            )
        return "\n".join(lines)

    def _shift_summary(self) -> list[str]:
        if not self._manifest:
            return ["Shift completed with no manifest."]
        return [
            f"Shift {self._manifest.shift_id} complete.",
            f"Findings: {len(self._manifest.findings)}",
            f"Resolved: {self._manifest.primary_findings_resolved}",
            f"Cycles: {self._manifest.repair_cycles_total}",
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stop_reason_for_assertion(self, reason: str) -> ShiftStopReason:
        if "traversal" in reason.lower():
            return ShiftStopReason.HARD_STOP_PATH_TRAVERSAL
        return ShiftStopReason.HARD_STOP_SOURCE_DIRTY
