"""
Jarvis Agent

The central decision maker for Jarvis.
Owns the conversation context, intelligence, behaviour, and memory detection layers.
Every incoming message is classified, evaluated for pending interactions,
and checked for natural memory statements before intent routing.
"""

import time

from core import telemetry
from core.logger import get_logger
from core.knowledge_engine.engine import KnowledgeEngine
from core.models.response import Response
from core.reasoning.engine import ReasoningEngine
from core.skills.reasoning import ReasoningSkill
from core.tools.manager import ToolManager
from core.router import IntentRouter
from core.intents import Intent

from core.skills.manager import SkillsManager
from core.skills.greeting import GreetingSkill
from core.skills.identity import IdentitySkill
from core.skills.memory import MemorySkill
from core.skills.tool import ToolSkill
from core.skills.exit import ExitSkill
from core.skills.engineering import EngineeringSkill  # Genesis-019.5
from core.skills.system import SystemSkill  # Genesis-042

from core.conversation.context import ConversationContext
from core.conversation.intelligence import ConversationIntelligence
from core.conversation.behaviour import ConversationBehaviour
from core.conversation.decision import ConversationDecision, ConversationOutcome
from core.conversation.memory_detector import MemoryDetector
from core.conversation.memory_detection import MemoryDetection
from core.conversation.conversation_observer import ConversationObserver  # Genesis-020 S1
from core.conversation.conversation_recall import ConversationRecall      # Genesis-020 S1
from core.conversation.session_context import SessionContext              # Genesis-020 S2 (compat stub)
from core.conversation.conversation_state import ConversationState           # Genesis-043 canonical state
from core.conversation.session_context_adapter import SessionContextAdapter  # Genesis-043 migration adapter
from core.conversation.context_manager import ContextManager             # Genesis-020 S2
from core.conversation.context_resolver import ContextResolver           # Genesis-020 S2
from core.conversation.context_inspector import ContextInspector         # Genesis-020 S2
from core.conversation.conversation_timeline import ConversationTimeline  # Genesis-020 S3
from core.conversation.timeline_query import TimelineQueryEngine          # Genesis-020 S3
from core.conversation.timeline_inspector import TimelineInspector        # Genesis-020 S3
from core.conversation.decision_engine import DecisionEngine              # Genesis-020 S4
from core.conversation.decision_query import DecisionQueryEngine          # Genesis-020 S4
from core.conversation.decision_inspector import DecisionInspector        # Genesis-020 S4
from core.conversation.goal_engine import GoalEngine                      # Genesis-020 S5
from core.conversation.goal_query import GoalQueryEngine                  # Genesis-020 S5
from core.conversation.goal_inspector import GoalInspector                # Genesis-020 S5
from core.conversation.session_summary_engine import SessionSummaryEngine      # Genesis-020 S6
from core.conversation.session_summary_query import SessionSummaryQueryEngine  # Genesis-020 S6
from core.conversation.session_summary_inspector import SessionSummaryInspector # Genesis-020 S6
from core.conversation.fact_extractor import FactExtractor       # Genesis-020: post-turn
from core.conversation.timeline_event import EventType           # Genesis-020: post-turn
from core.conversation.conversation_engine import ConversationEngine   # Genesis-022
from core.conversation.conversation_models import DecisionType         # Genesis-022
from core.conversation.slot_completion_engine import SlotCompletionEngine  # Genesis-025
from core.conversation.contextual_recall_engine import ContextualRecallEngine  # Genesis-025 S4
from core.conversation.reverse_entity_parser import ReverseEntityParser         # Genesis-026 S3
from core.workers.models import WorkerTask
from core.workers.manager import WorkerManager                                   # Genesis-027
from core.workers.orchestrator import WorkerOrchestrator                         # Genesis-027
from core.workers.worker_factory import WorkerFactory                            # Genesis-027
from core.workers.debug_worker import DebugWorker                                # Genesis-027
from core.workers.suite_worker import SuiteRunnerWorker                          # Genesis-027 S3
from core.workers.coding_worker import CodingWorker                              # Genesis-027 S2
from core.workers.engineering_review_worker import EngineeringReviewOSWorker  # Genesis-033 Integration
from core.workers.coordinator import WorkerCoordinator                           # Genesis-027 S3
from core.workers.task_planner import TaskPlanner, WorkerPlan                   # Genesis-027 S4
from core.workers.engineering_intent_detector import EngineeringIntentDetector  # Genesis-027 S4
from core.conversation.conversation_reference_detector import ConversationReferenceDetector  # CV-003
from core.conversation.property_assigner import PropertyAssigner                # Genesis-028
from core.conversation.property_recall_engine import PropertyRecallEngine       # Genesis-028
from core.conversation.conversation_state_engine import ConversationStateEngine # Genesis-029
from core.conversation.clarification_engine import (                             # Genesis-029 S3
    ClarificationEngine, PendingClarification,
)
from core.conversation.temporal_parser import TemporalParser                    # Genesis-031
from core.conversation.temporal_recall_engine import TemporalRecallEngine       # Genesis-031
from core.conversation.semantic_recall_engine import SemanticRecallEngine       # Genesis-032
from core.conversation.relationship_recall import (                              # Genesis-032 S2
    RelationshipProvider, RelationshipRecallEngine,
)
from core.episodic_memory_engine import EpisodicMemoryEngine
from core.conversation.followup_resolver import FollowUpResolver  # Genesis-042 S3                     # Genesis-032 S3
from core.ai_workers.claude_worker import ClaudeAIWorker
from core.engineering.collaboration.runner import CollaborationRunner  # Genesis-040 S2
from core.engineering.execution.execution_runner import ExecutionRunner  # Genesis-041 S5  # Genesis-040 S1
from core.engineering.execution.git_worker import GitWorker  # Genesis-041 S2
from core.engineering.execution.execution_workers import (  # Genesis-041 S3
    ExecutionWorker, RollbackWorker,
)
from core.worker_intelligence.engine import WorkerIntelligenceEngine  # Genesis-039 S1
from core.collaboration.engine import WorkerCollaborationEngine  # Genesis-038 S1
from core.planning.engine import PlanningEngine  # Genesis-037 S1
from core.decision.engine import DecisionEngine  # Genesis-036 S1
from core.executive.engine import ExecutiveDashboardEngine  # Genesis-035 S2
from core.progress.engine import ProgressEngine  # Genesis-035 S1
from core.engineering.lifecycle.manager import LifecycleManager
from core.engineering.evidence.manager import EvidenceManager  # Genesis-034 S2  # Genesis-034 S1
from core.goal_intelligence.engine import GoalIntelligenceEngine   # Genesis-033 S2


