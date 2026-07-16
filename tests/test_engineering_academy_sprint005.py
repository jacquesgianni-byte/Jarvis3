"""
Genesis-019 Sprint 005 — Engineering Academy Best Practices
Deterministic unit tests. Completely self-contained.

Coverage:
  - Best practice JSON loading
  - Schema validation
  - Missing required fields
  - Duplicate ID detection
  - Repository queries
  - Category filtering
  - Tag filtering
  - Relationship validation
  - Deterministic search
  - Read-only behaviour (frozen dataclass)
  - Service exception handling
  - Stable ordering
  - Real data end-to-end validation

No network access. No AI providers. All tests are deterministic.
All imports, constants, and fixtures are defined in this file.
"""

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.engineering.academy.exceptions import (
    AcademyError,
    AcademySchemaError,
    InvalidPrincipleError,
    PrincipleNotFoundError,
)
from core.engineering.academy.json_repository import JsonBestPracticeRepository
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import (
    BestPractice,
    REQUIRED_BEST_PRACTICE_FIELDS,
)
from core.engineering.academy.repository import BestPracticeRepository
from core.engineering.academy.service import BestPracticeService

# ---------------------------------------------------------------------------
# Real data path
# ---------------------------------------------------------------------------

REAL_DATA_PATH = REPO_ROOT / "data" / "engineering" / "best_practices.json"

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

VALID_BP = {
    "id": "single-responsibility",
    "name": "Single Responsibility",
    "category": "design",
    "description": "Every function, class, and module should have one reason to change.",
    "rationale": "Code that mixes responsibilities becomes difficult to test and change.",
    "implementation_guidance": [
        "Name every class so its single responsibility is obvious",
        "If you need 'and' to describe what a function does, split it",
    ],
    "benefits": ["Each unit is independently testable", "Changes to one concern cannot break others"],
    "common_mistakes": ["Creating Utils classes that accumulate unrelated functions"],
    "related_principles": ["solid-srp", "separation-of-concerns"],
    "related_patterns": ["facade", "strategy"],
    "related_anti_patterns": ["god-object", "long-method"],
    "related_architecture_patterns": ["clean-architecture", "layered-architecture"],
    "examples": ["Jarvis AcademyLoader has one responsibility: read JSON and construct models"],
    "references": ["Robert C. Martin — Clean Code"],
    "tags": ["single-responsibility", "design", "srp", "cohesion"],
}

VALID_BP_2 = {
    "id": "fail-fast",
    "name": "Fail Fast",
    "category": "reliability",
    "description": "Detect errors at the earliest possible point and report them immediately.",
    "rationale": "When an error is not detected immediately, it propagates through the system.",
    "implementation_guidance": [
        "Raise specific exceptions at the point of violation",
        "Validate preconditions at the start of every function",
    ],
    "benefits": ["Bugs are caught at the exact point they occur"],
    "common_mistakes": ["Catching exceptions broadly and logging 'something went wrong'"],
    "tags": ["fail-fast", "reliability", "errors", "debugging"],
}

VALID_BP_3 = {
    "id": "dry",
    "name": "DRY (Don't Repeat Yourself)",
    "category": "design",
    "description": "Every piece of knowledge should have a single authoritative representation.",
    "rationale": "Duplication is the root cause of a large class of bugs.",
    "implementation_guidance": [
        "Extract duplicated logic into a shared function the first time it appears twice",
    ],
    "benefits": ["A bug fixed once is fixed everywhere"],
    "common_mistakes": ["Merging code that is accidentally similar but conceptually distinct"],
    "tags": ["dry", "design", "duplication", "maintainability"],
}


def make_bp_file(tmp_path: Path, practices: list) -> Path:
    data = {"best_practices": practices}
    path = tmp_path / "best_practices.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_bp_repo(tmp_path: Path, practices: list) -> JsonBestPracticeRepository:
    path = make_bp_file(tmp_path, practices)
    return JsonBestPracticeRepository(path)


def make_bp_service(tmp_path: Path, practices: list) -> BestPracticeService:
    repo = make_bp_repo(tmp_path, practices)
    return BestPracticeService(repo)


