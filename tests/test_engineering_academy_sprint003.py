"""
Genesis-019 Sprint 003 — Engineering Academy Anti-Patterns
Deterministic unit tests. Completely self-contained.

Coverage:
  - Anti-pattern JSON loading
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
"""

import json
import sys
from pathlib import Path

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
from core.engineering.academy.json_repository import JsonAntiPatternRepository
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import AntiPattern, REQUIRED_ANTI_PATTERN_FIELDS
from core.engineering.academy.repository import AntiPatternRepository
from core.engineering.academy.service import AntiPatternService

REAL_ANTI_PATTERNS_PATH = REPO_ROOT / "data" / "engineering" / "anti_patterns.json"

# ---------------------------------------------------------------------------
# Sprint 003 helpers
# ---------------------------------------------------------------------------

VALID_ANTI_PATTERN = {
    "id": "god-object",
    "name": "God Object",
    "category": "object-oriented",
    "description": "A single class that knows too much or does too much.",
    "symptoms": ["A class with hundreds of methods", "Most other classes depend on it"],
    "consequences": ["Impossible to unit test", "Parallel development blocked"],
    "detection": ["Count public methods — more than 20 is a warning sign"],
    "recommended_solution": "Apply the Single Responsibility Principle.",
    "related_principles": ["solid-srp"],
    "related_patterns": ["facade"],
    "examples": ["A JarvisCore that handles AI, voice, and memory directly"],
    "references": ["Robert C. Martin — Clean Code"],
    "tags": ["god-object", "object-oriented", "srp", "bloat"],
}

VALID_ANTI_PATTERN_2 = {
    "id": "magic-numbers",
    "name": "Magic Numbers",
    "category": "readability",
    "description": "Numeric literals embedded in code with no explanation.",
    "symptoms": ["Literals appearing in conditions with no named constant"],
    "consequences": ["Future developers must guess the meaning of the value"],
    "detection": ["Audit any numeric literal other than 0 and 1"],
    "recommended_solution": "Replace with named constants.",
    "tags": ["magic-numbers", "readability", "constants"],
}

VALID_ANTI_PATTERN_3 = {
    "id": "dead-code",
    "name": "Dead Code",
    "category": "maintenance",
    "description": "Code that is never executed at runtime.",
    "symptoms": ["Functions defined but never called"],
    "consequences": ["Misleads readers into believing it is relevant"],
    "detection": ["Use static analysis tools to detect unreachable code"],
    "recommended_solution": "Delete dead code immediately.",
    "tags": ["dead-code", "maintenance", "cleanup"],
}


def make_anti_patterns_file(tmp_path, anti_patterns: list):
    data = {"anti_patterns": anti_patterns}
    path = tmp_path / "anti_patterns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_anti_pattern_repo(tmp_path, anti_patterns: list):
    path = make_anti_patterns_file(tmp_path, anti_patterns)
    return JsonAntiPatternRepository(path)


def make_anti_pattern_service(tmp_path, anti_patterns: list):
    repo = make_anti_pattern_repo(tmp_path, anti_patterns)
    return AntiPatternService(repo)


# ===========================================================================
# S3-1. ANTI-PATTERN LOADING
# ===========================================================================

