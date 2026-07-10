"""
Conversation Context

Stores the current state of an active Jarvis conversation.
This dataclass is the single source of truth for what Jarvis
knows about the ongoing interaction at any point in time.

It has no behaviour — it only holds data.
Other modules read from and write to it.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationContext:
    """
    Represents the current state of a Jarvis conversation.

    Passed between modules to share conversational awareness
    without tight coupling. All fields are optional — not every
    conversation will have all values populated.

    Attributes:
        topic:               The current subject being discussed.
        last_intent:         The last detected intent from the router.
        last_skill:          The name of the last skill that was invoked.
        pending_question:    A question Jarvis has asked and is waiting on.
        pending_action:      An action Jarvis proposed but has not yet executed.
        last_user_message:   The most recent message received from the user.
        last_jarvis_response: The most recent response Jarvis produced.
    """

    topic: Optional[str] = field(default=None)
    last_intent: Optional[str] = field(default=None)
    last_skill: Optional[str] = field(default=None)
    pending_question: Optional[str] = field(default=None)
    pending_action: Optional[str] = field(default=None)
    last_user_message: Optional[str] = field(default=None)
    last_jarvis_response: Optional[str] = field(default=None)

    def has_pending_interaction(self) -> bool:
        """
        Return True if Jarvis is waiting for a user response.

        Returns:
            True if there is a pending question or pending action.
        """

        return self.pending_question is not None or self.pending_action is not None

    def clear_pending(self) -> None:
        """
        Clear any pending question or action.

        Called after a pending interaction has been resolved —
        either confirmed, denied, or answered.
        """

        self.pending_question = None
        self.pending_action = None

    def reset(self) -> None:
        """
        Reset the context to its initial empty state.

        Used when starting a new conversation topic or
        after a conversation has concluded.
        """

        self.topic = None
        self.last_intent = None
        self.last_skill = None
        self.pending_question = None
        self.pending_action = None
        self.last_user_message = None
        self.last_jarvis_response = None