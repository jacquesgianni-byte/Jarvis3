"""
Jarvis OS - GenesisDeliveryRecord + GenesisDeliveryStore - Genesis-059 Sprint-001

Structured, authoritative record of what each Genesis delivered.

Design invariants:
    - GenesisDeliveryRecord is frozen - cannot be mutated after creation.
    - GenesisDeliveryStore is populated at declaration time only.
    - No dynamic loading. No filesystem scanning. No LLM.
    - get() returns None for unknown genesis_id - never raises.
    - latest_id() accepts current_genesis from MissionRegistry - not read independently.
    - This is the first node type toward a future Project Knowledge Graph.
      It is not a graph yet. It is a delivery record.

Populate new records here when a Genesis is complete.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenesisDeliveryRecord:
    """
    Authoritative record of what one Genesis delivered.

    All fields are set at declaration time from real evidence.
    frozen=True: any attempted mutation raises FrozenInstanceError.

    genesis_id:           canonical identifier, e.g. "Genesis-058"
    display_name:         human-readable name of the Genesis
    hypothesis:           what this Genesis set out to prove (one sentence)
    outcome:              what was actually proven or not proven (one sentence)
    sprints:              tuple of sprint summary strings
    components_delivered: tuple of component/class names delivered
    tests_added:          number of new tests added across all sprints
    commit:               final commit SHA for this Genesis
    """
    genesis_id:            str
    display_name:          str
    hypothesis:            str
    outcome:               str
    sprints:               Tuple[str, ...]
    components_delivered:  Tuple[str, ...]
    tests_added:           int
    commit:                str

    def format_answer(self) -> str:
        """Format a human-readable answer for 'What changed in Genesis X?'"""
        lines = [
            f"{self.genesis_id} — {self.display_name}",
            "-" * 40,
            "",
            f"Hypothesis: {self.hypothesis}",
            f"Outcome:    {self.outcome}",
            "",
            "Sprints:",
        ]
        for sprint in self.sprints:
            lines.append(f"  {sprint}")
        lines += [
            "",
            "Components delivered:",
        ]
        for component in self.components_delivered:
            lines.append(f"  - {component}")
        lines += [
            "",
            f"Tests added:  {self.tests_added}",
            f"Final commit: {self.commit}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# GenesisDeliveryStore - declared records only
# ---------------------------------------------------------------------------

# All Genesis delivery records. Populated at declaration time.
# Add a new record here when a Genesis is complete.
# Never add records dynamically or from external input.
_STORE: dict[str, GenesisDeliveryRecord] = {}


def _declare(record: GenesisDeliveryRecord) -> None:
    """Declare one delivery record. Called at module load time only."""
    if record.genesis_id in _STORE:
        raise ValueError(
            f"[GenesisDeliveryStore] Duplicate record: {record.genesis_id!r}"
        )
    _STORE[record.genesis_id] = record


# ---------------------------------------------------------------------------
# Declared Genesis delivery records
# ---------------------------------------------------------------------------

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-055",
    display_name = "Mission Control Reality Audit",
    hypothesis   = "A single MissionRegistry reading from one committed file can be the honest source of truth for all mission state displayed to Chief.",
    outcome      = "Proven. MissionRegistry became the single source; live dashboard reflects committed state without fabrication.",
    sprints      = (
        "Sprint-001: MissionPipeline, MissionCapabilityPolicy, MissionContext",
        "Sprint-002A: retrieval-first honesty hierarchy, IntentStage, DispatchStage",
        "Sprint-003: MissionRegistry as single source of truth, live dashboard",
    ),
    components_delivered = (
        "MissionPipeline",
        "MissionCapabilityPolicy",
        "MissionContext",
        "MissionRegistry",
        "InterfaceContextResolver",
    ),
    tests_added = 47,
    commit      = "f2a7744",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-063",
    display_name = "Gap-to-Objective Evidence Chain",
    hypothesis   = "Capability gaps can be linked to project objectives using the same deterministic proximity model applied to the objective list.",
    outcome      = "Proven. ObjectiveProximityAnalyser linked gaps to objectives; GapReportStage enriched with objective evidence chain.",
    sprints      = (
        "Sprint-001: ObjectiveProximityAnalyser, deterministic keyword overlap vs objectives -- 26 tests",
        "Sprint-002: Objective proximity wired into GapReportStage, why_failed + what_needed enriched -- 12 tests",
        "Sprint-003: Phone acceptance test -- golden conversation passed",
    ),
    components_delivered = (
        "ObjectiveProximityAnalyser",
        "ObjectiveProximityResult",
        "ObjectiveMatch",
        "GapReportStage (objective proximity enrichment)",
    ),
    tests_added = 38,
    commit      = "847e66b",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-062",
    display_name = "Richer Capability Surface",
    hypothesis   = "Jarvis can produce an evidence-backed capability inventory by running declared investigations against live project state.",
    outcome      = "Proven. CapabilityInventoryStage produced a real capability report; three new investigations added to the registry.",
    sprints      = (
        "Sprint-001: project_state.json isolation fixture (GC-008)",
        "Sprint-002: mission_registry_consistency, test_health, roadmap_vs_state investigations -- 33 tests",
        "Sprint-003: CapabilityInventoryStage, evidence-backed capability report -- 18 tests",
    ),
    components_delivered = (
        "mission_registry_consistency investigation",
        "test_health investigation",
        "roadmap_vs_state investigation",
        "CapabilityInventoryStage",
        "conftest.py GC-008 fixture",
    ),
    tests_added = 51,
    commit      = "7e37a6b",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-061",
    display_name = "Capability Gap Proximity Analysis",
    hypothesis   = "Capability gaps can be located within the known investigation space using deterministic keyword proximity, without an LLM.",
    outcome      = "Proven. CapabilityProximityAnalyser matched gaps to investigations by keyword overlap; audit trail written to why_failed.",
    sprints      = (
        "Sprint-001: ProximityResult, CapabilityProximityAnalyser, deterministic keyword overlap -- 26 tests",
        "Sprint-002: Proximity wired into GapReportStage, audit trail in why_failed + what_needed -- 15 tests",
    ),
    components_delivered = (
        "ProximityResult",
        "CapabilityProximityAnalyser",
        "GapReportStage (proximity enrichment)",
    ),
    tests_added = 41,
    commit      = "d648f46",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-060",
    display_name = "Evidence-Derived Capability Gap Observation",
    hypothesis   = "Gap observations derived from real pipeline failures can build an evidence journal that explains why Jarvis cannot answer a question.",
    outcome      = "Proven. GapObservationStore accumulates real failure evidence; GapReportStage reports evidence-derived gaps, not guesses.",
    sprints      = (
        "Sprint-001: CapabilityGapObservation, GapObservationStore, append-only evidence journal -- 28 tests",
        "Sprint-002: GapObservationEngine wired into pipeline, observational only -- 15 tests",
        "Sprint-003: GapReportStage, evidence-derived why_failed + what_needed reporting -- 24 tests",
    ),
    components_delivered = (
        "CapabilityGapObservation",
        "GapObservationStore",
        "GapObservationEngine",
        "GapReportStage",
        "IntentStage (why_failed + what_needed intents)",
    ),
    tests_added = 67,
    commit      = "330425d",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-059",
    display_name = "Project Knowledge Foundation",
    hypothesis   = "Structured delivery records and a knowledge query stage can replace LLM fabrication for questions about what Jarvis has built.",
    outcome      = "Proven. GenesisDeliveryStore + KnowledgeQueryStage answered delivery questions from declared facts; Git HEAD resolved authority.",
    sprints      = (
        "Sprint-001: GenesisDeliveryRecord, GenesisDeliveryStore, ConceptResolver -- 42 tests",
        "Sprint-002: KnowledgePreclassificationStage, KnowledgeQueryStage, pipeline wiring -- 31 tests",
        "Sprint-003: ContextBuildStage Git authority resolution -- 10 tests",
    ),
    components_delivered = (
        "GenesisDeliveryRecord",
        "GenesisDeliveryStore",
        "ConceptResolver",
        "KnowledgePreclassificationStage",
        "KnowledgeQueryStage",
        "ContextBuildStage (authority resolution)",
    ),
    tests_added = 83,
    commit      = "2f26927",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-057",
    display_name = "Evidence Reconciliation",
    hypothesis   = "Conflicting claims about the same fact can be resolved deterministically by declaring one source authoritative per fact type.",
    outcome      = "Proven. AuthorityPolicy + ReconciliationEngine resolved conflicts deterministically; blind test passed.",
    sprints      = (
        "Sprint-001: EvidenceRecord, ExtractionResult, ReconciliationEngine, AuthorityPolicy, ReconciledVerdict ? blind test passed",
    ),
    components_delivered = (
        "EvidenceRecord",
        "ExtractionResult",
        "Reconciliation",
        "ReconciliationEngine",
        "AuthorityPolicy",
        "ReconciledVerdict",
    ),
    tests_added = 26,
    commit      = "a305372",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-058",
    display_name = "Investigation Selection",
    hypothesis   = "Investigation selection can be made deterministic and auditable by replacing free-form routing with a declared descriptor registry.",
    outcome      = "Proven. InvestigationSelector matched by keyword overlap against declared descriptors; no LLM routing.",
    sprints      = (
        "Sprint-001: InvestigationDescriptor + InvestigationRegistry ? 26 tests",
        "Sprint-002: InvestigationSelector, deterministic keyword matching ? 27 tests",
        "Sprint-003: Selector wired into ReadOnlyInvestigator, investigation_name from descriptor ? 28 tests",
    ),
    components_delivered = (
        "InvestigationDescriptor",
        "InvestigationRegistry",
        "InvestigationSelector",
        "SelectionResult",
    ),
    tests_added = 81,
    commit      = "b43484a",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-064",
    display_name = "Chief-Governed Engineering Sprint",
    hypothesis   = "A Chief-governed engineering sprint loop can be implemented where Jarvis proposes, Chief approves, and execution is bounded and auditable.",
    outcome      = "Proven. SprintStateMachine, SprintStateStore, and sprint routes delivered a governed three-layer approval loop.",
    sprints      = (
        "Register mission_planning investigation descriptor",
    ),
    components_delivered = (
        "mission_planning",
    ),
    tests_added = 5719,
    commit      = "0409353",
))

_declare(GenesisDeliveryRecord(
    genesis_id   = "Genesis-067",
    display_name = "First Jarvis Participation Genesis",
    hypothesis   = "A four-way governed loop (Chief → Claude → Chief → Jarvis → Chief) can be proven end-to-end with Jarvis as an active participant rather than a passive executor.",
    outcome      = "Proven — loop delivery. However, the project record could not support independent cold-entry reconstruction: GPT's architectural participation left no trace, 5 questions missing, 5 fragmented. This Genesis is the documented baseline failure that Genesis-068 is designed to address.",
    sprints      = (
        "Sprint-001 through Sprint-004: four-way governed loop wired and proven on device (see git log for detail — sprint record not captured at Genesis scope, which is itself evidence of the gap this Genesis exposed)",
    ),
    components_delivered = (
        "code_quality",
        "uncategorised_gap",
        "mission_planning",
        "start_genesis",
    ),
    tests_added = 0,
    commit      = "ff96fbe",
))

# Add new records below as each Genesis is completed:
# _declare(GenesisDeliveryRecord(
#     genesis_id   = "Genesis-059",
#     display_name = "...",
#     ...
# ))


class GenesisDeliveryStore:
    """
    Query interface for declared Genesis delivery records.

    Constructed with the project root so latest_id() can read
    project_state.json - the single authoritative source for
    which Genesis is current.

    Cannot be extended at runtime. All records are declared above.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root.resolve()

    def get(self, genesis_id: str) -> Optional[GenesisDeliveryRecord]:
        """Return the delivery record for genesis_id, or None if not found."""
        return _STORE.get(genesis_id)

    def latest_id(self, current_genesis: Optional[str] = None) -> Optional[str]:
        """
        Return current_genesis.

        Callers should pass current_genesis from MissionRegistry.
        Falls back to reading project_state.json only if not provided,
        for backwards compatibility with call sites not yet updated.
        """
        if current_genesis is not None:
            return current_genesis
        # Fallback: read project_state.json directly (deprecated — update call sites)
        path = self._root / "project_state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            logger.warning(
                "[GenesisDeliveryStore] latest_id() falling back to project_state.json — "
                "pass current_genesis from MissionRegistry instead."
            )
            return data.get("current_genesis")
        except Exception as e:
            logger.warning("[GenesisDeliveryStore] Could not read project_state.json: %s", e)
            return None

    def all_ids(self) -> list[str]:
        """Return all declared genesis_ids in declaration order."""
        return list(_STORE.keys())
