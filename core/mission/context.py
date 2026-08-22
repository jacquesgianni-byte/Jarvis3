"""
Jarvis OS Mission Context — Genesis-055 Sprint-001

MissionContext is the frozen, immutable execution context for Mission Mode.
Created server-side at request entry. Never mutated — capability escalation
produces a new instance.

InterfaceMode identifies the resolved server-side context.
The Android header X-Interface-Context is a transport signal only;
the server resolves the authoritative InterfaceMode from the session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InterfaceMode(Enum):
    """Authoritative server-side interface context."""
    CHAT    = "chat"     # General conversation pipeline
    MISSION = "mission"  # Mission Mode — capability-restricted pipeline
    UNKNOWN = "unknown"  # Default — no valid context resolved


@dataclass(frozen=True)
class MissionContext:
    """
    Immutable execution context for a single Mission Mode request.

    Created at request entry by InterfaceContextResolver.
    Passed through MissionPipeline unchanged.

    Capability escalation (e.g. web access authorisation) requires
    constructing a new MissionContext — this instance cannot be mutated.

    frozen=True: any attempted field mutation raises FrozenInstanceError
    at the Python level — not a soft warning, a hard exception.
    """
    session_id:           str
    interface_mode:       InterfaceMode
    permitted_workers:    frozenset          # derived from MissionCapabilityPolicy
    knowledge_categories: frozenset          # Tier 1 only
    web_access:           bool        = False
    web_authorised_at:    Optional[str] = None   # ISO timestamp if authorised
    web_session_id:       Optional[str] = None   # session that authorised
    created_at:           str         = ""

    @classmethod
    def for_mission(
        cls,
        session_id: str,
        permitted_workers: frozenset,
        knowledge_categories: frozenset,
        web_access: bool = False,
        web_authorised_at: Optional[str] = None,
        web_session_id: Optional[str] = None,
    ) -> "MissionContext":
        """
        Construct a MissionContext for an active Mission Mode session.
        Called by InterfaceContextResolver — not by pipeline stages.
        """
        import datetime
        return cls(
            session_id=session_id,
            interface_mode=InterfaceMode.MISSION,
            permitted_workers=permitted_workers,
            knowledge_categories=knowledge_categories,
            web_access=web_access,
            web_authorised_at=web_authorised_at,
            web_session_id=web_session_id,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def with_web_access(self, authorised_by: str) -> "MissionContext":
        """
        Return a NEW MissionContext with web_access=True.
        This instance is unchanged.
        Called only from the server-side authorisation handler —
        never from pipeline stages or AI workers.
        """
        import datetime
        return MissionContext(
            session_id=self.session_id,
            interface_mode=self.interface_mode,
            permitted_workers=self.permitted_workers,
            knowledge_categories=self.knowledge_categories,
            web_access=True,
            web_authorised_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            web_session_id=authorised_by,
            created_at=self.created_at,
        )

    def without_web_access(self) -> "MissionContext":
        """
        Return a NEW MissionContext with web_access=False.
        Called when Mission session ends or Gianni revokes access.
        """
        return MissionContext(
            session_id=self.session_id,
            interface_mode=self.interface_mode,
            permitted_workers=self.permitted_workers,
            knowledge_categories=self.knowledge_categories,
            web_access=False,
            web_authorised_at=None,
            web_session_id=None,
            created_at=self.created_at,
        )
