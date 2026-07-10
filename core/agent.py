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

from core.conversation.context import ConversationContext
from core.conversation.intelligence import ConversationIntelligence
from core.conversation.behaviour import ConversationBehaviour
from core.conversation.decision import ConversationDecision, ConversationOutcome
from core.conversation.memory_detector import MemoryDetector
from core.conversation.memory_detection import MemoryDetection


class Agent:
    """
    The central decision maker for Jarvis.

    Owns one each of:
        ConversationContext       — current conversation state
        ConversationIntelligence  — message classification
        ConversationBehaviour     — pending interaction handling
        MemoryDetector            — natural memory statement detection

    Processing flow per request:
        1. Classify via ConversationIntelligence.
        2. Evaluate pending interactions via ConversationBehaviour.
        3. Detect natural memory statements via MemoryDetector.
        4. Route to intent skills or AI fallback.
        5. Update ConversationContext.

    Args:
        ai: Optional AI provider. Used as fallback when no intent is matched.
    """

    def __init__(self, ai=None):
        self.logger = get_logger()

        # Core services
        self.router = IntentRouter()
        # Genesis-012: persistent structured memory. Replaces the old
        # in-memory MemoryManager (which never persisted to disk).
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

        # Conversation layer
        self.context = ConversationContext()
        self.intelligence = ConversationIntelligence()
        self.behaviour = ConversationBehaviour()

        # Memory detection
        self.memory_detector = MemoryDetector()

    def process(self, request: str, token=None) -> Response:
        """
        Process a user request.

        Args:
            request: The user's message.
            token:   Opaque conversation-ownership context supplied by
                     JarvisCore. The Agent never inspects it and never
                     decides whether a response is stale — that is the
                     Conversation layer's job. It exists here so future
                     async/cancellation work needs no signature change.

        Flow:
            1. Classify the message via ConversationIntelligence.
            2. Evaluate for pending interactions via ConversationBehaviour.
            3. If handled, translate the ConversationDecision into a Response.
            4. Check for natural memory statements via MemoryDetector.
            5. If detected, store via MemorySkill and acknowledge.
            6. Proceed with normal intent routing.
            7. Update ConversationContext after every interaction.
        """

        self.logger.info("Request received: %s", request)

        # Telemetry: measures classification, pending-interaction
        # evaluation, memory detection and intent routing — everything
        # the Agent does before (or instead of) calling the AI.
        pipeline_start = time.perf_counter()

        # Update context with the incoming message.
        self.context.last_user_message = request

        # Step 1 — Classify.
        with telemetry.stage("classification"):
            category = self.intelligence.classify(request, self.context)
        self.logger.debug(f"Message category: {category.name}")

        # Step 2 — Evaluate for pending interaction.
        with telemetry.stage("behaviour"):
            decision = self.behaviour.handle(category, self.context)

        # Step 3 — If handled, translate decision to Response.
        # Check both that a decision was returned and that it is marked handled.
        # This future-proofs the pipeline — ConversationBehaviour may return
        # a decision with handled=False to pass metadata without intercepting routing.
        if decision is not None and decision.handled:
            response = self._respond_to_decision(decision)
            self.context.last_jarvis_response = response.message
            return response

        # Step 4 — Check for natural memory statements.
        with telemetry.stage("memory_detection"):
            detection = self.memory_detector.detect(request)

        # Step 5 — If a memory was detected, store and acknowledge.
        if detection is not None:
            response = self._handle_memory_detection(detection)
            self.context.last_skill = "memory"
            self.context.last_jarvis_response = response.message
            return response

        # Step 6 — Normal intent routing.
        with telemetry.stage("intent_routing"):
            intent = self.router.detect(request)
        telemetry.log_since("agent_pipeline", pipeline_start)
        response = self._route(intent, request)

        # Step 7 — Update context.
        self.context.last_intent = intent.name if intent else None
        self.context.last_jarvis_response = response.message

        return response

    def _handle_memory_detection(
        self,
        detection: MemoryDetection
    ) -> Response:
        """
        Store a detected memory via MemorySkill and return an acknowledgement.

        Routes through MemorySkill — the single gateway into the
        KnowledgeEngine. The Agent never calls the engine directly.

        Args:
            detection: A MemoryDetection returned by MemoryDetector.

        Returns:
            A Response acknowledging the stored memory.
        """

        self.logger.debug(
            "Memory detected — key: %r, value: %r, confidence: %.2f",
            detection.key,
            detection.value,
            detection.confidence
        )

        with telemetry.stage("skill_manager", skill="memory_store"):
            return self.skills.get("memory").remember(detection.key, detection.value)

    def _respond_to_decision(self, decision: ConversationDecision) -> Response:
        """
        Translate a ConversationDecision into a user-facing Response.

        ConversationBehaviour decides what happened.
        The Agent decides what to say about it.

        Args:
            decision: The ConversationDecision returned by ConversationBehaviour.

        Returns:
            A Response with appropriate user-facing language.
        """

        if decision.outcome == ConversationOutcome.CONFIRMED:
            self.logger.debug("Responding to CONFIRMED decision.")
            return Response(
                success=True,
                message="Understood, sir. I will proceed."
            )

        if decision.outcome == ConversationOutcome.DENIED:
            self.logger.debug("Responding to DENIED decision.")
            return Response(
                success=True,
                message="Understood, sir. I will stand by."
            )

        if decision.outcome == ConversationOutcome.CLARIFICATION:
            self.logger.debug("Responding to CLARIFICATION decision.")
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(
                    success=True,
                    message=f"Of course, sir. I was asking: {pending}"
                )
            return Response(
                success=True,
                message="I apologise for the confusion, sir. Please go ahead."
            )

        if decision.outcome == ConversationOutcome.CONTINUATION:
            self.logger.debug("Responding to CONTINUATION decision.")
            pending = decision.pending_question or decision.pending_action
            if pending:
                return Response(
                    success=True,
                    message=f"Of course, sir. To confirm — {pending}"
                )
            return Response(
                success=True,
                message="Please go ahead, sir."
            )

        return Response(
            success=False,
            message="I'm not sure how to proceed, sir."
        )

    def _route(self, intent: Intent, request: str) -> Response:
        """
        Route a detected intent to the appropriate skill or AI fallback.

        Args:
            intent:  The detected intent.
            request: The original user request.

        Returns:
            A Response from the matched skill, AI fallback, or default.
        """

        if intent == Intent.GREETING:
            return self._execute_skill("greeting", request)

        if intent == Intent.IDENTITY:
            return self._execute_skill("identity", request)

        if intent == Intent.MEMORY:
            response = self._execute_skill("memory", request)

            # Genesis-013 Task 002 — Memory <-> Reasoning escalation.
            # Priority: stored fact, then reasoned conclusion, then the
            # honest local miss. Knowledge is the source of truth;
            # reasoning fills gaps and never overrides it.
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

        # AI fallback — preserved unchanged.
        if self.ai is not None:
            self.context.last_skill = "ai_fallback"
            with telemetry.stage("ai_manager"):
                return self.ai.ask(request)

        self.context.last_skill = None

        return Response(
            success=False,
            message="I'm still learning, but I'll be able to help with that soon."
        )

    def _execute_skill(self, name: str, request: str) -> Response:
        """
        Execute a skill with telemetry.

        Behaviour is identical to the previous inline branches:
        record the skill in context, then execute it — now with the
        execution time logged and tagged with the skill name.
        """
        self.context.last_skill = name
        with telemetry.stage("skill_manager", skill=name):
            return self.skills.execute(name, request)