"""
Jarvis Test Worker (Genesis-027 Sprint-001)

Runs the Jarvis test suite programmatically and returns a structured result.

Responsibilities:
    - Accept a WorkerTask with task_type="run_tests"
    - Run pytest on the specified test paths
    - Return pass/fail counts, duration, and any failures
    - Never modify code

Design constraints:
    - No AI calls
    - Read-only — never modifies repository
    - Runs pytest in-process via pytest.main()
    - Returns structured WorkerResult

Task payload (all optional):
    {
        "paths":   list[str]   # test paths, default ["tests/"]
        "markers": str         # pytest -m expression, default ""
        "verbose": bool        # -v flag, default False
    }

Result data:
    {
        "passed":   int,
        "failed":   int,
        "skipped":  int,
        "errors":   int,
        "duration": float,     # seconds
        "exit_code": int,      # pytest exit code
        "failures": list[str], # failed test node IDs
    }

Genesis-027 Sprint-001.
"""

from __future__ import annotations

import logging
import pathlib
import time
from core.workers.base import Worker
from core.workers.models import WorkerResult, WorkerTask

logger = logging.getLogger(__name__)


class SuiteRunnerWorker(Worker):
    """
    Runs the Jarvis test suite and returns a structured result.

    Uses pytest.main() to run tests in-process. Returns pass/fail
    counts, duration, and failure details as structured data.

    Capabilities:
        run_tests — execute the pytest suite
    """

    # ------------------------------------------------------------------
    # Worker contract
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "suite_runner_worker"

    @property
    def description(self) -> str:
        return (
            "Runs the Jarvis test suite using pytest. "
            "Returns structured pass/fail counts, duration, and failure details. "
            "Never modifies code."
        )

    @property
    def capabilities(self) -> list[str]:
        return ["run_tests"]

    def validate(self, task: WorkerTask) -> bool:
        """Validate that the task type is run_tests."""
        return task.task_type == "run_tests"

    def execute(self, task: WorkerTask) -> WorkerResult:
        """
        Run pytest and return a structured WorkerResult.

        Args:
            task: WorkerTask with optional payload keys:
                  paths, markers, verbose

        Returns:
            WorkerResult with test counts and any failure details.
        """
        self._begin(task)

        try:
            import subprocess, re as _re, sys as _sys

            paths   = task.payload.get("paths", ["tests/"])
            markers = task.payload.get("markers", "")
            verbose = task.payload.get("verbose", False)

            args = [_sys.executable, "-m", "pytest"] + list(paths)
            args += ["--tb=line", "-q", "-p", "no:cacheprovider"]
            if verbose:
                args += ["-v"]
            if markers:
                args += ["-m", markers]

            logger.info("[TEST_WORKER] Running pytest subprocess: %s", args)
            start = time.perf_counter()

            # Fresh subprocess — no module cache contamination (Sprint-004 Gap B)
            repo_root = pathlib.Path(__file__).resolve().parents[2]  # jarvis3/
            proc = subprocess.run(args, capture_output=True, text=True, timeout=300, cwd=str(repo_root))
            duration = time.perf_counter() - start
            output = proc.stdout + proc.stderr

            passed = failed = skipped = errors = 0
            failures: list[str] = []

            m_passed  = _re.search(r"(\d+) passed",  output)
            m_failed  = _re.search(r"(\d+) failed",  output)
            m_skipped = _re.search(r"(\d+) skipped", output)
            m_error   = _re.search(r"(\d+) error",   output)
            if m_passed:  passed  = int(m_passed.group(1))
            if m_failed:  failed  = int(m_failed.group(1))
            if m_skipped: skipped = int(m_skipped.group(1))
            if m_error:   errors  = int(m_error.group(1))

            for line in output.splitlines():
                if line.startswith("FAILED "):
                    failures.append(line[7:].strip())

            exit_code = proc.returncode
            # exit_code 5 = no tests collected (not a failure)
            success = (exit_code in (0, 5)) and failed == 0 and errors == 0
            total = passed + failed + skipped

            observations = [
                f"Ran {total} tests in {duration:.1f}s (fresh subprocess)",
                f"Passed: {passed}",
                f"Failed: {failed}",
                f"Skipped: {skipped}",
            ]
            if failures:
                observations.append(f"Failures: {', '.join(failures[:5])}")

            recommendations = []
            if failed > 0:
                recommendations.append(
                    f"Investigate {failed} failing test(s): "
                    + ", ".join(failures[:3])
                )
            if success:
                recommendations.append(
                    "All tests passing — safe to proceed with next sprint."
                )

            logger.info(
                "[TEST_WORKER] Complete: passed=%d failed=%d skipped=%d exit=%d in %.1fs",
                passed, failed, skipped, exit_code, duration,
            )

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=success,
                observations=tuple(observations),
                recommendations=tuple(recommendations),
                requires_approval=False,
                data={
                    "passed":    passed,
                    "failed":    failed,
                    "skipped":   skipped,
                    "errors":    errors,
                    "duration":  round(duration, 2),
                    "exit_code": exit_code,
                    "failures":  failures,
                },
            ))

        except Exception as exc:
            logger.exception("[TEST_WORKER] Test run failed.")
            return self._fail(task.task_id, str(exc))