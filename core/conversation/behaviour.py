"""
Conversation Behaviour

The decision layer between Conversation Intelligence and the Agent.

Determines whether an incoming message is a continuation of a pending
interaction, or whether normal intent routing should proceed.

This module does not generate user-facing language, execute skills,
call AI providers, or modify context.

It returns a ConversationDecision if the interaction is handled,
or None if normal routing should continue.
"""

import logging
from typing import Optional

from core.conversation.context import ConversationContext
from core.conversation.decision import ConversationDecision, ConversationOutcome
from core.conversation.intelligence import MessageCategory

logger = logging.getLogger(__name__)


class ConversationBehaviour:
    """
    Determines how an incoming message should be handled in context.

    Sits between ConversationIntelligence and the Agent router.
    If this class handles the message, it returns a ConversationDecision.
    If normal routing should proceed, it returns None.

    This class has no side effects. It does not modify context, execute
    skills, call AI providers, or generate user-facing language.
    Language is the Agent's responsibility.

    Example usage:
        behaviour = ConversationBehaviour()
        decision = behaviour.handle(MessageCategory.CONFIRMATION, context)

        if decision is not None:
            # Conversation was handled — Agent translates to Response.
            return agent.respond_to_decision(decision)

        # Normal routing proceeds.
        intent = router.detect(request)
    """

    def handle(
        self,
        category: MessageCategory,
        context: ConversationContext
    ) -> Optional[ConversationDecision]:
        """
        Determine whether this message is part of a pending interaction.

        Inspects the message category and current context to decide
        whether the conversation should be handled here or passed to
        the normal intent router.

        Args:
            category: The MessageCategory returned by ConversationIntelligence.
            context:  The current ConversationContext.

        Returns:
            A ConversationDecision if the interaction is handled here.
            None if normal routing should continue.
        """

        if not context.has_pending_interaction():
            logger.debug(
                "No pending interaction — passing to normal routing."
            )
            return None

        if category == MessageCategory.CONFIRMATION:
            return self._decide(ConversationOutcome.CONFIRMED, context)

        if category == MessageCategory.DENIAL:
            return self._decide(ConversationOutcome.DENIED, context)

        if category == MessageCategory.CLARIFICATION:
            return self._decide(ConversationOutcome.CLARIFICATION, context)

        if category == MessageCategory.CONTINUATION:
            return self._decide(ConversationOutcome.CONTINUATION, context)

        # SELECTION and NORMAL fall through to standard routing.
        logger.debug(
            "Category %s with pending interaction — passing to normal routing.",
            category.name
        )
        return None

    def _decide(
        self,
        outcome: ConversationOutcome,
        context: ConversationContext
    ) -> ConversationDecision:
        """
        Build a ConversationDecision from the current context and outcome.

        Args:
            outcome: The ConversationOutcome that describes what happened.
            context: The current ConversationContext.

        Returns:
            A ConversationDecision carrying the outcome and pending state.
        """

        logger.debug(
            "Conversation handled — outcome: %s, pending_action: %r, pending_question: %r",
            outcome.name,
            context.pending_action,
            context.pending_question
        )

        return ConversationDecision(
            handled=True,
            outcome=outcome,
            pending_action=context.pending_action,
            pending_question=context.pending_question
        )