"""
Jarvis Conversation Engine Exceptions (Genesis-022 Sprint-001)

All conversation engine exceptions inherit from ConversationError
so callers can catch the entire family with a single except clause.
"""


class ConversationError(Exception):
    """Base class for all conversation engine errors."""


class InvalidInputError(ConversationError):
    """Raised when input is empty, None, or otherwise unusable."""


class NoDecisionError(ConversationError):
    """
    Raised when the pipeline completes without producing a Decision.
    Should never happen in production — indicates a pipeline misconfiguration.
    """


class SlotError(ConversationError):
    """Base class for slot-related errors."""


class SlotNotFoundError(SlotError):
    """Raised when a slot is looked up by name but does not exist."""


class SlotAlreadyFilledError(SlotError):
    """Raised when fill() is called on a slot that is already filled."""


class TopicError(ConversationError):
    """Base class for topic-related errors."""


class NoActiveTopicError(TopicError):
    """Raised when topic context is required but no topic is active."""


class PolicyViolationError(ConversationError):
    """
    Raised when a component attempts to dispatch work directly.
    Only ConversationRouter may produce a Decision.
    """


class RecoveryError(ConversationError):
    """Raised when recovery handling fails unexpectedly."""


class PipelineError(ConversationError):
    """Raised when the conversation pipeline encounters an unrecoverable error."""