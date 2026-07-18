"""
Jarvis Projection Interface (Genesis-020 Sprint-003 — Polish Pass)

Defines the generic Projection ABC that any read model can implement
to receive and process timeline events.

Design:
    This is the bridge between the immutable event log (Timeline)
    and any derived state (SessionContext, KnowledgeEngine, Workers).

    Timeline  →  replay(projection)  →  Projection.apply(event)
                                              ↓
                                         derived state

Constitutional constraints:
    - This is the interface only. No implementations here.
    - Implementations live in their own modules (SessionContext,
      Workers, etc.) and depend on this ABC — not the reverse.
    - No event bus, no Worker coordination — those belong in Genesis-021.
    - Backwards compatible: existing Timeline code is unchanged.

Usage:
    class MyProjection(Projection):
        def apply(self, event: TimelineEvent) -> None:
            if event.event_type == EventType.START_PROJECT:
                self.project = event.value

    projection = MyProjection()
    timeline.replay(projection)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.timeline_event import TimelineEvent


class Projection(ABC):
    """
    Generic interface for any read model built from timeline events.

    Implement `apply(event)` to process each event during replay.
    The Timeline calls apply() for every event in turn order.

    Projections are stateful by design — they accumulate state
    as events are applied. They are never the source of truth;
    the Timeline is.

    Future (Genesis-021):
        Workers will implement Projection to reconstruct their
        world view by replaying the Timeline without parameter passing.
    """

    @abstractmethod
    def apply(self, event: "TimelineEvent") -> None:
        """
        Process a single timeline event.

        Called by ConversationTimeline.replay() in turn order.
        Implementations should be deterministic — the same sequence
        of events always produces the same state.

        Args:
            event: The TimelineEvent to process. Never None.
        """
        ...

    def on_replay_complete(self) -> None:
        """
        Called by replay() after all events have been applied.

        Override to perform any post-replay finalisation.
        Default implementation is a no-op.
        """
        pass