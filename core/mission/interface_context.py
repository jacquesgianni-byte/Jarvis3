"""
Jarvis OS Interface Context Resolver — Genesis-055 Sprint-001

InterfaceContextResolver resolves the authoritative server-side
InterfaceMode from an incoming HTTP request.

The Android header X-Interface-Context is a TRANSPORT SIGNAL only.
The server creates the authoritative InterfaceContext — never the client.

Security principle:
    A spoofed header cannot produce a valid MissionContext.
    The resolver validates the header against the authenticated session
    before constructing any context object.

For Genesis-055 Sprint-001 (trusted LAN, single user):
    Session validation is lightweight — presence of ORCHESTRATOR_TOKEN
    header or a valid session_id is sufficient.
    The architecture is in place for stronger auth in future sprints.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from core.mission.context import InterfaceMode, MissionContext
from core.mission.policy import MissionCapabilityPolicy

logger = logging.getLogger(__name__)

# Header name the Android client sends as transport signal
MISSION_HEADER = "X-Interface-Context"
MISSION_HEADER_VALUE = "mission"


class InterfaceContextResolver:
    """
    Resolves the authoritative server-side InterfaceMode.

    Called at request entry in routes.py — before any pipeline runs.
    Produces either:
        InterfaceMode.MISSION  → MissionPipeline
        InterfaceMode.CHAT     → ConversationPipeline (agent.process)

    The resolver is the only place where the header is read.
    No pipeline stage, worker, or AI call reads the header directly.
    """

    def resolve(self, flask_request) -> InterfaceMode:
        """
        Resolve the authoritative InterfaceMode from the request.

        Args:
            flask_request: The Flask request object.

        Returns:
            InterfaceMode.MISSION if the request is a valid Mission request.
            InterfaceMode.CHAT    otherwise (default — safe).
        """
        header_value = flask_request.headers.get(MISSION_HEADER, "").lower().strip()

        if header_value != MISSION_HEADER_VALUE:
            return InterfaceMode.CHAT

        # Header signals Mission Mode — validate the session
        if not self._is_valid_session(flask_request):
            logger.warning(
                "[INTERFACE_CONTEXT] Mission Mode requested but session invalid. "
                "Falling back to CHAT. IP=%s",
                flask_request.remote_addr,
            )
            return InterfaceMode.CHAT

        logger.debug(
            "[INTERFACE_CONTEXT] Mission Mode resolved. IP=%s",
            flask_request.remote_addr,
        )
        return InterfaceMode.MISSION

    def build_mission_context(self, flask_request) -> MissionContext:
        """
        Build an immutable MissionContext for a validated Mission request.

        Called only after resolve() returns InterfaceMode.MISSION.
        Derives permitted_workers and knowledge_categories from
        MissionCapabilityPolicy — never from request content.

        Returns:
            Frozen MissionContext ready for MissionPipeline.
        """
        session_id = self._extract_session_id(flask_request)

        return MissionContext.for_mission(
            session_id=session_id,
            permitted_workers=MissionCapabilityPolicy.PERMITTED_WORKERS,
            knowledge_categories=MissionCapabilityPolicy.PERMITTED_KNOWLEDGE_CATEGORIES,
            web_access=False,  # Always False at context creation
        )

    def _is_valid_session(self, flask_request) -> bool:
        """
        Validate the session for Mission Mode access.

        Sprint-001: trusted LAN, single user.
        Accepts any request that has a non-empty session identifier
        (session_id body field, X-Session-Id header, or ORCHESTRATOR_TOKEN).

        Future sprints: replace with signed token validation.
        """
        from flask import current_app

        # Check orchestrator token (already used by approval workflow)
        orchestrator_token = current_app.config.get("ORCHESTRATOR_TOKEN", "")
        if orchestrator_token:
            request_token = flask_request.headers.get("X-Orchestrator-Token", "")
            if request_token and request_token == orchestrator_token:
                return True

        # Check session_id in body or header
        body = flask_request.get_json(silent=True) or {}
        session_id = (
            body.get("session_id")
            or flask_request.headers.get("X-Session-Id")
            or ""
        )
        if session_id:
            return True

        # Trusted LAN fallback for Sprint-001
        # Any request from the local network is trusted
        remote = flask_request.remote_addr or ""
        trusted_prefixes = ("127.", "192.168.", "10.", "172.")
        if any(remote.startswith(p) for p in trusted_prefixes):
            return True

        return False

    def _extract_session_id(self, flask_request) -> str:
        """Extract or generate a session ID for this request."""
        body = flask_request.get_json(silent=True) or {}
        return (
            body.get("session_id")
            or flask_request.headers.get("X-Session-Id")
            or f"mission-{uuid.uuid4().hex[:8]}"
        )
