"""
Genesis-021 Sprint-002 — Engineering Worker Tests
Completely self-contained.

Coverage:
  - Worker registration with WorkerManager
  - Successful repository analysis (real filesystem)
  - Empty directory handling
  - Skip directories honoured (__pycache__, .git, etc.)
  - validate() with valid/invalid/missing root_path
  - WorkerResult.observations populated
  - WorkerResult.data populated and structured
  - WorkerResult.requires_approval=True
  - WorkerResult.recommendations populated
  - Exception handling → failure result
  - Read-only: no files created or modified
  - Backwards compatibility
"""

import sys
import tempfile
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.engineering_worker import EngineeringWorker
from core.workers.manager import WorkerManager
from core.workers.models import WorkerTask, WorkerResult, WorkerStatus
from core.workers.exceptions import WorkerNotFoundError, InvalidTaskError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_task(root_path=None, **kwargs) -> WorkerTask:
    payload = {}
    if root_path is not None:
        payload["root_path"] = str(root_path)
    return WorkerTask(task_type="analyse_repository", payload=payload, **kwargs)


def make_worker() -> EngineeringWorker:
    return EngineeringWorker()


def make_manager_with_worker() -> WorkerManager:
    m = WorkerManager()
    m.register(EngineeringWorker())
    return m


def make_temp_repo(structure: dict) -> Path:
    """
    Create a temporary directory with the given structure.
    structure: {"path/to/file.py": "content", ...}
    Returns the root Path.
    """
    tmp = tempfile.mkdtemp()
    root = Path(tmp)
    for rel_path, content in structure.items():
        full = root / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
    return root


# ===========================================================================
# 1. WORKER INTERFACE
# ===========================================================================

class TestEngineeringWorkerInterface:

    def test_name_is_engineering(self):
        assert make_worker().name == "engineering"

    def test_has_description(self):
        assert make_worker().description

    def test_capabilities_include_analyse_repository(self):
        assert "analyse_repository" in make_worker().capabilities

    def test_starts_idle(self):
        assert make_worker().status() == WorkerStatus.IDLE

    def test_is_available(self):
        assert make_worker().is_available

    def test_last_result_none_initially(self):
        assert make_worker().last_result is None


# ===========================================================================
# 2. REGISTRATION
# ===========================================================================

class TestEngineeringWorkerRegistration:

    def test_registers_with_manager(self):
        m = make_manager_with_worker()
        assert m.has_worker("engineering")

    def test_appears_in_all_workers(self):
        m = make_manager_with_worker()
        names = [w.name for w in m.all_workers()]
        assert "engineering" in names

    def test_discoverable_by_capability(self):
        m = make_manager_with_worker()
        workers = m.workers_for("analyse_repository")
        assert len(workers) == 1
        assert workers[0].name == "engineering"

    def test_available_after_registration(self):
        m = make_manager_with_worker()
        assert len(m.available_workers()) == 1

    def test_duplicate_registration_raises(self):
        from core.workers.exceptions import WorkerAlreadyRegisteredError
        m = make_manager_with_worker()
        with pytest.raises(WorkerAlreadyRegisteredError):
            m.register(EngineeringWorker())


# ===========================================================================
# 3. VALIDATE
# ===========================================================================

class TestEngineeringWorkerValidate:

    def test_validate_no_root_path(self):
        w = make_worker()
        task = make_task()  # no root_path — defaults to cwd
        assert w.validate(task)

    def test_validate_valid_root_path(self):
        w = make_worker()
        task = make_task(root_path=REPO_ROOT)
        assert w.validate(task)

    def test_validate_nonexistent_root_path(self):
        w = make_worker()
        task = make_task(root_path="/nonexistent/path/xyz")
        assert not w.validate(task)

    def test_validate_wrong_task_type(self):
        w = make_worker()
        task = WorkerTask(task_type="wrong_type")
        assert not w.validate(task)


# ===========================================================================
# 4. SUCCESSFUL ANALYSIS — real repo
# ===========================================================================

