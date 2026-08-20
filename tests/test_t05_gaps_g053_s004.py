"""
Genesis-053 Sprint-004 — T-05 Regression Tests
Gap A: destructive-operation guardrails
Gap B: subprocess isolation in SuiteRunnerWorker
"""
from __future__ import annotations
import pytest


class TestGuardrailsDestructiveOps:

    def _g(self):
        from core.engineering.guardrails.guardrails import EngineeringGuardrails
        return EngineeringGuardrails(max_files=5)

    def test_delete_op_rejected(self, tmp_path):
        from core.engineering.guardrails.models import ApprovalStatus
        f = tmp_path / "health.py"
        f.write_text("# health")
        ops = [{"action": "delete", "path": str(f), "content": "", "reason": ""}]
        ep = self._g().evaluate("Delete", [str(f)], operations=ops)
        assert ep.status == ApprovalStatus.REJECTED
        assert "destructive" in ep.reason.lower() or "delete" in ep.reason.lower()

    def test_empty_overwrite_existing_rejected(self, tmp_path):
        from core.engineering.guardrails.models import ApprovalStatus
        f = tmp_path / "health.py"
        f.write_text("# health")
        ops = [{"action": "modify", "path": str(f), "content": "", "reason": ""}]
        ep = self._g().evaluate("Empty", [str(f)], operations=ops)
        assert ep.status == ApprovalStatus.REJECTED

    def test_normal_modify_approved(self, tmp_path):
        from core.engineering.guardrails.models import ApprovalStatus
        f = tmp_path / "health.py"
        f.write_text("# health")
        ops = [{"action": "modify", "path": str(f), "content": "def version_info(): pass", "reason": ""}]
        ep = self._g().evaluate("Add method", [str(f)], operations=ops)
        assert ep.status == ApprovalStatus.APPROVED

    def test_create_new_file_approved(self, tmp_path):
        from core.engineering.guardrails.models import ApprovalStatus
        f = tmp_path / "new_module.py"
        # file does NOT exist
        ops = [{"action": "create", "path": str(f), "content": "# new", "reason": ""}]
        ep = self._g().evaluate("Create", [str(f)], operations=ops)
        assert ep.status == ApprovalStatus.APPROVED

    def test_no_operations_backward_compatible(self):
        from core.engineering.guardrails.models import ApprovalStatus
        ep = self._g().evaluate("Normal", ["core/health.py"])
        assert ep.status in (ApprovalStatus.APPROVED, ApprovalStatus.REQUIRES_APPROVAL, ApprovalStatus.REJECTED)

    def test_empty_operations_backward_compatible(self):
        from core.engineering.guardrails.models import ApprovalStatus
        ep = self._g().evaluate("Normal", ["core/health.py"], operations=[])
        assert ep.status in (ApprovalStatus.APPROVED, ApprovalStatus.REQUIRES_APPROVAL, ApprovalStatus.REJECTED)

    def test_multiple_deletes_reported(self, tmp_path):
        from core.engineering.guardrails.models import ApprovalStatus
        files = []
        ops = []
        for name in ["a.py", "b.py"]:
            f = tmp_path / name
            f.write_text("# content")
            files.append(str(f))
            ops.append({"action": "delete", "path": str(f), "content": "", "reason": ""})
        ep = self._g().evaluate("Delete multiple", files, operations=ops)
        assert ep.status == ApprovalStatus.REJECTED
        assert "2" in ep.reason


class TestSuiteRunnerSubprocess:

    def _task(self, paths=None):
        from core.workers.models import WorkerTask
        return WorkerTask(
            task_type="run_tests",
            payload={"paths": paths or ["tests/test_health.py"], "verbose": False},
            requester="test",
        )

    def test_uses_subprocess_not_pytest_main(self):
        import inspect
        from core.workers.suite_worker import SuiteRunnerWorker
        src = inspect.getsource(SuiteRunnerWorker.execute)
        assert "subprocess" in src
        assert "pytest.main" not in src

    def test_returns_worker_result(self):
        from core.workers.suite_worker import SuiteRunnerWorker
        from core.workers.models import WorkerResult
        result = SuiteRunnerWorker().execute(self._task())
        assert isinstance(result, WorkerResult)
        assert "passed" in result.data
        assert "failed" in result.data
        assert "exit_code" in result.data

    def test_passing_suite_returns_success(self):
        from core.workers.suite_worker import SuiteRunnerWorker
        result = SuiteRunnerWorker().execute(self._task(["tests/test_health.py"]))
        assert result.success is True
        assert result.data["failed"] == 0

    def test_fresh_process_noted_in_observations(self):
        from core.workers.suite_worker import SuiteRunnerWorker
        result = SuiteRunnerWorker().execute(self._task(["tests/test_health.py"]))
        obs = " ".join(result.observations).lower()
        assert "subprocess" in obs or "fresh" in obs
