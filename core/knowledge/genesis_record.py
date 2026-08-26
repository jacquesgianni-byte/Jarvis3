"""
Jarvis OS - GenesisDeliveryRecord + GenesisDeliveryStore - Genesis-059 Sprint-001

Structured, authoritative record of what each Genesis delivered.

Design invariants:
    - GenesisDeliveryRecord is frozen - cannot be mutated after creation.
    - GenesisDeliveryStore is populated at declaration time only.
    - No dynamic loading. No filesystem scanning. No LLM.
    - get() returns None for unknown genesis_id - never raises.
    - latest_id() reads project_state.json - the single authoritative source.
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
    sprints:              tuple of sprint summary strings
    components_delivered: tuple of component/class names delivered
    tests_added:          number of new tests added across all sprints
    commit:               final commit SHA for this Genesis
    """
    genesis_id:            str
    display_name:          str
    sprints:               Tuple[str, ...]
    components_delivered:  Tuple[str, ...]
    tests_added:           int
    commit:                str

    def format_answer(self) -> str:
        """Format a human-readable answer for 'What changed in Genesis X?'"""
        lines = [
            f"{self.genesis_id} ? {self.display_name}",
            "-" * 40,
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
    genesis_id   = "Genesis-061",
    display_name = "Capability Gap Proximity Analysis",
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

    def latest_id(self) -> Optional[str]:
        """
        Read current_genesis from project_state.json.
        Returns None if the file cannot be read or the field is absent.
        This is the only filesystem access in this module.
        """
        path = self._root / "project_state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return data.get("current_genesis")
        except Exception as e:
            logger.warning("[GenesisDeliveryStore] Could not read project_state.json: %s", e)
            return None

    def all_ids(self) -> list[str]:
        """Return all declared genesis_ids in declaration order."""
        return list(_STORE.keys())