# ===========================================================================
# 1. LOADING
# ===========================================================================

class TestBestPracticeLoading:

    def test_loads_valid_file_successfully(self, tmp_path):
        path = make_bp_file(tmp_path, [VALID_BP])
        loader = AcademyLoader()
        practices = loader.load_best_practices(path)
        assert len(practices) == 1

    def test_loaded_practice_has_correct_id(self, tmp_path):
        path = make_bp_file(tmp_path, [VALID_BP])
        loader = AcademyLoader()
        practices = loader.load_best_practices(path)
        assert practices[0].id == "single-responsibility"

    def test_loads_multiple_practices(self, tmp_path):
        path = make_bp_file(tmp_path, [VALID_BP, VALID_BP_2, VALID_BP_3])
        loader = AcademyLoader()
        practices = loader.load_best_practices(path)
        assert len(practices) == 3

    def test_raises_on_missing_file(self, tmp_path):
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_best_practices(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "best_practices.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_best_practices(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        practice = {
            "id": "kiss",
            "name": "KISS",
            "category": "design",
            "description": "Prefer the simplest solution.",
            "rationale": "Every layer of abstraction adds complexity.",
            "implementation_guidance": ["Start with the simplest implementation"],
            "benefits": ["Simple code has fewer bugs"],
            "common_mistakes": ["Adding complexity speculatively"],
            "tags": ["kiss"],
            # related_* and examples and references omitted
        }
        path = make_bp_file(tmp_path, [practice])
        result = AcademyLoader().load_best_practices(path)
        assert result[0].related_principles == []
        assert result[0].related_patterns == []
        assert result[0].related_anti_patterns == []
        assert result[0].related_architecture_patterns == []
        assert result[0].examples == []
        assert result[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        practice = dict(VALID_BP)
        practice["future_field"] = "some value"
        path = make_bp_file(tmp_path, [practice])
        result = AcademyLoader().load_best_practices(path)
        assert result[0].extra.get("future_field") == "some value"

    def test_real_best_practices_file_loads(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        practices = AcademyLoader().load_best_practices(REAL_DATA_PATH)
        assert len(practices) > 0

    def test_real_best_practices_file_has_expected_count(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        practices = AcademyLoader().load_best_practices(REAL_DATA_PATH)
        assert len(practices) == 20


# ===========================================================================
# 2. SCHEMA VALIDATION
# ===========================================================================

class TestBestPracticeSchemaValidation:

    def test_raises_when_top_level_key_missing(self, tmp_path):
        path = tmp_path / "best_practices.json"
        path.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "best_practices" in str(exc_info.value)

    def test_raises_when_practice_is_not_object(self, tmp_path):
        path = make_bp_file(tmp_path, ["not a dict"])
        with pytest.raises(AcademySchemaError):
            AcademyLoader().load_best_practices(path)

    def test_implementation_guidance_must_be_list(self, tmp_path):
        practice = dict(VALID_BP)
        practice["implementation_guidance"] = "not a list"
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "implementation_guidance" in str(exc_info.value)

    def test_benefits_must_be_list(self, tmp_path):
        practice = dict(VALID_BP)
        practice["benefits"] = "not a list"
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "benefits" in str(exc_info.value)

    def test_common_mistakes_must_be_list(self, tmp_path):
        practice = dict(VALID_BP)
        practice["common_mistakes"] = "not a list"
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "common_mistakes" in str(exc_info.value)

    def test_tags_must_be_list(self, tmp_path):
        practice = dict(VALID_BP)
        practice["tags"] = "not a list"
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "tags" in str(exc_info.value)

    def test_empty_description_raises(self, tmp_path):
        practice = dict(VALID_BP)
        practice["description"] = "   "
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError):
            AcademyLoader().load_best_practices(path)

    def test_empty_rationale_raises(self, tmp_path):
        practice = dict(VALID_BP)
        practice["rationale"] = ""
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError):
            AcademyLoader().load_best_practices(path)

    def test_all_required_fields_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        practices = AcademyLoader().load_best_practices(REAL_DATA_PATH)
        for bp in practices:
            for f in REQUIRED_BEST_PRACTICE_FIELDS:
                assert hasattr(bp, f), f"BestPractice '{bp.id}' missing '{f}'"


# ===========================================================================
# 3. MISSING REQUIRED FIELDS
# ===========================================================================

class TestBestPracticeMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "description", "rationale",
        "implementation_guidance", "benefits", "common_mistakes", "tags",
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        practice = dict(VALID_BP)
        del practice[missing_field]
        path = make_bp_file(tmp_path, [practice])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert missing_field in str(exc_info.value)


# ===========================================================================
# 4. DUPLICATE DETECTION
# ===========================================================================

class TestBestPracticeDuplicateDetection:

    def test_raises_on_duplicate_ids(self, tmp_path):
        path = make_bp_file(tmp_path, [VALID_BP, VALID_BP])
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_best_practices(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_no_duplicate_ids_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        practices = AcademyLoader().load_best_practices(REAL_DATA_PATH)
        ids = [bp.id for bp in practices]
        assert len(ids) == len(set(ids))


# ===========================================================================
# 5. REPOSITORY QUERIES
# ===========================================================================

class TestBestPracticeRepositoryQueries:

    def test_get_by_id_returns_correct_practice(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2])
        result = repo.get_by_id("single-responsibility")
        assert result is not None
        assert result.id == "single-responsibility"
        assert result.name == "Single Responsibility"

    def test_get_by_id_returns_none_for_unknown(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        assert repo.get_by_id("nonexistent") is None

    def test_list_all_returns_all_practices(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2, VALID_BP_3])
        assert len(repo.list_all()) == 3

    def test_list_all_on_empty_data(self, tmp_path):
        repo = make_bp_repo(tmp_path, [])
        assert repo.list_all() == []

    def test_all_results_are_best_practice_instances(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2])
        for bp in repo.list_all():
            assert isinstance(bp, BestPractice)

    def test_repo_is_subclass_of_best_practice_repository(self, tmp_path):
        path = make_bp_file(tmp_path, [VALID_BP])
        repo = JsonBestPracticeRepository(path)
        assert isinstance(repo, BestPracticeRepository)

    def test_real_data_all_practices_retrievable(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        for bp in repo.list_all():
            retrieved = service.get_best_practice(bp.id)
            assert retrieved.id == bp.id


# ===========================================================================
# 6. CATEGORY FILTERING
# ===========================================================================

class TestBestPracticeCategoryFiltering:

    def test_filter_by_category_returns_matching(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2, VALID_BP_3])
        results = repo.filter_by_category("design")
        assert len(results) == 2
        ids = {bp.id for bp in results}
        assert "single-responsibility" in ids
        assert "dry" in ids

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        results = repo.filter_by_category("DESIGN")
        assert len(results) == 1

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        assert repo.filter_by_category("unknown-category") == []

    def test_real_data_design_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("design")
        assert len(results) >= 5
        ids = {bp.id for bp in results}
        assert "single-responsibility" in ids
        assert "dry" in ids
        assert "kiss" in ids
        assert "yagni" in ids
        assert "separation-of-concerns" in ids

    def test_real_data_reliability_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("reliability")
        assert len(results) >= 4
        ids = {bp.id for bp in results}
        assert "fail-fast" in ids
        assert "defensive-programming" in ids
        assert "error-handling" in ids
        assert "input-validation" in ids

    def test_real_data_quality_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("quality")
        assert len(results) >= 2
        ids = {bp.id for bp in results}
        assert "testing-first" in ids
        assert "code-reviews" in ids

    def test_real_data_process_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("process")
        assert len(results) >= 2
        ids = {bp.id for bp in results}
        assert "incremental-development" in ids
        assert "version-control-discipline" in ids

    def test_real_data_operations_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("operations")
        assert len(results) >= 2
        ids = {bp.id for bp in results}
        assert "logging-and-observability" in ids
        assert "configuration-over-hardcoding" in ids


