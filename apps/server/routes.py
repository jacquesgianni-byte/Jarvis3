"""
Jarvis API Routes

Thin wrappers around Agent.process(). No business logic lives here.
Every route translates HTTP -> Agent -> JSON and nothing more.

Stable response envelope:
    {
        "success": bool,
        "message": str,
        "processing": bool
    }

Sprint-003: Persistent Sessions
    Each client sends an optional session_id header or body field.
    The server maintains conversation context per session.
    Knowledge is shared. Conversation state is session-specific.
"""
from __future__ import annotations

import logging
import time
import uuid
from flask import current_app, jsonify, request

logger = logging.getLogger(__name__)

_processing = False

# Session store: session_id -> conversation context snapshot
# For Android Alpha, one session is sufficient.
# Future: session_id per client (Android, Desktop, Web, CLI)
_sessions: dict = {}
_DEFAULT_SESSION = "android-alpha"


def _agent():
    """Retrieve the shared Agent from app config."""
    return current_app.config["AGENT"]


def _get_session_id() -> str:
    """
    Extract session_id from request body or header.
    Defaults to a single shared session for Android Alpha.
    """
    body = request.get_json(silent=True) or {}
    return (
        body.get("session_id")
        or request.headers.get("X-Session-Id")
        or _DEFAULT_SESSION
    )


def _restore_session(agent, session_id: str) -> None:
    """Restore conversation context for a session."""
    if session_id not in _sessions:
        return
    ctx = _sessions[session_id]
    try:
        # Restore recent conversation context
        if ctx.get("last_user_message"):
            agent.context.last_user_message = ctx["last_user_message"]
        if ctx.get("last_jarvis_response"):
            agent.context.last_jarvis_response = ctx["last_jarvis_response"]
        if ctx.get("active_topic") and agent.session:
            agent.session.set_topic(ctx["active_topic"], raw=ctx["active_topic"])
        if ctx.get("recent_entities"):
            agent._recent_entities = ctx["recent_entities"]
    except Exception as e:
        logger.warning("[SESSION] Restore failed for %s: %s", session_id, e)


def _save_session(agent, session_id: str) -> None:
    """Save conversation context after a request."""
    try:
        active_topic = None
        if agent.session and agent.session.active_topic:
            active_topic = agent.session.active_topic.value

        _sessions[session_id] = {
            "last_user_message": agent.context.last_user_message,
            "last_jarvis_response": agent.context.last_jarvis_response,
            "active_topic": active_topic,
            "recent_entities": list(agent._recent_entities),
            "last_updated": time.time(),
        }
    except Exception as e:
        logger.warning("[SESSION] Save failed for %s: %s", session_id, e)


def _envelope(success: bool, message: str, processing: bool = False) -> dict:
    """
    Build the stable JSON response envelope.
    Fields are fixed so clients never need to handle structural changes.
    Extend by adding optional keys -- never remove or rename existing ones.
    """
    return {
        "success": success,
        "message": message,
        "processing": processing,
    }


def register_routes(app) -> None:
    """Attach all routes to the Flask app."""


    def _system_registry():
        return current_app.config.get("SYSTEM_REGISTRY")

    def _session_registry():
        return current_app.config.get("SESSION_REGISTRY")

    @app.route("/system", methods=["GET"])
    def system():
        """Live system state. Used by Android dashboard and heartbeat."""
        sr = _system_registry()
        if sr is None:
            return jsonify({"status": "online", "version": "0.1-alpha"}), 200
        data = sr.system_dict()
        data["latency_ms"] = 0  # filled in by client
        return jsonify(data), 200

    @app.route("/engineering", methods=["GET"])
    def engineering():
        """Live engineering state."""
        sr = _system_registry()
        if sr is None:
            return jsonify({"current_genesis": "Android Alpha"}), 200
        return jsonify(sr.engineering_dict()), 200

    @app.route("/session", methods=["GET"])
    def session_log():
        """Today's operational event log."""
        sr = _session_registry()
        if sr is None:
            return jsonify([]), 200
        return jsonify(sr.all_events()), 200

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        """Combined system + engineering snapshot for the dashboard."""
        sys_r = _system_registry()
        if sys_r is None:
            return jsonify({"status": "online"}), 200
        data = {
            "system":      sys_r.system_dict(),
            "engineering": sys_r.engineering_dict(),
        }
        return jsonify(data), 200

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify(_envelope(
            success=True,
            message="Jarvis is online.",
        )), 200

    @app.route("/chat", methods=["POST"])
    def chat():
        global _processing

        body = request.get_json(silent=True)
        if not body or "message" not in body:
            return jsonify(_envelope(
                success=False,
                message="Request body must include a 'message' field.",
            )), 400

        user_message = str(body["message"]).strip()
        if not user_message:
            return jsonify(_envelope(
                success=False,
                message="Message cannot be empty.",
            )), 400

        session_id = _get_session_id()
        agent = _agent()

        _processing = True
        start = time.perf_counter()
        try:
            # Restore conversation context for this session
            _restore_session(agent, session_id)

            response = agent.process(user_message)

            # Log to session registry
            try:
                sr = _session_registry()
                if sr:
                    sr.log_conversation()
            except Exception:
                pass

            # Save updated conversation context
            _save_session(agent, session_id)

            elapsed = time.perf_counter() - start
            logger.info(
                "[CHAT] %.0fms | session=%s | success=%s",
                elapsed * 1000, session_id, response.success
            )
            return jsonify(_envelope(
                success=response.success,
                message=response.message,
            )), 200

        except Exception:
            logger.exception("[CHAT] Agent.process() raised an exception.")
            return jsonify(_envelope(
                success=False,
                message="An internal error occurred. Please try again.",
            )), 500
        finally:
            _processing = False

    @app.route("/interrupt", methods=["POST"])
    def interrupt():
        logger.info("[INTERRUPT] Interrupt requested.")
        return jsonify(_envelope(
            success=True,
            message="Interrupt acknowledged.",
        )), 200

    @app.route("/status", methods=["GET"])
    def status():
        return jsonify({
            **_envelope(
                success=True,
                message="Status retrieved.",
                processing=_processing,
            ),
            "agent_ready": _agent() is not None,
            "active_sessions": len(_sessions),
        }), 200