class TestEngineeringWorkerRealRepo:

    def setup_method(self):
        self.worker = make_worker()
        self.task = make_task(root_path=REPO_ROOT)
        self.result = self.worker.execute(self.task)

    def test_result_is_success(self):
        assert self.result.success

    def test_result_requires_approval(self):
        assert self.result.requires_approval

    def test_result_worker_name(self):
        assert self.result.worker_name == "engineering"

    def test_result_task_id_matches(self):
        assert self.result.task_id == self.task.task_id

    def test_observations_non_empty(self):
        assert len(self.result.observations) > 0

    def test_observations_mention_root(self):
        assert any("root" in obs.lower() or str(REPO_ROOT) in obs
                   for obs in self.result.observations)

    def test_observations_mention_python_files(self):
        assert any("python" in obs.lower() or "py" in obs.lower()
                   for obs in self.result.observations)

    def test_observations_mention_packages(self):
        assert any("package" in obs.lower()
                   for obs in self.result.observations)

    def test_data_has_python_file_count(self):
        assert "python_file_count" in self.result.data
        assert self.result.data["python_file_count"] > 0

    def test_data_has_test_file_count(self):
        assert "test_file_count" in self.result.data
        assert self.result.data["test_file_count"] > 0

    def test_data_has_packages(self):
        assert "packages" in self.result.data
        assert len(self.result.data["packages"]) > 0

    def test_data_packages_includes_core(self):
        pkgs = self.result.data["packages"]
        assert any("core" in p for p in pkgs)

    def test_data_has_root(self):
        assert "root" in self.result.data

    def test_data_has_files_by_package(self):
        assert "files_by_package" in self.result.data
        assert isinstance(self.result.data["files_by_package"], dict)

    def test_data_has_largest_package(self):
        assert "largest_package" in self.result.data

    def test_recommendations_non_empty(self):
        assert len(self.result.recommendations) > 0

    def test_worker_status_completed(self):
        assert self.worker.status() == WorkerStatus.COMPLETED

    def test_worker_last_result_set(self):
        assert self.worker.last_result is self.result

    def test_no_files_created(self):
        """Worker must not create any files."""
        files_before = set(REPO_ROOT.rglob("*.py"))
        make_worker().execute(make_task(root_path=REPO_ROOT))
        files_after = set(REPO_ROOT.rglob("*.py"))
        assert files_before == files_after


# ===========================================================================
# 5. TEMP REPO ANALYSIS
# ===========================================================================

