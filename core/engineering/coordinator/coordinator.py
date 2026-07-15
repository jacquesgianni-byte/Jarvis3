"""
Genesis-018 Sprint 001 — Engineering Coordinator
Central orchestrator for the Jarvis engineering pipeline.

Responsibilities:
  - Receive an EngineeringRequest
  - Invoke Planning → Guardrails → Validation → (Debugging if needed)
  - Return one unified EngineeringResult

The coordinator performs NO engineering work itself.
It delegates to existing Genesis subsystems only.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .models import EngineeringRequest, EngineeringResult, EngineeringStatus


# ---------------------------------------------------------------------------
# Internal pipeline step helpers
# ---------------------------------------------------------------------------

class _PipelineStep:
    """
    Lightweight wrapper that binds a named step to a callable.
    Used internally by EngineeringCoordinator to build the pipeline.
    """

    def __init__(self, name: str, fn: Callable[..., Any]) -> None:
        self.name = name
        self.fn   = fn

    def __repr__(self) -> str:
        return f"_PipelineStep(name={self.name!r})"


# ---------------------------------------------------------------------------
# CoordinatorConfig
# ---------------------------------------------------------------------------

class CoordinatorConfig:
    """
    Immutable configuration for the EngineeringCoordinator.

    Allows callers to toggle which pipeline stages are active
    without modifying the coordinator itself.
    """

    def __init__(
        self,
        *,
        enable_planning:   bool = True,
        enable_guardrails: bool = True,
        enable_validation: bool = True,
        enable_debugging:  bool = True,
        enable_repair:     bool = True,
        max_debug_cycles:  int  = 1,
    ) -> None:
        if not isinstance(max_debug_cycles, int) or max_debug_cycles < 0:
            raise ValueError(
                f"max_debug_cycles must be a non-negative int, "
                f"got {max_debug_cycles!r}"
            )
        self.enable_planning   = enable_planning
        self.enable_guardrails = enable_guardrails
        self.enable_validation = enable_validation
        self.enable_debugging  = enable_debugging
        self.enable_repair     = enable_repair
        self.max_debug_cycles  = max_debug_cycles

    def __repr__(self) -> str:
        return (
            f"CoordinatorConfig("
            f"planning={self.enable_planning}, "
            f"guardrails={self.enable_guardrails}, "
            f"validation={self.enable_validation}, "
            f"debugging={self.enable_debugging}, "
            f"repair={self.enable_repair}, "
            f"max_debug_cycles={self.max_debug_cycles}"
            f")"
        )


# ---------------------------------------------------------------------------
# CoordinatorEvent
# ---------------------------------------------------------------------------

class CoordinatorEvent:
    """
    Represents a single event emitted during coordinator execution.
    Observers can subscribe to receive these for logging or monitoring.
    """

    def __init__(self, stage: str, status: EngineeringStatus, detail: str = "") -> None:
        self.stage  = stage
        self.status = status
        self.detail = detail

    def __repr__(self) -> str:
        return (
            f"CoordinatorEvent("
            f"stage={self.stage!r}, "
            f"status={self.status.value}, "
            f"detail={self.detail!r}"
            f")"
        )


# ---------------------------------------------------------------------------
# EngineeringCoordinator
# ---------------------------------------------------------------------------

class EngineeringCoordinator:
    """
    Central orchestrator for the Jarvis engineering pipeline.

    Connects existing Genesis engineering subsystems in the correct order:
      Request → Planning → Guardrails → Validation → (Debugging) → Result

    Design constraints (Genesis-018 Sprint 001):
      - Must NOT perform engineering work itself.
      - Must NOT invoke AI providers.
      - Must NOT modify repositories.
      - Must NOT execute repairs.
      - Must NOT perform autonomous engineering decisions.
      - Delegates all work to injected subsystem adapters.
    """

    VERSION = "018.001"

    def __init__(
        self,
        *,
        planner:   Optional[Any] = None,
        guardrails: Optional[Any] = None,
        test_runner: Optional[Any] = None,
        debugger:   Optional[Any] = None,
        config:     Optional[CoordinatorConfig] = None,
    ) -> None:
        """
        Initialise the coordinator with optional subsystem adapters.

        All adapters are optional at construction time to support
        incremental integration and testing with stubs.

        Args:
            planner:     Engineering Planner adapter (Genesis-016).
            guardrails:  Engineering Guardrails adapter (Genesis-016).
            test_runner: Engineering Test Runner adapter (Genesis-016).
            debugger:    Engineering Debugger adapter (Genesis-017).
            config:      Optional coordinator configuration.
        """
        self._planner     = planner
        self._guardrails  = guardrails
        self._test_runner = test_runner
        self._debugger    = debugger
        self._config      = config or CoordinatorConfig()
        self._observers:  List[Callable[[CoordinatorEvent], None]] = []

    # ------------------------------------------------------------------
    # Observer / event system
    # ------------------------------------------------------------------

    def add_observer(self, fn: Callable[[CoordinatorEvent], None]) -> None:
        """Register a callable that receives CoordinatorEvents during execution."""
        if not callable(fn):
            raise TypeError(f"Observer must be callable, got {type(fn).__name__}")
        if fn not in self._observers:
            self._observers.append(fn)

    def remove_observer(self, fn: Callable[[CoordinatorEvent], None]) -> None:
        """Remove a previously registered observer."""
        self._observers = [o for o in self._observers if o is not fn]

    @property
    def observer_count(self) -> int:
        return len(self._observers)

    def _emit(self, stage: str, status: EngineeringStatus, detail: str = "") -> None:
        """Emit an event to all registered observers."""
        event = CoordinatorEvent(stage=stage, status=status, detail=detail)
        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                # Observers must never crash the pipeline.
                pass

    # ------------------------------------------------------------------
    # Subsystem accessors
    # ------------------------------------------------------------------

    @property
    def has_planner(self) -> bool:
        return self._planner is not None

    @property
    def has_guardrails(self) -> bool:
        return self._guardrails is not None

    @property
    def has_test_runner(self) -> bool:
        return self._test_runner is not None

    @property
    def has_debugger(self) -> bool:
        return self._debugger is not None

    @property
    def config(self) -> CoordinatorConfig:
        return self._config

    def describe(self) -> Dict[str, Any]:
        """Return a summary of the coordinator's current configuration."""
        return {
            "version":        self.VERSION,
            "has_planner":    self.has_planner,
            "has_guardrails": self.has_guardrails,
            "has_test_runner": self.has_test_runner,
            "has_debugger":   self.has_debugger,
            "config":         repr(self._config),
            "observer_count": self.observer_count,
        }

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    def coordinate(self, request: EngineeringRequest) -> EngineeringResult:
        """
        Execute the full engineering pipeline for the given request.

        Pipeline:
            PENDING → PLANNING → VALIDATING → (DEBUGGING) → COMPLETE | FAILED

        Args:
            request: An immutable EngineeringRequest to process.

        Returns:
            An immutable EngineeringResult with the unified outcome.
        """
        if not isinstance(request, EngineeringRequest):
            raise TypeError(
                f"coordinate() expects EngineeringRequest, "
                f"got {type(request).__name__}"
            )

        start_ms = int(time.monotonic() * 1000)

        # Accumulated state across pipeline stages
        plan:         Optional[str] = None
        validation:   Optional[str] = None
        debug_report: Optional[str] = None
        repair_plan:  Optional[str] = None
        errors:       List[str]     = []
        warnings:     List[str]     = []

        self._emit("coordinator", EngineeringStatus.PENDING, "Pipeline started")

        # ── Stage 1: Planning ──────────────────────────────────────────
        if self._config.enable_planning:
            self._emit("planning", EngineeringStatus.PLANNING, "Invoking planner")
            plan, planning_warnings, planning_errors = self._run_planning(request)
            warnings.extend(planning_warnings)
            errors.extend(planning_errors)

            if planning_errors:
                return self._fail(
                    status=EngineeringStatus.FAILED,
                    plan=plan,
                    errors=errors,
                    warnings=warnings,
                    start_ms=start_ms,
                    reason="Planning stage failed",
                )
        else:
            warnings.append("Planning stage disabled by config")

        # ── Stage 2: Guardrails ────────────────────────────────────────
        if self._config.enable_guardrails:
            self._emit("guardrails", EngineeringStatus.VALIDATING, "Checking guardrails")
            guardrail_pass, guardrail_warnings, guardrail_errors = self._run_guardrails(
                request, plan
            )
            warnings.extend(guardrail_warnings)
            errors.extend(guardrail_errors)

            if not guardrail_pass:
                return self._fail(
                    status=EngineeringStatus.FAILED,
                    plan=plan,
                    errors=errors,
                    warnings=warnings,
                    start_ms=start_ms,
                    reason="Guardrails blocked the request",
                )
        else:
            warnings.append("Guardrails stage disabled by config")

        # ── Stage 3: Validation (Testing) ─────────────────────────────
        validation_pass = True
        if self._config.enable_validation:
            self._emit("validation", EngineeringStatus.VALIDATING, "Running validation")
            validation_pass, validation, val_warnings, val_errors = self._run_validation(
                request, plan
            )
            warnings.extend(val_warnings)
            errors.extend(val_errors)
        else:
            warnings.append("Validation stage disabled by config")
            validation = "Validation skipped by config"

        # ── Stage 4: Debugging (if validation failed) ──────────────────
        if not validation_pass:
            if self._config.enable_debugging and self.has_debugger:
                self._emit(
                    "debugging", EngineeringStatus.DEBUGGING,
                    "Validation failed — invoking debugger"
                )
                debug_report, repair_plan, debug_warnings, debug_errors = (
                    self._run_debugging(request, validation)
                )
                warnings.extend(debug_warnings)
                errors.extend(debug_errors)
            else:
                errors.append(
                    "Validation failed and no debugger is available "
                    "or debugging is disabled by config"
                )

            # After debugging the status is still FAILED unless the
            # repair plan is populated. The coordinator does NOT
            # execute repairs — it only produces the plan.
            end_ms = int(time.monotonic() * 1000)
            self._emit(
                "coordinator", EngineeringStatus.FAILED,
                "Pipeline complete — validation failure, repair plan produced"
            )
            return EngineeringResult(
                status=EngineeringStatus.FAILED,
                plan=plan,
                validation=validation,
                debug_report=debug_report,
                repair_plan=repair_plan,
                completed=False,
                duration_ms=end_ms - start_ms,
                errors=errors,
                warnings=warnings,
            )

        # ── Stage 5: Complete ──────────────────────────────────────────
        end_ms = int(time.monotonic() * 1000)
        self._emit(
            "coordinator", EngineeringStatus.COMPLETE,
            "Pipeline complete — all stages passed"
        )
        return EngineeringResult(
            status=EngineeringStatus.COMPLETE,
            plan=plan,
            validation=validation,
            debug_report=None,
            repair_plan=None,
            completed=True,
            duration_ms=end_ms - start_ms,
            errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Private stage runners
    # ------------------------------------------------------------------

    def _run_planning(
        self, request: EngineeringRequest
    ) -> tuple[Optional[str], List[str], List[str]]:
        """Delegate to the planner subsystem. Returns (plan, warnings, errors)."""
        warnings: List[str] = []
        errors:   List[str] = []

        if not self.has_planner:
            warnings.append("No planner registered — planning stage skipped")
            return None, warnings, errors

        try:
            result = self._planner.plan(request.request, context=request.context)
            plan   = str(result) if result is not None else None
            return plan, warnings, errors
        except Exception as exc:
            errors.append(f"Planner raised an exception: {exc}")
            return None, warnings, errors

    def _run_guardrails(
        self, request: EngineeringRequest, plan: Optional[str]
    ) -> tuple[bool, List[str], List[str]]:
        """Delegate to the guardrails subsystem. Returns (passed, warnings, errors)."""
        warnings: List[str] = []
        errors:   List[str] = []

        if not self.has_guardrails:
            warnings.append("No guardrails registered — guardrails stage skipped")
            return True, warnings, errors

        try:
            passed = self._guardrails.check(request.request, plan=plan)
            if not passed:
                errors.append("Guardrails check did not pass")
            return bool(passed), warnings, errors
        except Exception as exc:
            errors.append(f"Guardrails raised an exception: {exc}")
            return False, warnings, errors

    def _run_validation(
        self, request: EngineeringRequest, plan: Optional[str]
    ) -> tuple[bool, Optional[str], List[str], List[str]]:
        """Delegate to the test runner. Returns (passed, validation_output, warnings, errors)."""
        warnings:   List[str] = []
        errors:     List[str] = []
        validation: Optional[str] = None

        if not self.has_test_runner:
            warnings.append("No test runner registered — validation stage skipped")
            return True, "No test runner — validation skipped", warnings, errors

        try:
            result     = self._test_runner.run(request.request, plan=plan)
            passed     = bool(getattr(result, "passed", True))
            validation = str(result) if result is not None else None
            return passed, validation, warnings, errors
        except Exception as exc:
            errors.append(f"Test runner raised an exception: {exc}")
            return False, None, warnings, errors

    def _run_debugging(
        self, request: EngineeringRequest, validation: Optional[str]
    ) -> tuple[Optional[str], Optional[str], List[str], List[str]]:
        """Delegate to the debugger subsystem. Returns (debug_report, repair_plan, warnings, errors)."""
        warnings:     List[str] = []
        errors:       List[str] = []
        debug_report: Optional[str] = None
        repair_plan:  Optional[str] = None

        if not self.has_debugger:
            warnings.append("No debugger registered — debugging stage skipped")
            return None, None, warnings, errors

        try:
            result       = self._debugger.debug(
                request.request, failure_context=validation
            )
            debug_report = str(getattr(result, "report", result)) if result is not None else None
            repair_plan  = str(getattr(result, "repair_plan", None)) if result is not None else None
            return debug_report, repair_plan, warnings, errors
        except Exception as exc:
            errors.append(f"Debugger raised an exception: {exc}")
            return None, None, warnings, errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fail(
        self,
        *,
        status:   EngineeringStatus,
        plan:     Optional[str],
        errors:   List[str],
        warnings: List[str],
        start_ms: int,
        reason:   str,
    ) -> EngineeringResult:
        """Construct a failed EngineeringResult."""
        end_ms = int(time.monotonic() * 1000)
        errors.append(reason)
        self._emit("coordinator", EngineeringStatus.FAILED, reason)
        return EngineeringResult(
            status=status,
            plan=plan,
            validation=None,
            debug_report=None,
            repair_plan=None,
            completed=False,
            duration_ms=end_ms - start_ms,
            errors=errors,
            warnings=warnings,
        )

    def __repr__(self) -> str:
        return (
            f"EngineeringCoordinator("
            f"version={self.VERSION!r}, "
            f"subsystems={{"
            f"planner={self.has_planner}, "
            f"guardrails={self.has_guardrails}, "
            f"test_runner={self.has_test_runner}, "
            f"debugger={self.has_debugger}"
            f"}})"
        )