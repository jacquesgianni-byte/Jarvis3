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
from core.mission.investigation import ReadOnlyInvestigator
from core.mission.authorised_sources import AuthorisedSourceRegistry
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

    Genesis-055 Sprint-002A: adds deterministic/historical classification.

    Knowledge tiers (GPT-approved architecture):
        FACT        — answerable directly from MissionRegistry current state
        HISTORICAL  — requires project documents not yet in knowledge base
        UNKNOWN     — cannot classify; honest "I don't know" response

    Intent labels:
        read_current    — FACT: current genesis, sprint, mission, tests, commit
        read_objectives — FACT: objectives, progress, next milestone
        run_tests       — FACT: test execution request
        write           — requires approval
        historical      — HISTORICAL: past genesis delivery, rationale, ADRs
        unknown         — UNKNOWN: cannot classify
    """
    NAME = "IntentStage"

    @staticmethod
    def _matches_any(msg: str, keywords: tuple) -> bool:
        """Whole-word match ? prevents changes matching change."""
        import re as _re
        for kw in keywords:
            pattern = r'\b' + _re.escape(kw) + r'\b'
            if _re.search(pattern, msg):
                return True
        return False

    # FACT — answerable from MissionRegistry current state
    CURRENT_STATE_KEYWORDS = (
        "current genesis", "what genesis", "which genesis",
        "current sprint", "what sprint",
        "current mission", "what mission",
        "tests passing", "tests passed", "test results", "how many tests",
        "last commit", "current commit", "which commit",
        "current branch", "which branch",
        "what branch",
    )
    OBJECTIVES_KEYWORDS = (
        "objectives", "progress", "next milestone", "milestone",
        "what are we working on", "open tasks", "what is left",
        "what is done", "what have we completed",
    )
    RUN_TEST_KEYWORDS = (
        "run tests", "run the tests", "execute tests", "run pytest",
    )
    WRITE_KEYWORDS = (
        "modify", "change", "update", "write", "create file",
        "delete", "commit", "push",
    )
    INVESTIGATE_KEYWORDS = (
        "investigate", "why is", "why are", "diagnose", "root cause",
        "wrong genesis", "wrong sprint", "stale", "showing wrong",
        "showing the wrong", "why does mission", "find the problem",
        "consistent", "consistency", "is everything", "check everything",
        "anything wrong", "any issues", "any problems", "any inconsistencies",
    )

    # HISTORICAL — requires project documents not yet in knowledge base
    HISTORICAL_KEYWORDS = (
        "why did", "why was", "why were", "why have",
        "how did", "how was",
        "what did genesis", "what did g-", "what was genesis",
        "delivered", "deliver", "introduced", "added in",
        "history", "previous genesis", "past genesis",
        "adr", "architectural decision", "design decision",
        "rationale", "reason we", "reason for",
        "when did we", "when was",
    )

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start = time.perf_counter()
        msg   = request.message.lower()

        # Priority order: write > investigate > run_tests > historical > current > objectives > unknown
        # Whole-word matching prevents 'changes' matching 'change', etc. Genesis-056 Sprint-004 fix.
        if self._matches_any(msg, self.WRITE_KEYWORDS):
            intent    = "write"
            knowledge = "approval_required"
        elif self._matches_any(msg, self.INVESTIGATE_KEYWORDS):
            intent    = "investigate"
            knowledge = "fact"
        elif self._matches_any(msg, self.RUN_TEST_KEYWORDS):
            intent    = "run_tests"
            knowledge = "fact"
        elif self._matches_any(msg, self.HISTORICAL_KEYWORDS):
            intent    = "historical"
            knowledge = "historical"
        elif self._matches_any(msg, self.CURRENT_STATE_KEYWORDS):
            intent    = "read_current"
            knowledge = "fact"
        elif self._matches_any(msg, self.OBJECTIVES_KEYWORDS):
            intent    = "read_objectives"
            knowledge = "fact"
        else:
            intent    = "unknown"
            knowledge = "unknown"

        state["intent"]    = intent
        state["knowledge"] = knowledge
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome=f"intent={intent!r} knowledge={knowledge!r}",
            duration_ms=round(duration, 2),
        )


class InvestigationStage:
    """
    Stage 3b: Run ReadOnlyInvestigator for investigate intents.

    Genesis-056 Sprint-001.

    Deliberately boring: if intent is investigate, hand the question
    to ReadOnlyInvestigator and store the formatted report.
    No filesystem logic, git logic, or approval logic here.
    Those live in ReadOnlyInvestigator and authorised_sources.

    If ReadOnlyInvestigator is not available, falls through
    with a structured error ? never to ConversationPipeline.
    """
    NAME = "InvestigationStage"

    def __init__(self, investigator=None, session_store=None) -> None:
        self._investigator  = investigator
        self._session_store = session_store

    def run(
        self,
        request: "MissionRequest",
        state: dict,
    ) -> "MissionStageResult":
        start  = time.perf_counter()
        intent = state.get("intent", "unknown")

        if intent != "investigate":
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME,
                executed=False,
                outcome="skipped ? intent is not investigate",
                duration_ms=round(duration, 2),
            )

        if self._investigator is None:
            state["response_message"] = (
                "Investigation capability is not available in this session."
            )
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME,
                executed=True,
                outcome="investigator not available",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        try:
            report = self._investigator.investigate(request.message)
            state["investigation_report"]  = report
            state["response_message"]      = report.format_for_mission()
            state["approval_required"]     = report.approval_required
            state["investigation_terminal"] = True

            # Genesis-056 Sprint-002: register BoundProposal in SessionStore
            # so the existing approval workflow can execute it.
            if report.bound_proposal is not None and self._session_store is not None:
                try:
                    self._register_proposal(report.bound_proposal, request)
                except Exception as reg_exc:
                    logger.warning(
                        "[INVESTIGATION_STAGE] Could not register proposal: %s", reg_exc
                    )
        except Exception as exc:
            logger.exception("[INVESTIGATION_STAGE] Investigation failed: %s", exc)
            state["response_message"] = (
                "Investigation encountered an error. No changes were made."
            )
            state["investigation_terminal"] = True

        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome="investigation complete",
            duration_ms=round(duration, 2),
            terminal=state.get("investigation_terminal", False),
        )


    def _register_proposal(self, proposal, request) -> None:
        """
        Register a BoundProposal in the dedicated investigations SessionStore.

        Genesis-056 Sprint-003: uses data/orchestrator/investigations/ subdirectory
        so investigation proposals never mix with engineering coordinator sessions.
        This eliminates the duplicate approval card.
        """
        import time
        from pathlib import Path
        from core.engineering.coordinator.models import (
            EngineeringSession, EngineeringRequest, EngineeringStatus, EngineeringStage,
        )
        from core.engineering.coordinator.session_store import SessionStore

        inv_store_dir = Path("data") / "orchestrator" / "investigations"
        inv_store = SessionStore(directory=inv_store_dir)

        eng_request = EngineeringRequest(
            request  = f"[INVESTIGATION PROPOSAL] {proposal.investigation_id}",
            context  = "Mission Mode investigation proposal",
            metadata = {"investigation_id": proposal.investigation_id, "type": "INVESTIGATION_PROPOSAL"},
        )
        session = EngineeringSession(
            session_id     = proposal.investigation_id,
            request        = eng_request,
            status         = EngineeringStatus.AWAITING_APPROVAL,
            started_at     = int(time.monotonic() * 1000),
            current_stage  = EngineeringStage.AWAITING_APPROVAL,
            execution_plan = proposal.to_dict(),
        )
        session.events.record(
            EngineeringStage.AWAITING_APPROVAL,
            "Investigation proposal awaiting approval",
        )
        inv_store.save(session)
        logger.info(
            "[INVESTIGATION_STAGE] BoundProposal %s registered in investigations store.",
            proposal.investigation_id,
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

    Genesis-055 Sprint-002A: retrieval-first hierarchy (GPT-approved).

        FACT        -> answer directly from MissionRegistry (no AI call)
        HISTORICAL  -> honest "I don't have that document" (no fabrication)
        UNKNOWN     -> honest "I don't know" with capability description
        write       -> approval required
        run_tests   -> worker dispatch (wired in future sprint)

    Policy is already checked. This stage never checks policy itself.
    The AI is never called in this stage.
    """
    NAME = "DispatchStage"

    def run(
        self,
        request: MissionRequest,
        state: dict,
    ) -> MissionStageResult:
        start     = time.perf_counter()
        intent    = state.get("intent", "unknown")
        knowledge = state.get("knowledge", "unknown")
        ctx       = state.get("engineering_context", {})

        if state.get("approval_required"):
            state["response_message"] = (
                "That operation requires explicit approval from Gianni. "
                "Please use the approval workflow."
            )

        elif knowledge == "fact" and intent == "read_current":
            genesis  = ctx.get("current_genesis", "-")
            sprint   = ctx.get("current_sprint", "-")
            mission  = ctx.get("current_mission", "-")
            commit   = ctx.get("last_commit", "-")
            branch   = ctx.get("branch", "-")
            passed   = ctx.get("tests_passed", 0)
            skipped  = ctx.get("tests_skipped", 0)
            failed   = ctx.get("tests_failed", 0)
            t_commit = ctx.get("tests_commit", "-")
            if passed > 0:
                tests_str = str(passed) + " passed / " + str(skipped) + " skipped / " + str(failed) + " failed @ " + t_commit
            else:
                tests_str = "No test result recorded this session yet."
            parts = [
                "Current engineering state:",
                "  Genesis:  " + genesis,
                "  Sprint:   " + sprint,
                "  Mission:  " + mission,
                "  Tests:    " + tests_str,
                "  Commit:   " + commit,
                "  Branch:   " + branch,
            ]
            state["response_message"] = "\n".join(parts)

        elif knowledge == "fact" and intent == "read_objectives":
            progress  = ctx.get("progress_percent", 0)
            milestone = ctx.get("next_milestone", "-")
            objectives = ctx.get("objectives", [])
            obj_lines = []
            if objectives:
                for o in objectives:
                    tick = "v" if o.get("done") else "o"
                    obj_lines.append("  " + tick + " " + o.get("text", ""))
            else:
                obj_lines.append("  No objectives recorded.")
            parts = ["Objectives - " + str(progress) + "% complete:"] + obj_lines + ["Next milestone: " + milestone]
            state["response_message"] = "\n".join(parts)

        elif knowledge == "fact" and intent == "run_tests":
            state["response_message"] = (
                "Test execution is noted. "
                "Direct worker dispatch from Mission Mode will be wired "
                "in a future sprint. Run tests via the desktop for now."
            )

        elif knowledge == "historical":
            parts = [
                "I don't currently have an authoritative document for that in the project knowledge base.",
                "",
                "Historical Genesis delivery records and architectural decision documents (ADRs)",
                "have not yet been committed to the repository for Genesis-019 through Genesis-055.",
                "",
                "I won't invent an answer. If you need this information,",
                "the source is our engineering session history.",
            ]
            state["response_message"] = "\n".join(parts)

        else:
            genesis = ctx.get("current_genesis", "-")
            sprint  = ctx.get("current_sprint", "-")
            parts = [
                "I am in Mission Mode (" + genesis + " / " + sprint + ").",
                "",
                "I can answer questions about:",
                "  - Current genesis, sprint, and mission",
                "  - Objectives and progress",
                "  - Test results and commit state",
                "",
                "I cannot yet answer questions about past genesis delivery",
                "or architectural rationale - those documents do not exist",
                "in the knowledge base yet.",
            ]
            state["response_message"] = "\n".join(parts)

        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome="intent=" + repr(intent) + " knowledge=" + repr(knowledge),
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

    def __init__(self, mission_registry: Optional["MissionRegistry"] = None, project_root=None, session_store=None) -> None:
        # Genesis-056 Sprint-002: SessionStore for proposal registration
        mission_session_store = session_store

        # Genesis-056 Sprint-001: ReadOnlyInvestigator
        _investigator = None
        if project_root is not None:
            try:
                _registry_inv = AuthorisedSourceRegistry(project_root)
                _investigator = ReadOnlyInvestigator(_registry_inv, project_root)
                logger.info("[MISSION_PIPELINE] ReadOnlyInvestigator ready.")
            except Exception as e:
                logger.warning("[MISSION_PIPELINE] ReadOnlyInvestigator unavailable: %s", e)

        self._policy_check   = PolicyCheckStage()
        self._context_build  = ContextBuildStage(mission_registry)
        self._intent         = IntentStage()
        self._investigation  = InvestigationStage(_investigator, session_store=mission_session_store)
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

            # Stage 3b: Investigation (Genesis-056 Sprint-001)
            result = self._investigation.run(request, state)
            trace.append(result)
            if result.terminal:
                return self._response.run(request, state, trace)

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