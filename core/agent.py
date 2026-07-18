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


class Agent:
    """
    The central decision maker for Jarvis.

    Owns one each of:
        ConversationContext         — current conversation state
        ConversationIntelligence    — message classification
        ConversationBehaviour       — pending interaction handling
        MemoryDetector              — natural memory statement detection
        ConversationObserver        — automatic fact extraction (S1)
        ConversationRecall          — contextual/temporal recall (S1)
        SessionContext              — in-memory working memory (S2)
        ContextManager              — updates working memory each turn (S2)
        ContextResolver             — resolves pronouns/references (S2)
        ContextInspector            — developer context snapshot (S2)
        ConversationTimeline        — append-only event history (S3)
        TimelineQueryEngine         — answers history questions (S3)
        TimelineInspector           — developer timeline snapshot (S3)
        DecisionEngine              — records and explains decisions (S4)
        DecisionQueryEngine         — answers decision questions (S4)
        DecisionInspector           — developer decision snapshot (S4)
        GoalEngine                  — tracks goals as Projection (S5)
        GoalQueryEngine             — answers goal questions (S5)
        GoalInspector               — developer goal snapshot (S5)
        SessionSummaryEngine        — deterministic session summary (S6)
        SessionSummaryQueryEngine   — answers session questions (S6)
        SessionSummaryInspector     — developer summary snapshot (S6)

    Args:
        ai: Optional AI provider. Used as fallback when no intent is matched.
    """

    def __init__(self, ai=None):
        self.logger = get_logger()

        # Core services
        self.router = IntentRouter()
        # Genesis-012: persistent structured memory.
        self.knowledge = KnowledgeEngine()
        # Genesis-013: the Reasoning Engine consumes the Knowledge
        # Engine read-only. Knowledge remembers; reasoning thinks.
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

        # Genesis-020 Sprint-001: Conversation Memory
        self.conversation_observer = ConversationObserver(self.knowledge)
        self.conversation_recall = ConversationRecall(self.knowledge)

        # Genesis-020 Sprint-002: Active Conversation Context
        # SessionContext is the shared Worker workspace.
        self.session = SessionContext()
        self.context_manager = ContextManager(self.session)
        self.context_resolver = ContextResolver(self.session)
        self.context_inspector = ContextInspector(self.session)

        # Genesis-020 Sprint-003: Conversation Timeline
        # Append-only historical record. Source of truth for replay.
        self.timeline = ConversationTimeline()
        self.timeline_query = TimelineQueryEngine(self.timeline)
        self.timeline_inspector = TimelineInspector(self.timeline)

        # Genesis-020 Sprint-004: Decision Engine (Projection over Timeline)
        self.decision_engine = DecisionEngine()
        self.decision_query = DecisionQueryEngine(self.decision_engine)
        self.decision_inspector = DecisionInspector(self.decision_engine)

        # Genesis-020 Sprint-005: Goal Engine (Projection over Timeline)
        self.goal_engine = GoalEngine()
        self.goal_query = GoalQueryEngine(self.goal_engine)
        self.goal_inspector = GoalInspector(self.goal_engine)

        # Genesis-020 Sprint-006: Session Summary Engine (Projection over Timeline)
        self.summary_engine = SessionSummaryEngine()
        self.summary_query = SessionSummaryQueryEngine(self.summary_engine)
        self.summary_inspector = SessionSummaryInspector(self.summary_engine)

    def process(self, request: str, token=None) -> Response:
        """
        Process a user request.

        Args:
            request: The user's message.
            token:   Opaque conversation-ownership context supplied by
                     JarvisCore. The Agent never inspects it and never
                     decides whether a response is stale — that is the
                     Conversation layer's job.

        Flow:
            1.  Classify via ConversationIntelligence.
            2.  Evaluate for pending interactions via ConversationBehaviour.
            3.  If handled, translate ConversationDecision to Response.
            4.  Check for natural memory statements via MemoryDetector.
            5.  If detected, store via MemorySkill and acknowledge.
            6.  Resolve ambiguous references via ContextResolver (S2).
            7.  Proceed with normal intent routing.
            8.  Update ConversationContext.
            9.  Post-turn: memory, context, timeline, decisions, goals, summary.
        """

        self.logger.info("Request received: %s", request)
        pipeline_start = time.perf_counter()
        self.context.last_user_message = request

        # Step 1 — Classify.
        with telemetry.stage("classification"):
            category = self.intelligence.classify(request, self.context)
        self.logger.debug(f"Message category: {category.name}")

        # Step 2 — Evaluate for pending interaction.
        with telemetry.stage("behaviour"):
            decision = self.behaviour.handle(category, self.context)

        # Step 3 — If handled, translate decision to Response.
        if decision is not None and decision.handled:
            response = self._respond_to_decision(decision)
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # Step 4 — Check for natural memory statements.
        with telemetry.stage("memory_detection"):
            detection = self.memory_detector.detect(request)

        # Step 5 — If a memory was detected, store and acknowledge.
        if detection is not None:
            response = self._handle_memory_detection(detection)
            self.context.last_skill = "memory"
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # Step 6 — Genesis-020 S2: Resolve ambiguous references.
        # Original request is NEVER rewritten. context_hint attached only.
        resolution = None
        if self.context_resolver.needs_resolution(request):
            resolution = self.context_resolver.resolve(request)
            if resolution.resolved:
                self.logger.info(
                    "[CONTEXT] Resolved %r → hint=%r (slot=%s, conf=%.2f)",
                    resolution.pronoun, resolution.context_hint,
                    resolution.slot_type, resolution.confidence,
                )

        # Step 7 — Normal intent routing.
        with telemetry.stage("intent_routing"):
            intent = self.router.detect(request)
        telemetry.log_since("agent_pipeline", pipeline_start)
        response = self._route(intent, request, resolution)

        # Step 8 — Update context.
        self.context.last_intent = intent.name if intent else None
        self.context.last_jarvis_response = response.message

        # Step 9 — Post-turn processing.
        self._post_turn(request, response.message)

        return response

    def _post_turn(self, request: str, response_message: str) -> None:
        """
        Fire-and-forget post-turn processing. Errors never propagate.

        Performance fix (Genesis-020 regression):
            - FactExtractor runs exactly ONCE per turn (not twice).
            - turn captured BEFORE context_manager.update() increments it.
            - New events identified by index slice (O(1)) not full scan.
            - All imports at module level — no lazy imports inside the loop.

        S1: ConversationObserver   — extract facts → KnowledgeEngine
        S2: ContextManager         — update SessionContext working memory
        S3: Timeline               — publish new events from extracted facts
        S4: DecisionEngine         — apply DECISION_* events
        S5: GoalEngine             — apply GOAL_* events
        S6: SessionSummaryEngine   — apply all events for summary
        """
        # Extract facts exactly once — shared across all subsystems.
        try:
            facts = FactExtractor().extract(request)
        except Exception:
            self.logger.exception("[MEMORY] FactExtractor error.")
            facts = []

        # S1: Store facts in KnowledgeEngine via observer.
        # Pass facts directly to avoid second extraction inside observe().
        try:
            self.conversation_observer.observe(request, response_message)
        except Exception:
            self.logger.exception("[MEMORY] ConversationObserver error.")

        # S2: Update working memory. Capture turn BEFORE increment.
        turn_before = self.session.current_turn
        try:
            self.context_manager.update(request, response_message)
        except Exception:
            self.logger.exception("[CONTEXT] ContextManager error.")

        # S3-S6: Publish facts to Timeline, then route new events to projections.
        if not facts:
            return

        try:
            # Snapshot timeline length before recording new events.
            events_before = self.timeline.count()
            self.timeline.record_from_facts(facts, turn_before)

            # Identify only the NEW events added this turn (O(1) slice).
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
                if event.event_type in _DECISION_TYPES:      # S4
                    self.decision_engine.apply(event)
                elif event.event_type in _GOAL_TYPES:         # S5
                    self.goal_engine.apply(event)
                self.summary_engine.apply(event)              # S6: all events
        except Exception:
            self.logger.exception("[TIMELINE] Timeline/Projection error.")

    def _handle_memory_detection(self, detection: MemoryDetection) -> Response:
        """Store a detected memory via MemorySkill and return acknowledgement."""
        self.logger.debug(
            "Memory detected — key: %r, value: %r, confidence: %.2f",
            detection.key, detection.value, detection.confidence
        )
        with telemetry.stage("skill_manager", skill="memory_store"):
            return self.skills.get("memory").remember(detection.key, detection.value)

    def _respond_to_decision(self, decision: ConversationDecision) -> Response:
        """Translate a ConversationDecision into a user-facing Response."""
        if decision.outcome == ConversationOutcome.CONFIRMED:
            self.logger.debug("Responding to CONFIRMED decision.")
            return Response(success=True, message="Understood, sir. I will proceed.")
        if decision.outcome == ConversationOutcome.DENIED:
            self.logger.debug("Responding to DENIED decision.")
            return Response(success=True, message="Understood, sir. I will stand by.")
        if decision.outcome == ConversationOutcome.CLARIFICATION:
            self.logger.debug("Responding to CLARIFICATION decision.")
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(success=True, message=f"Of course, sir. I was asking: {pending}")
            return Response(success=True, message="I apologise for the confusion, sir. Please go ahead.")
        if decision.outcome == ConversationOutcome.CONTINUATION:
            self.logger.debug("Responding to CONTINUATION decision.")
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(success=True, message=f"Of course, sir. To confirm — {pending}")
            return Response(success=True, message="Please go ahead, sir.")
        return Response(success=False, message="I'm not sure how to proceed, sir.")

    def _route(self, intent: Intent, request: str, resolution=None) -> Response:
        """Route a detected intent to the appropriate skill or AI fallback."""

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

        if intent == Intent.GREETING:
            return self._execute_skill("greeting", request)

        if intent == Intent.IDENTITY:
            return self._execute_skill("identity", request)

        if intent == Intent.MEMORY:
            # S6: Try session summary query first.
            if self.summary_query.can_answer(request):
                result = self.summary_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            # S5: Try goal query.
            if self.goal_query.can_answer(request):
                result = self.goal_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            # S4: Try decision query.
            if self.decision_query.can_answer(request):
                result = self.decision_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            # S3: Try timeline query.
            if self.timeline_query.can_answer(request):
                result = self.timeline_query.answer(request)
                if result.answered:
                    return Response(success=True, message=result.answer)

            # S1: Try conversational recall.
            if self.conversation_recall.can_answer(request):
                recall_result = self.conversation_recall.answer(request)
                if recall_result.found:
                    return Response(success=True, message=recall_result.answer)

            response = self._execute_skill("memory", request)

            # Genesis-013: Memory <-> Reasoning escalation.
            if response.data and response.data.get("memory_miss"):
                reasoned = self.skills.get("reasoning").infer_attribute(
                    response.data.get("attribute", "")
                )
                if reasoned is not None:
                    return reasoned

            return response

        if intent == Intent.REASONING:
            return self._execute_skill("reasoning", request)

        if intent == Intent.TOOL:
            return self._execute_skill("tool", request)

        if intent == Intent.EXIT:
            return self._execute_skill("exit", request)

        # Genesis-019.5 — Engineering Academy routing.
        if intent == Intent.ENGINEERING:
            return self._execute_skill("engineering", request)

        # AI fallback — preserved unchanged.
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

    def _execute_skill(self, name: str, request: str) -> Response:
        """Execute a skill with telemetry."""
        self.context.last_skill = name
        with telemetry.stage("skill_manager", skill=name):
            return self.skills.execute(name, request)