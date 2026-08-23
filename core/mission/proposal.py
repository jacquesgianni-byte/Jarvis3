"""
Jarvis OS ? Bound Proposal ? Genesis-056 Sprint-002

Typed, structured proposals produced by ReadOnlyInvestigator.
Executed only after explicit human approval via the existing approval workflow.

Security properties:
    - BoundProposal is frozen ? cannot be mutated after creation
    - ProposalOperation is an enum ? no free-form operation strings
    - Sprint-002 supports only UPDATE_PROJECT_STATE
    - BoundProposalExecutor accepts only a validated BoundProposal ? no raw instructions
    - Replay is prevented: EXECUTED proposals are rejected
    - fields are set at investigation time ? never reinterpreted at execution time

Integration:
    BoundProposal is stored in EngineeringSession.execution_plan (as dict)
    via the existing SessionStore and approval workflow.
    No parallel approval mechanism. One approval authority.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProposalOperation(Enum):
    """
    Typed operations a BoundProposal may request.
    Sprint-002: only UPDATE_PROJECT_STATE.
    Future: UPDATE_REGISTRY, RELOAD_CONFIG, etc. ? each needs its own executor.
    """
    UPDATE_PROJECT_STATE = "UPDATE_PROJECT_STATE"


class ProposalStatus(Enum):
    PENDING  = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# BoundProposal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BoundProposal:
    """
    A typed, structured, immutable proposal produced by ReadOnlyInvestigator.

    Fields are set at investigation time from evidence ? never derived
    at execution time from user input or commit messages.

    investigation_id: ties this proposal to the exact investigation that produced it.
    operation:        typed enum ? not a free-form string.
    target:           the file to be modified (relative path from project root).
    fields:           exact key/value pairs to write ? only these are written.
    status:           starts PENDING, becomes EXECUTED or REJECTED after approval.

    frozen=True: any attempted mutation raises FrozenInstanceError.
    """
    investigation_id: str
    operation:        ProposalOperation
    target:           str
    fields:           Dict[str, str]
    status:           ProposalStatus = ProposalStatus.PENDING

    def with_status(self, status: ProposalStatus) -> "BoundProposal":
        """Return a new BoundProposal with updated status. Original unchanged."""
        return BoundProposal(
            investigation_id=self.investigation_id,
            operation=self.operation,
            target=self.target,
            fields=dict(self.fields),
            status=status,
        )

    def to_dict(self) -> dict:
        return {
            "investigation_id": self.investigation_id,
            "operation":        self.operation.value,
            "target":           self.target,
            "fields":           dict(self.fields),
            "status":           self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BoundProposal":
        return cls(
            investigation_id = data["investigation_id"],
            operation        = ProposalOperation(data["operation"]),
            target           = data["target"],
            fields           = dict(data["fields"]),
            status           = ProposalStatus(data["status"]),
        )


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionResult:
    """
    Immutable record of what BoundProposalExecutor changed.
    before_after contains {field: (old_value, new_value)} for every field written.
    """
    investigation_id: str
    operation:        ProposalOperation
    target:           str
    before_after:     Dict[str, tuple]   # {field: (before, after)}
    success:          bool
    message:          str

    def format_for_mission(self) -> str:
        lines = [
            "EXECUTION COMPLETE",
            "-" * 40,
            f"Investigation: {self.investigation_id}",
            f"Operation: {self.operation.value}",
            f"Target: {self.target}",
            "",
            "Changes made:",
        ]
        for field_name, (before, after) in self.before_after.items():
            lines.append(f"  {field_name}: {before!r} -> {after!r}")
        lines += [
            "",
            f"Status: {'SUCCESS' if self.success else 'FAILED'}",
            "",
            self.message,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# BoundProposalExecutor
# ---------------------------------------------------------------------------

# The only operations this executor will run.
# No generic write path exists.
_SUPPORTED_OPERATIONS = frozenset({
    ProposalOperation.UPDATE_PROJECT_STATE,
})

class BoundProposalExecutor:
    """
    Executes a validated BoundProposal.

    Accepts only a BoundProposal object ? never a raw string instruction.
    Sprint-002: only UPDATE_PROJECT_STATE is supported.
    Writes only the fields specified in the proposal ? no others.
    Rejects proposals that are not PENDING.
    Rejects operations not in _SUPPORTED_OPERATIONS.
    Has no general-purpose file write capability.
    """

    def __init__(self, project_root: Path):
        self._root = project_root.resolve()

    def execute(self, proposal: BoundProposal) -> ExecutionResult:
        """
        Execute the proposal. Returns ExecutionResult ? never raises.

        Validates:
            1. operation is in _SUPPORTED_OPERATIONS
            2. status is PENDING (not already executed or rejected)
        Then executes the specific operation.
        """
        if proposal.operation not in _SUPPORTED_OPERATIONS:
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = f"Operation {proposal.operation.value!r} is not supported in Sprint-002.",
            )

        if proposal.status != ProposalStatus.PENDING:
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = f"Proposal is not PENDING (status={proposal.status.value}). Cannot execute.",
            )

        if proposal.operation == ProposalOperation.UPDATE_PROJECT_STATE:
            return self._execute_update_project_state(proposal)

        return ExecutionResult(
            investigation_id = proposal.investigation_id,
            operation        = proposal.operation,
            target           = proposal.target,
            before_after     = {},
            success          = False,
            message          = "No executor for this operation.",
        )

    def _execute_update_project_state(self, proposal: BoundProposal) -> ExecutionResult:
        """
        Update project_state.json with exactly the fields in proposal.fields.
        No other fields are touched.
        """
        path = (self._root / proposal.target).resolve()

        # Validate path stays within project root
        try:
            path.relative_to(self._root)
        except ValueError:
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = "Target path is outside project root. Execution refused.",
            )

        if not path.exists():
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = f"{proposal.target} not found.",
            )

        try:
            current = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as e:
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = f"Could not read {proposal.target}: {e}",
            )

        # Record before/after for exactly the proposed fields
        before_after = {}
        updated = dict(current)
        for field_name, new_value in proposal.fields.items():
            old_value = current.get(field_name, "<not set>")
            updated[field_name] = new_value
            before_after[field_name] = (old_value, new_value)

        try:
            path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
            logger.info(
                "[BoundProposalExecutor] Updated %s: %s",
                proposal.target, before_after,
            )
        except Exception as e:
            return ExecutionResult(
                investigation_id = proposal.investigation_id,
                operation        = proposal.operation,
                target           = proposal.target,
                before_after     = {},
                success          = False,
                message          = f"Could not write {proposal.target}: {e}",
            )

        return ExecutionResult(
            investigation_id = proposal.investigation_id,
            operation        = proposal.operation,
            target           = proposal.target,
            before_after     = before_after,
            success          = True,
            message          = "Changes written. Restart the server so MissionRegistry reloads the corrected state.",
        )