class TestEngineeringWorkerTempRepo:

    def test_counts_python_files(self):
        root = make_temp_repo({
            "core/__init__.py": "",
            "core/module.py": "",
            "utils.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        assert result.success
        assert result.data["python_file_count"] == 3

    def test_counts_test_files(self):
        root = make_temp_repo({
            "tests/test_module.py": "",
            "tests/test_other.py": "",
            "module.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        assert result.data["test_file_count"] == 2

    def test_identifies_packages(self):
        root = make_temp_repo({
            "core/__init__.py": "",
            "core/sub/__init__.py": "",
            "module.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        assert result.data["package_count"] >= 2

    def test_skips_pycache(self):
        root = make_temp_repo({
            "module.py": "",
            "__pycache__/module.cpython-311.pyc": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        # __pycache__ .pyc files should NOT count as python files
        pyc_in_results = any(
            "__pycache__" in f
            for f in result.data.get("python_files", [])
        )
        assert not pyc_in_results

    def test_skips_git_directory(self):
        root = make_temp_repo({
            "module.py": "",
            ".git/config": "[core]",
            ".git/HEAD": "ref: refs/heads/main",
        })
        result = make_worker().execute(make_task(root_path=root))
        git_in_results = any(
            ".git" in f for f in result.data.get("all_files", [])
        )
        assert not git_in_results

    def test_skips_venv(self):
        root = make_temp_repo({
            "module.py": "",
            ".venv/lib/python3.11/site.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        venv_in_results = any(
            ".venv" in f for f in result.data.get("python_files", [])
        )
        assert not venv_in_results

    def test_empty_directory(self):
        import tempfile
        root = Path(tempfile.mkdtemp())
        result = make_worker().execute(make_task(root_path=root))
        assert result.success
        assert result.data["python_file_count"] == 0
        assert result.data["test_file_count"] == 0
        assert result.data["package_count"] == 0

    def test_no_packages_recommendation(self):
        root = make_temp_repo({"module.py": ""})
        result = make_worker().execute(make_task(root_path=root))
        assert any("package" in r.lower() for r in result.recommendations)

    def test_low_test_ratio_recommendation(self):
        root = make_temp_repo({
            "core/__init__.py": "",
            "core/a.py": "", "core/b.py": "", "core/c.py": "",
            "core/d.py": "", "core/e.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        # 0 test files, 6 py files → low ratio recommendation
        assert any("test" in r.lower() for r in result.recommendations)

    def test_healthy_repo_positive_recommendation(self):
        root = make_temp_repo({
            "core/__init__.py": "",
            "core/module.py": "",
            "tests/test_module.py": "",
            "tests/test_other.py": "",
        })
        result = make_worker().execute(make_task(root_path=root))
        assert len(result.recommendations) > 0

    def test_default_root_path_uses_cwd(self):
        """Task with no root_path defaults to cwd."""
        task = make_task()  # no root_path
        result = make_worker().execute(task)
        assert result.success
        assert "root" in result.data


# ===========================================================================
# 6. EXCEPTION HANDLING
# ===========================================================================

class TestEngineeringWorkerExceptions:

    def test_invalid_root_path_via_manager(self):
        """Manager validates before executing — raises InvalidTaskError."""
        m = make_manager_with_worker()
        task = make_task(root_path="/nonexistent/path/xyz")
        with pytest.raises(InvalidTaskError):
            m.execute("engineering", task)

    def test_permission_error_returns_failure(self):
        """If os.walk raises, worker returns failure result."""
        import unittest.mock as mock
        worker = make_worker()
        with mock.patch("os.walk", side_effect=PermissionError("Access denied")):
            result = worker.execute(make_task())
        assert not result.success
        assert "Access denied" in result.error or result.error


# ===========================================================================
# 7. EXECUTE VIA MANAGER
# ===========================================================================

class TestEngineeringWorkerViaManager:

    def test_execute_via_manager(self):
        m = make_manager_with_worker()
        result = m.execute("engineering", make_task(root_path=REPO_ROOT))
        assert result.success

    def test_execute_for_type_via_manager(self):
        m = make_manager_with_worker()
        result = m.execute_for_type(
            "analyse_repository", make_task(root_path=REPO_ROOT)
        )
        assert result.success

    def test_result_requires_approval_via_manager(self):
        m = make_manager_with_worker()
        result = m.execute("engineering", make_task(root_path=REPO_ROOT))
        assert result.requires_approval

    def test_worker_available_after_execution(self):
        m = make_manager_with_worker()
        m.execute("engineering", make_task(root_path=REPO_ROOT))
        assert m.status("engineering") == WorkerStatus.COMPLETED
        assert m.get_worker("engineering").is_available


# ===========================================================================
# 8. READ-ONLY GUARANTEE
# ===========================================================================

class TestEngineeringWorkerReadOnly:

    def test_does_not_modify_any_file(self):
        root = make_temp_repo({
            "module.py": "# original",
            "core/__init__.py": "",
        })
        content_before = (root / "module.py").read_text()
        make_worker().execute(make_task(root_path=root))
        content_after = (root / "module.py").read_text()
        assert content_before == content_after

    def test_does_not_create_new_files(self):
        root = make_temp_repo({"module.py": ""})
        files_before = set(root.iterdir())
        make_worker().execute(make_task(root_path=root))
        files_after = set(root.iterdir())
        assert files_before == files_after


# ===========================================================================
# 9. BACKWARDS COMPATIBILITY
# ===========================================================================

class TestBackwardsCompatibility:

    def test_worker_framework_unchanged(self):
        from core.workers.manager import WorkerManager
        from core.workers.registry import WorkerRegistry
        m = WorkerManager()
        assert m.worker_count() == 0

    def test_existing_router_unchanged(self):
        from core.router import IntentRouter
        from core.intents import Intent
        assert IntentRouter().detect("Hello.") == Intent.GREETING

    def test_engineering_worker_importable(self):
        from core.workers.engineering_worker import EngineeringWorker
        assert EngineeringWorker is not None