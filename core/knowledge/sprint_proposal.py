"""
Jarvis OS - BoundSprintProposal + SprintRecord + SprintProposalEngine
Genesis-064 Sprint-001

The first evidence-derived sprint proposal system.

Design invariants:
    - BoundSprintProposal is frozen ? immutable after creation.
    - Every field in the proposal traces to stored evidence.
    - The proposal explicitly states what it does NOT do.
    - SprintProposalEngine selects from declared templates only.
      It does not invent steps or criteria.
    - Acceptance criteria must be achievable by the declared steps alone.
    - SprintRecord is append-only ? never rewritten after creation.
    - INSUFFICIENT_EVIDENCE is returned when evidence does not meet threshold.
    - No LLM. No invented rationale. No scope expansion after approval.

Governing rule:
    Evidence selects the work.
    The template constrains the work.
    The acceptance criteria must be achievable by that exact work.
    Every proposal must explicitly state what it does NOT do.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template identifiers ? the only templates Jarvis may propose
# ---------------------------------------------------------------------------

TEMPLATE_A = "register_investigation_descriptor"   # registration only, no implementation
TEMPLATE_B = "update_delivery_record"              # add a missing GenesisDeliveryRecord

# Minimum gap observations required before Template A is considered
TEMPLATE_A_MIN_OBSERVATIONS = 2

# Minimum gap threshold: proximity score must be 0 (ISOLATED) for all investigations
TEMPLATE_A_REQUIRES_ISOLATED = True


# ---------------------------------------------------------------------------
# BoundSprintProposal ? immutable, evidence-linked proposal
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProposalStep:
    """One declared, bounded step in a sprint proposal."""
    step_number:  int
    description:  str
    action_type:  str   # "register_descriptor" | "run_tests" | "commit" | "add_record"
    parameters:   Tuple  # immutable tuple of (key, value) pairs

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "description": self.description,
            "action_type": self.action_type,
            "parameters":  list(self.parameters),
        }


@dataclass(frozen=True)
class AcceptanceCriterion:
    """One declared, verifiable acceptance criterion."""
    description:      str
    criterion_type:   str   # "proximity_nonzero" | "tests_pass" | "record_exists"
    test_input:       str   # what is sent/checked
    expected_outcome: str   # what must be true
    guaranteed_by:    str   # which step guarantees this is achievable

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BoundSprintProposal:
    """
    Immutable, evidence-linked sprint proposal.

    Every field traces to stored evidence.
    The proposal explicitly states what it does NOT do.
    Acceptance criteria are guaranteed achievable by the declared steps.
    """
    proposal_id:            str
    created_at:             str
    template_id:            str
    proposed_sprint_name:   str
    rationale:              str        # derived from evidence, not invented
    evidence_summary:       str        # what evidence was used
    gap_observation_count:  int
    recurring_question:     str        # the most common failing question
    steps:                  Tuple      # tuple of ProposalStep
    acceptance_criteria:    Tuple      # tuple of AcceptanceCriterion
    not_doing:              Tuple      # explicit statement of what this does NOT do
    evidence_sources:       Tuple      # what sources were consulted

    def format_for_approval(self) -> str:
        """
        Format the full proposal for the Android ApprovalCard.
        Must be fully readable on phone ? no truncation of critical fields.
        """
        lines = [
            "SPRINT PROPOSAL",
            "=" * 40,
            "",
            f"Proposal ID:  {self.proposal_id}",
            f"Template:     {self.template_id}",
            f"Sprint name:  {self.proposed_sprint_name}",
            "",
            "EVIDENCE BASIS",
            "-" * 40,
            self.evidence_summary,
            "",
            f"Gap observations: {self.gap_observation_count}",
            f"Recurring question: {self.recurring_question!r}",
            "",
            "PROPOSED STEPS",
            "-" * 40,
        ]

        for step in self.steps:
            lines.append(f"  Step {step.step_number}: {step.description}")

        lines += [
            "",
            "ACCEPTANCE CRITERIA",
            "-" * 40,
        ]
        for criterion in self.acceptance_criteria:
            lines += [
                f"  [{criterion.criterion_type}]",
                f"  Test: {criterion.test_input}",
                f"  Expected: {criterion.expected_outcome}",
                f"  Guaranteed by: {criterion.guaranteed_by}",
            ]

        lines += [
            "",
            "WHAT THIS DOES NOT DO",
            "-" * 40,
        ]
        for item in self.not_doing:
            lines.append(f"  - {item}")

        lines += [
            "",
            "EVIDENCE SOURCES CONSULTED",
            "-" * 40,
        ]
        for src in self.evidence_sources:
            lines.append(f"  - {src}")

        lines += [
            "",
            "=" * 40,
            "Awaiting Chief approval.",
            "Nothing will be executed until APPROVE is tapped.",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "proposal_id":           self.proposal_id,
            "created_at":            self.created_at,
            "template_id":           self.template_id,
            "proposed_sprint_name":  self.proposed_sprint_name,
            "rationale":             self.rationale,
            "evidence_summary":      self.evidence_summary,
            "gap_observation_count": self.gap_observation_count,
            "recurring_question":    self.recurring_question,
            "steps":                 [s.to_dict() for s in self.steps],
            "acceptance_criteria":   [c.to_dict() for c in self.acceptance_criteria],
            "not_doing":             list(self.not_doing),
            "evidence_sources":      list(self.evidence_sources),
        }


# ---------------------------------------------------------------------------
# InsufficientEvidenceResult ? honest response when evidence is too thin
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InsufficientEvidenceResult:
    """
    Returned by SprintProposalEngine when evidence does not meet threshold.
    Never a proposal. Never a guess.
    """
    reason:                str
    gap_observation_count: int
    required_count:        int
    message:               str

    def format_for_mission(self) -> str:
        return (
            f"INSUFFICIENT EVIDENCE FOR SPRINT PROPOSAL\n"
            f"{'-' * 40}\n"
            f"Reason: {self.reason}\n"
            f"Gap observations recorded: {self.gap_observation_count}\n"
            f"Minimum required: {self.required_count}\n\n"
            f"{self.message}\n\n"
            f"Continue using Jarvis and ask questions it cannot answer.\n"
            f"As evidence accumulates, a proposal will become available."
        )


# ---------------------------------------------------------------------------
# SprintRecord ? append-only audit trail
# ---------------------------------------------------------------------------

@dataclass
class SprintRecord:
    """
    Persistent audit trail for one sprint proposal lifecycle.

    Fields are added progressively as the sprint moves through layers.
    Written to data/sprint_records/ as append-only JSONL.
    Never rewritten after creation.
    """
    proposal_id:          str
    created_at:           str
    proposal:             dict          # BoundSprintProposal.to_dict()
    layer1_approved_at:   Optional[str] = None
    layer1_approved_by:   Optional[str] = None
    layer2_triggered_at:  Optional[str] = None
    execution_trace:      List[dict]    = field(default_factory=list)
    test_result:          Optional[dict] = None
    desktop_result:       Optional[dict] = None
    layer3_reviewed_at:   Optional[str] = None
    layer3_decision:      Optional[str] = None   # "accepted" | "rejected"
    final_outcome:        Optional[str] = None   # "success" | "failure" | "rejected"

    def to_dict(self) -> dict:
        return {
            "proposal_id":         self.proposal_id,
            "created_at":          self.created_at,
            "proposal":            self.proposal,
            "layer1_approved_at":  self.layer1_approved_at,
            "layer1_approved_by":  self.layer1_approved_by,
            "layer2_triggered_at": self.layer2_triggered_at,
            "execution_trace":     self.execution_trace,
            "test_result":         self.test_result,
            "desktop_result":      self.desktop_result,
            "layer3_reviewed_at":  self.layer3_reviewed_at,
            "layer3_decision":     self.layer3_decision,
            "final_outcome":       self.final_outcome,
        }


class SprintRecordStore:
    """
    Append-only persistent store for SprintRecord objects.
    One record per line (JSONL). Never rewritten.
    """

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "sprint_records.jsonl"
        data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: SprintRecord) -> None:
        """Append one record to the store."""
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict()) + "\n")
            logger.info("[SprintRecordStore] Saved record %s", record.proposal_id)
        except Exception as e:
            logger.warning("[SprintRecordStore] Could not save record: %s", e)

    def all_records(self) -> List[SprintRecord]:
        """Load all records. Safe if file missing or corrupt."""
        if not self._path.exists():
            return []
        records = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                r = SprintRecord(**{k: data.get(k) for k in SprintRecord.__dataclass_fields__})
                records.append(r)
            except Exception as e:
                logger.warning("[SprintRecordStore] Skipping corrupt line: %s", e)
        return records

    def get(self, proposal_id: str) -> Optional[SprintRecord]:
        """Return the record for a proposal_id, or None."""
        for r in self.all_records():
            if r.proposal_id == proposal_id:
                return r
        return None


# ---------------------------------------------------------------------------
# SprintProposalEngine ? evidence-derived, template-constrained
# ---------------------------------------------------------------------------

class SprintProposalEngine:
    """
    Derives sprint proposals from stored evidence.

    Selects from declared templates only ? never invents steps.
    Returns BoundSprintProposal or InsufficientEvidenceResult.
    No LLM. No invented rationale. No scope expansion.

    Template A (register_investigation_descriptor):
        Triggered when: >= TEMPLATE_A_MIN_OBSERVATIONS ISOLATED gap observations exist
        Steps: register descriptor, run tests, commit
        Criterion: proximity score changes from 0 to > 0

    Template B (update_delivery_record):
        Triggered when: GenesisDeliveryStore missing a record for a completed Genesis
        Steps: add record, run tests, commit
        Criterion: store.get(genesis_id) returns non-None
    """

    def __init__(
        self,
        gap_store,            # GapObservationStore
        inv_registry,         # InvestigationRegistry
        delivery_store,       # GenesisDeliveryStore
        project_root: Path,
    ) -> None:
        self._gap_store      = gap_store
        self._inv_registry   = inv_registry
        self._delivery_store = delivery_store
        self._project_root   = project_root

    def propose(self) -> "BoundSprintProposal | InsufficientEvidenceResult":
        """
        Derive the best available sprint proposal from current evidence.
        Returns InsufficientEvidenceResult if evidence is too thin.
        """
        # Check Template A first ? gap-driven
        result = self._try_template_a()
        if result is not None:
            return result

        # Check Template B ? delivery record gap
        result = self._try_template_b()
        if result is not None:
            return result

        # No template applicable
        observations = self._gap_store.all_observations()
        return InsufficientEvidenceResult(
            reason                = "No template conditions met by current evidence.",
            gap_observation_count = len(observations),
            required_count        = TEMPLATE_A_MIN_OBSERVATIONS,
            message               = (
                "Gap observations exist but do not yet meet the threshold "
                "for a Template A proposal, and no missing delivery records "
                "were detected for Template B."
            ),
        )

    def _try_template_a(self):
        """Attempt Template A: register new investigation descriptor."""
        from core.knowledge.capability_gap import CAPABILITY_GAP_SIGNATURE
        from core.knowledge.proximity import CapabilityProximityAnalyser

        observations = self._gap_store.observations_by_signature(CAPABILITY_GAP_SIGNATURE)

        if len(observations) < TEMPLATE_A_MIN_OBSERVATIONS:
            return None

        # Verify all are ISOLATED
        analyser = CapabilityProximityAnalyser()
        for obs in observations:
            result = analyser.analyse(obs.question, obs.observation_id, self._inv_registry)
            if not result.gap_is_isolated:
                return None  # not all isolated ? another investigation covers this

        # Derive descriptor fields from recurring question keywords
        recurring_question = self._most_common_question(observations)
        descriptor_name    = self._derive_descriptor_name(recurring_question)
        keywords           = self._derive_keywords(observations)

        proposal_id = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        now         = datetime.now(timezone.utc).isoformat()

        steps = (
            ProposalStep(
                step_number  = 1,
                description  = (
                    f"Register InvestigationDescriptor {descriptor_name!r} "
                    f"in InvestigationRegistry with keywords derived from "
                    f"{len(observations)} gap observations."
                ),
                action_type  = "register_descriptor",
                parameters   = (
                    ("name",              descriptor_name),
                    ("keywords",          ",".join(keywords)),
                    ("evidence_sources",  "project_state"),
                ),
            ),
            ProposalStep(
                step_number  = 2,
                description  = "Run full test suite ? all existing tests must pass.",
                action_type  = "run_tests",
                parameters   = (("scope", "full"),),
            ),
            ProposalStep(
                step_number  = 3,
                description  = "Commit if tests pass.",
                action_type  = "commit",
                parameters   = (
                    ("message", f"Genesis-064: register {descriptor_name} investigation descriptor"),
                ),
            ),
        )

        acceptance_criteria = (
            AcceptanceCriterion(
                description      = "Proximity score for recurring question changes from 0 to > 0.",
                criterion_type   = "proximity_nonzero",
                test_input       = recurring_question,
                expected_outcome = "CapabilityProximityAnalyser returns closest_score > 0",
                guaranteed_by    = "Step 1 ? descriptor registration with matching keywords",
            ),
            AcceptanceCriterion(
                description      = "All existing tests pass.",
                criterion_type   = "tests_pass",
                test_input       = "python -m pytest tests/ -x -q",
                expected_outcome = "0 failures",
                guaranteed_by    = "Step 2 ? full test suite run",
            ),
        )

        not_doing = (
            "Does not implement an investigation method.",
            "Does not add a dispatch entry to ReadOnlyInvestigator.",
            "Does not claim the investigation produces findings.",
            "Does not create any executable investigation capability.",
            "Does not modify any file other than investigation_registry.py.",
            "A separate approval is required to implement the investigation method.",
        )

        evidence_summary = (
            f"{len(observations)} gap observations with signature "
            f"intent=unknown+knowledge=no+investigation=no+boundary=no. "
            f"All questions are ISOLATED (score 0) against {len(self._inv_registry.all_descriptors())} "
            f"registered investigations. "
            f"Most recurring question: {recurring_question!r}."
        )

        return BoundSprintProposal(
            proposal_id            = proposal_id,
            created_at             = now,
            template_id            = TEMPLATE_A,
            proposed_sprint_name   = f"Register {descriptor_name} investigation descriptor",
            rationale              = evidence_summary,
            evidence_summary       = evidence_summary,
            gap_observation_count  = len(observations),
            recurring_question     = recurring_question,
            steps                  = steps,
            acceptance_criteria    = acceptance_criteria,
            not_doing              = not_doing,
            evidence_sources       = (
                "GapObservationStore",
                "InvestigationRegistry",
                "CapabilityProximityAnalyser",
            ),
        )

    def _try_template_b(self):
        """Attempt Template B: add missing delivery record."""
        # Check git log for completed Geneses not in delivery store
        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", "--oneline", "-20"],
                cwd=self._project_root,
                capture_output=True, text=True, timeout=10,
            )
            log = result.stdout
        except Exception:
            return None

        known_ids = set(self._delivery_store.all_ids())
        for line in log.splitlines():
            match = re.search(r"Genesis-(\d+)", line)
            if match:
                gid = f"Genesis-{match.group(1)}"
                if gid not in known_ids:
                    proposal_id = f"PROP-{uuid.uuid4().hex[:6].upper()}"
                    now         = datetime.now(timezone.utc).isoformat()
                    steps = (
                        ProposalStep(
                            step_number  = 1,
                            description  = f"Add GenesisDeliveryRecord for {gid} to genesis_record.py.",
                            action_type  = "add_record",
                            parameters   = (("genesis_id", gid),),
                        ),
                        ProposalStep(
                            step_number  = 2,
                            description  = "Run full test suite.",
                            action_type  = "run_tests",
                            parameters   = (("scope", "full"),),
                        ),
                        ProposalStep(
                            step_number  = 3,
                            description  = "Commit if tests pass.",
                            action_type  = "commit",
                            parameters   = (("message", f"chore: add {gid} delivery record"),),
                        ),
                    )
                    acceptance_criteria = (
                        AcceptanceCriterion(
                            description      = f"GenesisDeliveryStore.get({gid!r}) returns non-None.",
                            criterion_type   = "record_exists",
                            test_input       = gid,
                            expected_outcome = "GenesisDeliveryStore.get() returns a record",
                            guaranteed_by    = "Step 1 ? delivery record declaration",
                        ),
                        AcceptanceCriterion(
                            description      = "All existing tests pass.",
                            criterion_type   = "tests_pass",
                            test_input       = "python -m pytest tests/ -x -q",
                            expected_outcome = "0 failures",
                            guaranteed_by    = "Step 2 ? full test suite run",
                        ),
                    )
                    not_doing = (
                        "Does not modify any existing delivery records.",
                        "Does not change any investigation or pipeline code.",
                    )
                    return BoundSprintProposal(
                        proposal_id            = proposal_id,
                        created_at             = now,
                        template_id            = TEMPLATE_B,
                        proposed_sprint_name   = f"Add {gid} delivery record",
                        rationale              = f"{gid} appears in git log but has no delivery record.",
                        evidence_summary       = f"Git log contains {gid}. GenesisDeliveryStore has no record for it.",
                        gap_observation_count  = 0,
                        recurring_question     = "",
                        steps                  = steps,
                        acceptance_criteria    = acceptance_criteria,
                        not_doing              = not_doing,
                        evidence_sources       = ("GenesisDeliveryStore", "git log"),
                    )
        return None

    @staticmethod
    def _most_common_question(observations: list) -> str:
        """Return the most frequently occurring question from observations."""
        from collections import Counter
        counts = Counter(o.question for o in observations)
        return counts.most_common(1)[0][0] if counts else ""

    @staticmethod
    def _derive_descriptor_name(question: str) -> str:
        """Derive a snake_case descriptor name from the recurring question."""
        q = question.lower()
        if "mission" in q:
            return "mission_planning"
        if "recommend" in q or "suggest" in q:
            return "recommendation"
        if "next" in q and "work" in q:
            return "work_prioritisation"
        return "uncategorised_gap"

    @staticmethod
    def _derive_keywords(observations: list) -> list:
        """
        Extract recurring significant words from observation questions.
        Words appearing in >= 50% of observations are included as keywords.
        Short words (<=3 chars) are excluded.
        """
        import re
        from collections import Counter
        all_words = []
        for obs in observations:
            words = re.findall(r"\b[a-z]{4,}\b", obs.question.lower())
            all_words.extend(words)
        counts  = Counter(all_words)
        n       = len(observations)
        keywords = [w for w, c in counts.items() if c >= max(1, n // 2)]
        # Always include the core theme words
        for obs in observations:
            q = obs.question.lower()
            for phrase in ("next mission", "should we", "work on", "mission be"):
                if phrase in q and phrase not in keywords:
                    keywords.append(phrase)
        return list(dict.fromkeys(keywords))[:12]  # max 12 keywords, deduplicated
