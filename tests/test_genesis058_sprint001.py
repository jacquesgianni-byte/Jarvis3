"""
Genesis-058 Sprint-001 - InvestigationDescriptor + InvestigationRegistry tests.

Covers:
    - InvestigationDescriptor fields and immutability
    - InvestigationRegistry.all_descriptors()
    - InvestigationRegistry.get() - hit and miss
    - InvestigationRegistry.available() - with real project root
    - InvestigationRegistry.unavailable() - with fake root
    - InvestigationRegistry.source_availability() - per-source detail
    - InvestigationRegistry.summary() - smoke test
    - project_state_vs_git is registered with correct metadata
    - No duplicate registration
    - Catalogue is not empty
"""
from __future__ import annotations

import pathlib
import pytest

from core.mission.investigation_registry import (
    InvestigationDescriptor,
    InvestigationRegistry,
    _REGISTRY,
)

PROJECT_ROOT = pathlib.Path(r"C:\\Users\\ljmas\\Desktop\\jarvis3")
FAKE_ROOT    = pathlib.Path(r"C:\\nonexistent\\path\\that\\does\\not\\exist")


class TestInvestigationDescriptor:

    def test_fields_accessible(self):
        d = InvestigationDescriptor(
            name              = "test_investigation",
            display_name      = "Test Investigation",
            description       = "A test investigation.",
            question_keywords = ("test", "check"),
            evidence_sources  = ("project_state",),
        )
        assert d.name              == "test_investigation"
        assert d.display_name      == "Test Investigation"
        assert d.description       == "A test investigation."
        assert d.question_keywords == ("test", "check")
        assert d.evidence_sources  == ("project_state",)

    def test_immutable(self):
        d = InvestigationDescriptor(
            name              = "test_investigation",
            display_name      = "Test",
            description       = "Test.",
            question_keywords = ("test",),
            evidence_sources  = ("project_state",),
        )
        with pytest.raises((AttributeError, TypeError)):
            d.name = "something_else"

    def test_question_keywords_is_tuple(self):
        d = InvestigationDescriptor(
            name              = "t",
            display_name      = "T",
            description       = "T.",
            question_keywords = ("a", "b", "c"),
            evidence_sources  = ("project_state",),
        )
        assert isinstance(d.question_keywords, tuple)

    def test_evidence_sources_is_tuple(self):
        d = InvestigationDescriptor(
            name              = "t",
            display_name      = "T",
            description       = "T.",
            question_keywords = ("a",),
            evidence_sources  = ("project_state", "registry"),
        )
        assert isinstance(d.evidence_sources, tuple)


class TestInvestigationRegistryCatalogue:

    def test_catalogue_not_empty(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        assert len(reg.all_descriptors()) > 0

    def test_project_state_vs_git_registered(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = reg.get("project_state_vs_git")
        assert d is not None

    def test_project_state_vs_git_display_name(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = reg.get("project_state_vs_git")
        assert "Git" in d.display_name or "Reconciliation" in d.display_name

    def test_project_state_vs_git_has_description(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = reg.get("project_state_vs_git")
        assert len(d.description) > 10

    def test_project_state_vs_git_has_keywords(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = reg.get("project_state_vs_git")
        assert len(d.question_keywords) > 0

    def test_project_state_vs_git_has_evidence_sources(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = reg.get("project_state_vs_git")
        assert "project_state" in d.evidence_sources

    def test_get_unknown_returns_none(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        assert reg.get("nonexistent_investigation") is None

    def test_all_descriptors_returns_list(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        result = reg.all_descriptors()
        assert isinstance(result, list)

    def test_all_descriptors_are_investigation_descriptors(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        for d in reg.all_descriptors():
            assert isinstance(d, InvestigationDescriptor)

    def test_no_duplicate_names(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        names = [d.name for d in reg.all_descriptors()]
        assert len(names) == len(set(names))


class TestInvestigationRegistryAvailability:

    def test_available_with_real_root(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        avail = reg.available()
        names = [d.name for d in avail]
        assert "project_state_vs_git" in names

    def test_unavailable_with_fake_root(self):
        reg = InvestigationRegistry(FAKE_ROOT)
        avail = reg.available()
        assert len(avail) == 0

    def test_unavailable_list_with_fake_root(self):
        reg = InvestigationRegistry(FAKE_ROOT)
        unavail = reg.unavailable()
        names = [d.name for d in unavail]
        assert "project_state_vs_git" in names

    def test_available_and_unavailable_are_disjoint(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        avail_names   = {d.name for d in reg.available()}
        unavail_names = {d.name for d in reg.unavailable()}
        assert avail_names.isdisjoint(unavail_names)

    def test_available_plus_unavailable_equals_all(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        all_names     = {d.name for d in reg.all_descriptors()}
        avail_names   = {d.name for d in reg.available()}
        unavail_names = {d.name for d in reg.unavailable()}
        assert avail_names | unavail_names == all_names

    def test_source_availability_real_root(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d   = reg.get("project_state_vs_git")
        sa  = reg.source_availability(d)
        assert "project_state" in sa
        assert sa["project_state"] is True

    def test_source_availability_fake_root(self):
        reg = InvestigationRegistry(FAKE_ROOT)
        d   = reg.get("project_state_vs_git")
        sa  = reg.source_availability(d)
        assert all(v is False for v in sa.values())

    def test_source_availability_returns_dict(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d   = reg.get("project_state_vs_git")
        sa  = reg.source_availability(d)
        assert isinstance(sa, dict)

    def test_source_availability_unknown_source_is_false(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        d = InvestigationDescriptor(
            name              = "hypothetical",
            display_name      = "Hypothetical",
            description       = "Test only.",
            question_keywords = ("hypothetical",),
            evidence_sources  = ("nonexistent_source_xyz",),
        )
        sa = reg.source_availability(d)
        assert sa["nonexistent_source_xyz"] is False


class TestInvestigationRegistrySummary:

    def test_summary_is_string(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        assert isinstance(reg.summary(), str)

    def test_summary_contains_registry_header(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        assert "Investigation Registry" in reg.summary()

    def test_summary_contains_registered_investigation(self):
        reg = InvestigationRegistry(PROJECT_ROOT)
        assert "project_state_vs_git" in reg.summary()
