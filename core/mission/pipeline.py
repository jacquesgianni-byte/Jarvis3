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
from core.mission.investigation import ReadOnlyInvestigator, ReadOnlyGitReader
from core.mission.authorised_sources import AuthorisedSourceRegistry
from core.knowledge.concept_resolver import ConceptResolver
from core.knowledge.genesis_record import GenesisDeliveryStore
from core.knowledge.capability_gap import GapObservationStore
from core.knowledge.gap_observation_engine import GapObservationEngine
from core.knowledge.proximity import CapabilityProximityAnalyser
from core.mission.investigation_registry import InvestigationRegistry as _InvRegistry
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

    def __init__(self, mission_registry: Optional["MissionRegistry"], project_root=None) -> None:
        self._registry     = mission_registry
        self._project_root = project_root

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

        # Genesis-059 Sprint-003: apply AuthorityPolicy for current_genesis and current_sprint.
        # Git HEAD is declared authoritative for these keys (AuthorityPolicy.AUTHORITY).
        # ContextBuildStage is the single point where authority is resolved.
        # Downstream stages consume engineering_context and never re-decide authority.
        if self._project_root is not None:
            try:
                git_reader  = ReadOnlyGitReader(self._project_root)
                git_message = git_reader.head_message()
                from core.mission.investigation import extract_genesis_label, extract_sprint_label
                genesis_ex = extract_genesis_label(git_message)
                sprint_ex  = extract_sprint_label(git_message)
                if genesis_ex.present and genesis_ex.value:
                    engineering_context["current_genesis"] = genesis_ex.value
                if sprint_ex.present and sprint_ex.value:
                    engineering_context["current_sprint"] = sprint_ex.value
            except Exception as e:
                logger.warning(
                    "[CONTEXT_BUILD] Git authority resolution failed: %s - "
                    "engineering_context retains project_state.json values.", e
                )

        state["engineering_context"] = engineering_context
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME,
            executed=True,
            outcome=f"context built ({len(engineering_context)} fields)",
            duration_ms=round(duration, 2),
        )


