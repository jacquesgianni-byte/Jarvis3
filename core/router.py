"""
Jarvis Intent Router

Responsible for detecting the user's intent.

Genesis-012 fixes:
    * Word-boundary matching everywhere. The old substring matching
      routed "whICH weighs more..." to GREETING because "hi" is inside
      "which". Whole-word matching kills that class of bug.
    * Personal recall questions route to MEMORY before IDENTITY.
    * IDENTITY matches questions about Jarvis itself.

Genesis-019.5:
    * ENGINEERING intent added. Detected after MEMORY and REASONING
      (stored facts and reasoning always take priority) but before
      UNKNOWN so the Academy is always tried first.
"""

import re

from core.intents import Intent
from core.understanding.normalizer import Normalizer


def _has_word(request: str, word: str) -> bool:
    """True if the word or phrase appears with word boundaries."""
    return re.search(r"\b" + re.escape(word) + r"\b", request) is not None


class IntentRouter:

    _GREETINGS = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    ]

    _IDENTITY = [
        "who are you", "who r you", "who are u", "your name",
    ]

    _MEMORY_RECALL = re.compile(
        r"\b(?:what(?:'s|s| is| was)?|who(?:'s|s| is)?|tell me|do you know|"
        r"do you remember)\b.*\bmy\b",
        re.IGNORECASE,
    )

    _REASONING_FOLLOW_UPS = {
        "why", "why is that", "how did you work that out", "how do you know",
        "how do you know that", "explain", "explain that",
    }
    _REASONING_PATTERNS = [
        re.compile(r"\bwhat can you (?:conclude|infer|work out|tell)\b", re.IGNORECASE),
        re.compile(r"\b(?:what|which) sports? do i (?:follow|play|watch|support)\b", re.IGNORECASE),
        re.compile(r"\b(?:what|which) country (?:do i live in|am i in|am i from)\b", re.IGNORECASE),
        re.compile(r"\b(?:what|which) hemisphere\b", re.IGNORECASE),
    ]

    # Genesis-019.5 — engineering question detection.
    # Checked AFTER memory and reasoning, BEFORE UNKNOWN.
    _ENGINEERING_PATTERNS = [
        # Explain/describe questions about named engineering concepts
        re.compile(
            r"\b(?:what is|what are|explain|describe|tell me about|"
            r"how does|when should i use|when do i use|"
            r"what is the difference between)\b.{0,60}"
            r"(?:pattern|anti.?pattern|principle|architecture|"
            r"best practice|engineering decision)\b",
            re.IGNORECASE,
        ),
        # Named engineering concepts (patterns, anti-patterns, principles)
        re.compile(
            r"\b(?:repository pattern|strategy pattern|factory pattern|"
            r"observer pattern|adapter pattern|facade pattern|"
            r"builder pattern|command pattern|decorator pattern|"
            r"dependency injection|god object|spaghetti code|"
            r"dead code|magic number|tight coupling|circular dependency|"
            r"shotgun surgery|feature envy|copy.paste programming|"
            r"premature optimis|layered architecture|clean architecture|"
            r"hexagonal architecture|microservice|modular monolith|"
            r"event.driven architecture|mvc pattern|mvvm pattern|"
            r"pipeline architecture|plugin architecture|"
            r"dry principle|kiss principle|yagni principle|"
            r"single responsibility|separation of concerns|"
            r"dependency inversion|open.closed principle|"
            r"composition.{0,15}inheritance|refactor.{0,10}rewrite|"
            r"build vs buy|technical debt|version control discipline|"
            r"fail fast|defensive programming|input validation)\b",
            re.IGNORECASE,
        ),
        # List/enumerate queries
        re.compile(
            r"\b(?:list|show|give me|what).{0,20}"
            r"(?:engineering principles|design patterns|anti.?patterns|"
            r"architecture patterns|best practices|engineering decisions|"
            r"patterns you know|principles you know)\b",
            re.IGNORECASE,
        ),
        # Natural "what is X pattern" / "explain X anti-pattern"
        re.compile(
            r"\b(?:what is|explain|describe).{0,30}"
            r"(?:pattern|anti.?pattern|principle)\b",
            re.IGNORECASE,
        ),
    ]

    _EXITS = ["exit", "quit", "bye", "goodbye"]

    def __init__(self):
        self.normalizer = Normalizer()

    def detect(self, request: str) -> Intent:
        """Detect the user's intent."""

        request = self.normalizer.normalize(request)

        # Memory — explicit commands and personal recall questions.
        if _has_word(request, "remember") or _has_word(request, "forget"):
            return Intent.MEMORY
        if self._MEMORY_RECALL.search(request):
            return Intent.MEMORY
        if _has_word(request, "drink"):
            return Intent.MEMORY

        # Reasoning — checked after MEMORY.
        if request.rstrip("?!. ").strip() in self._REASONING_FOLLOW_UPS:
            return Intent.REASONING
        if any(pattern.search(request) for pattern in self._REASONING_PATTERNS):
            return Intent.REASONING

        # Greeting
        if any(_has_word(request, word) for word in self._GREETINGS):
            return Intent.GREETING

        # Identity — questions about Jarvis itself.
        if any(_has_word(request, phrase) for phrase in self._IDENTITY):
            return Intent.IDENTITY

        # Exit — exact match only.
        if any(word == request.strip() for word in self._EXITS):
            return Intent.EXIT

        # Tool
        if _has_word(request, "tool"):
            return Intent.TOOL

        # Engineering — Academy lookup before AI fallback.
        # Genesis-019.5: tried before UNKNOWN so the Academy is always
        # consulted for engineering questions.
        if any(p.search(request) for p in self._ENGINEERING_PATTERNS):
            return Intent.ENGINEERING

        return Intent.UNKNOWN
    