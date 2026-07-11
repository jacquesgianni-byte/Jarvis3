"""
Jarvis Intent Router

Responsible for detecting the user's intent.

Genesis-012 fixes:
    * Word-boundary matching everywhere. The old substring matching
      routed "whICH weighs more..." to GREETING because "hi" is inside
      "which". Whole-word matching kills that class of bug.
    * Personal recall questions ("what is my X", "who is my X",
      "do you know my X") now route to MEMORY — checked before
      IDENTITY, so "what is my name?" asks the Knowledge Engine about
      the user instead of asking Jarvis about itself.
    * IDENTITY matches questions about Jarvis ("your name",
      "who are you"), no longer the bare word "name".
"""

import re

from core.intents import Intent
from core.understanding.normalizer import Normalizer


def _has_word(request: str, word: str) -> bool:
    """True if the word or phrase appears with word boundaries."""
    return re.search(rf"\b{re.escape(word)}\b", request) is not None


class IntentRouter:

    _GREETINGS = [
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
    ]

    _IDENTITY = [
        "who are you",
        "who r you",
        "who are u",
        "your name",
    ]

    # "what is my X" / "who is my X" / "whats my X" / "do you know my X"
    # / "tell me my X" — personal recall questions.
    _MEMORY_RECALL = re.compile(
        r"\b(?:what(?:'s|s| is| was)?|who(?:'s|s| is)?|tell me|do you know|"
        r"do you remember)\b.*\bmy\b",
        re.IGNORECASE,
    )

    # Genesis-013 — reasoning questions and follow-ups. Conservative by
    # design: anything uncertain falls through to the normal AI path.
    # Follow-ups match the ENTIRE request (punctuation stripped), so
    # "why is the sky blue?" still reaches the AI.
    _REASONING_FOLLOW_UPS = {
        "why",
        "why is that",
        "how did you work that out",
        "how do you know",
        "how do you know that",
        "explain",
        "explain that",
    }
    _REASONING_PATTERNS = [
        re.compile(r"\bwhat can you (?:conclude|infer|work out|tell)\b",
                   re.IGNORECASE),
        re.compile(r"\b(?:what|which) sports? do i (?:follow|play|watch|support)\b",
                   re.IGNORECASE),
        re.compile(r"\b(?:what|which) country (?:do i live in|am i in|am i from)\b",
                   re.IGNORECASE),
        re.compile(r"\b(?:what|which) hemisphere\b", re.IGNORECASE),
    ]

    _EXITS = ["exit", "quit", "bye", "goodbye"]

    def __init__(self):
        self.normalizer = Normalizer()

    def detect(self, request: str) -> Intent:
        """
        Detect the user's intent.
        """

        request = self.normalizer.normalize(request)

        # Memory — explicit commands and personal recall questions.
        # Checked before GREETING and IDENTITY so "what is my name?"
        # is about the user, not about Jarvis.
        if _has_word(request, "remember") or _has_word(request, "forget"):
            return Intent.MEMORY

        if self._MEMORY_RECALL.search(request):
            return Intent.MEMORY

        if _has_word(request, "drink"):
            return Intent.MEMORY

        # Reasoning — checked after MEMORY (recall of stored facts
        # always beats deriving them) and before GREETING.
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

        # Exit — exact match only, unchanged.
        if any(word == request.strip() for word in self._EXITS):
            return Intent.EXIT

        # Tool
        if _has_word(request, "tool"):
            return Intent.TOOL

        return Intent.UNKNOWN