# ===========================================================================
# 7. TAG FILTERING
# ===========================================================================

class TestBestPracticeTagFiltering:

    def test_filter_by_tag_returns_matching(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2])
        results = repo.filter_by_tag("reliability")
        assert len(results) == 1
        assert results[0].id == "fail-fast"

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        results = repo.filter_by_tag("DESIGN")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        assert repo.filter_by_tag("nonexistent-tag") == []

    def test_real_data_testability_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("testability")
        assert len(results) > 0

    def test_real_data_jarvis_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        # All practices reference Jarvis in examples but tags are specific
        # Verify we can filter by any real tag
        results = repo.filter_by_tag("simplicity")
        assert len(results) > 0


# ===========================================================================
# 8. RELATIONSHIP VALIDATION
# ===========================================================================

class TestBestPracticeRelationshipValidation:

    def test_related_principles_is_a_list(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        assert isinstance(bp.related_principles, list)

    def test_related_patterns_is_a_list(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        assert isinstance(bp.related_patterns, list)

    def test_related_anti_patterns_is_a_list(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        assert isinstance(bp.related_anti_patterns, list)

    def test_related_architecture_patterns_is_a_list(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        assert isinstance(bp.related_architecture_patterns, list)

    def test_real_data_related_principles_are_strings(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        for bp in repo.list_all():
            for rp in bp.related_principles:
                assert isinstance(rp, str) and rp.strip(), \
                    f"BestPractice '{bp.id}' has empty related_principle"

    def test_single_responsibility_references_god_object(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        bp = repo.get_by_id("single-responsibility")
        assert "god-object" in bp.related_anti_patterns

    def test_dry_references_copy_paste_anti_pattern(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        bp = repo.get_by_id("dry")
        assert "copy-paste-programming" in bp.related_anti_patterns

    def test_logging_references_logging_and_observability_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        bp = repo.get_by_id("logging-and-observability")
        assert "logging" in bp.tags


# ===========================================================================
# 9. DETERMINISTIC SEARCH
# ===========================================================================

class TestBestPracticeDeterministicSearch:

    def test_search_finds_by_name_substring(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP, VALID_BP_2])
        results = service.search("Single")
        assert any(bp.id == "single-responsibility" for bp in results)

    def test_search_finds_by_description_substring(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP, VALID_BP_2])
        results = service.search("earliest possible point")
        assert any(bp.id == "fail-fast" for bp in results)

    def test_search_finds_by_rationale(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP, VALID_BP_3])
        results = service.search("root cause")
        assert any(bp.id == "dry" for bp in results)

    def test_search_finds_by_tag(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP, VALID_BP_2])
        results = service.search("debugging")
        assert any(bp.id == "fail-fast" for bp in results)

    def test_search_finds_by_implementation_guidance(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        results = service.search("split it")
        assert any(bp.id == "single-responsibility" for bp in results)

    def test_search_finds_by_common_mistakes(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP_3])
        results = service.search("accidentally similar")
        assert any(bp.id == "dry" for bp in results)

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        results = service.search("SINGLE")
        assert len(results) == 1

    def test_search_returns_empty_for_no_match(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        assert service.search("zzznomatch") == []

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        assert service.search("") == []

    def test_search_whitespace_only_returns_empty(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        assert service.search("   ") == []

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP, VALID_BP_2, VALID_BP_3])
        first = [bp.id for bp in service.search("a")]
        second = [bp.id for bp in service.search("a")]
        assert first == second

    def test_real_data_search_for_jarvis(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        results = service.search("Jarvis")
        assert len(results) >= 5

    def test_real_data_search_for_test(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        results = service.search("test")
        assert len(results) > 0


# ===========================================================================
# 10. READ-ONLY BEHAVIOUR
# ===========================================================================

class TestBestPracticeReadOnlyBehaviour:

    def test_best_practice_is_frozen(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        assert bp is not None
        with pytest.raises((AttributeError, TypeError)):
            bp.name = "Modified"  # type: ignore

    def test_best_practice_id_cannot_be_changed(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP])
        bp = repo.get_by_id("single-responsibility")
        with pytest.raises((AttributeError, TypeError)):
            bp.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2])
        results = repo.list_all()
        results.clear()
        assert len(repo.list_all()) == 2

    def test_filter_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_3])
        results = repo.filter_by_category("design")
        results.clear()
        assert len(repo.filter_by_category("design")) == 2


# ===========================================================================
# 11. SERVICE EXCEPTION HANDLING
# ===========================================================================

class TestBestPracticeServiceExceptions:

    def test_get_raises_for_unknown_id(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_best_practice("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_not_found_error_has_id(self, tmp_path):
        service = make_bp_service(tmp_path, [VALID_BP])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_best_practice("missing-id")
        assert exc_info.value.principle_id == "missing-id"

    def test_not_found_is_subclass_of_academy_error(self):
        exc = PrincipleNotFoundError("test-id")
        assert isinstance(exc, AcademyError)


# ===========================================================================
# 12. STABLE ORDERING
# ===========================================================================

class TestBestPracticeStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP_3, VALID_BP, VALID_BP_2])
        ids = [bp.id for bp in repo.list_all()]
        assert ids == sorted(ids)

    def test_filter_by_category_results_are_sorted(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP_3, VALID_BP])
        results = repo.filter_by_category("design")
        ids = [bp.id for bp in results]
        assert ids == sorted(ids)

    def test_list_all_order_stable_across_calls(self, tmp_path):
        repo = make_bp_repo(tmp_path, [VALID_BP, VALID_BP_2, VALID_BP_3])
        first = [bp.id for bp in repo.list_all()]
        second = [bp.id for bp in repo.list_all()]
        assert first == second

    def test_real_data_list_all_is_sorted(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        ids = [bp.id for bp in repo.list_all()]
        assert ids == sorted(ids)


# ===========================================================================
# 13. REAL DATA END-TO-END
# ===========================================================================

class TestBestPracticeRealDataEndToEnd:

    def test_service_get_single_responsibility(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        bp = service.get_best_practice("single-responsibility")
        assert bp.name == "Single Responsibility"

    def test_service_get_refactoring_safely(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        bp = service.get_best_practice("refactoring-safely")
        assert "Fowler" in " ".join(bp.references)

    def test_service_list_returns_all_twenty(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        assert len(service.list_best_practices()) == 20

    def test_find_by_category_quality_returns_expected(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        results = service.find_by_category("quality")
        ids = {bp.id for bp in results}
        assert "testing-first" in ids
        assert "code-reviews" in ids
        assert "refactoring-safely" in ids

    def test_find_by_tag_tdd(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        results = service.find_by_tag("tdd")
        assert any(bp.id == "testing-first" for bp in results)

    def test_search_for_genesis_returns_multiple(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        results = service.search("Genesis")
        assert len(results) >= 3

    def test_service_raises_for_nonexistent(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        service = BestPracticeService(repo)
        with pytest.raises(PrincipleNotFoundError):
            service.get_best_practice("nonexistent-xyz")

    def test_every_practice_has_non_empty_implementation_guidance(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        for bp in repo.list_all():
            assert len(bp.implementation_guidance) > 0, \
                f"BestPractice '{bp.id}' has no implementation_guidance"

    def test_every_practice_has_non_empty_common_mistakes(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        for bp in repo.list_all():
            assert len(bp.common_mistakes) > 0, \
                f"BestPractice '{bp.id}' has no common_mistakes"

    def test_every_practice_has_non_empty_benefits(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        for bp in repo.list_all():
            assert len(bp.benefits) > 0, \
                f"BestPractice '{bp.id}' has no benefits"

    def test_every_practice_has_jarvis_example(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        for bp in repo.list_all():
            assert any("Jarvis" in ex for ex in bp.examples), \
                f"BestPractice '{bp.id}' has no Jarvis-specific example"

    def test_version_control_references_genesis(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        bp = repo.get_by_id("version-control-discipline")
        assert any("Genesis" in ex for ex in bp.examples)

    def test_incremental_development_references_freeze(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real best_practices.json not present.")
        repo = JsonBestPracticeRepository(REAL_DATA_PATH)
        bp = repo.get_by_id("incremental-development")
        assert any("frozen" in ex.lower() for ex in bp.examples)