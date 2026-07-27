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


class Agent:
    """
    The central decision maker for Jarvis.

    Owns one each of:
        ConversationContext         â€” current conversation state
        ConversationIntelligence    â€” message classification
        ConversationBehaviour       â€” pending interaction handling
        MemoryDetector              â€” natural memory statement detection
        SlotCompletionEngine        â€” generic slot completion (Genesis-025)
        ConversationObserver        â€” automatic fact extraction (S1)
        ConversationRecall          â€” contextual/temporal recall (S1)
        SessionContext              â€” in-memory working memory (S2)
        ContextManager              â€” updates working memory each turn (S2)
        ContextResolver             â€” resolves pronouns/references (S2)
        ContextInspector            â€” developer context snapshot (S2)
        ConversationTimeline        â€” append-only event history (S3)
        TimelineQueryEngine         â€” answers history questions (S3)
        TimelineInspector           â€” developer timeline snapshot (S3)
        DecisionEngine              â€” records and explains decisions (S4)
        DecisionQueryEngine         â€” answers decision questions (S4)
        DecisionInspector           â€” developer decision snapshot (S4)
        GoalEngine                  â€” tracks goals as Projection (S5)
        GoalQueryEngine             â€” answers goal questions (S5)
        GoalInspector               â€” developer goal snapshot (S5)
        SessionSummaryEngine        â€” deterministic session summary (S6)
        SessionSummaryQueryEngine   â€” answers session questions (S6)
        SessionSummaryInspector     â€” developer summary snapshot (S6)

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

    def process(self, request: str, token=None) -> Response:
        """
        Process a user request.

        Args:
            request: The user's message.
            token:   Opaque conversation-ownership context supplied by
                     JarvisCore. The Agent never inspects it and never
                     decides whether a response is stale â€” that is the
                     Conversation layer's job.

        Flow:
            1.  Classify via ConversationIntelligence.
            2.  Evaluate for pending interactions via ConversationBehaviour.
            3.  If handled, translate ConversationDecision to Response.
            4.  Check for memory statements via SlotCompletionEngine (generic)
                then MemoryDetector (explicit patterns) â€” Genesis-025.
            5.  If detected, store via MemorySkill and acknowledge.
            6.  Resolve ambiguous references via ContextResolver (S2).
            7.  Proceed with normal intent routing.
            8.  Update ConversationContext.
            9.  Post-turn: memory, context, timeline, decisions, goals, summary.
        """

        self.logger.info("Request received: %s", request)
        pipeline_start = time.perf_counter()
        self.context.last_user_message = request

        # Step 1 â€” Classify.
        with telemetry.stage("classification"):
            category = self.intelligence.classify(request, self.context)
        self.logger.debug(f"Message category: {category.name}")

        # Step 2 â€” Evaluate for pending interaction.
        with telemetry.stage("behaviour"):
            decision = self.behaviour.handle(category, self.context)

        # Step 3 â€” If handled, translate decision to Response.
        if decision is not None and decision.handled:
            response = self._respond_to_decision(decision)
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # Step 4 â€” Check for natural memory statements.
        # Genesis-025 Sprint-002: SlotCompletionEngine runs first (generic),
        # then falls back to MemoryDetector (explicit patterns).
        # SlotCompletionEngine is pure detection â€” same inputs â†’ same output.
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
        # Step 5 â€” If a memory was detected, store and acknowledge.
        if detection is not None:
            response = self._handle_memory_detection(detection)
            self.context.last_skill = "memory"
            self.context.last_jarvis_response = response.message
            self._post_turn(request, response.message)
            return response

        # Step 6 â€” Genesis-020 S2: Resolve ambiguous references.
        resolution = None
        if self.context_resolver.needs_resolution(request):
            resolution = self.context_resolver.resolve(request)
            if resolution.resolved:
                self.logger.info(
                    "[CONTEXT] Resolved %r â†’ hint=%r (slot=%s, conf=%.2f)",
                    resolution.pronoun, resolution.context_hint,
                    resolution.slot_type, resolution.confidence,
                )

        # Step 7 â€” Normal intent routing.
        with telemetry.stage("intent_routing"):
            intent = self.router.detect(request)
        telemetry.log_since("agent_pipeline", pipeline_start)
        response = self._route(intent, request, resolution)

        # Step 8 â€” Update context.
        self.context.last_intent = intent.name if intent else None
        self.context.last_jarvis_response = response.message

        # Step 9 â€” Post-turn processing.
        self._post_turn(request, response.message)

        return response

    def _post_turn(self, request: str, response_message: str) -> None:
        """
        Fire-and-forget post-turn processing. Errors never propagate.

        S1: ConversationObserver   â€” extract facts â†’ KnowledgeEngine
        S2: ContextManager         â€” update SessionContext working memory
        S3: Timeline               â€” publish new events from extracted facts
        S4: DecisionEngine         â€” apply DECISION_* events
        S5: GoalEngine             â€” apply GOAL_* events
        S6: SessionSummaryEngine   â€” apply all events for summary
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
            "Memory detected â€” key: %r, value: %r, confidence: %.2f",
            detection.key, detection.value, detection.confidence
        )
        # Genesis-025 Sprint-003: set active_topic for group declarations
        # so subsequent turns can fill slots via SlotCompletionEngine.
        # Uses is_group_declaration signal â€” no entity type enumeration needed.
        if detection.is_group_declaration:
            self.session.set_topic(detection.value, raw=detection.value)
            self.logger.debug(
                "[SLOT] active_topic set to %r after group declaration",
                detection.value,
            )
        with telemetry.stage("skill_manager", skill="memory_store"):
            return self.skills.get("memory").remember(detection.key, detection.value)

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
                return Response(success=True, message=f"Of course, sir. To confirm â€” {pending}")
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

        # Genesis-022: Run Conversation Engine pipeline for enriched context.
        try:
            conv_decision = self.conversation_engine.process(request)
            if conv_decision.decision_type == DecisionType.RECOVERY:
                return Response(success=True, message="Understood, sir. I've cleared that.")
            if conv_decision.decision_type == DecisionType.SLOT_FILLED:
                slot_name  = conv_decision.payload.get("slot_name", "")
                slot_value = conv_decision.payload.get("slot_value", "")
                if slot_name and slot_value:
                    self.skills.get("memory").remember(slot_name, slot_value)
                return Response(success=True, message=f"Got it, sir. I've noted {slot_value!r}.")
        except Exception:
            self.logger.exception("[CONV] ConversationEngine error â€” continuing with intent routing.")

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
            # TODO (Genesis-026): Centralize contextual recall routing.
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
            # "I don't have information stored". The memory skill miss response
            # should only be the final word for explicit memory operations
            # (e.g. "What is my name?"), not general identity queries.
            import re as _re_cv003
            _IDENTITY_RE = _re_cv003.compile(
                r"\bwho\s+(?:is|are|was|were)\b",
                _re_cv003.IGNORECASE,
            )
            if _IDENTITY_RE.search(request):
                # Fall through to AI routing below
                self.logger.info(
                    "[MEMORY] Recall miss -> falling through to AI for identity query: %r",
                    request[:60],
                )
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
        # the query using session context. Without this guard, "Who are they?"
        # after "I have 5 servers" gets intercepted here: search_memory finds
        # the servers declaration record and returns "Your servers is 5 servers"
        # before the identity engine can produce the proper named answer.
        _ctxrecall_can_answer = self.contextual_recall.can_answer(request, self.session)
        self.logger.debug(
            "[CV-002-002] can_answer=%r for %r (active_topic=%r)",
            _ctxrecall_can_answer, request[:40],
            self.session.active_topic.value if self.session.active_topic else None,
        )
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
        # "Who is Rex?" / "Who are Rex and Tom?" / "What is staging?"
        reverse_request = self.reverse_entity_parser.parse(request)
        if reverse_request:
            reverse_result = self.contextual_recall.reverse_lookup(
                reverse_request, self.conversation_recall
            )
            if reverse_result and reverse_result.found:
                return Response(success=True, message=reverse_result.answer)

        # 5. Conversation recall and timeline.
        # Genesis-025 Sprint-004: ContextualRecallEngine resolves anaphoric
        # queries using SessionContext before delegating to ConversationRecall.
        # Genesis-026 Sprint-002: ResolutionType.IDENTITY uses two-step lookup.
        # TODO (Genesis-026): Centralize contextual recall routing.
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

        # 7. Reasoning
        reasoned = self.skills.get("reasoning").infer_attribute(
            request.strip()
        ) if request.strip() else None
        if reasoned is not None:
            return reasoned

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

    def _execute_skill(self, name: str, request: str) -> Response:
        """Execute a skill with telemetry."""
        self.context.last_skill = name
        with telemetry.stage("skill_manager", skill=name):
            return self.skills.execute(name, request)