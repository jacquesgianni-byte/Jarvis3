"""
Jarvis OS - ReadOnlyInvestigator - Genesis-057 Sprint-001

Evidence Reconciliation upgrade.

New in Genesis-057:
    EvidenceRecord      - one observed fact from one authorised source
    ExtractionResult    - structured label extraction (present/absent, not assumed)
    Reconciliation      - agreement/disagreement between two EvidenceRecords
    ReconciliationEngine - observes whether sources agree (never decides winner)
    AuthorityPolicy     - explicitly decides which source is authoritative
    ReconciledVerdict   - ruling from AuthorityPolicy on one anomaly

Architecture:
    ReadOnlyInvestigator
        |
        +-- AuthorisedFileReader   (reads authorised project files)
        |
        +-- ReadOnlyGitReader      (fixed read-only git commands only)
        |
        +-- ReconciliationEngine   (observes agreement/disagreement only)
        |
        +-- AuthorityPolicy        (decides winner - explicit, auditable)

Security properties (unchanged from Genesis-056):
    - No write(), delete(), execute(), or subprocess beyond fixed git commands.
    - Every file read goes through AuthorisedPath.
    - InvestigationReport.status is always NO_CHANGES_MADE.
    - Proposal fields come directly from authoritative evidence - not inferred.

Genesis-057 invariants:
    - ReconciliationEngine has no reference to AuthorityPolicy.
    - AuthorityPolicy has no reference to ReconciliationEngine.
    - Missing Git labels = insufficient evidence, not anomaly.
    - If authority undefined for a key, no proposal is generated (report only).
    - BoundProposal fields come from ReconciledVerdict.authoritative_value only.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from core.mission.authorised_sources import AuthorisedPath, AuthorisedSourceRegistry
from core.mission.proposal import BoundProposal, ProposalOperation, ProposalStatus
from core.mission.investigation_registry import InvestigationRegistry
from core.mission.investigation_selector import InvestigationSelector

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Investigation status - structural constant, not a settable boolean
# ---------------------------------------------------------------------------

class InvestigationStatus(Enum):
    NO_CHANGES_MADE = "NO_CHANGES_MADE"


# ---------------------------------------------------------------------------
# Genesis-057: Evidence model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRecord:
    """
    One observed fact from one authorised source.
    Created only when a value is actually present - never fabricated.
    """
    source:   str    # "project_state.json", "git HEAD"
    key:      str    # "current_genesis", "current_sprint"
    value:    str    # exactly what was read - no interpretation


@dataclass(frozen=True)
class ExtractionResult:
    """
    Result of extracting a structured label from a raw string.
    present=False means the label was not found - this is insufficient
    evidence, not an anomaly. Never assume absence = wrong.
    """
    value:   Optional[str]  # None if label not present
    present: bool           # False = insufficient evidence
    raw:     str            # the raw string that was searched


@dataclass(frozen=True)
class Reconciliation:
    """
    The result of comparing two EvidenceRecords about the same fact.
    consistent=True means sources agree.
    consistent=False means sources disagree (anomaly detected).
    ReconciliationEngine never decides which source is correct.
    """
    key:        str
    source_a:   EvidenceRecord
    source_b:   EvidenceRecord
    consistent: bool
    note:       str


@dataclass(frozen=True)
class ReconciledVerdict:
    """
    AuthorityPolicy ruling on one anomaly.
    Names which source is authoritative and what value should be applied.
    Never produced by ReconciliationEngine.
    """
    key:                  str
    authoritative_source: str            # "git HEAD" or "project_state.json"
    authoritative_value:  str            # what the authoritative source says
    stale_source:         str            # the source that disagrees
    stale_value:          str            # what the stale source says
    proposed_correction:  str            # human-readable description


# ---------------------------------------------------------------------------
# Genesis-057: Label extraction - structured, not substring search
# ---------------------------------------------------------------------------

def extract_genesis_label(text: str) -> ExtractionResult:
    """
    Extract 'Genesis-NNN' from a string.
    Returns present=False if no label found - this is insufficient evidence,
    not an anomaly. A chore commit with no genesis label is not stale.
    """
    match = re.search("Genesis-\\d+", text, re.IGNORECASE)
    return ExtractionResult(
        value   = match.group(0) if match else None,
        present = match is not None,
        raw     = text,
    )


def extract_sprint_label(text: str) -> ExtractionResult:
    """
    Extract 'Sprint-NNN' from a string.
    Returns present=False if no label found.
    """
    match = re.search("Sprint-\\d+", text, re.IGNORECASE)
    return ExtractionResult(
        value   = match.group(0) if match else None,
        present = match is not None,
        raw     = text,
    )


# ---------------------------------------------------------------------------
# Genesis-057: ReconciliationEngine - observes only, never decides
# ---------------------------------------------------------------------------

class ReconciliationEngine:
    """
    Compares two EvidenceRecords and reports whether they agree.

    Genesis-057 invariant:
        This class has NO reference to AuthorityPolicy.
        It does NOT decide which source is correct.
        It does NOT produce proposals or verdicts.
        It only observes agreement or disagreement.
    """

    def reconcile(
        self,
        key:      str,
        record_a: EvidenceRecord,
        record_b: EvidenceRecord,
    ) -> Reconciliation:
        consistent = record_a.value.lower() == record_b.value.lower()
        return Reconciliation(
            key        = key,
            source_a   = record_a,
            source_b   = record_b,
            consistent = consistent,
            note       = (
                f"{record_a.source} says {record_a.value!r}, "
                f"{record_b.source} says {record_b.value!r}."
            ) if not consistent else "Sources agree.",
        )


# ---------------------------------------------------------------------------
# Genesis-057: AuthorityPolicy - explicit, auditable, one place
# ---------------------------------------------------------------------------

class AuthorityPolicy:
    """
    Explicitly defines which source is authoritative for each key.

    Genesis-057 invariant:
        If a key has no configured authority, no verdict is produced
        and no proposal is generated. The anomaly is reported only.
        This prevents a future reconciliation from accidentally becoming
        an executable proposal simply because a new comparison was added.

    Sprint-001: git HEAD is authoritative for engineering identity.
    This is a policy decision - not derived from the evidence itself.
    """

    # Maps key -> authoritative source name
    # Only keys listed here can produce a ReconciledVerdict and BoundProposal.
    AUTHORITY: Dict[str, str] = {
        "current_genesis": "git HEAD",
        "current_sprint":  "git HEAD",
    }

    @classmethod
    def evaluate(
        cls,
        anomalies: List[Reconciliation],
    ) -> tuple[List[ReconciledVerdict], List[Reconciliation]]:
        """
        Evaluate a list of anomalies against the authority policy.

        Returns:
            verdicts:   anomalies where authority is defined -> ReconciledVerdict
            no_authority: anomalies where authority is undefined -> report only

        Anomalies with undefined authority produce NO proposal.
        """
        verdicts:      List[ReconciledVerdict] = []
        no_authority:  List[Reconciliation]    = []

        for anomaly in anomalies:
            auth_source = cls.AUTHORITY.get(anomaly.key)
            if auth_source is None:
                # Safety rail: authority undefined -> no proposal
                logger.info(
                    "[AuthorityPolicy] No authority defined for key %r. "
                    "Anomaly will be reported only, no proposal generated.",
                    anomaly.key,
                )
                no_authority.append(anomaly)
                continue

            # Determine which record is authoritative
            if anomaly.source_a.source == auth_source:
                auth_record   = anomaly.source_a
                stale_record  = anomaly.source_b
            else:
                auth_record   = anomaly.source_b
                stale_record  = anomaly.source_a

            verdicts.append(ReconciledVerdict(
                key                  = anomaly.key,
                authoritative_source = auth_record.source,
                authoritative_value  = auth_record.value,
                stale_source         = stale_record.source,
                stale_value          = stale_record.value,
                proposed_correction  = (
                    f"Update {stale_record.source}: "
                    f"set {anomaly.key} from {stale_record.value!r} "
                    f"to {auth_record.value!r} "
                    f"(authoritative source: {auth_record.source})."
                ),
            ))

        return verdicts, no_authority


# ---------------------------------------------------------------------------
# Existing data models (unchanged from Genesis-056)
# ---------------------------------------------------------------------------

@dataclass
class SourceRecord:
    """One source that was inspected during an investigation."""
    logical_name:  str
    found:         bool
    raw_value:     Optional[str] = None
    error:         Optional[str] = None


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
    """
    investigation_id:  str
    question:          str
    sources_inspected: List[SourceRecord]
    findings:          List[Finding]
    conclusion:        str
    proposed_action:   Optional[str]
    approval_required: bool
    bound_proposal:    Optional["BoundProposal"] = None
    status:            InvestigationStatus = InvestigationStatus.NO_CHANGES_MADE
    investigation_name: str = ""

    def format_for_mission(self) -> str:
        lines = [
            "INVESTIGATION",
            "-" * 40,
            f"ID: {self.investigation_id}",
            "",
            "Question:",
            self.question,
            "",
            "Sources inspected:",
        ]
        for s in self.sources_inspected:
            tick = "+" if s.found else "!"
            lines.append(f"  {tick} {s.logical_name}" + (f" - {s.error}" if s.error else ""))

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
# ReadOnlyGitReader - unchanged from Genesis-056
# ---------------------------------------------------------------------------

