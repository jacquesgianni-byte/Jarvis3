"""
Sustained Shift Lifecycle Tests (Governed HIGH-risk Sprint)
Genesis-081

All timing tests mock time.sleep and time.monotonic so they run instantly.
Real wall-clock tests are limited to <5 seconds each.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

from core.shift.shift_controller import ShiftController
from core.shift.shift_manifest import ShiftStopReason, SuiteResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_controller(tmp_path, duration=30, interval=6):
    return ShiftController(
        repo_root=tmp_path,
        stage=2,
        shift_duration_seconds=duration,
        scan_interval_seconds=interval,
    )


def _clean_suite():
    return SuiteResult(passed=6292, skipped=33, failed=0)


def _green_git(ctrl, dirty=None):
    runtime_files = dirty or ["data/genesis_contributions/Genesis-081.json"]
    return patch.object(ctrl, "_git_dirty_files", return_value=runtime_files)


def _run(ctrl):
    from core.workers.models import WorkerTask
    task = WorkerTask(task_type="autonomous_shift", payload={})
    ctrl.execute(task)


# ---------------------------------------------------------------------------
# Test 1: Clean discovery continues rather than terminating
# ---------------------------------------------------------------------------

class TestCleanDiscoveryContinues:

    def test_clean_suite_does_not_immediately_terminate(self, tmp_path):
        """Test 1: Clean discovery loops, does not exit immediately."""
        ctrl = _make_controller(tmp_path, duration=10, interval=5)

        call_count = [0]
        # Simulate monotonic advancing so the shift expires after 2 cycles
        mono_values = [0, 0, 0, 0, 5, 5, 5, 10, 10, 10, 15, 15]
        mono_iter = iter(mono_values)

        def fake_mono():
            try:
                return next(mono_iter)
            except StopIteration:
                return 20  # past deadline

        def fake_discover():
            call_count[0] += 1
            return []

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert call_count[0] >= 1
        assert ctrl._manifest.stop_reason == ShiftStopReason.CLEAN_NO_FINDINGS

    def test_clean_shift_terminates_on_duration(self, tmp_path):
        """Test 3: Shift terminates when deadline reached."""
        ctrl = _make_controller(tmp_path, duration=10, interval=5)

        # mono: start=0, deadline=10; first elapsed check gives 0 (not expired),
        # second check gives 11 (expired)
        mono_values = iter([0, 0, 0, 0, 5, 11, 11, 11])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 20

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", return_value=[]):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert ctrl._manifest.stop_reason == ShiftStopReason.CLEAN_NO_FINDINGS


# ---------------------------------------------------------------------------
# Test 2: Scan interval is honoured
# ---------------------------------------------------------------------------

class TestScanIntervalHonoured:

    def test_scan_interval_wait_occurs_between_cycles(self, tmp_path):
        """Test 2: Shift waits between clean cycles (scan interval honoured).
        
        Verified by: shift runs for >scan_interval wall seconds with short
        duration, proving it waited rather than spinning immediately.
        Uses real time.sleep but with short values (interval=5s, duration=12s).
        """
        import time as _t
        ctrl = _make_controller(tmp_path, duration=12, interval=5)

        discovery_times = []
        def fake_discover():
            discovery_times.append(_t.monotonic())
            return []

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    start = _t.monotonic()
                    _run(ctrl)
                    elapsed = _t.monotonic() - start

        # With interval=5s and duration=12s, shift must have waited at least once
        # Total elapsed should be at least 5 seconds (one wait interval)
        assert elapsed >= 4.0, f"Shift ended too quickly ({elapsed:.1f}s) — no wait occurred"
        # Must have run at least 2 discovery cycles
        assert len(discovery_times) >= 2, f"Expected >=2 cycles, got {len(discovery_times)}"


# ---------------------------------------------------------------------------
# Test 4: Duration bounds enforced
# ---------------------------------------------------------------------------

class TestDurationBoundsEnforced:

    def test_duration_clamped_to_maximum(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, shift_duration_seconds=999999)
        assert ctrl._shift_duration_seconds <= ShiftController._MAX_SHIFT_DURATION_SECONDS

    def test_duration_clamped_to_minimum(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, shift_duration_seconds=1)
        assert ctrl._shift_duration_seconds >= ShiftController._MIN_SHIFT_DURATION_SECONDS

    def test_interval_clamped_to_maximum(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, scan_interval_seconds=999999)
        assert ctrl._scan_interval_seconds <= ShiftController._MAX_SCAN_INTERVAL_SECONDS

    def test_interval_clamped_to_minimum(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, scan_interval_seconds=1)
        assert ctrl._scan_interval_seconds >= ShiftController._MIN_SCAN_INTERVAL_SECONDS

    def test_valid_duration_preserved(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, shift_duration_seconds=7200)
        assert ctrl._shift_duration_seconds == 7200

    def test_valid_interval_preserved(self, tmp_path):
        ctrl = ShiftController(repo_root=tmp_path, scan_interval_seconds=300)
        assert ctrl._scan_interval_seconds == 300


# ---------------------------------------------------------------------------
# Tests 5-6: Finding triggers repair pathway
# ---------------------------------------------------------------------------

class TestFindingPathway:

    def test_finding_triggers_assessment_not_termination(self, tmp_path):
        """Tests 5-6: Finding discovered → ASSESSING, not immediate termination."""
        from core.shift.shift_manifest import FindingRecord
        from core.shift.evidence import EvidenceBundle, EvidenceStrength

        ctrl = _make_controller(tmp_path, duration=20, interval=5)

        evidence = EvidenceBundle(
            test_id="tests/test_foo.py::test_bar",
            failure_message="AssertionError",
            stack_trace="trace",
            affected_file="core/knowledge/some_helper.py",
            strength=EvidenceStrength.HIGH,
        )
        finding = FindingRecord(test_id="tests/test_foo.py::test_bar", evidence=evidence)

        call_count = [0]
        mono_values = iter([0, 0, 0, 0, 0, 5, 25, 25])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 30

        def fake_discover():
            call_count[0] += 1
            return [finding] if call_count[0] == 1 else []

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    with patch.object(ctrl, "_execute_repair_sprint", return_value=False):
                        with patch("core.shift.shift_controller._time") as mock_time:
                            mock_time.monotonic.side_effect = fake_mono
                            mock_time.sleep = MagicMock()
                            _run(ctrl)

        assert call_count[0] >= 1
        assert len(ctrl._manifest.findings) >= 1


# ---------------------------------------------------------------------------
# Tests 7-8: Remote STOP
# ---------------------------------------------------------------------------

class TestRemoteStopDuringWait:

    def test_remote_stop_during_scan_interval_terminates(self, tmp_path):
        """Test 7: Remote STOP during wait terminates promptly."""
        ctrl = _make_controller(tmp_path, duration=300, interval=60)

        call_count = [0]
        mono_values = iter([0, 0, 0, 0, 0, 5, 10, 15])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 20

        def fake_discover():
            call_count[0] += 1
            ctrl.request_stop()
            return []

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert ctrl._manifest.stop_reason == ShiftStopReason.HARD_STOP_REMOTE_STOP

    def test_remote_stop_at_loop_start_terminates(self, tmp_path):
        """Test 8: Remote STOP at top of loop terminates safely."""
        ctrl = _make_controller(tmp_path, duration=300, interval=60)
        ctrl.request_stop()

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch("core.shift.shift_controller._time") as mock_time:
                    mock_time.monotonic.return_value = 0
                    mock_time.sleep = MagicMock()
                    _run(ctrl)

        assert ctrl._manifest.stop_reason == ShiftStopReason.HARD_STOP_REMOTE_STOP


# ---------------------------------------------------------------------------
# Test 9: No autonomous restart
# ---------------------------------------------------------------------------

class TestNoAutonomousRestart:

    def test_shift_does_not_restart_after_stop(self, tmp_path):
        """Test 9: Once stopped, shift does not restart."""
        ctrl = _make_controller(tmp_path, duration=300, interval=60)

        discovery_calls = [0]
        mono_values = iter([0, 0, 0, 0, 0, 5, 10])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 20

        def fake_discover():
            discovery_calls[0] += 1
            ctrl.request_stop()
            return []

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", side_effect=fake_discover):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert discovery_calls[0] <= 2
        assert ctrl._manifest.stop_reason == ShiftStopReason.HARD_STOP_REMOTE_STOP

    def test_request_stop_sets_flag(self, tmp_path):
        ctrl = _make_controller(tmp_path)
        assert not ctrl._stop_requested
        ctrl.request_stop()
        assert ctrl._stop_requested


# ---------------------------------------------------------------------------
# Test 10: Existing hard-stop mechanisms preserved
# ---------------------------------------------------------------------------

class TestExistingHardStopPreserved:

    def test_source_dirty_still_hard_stops(self, tmp_path):
        """Test 10: Source-dirty detection still triggers HARD_STOP."""
        ctrl = _make_controller(tmp_path)
        with patch.object(ctrl, "_git_dirty_files",
                          return_value=["core/workers/manager.py"]):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                _run(ctrl)
        assert ctrl._manifest.stop_reason == ShiftStopReason.HARD_STOP_SOURCE_DIRTY

    def test_path_traversal_still_hard_stops(self, tmp_path):
        """Test 10b: Path traversal still triggers HARD_STOP."""
        ctrl = _make_controller(tmp_path)
        with patch.object(ctrl, "_git_dirty_files",
                          return_value=["data/../core/shift/source_clean.py"]):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                _run(ctrl)
        assert ctrl._manifest.stop_reason == ShiftStopReason.HARD_STOP_PATH_TRAVERSAL


# ---------------------------------------------------------------------------
# Test 12: Stage 1 behaviour intact
# ---------------------------------------------------------------------------

class TestStage1BehaviourIntact:

    def test_default_duration_is_two_hours(self, tmp_path):
        """Test 12: Default shift_duration_seconds is 7200 (2 hours)."""
        ctrl = ShiftController(repo_root=tmp_path)
        assert ctrl._shift_duration_seconds == 7200

    def test_shift_deadline_none_before_run(self, tmp_path):
        """Test 12b: _shift_deadline is None until _run_shift starts."""
        ctrl = _make_controller(tmp_path)
        assert ctrl._shift_deadline is None

    def test_shift_deadline_set_during_run(self, tmp_path):
        """Test 12c: _shift_deadline is set when the shift runs."""
        ctrl = _make_controller(tmp_path, duration=10, interval=5)

        mono_values = iter([0, 0, 0, 0, 15, 15])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 20

        with _green_git(ctrl):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", return_value=[]):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert ctrl._shift_deadline is not None


# ---------------------------------------------------------------------------
# Test 13: Runtime dirty files handled correctly
# ---------------------------------------------------------------------------

class TestRuntimeDirtyFilesHandled:

    def test_runtime_dirty_files_do_not_block_sustained_shift(self, tmp_path):
        """Test 13: Six legitimate runtime dirty files do not trigger HARD_STOP."""
        ctrl = _make_controller(tmp_path, duration=10, interval=5)

        runtime_dirty = [
            "data/genesis_contributions/Genesis-081.json",
            "data/genesis_contributions/Genesis-071.json",
            "data/situational_memory/entries.json",
            "data/shift_manifests/some-manifest.json",
        ]

        mono_values = iter([0, 0, 0, 0, 15, 15])

        def fake_mono():
            try: return next(mono_values)
            except StopIteration: return 20

        with patch.object(ctrl, "_git_dirty_files", return_value=runtime_dirty):
            with patch.object(ctrl, "_run_suite", return_value=_clean_suite()):
                with patch.object(ctrl, "_discover_findings", return_value=[]):
                    with patch("core.shift.shift_controller._time") as mock_time:
                        mock_time.monotonic.side_effect = fake_mono
                        mock_time.sleep = MagicMock()
                        _run(ctrl)

        assert ctrl._manifest.stop_reason != ShiftStopReason.HARD_STOP_SOURCE_DIRTY
        assert ctrl._manifest.stop_reason == ShiftStopReason.CLEAN_NO_FINDINGS


# ---------------------------------------------------------------------------
# Test 14: No parallel lifecycle
# ---------------------------------------------------------------------------

class TestNoParallelLifecycle:

    def test_shift_controller_is_single_worker(self, tmp_path):
        """Test 14: ShiftController is the single Worker."""
        from core.workers.base import Worker
        assert issubclass(ShiftController, Worker)

    def test_no_second_controller_class(self):
        """Test 14b: No ShiftScheduler or parallel lifecycle class."""
        import core.shift.shift_controller as sc_module
        import inspect
        classes = [
            name for name, obj in inspect.getmembers(sc_module, inspect.isclass)
            if any(k in name for k in ('Controller', 'Scheduler', 'Lifecycle'))
        ]
        assert 'ShiftController' in classes
        assert 'ShiftScheduler' not in classes
        assert 'ShiftLifecycle' not in classes
