"""
Jarvis OS - InvestigationRegistry - Genesis-058 Sprint-001

Single catalogue of investigations ReadOnlyInvestigator can perform.

Design invariants:
    - Registration is explicit and controlled - no dynamic discovery.
    - No filesystem scanning. No Python introspection.
    - The registry is the only place that knows what investigations exist.
    - Each descriptor declares what evidence sources it needs.
    - Availability checking is read-only (does the source file exist on disk?).
    - The registry cannot be extended at runtime.

Capability surface is fully auditable: every investigation is listed here.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationDescriptor:
    """
    Declares one investigation that ReadOnlyInvestigator can perform.

    name:              unique identifier - matches the method name in
                       ReadOnlyInvestigator it will dispatch to.
    display_name:      human-readable label for reports and responses.
    description:       one sentence - what this investigation answers.
    question_keywords: words/phrases that indicate this investigation is
                       relevant. Used by InvestigationSelector (Sprint-002).
    evidence_sources:  logical source names (from AuthorisedSourceRegistry)
                       that this investigation requires. Used for availability
                       checking - if a required source does not exist on disk,
                       the investigation is reported as unavailable.
    """
    name:              str
    display_name:      str
    description:       str
    question_keywords: Tuple[str, ...]
    evidence_sources:  Tuple[str, ...]


# All registered investigations. Explicit. Controlled. Auditable.
# Add new investigations here - nowhere else.
_REGISTRY: Dict[str, InvestigationDescriptor] = {}


def _register(descriptor: InvestigationDescriptor) -> None:
    """Register one descriptor. Called at module load time only."""
    if descriptor.name in _REGISTRY:
        raise ValueError(
            f"[InvestigationRegistry] Duplicate registration: {descriptor.name!r}"
        )
    _REGISTRY[descriptor.name] = descriptor


_register(InvestigationDescriptor(
    name         = "project_state_vs_git",
    display_name = "Project State vs Git Reconciliation",
    description  = (
        "Compares project_state.json against live Git HEAD to detect "
        "inconsistencies in genesis and sprint labels."
    ),
    question_keywords = (
        "consistent", "consistency", "is everything", "check everything",
        "anything wrong", "any issues", "any problems", "any inconsistencies",
        "wrong genesis", "wrong sprint", "stale", "showing wrong",
        "showing the wrong", "project state", "project_state",
        "git", "reconcile", "reconciliation",
        "why does mission", "find the problem",
        "investigate", "diagnose", "root cause",
    ),
    evidence_sources = (
        "project_state",
    ),
))

_register(InvestigationDescriptor(
    name         = "mission_registry_consistency",
    display_name = "Mission Registry Consistency",
    description  = (
        "Compares MissionRegistry state against GenesisDeliveryStore records "
        "to detect stale or inconsistent mission metadata."
    ),
    question_keywords = (
        "mission registry", "dashboard", "showing wrong", "wrong genesis",
        "mission consistent", "is the dashboard", "is mission control",
        "registry consistent", "mission metadata", "registry up to date",
        "dashboard showing", "mission mode showing",
    ),
    evidence_sources = (
        "project_state",
    ),
))

_register(InvestigationDescriptor(
    name         = "test_health",
    display_name = "Test Health Investigation",
    description  = (
        "Inspects the most recent test run results from project_state.json "
        "and compares against current Git HEAD to detect stale or failing tests."
    ),
    question_keywords = (
        "tests passing", "tests failing", "test results", "test health",
        "are tests green", "are tests passing", "test failures",
        "tests stale", "when were tests run", "last test run",
        "tests current", "suite passing", "suite failing",
        "how many tests", "tests skipped",
    ),
    evidence_sources = (
        "project_state",
    ),
))

_register(InvestigationDescriptor(
    name         = "roadmap_vs_state",
    display_name = "Roadmap vs State Consistency",
    description  = (
        "Compares project_state.json roadmap fields against GenesisDeliveryStore "
        "records to detect stale milestones, objectives, or completion status."
    ),
    question_keywords = (
        "roadmap", "next milestone", "milestone", "objectives",
        "is the roadmap", "roadmap up to date", "roadmap consistent",
        "what have we completed", "last completed genesis",
        "is the milestone", "objectives up to date", "stale milestone",
        "roadmap accurate", "project plan",
    ),
    evidence_sources = (
        "project_state",
    ),
))

_register(InvestigationDescriptor(
    name         = "mission_planning",
    display_name = "Mission Planning",
    description  = (
        "Investigation for mission planning questions."
    ),
    question_keywords = (
        "next mission",
        "mission",
    ),
    evidence_sources = (
        "project_state",
    ),
))

# Future investigations registered here:


class InvestigationRegistry:
    """
    Query interface for the investigation catalogue.

    Constructed once. Cannot be extended at runtime.
    All registration happens at module load time via _register().

    project_root is used only for availability checking -
    to confirm required source files exist on disk.
    It is never used to discover or load investigations.
    """

    def __init__(self, project_root: Path) -> None:
        self._root = project_root.resolve()

    def all_descriptors(self) -> List[InvestigationDescriptor]:
        """Return all registered investigation descriptors."""
        return list(_REGISTRY.values())

    def get(self, name: str) -> Optional[InvestigationDescriptor]:
        """Return one descriptor by name, or None if not registered."""
        return _REGISTRY.get(name)

    def available(self) -> List[InvestigationDescriptor]:
        """
        Return descriptors whose required evidence sources exist on disk.
        A descriptor is available if ALL of its evidence_sources resolve
        to files that exist under the project root.
        This is a read-only check - no files are opened or parsed.
        """
        result = []
        for descriptor in _REGISTRY.values():
            if self._sources_available(descriptor):
                result.append(descriptor)
        return result

    def unavailable(self) -> List[InvestigationDescriptor]:
        """
        Return descriptors whose required evidence sources are missing from disk.
        Used for diagnostics and honest capability reporting.
        """
        result = []
        for descriptor in _REGISTRY.values():
            if not self._sources_available(descriptor):
                result.append(descriptor)
        return result

    def source_availability(self, descriptor: InvestigationDescriptor) -> Dict[str, bool]:
        """
        Return per-source availability for one descriptor.
        {logical_name: exists_on_disk}
        """
        from core.mission.authorised_sources import AUTHORISED_RELATIVE_PATHS
        result = {}
        for source_name in descriptor.evidence_sources:
            relative = AUTHORISED_RELATIVE_PATHS.get(source_name)
            if relative is None:
                result[source_name] = False
            else:
                result[source_name] = (self._root / relative).exists()
        return result

    def _sources_available(self, descriptor: InvestigationDescriptor) -> bool:
        """True if ALL evidence sources for this descriptor exist on disk."""
        availability = self.source_availability(descriptor)
        return all(availability.values()) if availability else False

    def summary(self) -> str:
        """Human-readable summary of registered investigations and availability."""
        lines = ["Investigation Registry", "-" * 40]
        for d in _REGISTRY.values():
            avail = self._sources_available(d)
            status = "available" if avail else "unavailable (missing sources)"
            lines.append(f"  [{'+' if avail else '!'}] {d.display_name} ({d.name})")
            lines.append(f"      {d.description}")
            lines.append(f"      Status: {status}")
            lines.append(f"      Sources: {', '.join(d.evidence_sources)}")
        return "\n".join(lines)