_ALLOWED_GIT_SUBCOMMANDS: frozenset = frozenset({
    "log", "branch", "status", "show", "diff", "rev-parse",
})

class ReadOnlyGitReader:
    def __init__(self, project_root: Path):
        self._root = project_root

    def head_sha(self) -> str:
        return self._run(["git", "log", "-1", "--format=%h"])

    def head_message(self) -> str:
        return self._run(["git", "log", "-1", "--format=%s"])

    def branch(self) -> str:
        return self._run(["git", "branch", "--show-current"])

    def recent_log(self, n: int = 5) -> str:
        n = min(max(1, n), 20)
        return self._run(["git", "log", f"-{n}", "--oneline"])

    def status_short(self) -> str:
        return self._run(["git", "status", "--short"])

    def _run(self, cmd: list) -> str:
        if len(cmd) < 2 or cmd[1] not in _ALLOWED_GIT_SUBCOMMANDS:
            raise ValueError(
                f"[ReadOnlyGitReader] Git subcommand {cmd[1]!r} is not in the allow-list. "
                f"Allowed: {sorted(_ALLOWED_GIT_SUBCOMMANDS)}"
            )
        try:
            return subprocess.check_output(
                cmd, cwd=str(self._root), stderr=subprocess.DEVNULL, text=True,
            ).strip()
        except Exception as e:
            logger.warning("[ReadOnlyGitReader] Git command failed: %s - %s", cmd, e)
            return ""


