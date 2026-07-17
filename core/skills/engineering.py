"""
Jarvis Engineering Skill (Genesis-019.5)

The gateway between natural language engineering questions and the
Engineering Academy.

    The skill owns orchestration. The Academy owns knowledge.

Responsibilities:
    * Detect the specific engineering sub-topic (pattern, anti-pattern,
      architecture pattern, best practice, decision, or principle).
    * Query the appropriate Academy service deterministically.
    * Return a structured, spoken response when the Academy matches.
    * Log the routing decision with [ENGINEERING] prefix for easy tracing.
    * Fall back cleanly to the AI provider when no Academy match exists.

Constitutional constraints:
    * This skill never modifies the Academy.
    * This skill never makes autonomous engineering decisions.
    * All Academy queries are deterministic and read-only.
    * The AI fallback is invoked only when the Academy cannot answer.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from core.models.response import Response
from core.skills.base import Skill

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data paths — resolved relative to the project root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENGINEERING = _REPO_ROOT / "data" / "engineering"

_PRINCIPLES_PATH         = _ENGINEERING / "principles.json"
_PATTERNS_PATH           = _ENGINEERING / "patterns.json"
_ANTI_PATTERNS_PATH      = _ENGINEERING / "anti_patterns.json"
_ARCHITECTURE_PATH       = _ENGINEERING / "architecture_patterns.json"
_BEST_PRACTICES_PATH     = _ENGINEERING / "best_practices.json"
_DECISIONS_PATH          = _ENGINEERING / "engineering_decisions.json"


# ---------------------------------------------------------------------------
# Lazy-loaded Academy services
# ---------------------------------------------------------------------------

def _load_services():
    """
    Load all Academy services once. Returns a dict of service instances.
    Lazy-loaded so the skill does not add startup cost when engineering
    questions are absent from a session.
    """
    from core.engineering.academy.loader import AcademyLoader
    from core.engineering.academy.json_repository import (
        JsonAcademyRepository,
        JsonPatternRepository,
        JsonAntiPatternRepository,
        JsonArchitecturePatternRepository,
        JsonBestPracticeRepository,
        JsonEngineeringDecisionRepository,
    )
    from core.engineering.academy.service import (
        AcademyService,
        PatternService,
        AntiPatternService,
        ArchitecturePatternService,
        BestPracticeService,
        EngineeringDecisionService,
    )

    loader = AcademyLoader()

    services = {}

    if _PRINCIPLES_PATH.exists():
        services["principles"] = AcademyService(
            JsonAcademyRepository(_PRINCIPLES_PATH, loader)
        )

    if _PATTERNS_PATH.exists():
        services["patterns"] = PatternService(
            JsonPatternRepository(_PATTERNS_PATH, loader)
        )

    if _ANTI_PATTERNS_PATH.exists():
        services["anti_patterns"] = AntiPatternService(
            JsonAntiPatternRepository(_ANTI_PATTERNS_PATH, loader)
        )

    if _ARCHITECTURE_PATH.exists():
        services["architecture"] = ArchitecturePatternService(
            JsonArchitecturePatternRepository(_ARCHITECTURE_PATH, loader)
        )

    if _BEST_PRACTICES_PATH.exists():
        services["best_practices"] = BestPracticeService(
            JsonBestPracticeRepository(_BEST_PRACTICES_PATH, loader)
        )

    if _DECISIONS_PATH.exists():
        services["decisions"] = EngineeringDecisionService(
            JsonEngineeringDecisionRepository(_DECISIONS_PATH, loader)
        )

    return services


# ---------------------------------------------------------------------------
# Intent patterns — what the user is asking about
# ---------------------------------------------------------------------------

# "list all patterns", "what patterns do you know", "show me the patterns"
_LIST_PATTERNS = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:pattern|patterns|design pattern|design patterns)\b",
    re.IGNORECASE,
)
_LIST_ANTI_PATTERNS = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:anti.?pattern|anti.?patterns)\b",
    re.IGNORECASE,
)
_LIST_ARCHITECTURE = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:architecture pattern|architecture patterns)\b",
    re.IGNORECASE,
)
_LIST_PRINCIPLES = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:principle|principles|engineering principle)\b",
    re.IGNORECASE,
)
_LIST_BEST_PRACTICES = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:best practice|best practices)\b",
    re.IGNORECASE,
)
_LIST_DECISIONS = re.compile(
    r"\b(?:list|show|what|tell me|give me).{0,20}"
    r"(?:engineering decision|engineering decisions|decision framework)\b",
    re.IGNORECASE,
)

# "explain the repository pattern", "what is the strategy pattern",
# "tell me about god object"
_EXPLAIN = re.compile(
    r"\b(?:explain|what is|what are|tell me about|describe|how does|"
    r"when (?:should|do) i use)\b",
    re.IGNORECASE,
)

# Keywords that signal an engineering context
_ENGINEERING_SIGNALS = re.compile(
    r"\b(?:pattern|anti.?pattern|principle|architecture|refactor|"
    r"solid|dry|kiss|yagni|coupling|cohesion|dependency|injection|"
    r"repository|strategy|factory|observer|adapter|facade|builder|"
    r"command|singleton|decorator|composite|proxy|iterator|template|"
    r"god object|spaghetti|dead code|magic number|premature optimis|"
    r"layered|clean architecture|hexagonal|microservice|monolith|"
    r"event.driven|mvc|mvvm|pipeline|plugin|"
    r"best practice|technical debt|code review|refactoring|"
    r"version control|incremental|backwards compat|"
    r"composition.{0,10}inheritance|build.{0,5}buy|"
    r"synchronous|asynchronous|scalabilit|maintainabilit|"
    r"single responsibility|separation of concerns|"
    r"engineering decision|engineering principle)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Query term extraction — strips preamble so the Academy search
# receives a short, matchable term rather than the full raw query.
# Academy search is: needle in field — so the needle must be short.
# ---------------------------------------------------------------------------

_STRIP_PREAMBLE = re.compile(
    r"^\s*(?:what is|what are|explain|describe|tell me about|how does|"
    r"when should i use|when do i use|tell me|show me|list|give me|"
    r"what are the|what is the|how do i|why is|why should i)\s+",
    re.IGNORECASE,
)
_STRIP_LEADING_ARTICLE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)
_STRIP_TYPE_SUFFIX = re.compile(
    r"\s+(?:anti.?pattern|pattern|principle|architecture|best practice|"
    r"engineering decision)s?\s*$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Knowledge base hint detection — infers which knowledge base the user
# is asking about from explicit type words in the query.
# Used to route directly to the right service before falling back to
# cross-knowledge-base search, avoiding false matches.
# ---------------------------------------------------------------------------

_HINT_ANTI_PATTERN = re.compile(r"\banti.?pattern\b", re.IGNORECASE)
_HINT_ARCHITECTURE = re.compile(r"\barchitecture\b", re.IGNORECASE)
_HINT_PATTERN = re.compile(r"\bpattern\b", re.IGNORECASE)
_HINT_PRINCIPLE = re.compile(r"\bprinciple\b", re.IGNORECASE)
_HINT_BEST_PRACTICE = re.compile(r"\bbest practice\b", re.IGNORECASE)
_HINT_DECISION = re.compile(r"\bdecision\b", re.IGNORECASE)


def _detect_knowledge_base(request: str) -> str | None:
    """
    Detect which knowledge base the user is asking about.

    Returns a key matching services dict, or None if no hint present.
    The original query (not the extracted term) is checked so type
    words like "anti-pattern" and "architecture" are preserved.
    """
    if _HINT_ANTI_PATTERN.search(request):
        return "anti_patterns"
    if _HINT_ARCHITECTURE.search(request):
        return "architecture"
    if _HINT_PATTERN.search(request):
        return "patterns"
    if _HINT_PRINCIPLE.search(request):
        return "principles"
    if _HINT_BEST_PRACTICE.search(request):
        return "best_practices"
    if _HINT_DECISION.search(request):
        return "decisions"
    return None


def _extract_search_term(request: str) -> str:
    """
    Extract the engineering term from a natural language query.

    "Explain the Strategy Pattern."        → "Strategy"
    "Explain the God Object anti-pattern." → "God Object"
    "What is tight coupling?"              → "tight coupling"
    "Explain clean architecture."          → "clean architecture"
    """
    term = request.strip().rstrip("?!.")
    term = _STRIP_PREAMBLE.sub("", term)
    term = _STRIP_LEADING_ARTICLE.sub("", term)
    term = _STRIP_TYPE_SUFFIX.sub("", term)
    return term.strip()


class EngineeringSkill(Skill):
    """
    Routes engineering questions to the Academy before calling any AI.

    On a cache miss (no Academy match), the skill returns None so the
    Agent can fall back to the AI provider transparently.
    """

    def __init__(self, ai=None):
        """
        Args:
            ai: The AIManager instance. Used as fallback when the Academy
                cannot answer. May be None during testing.
        """
        self.ai = ai
        self._services: Optional[dict] = None

    @property
    def name(self) -> str:
        return "engineering"

    def _get_services(self) -> dict:
        """Lazy-load Academy services on first use."""
        if self._services is None:
            logger.info("[ENGINEERING] Loading Engineering Academy services.")
            self._services = _load_services()
            logger.info(
                "[ENGINEERING] Academy loaded: %s",
                list(self._services.keys()),
            )
        return self._services

    # ------------------------------------------------------------------
    # Skill interface
    # ------------------------------------------------------------------

    def execute(self, request: str) -> Response:
        """
        Route the engineering question through the Academy.

        Attempts deterministic Academy lookup first. If the Academy
        cannot answer, falls back to the AI provider. If no AI provider
        is available, returns a graceful miss response.
        """
        logger.info("[ENGINEERING] Engineering question detected: %r", request)
        logger.info("[ENGINEERING] Querying Academy...")

        response = self._query_academy(request)
        if response is not None:
            return response

        # Academy miss — fall back to AI
        logger.info("[ENGINEERING] No Academy match.")
        if self.ai is not None:
            logger.info("[ENGINEERING] Falling back to AI provider.")
            return self.ai.ask(request)

        logger.info("[ENGINEERING] No AI provider available.")
        return Response(
            success=True,
            message=(
                "That's an engineering topic I don't have a specific "
                "Academy entry for yet, sir. Try asking about a specific "
                "pattern, principle, or anti-pattern by name."
            ),
        )

    # ------------------------------------------------------------------
    # Academy query logic
    # ------------------------------------------------------------------

    def _query_academy(self, request: str) -> Optional[Response]:
        """
        Try to answer the request from the Academy.

        Returns a Response on match, None on miss.
        """
        services = self._get_services()
        req_lower = request.lower()

        # --- List queries (broad) ---

        if _LIST_PRINCIPLES.search(request):
            return self._list_principles(services)

        if _LIST_ANTI_PATTERNS.search(request):
            return self._list_anti_patterns(services)

        if _LIST_ARCHITECTURE.search(request):
            return self._list_architecture(services)

        if _LIST_PATTERNS.search(request):
            return self._list_patterns(services)

        if _LIST_BEST_PRACTICES.search(request):
            return self._list_best_practices(services)

        if _LIST_DECISIONS.search(request):
            return self._list_decisions(services)

        # --- Specific lookup (search all knowledge bases) ---

        if _EXPLAIN.search(request):
            return self._search_all(services, request)

        # --- Signal-based search (e.g. "repository pattern") ---

        if _ENGINEERING_SIGNALS.search(request):
            return self._search_all(services, request)

        return None

    # ------------------------------------------------------------------
    # List handlers
    # ------------------------------------------------------------------

    def _list_principles(self, services: dict) -> Response:
        svc = services.get("principles")
        if not svc:
            return None
        principles = svc.list_principles()
        names = ", ".join(p.name for p in principles[:10])
        total = len(principles)
        logger.info("[ENGINEERING] Match found: %d principles", total)
        return Response(
            success=True,
            message=(
                f"I know {total} engineering principles, sir. "
                f"Here are some: {names}. "
                f"Ask me about any specific one for a full explanation."
            ),
        )

    def _list_patterns(self, services: dict) -> Response:
        svc = services.get("patterns")
        if not svc:
            return None
        patterns = svc.list_patterns()
        names = ", ".join(p.name for p in patterns)
        total = len(patterns)
        logger.info("[ENGINEERING] Match found: %d design patterns", total)
        return Response(
            success=True,
            message=(
                f"I know {total} design patterns, sir: {names}. "
                f"Ask me to explain any of them."
            ),
        )

    def _list_anti_patterns(self, services: dict) -> Response:
        svc = services.get("anti_patterns")
        if not svc:
            return None
        aps = svc.list_anti_patterns()
        names = ", ".join(ap.name for ap in aps)
        total = len(aps)
        logger.info("[ENGINEERING] Match found: %d anti-patterns", total)
        return Response(
            success=True,
            message=(
                f"I know {total} anti-patterns, sir: {names}. "
                f"Ask me to explain any of them."
            ),
        )

    def _list_architecture(self, services: dict) -> Response:
        svc = services.get("architecture")
        if not svc:
            return None
        patterns = svc.list_architecture_patterns()
        names = ", ".join(p.name for p in patterns)
        total = len(patterns)
        logger.info("[ENGINEERING] Match found: %d architecture patterns", total)
        return Response(
            success=True,
            message=(
                f"I know {total} architecture patterns, sir: {names}. "
                f"Ask me to explain any of them."
            ),
        )

    def _list_best_practices(self, services: dict) -> Response:
        svc = services.get("best_practices")
        if not svc:
            return None
        practices = svc.list_best_practices()
        names = ", ".join(p.name for p in practices[:8])
        total = len(practices)
        logger.info("[ENGINEERING] Match found: %d best practices", total)
        return Response(
            success=True,
            message=(
                f"I know {total} engineering best practices, sir. "
                f"Some include: {names}. "
                f"Ask me about any specific one."
            ),
        )

    def _list_decisions(self, services: dict) -> Response:
        svc = services.get("decisions")
        if not svc:
            return None
        decisions = svc.list_decisions()
        names = ", ".join(d.name for d in decisions[:6])
        total = len(decisions)
        logger.info("[ENGINEERING] Match found: %d engineering decisions", total)
        return Response(
            success=True,
            message=(
                f"I have {total} engineering decision frameworks, sir. "
                f"Some include: {names}. "
                f"Ask me about any specific one."
            ),
        )

    # ------------------------------------------------------------------
    # Cross-knowledge-base search
    # ------------------------------------------------------------------

    def _search_all(self, services: dict, request: str) -> Optional[Response]:
        """
        Search all knowledge bases in priority order.
        Returns the first match found, or None.

        Strategy:
        1. Detect a knowledge base hint from type words in the query
           ("anti-pattern", "architecture", "pattern", "principle").
        2. If a hint is found, search that knowledge base first to avoid
           false matches in other knowledge bases.
        3. Extract the engineering term (strips preamble and type suffix)
           so the Academy substring search receives a short, matchable term.
        4. Fall back to the full priority search if the hinted service
           does not return a match.
        """
        term = _extract_search_term(request)
        hint = _detect_knowledge_base(request)

        # Hinted search first — try the most likely knowledge base
        if hint == "anti_patterns":
            result = self._search_anti_patterns(services, term)
            if result:
                return result
        elif hint == "architecture":
            result = self._search_architecture(services, term)
            if result:
                return result
        elif hint == "patterns":
            result = self._search_patterns(services, term)
            if result:
                return result
        elif hint == "principles":
            result = self._search_principles(services, term)
            if result:
                return result
        elif hint == "best_practices":
            result = self._search_best_practices(services, term)
            if result:
                return result
        elif hint == "decisions":
            result = self._search_decisions(services, term)
            if result:
                return result

        # Full cross-knowledge-base fallback in priority order
        result = self._search_patterns(services, term)
        if result:
            return result
        result = self._search_anti_patterns(services, term)
        if result:
            return result
        result = self._search_architecture(services, term)
        if result:
            return result
        result = self._search_principles(services, term)
        if result:
            return result
        result = self._search_best_practices(services, term)
        if result:
            return result
        result = self._search_decisions(services, term)
        if result:
            return result

        return None

    def _search_patterns(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("patterns")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        p = results[0]
        logger.info("[ENGINEERING] Match found: Design Pattern — %s", p.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        return Response(
            success=True,
            message=(
                f"The {p.name} pattern, sir. {p.intent} "
                f"{p.solution} "
                f"Use it when: {p.when_to_use[0] if p.when_to_use else ''}."
            ),
        )

    def _search_anti_patterns(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("anti_patterns")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        ap = results[0]
        logger.info("[ENGINEERING] Match found: Anti-Pattern — %s", ap.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        symptom = ap.symptoms[0] if ap.symptoms else ""
        solution = ap.recommended_solution
        return Response(
            success=True,
            message=(
                f"The {ap.name} anti-pattern, sir. {ap.description} "
                f"A key symptom is: {symptom}. "
                f"The solution: {solution}"
            ),
        )

    def _search_architecture(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("architecture")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        ap = results[0]
        logger.info("[ENGINEERING] Match found: Architecture Pattern — %s", ap.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        use_when = ap.when_to_use[0] if ap.when_to_use else ""
        return Response(
            success=True,
            message=(
                f"The {ap.name} architecture, sir. {ap.intent} "
                f"{ap.description} "
                f"Use it when: {use_when}."
            ),
        )

    def _search_principles(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("principles")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        p = results[0]
        logger.info("[ENGINEERING] Match found: Principle — %s", p.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        return Response(
            success=True,
            message=(
                f"{p.name}, sir. {p.summary} "
                f"{p.rationale} "
                f"Guidance: {p.guidance}"
            ),
        )

    def _search_best_practices(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("best_practices")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        bp = results[0]
        logger.info("[ENGINEERING] Match found: Best Practice — %s", bp.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        guidance = bp.implementation_guidance[0] if bp.implementation_guidance else ""
        return Response(
            success=True,
            message=(
                f"{bp.name}, sir. {bp.description} "
                f"{bp.rationale} "
                f"Key guidance: {guidance}"
            ),
        )

    def _search_decisions(self, services: dict, request: str) -> Optional[Response]:
        svc = services.get("decisions")
        if not svc:
            return None
        results = svc.search(request)
        if not results:
            return None
        d = results[0]
        logger.info("[ENGINEERING] Match found: Engineering Decision — %s", d.name)
        logger.info("[ENGINEERING] Returning deterministic response.")
        question = d.decision_questions[0] if d.decision_questions else ""
        return Response(
            success=True,
            message=(
                f"{d.name}, sir. {d.situation} "
                f"Recommended approach: {d.recommended_action} "
                f"Key question to ask: {question}"
            ),
        )