"""
Conversation Decision

Describes the outcome of a conversation behaviour evaluation.

This model is returned by ConversationBehaviour instead of a user-facing
Response. It communicates what happened in the conversation without
generating any language — that responsibility belongs to the Agent.

Separation of concerns:
    ConversationBehaviour  — decides what happened
    ConversationDecision   — carries that decision
    Agent                  — translates the decision into user-facing language
    Response               — delivers the final message to the user
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class ConversationOutcome(Enum):
    """
    The outcome of a conversation behaviour evaluation.

    Outcomes:
        CONFIRMED:
            The user confirmed a pending action or question.

        DENIED:
            The user denied or cancelled a pending action or question.

        CLARIFICATION:
            The user asked for clarification about a pending interaction.

        CONTINUATION:
            The user signalled they want to continue the current interaction.
    """

    CONFIRMED = auto()
    DENIED = auto()
    CLARIFICATION = auto()
    CONTINUATION = auto()


@dataclass(slots=True)
class ConversationDecision:
    """
    Result returned by ConversationBehaviour.

    Describes what happened in the conversation without
    generating any user-facing language.

    Attributes:
        handled:
            True if ConversationBehaviour handled this message.
            False if normal Agent routing should proceed.

        outcome:
            The ConversationOutcome describing what happened.
            None when no conversational decision was made.

        pending_action:
            The pending action that was being resolved, if any.

        pending_question:
            The pending question that was being resolved, if any.
    """

    handled: bool
    outcome: ConversationOutcome | None = None
    pending_action: Optional[str] = None
    pending_question: Optional[str] = None