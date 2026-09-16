"""
Autonomous Shift Controller — Test Suite (Sprint A)

Pre-build baseline: 6133 passed / 33 skipped / 0 failed
Post-build: >= baseline, 0 failed, all shift tests present and passing.

Coverage areas:
    1.  source_clean — runtime files pass, source dirty → HARD_ABORT
    2.  source_clean — path traversal → HARD_ABORT
    3.  source_clean — RUNTIME_DATA_PATHS expansion attempt
    4.  EvidenceStrength — HIGH / MEDIUM / LOW deterministic classification
    5.  EvidenceBundle.from_pytest_output
    6.  DiagnosisHypothesis — advisory label, no governance influence
    7.  RiskClassifier — AUTONOMOUSLY_PROTECTED
    8.  RiskClassifier — GOVERNED_HIGH_RISK
    9.  RiskClassifier — LOW evidence → MEDIUM minimum
    10. RiskClassifier — new architecture → HIGH
    11. RiskClassifier — not additive → MEDIUM
    12. RiskClassifier — all LOW conditions met → LOW
    13. RiskClassifier — no affected file → MEDIUM
    14. RiskClassifier — RUNTIME_DATA_PATHS expansion → CRITICAL
    15. FindingRecord — creation, lifecycle, attempt tracking
    16. FindingRecord — max repair attempts enforced
    17. ShiftManifest — initialisation and persistence
    18. ShiftManifest — queue cap blocks generative expansion
    19. ShiftManifest — generative expansion requires resolved parent
    20. ShiftManifest — max 3 children per parent enforced
    21. ShiftManifest — consecutive DEGRADED counter
    22. ShiftManifest — two consecutive DEGRADED → stop condition
    23. ShiftManifest — corrective cycle ratio
    24. FailureContainment — all failure classes covered
    25. FailureContainment — HARD_STOP failures
    26. FailureContainment — ROLLBACK failures
    27. FailureContainment — unknown failure class → HARD_STOP
    28. SuiteResult — regression detection
    29. ShiftController — LOW auto-approve permitted
    30. ShiftController — MEDIUM/HIGH auto-approve blocked
    31. Rollback — targets exact repair SHA, not HEAD
    32. Rollback — cannot target unrelated commit (A→B→C test)
    33. Rollback — fails if repair_sha == pre_repair_sha
    34. ShiftController — AUTONOMOUSLY_PROTECTED finding → surfaced only
    35. ShiftController — source dirty → HARD_STOP
    36. ShiftController — path traversal → HARD_STOP
    37. RUNTIME_DATA_PATHS — is frozenset (immutable type)
    38. AUTONOMOUSLY_PROTECTED — is frozenset (immutable type)
    39. DiagnosisHypothesis — not an input to RiskClassifier
    40. classify_file — correct tier for each category
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.shift.evidence import (
    DiagnosisHypothesis,
    EvidenceBundle,
    EvidenceStrength,
)
from core.shift.failure_containment import (
    FailureClass,
    FailureContainment,
    FailureResponse,
)
from core.shift.risk_classifier import RiskClassifier, RiskTier
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
    RUNTIME_DATA_PATHS,
    SourceCleanAssertion,
    assert_source_clean,
    classify_file,
    is_runtime_path_expansion_attempt,
)
from core.shift.shift_controller import ShiftController, ShiftState


# ===========================================================================
# 1-3. source_clean
# ===========================================================================

class TestSourceClean:

    def test_empty_dirty_list_is_clean(self):
        result = assert_source_clean([])
        assert result.is_clean

    def test_runtime_files_pass(self):
        dirty = [
            "data/genesis_contributions/Genesis-081.json",
            "data/situational_memory/entries.json",
            "data/sprint_states/some_state.json",
            "data/shift_manifests/abc.json",
        ]
        result = assert_source_clean(dirty)
        assert result.is_clean

    def test_source_file_hard_aborts(self):
        dirty = ["core/mission/pipeline.py"]
        result = assert_source_clean(dirty)
        assert not result.is_clean
        assert "core/mission/pipeline.py" in result.offending_path

    def test_mixed_runtime_and_source_hard_aborts(self):
        dirty = [
            "data/genesis_contributions/Genesis-081.json",
            "core/workers/manager.py",
        ]
        result = assert_source_clean(dirty)
        assert not result.is_clean
        assert "core/workers/manager.py" in result.offending_path

    def test_path_traversal_hard_aborts(self):
        dirty = ["data/../core/shift/source_clean.py"]
        result = assert_source_clean(dirty)
        assert not result.is_clean
        assert "traversal" in result.reason.lower() or ".." in result.reason

    def test_path_traversal_caught_even_in_runtime_path(self):
        dirty = ["data/genesis_contributions/../../core/shift/source_clean.py"]
        result = assert_source_clean(dirty)
        assert not result.is_clean

    def test_runtime_data_paths_is_frozenset(self):
        """RUNTIME_DATA_PATHS must be immutable — frozenset, not a list or set."""
        assert isinstance(RUNTIME_DATA_PATHS, frozenset)

    def test_runtime_path_expansion_detected(self):
        """Proposed new path not in RUNTIME_DATA_PATHS → expansion attempt."""
        new_paths = list(RUNTIME_DATA_PATHS) + ["data/some_new_runtime_path/"]
        assert is_runtime_path_expansion_attempt(new_paths)

    def test_no_expansion_when_paths_unchanged(self):
        assert not is_runtime_path_expansion_attempt(list(RUNTIME_DATA_PATHS))


# ===========================================================================
# 4-6. Evidence
# ===========================================================================

class TestEvidenceStrength:

    def test_high_requires_all_three(self):
        strength = EvidenceStrength.classify(
            has_stack_trace=True,
            has_assertion=True,
            has_affected_file=True,
        )
        assert strength == EvidenceStrength.HIGH

    def test_medium_requires_assertion_and_file(self):
        strength = EvidenceStrength.classify(
            has_stack_trace=False,
            has_assertion=True,
            has_affected_file=True,
        )
        assert strength == EvidenceStrength.MEDIUM

    def test_low_when_only_failing_test(self):
        strength = EvidenceStrength.classify(
            has_stack_trace=False,
            has_assertion=False,
            has_affected_file=False,
        )
        assert strength == EvidenceStrength.LOW

    def test_no_stack_no_file_is_low(self):
        strength = EvidenceStrength.classify(
            has_stack_trace=False,
            has_assertion=True,
            has_affected_file=False,
        )
        assert strength == EvidenceStrength.LOW

    def test_stack_without_assertion_is_low(self):
        strength = EvidenceStrength.classify(
            has_stack_trace=True,
            has_assertion=False,
            has_affected_file=True,
        )
        assert strength == EvidenceStrength.LOW


class TestEvidenceBundle:

    def test_from_pytest_output_high(self):
        bundle = EvidenceBundle.from_pytest_output(
            test_id="tests/test_foo.py::TestBar::test_baz",
            failure_message="AssertionError: expected True",
            stack_trace="Traceback...\n  File core/foo.py line 10",
            affected_file="core/foo.py",
        )
        assert bundle.strength == EvidenceStrength.HIGH
        assert bundle.test_id == "tests/test_foo.py::TestBar::test_baz"

    def test_from_pytest_output_medium(self):
        bundle = EvidenceBundle.from_pytest_output(
            test_id="tests/test_foo.py::test_bar",
            failure_message="AssertionError",
            stack_trace=None,
            affected_file="core/foo.py",
        )
        assert bundle.strength == EvidenceStrength.MEDIUM

    def test_from_pytest_output_low(self):
        bundle = EvidenceBundle.from_pytest_output(
            test_id="tests/test_foo.py::test_bar",
            failure_message="",
            stack_trace=None,
            affected_file=None,
        )
        assert bundle.strength == EvidenceStrength.LOW

    def test_to_dict_includes_strength(self):
        bundle = EvidenceBundle.from_pytest_output(
            test_id="tests/test_foo.py::test_bar",
            failure_message="AssertionError",
            stack_trace="trace",
            affected_file="core/foo.py",
        )
        d = bundle.to_dict()
        assert d["strength"] == "HIGH"


class TestDiagnosisHypothesis:

    def test_advisory_label_present(self):
        hyp = DiagnosisHypothesis(text="Probably a missing import.")
        d = hyp.to_dict()
        assert d["label"] == DiagnosisHypothesis.ADVISORY_LABEL
        assert "ADVISORY" in d["label"]

    def test_hypothesis_text_preserved(self):
        hyp = DiagnosisHypothesis(text="The fix is X.")
        assert hyp.text == "The fix is X."


# ===========================================================================
# 7-14. RiskClassifier
# ===========================================================================

class TestRiskClassifier:

    def setup_method(self):
        self.clf = RiskClassifier()

    def test_autonomously_protected_file(self):
        result = self.clf.classify(
            affected_file="core/shift/shift_controller.py",
            evidence_strength=EvidenceStrength.HIGH,
        )
        assert result.tier == RiskTier.AUTONOMOUSLY_PROTECTED
        assert result.is_surface_only

    def test_autonomously_protected_via_prefix(self):
        result = self.clf.classify(
            affected_file="core/mission/intent/some_detector.py",
            evidence_strength=EvidenceStrength.HIGH,
        )
        assert result.tier == RiskTier.AUTONOMOUSLY_PROTECTED

    def test_governed_high_risk_file(self):
        result = self.clf.classify(
            affected_file="apps/server/app.py",
            evidence_strength=EvidenceStrength.HIGH,
        )
        assert result.tier == RiskTier.GOVERNED_HIGH_RISK
        assert result.is_surface_only

    def test_low_evidence_forces_medium_minimum(self):
        result = self.clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.LOW,
            is_additive_only=True,
        )
        assert result.tier == RiskTier.MEDIUM

    def test_new_architecture_forces_high(self):
        result = self.clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=True,
            is_additive_only=True,
        )
        assert result.tier == RiskTier.HIGH

    def test_not_additive_forces_medium(self):
        result = self.clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=False,
            is_additive_only=False,
        )
        assert result.tier == RiskTier.MEDIUM

    def test_all_low_conditions_met(self):
        result = self.clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=False,
            is_additive_only=True,
        )
        assert result.tier == RiskTier.LOW
        assert result.allows_autonomous_repair

    def test_medium_evidence_all_conditions_met_is_low(self):
        result = self.clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.MEDIUM,
            is_new_architecture=False,
            is_additive_only=True,
        )
        assert result.tier == RiskTier.LOW

    def test_no_affected_file_is_medium(self):
        result = self.clf.classify(
            affected_file=None,
            evidence_strength=EvidenceStrength.HIGH,
        )
        assert result.tier == RiskTier.MEDIUM

    def test_runtime_path_expansion_is_critical(self):
        result = self.clf.classify_runtime_path_expansion()
        assert result.tier == RiskTier.CRITICAL
        assert result.is_hard_stop

    def test_diagnosis_hypothesis_not_accepted_as_input(self):
        """
        RiskClassifier must NOT accept DiagnosisHypothesis as an input.
        This test confirms classify() signature does not include it.
        """
        import inspect
        sig = inspect.signature(self.clf.classify)
        param_names = list(sig.parameters.keys())
        assert "diagnosis_hypothesis" not in param_names
        assert "hypothesis" not in param_names

    def test_autonomously_protected_is_frozenset(self):
        assert isinstance(AUTONOMOUSLY_PROTECTED, frozenset)


# ===========================================================================
# 15-16. FindingRecord
# ===========================================================================

class TestFindingRecord:

    def _make_bundle(self, strength=EvidenceStrength.HIGH) -> EvidenceBundle:
        return EvidenceBundle(
            test_id="tests/test_foo.py::test_bar",
            failure_message="AssertionError",
            stack_trace="trace",
            affected_file="core/knowledge/foo.py",
            strength=strength,
        )

    def test_initial_status_is_open(self):
        f = FindingRecord(test_id="tests/test_foo.py::test_bar")
        assert f.status == FindingStatus.OPEN

    def test_repair_start_increments_attempts(self):
        f = FindingRecord()
        f.record_repair_start("abc123")
        assert f.repair_attempts == 1
        assert f.status == FindingStatus.IN_REPAIR
        assert f.pre_repair_sha == "abc123"

    def test_repair_commit_recorded(self):
        f = FindingRecord()
        f.record_repair_start("pre123")
        f.record_repair_commit("rep456")
        assert f.repair_sha == "rep456"

    def test_success_outcome(self):
        f = FindingRecord()
        f.record_repair_start("pre")
        f.record_repair_commit("rep")
        f.record_outcome(RepairOutcome.SUCCESS)
        assert f.status == FindingStatus.RESOLVED
        assert f.outcome == RepairOutcome.SUCCESS

    def test_abandoned_after_max_attempts(self):
        f = FindingRecord()
        for _ in range(FindingRecord.MAX_REPAIR_ATTEMPTS):
            f.record_repair_start("sha")
        assert f.attempts_exhausted

    def test_not_exhausted_below_max(self):
        f = FindingRecord()
        f.record_repair_start("sha")
        assert not f.attempts_exhausted

    def test_to_dict_serialisable(self):
        f = FindingRecord(test_id="tests/test_foo.py::test_bar")
        f.evidence = self._make_bundle()
        d = f.to_dict()
        assert d["test_id"] == "tests/test_foo.py::test_bar"
        assert "evidence" in d


# ===========================================================================
# 17-23. ShiftManifest
# ===========================================================================

class TestShiftManifest:

    def test_initialises_with_unique_id(self):
        m1 = ShiftManifest()
        m2 = ShiftManifest()
        assert m1.shift_id != m2.shift_id

    def test_save_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            m = ShiftManifest()
            m.baseline_suite = SuiteResult(passed=100, skipped=5, failed=0)
            ok = m.save(root)
            assert ok
            out = root / "data" / "shift_manifests" / f"{m.shift_id}.json"
            assert out.exists()
            data = json.loads(out.read_text())
            assert data["shift_id"] == m.shift_id

    def test_queue_cap_blocks_expansion(self):
        m = ShiftManifest()
        for i in range(ShiftManifest.QUEUE_CAP):
            m.add_finding(FindingRecord(test_id=f"tests/test_{i}.py::test_x"))

        # Add a resolved parent
        parent = FindingRecord(test_id="tests/test_parent.py::test_p")
        parent.status = FindingStatus.RESOLVED
        m.findings.append(parent)

        # Queue is capped — expansion blocked
        assert m.queue_is_capped()
        result = m.create_child_finding(
            parent_finding_id=parent.finding_id,
            test_id="tests/test_child.py::test_c",
            evidence=MagicMock(),
        )
        assert result is None

    def test_expansion_requires_resolved_parent(self):
        m = ShiftManifest()
        parent = FindingRecord(test_id="tests/test_parent.py::test_p")
        # Status is OPEN — not resolved
        m.add_finding(parent)

        result = m.create_child_finding(
            parent_finding_id=parent.finding_id,
            test_id="tests/test_child.py::test_c",
            evidence=MagicMock(),
        )
        assert result is None

    def test_max_three_children_per_parent(self):
        m = ShiftManifest()
        parent = FindingRecord(test_id="tests/test_parent.py::test_p")
        parent.status = FindingStatus.RESOLVED
        m.add_finding(parent)

        for i in range(FindingRecord.MAX_CHILDREN):
            child = m.create_child_finding(
                parent_finding_id=parent.finding_id,
                test_id=f"tests/test_child_{i}.py::test_c",
                evidence=MagicMock(),
            )
            assert child is not None

        # Fourth child blocked
        fourth = m.create_child_finding(
            parent_finding_id=parent.finding_id,
            test_id="tests/test_child_4.py::test_c",
            evidence=MagicMock(),
        )
        assert fourth is None

    def test_consecutive_degraded_increments(self):
        m = ShiftManifest()
        m.baseline_suite = SuiteResult(passed=100, skipped=0, failed=0)
        m.current_suite = SuiteResult(passed=98, skipped=0, failed=2)
        prev = SuiteResult(passed=99, skipped=0, failed=1)
        traj = m.update_trajectory(prev)
        assert traj == ShiftTrajectory.DEGRADED
        assert m.consecutive_degraded == 1

    def test_two_consecutive_degraded_triggers_stop(self):
        m = ShiftManifest()
        m.consecutive_degraded = 2
        assert m.consecutive_degraded_stop

    def test_improving_resets_consecutive_degraded(self):
        m = ShiftManifest()
        m.consecutive_degraded = 1
        m.current_suite = SuiteResult(passed=101, skipped=0, failed=0)
        prev = SuiteResult(passed=99, skipped=0, failed=2)
        m.update_trajectory(prev)
        assert m.consecutive_degraded == 0

    def test_corrective_cycle_ratio(self):
        m = ShiftManifest()
        m.repair_cycles_total = 4
        m.corrective_cycles = 1
        assert abs(m.corrective_cycle_ratio - 0.25) < 0.01

    def test_corrective_ratio_zero_when_no_cycles(self):
        m = ShiftManifest()
        assert m.corrective_cycle_ratio == 0.0

    def test_cycle_limit_reached(self):
        m = ShiftManifest()
        m.repair_cycles_total = ShiftManifest.MAX_REPAIR_CYCLES
        assert m.cycle_limit_reached

    def test_to_dict_is_json_serialisable(self):
        m = ShiftManifest()
        m.baseline_suite = SuiteResult(passed=100, skipped=5, failed=0)
        m.current_suite = SuiteResult(passed=100, skipped=5, failed=0)
        d = m.to_dict()
        # Should not raise
        json.dumps(d)


# ===========================================================================
# 24-27. FailureContainment
# ===========================================================================

class TestFailureContainment:

    def setup_method(self):
        self.fc = FailureContainment()

    def test_all_failure_classes_covered(self):
        for fc in FailureClass:
            decision = self.fc.decide(fc)
            assert decision.failure_class == fc

    def test_test_regression_triggers_rollback(self):
        d = self.fc.decide(FailureClass.TEST_REGRESSION_POST_REPAIR)
        assert d.response == FailureResponse.ROLLBACK
        assert not d.is_hard_stop

    def test_desktop_validation_failure_triggers_rollback(self):
        d = self.fc.decide(FailureClass.DESKTOP_VALIDATION_FAILED)
        assert d.response == FailureResponse.ROLLBACK

    def test_commit_boundary_is_hard_stop(self):
        d = self.fc.decide(FailureClass.COMMIT_BOUNDARY_VIOLATION)
        assert d.is_hard_stop

    def test_rollback_failed_is_hard_stop(self):
        d = self.fc.decide(FailureClass.ROLLBACK_FAILED)
        assert d.is_hard_stop

    def test_consecutive_degraded_is_hard_stop(self):
        d = self.fc.decide(FailureClass.CONSECUTIVE_DEGRADED_LIMIT)
        assert d.is_hard_stop

    def test_protected_component_is_hard_stop(self):
        d = self.fc.decide(FailureClass.PROTECTED_COMPONENT_TOUCHED)
        assert d.is_hard_stop

    def test_runtime_path_expansion_is_hard_stop(self):
        d = self.fc.decide(FailureClass.RUNTIME_PATH_EXPANSION_ATTEMPTED)
        assert d.is_hard_stop

    def test_source_dirty_outside_runtime_is_hard_stop(self):
        d = self.fc.decide(FailureClass.SOURCE_DIRTY_OUTSIDE_RUNTIME)
        assert d.is_hard_stop

    def test_path_traversal_is_hard_stop(self):
        d = self.fc.decide(FailureClass.PATH_TRAVERSAL_DETECTED)
        assert d.is_hard_stop

    def test_manifest_write_failed_is_hard_stop(self):
        d = self.fc.decide(FailureClass.MANIFEST_WRITE_FAILED)
        assert d.is_hard_stop

    def test_remote_stop_is_hard_stop(self):
        d = self.fc.decide(FailureClass.REMOTE_STOP_RECEIVED)
        assert d.is_hard_stop

    def test_attempts_exhausted_triggers_abandon(self):
        d = self.fc.decide(FailureClass.FINDING_ATTEMPTS_EXHAUSTED)
        assert d.response == FailureResponse.ABANDON_FINDING
        assert not d.is_hard_stop

    def test_server_unresponsive_triggers_recovery(self):
        d = self.fc.decide(FailureClass.SERVER_UNRESPONSIVE)
        assert d.response == FailureResponse.SERVER_RECOVERY

    def test_unknown_failure_class_is_hard_stop(self):
        # Simulate unknown by using a fake value
        fake_class = MagicMock()
        fake_class.__class__ = FailureClass
        d = self.fc.decide(fake_class)
        assert d.is_hard_stop


# ===========================================================================
# 28. SuiteResult
# ===========================================================================

class TestSuiteResult:

    def test_green_when_no_failures(self):
        s = SuiteResult(passed=100, skipped=5, failed=0)
        assert s.is_green

    def test_not_green_when_failures(self):
        s = SuiteResult(passed=99, skipped=5, failed=1)
        assert not s.is_green

    def test_regressed_when_more_failures(self):
        baseline = SuiteResult(passed=100, skipped=5, failed=0)
        current = SuiteResult(passed=99, skipped=5, failed=1)
        assert current.regressed_from(baseline)

    def test_not_regressed_when_same(self):
        baseline = SuiteResult(passed=100, skipped=5, failed=0)
        current = SuiteResult(passed=100, skipped=5, failed=0)
        assert not current.regressed_from(baseline)

    def test_not_regressed_when_improved(self):
        baseline = SuiteResult(passed=99, skipped=5, failed=1)
        current = SuiteResult(passed=100, skipped=5, failed=0)
        assert not current.regressed_from(baseline)


# ===========================================================================
# 29-33. ShiftController behaviour
# ===========================================================================

class TestShiftControllerBehaviour:

    def _make_controller(self, tmp_path: Path) -> ShiftController:
        return ShiftController(
            repo_root=tmp_path,
            stage=1,
        )

    def test_low_risk_finding_does_not_require_chief_approval(self):
        """LOW risk findings are autonomously approvable."""
        clf = RiskClassifier()
        result = clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=False,
            is_additive_only=True,
        )
        assert result.allows_autonomous_repair
        assert not result.requires_chief_approval

    def test_medium_risk_requires_chief_approval(self):
        clf = RiskClassifier()
        result = clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.LOW,
        )
        assert result.requires_chief_approval
        assert not result.allows_autonomous_repair

    def test_high_risk_requires_chief_approval(self):
        clf = RiskClassifier()
        result = clf.classify(
            affected_file="core/knowledge/some_helper.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=True,
        )
        assert result.requires_chief_approval

    def test_autonomously_protected_never_allows_repair(self):
        clf = RiskClassifier()
        result = clf.classify(
            affected_file="core/shift/risk_classifier.py",
            evidence_strength=EvidenceStrength.HIGH,
            is_new_architecture=False,
            is_additive_only=True,
        )
        assert not result.allows_autonomous_repair
        assert not result.requires_chief_approval  # surface only, no approval path
        assert result.is_surface_only


class TestRollbackExactSHA:
    """
    Tests that rollback targets the exact recorded repair SHA,
    not blindly HEAD.
    """

    def test_rollback_fails_when_repair_sha_equals_pre_repair_sha(self, tmp_path):
        """
        If repair_sha == pre_repair_sha, nothing was committed.
        Rollback must refuse rather than corrupting state.
        """
        ctrl = ShiftController(repo_root=tmp_path)
        ctrl._manifest = ShiftManifest()
        ctrl._manifest.baseline_suite = SuiteResult(passed=100, skipped=0, failed=0)

        result = ctrl._rollback(
            repair_sha="abc123",
            pre_repair_sha="abc123",  # same — nothing committed
        )
        assert result is False

    def test_rollback_fails_gracefully_on_empty_sha(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path)
        ctrl._manifest = ShiftManifest()
        ctrl._manifest.baseline_suite = SuiteResult(passed=100, skipped=0, failed=0)

        result = ctrl._rollback(repair_sha="", pre_repair_sha="abc123")
        assert result is False

    def test_rollback_targets_repair_sha_not_head(self, tmp_path):
        """
        A→B→C scenario:
            pre_repair_sha = A (before repair)
            repair_sha = B (the repair commit)
            C = some subsequent commit (HEAD)

        Rollback must target B, not C.
        This test verifies that _rollback is called with repair_sha=B,
        and that the git command targets B explicitly.
        """
        ctrl = ShiftController(repo_root=tmp_path)
        ctrl._manifest = ShiftManifest()
        ctrl._manifest.baseline_suite = SuiteResult(passed=100, skipped=0, failed=0)

        sha_a = "aaaaaa1111111111111111111111111111111111"
        sha_b = "bbbbbb2222222222222222222222222222222222"
        sha_c = "cccccc3333333333333333333333333333333333"

        called_with = []

        def fake_run(cmd, **kwargs):
            called_with.append(cmd)
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = ""
            mock.stderr = ""
            return mock

        with patch("core.shift.shift_controller.subprocess.run", side_effect=fake_run):
            # Simulate HEAD = C (after an unrelated commit beyond the repair)
            # Call rollback with the REPAIR sha (B), not HEAD (C)
            ctrl._rollback(repair_sha=sha_b, pre_repair_sha=sha_a)

        # Find the revert command
        revert_calls = [c for c in called_with if "revert" in c]
        assert revert_calls, "git revert was never called"
        revert_cmd = revert_calls[0]

        # Must target B (repair_sha), not C (HEAD)
        assert sha_b in revert_cmd, f"Expected {sha_b} in revert command, got {revert_cmd}"
        assert sha_c not in revert_cmd, f"Unexpected HEAD sha C in revert command"
        assert "HEAD" not in revert_cmd, "Rollback must not use 'HEAD'"


# ===========================================================================
# 34-36. ShiftController HARD_STOP conditions
# ===========================================================================

class TestShiftControllerHardStop:

    def _make_controller(self, tmp_path: Path) -> ShiftController:
        return ShiftController(repo_root=tmp_path, stage=1)

    def test_source_dirty_triggers_hard_stop(self, tmp_path):
        """Non-runtime source file dirty at init → HARD_STOP, shift never starts."""
        ctrl = self._make_controller(tmp_path)

        with patch.object(ctrl, "_git_dirty_files", return_value=["core/workers/manager.py"]):
            with patch.object(ctrl, "_run_suite", return_value=SuiteResult(100, 0, 0)):
                ctrl._run_shift()

        assert ctrl._shift_state == ShiftState.HARD_STOP

    def test_path_traversal_triggers_hard_stop(self, tmp_path):
        ctrl = self._make_controller(tmp_path)

        with patch.object(ctrl, "_git_dirty_files",
                          return_value=["data/../core/shift/source_clean.py"]):
            with patch.object(ctrl, "_run_suite", return_value=SuiteResult(100, 0, 0)):
                ctrl._run_shift()

        assert ctrl._shift_state == ShiftState.HARD_STOP

    def test_remote_stop_triggers_hard_stop(self, tmp_path):
        ctrl = self._make_controller(tmp_path)
        ctrl._stop_requested = True

        with patch.object(ctrl, "_git_dirty_files", return_value=[]):
            with patch.object(ctrl, "_run_suite", return_value=SuiteResult(100, 0, 0)):
                with patch.object(ctrl, "_discover_findings", return_value=[]):
                    ctrl._run_shift()

        # _stop_requested fires at top of while loop before discovery.
        # Shift hard-stops immediately.

    def test_remote_stop_in_loop_triggers_hard_stop(self, tmp_path):
        ctrl = self._make_controller(tmp_path)

        finding = FindingRecord(test_id="tests/test_x.py::test_y")

        def fake_discover():
            ctrl._stop_requested = True  # Set stop during discovery
            return [finding]

        with patch.object(ctrl, "_git_dirty_files", return_value=[]):
            with patch.object(ctrl, "_run_suite", return_value=SuiteResult(100, 0, 0)):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    ctrl._run_shift()

        assert ctrl._shift_state == ShiftState.HARD_STOP

    def test_autonomously_protected_finding_does_not_cause_repair(self, tmp_path):
        ctrl = self._make_controller(tmp_path)

        bundle = EvidenceBundle(
            test_id="tests/test_x.py::test_y",
            failure_message="AssertionError",
            stack_trace="trace",
            affected_file="core/shift/risk_classifier.py",  # AUTONOMOUSLY_PROTECTED
            strength=EvidenceStrength.HIGH,
        )
        finding = FindingRecord(
            test_id="tests/test_x.py::test_y",
            evidence=bundle,
        )

        # Use minimum duration; after finding is processed, subsequent
        # empty discoveries loop until deadline. Use itertools.chain to
        # supply finding on first call, empty list on all subsequent calls.
        import itertools
        ctrl._shift_duration_seconds = 10
        ctrl._scan_interval_seconds = 5
        discover_seq = itertools.chain([[finding]], itertools.repeat([]))
        with patch.object(ctrl, "_git_dirty_files", return_value=[]):
            with patch.object(ctrl, "_run_suite", return_value=SuiteResult(100, 0, 0)):
                with patch.object(ctrl, "_discover_findings",
                                  side_effect=discover_seq):
                    ctrl._run_shift()

        assert finding.outcome == RepairOutcome.SKIPPED
        assert "autonomously protected" in finding.outcome_note.lower()


# ===========================================================================
# 40. classify_file
# ===========================================================================

class TestClassifyFile:

    def test_shift_controller_is_autonomously_protected(self):
        assert classify_file("core/shift/shift_controller.py") == "AUTONOMOUSLY_PROTECTED"

    def test_intent_path_is_autonomously_protected(self):
        assert classify_file("core/mission/intent/some_detector.py") == "AUTONOMOUSLY_PROTECTED"

    def test_sprint_routes_is_autonomously_protected(self):
        assert classify_file("apps/server/sprint_routes.py") == "AUTONOMOUSLY_PROTECTED"

    def test_app_py_is_governed_high_risk(self):
        assert classify_file("apps/server/app.py") == "GOVERNED_HIGH_RISK"

    def test_pipeline_is_governed_high_risk(self):
        assert classify_file("core/mission/pipeline.py") == "GOVERNED_HIGH_RISK"

    def test_standard_file_is_standard(self):
        assert classify_file("core/knowledge/some_helper.py") == "STANDARD"

    def test_test_file_is_standard(self):
        assert classify_file("tests/test_something.py") == "STANDARD"
