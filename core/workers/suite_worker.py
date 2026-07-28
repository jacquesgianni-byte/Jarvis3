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
import time
from io import StringIO

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
            import pytest

            paths   = task.payload.get("paths", ["tests/"])
            markers = task.payload.get("markers", "")
            verbose = task.payload.get("verbose", False)

            args = list(paths)
            args += ["-q"]
            if verbose:
                args += ["-v"]
            if markers:
                args += ["-m", markers]

            # Capture pytest output
            output_buffer = StringIO()

            logger.info("[TEST_WORKER] Running pytest with args: %s", args)

            start = time.perf_counter()

            # Run pytest with a custom plugin to collect counts
            class _ResultCollector:
                def __init__(self):
                    self.passed  = 0
                    self.failed  = 0
                    self.skipped = 0
                    self.errors  = 0
                    self.failures: list[str] = []

                def pytest_runtest_logreport(self, report):
                    if report.when == "call":
                        if report.passed:
                            self.passed += 1
                        elif report.failed:
                            self.failed += 1
                            self.failures.append(report.nodeid)
                        elif report.skipped:
                            self.skipped += 1

                def pytest_internalerror(self, excrepr):
                    self.errors += 1

            collector = _ResultCollector()
            exit_code = pytest.main(args + ["--tb=no", "-p", "no:cacheprovider"],
                                    plugins=[collector])
            duration = time.perf_counter() - start

            total = collector.passed + collector.failed + collector.skipped
            success = collector.failed == 0 and collector.errors == 0

            observations = [
                f"Ran {total} tests in {duration:.1f}s",
                f"Passed: {collector.passed}",
                f"Failed: {collector.failed}",
                f"Skipped: {collector.skipped}",
            ]
            if collector.failures:
                observations.append(
                    f"Failures: {', '.join(collector.failures[:5])}"
                )

            recommendations = []
            if collector.failed > 0:
                recommendations.append(
                    f"Investigate {collector.failed} failing test(s): "
                    + ", ".join(collector.failures[:3])
                )
            if success:
                recommendations.append(
                    "All tests passing — safe to proceed with next sprint."
                )

            logger.info(
                "[TEST_WORKER] Complete: passed=%d failed=%d skipped=%d in %.1fs",
                collector.passed, collector.failed, collector.skipped, duration,
            )

            return self._succeed(WorkerResult(
                task_id=task.task_id,
                worker_name=self.name,
                success=success,
                observations=tuple(observations),
                recommendations=tuple(recommendations),
                requires_approval=False,
                data={
                    "passed":    collector.passed,
                    "failed":    collector.failed,
                    "skipped":   collector.skipped,
                    "errors":    collector.errors,
                    "duration":  round(duration, 2),
                    "exit_code": int(exit_code),
                    "failures":  collector.failures,
                },
            ))

        except Exception as exc:
            logger.exception("[TEST_WORKER] Test run failed.")
            return self._fail(task.task_id, str(exc))