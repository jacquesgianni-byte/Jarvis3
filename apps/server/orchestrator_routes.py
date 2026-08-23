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
from core.mission.proposal import BoundProposal, BoundProposalExecutor, ProposalStatus

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

        # Genesis-056 Sprint-002: also include investigation proposals
        # from SessionStore ? these are not in the coordinator's in-memory sessions
        try:
            from core.engineering.coordinator.session_store import SessionStore
            store = SessionStore()
            for session in store.load_resumable():
                plan = session.execution_plan or {}
                if "operation" in plan and plan.get("operation") == "UPDATE_PROJECT_STATE":
                    inv_id = plan.get("investigation_id", session.session_id)
                    sessions = sessions + [{
                        "session_id": session.session_id,
                        "request":    f"[INVESTIGATION] {inv_id}",
                        "stage":      "AWAITING_APPROVAL",
                        "status":     "AWAITING_APPROVAL",
                        "approved_by": "",
                        "approved_at": "",
                        "plan_summary": {
                            "operations": 1,
                            "creates":    0,
                            "modifies":   1,
                            "deletes":    0,
                            "files":      [plan.get("target", "project_state.json")],
                        },
                    }]
        except Exception as inv_exc:
            logger.warning("[ORCHESTRATOR] Could not load investigation proposals: %s", inv_exc)

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

def _try_execute_investigation_proposal(session_id, decision, decided_by, reason):
    """
    Genesis-056 Sprint-002.

    If session_id matches an INVESTIGATION_PROPOSAL in SessionStore,
    handle it via BoundProposalExecutor and return a Flask response.
    Returns None if this is not an investigation proposal (caller handles normally).
    """
    from core.engineering.coordinator.session_store import SessionStore
    from pathlib import Path

    store = SessionStore()
    session = store.load(session_id)

    if session is None:
        return None  # not found in store ? let coordinator handle

    plan = session.execution_plan or {}
    if plan.get("type") != "INVESTIGATION_PROPOSAL" and        "investigation_id" not in plan.get("metadata", {}) and        plan.get("operation") != "UPDATE_PROJECT_STATE":
        # Check execution_plan directly for proposal data
        if "operation" not in plan:
            return None  # not an investigation proposal

    # It's an investigation proposal
    try:
        proposal = BoundProposal.from_dict(plan)
    except Exception as e:
        logger.warning("[ORCHESTRATOR] Could not parse BoundProposal: %s", e)
        return None

    if decision == "reject":
        from core.engineering.coordinator.models import EngineeringStatus, EngineeringStage
        import datetime
        session.reject(
            rejected_by=decided_by,
            rejected_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            reason=reason or "Rejected via approval workflow",
        )
        store.save(session)
        return jsonify({
            "ok":        True,
            "message":   f"Investigation proposal {session_id[:8]}... rejected.",
            "session_id": session_id,
            "outcome":   "REJECTED",
        })

    # Approve ? execute via BoundProposalExecutor
    project_root = Path(__file__).resolve().parents[2]
    executor     = BoundProposalExecutor(project_root)
    result       = executor.execute(proposal)

    if result.success:
        # Mark session complete in store
        from core.engineering.coordinator.models import (
            EngineeringStatus, EngineeringStage, EngineeringResult,
        )
        import datetime
        session.approve(
            approved_by=decided_by,
            approved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        eng_result = EngineeringResult(
            status    = EngineeringStatus.COMPLETE,
            completed = True,
            plan      = result.format_for_mission(),
        )
        session.complete(eng_result)
        store.save(session)
        logger.info(
            "[ORCHESTRATOR] Investigation proposal %s executed successfully.",
            session_id[:8],
        )
    else:
        logger.warning(
            "[ORCHESTRATOR] Investigation proposal %s execution failed: %s",
            session_id[:8], result.message,
        )

    return jsonify({
        "ok":           result.success,
        "message":      result.format_for_mission(),
        "session_id":   session_id,
        "outcome":      "COMPLETE" if result.success else "FAILED",
        "before_after": {k: list(v) for k, v in result.before_after.items()},
    })


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

    # Genesis-056 Sprint-002: check if this is an investigation proposal
    # before routing to the engineering coordinator
    investigation_result = _try_execute_investigation_proposal(
        session_id=session_id,
        decision=decision,
        decided_by=decided_by,
        reason=reason,
    )
    if investigation_result is not None:
        return investigation_result

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
