"""
Genesis-064 Sprint-003c -- Sprint Approval Flask Routes

Endpoints for the three-layer sprint approval workflow.
All state transitions go through SprintStateMachine -- no separate logic here.

Endpoints:
    POST /sprint/propose
        Trigger sprint proposal generation from evidence.
        Body: {} (no body required)
        Response: {"ok": bool, "proposal_id": str, "proposal": str, "state": str}

    POST /sprint/approve-plan
        Layer 1: Chief approves the proposed sprint plan.
        Body: {"proposal_id": str}
        Response: {"ok": bool, "from": str, "to": str, "error": str}

    POST /sprint/approve-execution
        Layer 2: Chief explicitly authorises execution to begin.
        Body: {"proposal_id": str}
        Response: {"ok": bool, "from": str, "to": str, "error": str}

    POST /sprint/review-result
        Layer 3: Chief accepts or rejects the sprint result.
        Body: {"proposal_id": str, "decision": "accept"|"reject"}
        Response: {"ok": bool, "from": str, "to": str, "error": str}

    GET /sprint/status/<proposal_id>
        Return current sprint state.
        Response: {"ok": bool, "status": {...}}

Authentication:
    Header: X-Orchestrator-Token: <value>
    Same token as orchestrator routes (ORCHESTRATOR_TOKEN env var).
    Fails closed: if token not set, all requests rejected.

State machine invariant:
    Every transition is validated by SprintStateMachine.
    The API has no separate transition logic.
    An invalid transition (e.g. PROPOSED -> EXECUTING) is rejected by the
    state machine regardless of which endpoint is called.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

logger = logging.getLogger(__name__)

sprint_bp = Blueprint("sprint", __name__)

_TOKEN_ENV_VAR = "ORCHESTRATOR_TOKEN"


# ---------------------------------------------------------------------------
# Authentication -- same pattern as orchestrator_routes
# ---------------------------------------------------------------------------

def _check_auth() -> bool:
    expected = os.getenv(_TOKEN_ENV_VAR, "")
    if not expected:
        logger.warning("[SPRINT] %s not set -- all requests rejected.", _TOKEN_ENV_VAR)
        return False
    provided = request.headers.get("X-Orchestrator-Token", "")
    return provided == expected


def _auth_error():
    return jsonify({"ok": False, "error": "Unauthorised"}), 401


# ---------------------------------------------------------------------------
# POST /sprint/propose
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/propose", methods=["POST"])
def propose_sprint():
    """
    Trigger sprint proposal generation from stored evidence.
    The SprintProposalEngine derives the proposal -- no body required.
    Returns the proposal text and initial PROPOSED state.
    """
    if not _check_auth():
        return _auth_error()

    try:
        # Build proposal via SprintProposalEngine directly
        from core.knowledge.sprint_proposal import SprintProposalEngine, InsufficientEvidenceResult
        from core.knowledge.sprint_state import SprintStateStore
        from core.mission.investigation_registry import InvestigationRegistry
        from core.knowledge.genesis_record import GenesisDeliveryStore
        from core.knowledge.capability_gap import GapObservationStore

        project_root  = current_app.config.get("project_root")
        gap_store     = current_app.config.get("gap_store")
        sprint_store  = current_app.config.get("sprint_state_store")

        if not all([project_root, gap_store, sprint_store]):
            return jsonify({"ok": False, "error": "Sprint infrastructure not available."}), 503

        inv_registry   = InvestigationRegistry(project_root)
        delivery_store = GenesisDeliveryStore(project_root)

        engine = SprintProposalEngine(gap_store, inv_registry, delivery_store, project_root)
        result = engine.propose()

        if isinstance(result, InsufficientEvidenceResult):
            return jsonify({
                "ok":      False,
                "error":   "insufficient_evidence",
                "message": result.format_for_mission(),
                "gap_observation_count": result.gap_observation_count,
                "required_count":        result.required_count,
            }), 200

        # Create PROPOSED state record and store proposal for background execution
        record = sprint_store.create(result.proposal_id)
        record.stored_proposal = result.to_dict()
        sprint_store._persist(record)
        logger.info("[SPRINT] stored_proposal persisted for %s", result.proposal_id)

        return jsonify({
            "ok":          True,
            "proposal_id": result.proposal_id,
            "proposal":    result.format_for_approval(),
            "state":       "proposed",
            "template":    result.template_id,
        }), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/propose error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /sprint/approve-plan  (Layer 1)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/approve-plan", methods=["POST"])
def approve_plan():
    """
    Layer 1: Chief approves the proposed sprint plan.
    Transitions PROPOSED -> APPROVED via SprintStateMachine.
    Rejected if current state is not PROPOSED.
    """
    if not _check_auth():
        return _auth_error()

    body        = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id", "").strip()
    if not proposal_id:
        return jsonify({"ok": False, "error": "proposal_id required"}), 400

    try:
        from core.knowledge.sprint_state import SprintStateStore, SprintState
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        result = sprint_store.transition(
            proposal_id  = proposal_id,
            to_state     = SprintState.APPROVED,
            reason       = "Chief approved the sprint plan via /sprint/approve-plan (Layer 1).",
            chief_action = True,
        )
        return jsonify({
            "ok":    result.success,
            "from":  result.from_state,
            "to":    result.to_state,
            "error": result.error,
        }), 200 if result.success else 409

    except Exception as e:
        logger.exception("[SPRINT] /sprint/approve-plan error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /sprint/approve-execution  (Layer 2)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/approve-execution", methods=["POST"])
def approve_execution():
    """
    Layer 2: Chief explicitly authorises execution.
    Transitions APPROVED -> EXECUTING via SprintStateMachine.
    Rejected if current state is not APPROVED.
    Nothing executes until this endpoint is called.
    After transition, triggers SprintExecutor in background thread.
    """
    if not _check_auth():
        return _auth_error()

    body        = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id", "").strip()
    if not proposal_id:
        return jsonify({"ok": False, "error": "proposal_id required"}), 400

    try:
        from core.knowledge.sprint_state import SprintStateStore, SprintState
        from core.knowledge.sprint_proposal import SprintProposalEngine, InsufficientEvidenceResult
        from core.knowledge.genesis_record import GenesisDeliveryStore
        from core.mission.investigation_registry import InvestigationRegistry

        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        # Transition to EXECUTING -- state machine enforces this
        result = sprint_store.transition(
            proposal_id  = proposal_id,
            to_state     = SprintState.EXECUTING,
            reason       = "Chief authorised execution via /sprint/approve-execution (Layer 2).",
            chief_action = True,
        )

        if not result.success:
            return jsonify({
                "ok":    False,
                "from":  result.from_state,
                "to":    result.to_state,
                "error": result.error,
            }), 409

        # Retrieve stored proposal and execute in background
        project_root = current_app.config.get("project_root")
        gap_store    = current_app.config.get("gap_store")

        if project_root and gap_store:
            import threading
            t = threading.Thread(
                target=_run_sprint_execution,
                args=(proposal_id, project_root, sprint_store, gap_store),
                daemon=True,
            )
            t.start()

        return jsonify({
            "ok":    True,
            "from":  result.from_state,
            "to":    result.to_state,
            "error": "",
            "message": "Execution started in background. Use /sprint/status to monitor.",
        }), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/approve-execution error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


def _run_sprint_execution(proposal_id: str, project_root, sprint_store, gap_store):
    """
    Background thread: execute the approved sprint.
    Uses SprintProposalEngine to re-derive the proposal (it is deterministic),
    then SprintExecutor to run the declared steps.
    Records results in SprintStateStore.
    Never auto-advances beyond VALIDATING -- Layer 3 requires Chief action.
    """
    try:
        from core.knowledge.sprint_proposal import SprintProposalEngine
        from core.knowledge.sprint_executor import SprintExecutor
        from core.knowledge.sprint_state import SprintState
        from core.mission.investigation_registry import InvestigationRegistry
        from core.knowledge.genesis_record import GenesisDeliveryStore

        # Load stored proposal from sprint state instead of re-deriving
        # Re-deriving is unreliable as the capability surface may have changed
        import json as _json
        state_path = sprint_store._path_for(proposal_id)
        proposal = None
        if state_path.exists():
            state_data = _json.loads(state_path.read_text(encoding="utf-8"))
            stored = state_data.get("stored_proposal")
            if stored:
                from core.knowledge.sprint_proposal import (
                    BoundSprintProposal, ProposalStep, AcceptanceCriterion
                )
                try:
                    steps = tuple(ProposalStep(
                        step_number=s["step_number"],
                        description=s["description"],
                        action_type=s["action_type"],
                        parameters=tuple(map(tuple, s["parameters"])),
                    ) for s in stored.get("steps", []))
                    criteria = tuple(AcceptanceCriterion(
                        description=c["description"],
                        criterion_type=c["criterion_type"],
                        test_input=c["test_input"],
                        expected_outcome=c["expected_outcome"],
                        guaranteed_by=c["guaranteed_by"],
                    ) for c in stored.get("acceptance_criteria", []))
                    proposal = BoundSprintProposal(
                        proposal_id=stored["proposal_id"],
                        created_at=stored["created_at"],
                        template_id=stored["template_id"],
                        proposed_sprint_name=stored["proposed_sprint_name"],
                        rationale=stored["rationale"],
                        evidence_summary=stored["evidence_summary"],
                        gap_observation_count=stored["gap_observation_count"],
                        recurring_question=stored["recurring_question"],
                        steps=steps,
                        acceptance_criteria=criteria,
                        not_doing=tuple(stored.get("not_doing", [])),
                        evidence_sources=tuple(stored.get("evidence_sources", [])),
                    )
                except Exception as e:
                    logger.warning("[SPRINT] Could not restore proposal: %s", e)

        if proposal is None:
            sprint_store.transition(
                proposal_id=proposal_id,
                to_state=SprintState.FAILED,
                reason="Could not load stored proposal for execution.",
                chief_action=False,
            )
            return

        executor   = SprintExecutor(proposal, project_root)
        success, step_results = executor.execute()

        # Record execution trace
        record = sprint_store.load(proposal_id)
        if record:
            record.execution_trace = [
                {"step": r.step_number, "action": r.action_type,
                 "success": r.success, "detail": r.detail,
                 "commit_sha": r.commit_sha}
                for r in step_results
            ]
            sprint_store._persist(record)

        if not success:
            sprint_store.transition(
                proposal_id=proposal_id,
                to_state=SprintState.FAILED,
                reason=f"Execution failed at step {step_results[-1].step_number if step_results else 0}.",
                chief_action=False,
            )
            return

        # Move to VALIDATING -- desktop validation runs
        sprint_store.transition(
            proposal_id=proposal_id,
            to_state=SprintState.VALIDATING,
            reason="Execution complete -- running desktop validation.",
            chief_action=False,
        )

        # Desktop validation (bounded)
        validation_result = _run_desktop_validation(proposal, project_root)

        # Record validation result
        record = sprint_store.load(proposal_id)
        if record:
            record.validation_result = {
                "passed":   validation_result.get("passed", False),
                "detail":   validation_result.get("detail", ""),
            }
            sprint_store._persist(record)

        # Move to AWAITING_RESULT_REVIEW -- Chief must review
        commit_sha = next((r.commit_sha for r in reversed(step_results) if r.commit_sha), "")
        val_passed = validation_result.get("passed", False)
        val_reason = validation_result.get("failure_reason", "")
        summary = (
            f"Execution: {'SUCCESS' if success else 'FAILED'}. "
            f"Steps: {len(step_results)}. "
            f"Commit: {commit_sha}. "
            f"Desktop validation: {'PASS' if val_passed else 'FAIL'}."
            + (f" Reason: {val_reason}" if val_reason else "")
        )
        sprint_store.transition(
            proposal_id=proposal_id,
            to_state=SprintState.AWAITING_RESULT_REVIEW,
            reason="Validation complete -- awaiting Chief review (Layer 3).",
            chief_action=False,
        )

        logger.info("[SPRINT] %s ready for Chief review. Summary: %s", proposal_id, summary)

    except Exception as e:
        logger.exception("[SPRINT] Background execution error for %s: %s", proposal_id, e)
        try:
            from core.knowledge.sprint_state import SprintState
            sprint_store.transition(
                proposal_id=proposal_id,
                to_state=SprintState.FAILED,
                reason=f"Unhandled execution error: {e}",
                chief_action=False,
            )
        except Exception:
            pass


def _run_desktop_validation(proposal, project_root) -> dict:
    """
    Genesis-065 Sprint-002: Run bounded desktop validation.
    Returns full structured diagnostics dict from DesktopValidationResult.
    """
    try:
        from core.knowledge.sprint_executor import DesktopValidationRunner
        import sys

        desktop_criteria = [
            c for c in proposal.acceptance_criteria
            if c.criterion_type in ("proximity_nonzero", "record_exists")
        ]

        if not desktop_criteria:
            return {
                "passed": True,
                "detail": "No desktop validation criterion declared.",
                "failure_reason": "",
            }

        criterion = desktop_criteria[0]

        if criterion.criterion_type == "proximity_nonzero":
            expected_contains = "score"
        elif criterion.criterion_type == "record_exists":
            expected_contains = criterion.test_input
        else:
            expected_contains = criterion.expected_outcome

        class Spec:
            command           = " ".join([sys.executable, "-m", "apps.desktop.main"])
            criterion_type    = criterion.criterion_type
            test_message      = criterion.test_input
            expected_outcome  = criterion.expected_outcome
            expected_contains = expected_contains_val
            timeout_seconds   = 30

        runner = DesktopValidationRunner(project_root)
        result = runner.run(Spec())

        logger.info(
            "[SPRINT] Desktop validation: passed=%s process_ready=%s http=%s "
            "criterion=%s elapsed=%.1fs reason=%r",
            result.passed, result.process_ready, result.http_status,
            result.criterion_met, result.elapsed_seconds, result.failure_reason,
        )

        return result.to_dict()

    except Exception as e:
        logger.exception("[SPRINT] _run_desktop_validation error: %s", e)
        return {
            "passed": False,
            "detail": f"Desktop validation error: {e}",
            "failure_reason": f"Infrastructure failure: {e}",
        }

# ---------------------------------------------------------------------------
# POST /sprint/review-result  (Layer 3)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/review-result", methods=["POST"])
def review_result():
    """
    Layer 3: Chief accepts or rejects the sprint result.
    Transitions AWAITING_RESULT_REVIEW -> COMPLETED or REJECTED.
    Rejected if current state is not AWAITING_RESULT_REVIEW.
    """
    if not _check_auth():
        return _auth_error()

    body        = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id", "").strip()
    decision    = body.get("decision", "").strip().lower()

    if not proposal_id:
        return jsonify({"ok": False, "error": "proposal_id required"}), 400
    if decision not in ("accept", "reject"):
        return jsonify({"ok": False, "error": "decision must be accept or reject"}), 400

    try:
        from core.knowledge.sprint_state import SprintStateStore, SprintState
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        to_state = SprintState.COMPLETED if decision == "accept" else SprintState.REJECTED
        reason   = (
            f"Chief accepted the sprint result via /sprint/review-result (Layer 3)."
            if decision == "accept"
            else f"Chief rejected the sprint result via /sprint/review-result (Layer 3)."
        )

        result = sprint_store.transition(
            proposal_id  = proposal_id,
            to_state     = to_state,
            reason       = reason,
            chief_action = True,
        )
        return jsonify({
            "ok":    result.success,
            "from":  result.from_state,
            "to":    result.to_state,
            "error": result.error,
        }), 200 if result.success else 409

    except Exception as e:
        logger.exception("[SPRINT] /sprint/review-result error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /sprint/acknowledge  (Genesis-065 Sprint-001)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/acknowledge", methods=["POST"])
def acknowledge_sprint():
    """
    Genesis-065 Sprint-001: Chief acknowledges a terminal sprint result.
    Sets chief_acknowledged=True on the SprintStateRecord and persists.
    Idempotent -- acknowledging an already-acknowledged sprint is a no-op.
    Only valid for terminal states (COMPLETED, FAILED, INTERRUPTED, REJECTED).
    """
    if not _check_auth():
        return _auth_error()

    body        = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id", "").strip()
    if not proposal_id:
        return jsonify({"ok": False, "error": "proposal_id required"}), 400

    try:
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        record = sprint_store.load(proposal_id)
        if record is None:
            return jsonify({"ok": False, "error": f"No sprint found for {proposal_id!r}"}), 404

        if not record.is_terminal:
            return jsonify({
                "ok":    False,
                "error": f"Sprint {proposal_id!r} is in state {record.current_state!r} -- "
                         f"only terminal sprints can be acknowledged.",
            }), 409

        if record.chief_acknowledged:
            # Already acknowledged -- idempotent success
            return jsonify({"ok": True, "proposal_id": proposal_id, "already_acknowledged": True}), 200

        record.chief_acknowledged = True
        sprint_store._persist(record)
        logger.info("[SPRINT] %s acknowledged by Chief.", proposal_id)

        return jsonify({"ok": True, "proposal_id": proposal_id, "already_acknowledged": False}), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/acknowledge error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /sprint/status/<proposal_id>
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/status/<proposal_id>", methods=["GET"])
def sprint_status(proposal_id: str):
    """
    Return current sprint state for a proposal_id.
    Used by Android to poll status between layers.
    """
    if not _check_auth():
        return _auth_error()

    try:
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        record = sprint_store.load(proposal_id)
        if record is None:
            return jsonify({"ok": False, "error": f"No sprint found for {proposal_id!r}"}), 404

        return jsonify({
            "ok": True,
            "status": {
                "proposal_id":      record.proposal_id,
                "current_state":    record.current_state,
                "requires_chief":   record.requires_chief_action,
                "is_terminal":      record.is_terminal,
                "transition_count": len(record.transitions),
                "transitions":      record.transitions[-5:],  # last 5 only
                "execution_trace":  record.execution_trace,
                "validation_result": record.validation_result,
                "result_summary":   record.result_summary,
            }
        }), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/status error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500