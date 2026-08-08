"""
session_context.py — Genesis-043 compatibility shim.

ContextSlot and SessionContext have been migrated to:
    - ContextSlot     → core.conversation.conversation_state
    - SessionContext  → use SessionContextAdapter instead

This file re-exports both for backward compatibility during the
Genesis-043 migration period. It will be retired in Genesis-044.
"""

from core.conversation.conversation_state import ContextSlot, DECAY_TURNS, MIN_CONFIDENCE

# Re-export ContextSlot so existing imports don't break
__all__ = ["ContextSlot", "DECAY_TURNS", "MIN_CONFIDENCE", "SessionContext"]


class SessionContext:
    """
    Backward-compatibility stub.

    Genesis-043: Use SessionContextAdapter(ConversationState) instead.
    This class is retained only so existing tests that directly
    instantiate SessionContext continue to pass during migration.

    Will be retired in Genesis-044 Sprint-001.
    """

    def __init__(self):
        from core.conversation.conversation_state import ConversationState
        from core.conversation.session_context_adapter import SessionContextAdapter
        self._state   = ConversationState()
        self._adapter = SessionContextAdapter(self._state)

    def __getattr__(self, name):
        # Delegate everything to the adapter
        return getattr(self._adapter, name)

    def summary(self) -> dict:
        return self._adapter.summary()
