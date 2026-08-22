"""
Jarvis OS Mission Pipeline — Genesis-055 Sprint-001

MissionPipeline is a minimal, capability-restricted processing pipeline
for Mission Mode requests. It is a separate object from ConversationPipeline
with no shared fallback path.

Security guarantee:
    No stage in MissionPipeline routes to ConversationPipeline.
    On any failure, a structured MissionErrorResponse is returned.
    MissionBoundaryViolation is never caught silently.

Stage order:
    1. PolicyCheckStage   — validate request against MissionCapabilityPolicy
    2. ContextBuildStage  — assemble Tier 1 sources into engineering context
    3. IntentStage        — classify intent (interpretation only, cannot grant)
    4. ApprovalGateStage  — block write ops without approval record
    5. DispatchStage      — dispatch to PERMITTED_WORKERS only
    6. ResponseStage      — format engineering response

Policy is the authority. Intent classification is interpretation only.
Policy checks before dispatch — never after.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from core.mission.context import MissionContext, InterfaceMode
from core.mission.policy import (
    MissionCapabilityPolicy,
    MissionBoundaryViolation,
    ALLOWED,
    APPROVAL_REQUIRED,
    DENIED,
)

if TYPE_CHECKING:
    from core.mission.registry import MissionRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MissionRequest — input to MissionPipeline
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionRequest:
    """Immutable input to MissionPipeline."""
    message:    str
    session_id: str
    context:    MissionContext


# ---------------------------------------------------------------------------
# MissionResponse — output from MissionPipeline
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionResponse:
    """
    Structured output from MissionPipeline.

    success=False + boundary_violation=True means a policy boundary
    was crossed. The client receives this response — it never falls
    through to ConversationPipeline.
    """
    success:            bool
    message:            str
    boundary_violation: bool  = False
    approval_required:  bool  = False
    stage_trace:        tuple = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# MissionStageResult — single stage output
# ---------------------------------------------------------------------------

@dataclass
class MissionStageResult:
    stage:      str
    executed:   bool
    outcome:    str
    duration_ms: float = 0.0
    terminal:   bool   = False


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

class PolicyCheckStage:
    """
    Stage 1: Validate the request against MissionCapabilityPolicy.

    This is the authority stage. It runs before intent classification.
    If the request targets a denied capability or denied worker,
    MissionBoundaryViolation is raised immediately.

    Intent classification never runs before this stage completes.
    """
    NAME = "PolicyCheckStage"

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start = time.perf_counter()

        # Check for web access keywords — denied unconditionally
        web_keywords = ("search the web", "browse", "look up online",
                        "internet", "google", "web search")
        msg_lower = request.message.lower()
        if any(kw in msg_lower for kw in web_keywords):
            try:
                MissionCapabilityPolicy.check_web_access(request.session_id)
            except MissionBoundaryViolation:
                raise  # re-raise — never swallow

        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome="policy check passed",
            duration_ms=round(duration, 2),
        )


class ContextBuildStage:
    """
    Stage 2: Assemble Tier 1 sources into engineering context.

    Reads from MissionRegistry (project state) and permitted
    knowledge categories only. Never reads CHAT history.
    """
    NAME = "ContextBuildStage"

    def __init__(self, mission_registry: Optional["MissionRegistry"]) -> None:
        self._registry = mission_registry

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start = time.perf_counter()

        engineering_context = {}
        if self._registry is not None:
            try:
                engineering_context = self._registry.mission_dict()
            except Exception as e:
                logger.warning("[MISSION_PIPELINE] MissionRegistry unavailable: %s", e)
                # Fail closed — return error, not CHAT fallback
                raise RuntimeError(
                    "Mission Mode context unavailable. "
                    "MissionRegistry could not be read."
                ) from e

        state["engineering_context"] = engineering_context
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome=f"context built ({len(engineering_context)} fields)",
            duration_ms=round(duration, 2),
        )


class IntentStage:
    """
    Stage 3: Classify the intent of the request.

    Interpretation only — cannot grant or deny capabilities.
    Policy (Stage 1) has already determined what is permitted.
    This stage labels the request for routing purposes only.

    Intent labels:
        read_project    — query about project state, genesis, objectives
        read_tests      — query about test results
        read_git        — query about commits, branches
        read_knowledge  — query about engineering decisions, ADRs
        run_tests       — request to execute test suite
        write           — request that modifies files/state (approval_required)
        unknown         — cannot classify
    """
    NAME = "IntentStage"

    READ_KEYWORDS = (
        "what is", "what are", "show me", "tell me", "current",
        "status", "progress", "objectives", "mission", "genesis",
        "commit", "branch", "tests", "why did", "how did", "adr",
    )
    RUN_TEST_KEYWORDS = ("run tests", "run the tests", "execute tests")
    WRITE_KEYWORDS    = ("modify", "change", "update", "write", "create file",
                         "delete", "commit", "push")

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start    = time.perf_counter()
        msg      = request.message.lower()

        if any(kw in msg for kw in self.RUN_TEST_KEYWORDS):
            intent = "run_tests"
        elif any(kw in msg for kw in self.WRITE_KEYWORDS):
            intent = "write"
        elif any(kw in msg for kw in self.READ_KEYWORDS):
            intent = "read_project"
        else:
            intent = "unknown"

        state["intent"] = intent
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome=f"intent={intent!r}",
            duration_ms=round(duration, 2),
        )


class ApprovalGateStage:
    """
    Stage 4: Block write operations without an approval record.

    Write intents require an approved session in SessionStore.
    If no approval record exists, returns approval_required=True.
    Never executes write operations autonomously.
    """
    NAME = "ApprovalGateStage"

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start  = time.perf_counter()
        intent = state.get("intent", "unknown")

        if intent == "write":
            # In Sprint-001: no approval records exist for Mission Mode writes yet.
            # Return approval_required — do not execute.
            state["approval_required"] = True
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME,
                executed=True,
                outcome="write intent — approval required",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        state["approval_required"] = False
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome="no approval required",
            duration_ms=round(duration, 2),
        )


class DispatchStage:
    """
    Stage 5: Dispatch to permitted workers or compose response from context.

    In Sprint-001: read requests are answered from engineering_context
    (MissionRegistry data). Worker dispatch is scaffolded but not yet
    wired to live workers — that comes in Sprint-002.

    Policy is already checked. This stage never checks policy itself.
    """
    NAME = "DispatchStage"

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start  = time.perf_counter()
        intent = state.get("intent", "unknown")
        ctx    = state.get("engineering_context", {})

        if state.get("approval_required"):
            state["response_message"] = (
                "This operation requires explicit approval. "
                "Please use the approval workflow."
            )
        elif intent in ("read_project", "read_tests", "read_git",
                        "read_knowledge", "unknown"):
            # Compose response from MissionRegistry context
            genesis   = ctx.get("current_genesis", "—")
            sprint    = ctx.get("current_sprint", "—")
            mission   = ctx.get("current_mission", "—")
            progress  = ctx.get("progress_percent", 0)
            tests     = ctx.get("tests_passed", 0)
            commit    = ctx.get("last_commit", "—")
            branch    = ctx.get("branch", "—")
            milestone = ctx.get("next_milestone", "—")

            state["response_message"] = (
                f"Mission Mode — Engineering Context\n"
                f"Genesis: {genesis} | {sprint}\n"
                f"Mission: {mission}\n"
                f"Progress: {progress}%\n"
                f"Tests: {tests} passed | Commit: {commit} | Branch: {branch}\n"
                f"Next milestone: {milestone}"
            )
        elif intent == "run_tests":
            state["response_message"] = (
                "Test execution noted. "
                "Worker dispatch will be wired in Sprint-002."
            )
        else:
            state["response_message"] = (
                "Mission Mode is active. I can answer questions about the "
                "current project state, genesis, objectives, tests, and "
                "engineering decisions."
            )

        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome=f"intent={intent!r} handled",
            duration_ms=round(duration, 2),
        )


class ResponseStage:
    """
    Stage 6: Format the final MissionResponse.
    """
    NAME = "ResponseStage"

    def run(
        self,
        request: MissionRequest,
        state: dict,
        trace: list,
    ) -> MissionResponse:
        start   = time.perf_counter()
        message = state.get("response_message", "Mission Mode active.")
        approval_required = state.get("approval_required", False)
        duration = (time.perf_counter() - start) * 1000

        trace.append(MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome="response built",
            duration_ms=round(duration, 2),
        ))

        return MissionResponse(
            success=True,
            message=message,
            boundary_violation=False,
            approval_required=approval_required,
            stage_trace=tuple(s.stage for s in trace),
        )


# ---------------------------------------------------------------------------
# MissionPipeline
# ---------------------------------------------------------------------------

class MissionPipeline:
    """
    Minimal capability-restricted pipeline for Mission Mode requests.

    Separate object from ConversationPipeline.
    No shared fallback path. No stage routes to ConversationPipeline.

    On MissionBoundaryViolation: return structured error, log attempt.
    On any other failure: return structured error, never CHAT fallback.
    """

    def __init__(self, mission_registry: Optional["MissionRegistry"] = None) -> None:
        self._policy_check   = PolicyCheckStage()
        self._context_build  = ContextBuildStage(mission_registry)
        self._intent         = IntentStage()
        self._approval_gate  = ApprovalGateStage()
        self._dispatch       = DispatchStage()
        self._response       = ResponseStage()

    def process(self, request: MissionRequest) -> MissionResponse:
        """
        Process a Mission Mode request through all stages.

        Never raises. Never falls through to ConversationPipeline.
        Returns MissionResponse in all cases.
        """
        trace: list[MissionStageResult] = []
        state: dict = {}

        try:
            # Stage 1: Policy check — authority, runs before intent
            result = self._policy_check.run(request, state)
            trace.append(result)

            # Stage 2: Context build
            result = self._context_build.run(request, state)
            trace.append(result)

            # Stage 3: Intent classification — interpretation only
            result = self._intent.run(request, state)
            trace.append(result)

            # Stage 4: Approval gate
            result = self._approval_gate.run(request, state)
            trace.append(result)

            # Stage 5: Dispatch
            result = self._dispatch.run(request, state)
            trace.append(result)

            # Stage 6: Response
            return self._response.run(request, state, trace)

        except MissionBoundaryViolation as violation:
            # Hard boundary crossed — structured error, no CHAT fallback
            logger.warning(
                "[MISSION_PIPELINE] Boundary violation in session=%s: %s",
                request.session_id, violation.detail,
            )
            return MissionResponse(
                success=False,
                message=(
                    "That capability is not available in Mission Mode. "
                    f"({violation.capability})"
                ),
                boundary_violation=True,
                stage_trace=tuple(s.stage for s in trace),
            )

        except Exception as exc:
            # Any other failure — structured error, no CHAT fallback
            logger.exception(
                "[MISSION_PIPELINE] Unexpected error in session=%s",
                request.session_id,
            )
            return MissionResponse(
                success=False,
                message="Mission Mode encountered an error. Please try again.",
                boundary_violation=False,
                stage_trace=tuple(s.stage for s in trace),
            )
