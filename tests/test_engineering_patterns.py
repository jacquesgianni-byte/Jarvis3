"""
Genesis-019 Sprint 002 — Engineering Design Patterns
Extended deterministic unit tests.

This file EXTENDS test_engineering_academy.py from Sprint 001.
Sprint 001 tests are unchanged and still run in full.
Sprint 002 tests cover the new DesignPattern model, PatternRepository,
JsonPatternRepository, and PatternService.

Coverage (Sprint 002 additions):
  - Pattern JSON loading
  - Pattern schema validation
  - Pattern duplicate ID detection
  - Pattern missing required fields
  - Pattern repository queries (get, list, filter by category, filter by tag)
  - Pattern deterministic search
  - Pattern read-only behaviour (frozen dataclass)
  - Pattern exception handling
  - Pattern empty result handling
  - Pattern stable ordering

No network access. No AI providers. All tests are deterministic.
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
from core.engineering.academy.json_repository import (
    JsonAcademyRepository,
    JsonPatternRepository,
)
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import DesignPattern, EngineeringPrinciple
from core.engineering.academy.repository import AcademyRepository, PatternRepository
from core.engineering.academy.service import AcademyService, PatternService

# ---------------------------------------------------------------------------
# Paths to real data files
# ---------------------------------------------------------------------------

REAL_PRINCIPLES_PATH = REPO_ROOT / "data" / "engineering" / "principles.json"
REAL_PATTERNS_PATH = REPO_ROOT / "data" / "engineering" / "patterns.json"

# ---------------------------------------------------------------------------
# Pattern fixtures
# ---------------------------------------------------------------------------

VALID_PATTERN = {
    "id": "repository",
    "name": "Repository",
    "category": "architectural",
    "intent": "Encapsulate data access logic behind a collection-like interface.",
    "problem": "Business logic becomes tangled with database queries.",
    "solution": "Define an abstract interface that looks like a collection.",
    "when_to_use": ["When you need to swap storage backends"],
    "when_not_to_use": ["For simple scripts where direct calls are clearer"],
    "advantages": ["Domain logic is decoupled from persistence"],
    "disadvantages": ["Adds an extra layer of abstraction"],
    "related_principles": ["solid-dip", "solid-srp"],
    "examples": ["JsonAcademyRepository implements AcademyRepository"],
    "references": ["Martin Fowler — Patterns of Enterprise Application Architecture"],
    "tags": ["repository", "architectural", "testability", "decoupling"],
}

VALID_PATTERN_2 = {
    "id": "factory",
    "name": "Factory",
    "category": "creational",
    "intent": "Centralise object creation logic so callers are decoupled from concrete types.",
    "problem": "Callers become coupled to concrete types when constructing objects directly.",
    "solution": "Define a factory whose single responsibility is creating and returning objects.",
    "when_to_use": ["When the concrete type is determined at runtime"],
    "when_not_to_use": ["When there is only one concrete type"],
    "advantages": ["Callers are decoupled from concrete types"],
    "disadvantages": ["Adds indirection that can make code harder to trace"],
    "related_principles": ["solid-ocp", "solid-dip"],
    "examples": ["A RepositoryFactory returning JsonRepository or SqlRepository"],
    "references": ["Gang of Four — Design Patterns"],
    "tags": ["factory", "creational", "decoupling", "abstraction"],
}

VALID_PATTERN_BEHAVIOURAL = {
    "id": "strategy",
    "name": "Strategy",
    "category": "behavioural",
    "intent": "Define a family of algorithms and make them interchangeable.",
    "problem": "Hard-coded if/elif chains for algorithm variants violate Open/Closed.",
    "solution": "Extract each algorithm into its own class behind a shared interface.",
    "when_to_use": ["When multiple algorithm variants must be selectable at runtime"],
    "when_not_to_use": ["When only one algorithm exists"],
    "advantages": ["Algorithms are independently testable"],
    "disadvantages": ["Increases the number of classes"],
    "related_principles": ["solid-ocp"],
    "examples": ["A SearchStrategy interface with KeywordSearchStrategy"],
    "references": ["Gang of Four — Design Patterns"],
    "tags": ["strategy", "behavioural", "algorithm", "runtime"],
}


def make_patterns_file(tmp_path: Path, patterns: list) -> Path:
    data = {"patterns": patterns}
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_pattern_repo(tmp_path: Path, patterns: list) -> JsonPatternRepository:
    path = make_patterns_file(tmp_path, patterns)
    return JsonPatternRepository(path)


def make_pattern_service(tmp_path: Path, patterns: list) -> PatternService:
    repo = make_pattern_repo(tmp_path, patterns)
    return PatternService(repo)


# ===========================================================================
# 1. PATTERN JSON LOADING
# ===========================================================================

class TestPatternJsonLoading:

    def test_loads_valid_patterns_file(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN])
        loader = AcademyLoader()
        patterns = loader.load_patterns(path)
        assert len(patterns) == 1

    def test_loaded_pattern_has_correct_id(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN])
        loader = AcademyLoader()
        patterns = loader.load_patterns(path)
        assert patterns[0].id == "repository"

    def test_loads_multiple_patterns(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN, VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL])
        loader = AcademyLoader()
        patterns = loader.load_patterns(path)
        assert len(patterns) == 3

    def test_raises_on_missing_patterns_file(self, tmp_path):
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json_in_patterns_file(self, tmp_path):
        path = tmp_path / "patterns.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        del pattern["related_principles"]
        del pattern["examples"]
        del pattern["references"]
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        patterns = loader.load_patterns(path)
        assert patterns[0].related_principles == []
        assert patterns[0].examples == []
        assert patterns[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        pattern["future_field"] = "sprint 007 value"
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        patterns = loader.load_patterns(path)
        assert patterns[0].extra.get("future_field") == "sprint 007 value"

    def test_real_patterns_file_loads(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        assert len(patterns) > 0

    def test_real_patterns_file_has_expected_count(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        assert len(patterns) == 9

    def test_principles_and_patterns_load_independently(self):
        if not REAL_PRINCIPLES_PATH.exists() or not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real data files not present.")
        loader = AcademyLoader()
        principles = loader.load(REAL_PRINCIPLES_PATH)
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        assert len(principles) == 21
        assert len(patterns) == 9


# ===========================================================================
# 2. PATTERN SCHEMA VALIDATION
# ===========================================================================

class TestPatternSchemaValidation:

    def test_raises_when_top_level_not_object(self, tmp_path):
        path = tmp_path / "patterns.json"
        path.write_text(json.dumps([VALID_PATTERN]), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "top level" in str(exc_info.value).lower()

    def test_raises_when_patterns_key_missing(self, tmp_path):
        path = tmp_path / "patterns.json"
        path.write_text(json.dumps({"data": []}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "patterns" in str(exc_info.value)

    def test_raises_when_patterns_is_not_list(self, tmp_path):
        path = tmp_path / "patterns.json"
        path.write_text(json.dumps({"patterns": {}}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "array" in str(exc_info.value).lower()

    def test_raises_when_pattern_is_not_object(self, tmp_path):
        path = make_patterns_file(tmp_path, ["not a dict"])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError):
            loader.load_patterns(path)

    def test_when_to_use_must_be_list(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        pattern["when_to_use"] = "not a list"
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_patterns(path)
        assert "when_to_use" in str(exc_info.value)

    def test_advantages_must_be_list(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        pattern["advantages"] = "not a list"
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_patterns(path)
        assert "advantages" in str(exc_info.value)

    def test_empty_intent_raises(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        pattern["intent"] = "  "
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_patterns(path)

    def test_all_real_patterns_have_required_fields(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        from core.engineering.academy.models import REQUIRED_PATTERN_FIELDS
        for p in patterns:
            for field in REQUIRED_PATTERN_FIELDS:
                assert hasattr(p, field), f"Pattern '{p.id}' missing field '{field}'"


# ===========================================================================
# 3. PATTERN MISSING REQUIRED FIELDS
# ===========================================================================

class TestPatternMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "intent", "problem", "solution",
        "when_to_use", "when_not_to_use", "advantages", "disadvantages", "tags"
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        pattern = dict(VALID_PATTERN)
        del pattern[missing_field]
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_patterns(path)
        assert missing_field in str(exc_info.value)

    def test_error_contains_pattern_id(self, tmp_path):
        pattern = dict(VALID_PATTERN)
        del pattern["solution"]
        path = make_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_patterns(path)
        assert "repository" in str(exc_info.value)


# ===========================================================================
# 4. PATTERN DUPLICATE ID DETECTION
# ===========================================================================

class TestPatternDuplicateIdDetection:

    def test_raises_on_duplicate_pattern_ids(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN, VALID_PATTERN])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_duplicate_error_contains_id(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN, VALID_PATTERN])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_patterns(path)
        assert "repository" in str(exc_info.value)

    def test_no_duplicate_ids_in_real_patterns(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        ids = [p.id for p in patterns]
        assert len(ids) == len(set(ids))

    def test_principle_and_pattern_ids_are_independent(self):
        """Principle and pattern IDs may overlap — they are separate namespaces."""
        if not REAL_PRINCIPLES_PATH.exists() or not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real data files not present.")
        loader = AcademyLoader()
        principles = loader.load(REAL_PRINCIPLES_PATH)
        patterns = loader.load_patterns(REAL_PATTERNS_PATH)
        # Just confirm both loaded without error — overlapping IDs are allowed
        assert len(principles) > 0
        assert len(patterns) > 0


# ===========================================================================
# 5. PATTERN REPOSITORY QUERIES
# ===========================================================================

class TestPatternRepositoryQueries:

    def test_get_by_id_returns_correct_pattern(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        result = repo.get_by_id("repository")
        assert result is not None
        assert result.id == "repository"
        assert result.name == "Repository"

    def test_get_by_id_returns_none_for_unknown(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        assert repo.get_by_id("nonexistent") is None

    def test_list_all_returns_all_patterns(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL])
        assert len(repo.list_all()) == 3

    def test_list_all_empty_repo(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [])
        assert repo.list_all() == []

    def test_list_all_returns_design_pattern_instances(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        for p in repo.list_all():
            assert isinstance(p, DesignPattern)

    def test_repo_is_subclass_of_pattern_repository(self, tmp_path):
        path = make_patterns_file(tmp_path, [VALID_PATTERN])
        repo = JsonPatternRepository(path)
        assert isinstance(repo, PatternRepository)

    def test_real_patterns_all_retrievable_by_id(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        for p in repo.list_all():
            result = repo.get_by_id(p.id)
            assert result is not None
            assert result.id == p.id


# ===========================================================================
# 6. PATTERN CATEGORY FILTERING
# ===========================================================================

class TestPatternCategoryFiltering:

    def test_filter_by_category_architectural(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL])
        results = repo.filter_by_category("architectural")
        assert len(results) == 1
        assert results[0].id == "repository"

    def test_filter_by_category_creational(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        results = repo.filter_by_category("creational")
        assert len(results) == 1
        assert results[0].id == "factory"

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        results = repo.filter_by_category("ARCHITECTURAL")
        assert len(results) == 1

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        results = repo.filter_by_category("unknown-category")
        assert results == []

    def test_real_patterns_behavioural_category(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        results = repo.filter_by_category("behavioural")
        ids = [p.id for p in results]
        assert "strategy" in ids
        assert "observer" in ids
        assert "command" in ids

    def test_real_patterns_structural_category(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        results = repo.filter_by_category("structural")
        ids = [p.id for p in results]
        assert "adapter" in ids
        assert "facade" in ids

    def test_real_patterns_architectural_category(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        results = repo.filter_by_category("architectural")
        ids = [p.id for p in results]
        assert "repository" in ids
        assert "dependency-injection" in ids


# ===========================================================================
# 7. PATTERN TAG FILTERING
# ===========================================================================

class TestPatternTagFiltering:

    def test_filter_by_tag_returns_matching_patterns(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        results = repo.filter_by_tag("decoupling")
        ids = [p.id for p in results]
        assert "repository" in ids
        assert "factory" in ids

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        results = repo.filter_by_tag("ARCHITECTURAL")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown_tag(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        results = repo.filter_by_tag("nonexistent-tag")
        assert results == []

    def test_real_patterns_testability_tag(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        results = repo.filter_by_tag("testability")
        assert len(results) > 0

    def test_real_patterns_decoupling_tag(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        results = repo.filter_by_tag("decoupling")
        assert len(results) > 0


# ===========================================================================
# 8. PATTERN DETERMINISTIC SEARCH
# ===========================================================================

class TestPatternDeterministicSearch:

    def test_search_finds_by_name(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        results = service.search("Repository")
        assert any(p.id == "repository" for p in results)

    def test_search_finds_by_intent(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        results = service.search("Centralise object creation")
        assert len(results) == 1
        assert results[0].id == "factory"

    def test_search_finds_by_tag(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN, VALID_PATTERN_BEHAVIOURAL])
        results = service.search("algorithm")
        assert any(p.id == "strategy" for p in results)

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        results = service.search("ENCAPSULATE")
        assert len(results) == 1

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        assert service.search("") == []

    def test_search_whitespace_query_returns_empty(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        assert service.search("   ") == []

    def test_search_no_match_returns_empty(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        assert service.search("zzznomatch") == []

    def test_search_results_sorted_by_id(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN_2, VALID_PATTERN])
        results = service.search("decoupl")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN, VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL])
        r1 = [p.id for p in service.search("a")]
        r2 = [p.id for p in service.search("a")]
        assert r1 == r2

    def test_search_finds_in_when_to_use(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        results = service.search("swap storage backends")
        assert len(results) == 1

    def test_search_finds_in_advantages(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        results = service.search("persistence")
        assert len(results) == 1

    def test_real_patterns_search_for_injection(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        service = PatternService(repo)
        results = service.search("injection")
        assert any(p.id == "dependency-injection" for p in results)

    def test_real_patterns_search_for_queue(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        service = PatternService(repo)
        results = service.search("queue")
        assert len(results) > 0


# ===========================================================================
# 9. PATTERN READ-ONLY BEHAVIOUR
# ===========================================================================

class TestPatternReadOnlyBehaviour:

    def test_pattern_is_frozen(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        p = repo.get_by_id("repository")
        assert p is not None
        with pytest.raises((AttributeError, TypeError)):
            p.name = "Modified"  # type: ignore

    def test_pattern_id_cannot_be_changed(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN])
        p = repo.get_by_id("repository")
        with pytest.raises((AttributeError, TypeError)):
            p.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2])
        results = repo.list_all()
        results.clear()
        assert len(repo.list_all()) == 2


# ===========================================================================
# 10. PATTERN EXCEPTION HANDLING
# ===========================================================================

class TestPatternExceptionHandling:

    def test_get_pattern_raises_for_unknown_id(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_pattern("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_get_pattern_error_has_principle_id_attribute(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_pattern("missing")
        assert exc_info.value.principle_id == "missing"


# ===========================================================================
# 11. PATTERN EMPTY RESULT HANDLING
# ===========================================================================

class TestPatternEmptyResultHandling:

    def test_filter_by_category_empty_repo(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [])
        assert repo.filter_by_category("architectural") == []

    def test_filter_by_tag_empty_repo(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [])
        assert repo.filter_by_tag("decoupling") == []

    def test_search_empty_repo(self, tmp_path):
        service = make_pattern_service(tmp_path, [])
        assert service.search("repository") == []

    def test_list_patterns_empty_repo(self, tmp_path):
        service = make_pattern_service(tmp_path, [])
        assert service.list_patterns() == []


# ===========================================================================
# 12. PATTERN STABLE ORDERING
# ===========================================================================

class TestPatternStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL, VALID_PATTERN])
        ids = [p.id for p in repo.list_all()]
        assert ids == sorted(ids)

    def test_list_patterns_service_sorted_by_id(self, tmp_path):
        service = make_pattern_service(tmp_path, [VALID_PATTERN_2, VALID_PATTERN])
        ids = [p.id for p in service.list_patterns()]
        assert ids == sorted(ids)

    def test_filter_category_results_sorted(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN_2, VALID_PATTERN])
        results = repo.filter_by_category("architectural")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_real_patterns_list_all_sorted(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        ids = [p.id for p in repo.list_all()]
        assert ids == sorted(ids)

    def test_list_all_order_stable_across_calls(self, tmp_path):
        repo = make_pattern_repo(tmp_path, [VALID_PATTERN, VALID_PATTERN_2, VALID_PATTERN_BEHAVIOURAL])
        first = [p.id for p in repo.list_all()]
        second = [p.id for p in repo.list_all()]
        assert first == second


# ===========================================================================
# 13. REAL DATA — end-to-end pattern validation
# ===========================================================================

class TestRealPatternDataEndToEnd:

    def test_service_get_repository_pattern(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        service = PatternService(repo)
        p = service.get_pattern("repository")
        assert p.name == "Repository"
        assert p.category == "architectural"

    def test_service_get_dependency_injection_pattern(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        service = PatternService(repo)
        p = service.get_pattern("dependency-injection")
        assert "Dependency Injection" in p.name

    def test_all_nine_patterns_present(self):
        if not REAL_PATTERNS_PATH.exists():
            pytest.skip("Real patterns.json not present.")
        repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        service = PatternService(repo)
        expected = {
            "repository", "factory", "strategy", "adapter",
            "facade", "builder", "observer", "command", "dependency-injection"
        }
        actual = {p.id for p in service.list_patterns()}
        assert expected == actual

    def test_related_principles_reference_real_principle_ids(self):
        if not REAL_PATTERNS_PATH.exists() or not REAL_PRINCIPLES_PATH.exists():
            pytest.skip("Real data files not present.")
        principle_repo = JsonAcademyRepository(REAL_PRINCIPLES_PATH)
        pattern_repo = JsonPatternRepository(REAL_PATTERNS_PATH)
        valid_principle_ids = {p.id for p in principle_repo.list_all()}
        for pattern in pattern_repo.list_all():
            for ref_id in pattern.related_principles:
                assert ref_id in valid_principle_ids, (
                    f"Pattern '{pattern.id}' references unknown principle '{ref_id}'"
                )

    def test_sprint_001_principles_still_intact(self):
        """Regression: Sprint 001 must remain unaffected."""
        if not REAL_PRINCIPLES_PATH.exists():
            pytest.skip("Real principles.json not present.")
        repo = JsonAcademyRepository(REAL_PRINCIPLES_PATH)
        service = AcademyService(repo)
        assert len(service.list_principles()) == 21
        p = service.get_principle("dry")
        assert p.name == "Don't Repeat Yourself"
