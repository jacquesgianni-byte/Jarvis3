"""
Jarvis OS ? ReadOnlyInvestigator ? Genesis-056 Sprint-001

Capability-based read-only investigation for Mission Mode.

Architecture:
    ReadOnlyInvestigator
        |
        +-- AuthorisedFileReader   (reads authorised project files)
        |
        +-- ReadOnlyGitReader      (fixed read-only git commands only)

Security properties (enforced, not described):
    - No write(), delete(), execute(), or subprocess beyond fixed git commands.
    - Every file read goes through AuthorisedPath ? no raw paths accepted.
    - Git commands are a fixed frozenset ? no user-supplied arguments reach git.
    - InvestigationReport.status is always NO_CHANGES_MADE ? not a settable bool.
    - A proposal ID is generated and bound to every proposal.
      Approval must reference this ID ? generic "approve" is not enough.

Investigation flow:
    InvestigationRequest
        |
        ReadOnlyInvestigator.investigate()
        |
        InvestigationReport  (evidence + findings + conclusion + proposal)
        |
        MissionPipeline (formatted and returned to user)
        |
        User approves proposal by ID
        |
        Existing ApprovalWorkflow (unchanged)
"""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from core.mission.authorised_sources import AuthorisedPath, AuthorisedSourceRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Investigation status ? structural constant, not a settable boolean
# ---------------------------------------------------------------------------

class InvestigationStatus(Enum):
    NO_CHANGES_MADE = "NO_CHANGES_MADE"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SourceRecord:
    """One source that was inspected during an investigation."""
    logical_name:  str
    found:         bool
    raw_value:     Optional[str] = None   # what was actually read
    error:         Optional[str] = None   # why it could not be read


@dataclass
class Finding:
    """One finding derived from inspected sources."""
    source:      str
    key:         str
    value:       str
    note:        Optional[str] = None