class KnowledgePreclassificationStage:
    """
    Stage 2b: Attempt concept resolution before intent classification.

    Genesis-059 Sprint-002.

    Responsibility: one job only.
        Can this question be resolved to a known knowledge concept
        AND is it delivery-shaped (not investigation-shaped)?

    If yes:
        state["knowledge_query"] = {"resolved_id": ..., "query_type": "delivery"}
    If no:
        state["knowledge_query"] = None

    Uses ConceptResolver (pure, injected) with current_genesis from
    engineering_context - no filesystem access here.

    IntentStage reads state["knowledge_query"] and respects it.
    This stage never modifies IntentStage behaviour directly.
    """
    NAME = "KnowledgePreclassificationStage"

    # Questions that contain a resolvable concept but are NOT knowledge queries.
    # These stay in the investigation path even if concept resolves.
    _INVESTIGATION_SIGNALS = (
        "investigate", "consistent", "why", "should we",
        "diagnose", "root cause", "any issues", "any problems",
        "anything wrong", "reconcile", "reconciliation",
    )

    # Questions must contain at least one delivery signal to be classified
    # as a knowledge query. This prevents concept-only hijacking.
    _DELIVERY_SIGNALS = (
        "what changed", "what did", "what was changed",
        "what was delivered", "what was added", "what was introduced",
        "what did it deliver", "what did it change", "what did it add",
        "tell me what", "show me what", "delivered", "introduced",
    )

    def run(self, request, state: dict):
        import time
        start = time.perf_counter()

        state["knowledge_query"] = None

        ctx              = state.get("engineering_context", {})
        current_genesis  = ctx.get("current_genesis", "")

        if not current_genesis:
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome="no current_genesis in context ? skipped",
                duration_ms=round(duration, 2),
            )

        resolver   = ConceptResolver(current_genesis_id=current_genesis)
        msg_lower  = request.message.lower()
        resolved   = resolver.resolve(request.message)

        if resolved is None:
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome="no concept resolved",
                duration_ms=round(duration, 2),
            )

        # Concept resolved ? now check shape
        # Investigation-shaped questions stay out of knowledge path
        if any(sig in msg_lower for sig in self._INVESTIGATION_SIGNALS):
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome=f"concept resolved ({resolved}) but investigation-shaped ? not knowledge",
                duration_ms=round(duration, 2),
            )

        # Must be delivery-shaped to claim the knowledge path
        if not any(sig in msg_lower for sig in self._DELIVERY_SIGNALS):
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome=f"concept resolved ({resolved}) but not delivery-shaped ? not knowledge",
                duration_ms=round(duration, 2),
            )

        # Both conditions met: resolvable concept + delivery shape
        state["knowledge_query"] = {
            "resolved_id": resolved,
            "query_type":  "delivery",
        }
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME, executed=True,
            outcome=f"knowledge query: delivery / {resolved}",
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

    # Genesis-060 Sprint-003: gap reporting intents
    WHY_FAILED_KEYWORDS = (
        "why couldn't you", "why could you not", "why didn't you answer",
        "why don't you know", "why can't you answer", "what went wrong",
        "why did you fail", "why did jarvis fail",
        "why wouldn't you", "why won't you",
        "why didn't you", "why aren't you",
    )
    WHAT_NEEDED_KEYWORDS = (
        "what would you need", "what do you need", "what's missing",
        "what is missing", "what capability", "what would be needed",
        "what knowledge", "what would help you answer",
    )

    # Genesis-062 Sprint-003: capability inventory intent
    CAPABILITY_INVENTORY_KEYWORDS = (
        "what can you do", "what can jarvis do", "what are your capabilities",
        "what investigations can you run", "what investigations do you have",
        "what can you investigate", "list your capabilities",
        "what do you know how to do", "show me your capabilities",
        "what are you capable of", "what investigations are available",
        "what can you check", "what can you analyse",
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

        # Genesis-059 Sprint-002: respect KnowledgePreclassificationStage signal.
        # If a knowledge query was already identified, assign intent and skip matching.
        if state.get("knowledge_query") is not None:
            state["intent"]    = "read_knowledge"
            state["knowledge"] = "fact"
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME,
                executed=True,
                outcome="intent=read_knowledge (from KnowledgePreclassificationStage)",
                duration_ms=round(duration, 2),
            )

        # Priority order: write > why_failed > what_needed > investigate > run_tests > historical > current > objectives > unknown
        # Whole-word matching prevents 'changes' matching 'change', etc. Genesis-056 Sprint-004 fix.
        if self._matches_any(msg, self.WRITE_KEYWORDS):
            intent    = "write"
            knowledge = "approval_required"
        elif self._matches_any(msg, self.WHY_FAILED_KEYWORDS):
            intent    = "why_failed"
            knowledge = "fact"
        elif self._matches_any(msg, self.WHAT_NEEDED_KEYWORDS):
            intent    = "what_needed"
            knowledge = "fact"
        elif self._matches_any(msg, self.CAPABILITY_INVENTORY_KEYWORDS):
            intent    = "capability_inventory"
            knowledge = "fact"
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


class KnowledgeQueryStage:
    """
    Stage 3c: Answer knowledge queries from GenesisDeliveryStore.

    Genesis-059 Sprint-002.

    Runs only when state["knowledge_query"] is set by
    KnowledgePreclassificationStage. Never runs for investigation intents.

    Queries GenesisDeliveryStore with the resolved genesis_id.
    Returns a formatted answer from GenesisDeliveryRecord.format_answer().
    Terminal on success or honest no-record response.
    No LLM. No filesystem access beyond GenesisDeliveryStore.latest_id().
    """
    NAME = "KnowledgeQueryStage"

    def __init__(self, project_root=None) -> None:
        self._project_root = project_root

    def run(self, request, state: dict):
        import time
        start  = time.perf_counter()
        kq     = state.get("knowledge_query")

        if kq is None:
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=False,
                outcome="skipped ? no knowledge query",
                duration_ms=round(duration, 2),
            )

        resolved_id = kq.get("resolved_id")
        query_type  = kq.get("query_type")

        if query_type != "delivery" or not resolved_id:
            state["response_message"] = (
                "I recognised a project concept in your question "
                "but I don't yet support that type of query."
            )
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome="unsupported query type",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        if self._project_root is None:
            state["response_message"] = (
                "Knowledge store is not available in this session."
            )
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome="no project root",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        store  = GenesisDeliveryStore(self._project_root)
        record = store.get(resolved_id)

        if record is None:
            state["response_message"] = (
                f"I resolved your question to {resolved_id} "
                f"but I don't have a delivery record for it yet."
            )
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome=f"no record for {resolved_id}",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        state["response_message"] = record.format_answer()
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME, executed=True,
            outcome=f"delivery record returned for {resolved_id}",
            duration_ms=round(duration, 2),
            terminal=True,
        )


