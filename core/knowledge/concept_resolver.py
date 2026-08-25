"""
Jarvis OS - ConceptResolver - Genesis-059 Sprint-001

Resolves natural-language phrases to canonical project identifiers.

Design invariants:
    - Pure: no filesystem access, no network, no LLM.
    - Independent: zero dependency on GenesisDeliveryStore or any other
      knowledge component. Can be constructed and tested in complete isolation.
    - Deterministic: same phrase always returns same result.
    - Declared: only phrases explicitly registered here are resolved.
      Unknown phrases return None - never a guess.
    - current_genesis_id is injected at construction time (Option B).
      ConceptResolver does not read project_state.json itself.

When ConceptResolver does not know, it returns None.
It must not pretend it knows.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class ConceptResolver:
    """
    Resolves natural-language phrases to canonical project identifiers.

    Construction:
        current_genesis_id: injected from project_state.json by the caller.
        ConceptResolver never reads project_state.json itself.

    Resolution:
        resolve(phrase) -> canonical identifier string, or None.
        Matching is case-insensitive and whitespace-normalised.
        Only declared phrases are resolved. No inference. No keywords.

    Independence:
        This class has zero imports from core.knowledge or core.mission.
        It is independently testable without any other Jarvis component.
    """

    def __init__(self, current_genesis_id: str) -> None:
        self._current_genesis_id = current_genesis_id

    def resolve(self, phrase: str) -> Optional[str]:
        """
        Resolve a natural-language phrase to a canonical identifier.

        Returns the canonical identifier string, or None if the phrase
        is not recognised. Never raises. Never guesses.

        Sprint-001: resolves genesis-related phrases only.
        """
        normalised = self._normalise(phrase)

        resolved = (
            self._resolve_genesis(normalised)
        )

        if resolved is not None:
            logger.debug(
                "[ConceptResolver] %r -> %r", phrase, resolved
            )
        else:
            logger.debug(
                "[ConceptResolver] %r -> None (not recognised)", phrase
            )

        return resolved

    def _resolve_genesis(self, normalised: str) -> Optional[str]:
        """
        Resolve genesis-related phrases.

        'latest genesis', 'current genesis', 'last genesis',
        'most recent genesis' -> current_genesis_id

        Specific genesis references like 'genesis-058' -> 'Genesis-058'
        (canonical capitalisation applied).
        """
        # Latest / current genesis phrases
        LATEST_PHRASES = (
            "latest genesis",
            "current genesis",
            "last genesis",
            "most recent genesis",
            "the latest genesis",
            "the current genesis",
            "the last genesis",
        )
        for p in LATEST_PHRASES:
            if p in normalised:
                return self._current_genesis_id

        # Specific genesis reference: genesis-NNN or genesis NNN
        match = re.search(r"genesis[-\s](\d+)", normalised)
        if match:
            return f"Genesis-{match.group(1)}"

        return None

    @staticmethod
    def _normalise(phrase: str) -> str:
        """Lowercase and collapse whitespace for consistent matching."""
        return " ".join(phrase.lower().split())