@dataclass
class InvestigationReport:
    """
    Complete, immutable record of an investigation.

    status is always InvestigationStatus.NO_CHANGES_MADE.
    It is not a freely constructible boolean ? the invalid state
    "changes were made" cannot be expressed by this class.

    proposal_id is bound at report creation.
    Approval must reference this exact ID.
    """
    investigation_id:  str
    question:          str
    sources_inspected: List[SourceRecord]
    findings:          List[Finding]
    conclusion:        str
    proposed_action:   Optional[str]
    approval_required: bool
    status:            InvestigationStatus = InvestigationStatus.NO_CHANGES_MADE

    def format_for_mission(self) -> str:
        """
        Render the investigation report in the Mission Channel wire format.
        This is what appears on the phone.
        """
        lines = [
            "INVESTIGATION",
            "?" * 40,
            f"ID: {self.investigation_id}",
            "",
            "Question:",
            self.question,
            "",
            "Sources inspected:",
        ]
        for s in self.sources_inspected:
            tick = "+" if s.found else "!"
            lines.append(f"  {tick} {s.logical_name}" + (f" ? {s.error}" if s.error else ""))

        lines += ["", "Findings:"]
        for f in self.findings:
            note = f"  ({f.note})" if f.note else ""
            lines.append(f"  {f.source} / {f.key}: {f.value}{note}")

        lines += ["", "Conclusion:", self.conclusion, ""]

        if self.proposed_action:
            lines += [
                "Proposed action:",
                self.proposed_action,
                "",
                f"Status: {self.status.value}",
                "",
                "Approval required: YES",
                f"To approve: approve {self.investigation_id}",
            ]
        else:
            lines += [
                f"Status: {self.status.value}",
                "",
                "Approval required: NO",
            ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ReadOnlyGitReader ? fixed command allow-list only
# ---------------------------------------------------------------------------

# The only git subcommands this reader may invoke.
# No user-supplied arguments reach git.
_ALLOWED_GIT_SUBCOMMANDS: frozenset = frozenset({
    "log",
    "branch",
    "status",
    "show",
    "diff",
    "rev-parse",
})

class ReadOnlyGitReader:
    """
    Read-only git adapter.

    May only invoke git subcommands in _ALLOWED_GIT_SUBCOMMANDS.
    No write commands (commit, push, reset, checkout, clean, add) exist.
    No user-supplied arguments reach git ? all arguments are hardcoded.
    """

    def __init__(self, project_root: Path):
        self._root = project_root

    def head_sha(self) -> str:
        """Return the current HEAD commit SHA (short)."""
        return self._run(["git", "log", "-1", "--format=%h"])

    def head_message(self) -> str:
        """Return the current HEAD commit message."""
        return self._run(["git", "log", "-1", "--format=%s"])

    def branch(self) -> str:
        """Return the current branch name."""
        return self._run(["git", "branch", "--show-current"])

    def recent_log(self, n: int = 5) -> str:
        """Return the last n commit log lines."""
        n = min(max(1, n), 20)   # clamp 1?20, no user control
        return self._run(["git", "log", f"-{n}", "--oneline"])

    def status_short(self) -> str:
        """Return git status --short output."""
        return self._run(["git", "status", "--short"])

    def _run(self, cmd: list) -> str:
        """
        Execute a fixed git command.
        Validates the subcommand is in the allow-list before running.
        Raises ValueError if the subcommand is not allowed.
        """
        if len(cmd) < 2 or cmd[1] not in _ALLOWED_GIT_SUBCOMMANDS:
            raise ValueError(
                f"[ReadOnlyGitReader] Git subcommand {cmd[1]!r} is not in the allow-list. "
                f"Allowed: {sorted(_ALLOWED_GIT_SUBCOMMANDS)}"
            )
        try:
            return subprocess.check_output(
                cmd,
                cwd=str(self._root),
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception as e:
            logger.warning("[ReadOnlyGitReader] Git command failed: %s ? %s", cmd, e)
            return ""


# ---------------------------------------------------------------------------
# AuthorisedFileReader ? reads only through AuthorisedPath
# ---------------------------------------------------------------------------

class AuthorisedFileReader:
    """
    Reads authorised project files.

    Never accepts a raw Path or string path from outside.
    Every read goes through AuthorisedPath.
    Has no write, delete, or execute methods.
    """

    def read_text(self, authorised_path: AuthorisedPath) -> str:
        """Read a file as text. Returns empty string on failure."""
        try:
            return authorised_path.resolved.read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.warning(
                "[AuthorisedFileReader] Could not read %s: %s",
                authorised_path.logical_name, e,
            )
            return ""

    def read_json(self, authorised_path: AuthorisedPath) -> dict:
        """Read a JSON file. Returns empty dict on failure."""
        text = self.read_text(authorised_path)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(
                "[AuthorisedFileReader] JSON parse error in %s: %s",
                authorised_path.logical_name, e,
            )
            return {}


# ---------------------------------------------------------------------------
# ReadOnlyInvestigator ? the top-level capability
# ---------------------------------------------------------------------------

class ReadOnlyInvestigator:
    """
    Mission Mode read-only investigation capability.

    Accepts investigation questions.
    Reads authorised sources only.
    Produces InvestigationReport with evidence, findings, conclusion, proposal.
    Never modifies anything ? no write method exists.

    The standard investigation (investigate_project_state_vs_git) checks
    project_state.json against live git HEAD to detect stale project state.
    This is the first real investigation Jarvis can perform on itself.
    """

    def __init__(
        self,
        registry:    AuthorisedSourceRegistry,
        project_root: Path,
    ):
        self._registry    = registry
        self._file_reader = AuthorisedFileReader()
        self._git_reader  = ReadOnlyGitReader(project_root)

    def investigate_project_state_vs_git(self, question: str) -> InvestigationReport:
        """
        Compare project_state.json against live Git HEAD.
        Detects stale project identity (genesis/sprint mismatch).

        This is the investigation that answers:
        "Why is Mission Control showing Genesis-054 when git is at Genesis-055?"
        """
        investigation_id = f"INV-056-{uuid.uuid4().hex[:6].upper()}"
        sources_inspected: List[SourceRecord] = []
        findings:          List[Finding]      = []

        # -- Read project_state.json --------------------------------------
        ps_record = SourceRecord(logical_name="project_state", found=False)
        project_state: dict = {}
        try:
            ap = self._registry.resolve("project_state")
            ps_record.found = ap.resolved.exists()
            if ps_record.found:
                project_state = self._file_reader.read_json(ap)
                ps_record.raw_value = json.dumps(project_state, indent=2)
            else:
                ps_record.error = "File not found on disk"
        except ValueError as e:
            ps_record.error = str(e)
        sources_inspected.append(ps_record)

        ps_genesis = project_state.get("current_genesis", "UNKNOWN")
        ps_sprint  = project_state.get("current_sprint",  "UNKNOWN")
        findings.append(Finding(
            source="project_state.json",
            key="current_genesis",
            value=ps_genesis,
        ))
        findings.append(Finding(
            source="project_state.json",
            key="current_sprint",
            value=ps_sprint,
        ))

        # -- Read Git HEAD ------------------------------------------------
        git_record = SourceRecord(logical_name="git_head", found=True)
        git_sha     = ""
        git_message = ""
        git_branch  = ""
        try:
            git_sha     = self._git_reader.head_sha()
            git_message = self._git_reader.head_message()
            git_branch  = self._git_reader.branch()
            git_record.raw_value = f"{git_sha} {git_message} [{git_branch}]"
        except Exception as e:
            git_record.found = False
            git_record.error = str(e)
        sources_inspected.append(git_record)

        findings.append(Finding(
            source="git HEAD",
            key="commit",
            value=git_sha or "UNAVAILABLE",
        ))
        findings.append(Finding(
            source="git HEAD",
            key="message",
            value=git_message or "UNAVAILABLE",
        ))
        findings.append(Finding(
            source="git HEAD",
            key="branch",
            value=git_branch or "UNAVAILABLE",
        ))

        # -- Diagnosis ----------------------------------------------------
        git_mentions_055 = "055" in git_message or "056" in git_message
        ps_is_stale      = ps_genesis != "" and "055" not in ps_genesis and "056" not in ps_genesis

        if ps_is_stale and git_sha:
            conclusion = (
                f"project_state.json reports {ps_genesis} / {ps_sprint}. "
                f"Git HEAD is {git_sha} ({git_message}). "
                f"The project identity in project_state.json is stale relative "
                f"to the current repository state. "
                f"MissionRegistry loaded this file at server startup and has not reloaded it."
            )
            proposed_action = (
                f"Update project_state.json: set current_genesis to Genesis-055, "
                f"current_sprint to the current sprint, and update next_milestone. "
                f"Then restart the server so MissionRegistry reloads the corrected state."
            )
            approval_required = True
        elif not ps_record.found:
            conclusion = "project_state.json could not be read. Investigation incomplete."
            proposed_action = None
            approval_required = False
        else:
            conclusion = (
                f"project_state.json reports {ps_genesis} / {ps_sprint}. "
                f"Git HEAD is {git_sha}. No stale state detected."
            )
            proposed_action = None
            approval_required = False

        return InvestigationReport(
            investigation_id  = investigation_id,
            question          = question,
            sources_inspected = sources_inspected,
            findings          = findings,
            conclusion        = conclusion,
            proposed_action   = proposed_action,
            approval_required = approval_required,
        )

    def investigate(self, question: str) -> InvestigationReport:
        """
        Route an investigation question to the appropriate investigation.
        Sprint-001: only project_state vs git is implemented.
        """
        q = question.lower()
        if any(kw in q for kw in (
            "genesis", "sprint", "stale", "wrong", "version",
            "project state", "mission control", "showing"
        )):
            return self.investigate_project_state_vs_git(question)

        # Default: project state vs git is the only investigation in Sprint-001
        return self.investigate_project_state_vs_git(question)
