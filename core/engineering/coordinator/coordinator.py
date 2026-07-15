"""
Genesis-018 Sprint 002 — Engineering Coordinator
Central orchestrator with full session and workflow management.

Sprint 001: coordinate(), observer system, subsystem delegation
Sprint 002: EngineeringSession creation, EngineeringStage tracking,
            CoordinatorEventLog recording, stage duration measurement,
            complete execution timeline on EngineeringResult
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from .models import (
    CoordinatorEventLog,
    EngineeringRequest,
    EngineeringResult,
    EngineeringSession,
    EngineeringStage,
    EngineeringStatus,
    SessionEvent,
)


# ---------------------------------------------------------------------------
# CoordinatorConfig  (Sprint 001 — unchanged)
# ---------------------------------------------------------------------------

class CoordinatorConfig:
    """Immutable configuration for the EngineeringCoordinator."""

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
# CoordinatorEvent  (Sprint 001 — unchanged, distinct from SessionEvent)
# ---------------------------------------------------------------------------

class CoordinatorEvent:
    """
    External observer event emitted during coordinator execution.
    Distinct from SessionEvent (which is the internal session log entry).
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

    Sprint 001: delegates to subsystems, emits observer events,
                returns EngineeringResult.

    Sprint 002: creates an EngineeringSession per request, advances
                EngineeringStage at every pipeline transition, records
                all events in a CoordinatorEventLog, measures stage
                durations, and attaches the complete session + timeline
                to EngineeringResult.

    Design constraints (unchanged):
        - Must NOT perform engineering work.
        - Must NOT invoke AI providers.
        - Must NOT modify repositories.
        - Must NOT execute repairs.
        - Delegates all work to injected subsystem adapters.
    """

    VERSION = "018.002"

    def __init__(
        self,
        *,
        planner:     Optional[Any] = None,
        guardrails:  Optional[Any] = None,
        test_runner: Optional[Any] = None,
        debugger:    Optional[Any] = None,
        config:      Optional[CoordinatorConfig] = None,
    ) -> None:
        self._planner     = planner
        self._guardrails  = guardrails
        self._test_runner = test_runner
        self._debugger    = debugger
        self._config      = config or CoordinatorConfig()
        self._observers:  List[Callable[[CoordinatorEvent], None]] = []

    # ------------------------------------------------------------------
    # Observer / event system  (Sprint 001 — unchanged)
    # ------------------------------------------------------------------

    def add_observer(self, fn: Callable[[CoordinatorEvent], None]) -> None:
        if not callable(fn):
            raise TypeError(f"Observer must be callable, got {type(fn).__name__}")
        if fn not in self._observers:
            self._observers.append(fn)

    def remove_observer(self, fn: Callable[[CoordinatorEvent], None]) -> None:
        self._observers = [o for o in self._observers if o is not fn]

    @property
    def observer_count(self) -> int:
        return len(self._observers)

    def _emit(self, stage: str, status: EngineeringStatus, detail: str = "") -> None:
        event = CoordinatorEvent(stage=stage, status=status, detail=detail)
        for observer in self._observers:
            try:
                observer(event)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Subsystem accessors  (Sprint 001 — unchanged)
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
        return {
            "version":         self.VERSION,
            "has_planner":     self.has_planner,
            "has_guardrails":  self.has_guardrails,
            "has_test_runner": self.has_test_runner,
            "has_debugger":    self.has_debugger,
            "config":          repr(self._config),
            "observer_count":  self.observer_count,
        }

    # ------------------------------------------------------------------
    # Core pipeline  (Sprint 002 — session-aware)
    # ------------------------------------------------------------------

    def coordinate(self, request: EngineeringRequest) -> EngineeringResult:
        """
        Execute the full engineering pipeline for the given request.

        Sprint 002 enhancements:
          - Creates an EngineeringSession at the start.
          - Advances EngineeringStage at every pipeline transition.
          - Records every event with timestamps in CoordinatorEventLog.
          - Measures per-stage wall-clock durations.
          - Attaches complete session + timeline to EngineeringResult.
        """
        if not isinstance(request, EngineeringRequest):
            raise TypeError(
                f"coordinate() expects EngineeringRequest, "
                f"got {type(request).__name__}"
            )

        # ── Create session ─────────────────────────────────────────────
        session = EngineeringSession.create(request)
        session.advance_to(
            EngineeringStage.INITIALISING,
            "Session created — pipeline starting",
        )

        start_ms = session.started_at

        # Accumulated state
        plan:         Optional[str] = None
        validation:   Optional[str] = None
        debug_report: Optional[str] = None
        repair_plan:  Optional[str] = None
        errors:       List[str]     = []
        warnings:     List[str]     = []

        self._emit("coordinator", EngineeringStatus.PENDING, "Pipeline started")

        # ── Stage 1: Planning ──────────────────────────────────────────
        if self._config.enable_planning:
            stage_start = int(time.monotonic() * 1000)
            session.advance_to(EngineeringStage.PLANNING, "Planning stage started")
            self._emit("planning", EngineeringStatus.PLANNING, "Invoking planner")

            plan, planning_warnings, planning_errors = self._run_planning(request)
            warnings.extend(planning_warnings)
            errors.extend(planning_errors)

            stage_dur = int(time.monotonic() * 1000) - stage_start
            if planning_errors:
                session.advance_to(
                    EngineeringStage.FAILED,
                    "Planning stage failed",
                    duration_ms=stage_dur,
                )
                return self._finalise(
                    session=session,
                    status=EngineeringStatus.FAILED,
                    plan=plan,
                    errors=errors,
                    warnings=warnings,
                    start_ms=start_ms,
                    reason="Planning stage failed",
                )
            session.advance_to(
                EngineeringStage.PLANNING,
                "Planning stage completed",
                duration_ms=stage_dur,
            )
        else:
            warnings.append("Planning stage disabled by config")

        # ── Stage 2: Guardrails ────────────────────────────────────────
        if self._config.enable_guardrails:
            stage_start = int(time.monotonic() * 1000)
            session.advance_to(EngineeringStage.GUARDRAILS, "Guardrails stage started")
            self._emit("guardrails", EngineeringStatus.VALIDATING, "Checking guardrails")

            guardrail_pass, guardrail_warnings, guardrail_errors = self._run_guardrails(
                request, plan
            )
            warnings.extend(guardrail_warnings)
            errors.extend(guardrail_errors)

            stage_dur = int(time.monotonic() * 1000) - stage_start
            if not guardrail_pass:
                session.advance_to(
                    EngineeringStage.FAILED,
                    "Guardrails blocked the request",
                    duration_ms=stage_dur,
                )
                return self._finalise(
                    session=session,
                    status=EngineeringStatus.FAILED,
                    plan=plan,
                    errors=errors,
                    warnings=warnings,
                    start_ms=start_ms,
                    reason="Guardrails blocked the request",
                )
            session.advance_to(
                EngineeringStage.GUARDRAILS,
                "Guardrails passed",
                duration_ms=stage_dur,
            )
        else:
            warnings.append("Guardrails stage disabled by config")

        # ── Stage 3: Validation ────────────────────────────────────────
        validation_pass = True
        if self._config.enable_validation:
            stage_start = int(time.monotonic() * 1000)
            session.advance_to(EngineeringStage.VALIDATION, "Validation stage started")
            self._emit("validation", EngineeringStatus.VALIDATING, "Running validation")

            validation_pass, validation, val_warnings, val_errors = self._run_validation(
                request, plan
            )
            warnings.extend(val_warnings)
            errors.extend(val_errors)

            stage_dur = int(time.monotonic() * 1000) - stage_start
            outcome = "Validation passed" if validation_pass else "Validation failed"
            session.advance_to(
                EngineeringStage.VALIDATION,
                outcome,
                duration_ms=stage_dur,
            )
        else:
            warnings.append("Validation stage disabled by config")
            validation = "Validation skipped by config"

        # ── Stage 4: Debugging (if validation failed) ──────────────────
        if not validation_pass:
            if self._config.enable_debugging and self.has_debugger:
                stage_start = int(time.monotonic() * 1000)
                session.advance_to(
                    EngineeringStage.DEBUGGING,
                    "Validation failed — invoking debugger",
                )
                self._emit(
                    "debugging", EngineeringStatus.DEBUGGING,
                    "Validation failed — invoking debugger"
                )
                debug_report, repair_plan, debug_warnings, debug_errors = (
                    self._run_debugging(request, validation)
                )
                warnings.extend(debug_warnings)
                errors.extend(debug_errors)

                stage_dur = int(time.monotonic() * 1000) - stage_start
                session.advance_to(
                    EngineeringStage.DEBUGGING,
                    "Debugging complete",
                    duration_ms=stage_dur,
                )

                # Repair planning stage
                if repair_plan is not None:
                    session.advance_to(
                        EngineeringStage.REPAIR_PLANNING,
                        "Repair plan produced",
                        detail=repair_plan[:80] if len(repair_plan) > 80 else repair_plan,
                    )
            else:
                errors.append(
                    "Validation failed and no debugger is available "
                    "or debugging is disabled by config"
                )

            session.advance_to(
                EngineeringStage.FAILED,
                "Pipeline failed — validation could not be resolved",
            )
            return self._finalise(
                session=session,
                status=EngineeringStatus.FAILED,
                plan=plan,
                validation=validation,
                debug_report=debug_report,
                repair_plan=repair_plan,
                errors=errors,
                warnings=warnings,
                start_ms=start_ms,
                completed=False,
            )

        # ── Stage 5: Complete ──────────────────────────────────────────
        session.advance_to(EngineeringStage.COMPLETE, "Pipeline complete — all stages passed")
        self._emit(
            "coordinator", EngineeringStatus.COMPLETE,
            "Pipeline complete — all stages passed"
        )
        return self._finalise(
            session=session,
            status=EngineeringStatus.COMPLETE,
            plan=plan,
            validation=validation,
            errors=errors,
            warnings=warnings,
            start_ms=start_ms,
            completed=True,
        )

    # ------------------------------------------------------------------
    # Private stage runners  (Sprint 001 — unchanged)
    # ------------------------------------------------------------------

    def _run_planning(
        self, request: EngineeringRequest
    ) -> tuple[Optional[str], List[str], List[str]]:
        warnings: List[str] = []
        errors:   List[str] = []
        if not self.has_planner:
            warnings.append("No planner registered — planning stage skipped")
            return None, warnings, errors
        try:
            result = self._planner.plan(request.request, context=request.context)
            return str(result) if result is not None else None, warnings, errors
        except Exception as exc:
            errors.append(f"Planner raised an exception: {exc}")
            return None, warnings, errors

    def _run_guardrails(
        self, request: EngineeringRequest, plan: Optional[str]
    ) -> tuple[bool, List[str], List[str]]:
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
    # Finalise helper  (Sprint 002 — replaces _fail, handles session)
    # ------------------------------------------------------------------

    def _finalise(
        self,
        *,
        session:      EngineeringSession,
        status:       EngineeringStatus,
        start_ms:     int,
        errors:       List[str],
        warnings:     List[str],
        plan:         Optional[str] = None,
        validation:   Optional[str] = None,
        debug_report: Optional[str] = None,
        repair_plan:  Optional[str] = None,
        completed:    bool          = False,
        reason:       Optional[str] = None,
    ) -> EngineeringResult:
        """Build the final EngineeringResult, close the session, return."""
        if reason:
            errors.append(reason)
            self._emit("coordinator", EngineeringStatus.FAILED, reason)

        end_ms      = int(time.monotonic() * 1000)
        duration_ms = end_ms - start_ms

        result = EngineeringResult(
            status=status,
            plan=plan,
            validation=validation,
            debug_report=debug_report,
            repair_plan=repair_plan,
            completed=completed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            # Sprint 002 fields
            session=session,
            timeline=session.events.timeline(),
            stage_durations=session.stage_durations(),
        )

        session.complete(result)
        return result

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

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