class CapabilityInventoryStage:
    """
    Stage 3e: Answer capability inventory queries.

    Genesis-062 Sprint-003.

    Handles intent="capability_inventory" ? questions like:
        "What can you do?"
        "What investigations can you run?"
        "What are your capabilities?"

    Report is generated entirely from InvestigationRegistry.all_descriptors()
    and GenesisDeliveryStore ? no hardcoded prose, no developer-written
    capability descriptions. Every line in the report comes from declared,
    registered evidence.

    Does not create observations. Does not modify any store.
    Does not invoke an LLM. Terminal when it fires.
    """
    NAME = "CapabilityInventoryStage"

    def __init__(self, registry=None, delivery_store=None) -> None:
        self._registry       = registry
        self._delivery_store = delivery_store

    def run(self, request, state: dict):
        import time
        start  = time.perf_counter()
        intent = state.get("intent", "unknown")

        if intent != "capability_inventory":
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=False,
                outcome="skipped ? intent is not capability_inventory",
                duration_ms=round(duration, 2),
            )

        state["response_message"] = self._format_inventory()
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME, executed=True,
            outcome="capability inventory returned",
            duration_ms=round(duration, 2),
            terminal=True,
        )

    def _format_inventory(self) -> str:
        """
        Format a capability inventory from registered evidence only.
        No hardcoded prose. Every item comes from declared registry data.
        """
        lines = [
            "CAPABILITY INVENTORY",
            "-" * 40,
            "",
        ]

        if self._registry is not None:
            descriptors = self._registry.all_descriptors()
            lines.append(f"Registered investigations ({len(descriptors)}):")
            for d in descriptors:
                lines.append(f"  [{d.name}]")
                lines.append(f"    {d.description}")
                lines.append(f"    Evidence sources: {', '.join(d.evidence_sources)}")
        else:
            lines.append("Investigation registry: not available.")

        lines.append("")

        if self._delivery_store is not None:
            all_ids = self._delivery_store.all_ids()
            lines.append(f"Genesis delivery records ({len(all_ids)}):")
            for gid in all_ids:
                record = self._delivery_store.get(gid)
                if record:
                    lines.append(f"  {gid} ? {record.display_name}")
        else:
            lines.append("Genesis delivery store: not available.")

        lines += [
            "",
            "Knowledge query types supported:",
            "  [delivery] What changed in the latest Genesis?",
            "",
            "Note: this inventory is generated from registered evidence.",
            "It reflects actual declared capabilities, not a developer-written description.",
        ]

        return "\n".join(lines)