class Agent:
    """
    The central decision maker for Jarvis.

    Owns one each of:
        ConversationContext         -- current conversation state
        ConversationIntelligence    -- message classification
        ConversationBehaviour       -- pending interaction handling
        MemoryDetector              -- natural memory statement detection
        SlotCompletionEngine        -- generic slot completion (Genesis-025)
        ConversationObserver        -- automatic fact extraction (S1)
        ConversationRecall          -- contextual/temporal recall (S1)
        SessionContext              -- in-memory working memory (S2)
        ContextManager              -- updates working memory each turn (S2)
        ContextResolver             -- resolves pronouns/references (S2)
        ContextInspector            -- developer context snapshot (S2)
        ConversationTimeline        -- append-only event history (S3)
        TimelineQueryEngine         -- answers history questions (S3)
        TimelineInspector           -- developer timeline snapshot (S3)
        DecisionEngine              -- records and explains decisions (S4)
        DecisionQueryEngine         -- answers decision questions (S4)
        DecisionInspector           -- developer decision snapshot (S4)
        GoalEngine                  -- tracks goals as Projection (S5)
        GoalQueryEngine             -- answers goal questions (S5)
        GoalInspector               -- developer goal snapshot (S5)
        SessionSummaryEngine        -- deterministic session summary (S6)
        SessionSummaryQueryEngine   -- answers session questions (S6)
        SessionSummaryInspector     -- developer summary snapshot (S6)
        PropertyAssigner            -- generic entity property detection (Genesis-028)
        PropertyRecallEngine        -- entity property storage/retrieval (Genesis-028)

    Args:
        ai: Optional AI provider. Used as fallback when no intent is matched.
    """

    def __init__(self, ai=None):
        self.logger = get_logger()

        # Core services
        self.router = IntentRouter()
        self.knowledge = KnowledgeEngine()
        self.reasoning = ReasoningEngine(self.knowledge)
        self.tools = ToolManager()
        self.ai = ai

        # Skills
        self.skills = SkillsManager()
        self.skills.register(GreetingSkill())
        self.skills.register(IdentitySkill())
        self.skills.register(MemorySkill(self.knowledge))
        self.skills.register(ReasoningSkill(self.reasoning))
        self.skills.register(ToolSkill(self.tools))
        self.skills.register(ExitSkill())
        self.skills.register(EngineeringSkill(ai=self.ai))  # Genesis-019.5
        self.skills.register(SystemSkill())  # Genesis-042

        # Conversation layer
        self.context = ConversationContext()
        self.intelligence = ConversationIntelligence()
        self.behaviour = ConversationBehaviour()

        # Memory detection
        self.memory_detector = MemoryDetector()

        # Genesis-025: generic slot completion (runs before MemoryDetector)
        self.slot_completion = SlotCompletionEngine()

        # Genesis-025 Sprint-004: context-aware recall (runs before ConversationRecall)
        self.contextual_recall = ContextualRecallEngine()

        # Genesis-026 Sprint-003: reverse entity lookup parser
        self.reverse_entity_parser = ReverseEntityParser()

        # CV-003: conversational reference detector
        self.conversation_reference_detector = ConversationReferenceDetector()

        # Genesis-028: generic property assignment
        self.property_assigner = PropertyAssigner()
        self.property_recall = PropertyRecallEngine(self.knowledge)

        # Genesis-029: Conversation State Engine
        self.conversation_state = ConversationStateEngine()

        # Genesis-029 Sprint-003: Clarification Engine
        self.clarification_engine = ClarificationEngine()
        self._pending_clarification: PendingClarification | None = None
        self._recent_entities: list[str] = []

        # Genesis-031: Temporal Intelligence
        self.temporal_parser = TemporalParser()
        self.temporal_recall = TemporalRecallEngine()

        # Genesis-032: Semantic Recall Engine with RelationshipProvider
        self.semantic_recall = SemanticRecallEngine()
        self.semantic_recall.register_provider(RelationshipProvider())

        # Genesis-032 Sprint-002: Relationship Recall Engine
        self.relationship_recall = RelationshipRecallEngine()

        # Genesis-032 Sprint-003: Episodic Memory Engine
        self.episodic_memory = EpisodicMemoryEngine(self.knowledge, self.temporal_parser)
        # Genesis-042 Sprint-003: Follow-up resolver
        self.followup_resolver = FollowUpResolver()
        self.goal_intelligence = GoalIntelligenceEngine(self.knowledge)  # Genesis-033 S2
        # Genesis-034 Sprint-001: Engineering Lifecycle Manager
        self.lifecycle_manager = LifecycleManager(self.knowledge)
        # Genesis-035 Sprint-001: Progress Engine
        self.progress_engine = ProgressEngine(self.knowledge)
        # Genesis-035 Sprint-002: Executive Dashboard
        self.executive_dashboard = ExecutiveDashboardEngine(self.knowledge)


        # Genesis-034 Sprint-002: Evidence Manager
        self.evidence_manager = EvidenceManager(self.knowledge)



        # Genesis-020 Sprint-001: Conversation Memory
        self.conversation_observer = ConversationObserver(self.knowledge)
        self.conversation_recall = ConversationRecall(self.knowledge)

        # Genesis-043 Runtime Integration: ONE shared ConversationState
        # Named jarvis_state to avoid collision with self.conversation_state
        # which is already used for ConversationStateEngine (Genesis-029).
        # Genesis-044 will clean up this naming once ConversationStateEngine is renamed.
        # SessionContextAdapter is a temporary migration shim â€” retired in Genesis-044.
        self.jarvis_state = ConversationState()
        self.session = SessionContextAdapter(self.jarvis_state)

        # Genesis-020 Sprint-002: Active Conversation Context
        # These now write to ConversationState via the adapter.
        self.context_manager = ContextManager(self.session)
        self.context_resolver = ContextResolver(self.session)
        self.context_inspector = ContextInspector(self.session)

        # Genesis-020 Sprint-003: Conversation Timeline
        self.timeline = ConversationTimeline()
        self.timeline_query = TimelineQueryEngine(self.timeline)
        self.timeline_inspector = TimelineInspector(self.timeline)

        # Genesis-020 Sprint-004: Decision Engine
        self.decision_engine = DecisionEngine(self.knowledge)
        # Genesis-037 Sprint-001: Planning Engine
        self.planning_engine = PlanningEngine(self.knowledge)



        self.decision_query = DecisionQueryEngine(self.decision_engine)
        self.decision_inspector = DecisionInspector(self.decision_engine)

        # Genesis-020 Sprint-005: Goal Engine
        self.goal_engine = GoalEngine()
        self.goal_query = GoalQueryEngine(self.goal_engine)
        self.goal_inspector = GoalInspector(self.goal_engine)

        # Genesis-020 Sprint-006: Session Summary Engine
        self.summary_engine = SessionSummaryEngine()
        self.summary_query = SessionSummaryQueryEngine(self.summary_engine)
        self.summary_inspector = SessionSummaryInspector(self.summary_engine)

        # Genesis-022: Conversation Engine (owns its own internal ConversationState)
        # Genesis-044 will unify with jarvis_state.
        self.conversation_engine = ConversationEngine()

        # Genesis-027: Worker Operating System
        # WorkerManager owns the registry. WorkerOrchestrator routes tasks.
        # WorkerFactory creates workers with dependency injection.
        self.worker_manager      = WorkerManager()
        self.worker_orchestrator = WorkerOrchestrator(self.worker_manager)
        self.worker_factory      = WorkerFactory()

        # Register builders - lambdas only, no worker-specific logic in factory
        self.worker_factory.register_builder(
            "debug_worker", lambda deps: DebugWorker()
        )
        self.worker_factory.register_builder(
            "test_worker", lambda deps: SuiteRunnerWorker()
        )
        self.worker_factory.register_builder(
            "coding_worker", lambda deps: CodingWorker(deps["ai"])
        )
        self.worker_factory.register_builder(
            "engineering_review_worker", lambda deps: EngineeringReviewOSWorker()
        )  # Genesis-033 Integration
        self.worker_factory.register_builder(
            "claude_ai_worker", lambda deps: ClaudeAIWorker(deps.get("ai"))
        )  # Genesis-040 S1
        self.worker_factory.register_builder(
            "suite_runner_worker", lambda deps: SuiteRunnerWorker()
        )
        self.worker_factory.register_builder(
            "git_worker", lambda deps: GitWorker(deps.get("repo_root", "."))
        )  # Genesis-041 S2
        self.worker_factory.register_builder(
            "execution_worker", lambda deps: ExecutionWorker(deps.get("repo_root", "."))
        )  # Genesis-041 S3
        self.worker_factory.register_builder(
            "rollback_worker", lambda deps: RollbackWorker(deps.get("repo_root", "."))
        )  # Genesis-041 S3

        # Register workers via factory (single creation path)
        self.worker_manager.register(self.worker_factory.create("debug_worker"))
        self.worker_manager.register(self.worker_factory.create("claude_ai_worker", deps={"ai": self.ai}))  # Genesis-040 S1
        self.worker_manager.register(self.worker_factory.create("suite_runner_worker"))
        self.worker_manager.register(self.worker_factory.create("engineering_review_worker"))  # Genesis-033 Integration
        self.worker_manager.register(
            self.worker_factory.create("git_worker", deps={"repo_root": "."})
        )  # Genesis-041 S2
        self.worker_manager.register(
            self.worker_factory.create("execution_worker", deps={"repo_root": "."})
        )  # Genesis-041 S3
        self.worker_manager.register(
            self.worker_factory.create("rollback_worker", deps={"repo_root": "."})
        )  # Genesis-041 S3
        if self.ai is not None:
            self.worker_manager.register(
                self.worker_factory.create("coding_worker", deps={"ai": self.ai})
            )

        # Genesis-027 Sprint-003: WorkerCoordinator for multi-worker workflows
        self.worker_coordinator = WorkerCoordinator(self.worker_manager)

        # Register the engineering_review workflow:
        # CodingWorker -> DebugWorker -> SuiteRunnerWorker
        self.worker_coordinator.register_workflow(
            "engineering_review",
            ["coding_worker", "debug_worker", "suite_runner_worker"],
        )

        self.worker_coordinator.register_workflow(
            "run_engineering_review",
            ["engineering_review_worker"],
        )  # Genesis-033 Integration

        # Genesis-027 Sprint-004: TaskPlanner + EngineeringIntentDetector
        self.task_planner = TaskPlanner(self.worker_manager)

        # Genesis-038 Sprint-001: Worker Collaboration Engine
        self.collaboration_engine = WorkerCollaborationEngine(
            self.worker_manager, self.worker_coordinator
        )
        self.worker_intelligence = WorkerIntelligenceEngine(self.knowledge, self.worker_manager)
        # Genesis-040 Sprint-002: Engineering Collaboration Runner
        self.collaboration_runner = CollaborationRunner(
            worker_coordinator=self.worker_coordinator,
            worker_manager=self.worker_manager,
            worker_intelligence=self.worker_intelligence,
        )  # Genesis-039 S1
        # Genesis-041 Sprint-005: ExecutionRunner (post-approval pipeline)
        self.execution_runner = ExecutionRunner(
            worker_coordinator=self.worker_coordinator,
            worker_manager=self.worker_manager,
            worker_intelligence=self.worker_intelligence,
        )
        self.engineering_intent_detector = EngineeringIntentDetector()

    def process(self, request: str, token=None) -> Response:
        """
        Process a user request.

        Args:
            request: The user's message.
            token:   Opaque conversation-ownership context supplied by
                     JarvisCore. The Agent never inspects it and never
                     decides whether a response is stale -- that is the
                     Conversation layer's job.

        Flow:
            1.  Classify via ConversationIntelligence.
            2.  Evaluate for pending interactions via ConversationBehaviour.
            3.  If handled, translate ConversationDecision to Response.
            4.  Check for memory statements via SlotCompletionEngine (generic)
                then MemoryDetector (explicit patterns) -- Genesis-025.
            5.  If detected, store via MemorySkill and acknowledge.
            6.  Resolve ambiguous references via ContextResolver (S2).
            7.  Proceed with normal intent routing.
            8.  Update ConversationContext.
            9.  Post-turn: memory, context, timeline, decisions, goals, summary.
        """

        self.logger.info("Request received: %s", request)
        pipeline_start = time.perf_counter()
        self.context.last_user_message = request

        # Step 1 -- Classify.
        with telemetry.stage("classification"):
            category = self.intelligence.classify(request, self.context)
        self.logger.debug(f"Message category: {category.name}")

        # Step 2 -- Evaluate for pending interaction.
        with telemetry.stage("behaviour"):
            decision = self.behaviour.handle(category, self.context)

        # Step 3 -- If handled, translate decision to Response.
        if decision is not None and decision.handled:
            response = self._respond_to_decision(decision)
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # CV-003: Detect conversational reference statements before Step 4.
        # "Earlier I mentioned my servers." / "Remember my dogs?" etc.
        # Silently restores active_topic so the normal pipeline answers naturally.
        _conv_ref = self.conversation_reference_detector.detect(request)
        if _conv_ref:
            from core.conversation.contextual_recall_engine import _KIND_TO_DECLARATION_ATTR
            _decl_attr = _KIND_TO_DECLARATION_ATTR.get(_conv_ref.kind, f"group:{_conv_ref.kind}")
            _decl_rec = self.knowledge.recall_memory("user", _decl_attr)
            if _decl_rec:
                self.session.set_topic(_decl_rec.value, raw=_decl_rec.value)
                self.logger.info(
                    "[CVREF] Restored active_topic=%r for kind=%r",
                    _decl_rec.value, _conv_ref.kind,
                )
                _ack = Response(success=True, message="Of course.")
                self.context.last_jarvis_response = _ack.message
                self._post_turn(request, _ack.message)
                return _ack

        # Genesis-029 Sprint-003: Clarification checks BEFORE Step 4 (memory detection)
        # so pronoun questions don't get swallowed by the MemoryDetector.

        # 3a. If user is replying to a pending clarification, handle it now.
        if self._pending_clarification is not None:
            _clf_res = self.clarification_engine.try_resolve(request, self._pending_clarification)
            if _clf_res.resolved:
                self.conversation_state.update_entity(_clf_res.entity, self.session)
                self._pending_clarification = None
                _rewritten = _clf_res.rewritten
                _pq2 = self.property_assigner.detect_query(_rewritten)
                if _pq2 is not None:
                    _r2 = self.property_recall.retrieve(_pq2)
                    if _r2.found:
                        self.context.last_jarvis_response = _r2.message
                        self._post_turn(request, _r2.message)
                        return Response(success=True, message=_r2.message)
                _pa2 = self.property_assigner.detect_assignment(_rewritten)
                if _pa2 is not None:
                    _s2 = self.property_recall.store(_pa2)
                    if _s2.success:
                        self.context.last_jarvis_response = _s2.message
                        self._post_turn(request, _s2.message)
                        return Response(success=True, message=_s2.message)
            else:
                _q = self._pending_clarification.question
                self.context.last_jarvis_response = _q
                self._post_turn(request, _q)
                return Response(success=True, message=_q)

        # 3b. Check for ambiguous pronoun -- only when multiple entities are recent.
        self.logger.debug("[CLARIFY] recent_entities=%r", self._recent_entities)
        if len(self._recent_entities) >= 2:
            _focus_check = self.conversation_state.detect_focus_change(request)
            _clarify = self.clarification_engine.check(
                request,
                self._recent_entities,
                self.session,
                explicit_focus=_focus_check.detected,
            )
            if _clarify is not None:
                self._pending_clarification = PendingClarification(
                    candidates=_clarify.candidates,
                    original_request=_clarify.original_request,
                    pronoun=_clarify.pronoun,
                    question=_clarify.question,
                )
                self.context.last_jarvis_response = _clarify.question
                self._post_turn(request, _clarify.question)
                return Response(success=True, message=_clarify.question)

        # Genesis-032 S3: Tag-seeding syntax -- "Some text [tag: genesis-027]"
        import re as _re_tag
        _TAG_RE = _re_tag.compile(r"^(.+?)\s*\[tag:\s*([^\]]+)\]\s*$", _re_tag.IGNORECASE)
        _tag_match = _TAG_RE.match(request.strip())
        if _tag_match:
            _tag_content = _tag_match.group(1).strip()
            _tag_label   = _tag_match.group(2).strip().lower()
            self.knowledge.store_memory(
                subject="jarvis",
                category="general",
                attribute=f"episode_{_tag_label}_{hash(_tag_content) & 0xFFFF:04x}",
                value=_tag_content,
                tags=[_tag_label],
            )
            _ack = Response(success=True, message=f"Noted, sir. Tagged as [{_tag_label}].")
            self.context.last_jarvis_response = _ack.message
            self._post_turn(request, _ack.message)
            return _ack

        # Step 3b2 -- Engineering Collaboration Approval (Genesis-040 Final)
        # Must run BEFORE memory detection and intent routing so approval
        # commands ("Approve.", "yes", "proceed") are caught here, not sent
        # to the AI. Runs alongside the follow-up check (Step 3c).
        _APPROVAL_TRIGGERS_EARLY = frozenset({
            "yes", "approve", "approved", "apply",
            "apply the changes", "apply recommended changes",
            "apply the recommended changes",
            "apply the recommended changes automatically",
            "proceed", "proceed with changes", "confirm", "go ahead",
            "yes proceed", "yes, proceed", "install", "implement it",
            "implement the changes", "make the changes",
            "i approve", "yes i approve", "approved proceed",
        })
        if (
            self.collaboration_runner.has_pending_approval()
            and request.strip().lower().rstrip("?!.") in _APPROVAL_TRIGGERS_EARLY
        ):
            # Genesis-041 Sprint-005: Route approval through ExecutionRunner
            # Extract the approved plan from the last collaboration outcome
            _last_outcome = self.collaboration_runner._last_outcome
            _exec_plan = None
            if _last_outcome and _last_outcome.report:
                _plan_dict = (
                    (_last_outcome.session.result or {}).get("execution_plan")
                    or (_last_outcome.report.engineering_review or {}).get("execution_plan")
                )
                if _plan_dict:
                    from core.engineering.execution.execution_plan import ExecutionPlan
                    _exec_plan = ExecutionPlan.from_dict(_plan_dict)

            # If we have a structured plan, execute it; otherwise show approval gate
            if _exec_plan and not _exec_plan.is_empty:
                self.collaboration_runner.clear_pending_approval()
                _exec_outcome = self.execution_runner.run(
                    description=_last_outcome.report.description if _last_outcome else request,
                    plan=_exec_plan.to_worker_plan(),
                    session_id=_last_outcome.report.session_id[:8] if _last_outcome else "",
                )
                self.context.last_jarvis_response = _exec_outcome.markdown
                self._post_turn(request, _exec_outcome.markdown)
                return Response(success=True, message=_exec_outcome.markdown)
            else:
                # No structured plan yet â€” show approval gate as before
                _approval_text = self.collaboration_runner.get_pending_approval_text()
                self.collaboration_runner.clear_pending_approval()
                self.context.last_jarvis_response = _approval_text
                self._post_turn(request, _approval_text)
                return Response(success=True, message=_approval_text)


        # Step 3b3 -- Execution Commit Gate (Genesis-041 Sprint-005)
        # After successful execution, "Commit changes." triggers GitWorker.git_commit.
        _COMMIT_TRIGGERS = frozenset({
            "commit", "commit changes", "commit the changes",
            "commit changes.", "yes commit", "commit it",
        })
        if (
            self.execution_runner.has_pending_commit()
            and request.strip().lower().rstrip("?!.") in _COMMIT_TRIGGERS
        ):
            _commit_summary = self.execution_runner.get_commit_summary_text()
            self.execution_runner.clear_pending_commit()
            _msg = _commit_summary + "\n\nCommit recorded. Type 'Push to GitHub.' to push."
            self.context.last_jarvis_response = _msg
            self._post_turn(request, _msg)
            return Response(success=True, message=_msg)

        # Step 3b4 -- Push Gate (Genesis-041 Final)
        _PUSH_TRIGGERS = frozenset({
            "push", "push changes", "push to github", "git push",
            "push it", "push now", "push the changes",
            "publish", "publish changes", "upload to github",
        })
        if (
            self.execution_runner.has_pending_push()
            and request.strip().lower().rstrip("?!.") in _PUSH_TRIGGERS
        ):
            self.execution_runner.clear_pending_push()
            # Route through git_worker.git_push via coordinator
            from core.workers.models import WorkerTask as _WTask
            _push_task = _WTask(
                task_type="git_push",
                payload={"repo_root": "."},
                requester="agent",
            )
            try:
                self.worker_coordinator.register_workflow("git_push", ["git_worker"])
            except Exception:
                pass
            _push_result = self.worker_coordinator.run(_push_task)
            self.worker_intelligence.observe(_push_result, "git_push")
            if _push_result.success:
                _worker_data = (
                    _push_result.data.get("results", {}).get("git_worker", {})
                    or _push_result.data
                )
                _branch = _worker_data.get("branch", "main")
                _msg = f"âœ… Pushed to origin/{_branch}. Genesis-041 complete, sir."
            else:
                _msg = f"Push failed: {_push_result.error}. You can push manually with 'git push'."
            self.context.last_jarvis_response = _msg
            self._post_turn(request, _msg)
            return Response(success=True, message=_msg)

        # Step 3c -- Engineering Collaboration Follow-up (Genesis-040 Final)
        # Must run BEFORE memory detection and intent routing so follow-up
        # questions ("What risks did you identify?", "Summarise the recommendations.")
        # are answered from the active collaboration session rather than being
        # intercepted by Intent=MEMORY or sent to AI fallback.
        _COLLAB_FOLLOWUP_TRIGGERS = frozenset({
            "what risks", "what were the risks", "what risk",
            "what recommendations", "show recommendations",
            "show me the recommendations", "what did you find",
            "what did you identify", "what risks did you identify",
            "what are the recommendations", "summarise", "summarize",
            "summarise the recommendations", "summarize the recommendations",
            "what was the result", "show the report", "show report",
            "what did the review say", "review results", "session summary",
            "what did you recommend", "what should we do",
            "what did claude say", "summarise claude", "summarize claude",
        })
        _req_cf = request.strip().lower().rstrip("?!.")
        _matched_trigger = next((t for t in _COLLAB_FOLLOWUP_TRIGGERS if t in _req_cf), None)
        if (
            self.collaboration_runner.has_active_session()
            and _matched_trigger is not None
        ):
            _cf_summary = self.collaboration_runner.get_session_summary()
            if _cf_summary:
                self.context.last_jarvis_response = _cf_summary
                self._post_turn(request, _cf_summary)
                return Response(success=True, message=_cf_summary)

        # Genesis-043 Fix 2: FollowUpResolver â€” must run before memory detection
        # so "tell me another one", "make it shorter", "say that again" etc.
        # are handled from session context rather than sent to AI.
        # FollowUpResolver was instantiated but never called in process() â€” this wires it.
        try:
            _followup = self.followup_resolver.resolve(request, self.session)
            if _followup.is_followup:
                self.logger.info("[G043-Fix2] FollowUp detected: type=%r context=%r",
                                 _followup.resolved_type, _followup.context_hint)
                if _followup.resolved_type == "repeat" and self.session.last_response:
                    _fu_resp = Response(success=True, message=self.session.last_response)
                    self.context.last_jarvis_response = _fu_resp.message
                    self._post_turn(request, _fu_resp.message)
                    return _fu_resp
                elif _followup.suggested_prompt and self.ai is not None:
                    with telemetry.stage("ai_manager"):
                        _fu_resp = self.ai.ask(_followup.suggested_prompt)
                    self.context.last_skill = "followup_resolver"
                    self.context.last_jarvis_response = _fu_resp.message
                    self._post_turn(request, _fu_resp.message)
                    return _fu_resp
        except Exception:
            self.logger.debug("[G043-Fix2] FollowUpResolver error â€” continuing.")

        # FIX-6B: Catch "My [group] are [names]" before Step 4 for group nouns
        # that SlotCompletionEngine doesn't recognise (e.g. "children", "kids").
        import re as _re_group_pre
        _GROUP_PRE_RE = _re_group_pre.compile(
            r"^my\s+(children|kids|sons?|daughters?|family|relatives?|friends?|colleagues?)"
            r"\s+are\s+(.+)$",
            _re_group_pre.IGNORECASE,
        )
        _group_pre_m = _GROUP_PRE_RE.match(request.strip())
        if _group_pre_m:
            _gp_noun  = _group_pre_m.group(1).lower()
            _gp_names = _group_pre_m.group(2).strip().rstrip(".")
            # Store as people names + people declaration
            _gp_attr  = "people names"
            _gp_decl  = _gp_noun  # "children", "kids" etc.
            self.knowledge.store_memory(
                subject="user", category="personal",
                attribute=_gp_attr, value=_gp_names, tags=["user_fact"],
            )
            self.knowledge.store_memory(
                subject="user", category="personal",
                attribute="people", value=_gp_decl, tags=["user_fact"],
            )
            # Also set active_topic so pronouns resolve
            self.session.set_topic(_gp_decl, raw=_gp_decl)
            self.logger.info("[FIX-6B] Group pre-store: %r â†’ %r", _gp_attr, _gp_names)
            _gp_resp = Response(success=True, message="Got it, I'll remember that.")
            self.context.last_jarvis_response = _gp_resp.message
            self._post_turn(request, _gp_resp.message)
            return _gp_resp

        # FIX-6B: Catch "My [group] are [names]" before Step 4 for group nouns
        # that SlotCompletionEngine doesn't recognise (e.g. "children", "kids").
        import re as _re_group_pre
        _GROUP_PRE_RE = _re_group_pre.compile(
            r"^my\s+(children|kids|sons?|daughters?|family|relatives?|friends?|colleagues?)"
            r"\s+are\s+(.+)$",
            _re_group_pre.IGNORECASE,
        )
        _group_pre_m = _GROUP_PRE_RE.match(request.strip())
        if _group_pre_m:
            _gp_noun  = _group_pre_m.group(1).lower()
            _gp_names = _group_pre_m.group(2).strip().rstrip(".")
            # Store as people names + people declaration
            _gp_attr  = "people names"
            _gp_decl  = _gp_noun  # "children", "kids" etc.
            self.knowledge.store_memory(
                subject="user", category="personal",
                attribute=_gp_attr, value=_gp_names, tags=["user_fact"],
            )
            self.knowledge.store_memory(
                subject="user", category="personal",
                attribute="people", value=_gp_decl, tags=["user_fact"],
            )
            # Also set active_topic so pronouns resolve
            self.session.set_topic(_gp_decl, raw=_gp_decl)
            self.logger.info("[FIX-6B] Group pre-store: %r â†’ %r", _gp_attr, _gp_names)
            _gp_resp = Response(success=True, message="Got it, I'll remember that.")
            self.context.last_jarvis_response = _gp_resp.message
            self._post_turn(request, _gp_resp.message)
            return _gp_resp

        # Step 4 -- Check for natural memory statements.
        # Genesis-025 Sprint-002: SlotCompletionEngine runs first (generic),
        # then falls back to MemoryDetector (explicit patterns).
        # SlotCompletionEngine is pure detection -- same inputs -> same output.
        with telemetry.stage("memory_detection"):
            active_topic = (
                self.session.active_topic.value
                if self.session.active_topic else ""
            )
            detection = (
                self.slot_completion.detect(request, active_topic)
                or self.memory_detector.detect_with_context(request, active_topic)
            )

            # CV-002-001: Clear stale active_topic after unsupported entity.
            # If this looks like a possession declaration but SlotCompletionEngine
            # returned None (unknown entity e.g. planes), clear active_topic so
            # the previous group does not inherit the next slot fill.
            import re as _re_cv002
            _POSS_RE = _re_cv002.compile(
                r"\bi\s+(?:have|own|possess|keep)\b|\bi(?:'ve|\s+have)\s+got\b",
                _re_cv002.IGNORECASE,
            )
            if (detection is None
                    and _POSS_RE.search(request)
                    and self.slot_completion.detect(request) is None):
                self.session.active_topic = None
                self.logger.debug(
                    "[CV-002-001] Cleared active_topic: unsupported entity declaration"
                )

        # Step 5 -- If a memory was detected, store and acknowledge.
        if detection is not None:
            response = self._handle_memory_detection(detection)
            self.context.last_skill = "memory"
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # Step 6b -- Genesis-020 S2: Resolve ambiguous references.
        resolution = None
        if self.context_resolver.needs_resolution(request):
            resolution = self.context_resolver.resolve(request)
            if resolution.resolved:
                self.logger.info(
                    "[CONTEXT] Resolved %r -> hint=%r (slot=%s, conf=%.2f)",
                    resolution.pronoun, resolution.context_hint,
                    resolution.slot_type, resolution.confidence,
                )

        # Step 7 -- Normal intent routing.
        with telemetry.stage("intent_routing"):
            intent = self.router.detect(request)
        telemetry.log_since("agent_pipeline", pipeline_start)
        response = self._route(intent, request, resolution)

        # Step 8 -- Update context.
        self.context.last_intent = intent.name if intent else None
        self.context.last_jarvis_response = response.message

        # Step 9 -- Post-turn processing.
        self._post_turn(request, response.message)

        return response

    def _post_turn(self, request: str, response_message: str) -> None:
        # Genesis-042 Sprint-003: track last turn for follow-up resolution
        # FIX-3: Use a meaningful topic hint, not the EntityGroup active_topic.
        # If the last skill was AI fallback, the conversational topic is the
        # user's request subject â€” not which group of entities is active.
        # We use last_user_message keywords as a proxy when active_topic is
        # an entity group and the response came from AI.
        try:
            _active_topic_val = self.session.active_topic.value if self.session.active_topic else ""
            _last_skill = self.context.last_skill or "unknown"
            # If AI answered and active_topic looks like an entity group declaration
            # (contains a digit or is multi-word like "2 dogs"), prefer using
            # last_intent-derived topic or a short extract from the request.
            import re as _re_topic

            # CFR-003: Internal routing/skill names that must never become
            # the user's conversational topic. When _last_skill is one of
            # these, topic extraction runs on the user's words instead, and
            # if no meaningful words are found the previous last_topic is
            # preserved rather than falling back to the skill name.
            # Centralised here so all routing mechanisms are governed by
            # one place. Add new internal skill names here as they are built.
            _INTERNAL_SKILLS = frozenset({
                'ai_fallback', 'unknown', '',
                'followup_resolver',          # follow-up routing
                'memory', 'memory_store',     # memory skill
                'system',                     # system skill
                'engineering',                # engineering skill
                'reasoning',                  # reasoning skill
            })

            _is_group_topic = bool(
                _active_topic_val
                and _re_topic.search(r'\d', _active_topic_val)
            )
            _needs_topic_extract = (
                _last_skill in _INTERNAL_SKILLS
                and (_is_group_topic or not _active_topic_val)
            )
            if _needs_topic_extract:
                _words = _re_topic.findall(r'[a-z]{3,}', self.context.last_user_message or '', _re_topic.IGNORECASE)
                _SKIP = {
                    'tell', 'give', 'make', 'what', 'where', 'when', 'why', 'how',
                    'the', 'and', 'for', 'that', 'this', 'are', 'was', 'did', 'does',
                    'about', 'another', 'more', 'one', 'say', 'said', 'again',
                    'explain', 'describe', 'show', 'list', 'can', 'could', 'would',
                    'should', 'please', 'just', 'now', 'also', 'still', 'get',
                    'let', 'think', 'know', 'use', 'try', 'help', 'need', 'want',
                    'differently', 'simpler', 'shorter', 'better', 'different',
                    'simple', 'brief', 'quickly', 'else', 'other', 'another',
                }
                _topic_words = [w for w in _words if w.lower() not in _SKIP]
                if _topic_words:
                    _conv_topic = _topic_words[0]
                else:
                    # CFR-003: No meaningful topic words found and last skill
                    # is internal — preserve existing last_topic so "Tell me
                    # another one." after a follow-up stays on "joke", not
                    # "followup_resolver". Pass "" so set_last_turn() keeps
                    # the existing _last_topic via its `topic or self._last_topic` guard.
                    _conv_topic = ""
            else:
                _conv_topic = _active_topic_val or _last_skill
            self.session.set_last_turn(
                intent=_last_skill,
                response=response_message,
                topic=_conv_topic,
            )
        except Exception:
            pass

        # Genesis-043 Runtime Integration: wire summariser
        try:
            _sum_topic = self.session.active_topic.value if self.session.active_topic else ""
            self.jarvis_state.summariser.add_turn(
                user_msg        = request,
                jarvis_response = response_message,
                topic           = _sum_topic,
                turn_number     = self.jarvis_state.current_turn,
            )
            # Rebuild abstract every 5 turns
            if self.jarvis_state.current_turn % 5 == 0:
                self.jarvis_state.summariser.build_abstract_from_state(
                    self.jarvis_state
                )
        except Exception:
            pass

        """
        Fire-and-forget post-turn processing. Errors never propagate.

        S1: ConversationObserver   -- extract facts -> KnowledgeEngine
        S2: ContextManager         -- update SessionContext working memory
        S3: Timeline               -- publish new events from extracted facts
        S4: DecisionEngine         -- apply DECISION_* events
        S5: GoalEngine             -- apply GOAL_* events
        S6: SessionSummaryEngine   -- apply all events for summary
        """
        try:
            facts = FactExtractor().extract(request)
        except Exception:
            self.logger.exception("[MEMORY] FactExtractor error.")
            facts = []

        try:
            self.conversation_observer.observe(request, response_message)
        except Exception:
            self.logger.exception("[MEMORY] ConversationObserver error.")

        turn_before = self.session.current_turn
        try:
            self.context_manager.update(request, response_message)
        except Exception:
            self.logger.exception("[CONTEXT] ContextManager error.")

        if not facts:
            return

        try:
            events_before = self.timeline.count()
            self.timeline.record_from_facts(facts, turn_before)
            new_events = self.timeline.all_events()[events_before:]

            _DECISION_TYPES = (
                EventType.DECISION_PROPOSED, EventType.DECISION_ACCEPTED,
                EventType.DECISION_SUPERSEDED, EventType.DECISION_REJECTED,
                EventType.DECISION,
            )
            _GOAL_TYPES = (
                EventType.GOAL_CREATED, EventType.GOAL_STARTED,
                EventType.GOAL_COMPLETED, EventType.GOAL_CANCELLED,
                EventType.GOAL_BLOCKED, EventType.GOAL_UNBLOCKED,
                EventType.GOAL_PRIORITY_CHANGED,
            )

            for event in new_events:
                if event.event_type in _DECISION_TYPES:
                    self.decision_engine.apply(event)
                elif event.event_type in _GOAL_TYPES:
                    self.goal_engine.apply(event)
                self.summary_engine.apply(event)
        except Exception:
            self.logger.exception("[TIMELINE] Timeline/Projection error.")

    def _handle_memory_detection(self, detection: MemoryDetection) -> Response:
        """Store a detected memory via MemorySkill and return acknowledgement."""
        self.logger.debug(
            "Memory detected -- key: %r, value: %r, confidence: %.2f",
            detection.key, detection.value, detection.confidence
        )
        if detection.is_group_declaration:
            self.session.set_topic(detection.value, raw=detection.value)
            self.logger.debug(
                "[SLOT] active_topic set to %r after group declaration",
                detection.value,
            )
            self.conversation_state.update_group(detection.value, self.session)

        # Genesis-031: enrich with temporal metadata if expression found
        temporal_metadata = None
        temporal_tags = None
        _temporal_ctx = self.temporal_parser.parse(
            self.context.last_user_message or detection.value
        )
        if _temporal_ctx and _temporal_ctx.confidence > 0:
            temporal_metadata = _temporal_ctx.to_metadata()
            temporal_tags = _temporal_ctx.to_tags()
            self.logger.info(
                "[TEMPORAL] Enriching memory: expr=%r date=%s",
                _temporal_ctx.expression, _temporal_ctx.resolved_date,
            )

        # Log to session registry
        try:
            from flask import current_app
            sr = current_app.config.get("SESSION_REGISTRY")
            if sr:
                sr.log_memory_stored(detection.key, detection.value)
        except Exception:
            pass
        with telemetry.stage("skill_manager", skill="memory_store"):
            _mem_response = self.skills.get("memory").remember(
                detection.key,
                detection.value,
                temporal_tags=temporal_tags,
                temporal_metadata=temporal_metadata,
            )

        # Genesis-043 Fix 1: Register named entity so pronouns resolve next turn.
        # Scan detection.key and detection.value for capitalised names.
        # e.g. "My son Lucas is 14" -> detection.key="son lucas", value="14"
        # We find "Lucas" and register it in EntityRegistry + update_entity.
        try:
            _STOP_WORDS = {
                "Melbourne", "Sydney", "Brisbane", "Perth", "Adelaide",
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday", "January", "February", "March",
                "April", "May", "June", "July", "August", "September",
                "October", "November", "December", "Jarvis",
            }
            # FIX-9: Also title-case the message so lowercase names are found
            _raw_msg = self.context.last_user_message or ""
            _search_text = (detection.key or "") + " " + _raw_msg + " " + _raw_msg.title()
            import re as _re_fix1_inner
            _name_candidates = _re_fix1_inner.findall(r'\b([A-Z][a-z]{1,20})\b', _search_text)
            # Skip common sentence starters that are not entity names
            _SENTENCE_STARTERS = {
                "My", "The", "A", "An", "In", "It", "He", "She", "We",
                "They", "Is", "Are", "Was", "Were", "You", "Hi", "Oh",
                "So", "But", "And", "Or", "If", "To", "Do", "Go",
                # Relationship nouns that appear before names in title-cased input
                "Son", "Daughter", "Brother", "Sister", "Father", "Mother",
                "Wife", "Husband", "Friend", "Partner", "Child", "Kid",
                "Nephew", "Niece", "Cousin", "Uncle", "Aunt", "Pet", "Dog", "Cat",
            }
            for _cand in _name_candidates:
                if (_cand not in _STOP_WORDS
                        and _cand not in _SENTENCE_STARTERS
                        and len(_cand) >= 3):
                    self.conversation_state.update_entity(_cand, self.session)
                    try:
                        self.jarvis_state.entity_registry.mention(
                            _cand,
                            turn=self.jarvis_state.current_turn,
                            display_name=_cand,
                        )
                        self.logger.info("[G043-Fix1] Entity registered after memory: %r", _cand)
                    except Exception:
                        pass
                    break  # register first found name only
        except Exception:
            pass

        return _mem_response

    def _respond_to_decision(self, decision: ConversationDecision) -> Response:
        """Translate a ConversationDecision into a user-facing Response."""
        if decision.outcome == ConversationOutcome.CONFIRMED:
            return Response(success=True, message="Understood, sir. I will proceed.")
        if decision.outcome == ConversationOutcome.DENIED:
            return Response(success=True, message="Understood, sir. I will stand by.")
        if decision.outcome == ConversationOutcome.CLARIFICATION:
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(success=True, message=f"Of course, sir. I was asking: {pending}")
            return Response(success=True, message="I apologise for the confusion, sir. Please go ahead.")
        if decision.outcome == ConversationOutcome.CONTINUATION:
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(success=True, message=f"Of course, sir. To confirm -- {pending}")
            return Response(success=True, message="Please go ahead, sir.")
        return Response(success=False, message="I'm not sure how to proceed, sir.")

    def _route(self, intent: Intent, request: str, resolution=None) -> Response:
        """Route a detected intent to the appropriate skill or AI fallback."""

        # Initialise resolved_entity so it is always defined regardless of
        # which branch is taken.
        resolved_entity = ""

        # -- Section 7.0 - Engineering Collaboration Fast-Path (CV-040-002f) --
        # Must be first: engineering requests are intercepted by GoalIntelligence,
        # Reasoning, and Recall engines before reaching Section 7.5/7.6.
        _eng_early = self.engineering_intent_detector.detect(request)
        if _eng_early.is_engineering and self.worker_manager.worker_count() > 0:
            _req_lower_e = request.lower()
            _is_review_e = any(w in _req_lower_e for w in (
                "review", "analyse", "analyze", "inspect", "audit", "architecture",
            ))
            _is_implement_e = any(w in _req_lower_e for w in (
                "add", "implement", "build", "create", "write", "develop",
                "fix", "refactor", "extend", "introduce", "need to",
            ))
            if _is_review_e or _is_implement_e:
                _cap_e = (
                    "review_architecture"
                    if _is_review_e and not _is_implement_e
                    else "implement_feature"
                )
                _cr_early = self.collaboration_runner.run(
                    description=request,
                    payload={"genesis": self._extract_genesis_number(request)},
                    capability=_cap_e,
                )
                return Response(success=True, message=_cr_early.markdown)


        # -- Section 7.0a - Approval Routing (Genesis-040 Final) --
        # If a collaboration session is awaiting approval, intercept approval
        # intent before any other routing so "apply", "approve", "yes, proceed"
        # etc. return the approval gate rather than the AI fallback.
        _APPROVAL_TRIGGERS = frozenset({
            "yes", "yes.", "approve", "approved", "apply",
            "apply the changes", "apply recommended changes",
            "apply the recommended changes", "apply the recommended changes automatically",
            "proceed", "proceed with changes", "confirm", "go ahead",
            "yes proceed", "yes, proceed", "install", "implement it",
        })
        if (
            self.collaboration_runner.has_pending_approval()
            and request.strip().lower().rstrip("?!.") in _APPROVAL_TRIGGERS
        ):
            _approval_text = self.collaboration_runner.get_pending_approval_text()
            self.collaboration_runner.clear_pending_approval()
            return Response(success=True, message=_approval_text)

        # Developer inspector commands
        req_lower = request.strip().lower()
        if req_lower in ("inspect context", "/context", "show context", "context"):
            return Response(success=True, message=self.context_inspector.inspect())
        if req_lower in ("show timeline", "/timeline", "inspect timeline", "timeline"):
            return Response(success=True, message=self.timeline_inspector.inspect())
        if req_lower in ("/decisions", "show decisions", "inspect decisions", "decisions"):
            return Response(success=True, message=self.decision_inspector.inspect())
        if req_lower in ("/goals", "show goals", "inspect goals", "goals"):
            return Response(success=True, message=self.goal_inspector.inspect())
        if req_lower in ("/summary", "show summary", "inspect summary", "summary"):
            return Response(success=True, message=self.summary_inspector.inspect())

        # Genesis-028/029: Resolve pronouns and handle property operations
        # BEFORE ConversationEngine so queries like "what does he like?"
        # are not intercepted as slot fills.

        # Genesis-029 Sprint-002: detect explicit focus change BEFORE pronoun resolution
        _focus = self.conversation_state.detect_focus_change(request)
        if _focus.detected:
            self.conversation_state.apply_focus_change(_focus, self.session)
            # Genesis-029 Sprint-003: reset recent entities to just this one
            # so subsequent pronouns don't trigger ambiguity clarification.
            if not _focus.is_group:
                self._recent_entities = [_focus.entity.title()]
            if not _focus.is_group:
                _display = _focus.entity.upper() if len(_focus.entity) <= 2 else _focus.entity.title()
                # FIX-F2: Try reverse lookup first to answer "What about Tom?"
                # in the context of "My dogs are Rex and Tom." / "Who is Rex?"
                # Reuse the same path as "Who is Rex?" for consistency.
                try:
                    from core.conversation.reverse_entity_parser import ReverseLookupRequest
                    _rl_req = ReverseLookupRequest(members=[_focus.entity])
                    _rl_res = self.contextual_recall.reverse_lookup(
                        _rl_req, self.conversation_recall
                    )
                    if _rl_res and _rl_res.found:
                        return Response(success=True, message=_rl_res.answer)
                except Exception:
                    pass
                # Fall back to property summary if no relationship found
                _props = self.property_recall.retrieve_all_properties(_focus.entity)
                if _props:
                    # JTI-001 Fix 3 (P5): use SemanticRecallEngine for natural language
                    # instead of raw 'Chase -- colour: white.' format.
                    _profile = self.semantic_recall.recall(_focus.entity, self.knowledge)
                    if _profile.found:
                        _summary = _profile.to_text()
                    else:
                        # SemanticRecallEngine found nothing — format via property formatter
                        _parts = [
                            self.property_recall._format_retrieve_response(_focus.entity, k, v)
                            for k, v in _props.items()
                        ]
                        _summary = " ".join(_parts)
                else:
                    _summary = f"Focusing on {_display}."
            else:
                _summary = f"Focusing on {_focus.entity}."
            return Response(success=True, message=_summary)

        # Resolve pronouns
        _pronoun_res = self.conversation_state.resolve_pronoun(request, self.session)
        _effective_request = (
            self.conversation_state.rewrite_with_entity(request, _pronoun_res)
            if _pronoun_res.resolved
            else request
        )

        # --- Group-property query first: "Which printer is offline?" ---
        _gq = self.property_assigner.detect_group_query(_effective_request)
        if _gq is not None:
            _all_members = self._collect_all_entity_members()
            _scan = self.property_recall.scan_group(_gq, _all_members)
            return Response(success=True, message=_scan.message)

        # --- Direct property query: "How old is Leo?" / "What does he like?" ---
        _pq = self.property_assigner.detect_query(_effective_request)
        if _pq is not None:
            _result = self.property_recall.retrieve(_pq)
            if _result.found:
                return Response(success=True, message=_result.message)
            # Not found -- fall through

        # --- Property assignment: "Lucas is 14." / "Leo likes football." ---
        # JTI-001 Fix 2 (P2): use detect_assignments() to handle conjunction
        # statements like "Lucas is 14 and Leo is 8" as two independent facts.
        _assignments = self.property_assigner.detect_assignments(_effective_request)
        if _assignments:
            _last_store = None
            for _pa in _assignments:
                _last_store = self.property_recall.store(_pa)
                # Update active entity in conversation state
                self.conversation_state.update_entity(_pa.subject.title(), self.session)
                # Genesis-029 Sprint-003: track recent entities for clarification
                _entity_name = _pa.subject.title()
                if _entity_name not in self._recent_entities:
                    self._recent_entities.append(_entity_name)
                if len(self._recent_entities) > 5:
                    self._recent_entities.pop(0)
                # Genesis-043: record entity mention in EntityRegistry
                try:
                    self.jarvis_state.entity_registry.mention(
                        _pa.subject, turn=self.jarvis_state.current_turn,
                        display_name=_pa.subject.title()
                    )
                except Exception:
                    pass
            if _last_store and _last_store.success:
                if len(_assignments) == 1:
                    return Response(success=True, message=_last_store.message)
                _names = ' and '.join(a.subject.title() for a in _assignments)
                return Response(success=True, message=f"Got it — noted for {_names}.")

        # Genesis-022: Run Conversation Engine pipeline for enriched context.
        try:
            conv_decision = self.conversation_engine.process(request)
            if conv_decision.decision_type == DecisionType.RECOVERY:
                return Response(success=True, message="Understood, I've cleared that.")
            if conv_decision.decision_type == DecisionType.SLOT_FILLED:
                slot_name  = conv_decision.payload.get("slot_name", "")
                slot_value = conv_decision.payload.get("slot_value", "")
                if slot_name and slot_value:
                    self.skills.get("memory").remember(slot_name, slot_value)
                return Response(success=True, message=f"Got it. I've noted {slot_value!r}.")
        except Exception:
            self.logger.exception("[CONV] ConversationEngine error -- continuing with intent routing.")

        # Genesis-042: System intent -- always answered locally.
        if intent == Intent.SYSTEM:
            skill = self.skills.get("system")
            if skill:
                return skill.execute(request, agent=self)
            return Response(success=True, message="Jarvis OS 0.1-alpha -- online.")

        if intent == Intent.GREETING:
            return self._execute_skill("greeting", request)

        if intent == Intent.IDENTITY:
            return self._execute_skill("identity", request)

        if intent == Intent.MEMORY:
            # Genesis-026 Sprint-003: Reverse entity lookup (member to group).
            # "Who is Rex?" / "Who are Rex and Tom?" / "What is staging?"
            reverse_request = self.reverse_entity_parser.parse(request)
            if reverse_request:
                reverse_result = self.contextual_recall.reverse_lookup(
                    reverse_request, self.conversation_recall
                )
                if reverse_result and reverse_result.found:
                    return Response(success=True, message=reverse_result.answer)

            # Genesis-026: contextual recall for anaphoric memory queries.
            # Sprint-002: ResolutionType determines answer format.
            recall_request = self.contextual_recall.resolve(request, self.session)
            if recall_request:
                from core.conversation.contextual_recall_engine import ResolutionType
                if recall_request.resolution_type == ResolutionType.IDENTITY:
                    ctx_result = self.contextual_recall.answer(
                        request, self.session, self.conversation_recall
                    )
                else:
                    ctx_result = self.conversation_recall.lookup(
                        recall_request.subject, recall_request.attribute
                    )
                if ctx_result and ctx_result.found:
                    return Response(success=True, message=ctx_result.answer)

            if self.summary_query.can_answer(request):
                result = self.summary_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            if self.goal_query.can_answer(request):
                result = self.goal_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            if self.decision_query.can_answer(request):
                result = self.decision_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            if self.timeline_query.can_answer(request):
                result = self.timeline_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            if self.conversation_recall.can_answer(request):
                recall_result = self.conversation_recall.answer(request)
                if recall_result.found:
                    return Response(success=True, message=recall_result.answer)

            # CV-002-003: For identity queries ("Who is X?") that reach this
            # point with no match, fall through to AI rather than returning
            # "I don't have information stored".
            import re as _re_cv003
            _IDENTITY_RE = _re_cv003.compile(
                r"\bwho\s+(?:is|are|was|were)\b",
                _re_cv003.IGNORECASE,
            )

            # FIX-4B: "Who are my X?" group queries match _IDENTITY_RE but
            # have a stored answer. Handle them before the generic identity pass.
            # Generic: map group nouns to KnowledgeEngine attribute keys.
            _WHO_MY_RE = _re_cv003.compile(
                r"\bwho\s+are\s+my\s+(\w+)\b", _re_cv003.IGNORECASE
            )
            _who_my_m = _WHO_MY_RE.search(request)
            if _who_my_m:
                _group_noun = _who_my_m.group(1).lower().rstrip("s")  # dogsâ†’dog, childrenâ†’children
                # Map common group nouns to attribute keys
                _GROUP_ATTR = {
                    "dog":    ("pet names", "pets"),
                    "pet":    ("pet names", "pets"),
                    "cat":    ("pet names", "pets"),
                    "animal": ("pet names", "pets"),
                    "child":  ("people names", "people"),
                    "children": ("people names", "people"),
                    "kid":    ("people names", "people"),
                    "son":    ("people names", "people"),
                    "daughter": ("people names", "people"),
                    "sibling": ("people names", "people"),
                    "friend": ("people names", "people"),
                }
                _names_attr, _decl_attr = _GROUP_ATTR.get(
                    _group_noun,
                    (f"{_group_noun} names", _group_noun + "s")
                )
                _grp_names = self.knowledge.recall_memory("user", _names_attr)
                _grp_decl  = self.knowledge.recall_memory("user", _decl_attr)
                if _grp_names and _grp_names.value:
                    _grp_noun_display = _grp_decl.value if _grp_decl else _group_noun + "s"
                    _grp_msg = f"{_grp_names.value} are your {_grp_noun_display}."
                    self.logger.info("[FIX-4B] Group recall: %r â†’ %r", _names_attr, _grp_names.value)
                    return Response(success=True, message=_grp_msg)
                # Also try the declaration alone
                if _grp_decl and _grp_decl.value:
                    return Response(success=True, message=f"You have {_grp_decl.value}.")

            if _IDENTITY_RE.search(request):
                pass  # Fall through to AI routing below
            else:
                # FIX-A: Direct KnowledgeEngine lookup before MemorySkill.execute().
                # Handles queries like "Where do I live?" / "Who are my dogs?" when
                # active_topic is None (no session context) but the fact IS stored.
                import re as _re_direct
                _req_lower_direct = request.strip().lower()
                _DIRECT_ATTR_MAP = [
                    # (pattern, attribute_key)
                    (r"\bwhere\s+do\s+i\s+live\b",          "location"),
                    (r"\bhow\s+old\s+(?:is|are|was)\s+(?:he|she|they|it)\b", "_pronoun_age"),
                    (r"\bwhat\s+(?:is|are)\s+(?:his|her|their)\s+age\b", "_pronoun_age"),
                    (r"\bwhere\s+(?:am|do)\s+i\s+(?:live|stay|reside)\b", "location"),
                    (r"\bwhere\s+(?:was|am)\s+i\s+from\b",  "location"),
                    (r"\bwhat\s+(?:is|was)\s+my\s+name\b",  "name"),
                    (r"\bwhat(?:'s|\s+is)\s+my\s+name\b",   "name"),
                    (r"\bhow\s+old\s+am\s+i\b",             "age"),
                    (r"\bwhat(?:'s|\s+is)\s+my\s+age\b",    "age"),
                    (r"\bwho\s+are\s+my\s+(?:dogs?|pets?)\b", "pet names"),
                    (r"\bwhat\s+are\s+my\s+(?:dogs?|pets?)\s+(?:called|named)\b", "pet names"),
                    (r"\bwhat\s+are\s+my\s+(?:dogs?|pets?)\s+names?\b", "pet names"),
                    (r"\bwho\s+are\s+my\s+children\b",      "people names"),
                    (r"\bwho\s+are\s+my\s+kids\b",          "people names"),
                    (r"\bwhat(?:'s|\s+is)\s+my\s+(?:job|occupation|work|profession)\b", "occupation"),
                    (r"\bwhere\s+do\s+i\s+work\b",          "occupation"),
                ]
                _direct_hit = None
                for _pat, _attr in _DIRECT_ATTR_MAP:
                    if _re_direct.search(_pat, _req_lower_direct):
                        _rec = self.knowledge.recall_memory("user", _attr)
                        if _rec is not None:
                            _msg = f"Your {_attr} is {_rec.value}."
                            # Format location naturally
                            if _attr == "location":
                                _msg = f"You live in {_rec.value}."
                            elif _attr == "name":
                                _msg = f"Your name is {_rec.value}."
                            elif _attr == "age":
                                _msg = f"You are {_rec.value}."
                            elif _attr in ("pet names", "people names"):
                                _msg = f"{_rec.value}."
                            self.logger.info("[FIX-A] Direct recall: attr=%r value=%r", _attr, _rec.value)
                            return Response(success=True, message=_msg)
                        # Also try search for group recall (pets â†’ pet names)
                        if _attr == "pet names":
                            _decl = self.knowledge.recall_memory("user", "pets")
                            _names = self.knowledge.recall_memory("user", "pet names")
                            if _names:
                                _msg = f"{_names.value} are your {_decl.value if _decl else 'pets'}."
                                return Response(success=True, message=_msg)
                        if _attr == "people names":
                            _decl2 = self.knowledge.recall_memory("user", "people")
                            _names2 = self.knowledge.recall_memory("user", "people names")
                            if _names2:
                                _msg2 = f"{_names2.value} are your {_decl2.value if _decl2 else 'people'}."
                                return Response(success=True, message=_msg2)
                        if _attr == "_pronoun_age":
                            # Resolve pronoun to entity, search KE for age
                            _age_entity = None
                            if self.session.active_person:
                                _age_entity = self.session.active_person.value
                            elif self.jarvis_state.entity_registry.most_salient(self.jarvis_state.current_turn):
                                _age_entity = self.jarvis_state.entity_registry.most_salient(self.jarvis_state.current_turn)
                            if _age_entity:
                                # Search for "[name] [property]" in personal records
                                _age_key = _age_entity.lower()
                                _age_results = self.knowledge.search_memory(_age_key, subject="user")
                                for _ar in _age_results:
                                    if _age_key in _ar.attribute.lower() and _ar.value.strip().replace(".", "").isdigit():
                                        return Response(success=True, message=f"{_age_entity} is {_ar.value}.")
                                # Also try property recall
                                from core.conversation.property_assigner import PropertyQuery
                                _pq_age = PropertyQuery(subject=_age_key, property_key="age", raw=request)
                                _pr_age = self.property_recall.retrieve(_pq_age)
                                if _pr_age.found:
                                    return Response(success=True, message=_pr_age.message)
                            else:
                                # FIX-9B: No active person â€” search all personal records for age values
                                # Find any record with a numeric value stored under a relationship key
                                # e.g. subject=user, attribute="son lucas", value="14"
                                _all_personal = self.knowledge.list_memories(subject="user", category="personal")
                                for _pr in _all_personal:
                                    if _pr.value.strip().replace(".", "").isdigit():
                                        # Extract name from attribute like "son lucas" -> "lucas"
                                        _attr_parts = _pr.attribute.split()
                                        # Need 2+ words: first=relationship, last=name
                                        # e.g. "son lucas" â†’ "Lucas"
                                        _REL_WORDS = {"son","daughter","brother","sister","father","mother","wife","husband","friend","partner","child","kid","nephew","niece","cousin","uncle","aunt"}
                                        if len(_attr_parts) >= 2 and _attr_parts[0].lower() in _REL_WORDS:
                                            _name_part = _attr_parts[-1].title()
                                        else:
                                            _name_part = None
                                        if _name_part and len(_name_part) >= 3:
                                            return Response(success=True, message=f"{_name_part} is {_pr.value}.")
                        break

                response = self._execute_skill("memory", request)

                if response.data and response.data.get("memory_miss"):
                    reasoned = self.skills.get("reasoning").infer_attribute(
                        response.data.get("attribute", "")
                    )
                    if reasoned is not None:
                        return reasoned

                return response

        if intent == Intent.REASONING:
            _why_triggers = frozenset({
                "why", "why?", "how so", "how so?",
                "what do you mean", "what do you mean?",
                "how do you know", "how do you know that",
            })
            req_norm = request.strip().lower().rstrip("?.,!")
            if req_norm in _why_triggers:
                last_response = self.context.last_jarvis_response
                if last_response:
                    if req_norm in {"how do you know", "how do you know that"}:
                        return Response(
                            success=True,
                            message=f"You told me that earlier, sir. {last_response}"
                        )
                    return Response(success=True, message=f"I said: {last_response}")
            return self._execute_skill("reasoning", request)

        if intent == Intent.TOOL:
            return self._execute_skill("tool", request)

        if intent == Intent.EXIT:
            return self._execute_skill("exit", request)

        if intent == Intent.ENGINEERING:
            return self._execute_skill("engineering", request)

        # ----------------------------------------------------------------
        # Conversation Resolution Phase (Genesis-024 Sprint-002)
        # ----------------------------------------------------------------

        # 1. Reference resolution
        # CV-002-002: Skip this block when ContextualRecallEngine can answer
        # the query using session context.
        _ctxrecall_can_answer = self.contextual_recall.can_answer(request, self.session)
        if (resolution and resolution.resolved and resolution.context_hint
                and not _ctxrecall_can_answer):
            resolved_hint = resolution.context_hint
            rec = self.knowledge.recall_memory("user", resolved_hint)
            if rec is None:
                results = self.knowledge.search_memory(resolved_hint, subject="user")
                canonical = [r for r in results if "derived" not in r.tags]
                if canonical:
                    rec = canonical[0]
            if rec is not None:
                return Response(
                    success=True,
                    message=f"Your {rec.attribute} is {rec.value}, sir."
                )

        # 2-3. Recent conversation
        recent_triggers = frozenset({
            "why", "why?", "how so", "how so?", "really", "really?",
            "what did you just say", "what did you say",
            "what did i just tell you", "what did i say",
            "what was that", "repeat that", "say that again",
            "what do you mean", "what do you mean?",
            "what did i mean", "what did i mean?",
            "who told you", "who told you that", "who told you that?",
            "how do you know", "how do you know that", "how do you know that?",
            "where did you get that", "where did that come from",
        })
        req_stripped = request.strip().lower().rstrip("?.,!")
        if req_stripped in recent_triggers or request.strip().lower() in recent_triggers:
            last_response = self.context.last_jarvis_response
            last_message  = self.context.last_user_message

            if req_stripped in {"why", "how so", "really", "what do you mean"}:
                if last_response:
                    return Response(success=True, message=f"I said: {last_response}")

            if req_stripped in {
                "who told you", "who told you that", "who told you that?",
                "how do you know", "how do you know that", "how do you know that?",
                "where did you get that", "where did that come from",
            }:
                if last_response:
                    return Response(
                        success=True,
                        message=f"You told me that earlier, sir. {last_response}"
                    )
                return Response(
                    success=True,
                    message="You told me, sir. I store what you share with me."
                )

            if req_stripped in {
                "what did i just tell you", "what did i say",
                "what was that", "what did i mean",
            }:
                if last_message:
                    return Response(
                        success=True,
                        message=f"You just said: \"{last_message}\", sir."
                    )

        # 4. Session context
        if self.session.active_project or self.session.active_person:
            ctx_triggers = frozenset({
                "what project", "which project", "what are we working on",
                "who is that", "who was that", "who are they",
            })
            if any(t in request.lower() for t in ctx_triggers):
                parts = []
                if self.session.active_project:
                    parts.append(f"the current project is {self.session.active_project.value}")
                if self.session.active_person:
                    parts.append(f"the active person is {self.session.active_person.value}")
                if parts:
                    return Response(
                        success=True,
                        message=f"From context: {', '.join(parts)}, sir."
                    )

        # Genesis-026 Sprint-003: Reverse entity lookup (member to group).
        reverse_request = self.reverse_entity_parser.parse(request)
        if reverse_request:
            reverse_result = self.contextual_recall.reverse_lookup(
                reverse_request, self.conversation_recall
            )
            if reverse_result and reverse_result.found:
                return Response(success=True, message=reverse_result.answer)

        # 5. Conversation recall and timeline.
        recall_request = self.contextual_recall.resolve(request, self.session)
        if recall_request:
            from core.conversation.contextual_recall_engine import ResolutionType
            if recall_request.resolution_type == ResolutionType.IDENTITY:
                ctx_result = self.contextual_recall.answer(
                    request, self.session, self.conversation_recall
                )
            else:
                ctx_result = self.conversation_recall.lookup(
                    recall_request.subject, recall_request.attribute
                )
            if ctx_result and ctx_result.found:
                return Response(success=True, message=ctx_result.answer)

        resolved_entity = (
            resolution.context_hint
            if resolution and resolution.resolved and resolution.context_hint
            else ""
        )
        if self.conversation_recall.can_answer(request) or resolved_entity:
            recall_result = self.conversation_recall.answer(request, resolved_entity)
            if recall_result.found:
                return Response(success=True, message=recall_result.answer)

        if self.timeline_query.can_answer(request):
            result = self.timeline_query.answer(request)
            if result.answered:
                return Response(success=True, message=result.answer)

        # 6. Knowledge lookup
        if resolution and resolution.resolved and resolution.context_hint:
            results = self.knowledge.search_memory(resolution.context_hint)
            canonical = [r for r in results if "derived" not in r.tags]
            if canonical:
                r = canonical[0]
                return Response(
                    success=True,
                    message=f"Regarding {resolution.context_hint}: "
                            f"{r.attribute} is {r.value}, sir."
                )


        # â”€â”€ Section 7.7 â€” Goal & Task Intelligence (Genesis-033 Sprint-002) â”€â”€â”€â”€
        # -- Section 7.6 - Engineering Collaboration Fast-Path (CV-040-002) --
        # Must run before GoalIntelligenceEngine which intercepts "I need to add X".
        _eng_fast = self.engineering_intent_detector.detect(request)
        if _eng_fast.is_engineering and self.worker_manager.worker_count() > 0:
            _req_lower_f = request.lower()
            _is_review_f = any(w in _req_lower_f for w in (
                "review", "analyse", "analyze", "inspect", "audit", "architecture"
            ))
            _is_implement_f = any(w in _req_lower_f for w in (
                "add", "implement", "build", "create", "write", "develop",
                "fix", "refactor", "extend", "introduce", "need to",
            ))
            if _is_review_f or _is_implement_f:
                _cap_f = (
                    "review_architecture"
                    if _is_review_f and not _is_implement_f
                    else "implement_feature"
                )
                _cr_fast = self.collaboration_runner.run(
                    description=request,
                    payload={"genesis": self._extract_genesis_number(request)},
                    capability=_cap_f,
                )
                return Response(success=True, message=_cr_fast.markdown)

        if self.goal_intelligence.can_answer(request):
            _gi_response = self.goal_intelligence.process(request)
            if _gi_response:
                return Response(success=True, message=_gi_response)
        # Genesis-032 Sprint-003: Episodic recall -- "What happened during Genesis-027?"
        _eq = self.episodic_memory.parse_query(request)
        if _eq is not None:
            _es = self.episodic_memory.recall(_eq)
            return Response(success=True, message=self.episodic_memory.format_response(_es))

        # Genesis-032 Sprint-002: Relationship recall
        _rq = self.relationship_recall.detect_query(request)
        if _rq is not None:
            _ra = self.relationship_recall.answer(_rq, self.knowledge)
            if _ra.found:
                return Response(success=True, message=_ra.answer)

        # Genesis-032: Semantic recall -- "Tell me everything about Leo."
        _sq = self.semantic_recall.detect_query(request)
        if _sq is not None:
            _profile = self.semantic_recall.recall(_sq, self.knowledge)
            return Response(success=True, message=_profile.to_text())

        # Genesis-031: Temporal recall -- "When did I start my job?"
        _tq = self.temporal_recall.detect_query(request)
        if _tq is not None:
            _ta = self.temporal_recall.answer(_tq, self.knowledge)
            if _ta.found:
                return Response(success=True, message=_ta.answer)
            # Not found -- fall through to AI

        # 7. Reasoning
        reasoned = self.skills.get("reasoning").infer_attribute(
            request.strip()
        ) if request.strip() else None
        if reasoned is not None:
            return reasoned










        # â”€â”€ Section 7.46 â€“ Engineering Collaboration Runner (Genesis-040 Sprint-002) â”€â”€
        if self.collaboration_runner.can_handle(request):
            _cr_outcome = self.collaboration_runner.run(
                description=request,
                payload={"genesis": self._extract_genesis_number(request)},
            )
            return Response(success=True, message=_cr_outcome.markdown)

        # â”€â”€ Section 7.38 â€” Worker Intelligence (Genesis-039 Sprint-001) â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.worker_intelligence.can_handle(request):
            _wi_response = self.worker_intelligence.handle(request)
            if _wi_response:
                return Response(success=True, message=_wi_response)

        # â”€â”€ Section 7.39 â€” Worker Collaboration Engine (Genesis-038 Sprint-001) â”€
        if self.collaboration_engine.can_handle(request):
            _wce_response = self.collaboration_engine.handle(request)
            if _wce_response:
                return Response(success=True, message=_wce_response)

        # â”€â”€ Section 7.40 â€” Planning Engine (Genesis-037 Sprint-001) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.planning_engine.can_handle(request):
            _pe_plan = self.planning_engine.handle(request)
            if _pe_plan:
                return Response(success=True, message=_pe_plan)

        # â”€â”€ Section 7.41 â€” Decision Engine (Genesis-036 Sprint-001) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.decision_engine.can_handle(request):
            _de_response = self.decision_engine.handle(request)
            if _de_response:
                return Response(success=True, message=_de_response)

        # â”€â”€ Section 7.42 â€” Executive Dashboard (Genesis-035 Sprint-002) â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.executive_dashboard.can_handle(request):
            _ed_response = self.executive_dashboard.handle(request)
            if _ed_response:
                return Response(success=True, message=_ed_response)

        # â”€â”€ Section 7.43 â€” Progress Engine (Genesis-035 Sprint-001) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.progress_engine.can_handle(request):
            _pe_response = self.progress_engine.handle(request)
            if _pe_response:
                return Response(success=True, message=_pe_response)

        # â”€â”€ Section 7.44 â€” Engineering Lifecycle Manager (Genesis-034 Sprint-001) â”€
        if self.lifecycle_manager.can_handle(request):
            _lc_response = self.lifecycle_manager.handle(
                request,
                worker_coordinator=self.worker_coordinator,
                task_planner=self.task_planner,
            )
            if _lc_response:
                return Response(success=True, message=_lc_response)

        # â”€â”€ Section 7.45 â€” Review routing via TaskPlanner (Genesis-033 Integration) â”€â”€
        # EngineeringIntentDetector does not cover review requests (by design â€”
        # it would break threshold calibration). TaskPlanner's capability signals
        # handle review detection instead. Check the planner first.
        _review_caps = self.task_planner.capabilities_for(request)
        if "run_engineering_review" in _review_caps and self.worker_manager.worker_count() > 0:
            _review_task = WorkerTask(
                task_type="run_engineering_review",
                payload={
                    "description": request,
                    "genesis": self._extract_genesis_number(request),
                },
                requester="agent",
            )
            _review_result = self.worker_coordinator.run(_review_task)
            self.worker_intelligence.observe(_review_result, 'run_engineering_review')
            if _review_result.success:
                _worker_data = (
                    _review_result.data
                    .get("results", {})
                    .get("engineering_review_worker", {})
                )
                _md = _worker_data.get("markdown", "")
                if _md:
                    return Response(success=True, message=_md)
            return Response(
                success=False,
                message=f"Engineering review failed: {_review_result.error}",
            )

        # 7.5 Engineering intent routing (Genesis-027 Sprint-004)
        # CV-040-002: natural language engineering requests (implement/review/fix)
        # are routed through CollaborationRunner so they enter the full
        # Genesis-040 pipeline: AI worker â†’ engineering review â†’ approval gate.
        _eng_intent = self.engineering_intent_detector.detect(request)
        if _eng_intent.is_engineering and self.worker_manager.worker_count() > 0:
            _caps = self.task_planner.capabilities_for(request)
            # Map TaskPlanner capability names to ClaudeAIWorker capability names
            _cap_map = {
                "plan_implementation": "implement_feature",
                "analyse_session":     "review_architecture",
                "run_tests":           "write_tests",
            }
            # Also detect review_architecture from signals directly
            _req_lower = request.lower()
            _is_review = any(w in _req_lower for w in ("review", "analyse", "analyze", "inspect", "architecture"))
            _is_implement = any(w in _req_lower for w in ("add", "implement", "build", "create", "write", "develop", "fix", "refactor"))
            _collab_caps = [_cap_map[c] for c in _caps if c in _cap_map]
            if not _collab_caps and (_is_implement or _is_review):
                _collab_caps = ["review_architecture" if _is_review and not _is_implement else "implement_feature"]
            if _collab_caps:
                # Route through CollaborationRunner (Genesis-040 pipeline)
                _capability = "review_architecture" if _is_review and not _is_implement else _collab_caps[0]
                _cr_outcome = self.collaboration_runner.run(
                    description=request,
                    payload={"genesis": self._extract_genesis_number(request)},
                    capability=_capability,
                )
                return Response(success=True, message=_cr_outcome.markdown)

            # Fallback: non-AI capabilities (debug, run_tests) use old path
            _plan = self.task_planner.plan(
                request,
                payload={
                    "description": request,
                    "log_lines": [],
                    "paths": ["tests/"],
                    "context": "",
                },
            )
            if not _plan.is_empty:
                _wf_name = f"dynamic_{id(_plan)}"
                _worker_names = [t.requester for t in _plan.tasks]
                self.worker_coordinator.register_workflow(_wf_name, _worker_names)
                _wf_task = WorkerTask(
                    task_type=_wf_name,
                    payload=dict(_plan.tasks[0].payload),
                    requester="agent",
                )
                _wf_result = self.worker_coordinator.run(_wf_task)
                self.worker_intelligence.observe(_wf_result, _plan.tasks[0].task_type if _plan.tasks else '')
                if _wf_result.success:
                    _steps = _wf_result.data.get("workers_executed", [])
                    _n = len(_steps)
                    _msg = (
                        f"I've reviewed your request and coordinated {_n} "
                        f"specialist worker" + ("s" if _n != 1 else "") +
                        " to handle it. The plan is ready for your review, sir."
                    )
                    return Response(success=True, message=_msg)

        # 8. AI fallback
        if self.ai is not None:
            self.context.last_skill = "ai_fallback"
            ai_request = request
            if resolution and resolution.resolved:
                ai_request = (
                    f"{request} "
                    f"[Context: {resolution.pronoun} refers to "
                    f"{resolution.context_hint}]"
                )
            with telemetry.stage("ai_manager"):
                return self.ai.ask(ai_request)

        self.context.last_skill = None
        return Response(
            success=False,
            message="I'm still learning, but I'll be able to help with that soon."
        )


    def _extract_genesis_number(self, request: str) -> str:
        """Extract a genesis number string from a request e.g. 'Genesis-040' -> '040'."""
        import re as _re
        m = _re.search(r"genesis[-_]?(\d{3})", request, _re.IGNORECASE)
        return m.group(1) if m else ""
    def _collect_all_entity_members(self) -> list[str]:
        """
        Collect all known entity member names from KnowledgeEngine.

        Searches group slot records for names and entity_property subjects.
        Used by scan_group() for "Which printer is offline?" style queries.
        """
        import re as _re
        members: list[str] = []

        # Pull names from group slot records
        slot_records = self.knowledge.search_memory("group_slot", limit=50)
        for r in slot_records:
            if "names" in r.attribute:
                parts = _re.split(
                    r"\s*,\s*(?:and\s+)?|\s+and\s+",
                    r.value,
                    flags=_re.IGNORECASE,
                )
                for p in parts:
                    name = p.strip().rstrip(".")
                    if name and name not in members:
                        members.append(name)

        # Also include subjects from entity_property records
        prop_records = self.knowledge.list_memories(category="entity_property")
        for r in prop_records:
            if r.subject not in [m.lower() for m in members]:
                members.append(r.subject)

        return members

    def _execute_skill(self, name: str, request: str) -> Response:
        """Execute a skill with telemetry."""
        self.context.last_skill = name
        with telemetry.stage("skill_manager", skill=name):
            return self.skills.execute(name, request)
