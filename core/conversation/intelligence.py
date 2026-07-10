"""
Conversation Intelligence

Classifies incoming user messages based on conversational context.
Uses rule-based logic only — no AI provider calls.

This module interprets what a message means in context.
It does not execute actions, call skills, or modify state.
Classification results are consumed by the router to decide
what to do next.
"""

import logging
from enum import Enum, auto

from core.conversation.context import ConversationContext

logger = logging.getLogger(__name__)


class MessageCategory(Enum):
    """
    The interpreted category of a user message in conversational context.

    Categories:
        CONFIRMATION:
            The user is agreeing to something Jarvis proposed.
            Example: "yes", "go ahead", "do it", "sure"

        DENIAL:
            The user is refusing or cancelling something Jarvis proposed.
            Example: "no", "cancel", "never mind", "stop"

        CONTINUATION:
            The user is continuing the current topic without a new request.
            Example: "tell me more", "and?", "what else?"

        CLARIFICATION:
            The user is asking Jarvis to explain or repeat something.
            Example: "what do you mean?", "can you explain that?", "pardon?"

        SELECTION:
            The user is choosing from options Jarvis presented.
            Example: "the first one", "option 2", "the second"

        NORMAL:
            A standard new request with no special conversational meaning.
            This is the default when no other category applies.
    """

    CONFIRMATION = auto()
    DENIAL = auto()
    CONTINUATION = auto()
    CLARIFICATION = auto()
    SELECTION = auto()
    NORMAL = auto()


# Rule sets — lowercase trigger words for each category.
_CONFIRMATION_TRIGGERS = frozenset({
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay",
    "go ahead", "do it", "please do", "correct", "affirmative",
    "proceed", "absolutely", "of course", "please", "go for it",
    "yes please", "sounds good", "that's right", "confirmed",
})

_DENIAL_TRIGGERS = frozenset({
    "no", "nope", "nah", "never mind", "nevermind", "cancel",
    "stop", "forget it", "don't", "do not", "abort", "negative",
    "not now", "skip it",
})

_CONTINUATION_TRIGGERS = frozenset({
    "tell me more", "more", "continue", "go on", "and?",
    "what else", "keep going", "elaborate", "expand on that",
    "what about", "anything else",
})

_CLARIFICATION_TRIGGERS = frozenset({
    "what do you mean", "can you explain", "explain that",
    "pardon", "sorry", "what", "huh", "i don't understand",
    "clarify", "could you repeat", "say that again",
})

_SELECTION_TRIGGERS = frozenset({
    "the first", "first one", "option 1", "number 1",
    "the second", "second one", "option 2", "number 2",
    "the third", "third one", "option 3", "number 3",
    "the last", "that one", "this one",
})


class ConversationIntelligence:
    """
    Classifies user messages using rule-based conversational logic.

    Takes a message and the current ConversationContext and returns
    the most appropriate MessageCategory.

    This class has no side effects. It reads context but never modifies it.
    It never calls any AI provider, skill, or tool.

    Example usage:
        intelligence = ConversationIntelligence()
        category = intelligence.classify("yes please", context)
        # Returns MessageCategory.CONFIRMATION
    """

    def classify(
        self,
        message: str,
        context: ConversationContext
    ) -> MessageCategory:
        """
        Classify a user message in the context of the current conversation.

        Classification considers both the message content and whether
        Jarvis has a pending interaction. A message like "yes" only
        means CONFIRMATION if Jarvis is actually waiting for one.

        Args:
            message: The raw user message to classify.
            context: The current conversation context.

        Returns:
            The MessageCategory that best describes this message.
        """

        if not message or not message.strip():
            return MessageCategory.NORMAL

        normalised = message.strip().lower()

        # Only classify as confirmation or denial if Jarvis
        # has something pending — otherwise "yes" is just a normal input.
        if context.has_pending_interaction():
            if self._matches(normalised, _CONFIRMATION_TRIGGERS):
                logger.debug("Classified as CONFIRMATION: %r", message)
                return MessageCategory.CONFIRMATION

            if self._matches(normalised, _DENIAL_TRIGGERS):
                logger.debug("Classified as DENIAL: %r", message)
                return MessageCategory.DENIAL

        if self._matches(normalised, _CLARIFICATION_TRIGGERS):
            logger.debug("Classified as CLARIFICATION: %r", message)
            return MessageCategory.CLARIFICATION

        if self._matches(normalised, _CONTINUATION_TRIGGERS):
            logger.debug("Classified as CONTINUATION: %r", message)
            return MessageCategory.CONTINUATION

        if self._matches(normalised, _SELECTION_TRIGGERS):
            logger.debug("Classified as SELECTION: %r", message)
            return MessageCategory.SELECTION

        logger.debug("Classified as NORMAL: %r", message)
        return MessageCategory.NORMAL

    def _matches(self, normalised: str, triggers: frozenset) -> bool:
        """
        Return True if the normalised message matches any trigger phrase.

        Checks both exact matches and whether the message starts with
        any trigger — allowing for natural phrasing like
        "yes please go ahead" to match the "yes" trigger.

        Args:
            normalised: The lowercased, stripped user message.
            triggers:   A frozenset of trigger phrases to check against.

        Returns:
            True if any trigger matches.
        """

        if normalised in triggers:
            return True

        return any(normalised.startswith(trigger) for trigger in triggers)