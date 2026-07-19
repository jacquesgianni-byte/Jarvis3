"""
Jarvis Engineering Worker (Genesis-021 Sprint-002)

Read-only repository analysis worker.

Responsibilities:
    - Analyse repository structure recursively
    - Count Python and test files
    - Identify packages (directories with __init__.py)
    - Return structured engineering report via WorkerResult

Constraints:
    - No AI calls
    - No memory access
    - No repository modification
    - No Git operations
    - Read-only filesystem access only
    - requires_approval=True on all results

Task type: "analyse_repository"
Payload:   {"root_path": "/optional/override/path"}
           root_path defaults to cwd if omitted.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)

# Directories to skip during recursive analysis
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", "venv", ".env",
    ".pytest_cache", ".mypy_cache", ".tox", "node_modules",
    "dist", "build", ".eggs", "*.egg-info",
})


def _should_skip(directory: str) -> bool:
    """Return True if this directory name should be excluded from analysis."""
    return directory in _SKIP_DIRS or directory.endswith(".egg-info")


class EngineeringWorker(Worker):
    """
    Read-only repository analysis worker.

    Recursively scans the repository and produces a structured
    engineering report. Safe to run at any time — no side effects.

    Registers under name "engineering" with capability "analyse_repository".
    """

    @property
    def name(self) -> str:
        return "engineering"

    @property
    def description(self) -> str:
        return (
            "Read-only repository analysis. Counts files, identifies "
            "packages, and produces a structured engineering report."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["analyse_repository"]

    def validate(self, task: WorkerTask) -> bool:
        """
        Validate the task.

        Always valid if task_type matches. If root_path is provided
        in payload, check it exists.
        """
        if task.task_type not in self.capabilities:
            return False
        root_path = task.payload.get("root_path")
        if root_path is not None:
            return Path(root_path).exists()
        return True

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Analyse the repository and return a WorkerResult.

        Args:
            task: WorkerTask with optional payload["root_path"].

        Returns:
            WorkerResult with observations (human-readable) and
            data (structured, machine-readable for future workers).
        """
        self._begin(task)

        try:
            root = Path(task.payload.get("root_path") or os.getcwd()).resolve()
            logger.info("[ENGINEERING] Analysing repository at: %s", root)

            report = self._analyse(root)
            observations = self._build_observations(root, report)
            data = self._build_data(root, report)

            result = WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=True,
                observations=tuple(observations),
                recommendations=self._build_recommendations(report),
                requires_approval=True,
                data=data,
            )
            logger.info(
                "[ENGINEERING] Analysis complete: %d py files, %d packages",
                report["python_file_count"], len(report["packages"]),
            )
            return self._succeed(result)

        except Exception as exc:
            logger.exception("[ENGINEERING] Analysis failed.")
            return self._fail(task.task_id, str(exc))

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _analyse(self, root: Path) -> dict[str, Any]:
        """
        Recursively scan the repository. Returns a raw report dict.
        """
        python_files: list[str] = []
        test_files:   list[str] = []
        packages:     list[str] = []
        all_files:    list[str] = []
        files_by_package: dict[str, int] = {}

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories in-place so os.walk won't recurse
            dirnames[:] = [
                d for d in dirnames if not _should_skip(d)
            ]

            rel_dir = Path(dirpath).relative_to(root)
            rel_dir_str = str(rel_dir) if str(rel_dir) != "." else ""

            # Detect packages
            if "__init__.py" in filenames:
                pkg = rel_dir_str or root.name
                packages.append(pkg)

            py_count_here = 0
            for filename in filenames:
                rel_path = str(rel_dir / filename) if rel_dir_str else filename
                all_files.append(rel_path)

                if filename.endswith(".py"):
                    python_files.append(rel_path)
                    py_count_here += 1

                    if filename.startswith("test_") or filename.endswith("_test.py"):
                        test_files.append(rel_path)

            if py_count_here and rel_dir_str:
                pkg_key = rel_dir_str
                files_by_package[pkg_key] = (
                    files_by_package.get(pkg_key, 0) + py_count_here
                )

        # Largest package by Python file count
        largest_pkg = ""
        largest_count = 0
        if files_by_package:
            largest_pkg = max(files_by_package, key=lambda k: files_by_package[k])
            largest_count = files_by_package[largest_pkg]

        return {
            "root":               str(root),
            "python_files":       sorted(python_files),
            "test_files":         sorted(test_files),
            "packages":           sorted(packages),
            "all_files":          all_files,
            "python_file_count":  len(python_files),
            "test_file_count":    len(test_files),
            "total_file_count":   len(all_files),
            "package_count":      len(packages),
            "files_by_package":   files_by_package,
            "largest_package":    largest_pkg,
            "largest_pkg_count":  largest_count,
        }

    # ------------------------------------------------------------------
    # Human-readable observations
    # ------------------------------------------------------------------

    def _build_observations(self, root: Path, report: dict) -> list[str]:
        obs = [
            f"Repository root: {root}",
            f"Python files: {report['python_file_count']}",
            f"Test files: {report['test_file_count']}",
            f"Total files: {report['total_file_count']}",
            f"Packages identified: {report['package_count']}",
        ]

        if report["packages"]:
            pkg_list = ", ".join(report["packages"][:10])
            suffix = f" (and {len(report['packages']) - 10} more)" \
                if len(report["packages"]) > 10 else ""
            obs.append(f"Packages: {pkg_list}{suffix}")

        if report["largest_package"]:
            obs.append(
                f"Largest package: {report['largest_package']} "
                f"({report['largest_pkg_count']} Python files)"
            )

        if report["test_file_count"] > 0 and report["python_file_count"] > 0:
            ratio = report["test_file_count"] / report["python_file_count"]
            obs.append(f"Test coverage ratio: {ratio:.1%} (test files / py files)")

        return obs

    # ------------------------------------------------------------------
    # Structured data for future workers
    # ------------------------------------------------------------------

    def _build_data(self, root: Path, report: dict) -> dict[str, Any]:
        return {
            "root":              str(root),
            "python_file_count": report["python_file_count"],
            "test_file_count":   report["test_file_count"],
            "total_file_count":  report["total_file_count"],
            "package_count":     report["package_count"],
            "packages":          report["packages"],
            "test_files":        report["test_files"],
            "python_files":      report["python_files"],
            "files_by_package":  report["files_by_package"],
            "largest_package":   report["largest_package"],
            "largest_pkg_count": report["largest_pkg_count"],
        }

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(self, report: dict) -> tuple[str, ...]:
        recs = []

        if report["test_file_count"] == 0:
            recs.append("No test files found. Consider adding a test suite.")
        elif report["python_file_count"] > 0:
            ratio = report["test_file_count"] / report["python_file_count"]
            if ratio < 0.3:
                recs.append(
                    f"Test coverage ratio is low ({ratio:.1%}). "
                    f"Consider adding more tests."
                )

        if report["package_count"] == 0:
            recs.append(
                "No Python packages detected. "
                "Add __init__.py files to create packages."
            )

        if not recs:
            recs.append(
                "Repository structure looks healthy. "
                "No immediate recommendations."
            )

        return tuple(recs)