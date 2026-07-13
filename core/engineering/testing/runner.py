"""
Engineering Test Runner (Genesis-016 Sprint 005)

Translates abstract validation recommendations from an EngineeringPlan
into executable actions via a ValidationRegistry, then executes them.

Constitutional constraints — this module MUST NEVER:
    * Modify any source file.
    * Execute any Git write command.
    * Generate or apply code patches.
    * Make decisions about plan safety (Guardrails' job).
    * Generate plans (Planner's job).

Architecture:
    ValidationRegistry  — owns the mapping from abstract name to command.
    EngineeringTestRunner — consumes the registry; executes; returns result.

Adding a new validation type = one line in the registry.
The runner never needs to change.

Pipeline position:
    EngineeringPlan -> EngineeringGuardrails -> Chief Approval
    -> EngineeringTestRunner -> EngineeringTestResult
"""

import logging
import subprocess
from subprocess import PIPE
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.engineering.testing.models import (
    EngineeringTestResult,
    StepResult,
    ValidationStatus,
)
from core.engineering.planning.models import EngineeringPlan

logger = logging.getLogger(__name__)

# Per-step timeout in seconds
_STEP_TIMEOUT = 120

# Steps where None command = gracefully skipped (manual or hardware steps)
_SKIP_REASON = "Manual or hardware-dependent — skipped in automated validation."


class ValidationRegistry:
    """
    Maps abstract validation recommendation names to executable commands.

    The runner consumes this registry. Adding a new validation type
    requires only a one-line update here — the runner is unaffected.

    Commands are lists of tokens (subprocess-safe, no shell injection).
    None = manual/hardware step, skipped gracefully.
    """

    def __init__(self):
        py = sys.executable
        self._registry: dict[str, list[str] | None] = {
            "compile check":                [py, "-m", "compileall", "core/"],
            "regression tests":             [py, "-m", "pytest", "tests/", "-q"],
            "reasoning engine tests":       [py, "tests/test_reasoning_engine.py"],
            "reasoning integration tests":  [py, "tests/test_reasoning_integration.py"],
            "knowledge engine tests":       [py, "tests/test_knowledge_engine.py"],
            "knowledge data integrity check": [py, "-m", "pytest",
                                               "tests/test_knowledge_engine.py", "-q"],
            "ai provider tests":            [py, "tests/test_anthropic_provider.py"],
            "multi-provider validation":    [py, "-m", "pytest",
                                             "tests/test_anthropic_provider.py", "-q"],
            "skills integration tests":     [py, "-m", "pytest", "tests/", "-k", "skill", "-q"],
            "settings load test":           [py, "-m", "pytest",
                                             "tests/test_edge_cases.py", "-q"],
            "engineering repository tests": [py, "tests/test_engineering_repository.py"],
            "git awareness tests":          [py, "tests/test_engineering_git.py"],
            "guardrails tests":             [py, "tests/test_engineering_guardrails.py"],
            # Manual / hardware steps — skipped in automated runs
            "desktop ui smoke test":        None,
            "visual inspection":            None,
            "audio output test":            None,
            "voice provider tests":         None,
        }

    def command_for(self, recommendation: str) -> list[str] | None:
        """
        Return the command tokens for a recommendation.

        Returns:
            list[str]  — command to execute via subprocess.
            None       — manual/hardware step, skip gracefully.
            KeyError   — recommendation not registered (caller handles).
        """
        return self._registry[recommendation.lower()]

    def is_registered(self, recommendation: str) -> bool:
        return recommendation.lower() in self._registry

    def is_manual(self, recommendation: str) -> bool:
        return self._registry.get(recommendation.lower()) is None

    def all_recommendations(self) -> list[str]:
        """Return all registered recommendation names."""
        return list(self._registry.keys())

    def register(self, name: str, command: list[str] | None) -> None:
        """
        Register a new validation recommendation.

        Args:
            name:    Abstract recommendation name (case-insensitive).
            command: Command tokens, or None for manual steps.
        """
        self._registry[name.lower()] = command
        logger.info("ValidationRegistry: registered %r", name)


# Module-level default registry — shared unless overridden in tests
_DEFAULT_REGISTRY = ValidationRegistry()


