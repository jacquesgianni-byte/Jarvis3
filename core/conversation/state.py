"""
Conversation State

Defines the possible states of a Jarvis conversation at any point in time.
Used by the ConversationIntelligence and router to determine how an
incoming message should be handled.

State transitions are managed externally — this module only defines the states.
"""

from enum import Enum, auto


class ConversationState(Enum):
    """
    Represents the current phase of a Jarvis conversation.

    States:
        IDLE:
            No active conversation. Jarvis is waiting for a new request.
            Default state at startup and after a conversation concludes.

        WAITING_FOR_CONFIRMATION:
            Jarvis has proposed an action and is waiting for the user
            to confirm or deny it.
            Example: "Shall I build and install JarvisApp, sir?"

        WAITING_FOR_INFORMATION:
            Jarvis has asked a question and needs the user to provide
            specific information before proceeding.
            Example: "Which project would you like me to open, sir?"

        WAITING_FOR_SELECTION:
            Jarvis has presented multiple options and is waiting for
            the user to choose one.
            Example: "I found three matches. Which one did you mean, sir?"

        EXECUTING:
            Jarvis is currently performing a task. The user's input
            during this state may be interpreted as a cancellation request.

        FINISHED:
            The current task or conversation has completed.
            Jarvis will transition back to IDLE after acknowledging.
    """

    IDLE = auto()
    WAITING_FOR_CONFIRMATION = auto()
    WAITING_FOR_INFORMATION = auto()
    WAITING_FOR_SELECTION = auto()
    EXECUTING = auto()
    FINISHED = auto()