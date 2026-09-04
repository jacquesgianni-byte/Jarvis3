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
        # Genesis-067 Experiment 2: on successful L1 approval, trigger Claude
        # implementation planning in a background thread.
        if result.success:
            import threading as _threading
            _t = _threading.Thread(
                target=_run_claude_planning,
                args=(proposal_id, sprint_store),
                daemon=True,
            )
            _t.start()

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
            _contrib_store_1 = current_app.config.get("genesis_contribution_store")
            t = threading.Thread(
                target=_run_sprint_execution,
                args=(proposal_id, project_root, sprint_store, gap_store, _contrib_store_1),
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


# ---------------------------------------------------------------------------
# Genesis-067 Experiment 2 - Claude planning background thread
# ---------------------------------------------------------------------------

def _run_claude_planning(proposal_id: str, sprint_store):
    # Background thread: invoke ClaudeAIWorker.produce_implementation_plan().
    # On success:  Claude calls /sprint/approve-claude-plan-pending itself,
    #              transitioning APPROVED -> AWAITING_CLAUDE_APPROVAL.
    # On failure:  record an auditable contribution and transition to FAILED
    #              so Chief always sees a clear, non-silent state.
    try:
        from core.ai_workers.claude_worker import ClaudeAIWorker
        from core.knowledge.sprint_state import SprintState

        worker = ClaudeAIWorker()
        logger.info("[SPRINT] Claude planning started for %s", proposal_id)

        plan = worker.produce_implementation_plan(
            proposal_id     = proposal_id,
            server_base_url = "http://localhost:5001",
        )

        if plan.get("status") == "AWAITING_CHIEF_APPROVAL":
            logger.info(
                "[SPRINT] Claude planning complete for %s - state now AWAITING_CLAUDE_APPROVAL.",
                proposal_id,
            )
        else:
            _record_failed_claude_contribution(
                sprint_store, proposal_id,
                reason="Claude produced an INCOMPLETE_PLAN - exact_file or exact_change missing.",
            )
            sprint_store.transition(
                proposal_id  = proposal_id,
                to_state     = SprintState.FAILED,
                reason       = "Claude implementation plan was incomplete. Chief review required.",
                chief_action = False,
            )
            logger.warning(
                "[SPRINT] Claude planning INCOMPLETE for %s - sprint marked FAILED.",
                proposal_id,
            )

    except Exception as e:
        logger.exception("[SPRINT] Claude planning error for %s: %s", proposal_id, e)
        try:
            from core.knowledge.sprint_state import SprintState
            _record_failed_claude_contribution(
                sprint_store, proposal_id,
                reason=f"Claude planning raised an unhandled exception: {e}",
            )
            sprint_store.transition(
                proposal_id  = proposal_id,
                to_state     = SprintState.FAILED,
                reason       = f"Claude planning failed: {e}",
                chief_action = False,
            )
        except Exception as inner:
            logger.exception(
                "[SPRINT] Could not record Claude planning failure for %s: %s",
                proposal_id, inner,
            )


def _record_failed_claude_contribution(sprint_store, proposal_id: str, reason: str) -> None:
    # Record an auditable Claude failure contribution. Silent on error.
    try:
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        record = sprint_store.load(proposal_id)
        if record is None:
            return
        record.contributions.append({
            "contribution_id": f"CONTRIB-{_uuid.uuid4().hex[:8].upper()}",
            "parent_id":       None,
            "proposal_id":     proposal_id,
            "agent":           "claude",
            "contributed_by":  "claude_ai_worker",
            "role":            "implementation",
            "timestamp":       _dt.now(_tz.utc).isoformat(),
            "summary":         reason,
            "decision":        "FAILED",
            "evidence_refs":   [proposal_id],
            "artifact":        None,
        })
        sprint_store._persist(record)
    except Exception as e:
        logger.warning(
            "[SPRINT] Could not record failed Claude contribution for %s: %s",
            proposal_id, e,
        )


def _run_sprint_execution(proposal_id: str, project_root, sprint_store, gap_store, contribution_store=None):
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

        # Record Jarvis execution contribution
        if record:
            _commit_ref = next((r.commit_sha for r in reversed(step_results) if r.commit_sha), '')
            try:
                import uuid as _uuid2
                from datetime import datetime as _dt2, timezone as _tz2
                record.contributions.append({
                    'contribution_id': f'CONTRIB-{_uuid2.uuid4().hex[:8].upper()}',
                    'parent_id':       None,
                    'proposal_id':     proposal_id,
                    'agent':           'jarvis',
                    'contributed_by':  'jarvis',
                    'role':            'execution',
                    'timestamp':       _dt2.now(_tz2.utc).isoformat(),
                    'summary':         f'Jarvis executed {len(step_results)} step(s). '
                                       f'Success: {success}. Commit: {_commit_ref or "none"}.', 
                    'decision':        'SUCCESS' if success else 'FAILED',
                    'evidence_refs':   [proposal_id],
                    'artifact':        _commit_ref or None,
                })
                sprint_store._persist(record)
            except Exception as _ce:
                logger.warning('[SPRINT] Could not record Jarvis execution contribution: %s', _ce)

        # Genesis-070 Sprint-001: write execution outcome to GenesisContributionStore.
        # Only written on SUCCESS — never on failure (Chief governance rule).
        # genesis_id resolved from the loaded sprint record.
        if success and contribution_store is not None and record is not None:
            try:
                import json as _json2
                _state_data2  = _json2.loads(sprint_store._path_for(proposal_id).read_text(encoding="utf-8")) if sprint_store._path_for(proposal_id).exists() else {}
                _genesis_id2  = _state_data2.get("genesis_id", "") or _state_data2.get("stored_proposal", {}).get("genesis_id", "")
                if not _genesis_id2:
                    # Fallback: read from stored_proposal if nested
                    _sp2 = _state_data2.get("stored_proposal", {})
                    _genesis_id2 = _sp2.get("genesis_id", "")
                if _genesis_id2:
                    _commit_ref2 = next((r.commit_sha for r in reversed(step_results) if r.commit_sha), "")
                    _step_count  = len(step_results)
                    # Genesis-072 Sprint-001: parse suite counts from run_tests step
                    import re as _re_072
                    _passed2 = _skipped2 = _failed2 = None
                    for _sr in step_results:
                        if _sr.action_type == "run_tests" and _sr.success:
                            _mp = _re_072.search(r"(\d+) passed", _sr.detail or "")
                            if _mp: _passed2 = int(_mp.group(1))
                            _ms = _re_072.search(r"(\d+) skipped", _sr.detail or "")
                            if _ms: _skipped2 = int(_ms.group(1))
                            _mf = _re_072.search(r"(\d+) failed", _sr.detail or "")
                            if _mf: _failed2 = int(_mf.group(1))
                            break
                    _suite_str2 = (
                        f"tests_passed={_passed2} tests_skipped={_skipped2} tests_failed={_failed2 or 0}"
                        if _passed2 is not None else "suite_result=unavailable"
                    )
                    _summary2    = (
                        f"Jarvis executed {_step_count} step(s) for {_genesis_id2}. "
                        f"All steps succeeded. {_suite_str2}. "
                        f"Commit: {_commit_ref2 or 'none'}."
                    )
                    from core.knowledge.genesis_contributions import GenesisContribution
                    import uuid as _uuid3, datetime as _dt3
                    _contrib = GenesisContribution(
                        contribution_id=str(_uuid3.uuid4()),
                        genesis_id=_genesis_id2,
                        agent="jarvis",
                        role="execution",
                        summary=_summary2,
                        artifact=_commit_ref2 or proposal_id,
                        timestamp=_dt3.datetime.now(_dt3.timezone.utc).isoformat(),
                    )
                    contribution_store.append(_genesis_id2, _contrib)
                    logger.info(
                        "[SPRINT] Jarvis execution contribution written to GenesisContributionStore "
                        "for %s (commit: %s)", _genesis_id2, _commit_ref2 or "none"
                    )
                else:
                    logger.warning(
                        "[SPRINT] Could not resolve genesis_id for execution contribution "
                        "(proposal_id=%s) — skipping GenesisContributionStore write.", proposal_id
                    )
            except Exception as _gce:
                logger.warning(
                    "[SPRINT] GenesisContributionStore write failed for proposal %s: %s",
                    proposal_id, _gce
                )

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

        _ctype = criterion.criterion_type
        _tmsg  = criterion.test_input
        _eout  = criterion.expected_outcome
        _ec = _ctype  # hoist criterion type before class scope
        if _ctype == 'proximity_nonzero':
            _ec = 'score'
        elif _ctype == 'record_exists':
            _ec = _tmsg
        else:
            _ec = _eout
        class Spec:
            command           = ' '.join([sys.executable, '-m', 'apps.desktop.main'])
            criterion_type    = _ctype
            test_message      = _tmsg
            expected_outcome  = _eout
            expected_contains = _ec
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

def _record_chief_contribution(sprint_store, proposal_id: str, role: str, summary: str) -> None:
    """Write a chief approval contribution to the sprint record. Silent on failure."""
    try:
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz
        record = sprint_store.load(proposal_id)
        if record is None:
            return
        contribution = {
            "contribution_id": f"CONTRIB-{_uuid.uuid4().hex[:8].upper()}",
            "parent_id":       None,
            "proposal_id":     proposal_id,
            "agent":           "chief",
            "contributed_by":  "chief",
            "role":            role,
            "timestamp":       _dt.now(_tz.utc).isoformat(),
            "summary":         summary,
            "decision":        None,
            "evidence_refs":   [],
            "artifact":        None,
        }
        record.contributions.append(contribution)
        sprint_store._persist(record)
    except Exception as e:
        logger.warning("[SPRINT] Could not record chief contribution: %s", e)



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
        if result.success:
            _outcome = 'accepted' if decision == 'accept' else 'rejected'
            _record_chief_contribution(sprint_store, proposal_id, 'approval',
                f'Chief {_outcome} sprint result (Layer 3 -- result review).')
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
# Agent token model -- Genesis-067 Sprint-003
# ---------------------------------------------------------------------------

# Permitted roles per agent.
# Enforced at POST /sprint/contribute.
# GPT has no write access -- its token is for /sprint/handoff (GET) only.
_AGENT_ROLES = {
    "claude": {"architecture", "implementation"},
    "jarvis": {"execution", "validation", "coordination"},
    # chief contributions are written automatically on approval transitions
    # gpt has read-only access -- no write roles
}

def _resolve_agent_token() -> str | None:
    """
    Resolve which agent is making the request from the token presented.
    Returns agent name string or None if token is unknown.
    Chief token is handled by _check_auth() separately.
    """
    provided = request.headers.get("X-Agent-Token", "")
    if not provided:
        return None
    for agent in ("claude", "jarvis", "gpt"):
        env_var = f"AGENT_TOKEN_{agent.upper()}"
        token = os.getenv(env_var, "")
        if token and provided == token:
            return agent
    return None


def _check_agent_auth(permitted_agents=None) -> tuple[str | None, object | None]:
    """
    Check agent token. Returns (agent_name, None) on success or (None, error_response).
    Also accepts the Chief ORCHESTRATOR_TOKEN (maps to 'chief').
    """
    # Check chief token first
    if _check_auth():
        return "chief", None
    agent = _resolve_agent_token()
    if agent is None:
        return None, (jsonify({"ok": False, "error": "Unauthorised"}), 401)
    if permitted_agents and agent not in permitted_agents:
        return None, (jsonify({"ok": False, "error": f"Agent {agent!r} not permitted for this endpoint."}), 403)
    return agent, None


# ---------------------------------------------------------------------------
# POST /sprint/contribute  (Genesis-067 Sprint-003)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/contribute", methods=["POST"])
def contribute_to_sprint():
    """
    Genesis-067 Sprint-003: Record an agent contribution to a sprint.

    Authenticated agents (Claude, Jarvis) append a structured contribution
    to the SprintStateRecord. Contributions are append-only and role-gated.

    GPT has read-only access and cannot call this endpoint.
    Chief contributions are recorded automatically on approval transitions.

    Body:
        proposal_id:    str  (required)
        role:           str  (required -- must be in agent's permitted roles)
        summary:        str  (required -- one paragraph)
        decision:       str  (optional -- specific decision or outcome)
        evidence_refs:  list (optional -- observation IDs, commit SHAs, etc.)
        artifact:       str  (optional -- commit SHA or file path)
        parent_id:      str  (optional -- parent contribution_id)
    """
    agent, err = _check_agent_auth(permitted_agents={"claude", "jarvis", "chief"})
    if err:
        return err

    body        = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id", "").strip()
    role        = body.get("role", "").strip()
    summary     = body.get("summary", "").strip()

    if not proposal_id:
        return jsonify({"ok": False, "error": "proposal_id required"}), 400
    if not role:
        return jsonify({"ok": False, "error": "role required"}), 400
    if not summary:
        return jsonify({"ok": False, "error": "summary required"}), 400

    # Enforce role boundaries
    permitted_roles = _AGENT_ROLES.get(agent, set())
    if agent != "chief" and role not in permitted_roles:
        return jsonify({
            "ok": False,
            "error": f"Agent {agent!r} is not permitted to submit role {role!r}. "
                     f"Permitted: {sorted(permitted_roles)}",
        }), 403

    try:
        from core.knowledge.sprint_state import SprintStateStore
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz

        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        record = sprint_store.load(proposal_id)
        if record is None:
            return jsonify({"ok": False, "error": f"No sprint found for {proposal_id!r}"}), 404

        contribution_id = f"CONTRIB-{_uuid.uuid4().hex[:8].upper()}"
        # on_behalf_of: whose work this represents (e.g. 'gpt' when Chief submits GPT's review)
        on_behalf_of = body.get("on_behalf_of") or agent
        contribution = {
            "contribution_id": contribution_id,
            "parent_id":       body.get("parent_id") or None,
            "proposal_id":     proposal_id,
            "agent":           on_behalf_of,   # whose work this represents
            "contributed_by":  agent,           # who physically submitted it
            "role":            role,
            "timestamp":       _dt.now(_tz.utc).isoformat(),
            "summary":         summary,
            "decision":        body.get("decision") or None,
            "evidence_refs":   body.get("evidence_refs") or [],
            "artifact":        body.get("artifact") or None,
        }

        record.contributions.append(contribution)
        sprint_store._persist(record)

        logger.info(
            "[SPRINT] Contribution %s from agent=%s role=%s for %s",
            contribution_id, agent, role, proposal_id,
        )

        return jsonify({
            "ok":              True,
            "contribution_id": contribution_id,
            "proposal_id":     proposal_id,
            "agent":           on_behalf_of,
            "contributed_by":  agent,
            "role":            role,
        }), 201

    except Exception as e:
        logger.exception("[SPRINT] /sprint/contribute error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500




# ---------------------------------------------------------------------------
# POST /sprint/approve-claude-plan-pending  (Claude agent — internal)
# Genesis-067 Experiment 2
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/approve-claude-plan-pending", methods=["POST"])
def set_awaiting_claude_approval():
    """
    Called by ClaudeAIWorker after producing a complete implementation plan.
    Transitions APPROVED -> AWAITING_CLAUDE_APPROVAL.

    This is NOT a Chief approval endpoint. It is an internal signal from Claude
    that the plan is ready for Chief review. Auth: Claude agent token.

    Body: {"proposal_id": str}
    Response: {"ok": bool, "from": str, "to": str, "error": str}
    """
    agent, err = _check_agent_auth(permitted_agents={"claude"})
    if err:
        return err

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
            to_state     = SprintState.AWAITING_CLAUDE_APPROVAL,
            reason       = "Claude implementation plan recorded and complete — awaiting Chief approval (L-Claude gate).",
            chief_action = False,
        )
        return jsonify({
            "ok":    result.success,
            "from":  result.from_state,
            "to":    result.to_state,
            "error": result.error,
        }), 200 if result.success else 409

    except Exception as e:
        logger.exception("[SPRINT] /sprint/approve-claude-plan-pending error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------------------------------------------------------------
# POST /sprint/approve-claude-plan  (L-Claude)
# Genesis-067 Experiment 2
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/approve-claude-plan", methods=["POST"])
def approve_claude_plan():
    """
    L-Claude: Chief approves Claude's implementation plan.

    This is the gate between Claude's implementation plan and Claude's
    first write to source files. No approval here = no file modification.

    Transitions AWAITING_CLAUDE_APPROVAL -> EXECUTING via SprintStateMachine.
    ScopeEnforcer will independently verify Claude's action before any write.

    Body: {"proposal_id": str}
    Response: {"ok": bool, "from": str, "to": str, "error": str}
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
            to_state     = SprintState.EXECUTING,
            reason       = "Chief approved Claude implementation plan via /sprint/approve-claude-plan (L-Claude gate).",
            chief_action = True,
        )
        if result.success:
            project_root = current_app.config.get("project_root")
            gap_store    = current_app.config.get("gap_store")
            if project_root and gap_store:
                import threading as _threading
                _contrib_store_2 = current_app.config.get("genesis_contribution_store")
                _t = _threading.Thread(target=_run_sprint_execution, args=(proposal_id, project_root, sprint_store, gap_store, _contrib_store_2), daemon=True)
                _t.start()
        return jsonify({
            "ok":    result.success,
            "from":  result.from_state,
            "to":    result.to_state,
            "error": result.error,
        }), 200 if result.success else 409

    except Exception as e:
        logger.exception("[SPRINT] /sprint/approve-claude-plan error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------------------------------------------------------------------
# GET /sprint/handoff/<proposal_id>  (Genesis-067 Sprint-003)
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/handoff/<proposal_id>", methods=["GET"])
def sprint_handoff(proposal_id: str):
    """
    Genesis-067 Sprint-003: Structured Sprint Handoff View for GPT.

    GPT-read-token authenticated. Returns a structured summary of the sprint
    containing exactly the information GPT needs for architecture review:
    - Genesis and objective context
    - Why this sprint exists (evidence)
    - Approved scope and acceptance criteria
    - Current state
    - Previous contributions

    Does NOT expose raw stored_proposal internals or full execution traces.
    GPT receives only what is necessary for its architecture role.
    """
    # Accept GPT read token OR Chief token OR Claude/Jarvis agent tokens
    agent, err = _check_agent_auth(permitted_agents={"gpt", "claude", "jarvis", "chief"})
    if err:
        # Also try GPT read token specifically
        gpt_token = os.getenv("AGENT_TOKEN_GPT", "")
        provided  = request.headers.get("X-Agent-Token", "")
        if not gpt_token or provided != gpt_token:
            return jsonify({"ok": False, "error": "Unauthorised"}), 401
        agent = "gpt"

    try:
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        record = sprint_store.load(proposal_id)
        if record is None:
            return jsonify({"ok": False, "error": f"No sprint found for {proposal_id!r}"}), 404

        sp = record.stored_proposal or {}

        # Build structured handoff view
        steps = []
        for s in sp.get("steps", []):
            steps.append({
                "step_number": s.get("step_number"),
                "description": s.get("description"),
                "action_type": s.get("action_type"),
            })

        criteria = []
        for c in sp.get("acceptance_criteria", []):
            criteria.append({
                "description":    c.get("description"),
                "criterion_type": c.get("criterion_type"),
                "expected":       c.get("expected_outcome"),
            })

        not_doing = sp.get("not_doing", [])

        # Genesis-068 Sprint-003: resolve Genesis narrative + contributions
        _genesis_id  = sp.get("genesis_id", "")
        _delivery_store = current_app.config.get("project_root")
        _genesis_narrative = {}
        if _genesis_id and _delivery_store:
            try:
                from core.knowledge.genesis_record import GenesisDeliveryStore
                _ds = GenesisDeliveryStore(_delivery_store)
                _rec = _ds.get(_genesis_id)
                if _rec:
                    _genesis_narrative = {
                        "display_name": _rec.display_name,
                        "hypothesis":   _rec.hypothesis,
                        "outcome":      _rec.outcome,
                    }
            except Exception as _ge:
                logger.warning("[SPRINT] Could not load genesis narrative for %s: %s", _genesis_id, _ge)

        _contrib_store = current_app.config.get("genesis_contribution_store")
        _genesis_contributions = []
        if _contrib_store and _genesis_id:
            try:
                _genesis_contributions = [
                    c.to_dict() for c in _contrib_store.get_contributions(_genesis_id)
                ]
            except Exception as _ce:
                logger.warning("[SPRINT] Could not load genesis contributions for %s: %s", _genesis_id, _ce)

        handoff = {
            "ok":          True,
            "handoff_for": agent,
            "sprint": {
                "proposal_id":   proposal_id,
                "genesis_id":    sp.get("genesis_id", ""),
                "current_state": record.current_state,
                "sprint_name":   sp.get("proposed_sprint_name", ""),
                "template":      sp.get("template_id", ""),
            },
            "genesis_association": {
                "genesis_id":           sp.get("genesis_id", ""),
                "objective":            sp.get("objective_text", ""),
                "objective_score":      sp.get("objective_score", 0),
                "objective_confidence": sp.get("objective_confidence", "NONE"),
            },
            "genesis_narrative":     _genesis_narrative,
            "genesis_contributions": _genesis_contributions,
            "why_this_sprint_exists": {
                "rationale":              sp.get("rationale", ""),
                "evidence_summary":       sp.get("evidence_summary", ""),
                "gap_observation_count":  sp.get("gap_observation_count", 0),
                "recurring_question":     sp.get("recurring_question", ""),
                "evidence_sources":       sp.get("evidence_sources", []),
            },
            "approved_scope": {
                "steps":    steps,
                "not_doing": not_doing,
            },
            "acceptance_criteria": criteria,
            "contributions": record.contributions,
            "execution_summary": {
                "steps_completed": len(record.execution_trace),
                "execution_ok":    all(s.get("success") for s in record.execution_trace) if record.execution_trace else None,
                "test_result":     record.test_result,
                "validation":      {
                    "passed":         record.validation_result.get("passed") if record.validation_result else None,
                    "failure_reason": record.validation_result.get("failure_reason", "") if record.validation_result else "",
                } if record.validation_result else None,
            },
        }

        logger.info("[SPRINT] Handoff view served to agent=%s for %s", agent, proposal_id)
        return jsonify(handoff), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/handoff error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500



# ---------------------------------------------------------------------------
# GET /sprint/pending-claude-approval  (Android poll)
# Genesis-067 Experiment 2
# ---------------------------------------------------------------------------

@sprint_bp.route("/sprint/pending-claude-approval", methods=["GET"])
def pending_claude_approval():
    """
    Android polls this to find sprints in AWAITING_CLAUDE_APPROVAL state.
    Returns structured plan details so Chief can read exactly what Claude proposes
    before approving or rejecting.

    Auth: orchestrator token.
    Response: {"ok": bool, "pending": [{proposal_id, sprint_name, plan: {...}}]}
    """
    if not _check_auth():
        return _auth_error()

    try:
        from core.knowledge.sprint_state import SprintStateStore, SprintState
        sprint_store = current_app.config.get("sprint_state_store")
        if sprint_store is None:
            return jsonify({"ok": False, "error": "Sprint state store not available."}), 503

        pending = []
        for record in sprint_store.all_active():
            if record.state != SprintState.AWAITING_CLAUDE_APPROVAL:
                continue

            sp = record.stored_proposal or {}

            # Find Claude's implementation plan contribution
            plan_contribution = None
            for contrib in reversed(record.contributions):
                if contrib.get("agent") == "claude" and contrib.get("role") == "implementation":
                    plan_contribution = contrib
                    break

            pending.append({
                "proposal_id":  record.proposal_id,
                "sprint_name":  sp.get("proposed_sprint_name", ""),
                "genesis_id":   sp.get("genesis_id", ""),
                "updated_at":   record.updated_at,
                "plan": {
                    "summary":          plan_contribution.get("summary", "") if plan_contribution else "",
                    "contribution_id":  plan_contribution.get("contribution_id", "") if plan_contribution else "",
                    "artifact":         plan_contribution.get("artifact", "") if plan_contribution else "",
                },
            })

        return jsonify({"ok": True, "pending": pending}), 200

    except Exception as e:
        logger.exception("[SPRINT] /sprint/pending-claude-approval error: %s", e)
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


# ---------------------------------------------------------------------------
# Genesis read-only blueprint — Genesis-068 Sprint-003b
# ---------------------------------------------------------------------------

from flask import Blueprint as _Blueprint
genesis_bp = _Blueprint("genesis", __name__)


@genesis_bp.route("/genesis/<genesis_id>", methods=["GET"])
def get_genesis(genesis_id: str):
    """
    Read-only Genesis record endpoint for cold-entry reconstruction.

    Returns the full Genesis narrative, delivery record, and contribution log
    for the given genesis_id. No auth required — read-only public record.

    Used by cold-entry participants (GPT, Claude, Jarvis, Chief) to reconstruct
    a Genesis independently without conversational context.
    """
    from core.knowledge.genesis_record import GenesisDeliveryStore
    from flask import current_app, jsonify

    project_root = current_app.config.get("project_root")
    if project_root is None:
        return jsonify({"ok": False, "error": "project_root not configured"}), 500

    store = GenesisDeliveryStore(project_root)
    record = store.get(genesis_id)

    if record is None:
        return jsonify({
            "ok":    False,
            "error": f"No Genesis record found for {genesis_id!r}",
        }), 404

    # Genesis contributions
    contrib_store = current_app.config.get("genesis_contribution_store")
    contributions = []
    if contrib_store:
        try:
            contributions = [c.to_dict() for c in contrib_store.get_contributions(genesis_id)]
        except Exception as e:
            logger.warning("[GENESIS] Could not load contributions for %s: %s", genesis_id, e)

    # Genesis-072 Sprint-001: project last_successful_execution from contributions
    import re as _re_lse
    _last_exec = None
    for _c in reversed(contributions):
        if _c.get("agent") == "jarvis" and _c.get("role") == "execution":
            _s = _c.get("summary", "")
            _lse = {
                "agent":     "jarvis",
                "timestamp": _c.get("timestamp", ""),
                "commit":    _c.get("artifact", ""),
            }
            _mp = _re_lse.search(r"tests_passed=(\d+)", _s)
            if _mp: _lse["tests_passed"]  = int(_mp.group(1))
            _ms = _re_lse.search(r"tests_skipped=(\d+)", _s)
            if _ms: _lse["tests_skipped"] = int(_ms.group(1))
            _mf = _re_lse.search(r"tests_failed=(\d+)", _s)
            if _mf: _lse["tests_failed"]  = int(_mf.group(1))
            _last_exec = _lse
            break

    return jsonify({
        "ok":        True,
        "genesis_id": genesis_id,
        "narrative": {
            "display_name": record.display_name,
            "hypothesis":   record.hypothesis,
            "outcome":      record.outcome,
        },
        "delivery": {
            "sprints":              list(record.sprints),
            "components_delivered": list(record.components_delivered),
            "tests_added":          record.tests_added,
            "commit":               record.commit,
        },
        "last_successful_execution": _last_exec,
        "contributions": contributions,
    }), 200

# ---------------------------------------------------------------------------
# POST /genesis/contribute  (Genesis-071 Sprint-001)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory endpoints -- Genesis-073 Sprint-001 (Foundation A)
# ---------------------------------------------------------------------------

@genesis_bp.route("/memory/situational", methods=["POST"])
def memory_store():
    """
    Store a single MemoryEntry.

    Body:
        category: str  (required -- decision|question|constraint|intention|unresolved)
        content:  str  (required)

    Responses:
        201  {ok, id, category, content, timestamp}
        400  missing or invalid field
        503  store not available
        500  persist failure
    """
    from core.knowledge.situational_memory import MemoryEntry, SituationalMemoryStore
    if not _check_auth():
        return _auth_error()

    body     = request.get_json(silent=True) or {}
    category = body.get("category", "").strip()
    content  = body.get("content", "").strip()

    if not category:
        return jsonify({"ok": False, "error": "category required"}), 400
    if not content:
        return jsonify({"ok": False, "error": "content required"}), 400

    mem_store = current_app.config.get("situational_memory_store")
    if mem_store is None:
        return jsonify({"ok": False, "error": "situational_memory_store not available"}), 503

    try:
        entry = MemoryEntry.create(category=category, content=content)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        mem_store.store(entry)
    except Exception as e:
        logger.exception("[MEMORY] store failed: %s", e)
        return jsonify({"ok": False, "error": "persist failure"}), 500

    return jsonify({
        "ok":        True,
        "id":        entry.id,
        "category":  entry.category,
        "content":   entry.content,
        "timestamp": entry.timestamp,
    }), 201


@genesis_bp.route("/memory/situational", methods=["GET"])
def memory_query():
    """
    Retrieve active MemoryEntry records, optionally filtered by category.

    Query params:
        category: str  (optional)

    Responses:
        200  {ok, entries: [...], count: int}
        400  unknown category
        503  store not available
    """
    from core.knowledge.situational_memory import VALID_CATEGORIES
    if not _check_auth():
        return _auth_error()

    category = request.args.get("category", "").strip() or None
    if category and category not in VALID_CATEGORIES:
        return jsonify({
            "ok":    False,
            "error": f"Unknown category {category!r}. Valid: {sorted(VALID_CATEGORIES)}",
        }), 400

    mem_store = current_app.config.get("situational_memory_store")
    if mem_store is None:
        return jsonify({"ok": False, "error": "situational_memory_store not available"}), 503

    entries = mem_store.get_all(category=category, active_only=True)
    return jsonify({
        "ok":      True,
        "entries": [e.to_dict() for e in entries],
        "count":   len(entries),
    }), 200


@genesis_bp.route("/memory/situational/<entry_id>", methods=["PATCH"])
def memory_correct(entry_id: str):
    """
    Correct (overwrite) category and/or content of an existing MemoryEntry.
    active flag is preserved.

    Body:
        category: str  (optional)
        content:  str  (optional)

    Responses:
        200  {ok, entry: {...}}
        400  nothing to update / invalid category
        404  entry not found
        503  store not available
    """
    if not _check_auth():
        return _auth_error()

    body     = request.get_json(silent=True) or {}
    category = body.get("category", "").strip() or None
    content  = body.get("content", "").strip() or None

    if category is None and content is None:
        return jsonify({"ok": False, "error": "Provide category and/or content to correct"}), 400

    mem_store = current_app.config.get("situational_memory_store")
    if mem_store is None:
        return jsonify({"ok": False, "error": "situational_memory_store not available"}), 503

    try:
        updated = mem_store.correct(entry_id, category=category, content=content)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    if updated is None:
        return jsonify({"ok": False, "error": f"No entry found for id {entry_id!r}"}), 404

    return jsonify({"ok": True, "entry": updated.to_dict()}), 200


@genesis_bp.route("/genesis/contribute", methods=["POST"])

def genesis_contribute():
    """
    Genesis-071 Sprint-001: Record an agent contribution at Genesis scope.

    Identity is resolved server-side from X-Agent-Token (or X-Orchestrator-Token
    for Chief). No agent field is accepted in the request body.

    Authority is enforced exclusively by GenesisContributionStore._AUTHORITY_TABLE.
    This route does not duplicate or shadow that table.

    Body:
        genesis_id:  str  (required)
        role:        str  (required -- must be in _AUTHORITY_TABLE for resolved agent)
        summary:     str  (required)
        artifact:    str  (optional -- commit SHA, URL, or description; defaults to "")

    Responses:
        201  {ok, contribution_id, genesis_id, agent, role}
        400  missing required field
        401  unknown or missing token
        403  agent not permitted for requested role (_AUTHORITY_TABLE enforces)
        500  persist failure
    """
    from core.knowledge.genesis_contributions import resolve_agent_from_request

    agent = resolve_agent_from_request(request)
    if agent is None:
        return jsonify({"ok": False, "error": "Unauthorised"}), 401

    body       = request.get_json(silent=True) or {}
    genesis_id = body.get("genesis_id", "").strip()
    role       = body.get("role", "").strip()
    summary    = body.get("summary", "").strip()
    artifact   = body.get("artifact", "").strip()

    if not genesis_id:
        return jsonify({"ok": False, "error": "genesis_id required"}), 400
    if not role:
        return jsonify({"ok": False, "error": "role required"}), 400
    if not summary:
        return jsonify({"ok": False, "error": "summary required"}), 400

    contrib_store = current_app.config.get("genesis_contribution_store")
    if contrib_store is None:
        return jsonify({"ok": False, "error": "genesis_contribution_store not available"}), 503

    result = contrib_store.contribute(
        genesis_id = genesis_id,
        agent      = agent,
        role       = role,
        summary    = summary,
        artifact   = artifact,
    )

    if not result.success:
        if "not permitted" in result.error or "Unknown agent" in result.error or "may not claim" in result.error:
            return jsonify({"ok": False, "error": result.error}), 403
        return jsonify({"ok": False, "error": result.error}), 500

    logger.info(
        "[GENESIS] %s contributed %r to %s (id=%s)",
        agent, role, genesis_id, result.contribution_id[:8],
    )

    return jsonify({
        "ok":              True,
        "contribution_id": result.contribution_id,
        "genesis_id":      genesis_id,
        "agent":           agent,
        "role":            role,
    }), 201