class EngineeringTestRunner:
    """
    Executes validation steps derived from an EngineeringPlan.

    Consumes a ValidationRegistry to resolve abstract recommendation
    names to executable commands. The runner itself contains no
    hard-coded command strings.

    Read-only with respect to source files.
    """

    def __init__(
        self,
        project_root: str | Path | None = None,
        registry: ValidationRegistry | None = None,
    ):
        if project_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.project_root = Path(project_root).resolve()
        self.registry = registry or _DEFAULT_REGISTRY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, plan: EngineeringPlan) -> EngineeringTestResult:
        """
        Translate the plan's validation recommendations into commands
        and execute them via the registry.

        Returns:
            Immutable EngineeringTestResult with start/finish timestamps
            and elapsed duration. Never raises.
        """
        started_wall = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        step_results: list[StepResult] = []

        logger.info(
            "EngineeringTestRunner: starting validation | steps=%d | "
            "objective=%s",
            len(plan.validation_steps),
            plan.objective[:60],
        )

        for recommendation in plan.validation_steps:
            result = self._execute_step(recommendation)
            step_results.append(result)
            logger.info(
                "EngineeringTestRunner: step %r -> %s (%.0f ms)",
                recommendation,
                "PASS" if result.passed else "FAIL",
                result.duration_ms,
            )

        finished_wall = datetime.now(timezone.utc)
        total_ms = (time.perf_counter() - started_perf) * 1000.0
        status = self._overall_status(step_results)

        result = EngineeringTestResult(
            plan_objective=plan.objective,
            steps=tuple(step_results),
            status=status,
            total_duration_ms=total_ms,
            started_at=started_wall.isoformat(),
            finished_at=finished_wall.isoformat(),
        )

        logger.info(
            "EngineeringTestRunner: complete | status=%s | "
            "passed=%d/%d | total_ms=%.0f",
            status.value,
            result.steps_passed,
            result.steps_total,
            total_ms,
        )
        return result

    def supported_recommendations(self) -> list[str]:
        """Return all recommendation names known to the registry."""
        return self.registry.all_recommendations()

    def command_for(self, recommendation: str) -> list[str] | None:
        """Return the command tokens for a recommendation, or None."""
        if not self.registry.is_registered(recommendation):
            return None
        return self.registry.command_for(recommendation)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _execute_step(self, recommendation: str) -> StepResult:
        """Execute one validation step via the registry."""
        step_started = time.perf_counter()

        # Unknown recommendation — warn and skip non-blocking
        if not self.registry.is_registered(recommendation):
            logger.warning(
                "EngineeringTestRunner: no mapping for %r — skipping",
                recommendation,
            )
            return StepResult(
                name=recommendation,
                command="(unmapped)",
                passed=True,
                duration_ms=(time.perf_counter() - step_started) * 1000.0,
                output="",
                error=f"No registry entry for {recommendation!r}.",
            )

        # Manual/hardware step — skip gracefully
        if self.registry.is_manual(recommendation):
            return StepResult(
                name=recommendation,
                command="(skipped)",
                passed=True,
                duration_ms=(time.perf_counter() - step_started) * 1000.0,
                output=_SKIP_REASON,
            )

        # Execute via registry command
        command = self.registry.command_for(recommendation)
        cmd_str = " ".join(command)
        try:
            # Use Popen + communicate() to avoid the capture_output
            # buffering deadlock on Python 3.14 / Windows.
            with subprocess.Popen(
                command,
                cwd=self.project_root,
                stdout=PIPE,
                stderr=PIPE,
                text=True,
            ) as proc:
                try:
                    raw_out, raw_err = proc.communicate(timeout=_STEP_TIMEOUT)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    raw_out, raw_err = proc.communicate()
                    return StepResult(
                        name=recommendation,
                        command=cmd_str,
                        passed=False,
                        duration_ms=(time.perf_counter() - step_started) * 1000.0,
                        output="",
                        error=f"Step timed out after {_STEP_TIMEOUT}s.",
                    )
                returncode = proc.returncode
            duration_ms = (time.perf_counter() - step_started) * 1000.0
            stdout = raw_out.strip()
            stderr = raw_err.strip()
            combined = "\n".join(filter(None, [stdout, stderr]))
            output = combined or f"(no output captured — exit code {returncode})"
            return StepResult(
                name=recommendation,
                command=cmd_str,
                passed=returncode == 0,
                duration_ms=duration_ms,
                output=output[:2000],
            )

        except subprocess.TimeoutExpired:  # safety net — already handled in Popen block
            return StepResult(
                name=recommendation,
                command=cmd_str,
                passed=False,
                duration_ms=(time.perf_counter() - step_started) * 1000.0,
                output="",
                error=f"Step timed out after {_STEP_TIMEOUT}s.",
            )
        except Exception as exc:
            return StepResult(
                name=recommendation,
                command=cmd_str,
                passed=False,
                duration_ms=(time.perf_counter() - step_started) * 1000.0,
                output="",
                error=str(exc),
            )

    @staticmethod
    def _overall_status(steps: list[StepResult]) -> ValidationStatus:
        if not steps:
            return ValidationStatus.SKIPPED
        total = len(steps)
        passed = sum(1 for s in steps if s.passed)
        if passed == total:
            return ValidationStatus.PASSED
        if passed == 0:
            return ValidationStatus.FAILED
        return ValidationStatus.PARTIAL