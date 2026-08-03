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

from core.conversation.context import ConversationContext
from core.conversation.intelligence import ConversationIntelligence
from core.conversation.behaviour import ConversationBehaviour
from core.conversation.decision import ConversationDecision, ConversationOutcome
from core.conversation.memory_detector import MemoryDetector
from core.conversation.memory_detection import MemoryDetection
from core.conversation.conversation_observer import ConversationObserver  # Genesis-020 S1
from core.conversation.conversation_recall import ConversationRecall      # Genesis-020 S1
from core.conversation.session_context import SessionContext              # Genesis-020 S2
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
from core.episodic_memory_engine import EpisodicMemoryEngine                     # Genesis-032 S3


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

        # Genesis-020 Sprint-001: Conversation Memory
        self.conversation_observer = ConversationObserver(self.knowledge)
        self.conversation_recall = ConversationRecall(self.knowledge)

        # Genesis-020 Sprint-002: Active Conversation Context
        self.session = SessionContext()
        self.context_manager = ContextManager(self.session)
        self.context_resolver = ContextResolver(self.session)
        self.context_inspector = ContextInspector(self.session)

        # Genesis-020 Sprint-003: Conversation Timeline
        self.timeline = ConversationTimeline()
        self.timeline_query = TimelineQueryEngine(self.timeline)
        self.timeline_inspector = TimelineInspector(self.timeline)

        # Genesis-020 Sprint-004: Decision Engine
        self.decision_engine = DecisionEngine()
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

        # Genesis-022: Conversation Engine
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
            "suite_runner_worker", lambda deps: SuiteRunnerWorker()
        )

        # Register workers via factory (single creation path)
        self.worker_manager.register(self.worker_factory.create("debug_worker"))
        self.worker_manager.register(self.worker_factory.create("suite_runner_worker"))
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

        # Genesis-027 Sprint-004: TaskPlanner + EngineeringIntentDetector
        self.task_planner = TaskPlanner(self.worker_manager)
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

        with telemetry.stage("skill_manager", skill="memory_store"):
            return self.skills.get("memory").remember(
                detection.key,
                detection.value,
                temporal_tags=temporal_tags,
                temporal_metadata=temporal_metadata,
            )

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
                _props = self.property_recall.retrieve_all_properties(_focus.entity)
                _display = _focus.entity.upper() if len(_focus.entity) <= 2 else _focus.entity.title()
                if _props:
                    _parts = [f"{k}: {v}" for k, v in _props.items()]
                    _summary = f"{_display} -- {', '.join(_parts)}."
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
        _pa = self.property_assigner.detect_assignment(_effective_request)
        if _pa is not None:
            _store = self.property_recall.store(_pa)
            # Update active entity in conversation state
            self.conversation_state.update_entity(_pa.subject.title(), self.session)
            # Genesis-029 Sprint-003: track recent entities for clarification
            _entity_name = _pa.subject.title()
            if _entity_name not in self._recent_entities:
                self._recent_entities.append(_entity_name)
            if len(self._recent_entities) > 5:
                self._recent_entities.pop(0)
            if _store.success:
                return Response(success=True, message=_store.message)

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
            if _IDENTITY_RE.search(request):
                pass  # Fall through to AI routing below
            else:
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

        # 7.5 Engineering intent routing (Genesis-027 Sprint-004)
        _eng_intent = self.engineering_intent_detector.detect(request)
        if _eng_intent.is_engineering and self.worker_manager.worker_count() > 0:
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