class TestAntiPatternLoading:

    def test_loads_valid_file_successfully(self, tmp_path):
        path = make_anti_patterns_file(tmp_path, [VALID_ANTI_PATTERN])
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(path)
        assert len(anti_patterns) == 1

    def test_loaded_anti_pattern_has_correct_id(self, tmp_path):
        path = make_anti_patterns_file(tmp_path, [VALID_ANTI_PATTERN])
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(path)
        assert anti_patterns[0].id == "god-object"

    def test_loads_multiple_anti_patterns(self, tmp_path):
        path = make_anti_patterns_file(
            tmp_path,
            [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN_3]
        )
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(path)
        assert len(anti_patterns) == 3

    def test_raises_on_missing_file(self, tmp_path):
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_anti_patterns(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "anti_patterns.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_anti_patterns(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        ap = {
            "id": "tight-coupling",
            "name": "Tight Coupling",
            "category": "structural",
            "description": "Components depend on concrete implementations.",
            "symptoms": ["Direct instantiation of concrete classes"],
            "consequences": ["Cannot test independently"],
            "detection": ["Look for direct instantiation"],
            "recommended_solution": "Apply Dependency Inversion.",
            "tags": ["tight-coupling"],
            # related_principles, related_patterns, examples, references omitted
        }
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        result = loader.load_anti_patterns(path)
        assert result[0].related_principles == []
        assert result[0].related_patterns == []
        assert result[0].examples == []
        assert result[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["future_field"] = "some value"
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        result = loader.load_anti_patterns(path)
        assert result[0].extra.get("future_field") == "some value"

    def test_real_anti_patterns_file_loads(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(REAL_ANTI_PATTERNS_PATH)
        assert len(anti_patterns) > 0

    def test_real_anti_patterns_file_has_expected_count(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(REAL_ANTI_PATTERNS_PATH)
        assert len(anti_patterns) == 12


# ===========================================================================
# S3-2. ANTI-PATTERN SCHEMA VALIDATION
# ===========================================================================

class TestAntiPatternSchemaValidation:

    def test_raises_when_top_level_key_missing(self, tmp_path):
        path = tmp_path / "anti_patterns.json"
        path.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_anti_patterns(path)
        assert "anti_patterns" in str(exc_info.value)

    def test_raises_when_anti_pattern_is_not_object(self, tmp_path):
        path = make_anti_patterns_file(tmp_path, ["not a dict"])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError):
            loader.load_anti_patterns(path)

    def test_symptoms_field_must_be_list(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["symptoms"] = "not a list"
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_anti_patterns(path)
        assert "symptoms" in str(exc_info.value)

    def test_consequences_field_must_be_list(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["consequences"] = "not a list"
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_anti_patterns(path)
        assert "consequences" in str(exc_info.value)

    def test_detection_field_must_be_list(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["detection"] = "not a list"
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_anti_patterns(path)
        assert "detection" in str(exc_info.value)

    def test_tags_field_must_be_list(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["tags"] = "not a list"
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_anti_patterns(path)
        assert "tags" in str(exc_info.value)

    def test_empty_description_raises(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["description"] = "   "
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_anti_patterns(path)

    def test_empty_recommended_solution_raises(self, tmp_path):
        ap = dict(VALID_ANTI_PATTERN)
        ap["recommended_solution"] = ""
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_anti_patterns(path)

    def test_all_required_anti_pattern_fields_present_in_real_data(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(REAL_ANTI_PATTERNS_PATH)
        for ap in anti_patterns:
            for f in REQUIRED_ANTI_PATTERN_FIELDS:
                assert hasattr(ap, f), f"AntiPattern '{ap.id}' missing field '{f}'"


# ===========================================================================
# S3-3. ANTI-PATTERN MISSING REQUIRED FIELDS
# ===========================================================================

class TestAntiPatternMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "description",
        "symptoms", "consequences", "detection",
        "recommended_solution", "tags",
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        ap = dict(VALID_ANTI_PATTERN)
        del ap[missing_field]
        path = make_anti_patterns_file(tmp_path, [ap])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_anti_patterns(path)
        assert missing_field in str(exc_info.value)


# ===========================================================================
# S3-4. ANTI-PATTERN DUPLICATE DETECTION
# ===========================================================================

class TestAntiPatternDuplicateDetection:

    def test_raises_on_duplicate_ids(self, tmp_path):
        path = make_anti_patterns_file(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN]
        )
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_anti_patterns(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_no_duplicate_ids_in_real_data(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        loader = AcademyLoader()
        anti_patterns = loader.load_anti_patterns(REAL_ANTI_PATTERNS_PATH)
        ids = [ap.id for ap in anti_patterns]
        assert len(ids) == len(set(ids)), "Duplicate IDs found in anti_patterns.json"


# ===========================================================================
# S3-5. ANTI-PATTERN REPOSITORY QUERIES
# ===========================================================================

class TestAntiPatternRepositoryQueries:

    def test_get_by_id_returns_correct_anti_pattern(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        result = repo.get_by_id("god-object")
        assert result is not None
        assert result.id == "god-object"
        assert result.name == "God Object"

    def test_get_by_id_returns_none_for_unknown(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        assert repo.get_by_id("nonexistent") is None

    def test_list_all_returns_all_anti_patterns(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path,
            [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN_3]
        )
        assert len(repo.list_all()) == 3

    def test_list_all_on_empty_data(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [])
        assert repo.list_all() == []

    def test_all_results_are_anti_pattern_instances(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        for ap in repo.list_all():
            assert isinstance(ap, AntiPattern)

    def test_repo_is_subclass_of_anti_pattern_repository(self, tmp_path):
        path = make_anti_patterns_file(tmp_path, [VALID_ANTI_PATTERN])
        repo = JsonAntiPatternRepository(path)
        assert isinstance(repo, AntiPatternRepository)


# ===========================================================================
# S3-6. ANTI-PATTERN CATEGORY FILTERING
# ===========================================================================

class TestAntiPatternCategoryFiltering:

    def test_filter_by_category_returns_matching(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path,
            [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN_3]
        )
        results = repo.filter_by_category("object-oriented")
        assert len(results) == 1
        assert results[0].id == "god-object"

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        results = repo.filter_by_category("OBJECT-ORIENTED")
        assert len(results) == 1

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        assert repo.filter_by_category("unknown-category") == []

    def test_filter_by_category_real_data_object_oriented(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_category("object-oriented")
        assert len(results) == 2
        ids = {ap.id for ap in results}
        assert "god-object" in ids
        assert "feature-envy" in ids

    def test_filter_by_category_real_data_structural(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_category("structural")
        assert len(results) == 3

    def test_filter_by_category_real_data_maintenance(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_category("maintenance")
        assert len(results) == 3

    def test_filter_by_category_real_data_readability(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_category("readability")
        assert len(results) == 3

    def test_filter_by_category_real_data_process(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_category("process")
        assert len(results) == 1
        assert results[0].id == "premature-optimisation"


# ===========================================================================
# S3-7. ANTI-PATTERN TAG FILTERING
# ===========================================================================

class TestAntiPatternTagFiltering:

    def test_filter_by_tag_returns_matching(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        results = repo.filter_by_tag("readability")
        assert len(results) == 1
        assert results[0].id == "magic-numbers"

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        results = repo.filter_by_tag("SRP")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        assert repo.filter_by_tag("nonexistent-tag") == []

    def test_filter_by_tag_refactoring_real_data(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        results = repo.filter_by_tag("refactoring")
        assert len(results) > 0


# ===========================================================================
# S3-8. ANTI-PATTERN RELATIONSHIP VALIDATION
# ===========================================================================

class TestAntiPatternRelationshipValidation:

    def test_related_principles_is_a_list(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        ap = repo.get_by_id("god-object")
        assert isinstance(ap.related_principles, list)

    def test_related_patterns_is_a_list(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        ap = repo.get_by_id("god-object")
        assert isinstance(ap.related_patterns, list)

    def test_real_data_related_principles_are_strings(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        for ap in repo.list_all():
            for rp in ap.related_principles:
                assert isinstance(rp, str) and rp.strip(), \
                    f"AntiPattern '{ap.id}' has empty related_principle"

    def test_real_data_related_patterns_are_strings(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        for ap in repo.list_all():
            for rp in ap.related_patterns:
                assert isinstance(rp, str) and rp.strip(), \
                    f"AntiPattern '{ap.id}' has empty related_pattern"

    def test_god_object_related_principles(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        ap = repo.get_by_id("god-object")
        assert "solid-srp" in ap.related_principles

    def test_tight_coupling_related_patterns(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        ap = repo.get_by_id("tight-coupling")
        assert "adapter" in ap.related_patterns or \
               "dependency-injection" in ap.related_patterns


# ===========================================================================
# S3-9. ANTI-PATTERN DETERMINISTIC SEARCH
# ===========================================================================

class TestAntiPatternDeterministicSearch:

    def test_search_finds_by_name_substring(self, tmp_path):
        service = make_anti_pattern_service(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        results = service.search("God")
        assert len(results) == 1
        assert results[0].id == "god-object"

    def test_search_finds_by_description_substring(self, tmp_path):
        service = make_anti_pattern_service(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        results = service.search("literals embedded")
        assert any(ap.id == "magic-numbers" for ap in results)

    def test_search_finds_by_tag(self, tmp_path):
        service = make_anti_pattern_service(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        results = service.search("constants")
        assert len(results) == 1
        assert results[0].id == "magic-numbers"

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        results = service.search("GOD")
        assert len(results) == 1

    def test_search_returns_empty_for_no_match(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        assert service.search("zzznomatch") == []

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        assert service.search("") == []

    def test_search_whitespace_only_returns_empty(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        assert service.search("   ") == []

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_anti_pattern_service(
            tmp_path,
            [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN_3]
        )
        first = [ap.id for ap in service.search("a")]
        second = [ap.id for ap in service.search("a")]
        assert first == second

    def test_search_finds_in_symptoms(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        results = service.search("hundreds of methods")
        assert len(results) == 1

    def test_search_finds_in_recommended_solution(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        results = service.search("Single Responsibility")
        assert len(results) == 1


# ===========================================================================
# S3-10. ANTI-PATTERN READ-ONLY BEHAVIOUR
# ===========================================================================

class TestAntiPatternReadOnlyBehaviour:

    def test_anti_pattern_is_frozen(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        ap = repo.get_by_id("god-object")
        assert ap is not None
        with pytest.raises((AttributeError, TypeError)):
            ap.name = "Modified"  # type: ignore

    def test_anti_pattern_id_cannot_be_changed(self, tmp_path):
        repo = make_anti_pattern_repo(tmp_path, [VALID_ANTI_PATTERN])
        ap = repo.get_by_id("god-object")
        with pytest.raises((AttributeError, TypeError)):
            ap.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path, [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        results = repo.list_all()
        results.clear()
        assert len(repo.list_all()) == 2


# ===========================================================================
# S3-11. ANTI-PATTERN SERVICE EXCEPTION HANDLING
# ===========================================================================

class TestAntiPatternServiceExceptions:

    def test_get_anti_pattern_raises_for_unknown_id(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_anti_pattern("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_not_found_error_has_id(self, tmp_path):
        service = make_anti_pattern_service(tmp_path, [VALID_ANTI_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_anti_pattern("missing-id")
        assert exc_info.value.principle_id == "missing-id"


# ===========================================================================
# S3-12. ANTI-PATTERN STABLE ORDERING
# ===========================================================================

class TestAntiPatternStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path,
            [VALID_ANTI_PATTERN_3, VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2]
        )
        ids = [ap.id for ap in repo.list_all()]
        assert ids == sorted(ids)

    def test_filter_by_category_results_are_sorted(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path, [VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN]
        )
        # Add another object-oriented anti-pattern to test sort
        ap_extra = dict(VALID_ANTI_PATTERN)
        ap_extra["id"] = "feature-envy"
        ap_extra["name"] = "Feature Envy"
        path = make_anti_patterns_file(
            tmp_path, [VALID_ANTI_PATTERN, ap_extra]
        )
        repo2 = JsonAntiPatternRepository(path)
        results = repo2.filter_by_category("object-oriented")
        ids = [ap.id for ap in results]
        assert ids == sorted(ids)

    def test_list_all_order_is_stable_across_calls(self, tmp_path):
        repo = make_anti_pattern_repo(
            tmp_path,
            [VALID_ANTI_PATTERN, VALID_ANTI_PATTERN_2, VALID_ANTI_PATTERN_3]
        )
        first = [ap.id for ap in repo.list_all()]
        second = [ap.id for ap in repo.list_all()]
        assert first == second

    def test_real_data_list_all_is_sorted(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        ids = [ap.id for ap in repo.list_all()]
        assert ids == sorted(ids)


# ===========================================================================
# S3-13. REAL DATA END-TO-END
# ===========================================================================

class TestAntiPatternRealDataEndToEnd:

    def test_service_get_god_object_by_id(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        ap = service.get_anti_pattern("god-object")
        assert ap.name == "God Object"

    def test_service_get_premature_optimisation(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        ap = service.get_anti_pattern("premature-optimisation")
        assert "Knuth" in " ".join(ap.references)

    def test_service_list_returns_all_twelve(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        assert len(service.list_anti_patterns()) == 12

    def test_every_real_anti_pattern_retrievable_by_id(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        for ap in repo.list_all():
            retrieved = service.get_anti_pattern(ap.id)
            assert retrieved.id == ap.id

    def test_search_for_coupling_finds_related_entries(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        results = service.search("coupling")
        ids = {ap.id for ap in results}
        assert "tight-coupling" in ids
        assert "circular-dependency" in ids

    def test_search_for_refactoring_returns_multiple(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        results = service.search("refactoring")
        assert len(results) >= 3

    def test_service_raises_for_nonexistent_anti_pattern(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        with pytest.raises(PrincipleNotFoundError):
            service.get_anti_pattern("nonexistent-xyz")

    def test_find_by_category_process_returns_premature_optimisation(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        results = service.find_by_category("process")
        assert any(ap.id == "premature-optimisation" for ap in results)

    def test_find_by_tag_dry_returns_copy_paste(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        service = AntiPatternService(repo)
        results = service.find_by_tag("dry")
        assert any(ap.id == "copy-paste-programming" for ap in results)

    def test_every_anti_pattern_has_non_empty_symptoms(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        for ap in repo.list_all():
            assert len(ap.symptoms) > 0, \
                f"AntiPattern '{ap.id}' has no symptoms"

    def test_every_anti_pattern_has_non_empty_detection(self):
        if not REAL_ANTI_PATTERNS_PATH.exists():
            pytest.skip("Real anti_patterns.json not present.")
        repo = JsonAntiPatternRepository(REAL_ANTI_PATTERNS_PATH)
        for ap in repo.list_all():
            assert len(ap.detection) > 0, \
                f"AntiPattern '{ap.id}' has no detection guidance"