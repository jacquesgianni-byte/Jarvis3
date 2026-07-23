"""
Jarvis Context Resolver (Genesis-020 Sprint-002 — Revised)

Resolves ambiguous pronoun and reference expressions using SessionContext.

Key design decisions (post-review):
    - NEVER rewrites the original request. Returns a Resolution with
      context_hint attached. The Agent passes both to skills/AI so
      the original user intent is always preserved.
    - Confidence field on every Resolution (0.0–1.0).
    - Only resolves above MIN_RESOLUTION_CONFIDENCE threshold.
    - Fully deterministic — no AI calls.

Resolution confidence levels:
    Person pronouns (him/her):   0.95 — very specific
    Named references (the sprint): 0.90
    Generic pronouns (it/this):  0.70 — ambiguous
    Continuation:                0.80

Integration contract:
    Agent receives Resolution. If resolved=True and confidence >= threshold:
        - Passes original request to skills/routing unchanged
        - Attaches resolution.context_hint as additional context
    The original prompt is NEVER replaced.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from core.conversation.session_context import SessionContext

logger = logging.getLogger(__name__)

# Minimum confidence to use a resolution
MIN_RESOLUTION_CONFIDENCE: float = 0.60

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PERSON_PRONOUNS   = re.compile(r"\b(him|her|he|she|they|them)\b", re.IGNORECASE)
_PROJECT_REFS      = re.compile(r"\b(the project|the app|the system|the platform|this project|that project)\b", re.IGNORECASE)
_MILESTONE_REFS    = re.compile(r"\b(the milestone|the genesis|the release|this milestone|that milestone|the freeze)\b", re.IGNORECASE)
_TASK_REFS         = re.compile(r"\b(the sprint|the task|this sprint|that sprint|the current sprint)\b", re.IGNORECASE)
_GENERIC_PRONOUNS  = re.compile(r"\b(it|this|that|the thing|the one)\b", re.IGNORECASE)
_CONTINUATION      = re.compile(r"\b(?:let(?:'s| us)\s+)?(?:continue|keep going|carry on|resume|pick up)\b", re.IGNORECASE)
_WHAT_ARE_WE       = re.compile(r"\bwhat are we (?:doing|working on|building|talking about)\b", re.IGNORECASE)
_WHO_ARE_WE        = re.compile(r"\bwho (?:are we|is|was) (?:talking about|discussing|working with)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Resolution:
    """
    Result of a context resolution attempt.

    The original request is NEVER modified. If resolved=True,
    context_hint contains the resolved value the Agent can use
    to enrich calls to skills or AI without replacing the user's words.

    Attributes:
        resolved:     True if a resolution was found.
        original:     The user's original message (unchanged always).
        context_hint: The resolved context value ("Claude", "Genesis-020", etc.)
        slot_type:    Which slot was used ("person", "project", etc.)
        confidence:   Resolver confidence (0.0–1.0).
        pronoun:      The specific pronoun/reference that was resolved.
    """
    resolved:     bool
    original:     str
    context_hint: str  = ""
    slot_type:    str  = ""
    confidence:   float = 0.0
    pronoun:      str  = ""


class ContextResolver:
    """
    Resolves ambiguous references using active SessionContext.

    Returns a Resolution — never modifies the request.
    Callers decide how to use the context_hint.
    """

    def __init__(self, session: SessionContext):
        self._session = session

    def needs_resolution(self, request: str) -> bool:
        """Fast check: does the request contain anything resolvable?"""
        lower = request.lower()
        return any([
            _PERSON_PRONOUNS.search(lower),
            _PROJECT_REFS.search(lower),
            _MILESTONE_REFS.search(lower),
            _TASK_REFS.search(lower),
            _GENERIC_PRONOUNS.search(lower),
            _CONTINUATION.search(lower),
            _WHAT_ARE_WE.search(lower),
            _WHO_ARE_WE.search(lower),
        ])

    def resolve(self, request: str) -> Resolution:
        """
        Attempt resolution. Returns Resolution with original unchanged.
        Only resolves if confidence >= MIN_RESOLUTION_CONFIDENCE.
        """
        # Status queries
        if _WHAT_ARE_WE.search(request):
            return self._resolve_what_are_we(request)
        if _WHO_ARE_WE.search(request):
            return self._resolve_who(request)

        # Continuation
        if _CONTINUATION.search(request) and not _GENERIC_PRONOUNS.search(request):
            return self._resolve_continuation(request)

        # Person pronouns — highest specificity
        if _PERSON_PRONOUNS.search(request):
            r = self._resolve_person_pronoun(request)
            if r.resolved:
                return r

        # Named references
        if _PROJECT_REFS.search(request):
            return self._resolve_named(request, _PROJECT_REFS,
                                       self._session.active_project, "project", 0.90)
        if _MILESTONE_REFS.search(request):
            return self._resolve_named(request, _MILESTONE_REFS,
                                       self._session.active_milestone, "milestone", 0.90)
        if _TASK_REFS.search(request):
            return self._resolve_named(request, _TASK_REFS,
                                       self._session.active_task, "task", 0.90)

        # Generic pronouns — lowest specificity
        if _GENERIC_PRONOUNS.search(request):
            return self._resolve_generic(request)

        return Resolution(resolved=False, original=request)

    # ------------------------------------------------------------------

    def _resolve_person_pronoun(self, request: str) -> Resolution:
        slot = self._session.fresh(self._session.active_person)
        if not slot:
            # GC-009: fall back to active_topic for plural pronouns
            # (they/them) referring to pets or groups when no active person.
            topic_slot = self._session.fresh(self._session.active_topic)
            if topic_slot and self._session.is_usable(topic_slot):
                m = _PERSON_PRONOUNS.search(request)
                if m:
                    conf = min(0.90, self._session.effective_confidence(topic_slot))
                    if conf >= MIN_RESOLUTION_CONFIDENCE:
                        logger.info(
                            "[CONTEXT] Resolved pronoun %r → %r (topic fallback, conf=%.2f)",
                            m.group(1), topic_slot.value, conf,
                        )
                        return Resolution(
                            resolved=True, original=request,
                            context_hint=topic_slot.value,
                            slot_type="topic", confidence=conf,
                            pronoun=m.group(1),
                        )
            return Resolution(resolved=False, original=request)
        m = _PERSON_PRONOUNS.search(request)
        if not m:
            return Resolution(resolved=False, original=request)
        conf = min(0.95, self._session.effective_confidence(slot))
        if conf < MIN_RESOLUTION_CONFIDENCE:
            return Resolution(resolved=False, original=request)
        logger.info("[CONTEXT] Resolved pronoun %r → %r (person, conf=%.2f)",
                    m.group(1), slot.value, conf)
        return Resolution(resolved=True, original=request, context_hint=slot.value,
                          slot_type="person", confidence=conf, pronoun=m.group(1))

    def _resolve_named(self, request, pattern, slot, slot_type, base_conf) -> Resolution:
        fresh = self._session.fresh(slot)
        if not fresh:
            return Resolution(resolved=False, original=request)
        m = pattern.search(request)
        if not m:
            return Resolution(resolved=False, original=request)
        conf = min(base_conf, self._session.effective_confidence(fresh))
        if conf < MIN_RESOLUTION_CONFIDENCE:
            return Resolution(resolved=False, original=request)
        logger.info("[CONTEXT] Resolved %r → %r (%s, conf=%.2f)",
                    m.group(0), fresh.value, slot_type, conf)
        return Resolution(resolved=True, original=request, context_hint=fresh.value,
                          slot_type=slot_type, confidence=conf, pronoun=m.group(0))

    def _resolve_generic(self, request: str) -> Resolution:
        """Resolve it/this/that to the freshest, most confident slot."""
        candidates = [
            (self._session.active_task,      "task"),
            (self._session.active_milestone,  "milestone"),
            (self._session.active_project,    "project"),
            (self._session.active_topic,      "topic"),
            (self._session.active_person,     "person"),
        ]
        best_slot, best_type, best_conf = None, "", 0.0
        for slot, slot_type in candidates:
            ec = self._session.effective_confidence(slot)
            if self._session.is_usable(slot) and ec > best_conf:
                best_slot, best_type, best_conf = slot, slot_type, ec

        if not best_slot:
            return Resolution(resolved=False, original=request)
        conf = min(0.70, best_conf)
        if conf < MIN_RESOLUTION_CONFIDENCE:
            return Resolution(resolved=False, original=request)
        m = _GENERIC_PRONOUNS.search(request)
        pronoun = m.group(0) if m else ""
        logger.info("[CONTEXT] Resolved generic %r → %r (%s, conf=%.2f)",
                    pronoun, best_slot.value, best_type, conf)
        return Resolution(resolved=True, original=request, context_hint=best_slot.value,
                          slot_type=best_type, confidence=conf, pronoun=pronoun)

    def _resolve_continuation(self, request: str) -> Resolution:
        slot = (self._session.fresh(self._session.active_task) or
                self._session.fresh(self._session.active_milestone) or
                self._session.fresh(self._session.active_project))
        if not slot:
            return Resolution(resolved=False, original=request)
        conf = min(0.80, self._session.effective_confidence(slot))
        if conf < MIN_RESOLUTION_CONFIDENCE:
            return Resolution(resolved=False, original=request)
        logger.info("[CONTEXT] Continuation → %r (conf=%.2f)", slot.value, conf)
        return Resolution(resolved=True, original=request, context_hint=slot.value,
                          slot_type="continuation", confidence=conf)

    def _resolve_what_are_we(self, request: str) -> Resolution:
        parts = []
        if s := self._session.fresh(self._session.active_task):
            parts.append(f"working on {s.value}")
        elif s := self._session.fresh(self._session.active_project):
            parts.append(f"working on {s.value}")
        if not parts:
            return Resolution(resolved=False, original=request)
        hint = "We are " + " and ".join(parts) + "."
        return Resolution(resolved=True, original=request, context_hint=hint,
                          slot_type="status", confidence=0.95)

    def _resolve_who(self, request: str) -> Resolution:
        slot = self._session.fresh(self._session.active_person)
        if not slot:
            return Resolution(resolved=False, original=request)
        return Resolution(resolved=True, original=request, context_hint=slot.value,
                          slot_type="person", confidence=0.95)