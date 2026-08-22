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
from core.conversation.interface_source import InterfaceSource  # Genesis-047 Sprint-002
from core.mission.context import InterfaceMode                  # Genesis-055 Sprint-001
from core.mission.interface_context import InterfaceContextResolver  # Genesis-055 Sprint-001
from core.mission.pipeline import MissionRequest                # Genesis-055 Sprint-001

_interface_resolver = InterfaceContextResolver()

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
        if ctx.get("active_topic") and agent.session:
            agent.session.set_topic(ctx["active_topic"], raw=ctx["active_topic"])
        if ctx.get("recent_entities"):
            agent._recent_entities = ctx["recent_entities"]
        if ctx.get("last_intent"):
            try:
                agent.session.last_intent = ctx["last_intent"]
            except Exception:
                pass
        if ctx.get("last_topic"):
            try:
                agent.session.last_topic = ctx["last_topic"]
            except Exception:
                pass
        # FIX-1: Restore full ConversationState (entity_registry, active slots, etc.)
        if ctx.get("jarvis_state") is not None:
            try:
                saved_state = ctx["jarvis_state"]
                # Genesis-044 Sprint-002: self.session IS jarvis_state directly.
                # Re-pointing agent.jarvis_state is sufficient â€” no adapter to update.
                agent.jarvis_state = saved_state
                agent.session = saved_state
            except Exception as e:
                logger.warning("[SESSION] jarvis_state restore failed: %s", e)
    except Exception as e:
        logger.warning("[SESSION] Restore failed for %s: %s", session_id, e)


def _save_session(agent, session_id: str) -> None:
    """Save conversation context after a request."""
    try:
        active_topic = None
        if agent.session and agent.session.active_topic:
            active_topic = agent.session.active_topic.value

        _sessions[session_id] = {
            "last_user_message":   agent.context.last_user_message,
            "active_topic":        active_topic,
            "recent_entities":     list(agent._recent_entities),
            "last_updated":        time.time(),
            "last_intent":         agent.session.last_intent or "",
            "last_topic":          agent.session.last_topic or "",
            # FIX-1: Persist full ConversationState across requests
            "jarvis_state":        agent.jarvis_state,
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


    @app.route("/plugins", methods=["GET"])
    def plugins():
        """Plugin ecosystem status. Read-only diagnostic endpoint."""
        agent = _agent()
        loader = getattr(agent, "plugin_loader", None)
        if loader is None:
            return jsonify({"loaded": [], "failed": [], "note": "PluginLoader not available"}), 200

        loaded = [
            {
                "name":        r.metadata.name,
                "version":     r.metadata.version,
                "description": r.metadata.description,
                "workers":     list(r.worker_names),
            }
            for r in loader.loaded_plugins()
        ]
        failed = [
            {
                "name":  r.plugin_name,
                "error": r.error,
            }
            for r in loader.failed_plugins()
        ]
        return jsonify({"loaded": loaded, "failed": failed}), 200

    @app.route("/session", methods=["GET"])
    def session_log():
        """Today's operational event log."""
        sr = _session_registry()
        if sr is None:
            return jsonify([]), 200
        return jsonify(sr.all_events()), 200

    @app.route("/dashboard", methods=["GET"])
    def dashboard():
        """Combined system + engineering + mission snapshot for the dashboard."""
        sys_r     = _system_registry()
        mission_r = current_app.config.get("MISSION_REGISTRY")
        if sys_r is None:
            return jsonify({"status": "online"}), 200
        data = {
            "system":      sys_r.system_dict(),
            "engineering": sys_r.engineering_dict(),
            "mission":     mission_r.mission_dict() if mission_r is not None else {},
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

        # Genesis-055 Sprint-001: server-side interface context resolution
        # Header is transport signal only -- server is authoritative.
        interface_mode = _interface_resolver.resolve(request)

        if interface_mode == InterfaceMode.MISSION:
            mission_pipeline = current_app.config.get("MISSION_PIPELINE")
            if mission_pipeline is not None:
                mission_context = _interface_resolver.build_mission_context(request)
                mission_request = MissionRequest(
                    message=user_message,
                    session_id=mission_context.session_id,
                    context=mission_context,
                )
                mission_response = mission_pipeline.process(mission_request)
                return jsonify(_envelope(
                    success=mission_response.success,
                    message=mission_response.message,
                )), 200
            # Mission pipeline not available -- fail closed, not CHAT fallback
            return jsonify(_envelope(
                success=False,
                message="Mission Mode pipeline is not available.",
            )), 503

        session_id = _get_session_id()
        agent = _agent()

        _processing = True
        start = time.perf_counter()
        try:
            # Restore conversation context for this session
            _restore_session(agent, session_id)

            response = agent.process(user_message, source=InterfaceSource.HTTP)  # Genesis-047 Sprint-002

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


    # â”€â”€ File Upload endpoint (File Intelligence Sprint) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    @app.route("/upload", methods=["POST"])
    def upload():
        """
        Accept a file upload from Android.
        Multipart form: file=<bytes>, message=<optional str>
        Returns: upload_id, filename, detected_type, readable, prompt_context
        """
        from apps.server.document_intake.document_intake import DocumentIntake

        if "file" not in request.files:
            return jsonify(_envelope(
                success=False,
                message="No file field in request.",
            )), 400

        f         = request.files["file"]
        filename  = f.filename or "upload"
        mime_type = f.content_type or ""
        user_msg  = request.form.get("message", "").strip()

        try:
            file_bytes = f.read()
            intake     = DocumentIntake()
            result     = intake.process(file_bytes, filename, mime_type)
        except ValueError as e:
            return jsonify(_envelope(success=False, message=str(e))), 400
        except Exception as e:
            logger.exception("[UPLOAD] DocumentIntake failed.")
            return jsonify(_envelope(success=False, message=f"Upload failed: {e}")), 500

        # Route file content directly to AI, bypassing intent routing
        agent_reply = None
        if result.context.is_readable:
            try:
                session_id = _get_session_id()
                agent = _agent()
                _restore_session(agent, session_id)

                # Build a clear AI-directed prompt with file content
                attachment_context = result.context.to_prompt_context()
                user_instruction = user_msg if user_msg else "Please analyse this file and give me a summary of its key points."
                combined_message = f"{user_instruction}\n\n{attachment_context}"

                # Go straight to AI â€” file content should never be intercepted
                # by intent routing (memory detector, engineering detector etc.)
                if agent.ai is not None:
                    ai_response = agent.ai.ask(combined_message)
                    agent_reply = ai_response.message
                else:
                    response = agent.process(combined_message, source=InterfaceSource.HTTP)  # Genesis-047 Sprint-002
                    agent_reply = response.message

                _save_session(agent, session_id)
            except Exception:
                logger.exception("[UPLOAD] Agent.process() failed after upload.")
                agent_reply = f"File received: {filename}. I couldn't process it right now."
        else:
            agent_reply = (
                f"I received {filename} but couldn't read it: {result.context.error}"
            )

        return jsonify({
            **_envelope(success=True, message=agent_reply or "File received."),
            "upload_id":    result.upload_id,
            "filename":     result.detected.filename,
            "detected_type": result.detected.file_type.value,
            "mime_type":    result.detected.mime_type,
            "readable":     result.context.is_readable,
        }), 200

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

