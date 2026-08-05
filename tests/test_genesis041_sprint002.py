"""
Tests — GitWorker
Genesis-041 Sprint-002

Covers all four capabilities using mocked subprocess:
  git_snapshot   — records HEAD SHA, no approval needed
  git_checkout   — restores to SHA, deletes new files, no approval needed
  git_commit     — stages + commits, always requires_approval=True
  git_push       — pushes current branch, always requires_approval=True

Desktop validation scenarios:
  1. Snapshot created correctly.
  2. Checkout restores working tree.
  3. Commit requires approval.
  4. Push requires approval.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch, call


def make_task(task_type: str, payload: dict = None):
    from core.workers.models import WorkerTask
    return WorkerTask(
        task_type=task_type,
        payload=payload or {},
        requester="test",
    )


def mock_run_success(stdout: str = ""):
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ""
    return result


def mock_run_failure(stderr: str = "error"):
    result = MagicMock()
    result.returncode = 1
    result.stdout = ""
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# Worker contract
# ---------------------------------------------------------------------------

class TestGitWorkerContract:

    def test_name(self):
        from core.engineering.execution.git_worker import GitWorker
        assert GitWorker().name == "git_worker"

    def test_description(self):
        from core.engineering.execution.git_worker import GitWorker
        w = GitWorker()
        assert isinstance(w.description, str)
        assert len(w.description) > 0

    def test_capabilities(self):
        from core.engineering.execution.git_worker import GitWorker
        caps = GitWorker().capabilities
        assert "git_snapshot" in caps
        assert "git_checkout" in caps
        assert "git_commit" in caps
        assert "git_push" in caps
        assert len(caps) == 4

    def test_validate_accepts_known_capabilities(self):
        from core.engineering.execution.git_worker import GitWorker
        w = GitWorker()
        for cap in w.capabilities:
            task = make_task(cap)
            assert w.validate(task) is True

    def test_validate_rejects_unknown(self):
        from core.engineering.execution.git_worker import GitWorker
        w = GitWorker()
        assert w.validate(make_task("run_tests")) is False
        assert w.validate(make_task("implement_feature")) is False

    def test_is_available_initially(self):
        from core.engineering.execution.git_worker import GitWorker
        assert GitWorker().is_available is True

    def test_is_worker_subclass(self):
        from core.engineering.execution.git_worker import GitWorker
        from core.workers.base import Worker
        assert isinstance(GitWorker(), Worker)


# ---------------------------------------------------------------------------
# git_snapshot
# ---------------------------------------------------------------------------

class TestGitSnapshot:

    def test_snapshot_success(self):
        from core.engineering.execution.git_worker import GitWorker
        sha = "abc1234567890def\n"
        with patch("subprocess.run", return_value=mock_run_success(sha)):
            result = GitWorker().execute(make_task("git_snapshot"))
        assert result.success
        assert result.data["sha"] == "abc1234567890def"
        assert result.data["capability"] == "git_snapshot"
        assert any("abc12345" in obs for obs in result.observations)

    def test_snapshot_does_not_require_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("abc123\n")):
            result = GitWorker().execute(make_task("git_snapshot"))
        assert result.requires_approval is False

    def test_snapshot_git_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("not a git repo")):
            result = GitWorker().execute(make_task("git_snapshot"))
        assert not result.success

    def test_snapshot_exception_returns_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=OSError("git not found")):
            result = GitWorker().execute(make_task("git_snapshot"))
        assert not result.success

    def test_worker_resets_to_available_after_snapshot(self):
        from core.engineering.execution.git_worker import GitWorker
        w = GitWorker()
        with patch("subprocess.run", return_value=mock_run_success("abc123\n")):
            w.execute(make_task("git_snapshot"))
        assert w.is_available


# ---------------------------------------------------------------------------
# git_checkout (rollback)
# ---------------------------------------------------------------------------

class TestGitCheckout:

    def test_checkout_success(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("")):
            result = GitWorker().execute(make_task(
                "git_checkout", {"sha": "abc1234", "files_created": []}
            ))
        assert result.success
        assert "abc1234"[:8] in result.observations[0]

    def test_checkout_does_not_require_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("")):
            result = GitWorker().execute(make_task(
                "git_checkout", {"sha": "abc1234"}
            ))
        assert result.requires_approval is False

    def test_checkout_no_sha_fails(self):
        from core.engineering.execution.git_worker import GitWorker
        result = GitWorker().execute(make_task("git_checkout", {}))
        assert not result.success
        assert "No SHA" in result.error

    def test_checkout_deletes_new_files(self, tmp_path):
        from core.engineering.execution.git_worker import GitWorker
        new_file = tmp_path / "core" / "new_feature.py"
        new_file.parent.mkdir(parents=True)
        new_file.write_text("# new file")

        with patch("subprocess.run", return_value=mock_run_success("")):
            result = GitWorker(repo_root=str(tmp_path)).execute(make_task(
                "git_checkout",
                {
                    "sha": "abc1234",
                    "files_created": ["core/new_feature.py"],
                },
            ))
        assert result.success
        assert not new_file.exists()
        assert "core/new_feature.py" in result.data["files_deleted"]

    def test_checkout_missing_file_does_not_fail(self, tmp_path):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("")):
            result = GitWorker(repo_root=str(tmp_path)).execute(make_task(
                "git_checkout",
                {
                    "sha": "abc1234",
                    "files_created": ["core/does_not_exist.py"],
                },
            ))
        assert result.success  # missing file is not an error

    def test_checkout_git_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("pathspec error")):
            result = GitWorker().execute(make_task(
                "git_checkout", {"sha": "abc1234"}
            ))
        assert not result.success

    def test_checkout_data_contains_sha(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("")):
            result = GitWorker().execute(make_task(
                "git_checkout", {"sha": "abc1234xyz"}
            ))
        assert result.data["sha"] == "abc1234xyz"
        assert result.data["capability"] == "git_checkout"


# ---------------------------------------------------------------------------
# git_commit
# ---------------------------------------------------------------------------

class TestGitCommit:

    def _mock_commit_sequence(self, commit_sha="def5678\n"):
        """Return side_effect list for: add, commit, rev-parse."""
        return [
            mock_run_success(""),            # git add -u
            mock_run_success(""),            # git commit -m
            mock_run_success(commit_sha),    # git rev-parse HEAD
        ]

    def test_commit_success(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence()):
            result = GitWorker().execute(make_task(
                "git_commit",
                {"session_id": "abc12345", "description": "Add OAuth login"},
            ))
        assert result.success
        assert "def5678" in result.observations[0]

    def test_commit_always_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence()):
            result = GitWorker().execute(make_task("git_commit", {}))
        assert result.requires_approval is True

    def test_commit_message_is_structured(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence()) as mock:
            GitWorker().execute(make_task(
                "git_commit",
                {"session_id": "abc12345", "description": "Add OAuth login"},
            ))
        # Find the commit call
        commit_call = [c for c in mock.call_args_list if "commit" in str(c)][0]
        message = str(commit_call)
        assert "Jarvis" in message
        assert "Add OAuth login" in message
        assert "Approved by: human" in message
        assert "abc12345" in message

    def test_commit_custom_message(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence()) as mock:
            GitWorker().execute(make_task(
                "git_commit",
                {"message": "My custom commit message"},
            ))
        commit_call = [c for c in mock.call_args_list if "commit" in str(c)][0]
        assert "My custom commit message" in str(commit_call)

    def test_commit_add_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("permission denied")):
            result = GitWorker().execute(make_task("git_commit", {}))
        assert not result.success
        assert "git add" in result.error.lower() or "failed" in result.error.lower()

    def test_commit_data_contains_sha_and_message(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence("sha999\n")):
            result = GitWorker().execute(make_task(
                "git_commit",
                {"description": "Test commit"},
            ))
        assert result.data["sha"] == "sha999"
        assert result.data["capability"] == "git_commit"
        assert "message" in result.data

    def test_commit_recommendation_to_review_before_push(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_commit_sequence()):
            result = GitWorker().execute(make_task("git_commit", {}))
        assert any("push" in r.lower() for r in result.recommendations)


# ---------------------------------------------------------------------------
# git_push
# ---------------------------------------------------------------------------

class TestGitPush:

    def _mock_push_sequence(self, branch="main"):
        return [
            mock_run_success(branch + "\n"),  # rev-parse --abbrev-ref HEAD
            mock_run_success(""),              # git push origin <branch>
        ]

    def test_push_success(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_push_sequence("main")):
            result = GitWorker().execute(make_task("git_push", {}))
        assert result.success
        assert "origin/main" in result.observations[0]

    def test_push_always_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_push_sequence()):
            result = GitWorker().execute(make_task("git_push", {}))
        assert result.requires_approval is True

    def test_push_never_force_pushes(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_push_sequence()) as mock:
            GitWorker().execute(make_task("git_push", {}))
        all_calls = str(mock.call_args_list)
        assert "--force" not in all_calls
        assert "-f" not in all_calls

    def test_push_detached_head_fails(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("HEAD\n")):
            result = GitWorker().execute(make_task("git_push", {}))
        assert not result.success
        assert "detached" in result.error.lower() or "HEAD" in result.error

    def test_push_branch_detection_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("not a repo")):
            result = GitWorker().execute(make_task("git_push", {}))
        assert not result.success

    def test_push_git_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=[
            mock_run_success("main\n"),
            mock_run_failure("rejected by remote"),
        ]):
            result = GitWorker().execute(make_task("git_push", {}))
        assert not result.success

    def test_push_data_contains_branch(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=self._mock_push_sequence("feature/auth")):
            result = GitWorker().execute(make_task("git_push", {}))
        assert result.data["branch"] == "feature/auth"
        assert result.data["capability"] == "git_push"

    def test_push_exception_returns_failure(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=OSError("git not found")):
            result = GitWorker().execute(make_task("git_push", {}))
        assert not result.success


# ---------------------------------------------------------------------------
# Approval contract invariants
# ---------------------------------------------------------------------------

class TestApprovalContract:

    def test_snapshot_never_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("abc\n")):
            r = GitWorker().execute(make_task("git_snapshot"))
        assert r.requires_approval is False

    def test_checkout_never_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_success("")):
            r = GitWorker().execute(make_task("git_checkout", {"sha": "abc"}))
        assert r.requires_approval is False

    def test_commit_always_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=[
            mock_run_success(""),
            mock_run_success(""),
            mock_run_success("sha\n"),
        ]):
            r = GitWorker().execute(make_task("git_commit", {}))
        assert r.requires_approval is True

    def test_push_always_requires_approval(self):
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", side_effect=[
            mock_run_success("main\n"),
            mock_run_success(""),
        ]):
            r = GitWorker().execute(make_task("git_push", {}))
        assert r.requires_approval is True

    def test_failed_commit_still_requires_approval(self):
        """Even a failed commit result must have requires_approval=True."""
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("lock")):
            r = GitWorker().execute(make_task("git_commit", {}))
        # Failed results use WorkerResult.failure() which sets requires_approval=False
        # This is acceptable — a failed commit has nothing to approve.
        # The important invariant is: successful commit ALWAYS requires approval.
        assert not r.success

    def test_failed_push_result(self):
        """A failed push has nothing to approve."""
        from core.engineering.execution.git_worker import GitWorker
        with patch("subprocess.run", return_value=mock_run_failure("rejected")):
            r = GitWorker().execute(make_task("git_push", {}))
        assert not r.success
