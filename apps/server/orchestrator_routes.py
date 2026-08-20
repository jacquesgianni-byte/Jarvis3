"""
Genesis-053 Sprint-001 — Orchestrator Flask Routes

Authenticated endpoints for the Development Orchestrator approval workflow.

Endpoints:
    GET  /orchestrator/status
        Returns all sessions currently AWAITING_APPROVAL.
        Response: {"sessions": [...], "count": int}

    POST /orchestrator/approve
        Approve or reject a suspended session.
        Body: {
            "session_id": str,
            "decision":   "approve" | "reject",
            "decided_by": str (optional, default "ludovic"),
            "reason":     str (optional, required for reject)
        }
        Response: {"ok": bool, "message": str, "session_id": str}

Authentication:
    Header: X-Orchestrator-Token: <value>
    Value must match ORCHESTRATOR_TOKEN environment variable.
    Returns 401 if header is missing or token does not match.
    Returns 403 if ORCHESTRATOR_TOKEN is not set (safety: fail closed).
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

orchestrator_bp = Blueprint("orchestrator", __name__)

_TOKEN_ENV_VAR = "ORCHESTRATOR_TOKEN"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _check_auth() -> bool:
    """
    Return True if the request carries a valid orchestrator token.

    Fails closed: if ORCHESTRATOR_TOKEN is not set in the environment,
    all requests are rejected regardless of what header is sent.
    """
    expected = os.getenv(_TOKEN_ENV_VAR, "")
    if not expected:
        logger.warning(
            "[ORCHESTRATOR] %s not set — all requests rejected (fail-closed).",
            _TOKEN_ENV_VAR,
        )
        return False
    provided = request.headers.get("X-Orchestrator-Token", "")
    return provided == expected


def _unauthorized(message: str = "Unauthorized"):
    return jsonify({"ok": False, "error": message}), 401


def _coordinator():
    """Return the EngineeringCoordinator from app config, or None."""
    return current_app.config.get("ORCHESTRATOR_COORDINATOR")


# ---------------------------------------------------------------------------
# GET /orchestrator/status
# ---------------------------------------------------------------------------

@orchestrator_bp.route("/orchestrator/status", methods=["GET"])
def orchestrator_status():
    """
    Return all sessions currently awaiting approval.

    Authentication: X-Orchestrator-Token header required.
    """
    if not _check_auth():
        return _unauthorized()

    coord = _coordinator()
    if coord is None:
        return jsonify({
            "ok":      True,
            "sessions": [],
            "count":    0,
            "warning":  "No coordinator registered — orchestrator not active",
        })

    try:
        sessions = coord.suspended_sessions()
        return jsonify({
            "ok":      True,
            "sessions": sessions,
            "count":    len(sessions),
        })
    except Exception as exc:
        logger.exception("[ORCHESTRATOR] /status failed.")
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /orchestrator/approve
# ---------------------------------------------------------------------------

@orchestrator_bp.route("/orchestrator/approve", methods=["POST"])
def orchestrator_approve():
    """
    Approve or reject a suspended session.

    Authentication: X-Orchestrator-Token header required.
    Body (JSON): {session_id, decision, decided_by?, reason?}
    """
    if not _check_auth():
        return _unauthorized()

    body = request.get_json(silent=True) or {}

    session_id = body.get("session_id", "").strip()
    decision   = body.get("decision", "").strip().lower()
    decided_by = body.get("decided_by", "ludovic").strip()
    reason     = body.get("reason", "").strip()

    if not session_id:
        return jsonify({"ok": False, "error": "session_id is required"}), 400

    if decision not in ("approve", "reject"):
        return jsonify({
            "ok":    False,
            "error": "decision must be 'approve' or 'reject'",
        }), 400

    if decision == "reject" and not reason:
        return jsonify({
            "ok":    False,
            "error": "reason is required for rejection",
        }), 400

    coord = _coordinator()
    if coord is None:
        return jsonify({"ok": False, "error": "No coordinator registered"}), 503

    try:
        result = coord.resume_session(
            session_id=session_id,
            decision=decision,
            decided_by=decided_by,
            reason=reason,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("[ORCHESTRATOR] /approve failed for session %s", session_id[:8])
        return jsonify({"ok": False, "error": str(exc)}), 500

    if result is None:
        return jsonify({
            "ok":        False,
            "error":     "Session not found or not awaiting approval",
            "session_id": session_id,
        }), 404

    return jsonify({
        "ok":        True,
        "message":   f"Session {session_id[:8]}… {decision}d by {decided_by!r}",
        "session_id": session_id,
        "outcome":   result.status.value,
    })


# ---------------------------------------------------------------------------
# POST /orchestrator/coordinate
# ---------------------------------------------------------------------------

@orchestrator_bp.route("/orchestrator/coordinate", methods=["POST"])
def orchestrator_coordinate():
    """
    Submit an engineering request to the coordinator.
    Creates a new session and suspends it awaiting approval.

    Authentication: X-Orchestrator-Token header required.
    Body (JSON): {"request": str}
    Response: {"ok": bool, "session_id": str, "status": str, "plan_summary": dict}
    """
    if not _check_auth():
        return _unauthorized()

    body = request.get_json(silent=True) or {}
    engineering_request = body.get("request", "").strip()

    if not engineering_request:
        return jsonify({"ok": False, "error": "request is required"}), 400

    coord = _coordinator()
    if coord is None:
        return jsonify({"ok": False, "error": "No coordinator registered"}), 503

    try:
        from core.engineering.coordinator.models import EngineeringRequest
        req = EngineeringRequest(request=engineering_request)
        result = coord.coordinate(req)
    except Exception as exc:
        logger.exception("[ORCHESTRATOR] /coordinate failed.")
        return jsonify({"ok": False, "error": str(exc)}), 500

    # Find plan_summary from suspended sessions if available
    plan_summary = {"available": False}
    if result.session_id:
        try:
            sessions = coord.suspended_sessions()
            match = next((s for s in sessions if s["session_id"] == result.session_id), None)
            if match:
                plan_summary = match.get("plan_summary", plan_summary)
        except Exception:
            pass

    return jsonify({
        "ok":          True,
        "session_id":  result.session_id,
        "status":      result.status.value,
        "plan_summary": plan_summary,
        "errors":      result.errors,
        "warnings":    result.warnings,
    })
