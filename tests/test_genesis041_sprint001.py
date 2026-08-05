"""
Tests — Autonomous Engineering Execution Safety Foundation
Genesis-041 Sprint-001

Covers:
  ExecutionResult   — state machine, immutability, summary
  RollbackStrategy  — ABC contract, GitRollbackStrategy (mocked subprocess)
  PlanValidator     — path safety, existence checks, empty plan
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# ExecutionResult tests
# ---------------------------------------------------------------------------

class TestExecutionResult:

    def _result(self):
        from core.engineering.execution.safety import ExecutionResult
        return ExecutionResult.pending("session-001", "Add OAuth login")

    def test_pending_state(self):
        from core.engineering.execution.safety import ExecutionResult, ExecutionStatus
        r = self._result()
        assert r.status == ExecutionStatus.PENDING
        assert r.session_id == "session-001"
        assert r.description == "Add OAuth login"
        assert r.files_written == ()
        assert r.snapshot_sha == ""
        assert r.error == ""
        assert r.completed_at is None

    def test_with_success(self):
        from core.engineering.execution.safety import (
            ExecutionResult, ExecutionStatus, FileChange,
        )
        r = self._result()
        fc = FileChange(path="core/auth.py", operation="create", backup_path="")
        completed = r.with_success(
            files_written=(fc,),
            files_created=("core/auth.py",),
            files_modified=(),
            snapshot_sha="abc1234",
        )
        assert completed.status == ExecutionStatus.COMPLETE
        assert completed.is_complete
        assert not completed.is_failed
        assert completed.snapshot_sha == "abc1234"
        assert len(completed.files_written) == 1
        assert completed.completed_at is not None
        assert completed.duration_seconds is not None
        assert completed.duration_seconds >= 0

    def test_with_failure(self):
        from core.engineering.execution.safety import ExecutionResult, ExecutionStatus
        r = self._result()
        failed = r.with_failure("Permission denied on core/auth.py")
        assert failed.status == ExecutionStatus.FAILED
        assert failed.is_failed
        assert "Permission denied" in failed.error

    def test_with_rollback(self):
        from core.engineering.execution.safety import ExecutionResult, ExecutionStatus
        r = self._result()
        failed = r.with_failure("Something went wrong")
        rolled = failed.with_rollback()
        assert rolled.status == ExecutionStatus.ROLLED_BACK
        assert rolled.is_failed
        assert rolled.error == "Something went wrong"

    def test_is_immutable(self):
        from core.engineering.execution.safety import ExecutionResult
        r = self._result()
        with pytest.raises((AttributeError, TypeError)):
            r.status = "hacked"  # type: ignore[misc]

    def test_original_unchanged_after_transition(self):
        from core.engineering.execution.safety import ExecutionResult, ExecutionStatus
        r = self._result()
        _ = r.with_failure("error")
        assert r.status == ExecutionStatus.PENDING  # original unchanged

    def test_to_summary_success(self):
        from core.engineering.execution.safety import ExecutionResult, FileChange
        r = self._result()
        completed = r.with_success(
            files_written=(FileChange("core/auth.py", "create", ""),),
            files_created=("core/auth.py",),
            files_modified=(),
            snapshot_sha="abc1234",
        )
        summary = completed.to_summary()
        assert "COMPLETE" in summary
        assert "auth.py" in summary

    def test_to_summary_failure(self):
        from core.engineering.execution.safety import ExecutionResult
        r = self._result()
        failed = r.with_failure("File not found")
        summary = failed.to_summary()
        assert "FAILED" in summary
        assert "File not found" in summary

    def test_result_id_is_unique(self):
        from core.engineering.execution.safety import ExecutionResult
        r1 = ExecutionResult.pending("s1", "desc")
        r2 = ExecutionResult.pending("s2", "desc")
        assert r1.result_id != r2.result_id


# ---------------------------------------------------------------------------
# FileChange tests
# ---------------------------------------------------------------------------

class TestFileChange:

    def test_create_operation(self):
        from core.engineering.execution.safety import FileChange
        fc = FileChange(path="core/new.py", operation="create", backup_path="")
        assert fc.operation == "create"
        assert fc.backup_path == ""

    def test_modify_operation(self):
        from core.engineering.execution.safety import FileChange
        fc = FileChange(
            path="core/agent.py",
            operation="modify",
            backup_path=".jarvis_backup/core_agent.py",
        )
        assert fc.backup_path != ""

    def test_is_immutable(self):
        from core.engineering.execution.safety import FileChange
        fc = FileChange("core/x.py", "create", "")
        with pytest.raises((AttributeError, TypeError)):
            fc.path = "hacked"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RollbackResult tests
# ---------------------------------------------------------------------------

class TestRollbackResult:

    def test_succeeded(self):
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        r = RollbackResult(
            status=RollbackStatus.SUCCEEDED,
            message="Rolled back to abc1234.",
            sha="abc1234",
        )
        assert r.status == RollbackStatus.SUCCEEDED

    def test_failed(self):
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        r = RollbackResult(
            status=RollbackStatus.FAILED,
            message="No anchor available.",
            sha="",
        )
        assert r.status == RollbackStatus.FAILED

    def test_is_immutable(self):
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        r = RollbackResult(RollbackStatus.SUCCEEDED, "ok", "abc")
        with pytest.raises((AttributeError, TypeError)):
            r.status = RollbackStatus.FAILED  # type: ignore[misc]


# ---------------------------------------------------------------------------
# GitRollbackStrategy tests
# ---------------------------------------------------------------------------

class TestGitRollbackStrategy:

    def test_name(self):
        from core.engineering.execution.safety import GitRollbackStrategy
        assert GitRollbackStrategy().name == "git_rollback"

    def test_snapshot_success(self):
        from core.engineering.execution.safety import GitRollbackStrategy
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234567890\n"
        with patch("subprocess.run", return_value=mock_result):
            sha = GitRollbackStrategy().snapshot("/repo")
        assert sha == "abc1234567890"

    def test_snapshot_failure_returns_empty(self):
        from core.engineering.execution.safety import GitRollbackStrategy
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not a git repo"
        with patch("subprocess.run", return_value=mock_result):
            sha = GitRollbackStrategy().snapshot("/repo")
        assert sha == ""

    def test_snapshot_exception_returns_empty(self):
        from core.engineering.execution.safety import GitRollbackStrategy
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            sha = GitRollbackStrategy().snapshot("/repo")
        assert sha == ""

    def test_rollback_no_anchor(self):
        from core.engineering.execution.safety import GitRollbackStrategy, RollbackStatus
        result = GitRollbackStrategy().rollback("/repo", "")
        assert result.status == RollbackStatus.FAILED
        assert "No anchor" in result.message

    def test_rollback_success(self):
        from core.engineering.execution.safety import GitRollbackStrategy, RollbackStatus
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = GitRollbackStrategy().rollback("/repo", "abc1234")
        assert result.status == RollbackStatus.SUCCEEDED
        assert "abc1234"[:8] in result.message
        assert result.sha == "abc1234"

    def test_rollback_git_failure(self):
        from core.engineering.execution.safety import GitRollbackStrategy, RollbackStatus
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: pathspec did not match"
        with patch("subprocess.run", return_value=mock_result):
            result = GitRollbackStrategy().rollback("/repo", "abc1234")
        assert result.status == RollbackStatus.FAILED

    def test_rollback_deletes_new_files(self, tmp_path):
        from core.engineering.execution.safety import GitRollbackStrategy, RollbackStatus
        # Create a "new" file that should be deleted on rollback
        new_file = tmp_path / "core" / "new_feature.py"
        new_file.parent.mkdir(parents=True)
        new_file.write_text("# new file")

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = GitRollbackStrategy().rollback(
                str(tmp_path),
                "abc1234",
                files_created=("core/new_feature.py",),
            )
        assert result.status == RollbackStatus.SUCCEEDED
        assert not new_file.exists()

    def test_rollback_exception_returns_failure(self):
        from core.engineering.execution.safety import GitRollbackStrategy, RollbackStatus
        with patch("subprocess.run", side_effect=OSError("permission denied")):
            result = GitRollbackStrategy().rollback("/repo", "abc1234")
        assert result.status == RollbackStatus.FAILED

    def test_is_rollback_strategy_subclass(self):
        from core.engineering.execution.safety import (
            GitRollbackStrategy, RollbackStrategy,
        )
        assert isinstance(GitRollbackStrategy(), RollbackStrategy)

    def test_cannot_instantiate_abstract_strategy(self):
        from core.engineering.execution.safety import RollbackStrategy
        with pytest.raises(TypeError):
            RollbackStrategy()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# PlanValidator tests
# ---------------------------------------------------------------------------

class TestPlanValidator:

    def test_valid_plan_create(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator, ValidationStatus
        pv = PlanValidator()
        plan = {"files_to_create": ["core/new_feature.py"]}
        result = pv.validate(plan, str(tmp_path))
        assert result.is_valid
        assert result.status == ValidationStatus.VALID
        assert "core/new_feature.py" in result.validated_paths
        assert result.repo_root == str(tmp_path)

    def test_valid_plan_modify_existing(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        existing = tmp_path / "core" / "agent.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("# existing")
        pv = PlanValidator()
        plan = {"files_to_modify": ["core/agent.py"]}
        result = pv.validate(plan, str(tmp_path))
        assert result.is_valid

    def test_invalid_modify_nonexistent(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator, ValidationStatus
        pv = PlanValidator()
        plan = {"files_to_modify": ["core/does_not_exist.py"]}
        result = pv.validate(plan, str(tmp_path))
        assert not result.is_valid
        assert result.status == ValidationStatus.INVALID
        assert len(result.errors) == 1
        assert "does not exist" in result.errors[0].message

    def test_path_traversal_rejected(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_create": ["../outside_repo.py"]}
        result = pv.validate(plan, str(tmp_path))
        assert not result.is_valid
        assert any("traversal" in e.message.lower() for e in result.errors)

    def test_absolute_path_rejected(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_create": ["/etc/passwd"]}
        result = pv.validate(plan, str(tmp_path))
        assert not result.is_valid

    def test_empty_plan_rejected(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {}
        result = pv.validate(plan, str(tmp_path))
        assert not result.is_valid
        assert any("no file operations" in e.message.lower() for e in result.errors)

    def test_multiple_operations(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        existing = tmp_path / "core" / "agent.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("# existing")
        pv = PlanValidator()
        plan = {
            "files_to_create": ["core/new.py"],
            "files_to_modify": ["core/agent.py"],
        }
        result = pv.validate(plan, str(tmp_path))
        assert result.is_valid
        assert len(result.validated_paths) == 2

    def test_mixed_valid_invalid(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {
            "files_to_create": ["core/new.py"],
            "files_to_modify": ["core/missing.py"],  # doesn't exist
        }
        result = pv.validate(plan, str(tmp_path))
        assert not result.is_valid
        assert len(result.errors) == 1
        assert len(result.validated_paths) == 1

    def test_to_text_valid(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_create": ["core/new.py"]}
        result = pv.validate(plan, str(tmp_path))
        text = result.to_text()
        assert "valid" in text.lower()
        assert "1 path" in text

    def test_to_text_invalid(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_modify": ["missing.py"]}
        result = pv.validate(plan, str(tmp_path))
        text = result.to_text()
        assert "invalid" in text.lower()
        assert "error" in text.lower()

    def test_nested_path_allowed(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_create": ["core/engineering/execution/worker.py"]}
        result = pv.validate(plan, str(tmp_path))
        assert result.is_valid

    def test_validation_result_is_immutable(self, tmp_path):
        from core.engineering.execution.safety import PlanValidator
        pv = PlanValidator()
        plan = {"files_to_create": ["core/new.py"]}
        result = pv.validate(plan, str(tmp_path))
        with pytest.raises((AttributeError, TypeError)):
            result.status = "hacked"  # type: ignore[misc]
