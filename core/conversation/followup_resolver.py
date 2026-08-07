"""
Follow-up Resolver — Genesis-042 Sprint-003

Detects follow-up requests like:
    "tell me another one"
    "can you explain that differently"
    "give me one more"
    "what else?"
    "say that again"

and resolves them using the last turn's context.

No AI. Pure pattern matching + session context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.conversation.session_context import SessionContext


@dataclass
class FollowUpResult:
    is_followup:    bool
    resolved_type:  str   = ""   # "repeat", "another", "rephrase", "expand"
    context_hint:   str   = ""   # what we think they're following up on
    suggested_prompt: str = ""   # rewritten prompt for the AI


# Patterns that signal a follow-up request
_ANOTHER_RE = re.compile(
    r"\b(another one|one more|tell me another|give me another|"
    r"another joke|more jokes?|keep going|next one)\b",
    re.IGNORECASE,
)
_REPHRASE_RE = re.compile(
    r"\b(explain that differently|say that differently|"
    r"can you rephrase|rephrase that|explain that again|"
    r"in simpler terms|simplify that|dumbed? down)\b",
    re.IGNORECASE,
)
_REPEAT_RE = re.compile(
    r"^(what did you say|say that again|repeat that|"
    r"what was that|can you repeat)\??$",
    re.IGNORECASE,
)
_EXPAND_RE = re.compile(
    r"\b(tell me more|more details?|expand on that|"
    r"what else|go on|continue|elaborate)\b",
    re.IGNORECASE,
)
_SHORTER_RE = re.compile(
    r"\b(make it shorter|too long|summarise that|"
    r"shorten that|brief(?:er)?|tldr|tl;dr)\b",
    re.IGNORECASE,
)


class FollowUpResolver:
    """
    Detects and resolves follow-up references using session context.

    Public API:
        resolve(request, session) -> FollowUpResult
    """

    def resolve(self, request: str, session: SessionContext) -> FollowUpResult:
        """
        Check if request is a follow-up and resolve it.

        Args:
            request: The user's raw message.
            session: Current SessionContext with last_intent etc.

        Returns:
            FollowUpResult with is_followup=True if this is a follow-up.
        """
        req = request.strip()

        # Repeat last response
        if _REPEAT_RE.match(req):
            if session.last_response:
                return FollowUpResult(
                    is_followup=True,
                    resolved_type="repeat",
                    context_hint=session.last_topic or "last response",
                    suggested_prompt=""  # agent returns last_response directly
                )

        # Another one (same type as last)
        if _ANOTHER_RE.search(req):
            topic = session.last_topic or session.last_intent or "joke"
            return FollowUpResult(
                is_followup=True,
                resolved_type="another",
                context_hint=topic,
                suggested_prompt=f"Tell me another {topic}. Just give me the {topic} directly, no preamble or questions."
            )

        # Rephrase / explain differently
        if _REPHRASE_RE.search(req):
            if session.last_response:
                return FollowUpResult(
                    is_followup=True,
                    resolved_type="rephrase",
                    context_hint=session.last_topic or "last explanation",
                    suggested_prompt=(
                        f"Please explain this differently, in simpler terms:\n"
                        f"{session.last_response[:300]}"
                    )
                )

        # Make shorter
        if _SHORTER_RE.search(req):
            if session.last_response:
                return FollowUpResult(
                    is_followup=True,
                    resolved_type="shorter",
                    context_hint=session.last_topic or "last response",
                    suggested_prompt=(
                        f"Please give a much shorter version of this:\n"
                        f"{session.last_response[:300]}"
                    )
                )

        # Expand / tell me more
        if _EXPAND_RE.search(req):
            topic = session.last_topic or session.last_intent or "that topic"
            return FollowUpResult(
                is_followup=True,
                resolved_type="expand",
                context_hint=topic,
                suggested_prompt=f"Tell me more about {topic}. Be direct and concise."
            )

        return FollowUpResult(is_followup=False)