class GapReportStage:
    """
    Stage 3d: Report capability-gap evidence for why_failed / what_needed intents.

    Genesis-060 Sprint-003.

    Responsibilities:
        - Report stored gap observations for why_failed intent
        - Derive missing capability from observations for what_needed intent
        - Never create new observations
        - Never modify GapObservationStore
        - Never invoke an LLM
        - Never recommend a mission
        - Report boundary violations and knowledge gaps as what they are
          (not as capability gaps)

    A single observation is reported as an observation.
    Two or more matching observations are reported as a recurring gap.
    All report content is derived from stored evidence ? never developer-written.
    """
    NAME = "GapReportStage"

    def __init__(self, gap_store=None, registry=None) -> None:
        self._store    = gap_store
        self._registry = registry
        # NOTE: proximity uses the most recent observation from the store.
        # This is deliberately simple for Genesis-061 Sprint-002.
        # Session-scoped filtering can be added when the store grows large enough
        # to make per-session isolation necessary.

    def run(self, request, state: dict) -> "MissionStageResult":
        import time
        start  = time.perf_counter()
        intent = state.get("intent", "unknown")

        if intent not in ("why_failed", "what_needed"):
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=False,
                outcome="skipped ? intent is not why_failed or what_needed",
                duration_ms=round(duration, 2),
            )

        if self._store is None:
            state["response_message"] = (
                "Gap observation store is not available in this session."
            )
            duration = (time.perf_counter() - start) * 1000
            return MissionStageResult(
                stage=self.NAME, executed=True,
                outcome="store unavailable",
                duration_ms=round(duration, 2),
                terminal=True,
            )

        from core.knowledge.capability_gap import CAPABILITY_GAP_SIGNATURE, RECURRENCE_THRESHOLD
        observations = self._store.observations_by_signature(CAPABILITY_GAP_SIGNATURE)
        count        = len(observations)

        # Proximity analysis ? only when observations exist and registry available
        # Uses most recent observation (Sprint-002: deliberately simple, see __init__)
        proximity = None
        if count > 0 and self._registry is not None:
            try:
                recent   = observations[-1]
                analyser = CapabilityProximityAnalyser()
                proximity = analyser.analyse(
                    question       = recent.question,
                    observation_id = recent.observation_id,
                    registry       = self._registry,
                )
            except Exception as e:
                logger.warning("[GapReportStage] Proximity analysis failed: %s", e)
                proximity = None

        if intent == "why_failed":
            state["response_message"] = self._format_why_failed(observations, count, proximity)
        else:  # what_needed
            state["response_message"] = self._format_what_needed(observations, count, proximity)

        state["gap_report_terminal"] = True
        duration = (time.perf_counter() - start) * 1000
        return MissionStageResult(
            stage=self.NAME, executed=True,
            outcome=f"gap report: intent={intent!r} observations={count}",
            duration_ms=round(duration, 2),
            terminal=True,
        )

    @staticmethod
    def _format_why_failed(observations: list, count: int, proximity=None) -> str:
        """
        Format a why_failed report from stored evidence.
        Content derived entirely from observations ? no developer sentences.
        """
        if count == 0:
            return (
                "I have no recorded capability-gap observations in this session.\n"
                "I may not have attempted to answer an uncovered question yet, "
                "or the observation store was reset."
            )

        recent = observations[-1]
        lines  = [
            "CAPABILITY GAP EVIDENCE",
            "-" * 40,
            "",
            f"Observations recorded: {count}",
            f"Failure signature:     {recent.failure_signature}",
            "",
            "Most recent failure:",
            f"  Question:             {recent.question!r}",
            f"  Observed at:          {recent.observed_at}",
            f"  Intent classified:    {recent.intent_result}",
            f"  Knowledge path match: {'yes' if recent.knowledge_match else 'no'}",
            f"  Investigation match:  {'yes' if recent.investigation_match else 'no'}",
            f"  Boundary violation:   {'yes' if recent.boundary_violation else 'no'}",
            "",
        ]

        if count >= 2:
            lines += [
                f"Pattern: this failure signature has occurred {count} times.",
                "This is a recurring capability gap.",
                "",
                "Questions that produced this gap:",
            ]
            for obs in observations[-5:]:
                lines.append(f"  - {obs.question!r} ({obs.observed_at[:10]})")
        else:
            lines += [
                "Pattern: single observation ? not yet a confirmed recurring gap.",
                f"(Recurring gap threshold: {2} or more matching observations)",
            ]

        lines += [
            "",
            "Evidence interpretation:",
            "  No registered investigation matched the question.",
            "  No knowledge path resolved a concept in the question.",
            "  The request was not blocked by policy.",
            "  Conclusion: the question type has no registered capability.",
        ]

        if proximity is not None:
            lines += ["", proximity.format_for_report()]
        else:
            lines += [
                "",
                "Proximity analysis: not available",
                "  (no registry or no observations to analyse)",
            ]

        return "\n".join(lines)

    @staticmethod
    def _format_what_needed(observations: list, count: int, proximity=None) -> str:
        """
        Format a what_needed report derived from stored evidence.
        Derives the missing capability from the failure signature ? not hardcoded.
        """
        if count == 0:
            return (
                "I have no recorded capability-gap observations to derive from.\n"
                "Ask me something I cannot answer, then ask what I would need."
            )

        recent = observations[-1]
        lines  = [
            "DERIVED CAPABILITY REQUIREMENT",
            "-" * 40,
            "",
            f"Based on {count} recorded observation(s) with signature:",
            f"  {recent.failure_signature}",
            "",
            "What was missing:",
        ]

        # Derive from the evidence signals ? not from developer sentences
        if not recent.knowledge_match:
            lines.append(
                "  - A knowledge record covering the concept in the question."
            )
            lines.append(
                "    (No entry in GenesisDeliveryStore or equivalent resolved the request.)"
            )

        if not recent.investigation_match:
            lines.append(
                "  - A registered investigation covering the question type."
            )
            lines.append(
                "    (No entry in InvestigationRegistry matched the request.)"
            )

        if recent.intent_result == "unknown":
            lines.append(
                "  - A classified intent for this question type in IntentStage."
            )
            lines.append(
                "    (The question type is not yet recognised by the pipeline.)"
            )

        lines += [
            "",
            "To answer questions of this type, Jarvis would need at least one of:",
            "  1. A registered investigation that covers this question domain.",
            "  2. A knowledge record for the concept the question refers to.",
            "  3. A classified intent that routes this question type to a handler.",
            "",
            "No action has been taken. This is an observation report only.",
            "Any capability addition requires Gianni's approval.",
        ]

        if proximity is not None:
            lines += ["", proximity.format_for_report()]
        else:
            lines += [
                "",
                "Proximity analysis: not available",
                "  (no registry or no observations to analyse)",
            ]

        return "\n".join(lines)


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

        # Genesis-060 Sprint-002: capability gap observation
        _gap_data_dir = (project_root / "data" / "observations") if project_root else None
        _gap_store    = GapObservationStore(_gap_data_dir) if _gap_data_dir else None
        self._gap_engine = GapObservationEngine(_gap_store) if _gap_store else None

        self._policy_check        = PolicyCheckStage()
        self._context_build       = ContextBuildStage(mission_registry, project_root)
        self._knowledge_preclassify = KnowledgePreclassificationStage()
        self._intent              = IntentStage()
        self._knowledge_query     = KnowledgeQueryStage(project_root)
        # Genesis-061 Sprint-002: separate InvestigationRegistry instance for
        # GapReportStage proximity analysis. Both this instance and the one
        # inside ReadOnlyInvestigator read from the same declared _REGISTRY dict.
        # No coupling between GapReportStage and ReadOnlyInvestigator.
        _inv_registry_for_gap      = _InvRegistry(project_root) if project_root else None
        _delivery_store_for_inv    = GenesisDeliveryStore(project_root) if project_root else None
        self._capability_inventory = CapabilityInventoryStage(_inv_registry_for_gap, _delivery_store_for_inv)
        self._gap_report           = GapReportStage(_gap_store, _inv_registry_for_gap)
        self._investigation       = InvestigationStage(_investigator, session_store=mission_session_store)
        self._approval_gate       = ApprovalGateStage()
        self._dispatch            = DispatchStage()
        self._response            = ResponseStage()

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

            # Stage 2b: Knowledge preclassification (Genesis-059 Sprint-002)
            result = self._knowledge_preclassify.run(request, state)
            trace.append(result)

            # Stage 3: Intent classification — respects knowledge_query signal
            result = self._intent.run(request, state)
            trace.append(result)

            # Stage 3c: Knowledge query (Genesis-059 Sprint-002)
            result = self._knowledge_query.run(request, state)
            trace.append(result)
            if result.terminal:
                return self._response.run(request, state, trace)

            # Stage 3e: Capability inventory (Genesis-062 Sprint-003)
            result = self._capability_inventory.run(request, state)
            trace.append(result)
            if result.terminal:
                final_response = self._response.run(request, state, trace)
                if self._gap_engine is not None:
                    self._gap_engine.observe(request, state, final_response)
                return final_response

            # Stage 3d: Gap report (Genesis-060 Sprint-003)
            result = self._gap_report.run(request, state)
            trace.append(result)
            if result.terminal:
                final_response = self._response.run(request, state, trace)
                if self._gap_engine is not None:
                    self._gap_engine.observe(request, state, final_response)
                return final_response

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
            final_response = self._response.run(request, state, trace)
            # Genesis-060 Sprint-002: observe outcome for capability-gap evidence
            if self._gap_engine is not None:
                self._gap_engine.observe(request, state, final_response)
            return final_response

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