# ---------------------------------------------------------------------------
# AuthorisedFileReader - unchanged from Genesis-056
# ---------------------------------------------------------------------------

class AuthorisedFileReader:
    def read_text(self, authorised_path: AuthorisedPath) -> str:
        try:
            return authorised_path.resolved.read_text(encoding="utf-8-sig")
        except Exception as e:
            logger.warning("[AuthorisedFileReader] Could not read %s: %s",
                           authorised_path.logical_name, e)
            return ""

    def read_json(self, authorised_path: AuthorisedPath) -> dict:
        text = self.read_text(authorised_path)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("[AuthorisedFileReader] JSON parse error in %s: %s",
                           authorised_path.logical_name, e)
            return {}


# ---------------------------------------------------------------------------
# ReadOnlyInvestigator - Genesis-057 upgrade
# ---------------------------------------------------------------------------

class ReadOnlyInvestigator:
    """
    Mission Mode read-only investigation capability.

    Genesis-057: upgraded to use ReconciliationEngine + AuthorityPolicy.
    Genesis-058: InvestigationSelector routes questions to registered
                 investigations. investigate() no longer hardcodes a target.

    Chain: question -> InvestigationSelector -> registered descriptor
           -> dispatch to named method -> evidence -> InvestigationReport.

    investigation_name in every report comes from the registered descriptor,
    never reconstructed from the question.
    """

    def __init__(self, registry: AuthorisedSourceRegistry, project_root: Path):
        self._registry    = registry
        self._file_reader = AuthorisedFileReader()
        self._git_reader  = ReadOnlyGitReader(project_root)
        self._engine      = ReconciliationEngine()

        # Genesis-058 Sprint-003: selector wired from declared registry
        _inv_registry  = InvestigationRegistry(project_root)
        self._selector = InvestigationSelector(_inv_registry)

        # Dispatch table: descriptor.name -> bound method
        # Add new investigations here when registered in InvestigationRegistry.
        self._dispatch: dict = {
            "project_state_vs_git": self.investigate_project_state_vs_git,
        }

    def investigate(self, question: str) -> InvestigationReport:
        """
        Route a question to the appropriate registered investigation.

        Genesis-058 Sprint-003: uses InvestigationSelector.
        - No match  -> honest report, no proposal, approval_required=False
        - Ambiguous -> honest report, no proposal, approval_required=False
        - Match     -> dispatch to named method, investigation_name from descriptor

        investigation_name always comes from the registered descriptor.
        """
        result = self._selector.select(question)

        if result.no_match:
            return InvestigationReport(
                investigation_id   = f"INV-NOMATCH-{__import__('uuid').uuid4().hex[:6].upper()}",
                question           = question,
                sources_inspected  = [],
                findings           = [],
                conclusion         = "No available investigation matches this question.",
                proposed_action    = None,
                approval_required  = False,
                bound_proposal     = None,
                investigation_name = "",
            )

        if result.ambiguous:
            candidate_names = ", ".join(c.display_name for c in result.candidates)
            return InvestigationReport(
                investigation_id   = f"INV-AMBIG-{__import__('uuid').uuid4().hex[:6].upper()}",
                question           = question,
                sources_inspected  = [],
                findings           = [],
                conclusion         = (
                    "Multiple investigations match this question; "
                    "I cannot safely choose between them. "
                    f"Matched: {candidate_names}."
                ),
                proposed_action    = None,
                approval_required  = False,
                bound_proposal     = None,
                investigation_name = "",
            )

        # Exactly one match - dispatch to the registered method
        descriptor = result.descriptor
        method = self._dispatch.get(descriptor.name)
        if method is None:
            # Registry has a descriptor but no wired method - report honestly
            return InvestigationReport(
                investigation_id   = f"INV-NOWIRE-{__import__('uuid').uuid4().hex[:6].upper()}",
                question           = question,
                sources_inspected  = [],
                findings           = [],
                conclusion         = (
                    f"Investigation {descriptor.display_name!r} is registered "
                    f"but not yet wired to an implementation."
                ),
                proposed_action    = None,
                approval_required  = False,
                bound_proposal     = None,
                investigation_name = descriptor.name,
            )

        report = method(question)
        # investigation_name always from the registered descriptor
        return InvestigationReport(
            investigation_id   = report.investigation_id,
            question           = report.question,
            sources_inspected  = report.sources_inspected,
            findings           = report.findings,
            conclusion         = report.conclusion,
            proposed_action    = report.proposed_action,
            approval_required  = report.approval_required,
            bound_proposal     = report.bound_proposal,
            status             = report.status,
            investigation_name = descriptor.name,
        )

    def investigate_project_state_vs_git(self, question: str) -> InvestigationReport:
        """
        Compare project_state.json against live Git HEAD.

        Genesis-057: uses ReconciliationEngine + AuthorityPolicy.
        - Extracts structured labels from git commit message
        - Missing labels = insufficient evidence (not anomaly)
        - ReconciliationEngine observes agreement/disagreement only
        - AuthorityPolicy decides which source is authoritative
        - Proposal fields come from ReconciledVerdict - not hardcoded
        """
        investigation_id   = f"INV-057-{uuid.uuid4().hex[:6].upper()}"
        sources_inspected: List[SourceRecord] = []
        findings:          List[Finding]      = []
        reconciliations:   List[Reconciliation] = []
        insufficient:      List[str]          = []

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

        ps_genesis = project_state.get("current_genesis", "")
        ps_sprint  = project_state.get("current_sprint",  "")

        findings.append(Finding(source="project_state.json", key="current_genesis", value=ps_genesis or "UNKNOWN"))
        findings.append(Finding(source="project_state.json", key="current_sprint",  value=ps_sprint  or "UNKNOWN"))

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

        findings.append(Finding(source="git HEAD", key="commit",  value=git_sha     or "UNAVAILABLE"))
        findings.append(Finding(source="git HEAD", key="message", value=git_message or "UNAVAILABLE"))
        findings.append(Finding(source="git HEAD", key="branch",  value=git_branch  or "UNAVAILABLE"))

        # -- Genesis-057: structured label extraction ---------------------
        genesis_extraction = extract_genesis_label(git_message)
        sprint_extraction  = extract_sprint_label(git_message)

        findings.append(Finding(
            source = "git HEAD",
            key    = "current_genesis",
            value  = genesis_extraction.value or "NOT FOUND IN COMMIT MESSAGE",
            note   = None if genesis_extraction.present else "insufficient evidence",
        ))
        findings.append(Finding(
            source = "git HEAD",
            key    = "current_sprint",
            value  = sprint_extraction.value or "NOT FOUND IN COMMIT MESSAGE",
            note   = None if sprint_extraction.present else "insufficient evidence",
        ))

        # -- Genesis-057: reconcile where both sources have evidence ------
        if ps_genesis and genesis_extraction.present:
            rec = self._engine.reconcile(
                "current_genesis",
                EvidenceRecord(source="project_state.json", key="current_genesis", value=ps_genesis),
                EvidenceRecord(source="git HEAD",           key="current_genesis", value=genesis_extraction.value),
            )
            reconciliations.append(rec)
            if not rec.consistent:
                findings.append(Finding(
                    source="reconciliation",
                    key="current_genesis",
                    value="ANOMALY",
                    note=rec.note,
                ))
        elif not genesis_extraction.present:
            insufficient.append("current_genesis: git HEAD commit message contains no genesis label")

        if ps_sprint and sprint_extraction.present:
            rec = self._engine.reconcile(
                "current_sprint",
                EvidenceRecord(source="project_state.json", key="current_sprint", value=ps_sprint),
                EvidenceRecord(source="git HEAD",           key="current_sprint", value=sprint_extraction.value),
            )
            reconciliations.append(rec)
            if not rec.consistent:
                findings.append(Finding(
                    source="reconciliation",
                    key="current_sprint",
                    value="ANOMALY",
                    note=rec.note,
                ))
        elif not sprint_extraction.present:
            insufficient.append("current_sprint: git HEAD commit message contains no sprint label")

        # -- Genesis-057: AuthorityPolicy evaluation ----------------------
        anomalies = [r for r in reconciliations if not r.consistent]
        verdicts, no_authority = AuthorityPolicy.evaluate(anomalies)

        # -- Build conclusion and proposal --------------------------------
        bound_proposal   = None
        proposed_action  = None
        approval_required = False

        if not ps_record.found:
            conclusion = "project_state.json could not be read. Investigation incomplete."

        elif anomalies and verdicts:
            # Anomalies detected AND authority defined -> proposal
            verdict_lines = [v.proposed_correction for v in verdicts]
            conclusion = (
                f"Inconsistency detected between project_state.json and git HEAD. "
                + " ".join(
                    f"{v.key}: project_state.json says {v.stale_value!r}, "
                    f"git HEAD says {v.authoritative_value!r}."
                    for v in verdicts
                )
            )
            proposed_action = " ".join(verdict_lines)
            approval_required = True

            # Proposal fields come directly from verdicts - not hardcoded
            fields = {v.key: v.authoritative_value for v in verdicts}
            bound_proposal = BoundProposal(
                investigation_id = investigation_id,
                operation        = ProposalOperation.UPDATE_PROJECT_STATE,
                target           = "project_state.json",
                fields           = fields,
                status           = ProposalStatus.PENDING,
            )

        elif anomalies and no_authority:
            # Anomalies detected but authority undefined -> report only
            conclusion = (
                f"Inconsistency detected but authority is undefined for: "
                f"{[r.key for r in no_authority]}. "
                f"Anomaly reported. No proposal generated."
            )

        elif insufficient:
            # Insufficient evidence - git commits had no labels
            conclusion = (
                f"Insufficient evidence to reconcile all keys. "
                f"Git HEAD commit message contains no structured labels. "
                f"project_state.json reports {ps_genesis} / {ps_sprint}. "
                f"No anomaly declared."
            )

        else:
            # All reconciliations consistent
            conclusion = (
                f"Sources consistent. "
                f"project_state.json and git HEAD agree: "
                f"{ps_genesis} / {ps_sprint}."
            )

        return InvestigationReport(
            investigation_id  = investigation_id,
            question          = question,
            sources_inspected = sources_inspected,
            findings          = findings,
            conclusion        = conclusion,
            proposed_action   = proposed_action,
            approval_required = approval_required,
            bound_proposal    = bound_proposal,
        )


