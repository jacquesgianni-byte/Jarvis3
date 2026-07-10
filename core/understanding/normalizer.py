"""
Jarvis Understanding Engine

Normalizes user input before intent detection.

DEFECT FIX (Genesis-013 Task 002 validation, 2026-07-10):
corrections previously used substring replacement, which corrupted
valid English words from the inside — "ur"->"your" turned "your" into
"yoyour" and "colour" into "coloyour"; "fav"->"favorite" turned
"favourite" into "favoriteourite". Corrections now apply only to WHOLE
WORDS via word-boundary regex, so "whats ur name" still becomes
"whats your name" while "your", "colour", "purpose" and "Saturday"
pass through untouched.
"""

import re


class Normalizer:

    # Whole-word corrections: typo fixes, spacing fixes, slang
    # expansion, and spelling unification for the router's benefit.
    _CORRECTIONS = {
        "rember": "remember",
        "remeber": "remember",
        "remeberr": "remember",

        "goodevening": "good evening",
        "goodmorning": "good morning",
        "goodafternoon": "good afternoon",

        "fav": "favorite",
        "favourite": "favorite",

        "ur": "your",
    }

    # Compiled once: each correction matches only as a complete word.
    _PATTERNS = [
        (re.compile(rf"\b{re.escape(wrong)}\b"), correct)
        for wrong, correct in _CORRECTIONS.items()
    ]

    def normalize(self, text: str) -> str:
        """
        Normalize the user's request.
        """

        text = text.lower().strip()

        for pattern, correct in self._PATTERNS:
            text = pattern.sub(correct, text)

        return text