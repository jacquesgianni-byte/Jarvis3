"""
Genesis-019 Sprint 001 — Engineering Academy Foundation
Deterministic unit tests.

Coverage:
  - JSON loading
  - Schema validation
  - Duplicate ID detection
  - Missing required fields
  - Repository queries
  - Category filtering
  - Tag filtering
  - Deterministic search
  - Read-only behaviour (frozen dataclass)
  - Exception handling
  - Empty result handling
  - Stable ordering of results

No network access. No AI providers. All tests are deterministic.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root or tests/ directory
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering.academy.exceptions import (
    AcademyError,
    AcademySchemaError,
    InvalidPrincipleError,
    PrincipleNotFoundError,
)
from core.engineering.academy.json_repository import JsonAcademyRepository
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import EngineeringPrinciple
from core.engineering.academy.repository import AcademyRepository
from core.engineering.academy.service import AcademyService


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

VALID_PRINCIPLE = {
    "id": "dry",
    "name": "Don't Repeat Yourself",
    "category": "core",
    "summary": "Every piece of knowledge must have a single representation.",
    "rationale": "Duplication forces multiple update points.",
    "guidance": "Extract duplicated logic into a shared function.",
    "violations": ["Copy-pasting validation logic"],
    "examples": ["shared utility module"],
    "references": ["Pragmatic Programmer"],
    "tags": ["dry", "duplication", "maintainability"],
}

VALID_PRINCIPLE_2 = {
    "id": "kiss",
    "name": "Keep It Simple",
    "category": "core",
    "summary": "Avoid unnecessary complexity.",
    "rationale": "Complexity increases failure surface.",
    "guidance": "Choose the simplest correct solution.",
    "violations": ["Over-engineered abstractions"],
    "examples": [],
    "references": [],
    "tags": ["kiss", "simplicity"],
}

JARVIS_PRINCIPLE = {
    "id": "jarvis-fail-fast",
    "name": "Fail Fast",
    "category": "jarvis",
    "summary": "Detect errors at the point of failure.",
    "rationale": "Early errors are easier to diagnose.",
    "guidance": "Validate inputs at boundaries.",
    "violations": ["Silent None returns"],
    "examples": [],
    "references": [],
    "tags": ["jarvis", "validation", "error-handling"],
}


def make_principles_file(tmp_path: Path, principles: list) -> Path:
    """Write a principles.json to tmp_path and return its path."""
    data = {"principles": principles}
    path = tmp_path / "principles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_repo(tmp_path: Path, principles: list) -> JsonAcademyRepository:
    """Create a JsonAcademyRepository with the given principles list."""
    path = make_principles_file(tmp_path, principles)
    return JsonAcademyRepository(path)


def make_service(tmp_path: Path, principles: list) -> AcademyService:
    """Create an AcademyService backed by the given principles list."""
    repo = make_repo(tmp_path, principles)
    return AcademyService(repo)


REAL_DATA_PATH = REPO_ROOT / "data" / "engineering" / "principles.json"


# ===========================================================================
# 1. JSON LOADING
# ===========================================================================

class TestJsonLoading:

    def test_loads_valid_file_successfully(self, tmp_path):
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE])
        loader = AcademyLoader()
        principles = loader.load(path)
        assert len(principles) == 1

    def test_loaded_principle_has_correct_id(self, tmp_path):
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE])
        loader = AcademyLoader()
        principles = loader.load(path)
        assert principles[0].id == "dry"

    def test_loads_multiple_principles(self, tmp_path):
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2, JARVIS_PRINCIPLE])
        loader = AcademyLoader()
        principles = loader.load(path)
        assert len(principles) == 3

    def test_raises_on_missing_file(self, tmp_path):
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "principles.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        principle = {
            "id": "yagni",
            "name": "YAGNI",
            "category": "core",
            "summary": "You aren't gonna need it.",
            "rationale": "Speculative code is waste.",
            "guidance": "Build only what is needed now.",
            "violations": ["Premature optimisation"],
            "tags": ["yagni"],
            # examples and references omitted
        }
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        principles = loader.load(path)
        assert principles[0].examples == []
        assert principles[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        principle["future_field"] = "some value"
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        principles = loader.load(path)
        assert principles[0].extra.get("future_field") == "some value"

    def test_real_principles_file_loads(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present at expected path.")
        loader = AcademyLoader()
        principles = loader.load(REAL_DATA_PATH)
        assert len(principles) > 0

    def test_real_principles_file_has_expected_count(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present at expected path.")
        loader = AcademyLoader()
        principles = loader.load(REAL_DATA_PATH)
        # 5 SOLID + 8 core + 8 Jarvis = 21 total
        assert len(principles) == 21


# ===========================================================================
# 2. SCHEMA VALIDATION
# ===========================================================================

class TestSchemaValidation:

    def test_raises_when_top_level_is_not_object(self, tmp_path):
        path = tmp_path / "principles.json"
        path.write_text(json.dumps([VALID_PRINCIPLE]), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "top level" in str(exc_info.value).lower()

    def test_raises_when_principles_key_missing(self, tmp_path):
        path = tmp_path / "principles.json"
        path.write_text(json.dumps({"data": []}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "principles" in str(exc_info.value)

    def test_raises_when_principles_is_not_list(self, tmp_path):
        path = tmp_path / "principles.json"
        path.write_text(json.dumps({"principles": {}}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "array" in str(exc_info.value).lower()

    def test_raises_when_principle_is_not_object(self, tmp_path):
        path = make_principles_file(tmp_path, ["not a dict"])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError):
            loader.load(path)

    def test_all_real_principles_have_required_fields(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        loader = AcademyLoader()
        principles = loader.load(REAL_DATA_PATH)
        from core.engineering.academy.models import REQUIRED_FIELDS
        for p in principles:
            for field in REQUIRED_FIELDS:
                assert hasattr(p, field), f"Principle '{p.id}' missing field '{field}'"

    def test_violations_field_must_be_list(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        principle["violations"] = "not a list"
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load(path)
        assert "violations" in str(exc_info.value)

    def test_tags_field_must_be_list(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        principle["tags"] = "not a list"
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load(path)
        assert "tags" in str(exc_info.value)

    def test_empty_id_string_raises(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        principle["id"] = "   "
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load(path)

    def test_empty_name_string_raises(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        principle["name"] = ""
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load(path)


# ===========================================================================
# 3. MISSING REQUIRED FIELDS
# ===========================================================================

class TestMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "summary", "rationale", "guidance", "violations", "tags"
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        principle = dict(VALID_PRINCIPLE)
        del principle[missing_field]
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load(path)
        assert missing_field in str(exc_info.value)

    def test_invalid_principle_error_contains_field_name(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        del principle["rationale"]
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load(path)
        assert "rationale" in str(exc_info.value)

    def test_invalid_principle_error_contains_principle_id(self, tmp_path):
        principle = dict(VALID_PRINCIPLE)
        del principle["guidance"]
        path = make_principles_file(tmp_path, [principle])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load(path)
        assert "dry" in str(exc_info.value)


# ===========================================================================
# 4. DUPLICATE ID DETECTION
# ===========================================================================

class TestDuplicateIdDetection:

    def test_raises_on_duplicate_ids(self, tmp_path):
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_raises_on_duplicate_ids_different_names(self, tmp_path):
        duplicate = dict(VALID_PRINCIPLE)
        duplicate["name"] = "A Different Name"
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE, duplicate])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load(path)
        assert "dry" in str(exc_info.value)

    def test_no_duplicate_ids_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        loader = AcademyLoader()
        principles = loader.load(REAL_DATA_PATH)
        ids = [p.id for p in principles]
        assert len(ids) == len(set(ids)), "Duplicate IDs found in principles.json"


# ===========================================================================
# 5. REPOSITORY QUERIES
# ===========================================================================

class TestRepositoryQueries:

    def test_get_by_id_returns_correct_principle(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        result = repo.get_by_id("dry")
        assert result is not None
        assert result.id == "dry"
        assert result.name == "Don't Repeat Yourself"

    def test_get_by_id_returns_none_for_unknown_id(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        result = repo.get_by_id("nonexistent")
        assert result is None

    def test_list_all_returns_all_principles(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2, JARVIS_PRINCIPLE])
        results = repo.list_all()
        assert len(results) == 3

    def test_list_all_on_empty_data(self, tmp_path):
        repo = make_repo(tmp_path, [])
        results = repo.list_all()
        assert results == []

    def test_list_all_returns_list_type(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        results = repo.list_all()
        assert isinstance(results, list)

    def test_all_results_are_engineering_principle_instances(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        for p in repo.list_all():
            assert isinstance(p, EngineeringPrinciple)

    def test_repo_is_subclass_of_abstract_repository(self, tmp_path):
        path = make_principles_file(tmp_path, [VALID_PRINCIPLE])
        repo = JsonAcademyRepository(path)
        assert isinstance(repo, AcademyRepository)


# ===========================================================================
# 6. CATEGORY FILTERING
# ===========================================================================

class TestCategoryFiltering:

    def test_filter_by_category_returns_matching_principles(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2, JARVIS_PRINCIPLE])
        results = repo.filter_by_category("core")
        assert len(results) == 2
        for p in results:
            assert p.category == "core"

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, JARVIS_PRINCIPLE])
        results = repo.filter_by_category("CORE")
        assert len(results) == 1
        assert results[0].id == "dry"

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        results = repo.filter_by_category("unknown-category")
        assert results == []

    def test_filter_by_category_jarvis(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, JARVIS_PRINCIPLE])
        results = repo.filter_by_category("jarvis")
        assert len(results) == 1
        assert results[0].id == "jarvis-fail-fast"

    def test_filter_by_category_real_data_solid(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("solid")
        assert len(results) == 5

    def test_filter_by_category_real_data_jarvis(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("jarvis")
        assert len(results) == 8

    def test_filter_by_category_real_data_core(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("core")
        assert len(results) == 8


# ===========================================================================
# 7. TAG FILTERING
# ===========================================================================

class TestTagFiltering:

    def test_filter_by_tag_returns_matching_principles(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = repo.filter_by_tag("simplicity")
        assert len(results) == 1
        assert results[0].id == "kiss"

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        results = repo.filter_by_tag("DRY")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown_tag(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        results = repo.filter_by_tag("nonexistent-tag")
        assert results == []

    def test_filter_by_tag_matches_shared_tags(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        # both have "dry" or "kiss" but also let's check "maintainability"
        results = repo.filter_by_tag("maintainability")
        assert len(results) == 1
        assert results[0].id == "dry"

    def test_filter_by_tag_jarvis_tag(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, JARVIS_PRINCIPLE])
        results = repo.filter_by_tag("jarvis")
        assert len(results) == 1
        assert results[0].id == "jarvis-fail-fast"

    def test_filter_by_tag_real_data_design_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("design")
        assert len(results) > 0

    def test_filter_by_tag_real_data_jarvis_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("jarvis")
        assert len(results) == 8


# ===========================================================================
# 8. DETERMINISTIC SEARCH
# ===========================================================================

class TestDeterministicSearch:

    def test_search_finds_by_name_substring(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = service.search("Repeat")
        assert len(results) == 1
        assert results[0].id == "dry"

    def test_search_finds_by_summary_substring(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = service.search("complexity")
        assert len(results) == 1
        assert results[0].id == "kiss"

    def test_search_finds_by_tag(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = service.search("simplicity")
        assert len(results) == 1
        assert results[0].id == "kiss"

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("REPEAT")
        assert len(results) == 1

    def test_search_returns_empty_for_no_match(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("zzznomatch")
        assert results == []

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("")
        assert results == []

    def test_search_whitespace_only_query_returns_empty(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("   ")
        assert results == []

    def test_search_results_are_sorted_by_id(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE_2, VALID_PRINCIPLE])
        # both have "core" in category or rationale — search by a common word
        results = service.search("complexity")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2, JARVIS_PRINCIPLE])
        results_1 = [p.id for p in service.search("a")]
        results_2 = [p.id for p in service.search("a")]
        assert results_1 == results_2

    def test_search_finds_in_violations(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("Copy-pasting")
        assert len(results) == 1

    def test_search_finds_in_guidance(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.search("shared function")
        assert len(results) == 1


# ===========================================================================
# 9. READ-ONLY BEHAVIOUR (frozen dataclass)
# ===========================================================================

class TestReadOnlyBehaviour:

    def test_principle_is_frozen(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        p = repo.get_by_id("dry")
        assert p is not None
        with pytest.raises((AttributeError, TypeError)):
            p.name = "Modified Name"  # type: ignore

    def test_principle_id_cannot_be_changed(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE])
        p = repo.get_by_id("dry")
        with pytest.raises((AttributeError, TypeError)):
            p.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = repo.list_all()
        results.clear()  # mutate the returned list
        # repo should still return both principles
        assert len(repo.list_all()) == 2

    def test_filter_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2])
        results = repo.filter_by_category("core")
        results.clear()
        assert len(repo.filter_by_category("core")) == 2


# ===========================================================================
# 10. SERVICE EXCEPTION HANDLING
# ===========================================================================

class TestServiceExceptionHandling:

    def test_get_principle_raises_not_found_for_unknown_id(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_principle("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_principle_not_found_error_has_principle_id(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_principle("missing-id")
        assert exc_info.value.principle_id == "missing-id"

    def test_principle_not_found_is_subclass_of_academy_error(self):
        exc = PrincipleNotFoundError("test-id")
        assert isinstance(exc, AcademyError)

    def test_invalid_principle_error_is_subclass_of_academy_error(self):
        exc = InvalidPrincipleError("test-id", "reason")
        assert isinstance(exc, AcademyError)

    def test_academy_schema_error_is_subclass_of_academy_error(self):
        exc = AcademySchemaError("reason")
        assert isinstance(exc, AcademyError)

    def test_all_academy_errors_are_subclass_of_exception(self):
        for exc_class in (AcademyError, PrincipleNotFoundError, InvalidPrincipleError, AcademySchemaError):
            assert issubclass(exc_class, Exception)


# ===========================================================================
# 11. EMPTY RESULT HANDLING
# ===========================================================================

class TestEmptyResultHandling:

    def test_filter_by_category_empty_repo(self, tmp_path):
        repo = make_repo(tmp_path, [])
        results = repo.filter_by_category("core")
        assert results == []

    def test_filter_by_tag_empty_repo(self, tmp_path):
        repo = make_repo(tmp_path, [])
        results = repo.filter_by_tag("dry")
        assert results == []

    def test_search_empty_repo(self, tmp_path):
        service = make_service(tmp_path, [])
        results = service.search("anything")
        assert results == []

    def test_list_principles_empty_repo(self, tmp_path):
        service = make_service(tmp_path, [])
        results = service.list_principles()
        assert results == []

    def test_get_by_id_empty_repo(self, tmp_path):
        repo = make_repo(tmp_path, [])
        result = repo.get_by_id("dry")
        assert result is None

    def test_find_by_category_no_match_returns_empty_list(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.find_by_category("completely-unknown")
        assert results == []
        assert isinstance(results, list)

    def test_find_by_tag_no_match_returns_empty_list(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE])
        results = service.find_by_tag("completely-unknown")
        assert results == []
        assert isinstance(results, list)


# ===========================================================================
# 12. STABLE ORDERING
# ===========================================================================

class TestStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        # Insert in reverse alphabetical order
        repo = make_repo(tmp_path, [VALID_PRINCIPLE_2, JARVIS_PRINCIPLE, VALID_PRINCIPLE])
        results = repo.list_all()
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_list_principles_service_is_sorted_by_id(self, tmp_path):
        service = make_service(tmp_path, [VALID_PRINCIPLE_2, JARVIS_PRINCIPLE, VALID_PRINCIPLE])
        results = service.list_principles()
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_filter_by_category_results_are_sorted(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE_2, VALID_PRINCIPLE])
        results = repo.filter_by_category("core")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_filter_by_tag_results_are_sorted(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE_2, VALID_PRINCIPLE])
        # Both have "dry" and "kiss" tags respectively — filter by something broader
        results = repo.filter_by_tag("dry")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_real_data_list_all_is_sorted(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        results = repo.list_all()
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_list_all_order_is_stable_across_calls(self, tmp_path):
        repo = make_repo(tmp_path, [VALID_PRINCIPLE, VALID_PRINCIPLE_2, JARVIS_PRINCIPLE])
        first = [p.id for p in repo.list_all()]
        second = [p.id for p in repo.list_all()]
        assert first == second


# ===========================================================================
# 13. REAL DATA — end-to-end validation
# ===========================================================================

class TestRealDataEndToEnd:

    def test_service_get_principle_by_id(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        principle = service.get_principle("dry")
        assert principle.name == "Don't Repeat Yourself"

    def test_service_get_solid_srp(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        principle = service.get_principle("solid-srp")
        assert "Single Responsibility" in principle.name

    def test_service_search_for_solid(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        results = service.search("solid")
        assert len(results) >= 5  # at minimum the 5 SOLID entries

    def test_service_find_jarvis_principles(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        results = service.find_by_category("jarvis")
        ids = [p.id for p in results]
        assert "jarvis-evidence-before-assumption" in ids
        assert "jarvis-architecture-before-implementation" in ids

    def test_service_search_returns_principle_for_duplication(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        results = service.search("duplication")
        assert any(p.id == "dry" for p in results)

    def test_service_raises_for_nonexistent_principle(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        with pytest.raises(PrincipleNotFoundError):
            service.get_principle("nonexistent-principle-xyz")

    def test_every_real_principle_is_retrievable_by_id(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        for principle in repo.list_all():
            retrieved = service.get_principle(principle.id)
            assert retrieved.id == principle.id

    def test_find_by_process_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_DATA_PATH)
        service = AcademyService(repo)
        results = service.find_by_tag("process")
        assert len(results) > 0
        jarvis_ids = [p.id for p in results if p.category == "jarvis"]
        assert len(jarvis_ids) > 0
