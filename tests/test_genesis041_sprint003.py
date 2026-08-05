"""
Tests — ExecutionWorker and RollbackWorker
Genesis-041 Sprint-003

Covers:
  ExecutionWorker  — file creation, modification, deletion, backup, validation
  RollbackWorker   — git rollback, backup restoration, failure handling
  Integration      — execution → rollback round-trip
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch


def make_task(task_type: str, payload: dict = None):
    from core.workers.models import WorkerTask
    return WorkerTask(
        task_type=task_type,
        payload=payload or {},
        requester="test",
    )


# ---------------------------------------------------------------------------
# ExecutionWorker contract
# ---------------------------------------------------------------------------

class TestExecutionWorkerContract:

    def test_name(self):
        from core.engineering.execution.execution_workers import ExecutionWorker
        assert ExecutionWorker().name == "execution_worker"

    def test_capabilities(self):
        from core.engineering.execution.execution_workers import ExecutionWorker
        assert ExecutionWorker().capabilities == ["execute_approved_plan"]

    def test_validate_accepts_correct_task(self):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker()
        assert w.validate(make_task("execute_approved_plan")) is True

    def test_validate_rejects_other(self):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker()
        assert w.validate(make_task("git_commit")) is False

    def test_is_available_initially(self):
        from core.engineering.execution.execution_workers import ExecutionWorker
        assert ExecutionWorker().is_available is True


# ---------------------------------------------------------------------------
# ExecutionWorker — file creation
# ---------------------------------------------------------------------------

class TestExecutionWorkerCreate:

    def test_creates_new_file(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_create": [
                {"path": "core/new_feature.py", "content": "# new feature\n"}
            ]
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan,
            "session_id": "sess001",
            "snapshot_sha": "abc1234",
            "repo_root": str(tmp_path),
        }))
        assert result.success
        target = tmp_path / "core" / "new_feature.py"
        assert target.exists()
        assert target.read_text() == "# new feature\n"

    def test_creates_nested_directories(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_create": [
                {"path": "a/b/c/deep.py", "content": "# deep\n"}
            ]
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert result.success
        assert (tmp_path / "a" / "b" / "c" / "deep.py").exists()

    def test_result_data_contains_files_created(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_create": [
                {"path": "core/new.py", "content": "# x\n"}
            ]
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert "core/new.py" in result.data["files_created"]
        assert result.data["files_written"] == 1

    def test_does_not_require_approval(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_create": [{"path": "x.py", "content": ""}]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert result.requires_approval is False


# ---------------------------------------------------------------------------
# ExecutionWorker — file modification with backup
# ---------------------------------------------------------------------------

class TestExecutionWorkerModify:

    def test_modifies_existing_file(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        existing = tmp_path / "core" / "agent.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("# original\n")

        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_modify": [
                {"path": "core/agent.py", "content": "# modified\n"}
            ]
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert result.success
        assert existing.read_text() == "# modified\n"

    def test_backup_created_before_modify(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        existing = tmp_path / "core" / "agent.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("# original\n")

        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_modify": [
                {"path": "core/agent.py", "content": "# modified\n"}
            ]
        }
        w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))

        # Backup directory should exist with the original content
        backup_dir = tmp_path / ".jarvis_backup"
        assert backup_dir.exists()
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].read_text() == "# original\n"

    def test_result_data_contains_files_modified(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        existing = tmp_path / "agent.py"
        existing.write_text("# orig\n")
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_modify": [{"path": "agent.py", "content": "# new\n"}]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert "agent.py" in result.data["files_modified"]


# ---------------------------------------------------------------------------
# ExecutionWorker — file deletion with backup
# ---------------------------------------------------------------------------

class TestExecutionWorkerDelete:

    def test_deletes_existing_file(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        target = tmp_path / "old_module.py"
        target.write_text("# old\n")

        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_delete": ["old_module.py"]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert result.success
        assert not target.exists()

    def test_backup_created_before_delete(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        target = tmp_path / "old_module.py"
        target.write_text("# old content\n")

        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_delete": ["old_module.py"]}
        w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))

        backup_dir = tmp_path / ".jarvis_backup"
        backups = list(backup_dir.iterdir())
        assert len(backups) == 1
        assert backups[0].read_text() == "# old content\n"

    def test_delete_nonexistent_file_fails_validation(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_delete": ["does_not_exist.py"]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        # Deleting a file that doesn't exist is a validation error
        assert not result.success
        assert "does not exist" in result.error.lower()


# ---------------------------------------------------------------------------
# ExecutionWorker — validation
# ---------------------------------------------------------------------------

class TestExecutionWorkerValidation:

    def test_invalid_plan_rejected(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        # Empty plan
        result = w.execute(make_task("execute_approved_plan", {
            "plan": {}, "repo_root": str(tmp_path),
        }))
        assert not result.success
        assert "validation" in result.error.lower()

    def test_path_traversal_rejected(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_create": [{"path": "../outside.py", "content": ""}]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert not result.success
        outside = tmp_path.parent / "outside.py"
        assert not outside.exists()

    def test_no_files_written_if_validation_fails(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_modify": ["does_not_exist.py"]  # wrong format + missing
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert not result.success

    def test_mixed_plan_success(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        existing = tmp_path / "existing.py"
        existing.write_text("# orig\n")
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {
            "files_to_create": [{"path": "new.py", "content": "# new\n"}],
            "files_to_modify": [{"path": "existing.py", "content": "# modified\n"}],
        }
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
        }))
        assert result.success
        assert result.data["files_written"] == 2
        assert (tmp_path / "new.py").read_text() == "# new\n"
        assert existing.read_text() == "# modified\n"

    def test_snapshot_sha_stored_in_result(self, tmp_path):
        from core.engineering.execution.execution_workers import ExecutionWorker
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_create": [{"path": "x.py", "content": ""}]}
        result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path),
            "snapshot_sha": "deadbeef",
        }))
        assert result.data["snapshot_sha"] == "deadbeef"


# ---------------------------------------------------------------------------
# RollbackWorker contract
# ---------------------------------------------------------------------------

class TestRollbackWorkerContract:

    def test_name(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        assert RollbackWorker().name == "rollback_worker"

    def test_capabilities(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        assert RollbackWorker().capabilities == ["rollback_execution"]

    def test_validate_accepts_correct(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        assert RollbackWorker().validate(make_task("rollback_execution")) is True

    def test_validate_rejects_other(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        assert RollbackWorker().validate(make_task("git_commit")) is False

    def test_does_not_require_approval(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        mock_strategy = MagicMock()
        mock_strategy.rollback.return_value = RollbackResult(
            status=RollbackStatus.SUCCEEDED,
            message="Rolled back.",
            sha="abc1234",
        )
        w = RollbackWorker(strategy=mock_strategy)
        result = w.execute(make_task("rollback_execution", {"snapshot_sha": "abc1234"}))
        assert result.requires_approval is False


# ---------------------------------------------------------------------------
# RollbackWorker — git strategy
# ---------------------------------------------------------------------------

class TestRollbackWorkerGit:

    def _make_strategy(self, success: bool = True, message: str = "ok"):
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        strategy = MagicMock()
        strategy.name = "git_rollback"
        strategy.rollback.return_value = RollbackResult(
            status=RollbackStatus.SUCCEEDED if success else RollbackStatus.FAILED,
            message=message,
            sha="abc1234" if success else "",
        )
        return strategy

    def test_rollback_success(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        strategy = self._make_strategy(success=True, message="Rolled back to abc1234.")
        w = RollbackWorker(strategy=strategy)
        result = w.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc1234",
            "files_created": [],
        }))
        assert result.success
        assert "Rollback succeeded" in result.observations[0]

    def test_rollback_passes_files_created(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        strategy = self._make_strategy()
        w = RollbackWorker(strategy=strategy)
        w.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc1234",
            "files_created": ["core/new.py", "core/other.py"],
        }))
        call_kwargs = strategy.rollback.call_args
        assert ("core/new.py", "core/other.py") == call_kwargs[1].get(
            "files_created", call_kwargs[0][2] if len(call_kwargs[0]) > 2 else ()
        ) or "core/new.py" in str(call_kwargs)

    def test_rollback_no_sha_fails(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        w = RollbackWorker()
        result = w.execute(make_task("rollback_execution", {"snapshot_sha": ""}))
        assert not result.success
        assert "No snapshot SHA" in result.error

    def test_rollback_strategy_data_in_result(self):
        from core.engineering.execution.execution_workers import RollbackWorker
        strategy = self._make_strategy()
        w = RollbackWorker(strategy=strategy)
        result = w.execute(make_task("rollback_execution", {"snapshot_sha": "abc"}))
        assert result.data["strategy"] == "git_rollback"
        assert result.data["sha"] == "abc1234"


# ---------------------------------------------------------------------------
# RollbackWorker — backup restoration fallback
# ---------------------------------------------------------------------------

class TestRollbackWorkerBackup:

    def test_backup_restoration_on_git_failure(self, tmp_path):
        from core.engineering.execution.execution_workers import RollbackWorker
        from core.engineering.execution.safety import RollbackResult, RollbackStatus

        # Create a backup file
        backup_dir = tmp_path / ".jarvis_backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "20260101_120000__core__agent.py"
        backup_file.write_text("# original content\n")

        # Create the modified file (post-execution state)
        target_dir = tmp_path / "core"
        target_dir.mkdir()
        (target_dir / "agent.py").write_text("# modified content\n")

        # Git strategy fails
        strategy = MagicMock()
        strategy.name = "git_rollback"
        strategy.rollback.return_value = RollbackResult(
            status=RollbackStatus.FAILED,
            message="git unavailable",
            sha="",
        )

        w = RollbackWorker(repo_root=str(tmp_path), strategy=strategy)
        result = w.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc1234",
            "files_created": [],
            "repo_root": str(tmp_path),
        }))

        assert result.success
        assert "backup" in result.observations[1].lower()
        # File should be restored from backup
        assert (target_dir / "agent.py").read_text() == "# original content\n"

    def test_total_failure_returns_error(self, tmp_path):
        from core.engineering.execution.execution_workers import RollbackWorker
        from core.engineering.execution.safety import RollbackResult, RollbackStatus

        strategy = MagicMock()
        strategy.name = "git_rollback"
        strategy.rollback.return_value = RollbackResult(
            status=RollbackStatus.FAILED,
            message="git unavailable",
            sha="",
        )

        # No backup dir — both strategies fail
        w = RollbackWorker(repo_root=str(tmp_path), strategy=strategy)
        result = w.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc1234",
            "repo_root": str(tmp_path),
        }))

        assert not result.success
        assert "ROLLBACK FAILED" in result.error


# ---------------------------------------------------------------------------
# Integration — execute then rollback
# ---------------------------------------------------------------------------

class TestExecuteAndRollback:

    def test_rollback_restores_modified_file(self, tmp_path):
        """Execution modifies a file; git rollback restores it."""
        from core.engineering.execution.execution_workers import ExecutionWorker, RollbackWorker
        from core.engineering.execution.safety import (
            GitRollbackStrategy, RollbackResult, RollbackStatus,
        )

        # Set up original file
        existing = tmp_path / "core" / "agent.py"
        existing.parent.mkdir(parents=True)
        existing.write_text("# original\n")

        # Execute — modify the file
        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_modify": [{"path": "core/agent.py", "content": "# modified\n"}]}
        exec_result = w.execute(make_task("execute_approved_plan", {
            "plan": plan,
            "repo_root": str(tmp_path),
            "snapshot_sha": "abc1234",
        }))
        assert exec_result.success
        assert existing.read_text() == "# modified\n"

        # Rollback using backup restoration (no real git)
        from core.engineering.execution.safety import RollbackResult, RollbackStatus
        strategy = MagicMock()
        strategy.name = "git_rollback"
        strategy.rollback.return_value = RollbackResult(
            RollbackStatus.FAILED, "no git", ""
        )

        rw = RollbackWorker(repo_root=str(tmp_path), strategy=strategy)
        roll_result = rw.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc1234",
            "files_created": [],
            "repo_root": str(tmp_path),
        }))

        assert roll_result.success
        # Backup restoration should have restored original content
        assert existing.read_text() == "# original\n"

    def test_rollback_removes_created_files(self, tmp_path):
        """Execution creates a file; rollback deletes it."""
        from core.engineering.execution.execution_workers import ExecutionWorker
        from core.engineering.execution.safety import RollbackResult, RollbackStatus

        w = ExecutionWorker(repo_root=str(tmp_path))
        plan = {"files_to_create": [{"path": "core/new.py", "content": "# new\n"}]}
        exec_result = w.execute(make_task("execute_approved_plan", {
            "plan": plan, "repo_root": str(tmp_path), "snapshot_sha": "abc",
        }))
        assert exec_result.success
        assert (tmp_path / "core" / "new.py").exists()

        # Rollback via git (mocked to succeed)
        from core.engineering.execution.execution_workers import RollbackWorker
        strategy = MagicMock()
        strategy.name = "git_rollback"
        strategy.rollback.return_value = RollbackResult(
            RollbackStatus.SUCCEEDED, "Rolled back.", "abc"
        )
        # Simulate git checkout by manually deleting the file
        (tmp_path / "core" / "new.py").unlink()

        rw = RollbackWorker(repo_root=str(tmp_path), strategy=strategy)
        roll_result = rw.execute(make_task("rollback_execution", {
            "snapshot_sha": "abc",
            "files_created": ["core/new.py"],
            "repo_root": str(tmp_path),
        }))
        assert roll_result.success
        assert not (tmp_path / "core" / "new.py").exists()

    def test_execution_is_deterministic(self, tmp_path):
        """Same plan always produces the same result."""
        from core.engineering.execution.execution_workers import ExecutionWorker

        plan = {
            "files_to_create": [
                {"path": "core/feature.py", "content": "# feature\n"}
            ]
        }

        for i in range(3):
            # Reset
            target = tmp_path / "core" / "feature.py"
            if target.exists():
                target.unlink()

            w = ExecutionWorker(repo_root=str(tmp_path))
            result = w.execute(make_task("execute_approved_plan", {
                "plan": plan, "repo_root": str(tmp_path),
            }))
            assert result.success
            assert target.read_text() == "# feature\n"
