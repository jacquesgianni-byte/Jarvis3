"""
Genesis-019 Sprint 004 — Engineering Academy Architecture Patterns
Deterministic unit tests. Completely self-contained.

Coverage:
  - Architecture pattern JSON loading
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
from core.engineering.academy.json_repository import JsonArchitecturePatternRepository
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import (
    ArchitecturePattern,
    REQUIRED_ARCHITECTURE_PATTERN_FIELDS,
)
from core.engineering.academy.repository import ArchitecturePatternRepository
from core.engineering.academy.service import ArchitecturePatternService

# ---------------------------------------------------------------------------
# Real data path
# ---------------------------------------------------------------------------

REAL_DATA_PATH = REPO_ROOT / "data" / "engineering" / "architecture_patterns.json"

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

VALID_ARCH_PATTERN = {
    "id": "layered-architecture",
    "name": "Layered Architecture",
    "category": "structural",
    "description": "Organises a system into horizontal layers where each layer has a specific responsibility.",
    "intent": "Separate concerns across horizontal layers so each can evolve independently.",
    "structure": "Layers are stacked vertically. Each layer exposes an interface to the layer above it.",
    "components": [
        "Presentation Layer — handles user interface",
        "Business Logic Layer — owns domain rules",
        "Data Access Layer — abstracts persistence",
    ],
    "advantages": ["Clear separation of concerns", "Layers can be tested independently"],
    "disadvantages": ["Can degenerate into a God Object at each layer"],
    "when_to_use": ["Enterprise applications with clear domain boundaries"],
    "when_not_to_use": ["When performance is critical and layering adds unacceptable latency"],
    "related_principles": ["solid-srp", "separation-of-concerns"],
    "related_patterns": ["repository", "facade"],
    "related_anti_patterns": ["god-object", "tight-coupling"],
    "examples": ["Jarvis OS: desktop UI calls JarvisCore which calls Skills — a three-layer structure"],
    "references": ["Martin Fowler — Patterns of Enterprise Application Architecture"],
    "tags": ["layered", "structural", "tiers", "separation-of-concerns"],
}

VALID_ARCH_PATTERN_2 = {
    "id": "clean-architecture",
    "name": "Clean Architecture",
    "category": "structural",
    "description": "Organises a system around the business domain, placing entities and use cases at the centre.",
    "intent": "Make business rules the most stable part of the system.",
    "structure": "Four concentric rings with dependencies pointing inward.",
    "components": [
        "Entities — pure business objects",
        "Use Cases — application business rules",
        "Interface Adapters — controllers and presenters",
        "Frameworks and Drivers — databases and UI",
    ],
    "advantages": ["Business rules testable without infrastructure", "Infrastructure is swappable"],
    "disadvantages": ["Higher upfront complexity than layered architecture"],
    "when_to_use": ["Complex domains with rich business rules"],
    "when_not_to_use": ["Simple CRUD applications"],
    "tags": ["clean-architecture", "structural", "domain", "dependency-rule"],
}

VALID_ARCH_PATTERN_3 = {
    "id": "pipeline-architecture",
    "name": "Pipeline Architecture",
    "category": "data-flow",
    "description": "Structures processing as a sequence of independent stages.",
    "intent": "Make complex data processing clear and composable.",
    "structure": "Source produces data; stages transform it; sink consumes it.",
    "components": ["Source", "Filters", "Pipes", "Sink"],
    "advantages": ["Each stage is independently testable", "Stages can be reordered"],
    "disadvantages": ["All data must pass through every stage"],
    "when_to_use": ["Data transformation and ETL systems"],
    "when_not_to_use": ["Complex branching that cannot be expressed linearly"],
    "tags": ["pipeline", "data-flow", "stages", "composable"],
}


def make_arch_patterns_file(tmp_path: Path, patterns: list) -> Path:
    data = {"architecture_patterns": patterns}
    path = tmp_path / "architecture_patterns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_arch_pattern_repo(tmp_path: Path, patterns: list) -> JsonArchitecturePatternRepository:
    path = make_arch_patterns_file(tmp_path, patterns)
    return JsonArchitecturePatternRepository(path)


def make_arch_pattern_service(tmp_path: Path, patterns: list) -> ArchitecturePatternService:
    repo = make_arch_pattern_repo(tmp_path, patterns)
    return ArchitecturePatternService(repo)


# ===========================================================================
# 1. ARCHITECTURE PATTERN LOADING
# ===========================================================================

class TestArchitecturePatternLoading:

    def test_loads_valid_file_successfully(self, tmp_path):
        path = make_arch_patterns_file(tmp_path, [VALID_ARCH_PATTERN])
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(path)
        assert len(patterns) == 1

    def test_loaded_pattern_has_correct_id(self, tmp_path):
        path = make_arch_patterns_file(tmp_path, [VALID_ARCH_PATTERN])
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(path)
        assert patterns[0].id == "layered-architecture"

    def test_loads_multiple_patterns(self, tmp_path):
        path = make_arch_patterns_file(
            tmp_path,
            [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN_3]
        )
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(path)
        assert len(patterns) == 3

    def test_raises_on_missing_file(self, tmp_path):
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_architecture_patterns(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "architecture_patterns.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        pattern = {
            "id": "microservices",
            "name": "Microservices",
            "category": "distributed",
            "description": "Independent deployable services.",
            "intent": "Enable independent deployment.",
            "structure": "Each service runs in its own process.",
            "components": ["Individual Services", "API Gateway"],
            "advantages": ["Independent deployment"],
            "disadvantages": ["Distributed systems complexity"],
            "when_to_use": ["Large systems with distinct capabilities"],
            "when_not_to_use": ["Small teams"],
            "tags": ["microservices"],
            # related_principles, related_patterns, related_anti_patterns,
            # examples, references omitted
        }
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        result = loader.load_architecture_patterns(path)
        assert result[0].related_principles == []
        assert result[0].related_patterns == []
        assert result[0].related_anti_patterns == []
        assert result[0].examples == []
        assert result[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["future_field"] = "some value"
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        result = loader.load_architecture_patterns(path)
        assert result[0].extra.get("future_field") == "some value"

    def test_real_architecture_patterns_file_loads(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(REAL_DATA_PATH)
        assert len(patterns) > 0

    def test_real_architecture_patterns_file_has_expected_count(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(REAL_DATA_PATH)
        assert len(patterns) == 12


# ===========================================================================
# 2. SCHEMA VALIDATION
# ===========================================================================

class TestArchitecturePatternSchemaValidation:

    def test_raises_when_top_level_key_missing(self, tmp_path):
        path = tmp_path / "architecture_patterns.json"
        path.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "architecture_patterns" in str(exc_info.value)

    def test_raises_when_pattern_is_not_object(self, tmp_path):
        path = make_arch_patterns_file(tmp_path, ["not a dict"])
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError):
            loader.load_architecture_patterns(path)

    def test_components_field_must_be_list(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["components"] = "not a list"
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "components" in str(exc_info.value)

    def test_advantages_field_must_be_list(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["advantages"] = "not a list"
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "advantages" in str(exc_info.value)

    def test_tags_field_must_be_list(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["tags"] = "not a list"
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "tags" in str(exc_info.value)

    def test_empty_description_raises(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["description"] = "   "
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_architecture_patterns(path)

    def test_empty_intent_raises(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["intent"] = ""
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_architecture_patterns(path)

    def test_empty_structure_raises(self, tmp_path):
        pattern = dict(VALID_ARCH_PATTERN)
        pattern["structure"] = ""
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError):
            loader.load_architecture_patterns(path)

    def test_all_required_fields_present_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(REAL_DATA_PATH)
        for p in patterns:
            for f in REQUIRED_ARCHITECTURE_PATTERN_FIELDS:
                assert hasattr(p, f), f"ArchitecturePattern '{p.id}' missing field '{f}'"


# ===========================================================================
# 3. MISSING REQUIRED FIELDS
# ===========================================================================

class TestArchitecturePatternMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "description", "intent", "structure",
        "components", "advantages", "disadvantages",
        "when_to_use", "when_not_to_use", "tags",
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        pattern = dict(VALID_ARCH_PATTERN)
        del pattern[missing_field]
        path = make_arch_patterns_file(tmp_path, [pattern])
        loader = AcademyLoader()
        with pytest.raises(InvalidPrincipleError) as exc_info:
            loader.load_architecture_patterns(path)
        assert missing_field in str(exc_info.value)


# ===========================================================================
# 4. DUPLICATE DETECTION
# ===========================================================================

class TestArchitecturePatternDuplicateDetection:

    def test_raises_on_duplicate_ids(self, tmp_path):
        path = make_arch_patterns_file(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN]
        )
        loader = AcademyLoader()
        with pytest.raises(AcademySchemaError) as exc_info:
            loader.load_architecture_patterns(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_no_duplicate_ids_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        loader = AcademyLoader()
        patterns = loader.load_architecture_patterns(REAL_DATA_PATH)
        ids = [p.id for p in patterns]
        assert len(ids) == len(set(ids)), "Duplicate IDs in architecture_patterns.json"


# ===========================================================================
# 5. REPOSITORY QUERIES
# ===========================================================================

class TestArchitecturePatternRepositoryQueries:

    def test_get_by_id_returns_correct_pattern(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        result = repo.get_by_id("layered-architecture")
        assert result is not None
        assert result.id == "layered-architecture"
        assert result.name == "Layered Architecture"

    def test_get_by_id_returns_none_for_unknown(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        assert repo.get_by_id("nonexistent") is None

    def test_list_all_returns_all_patterns(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path,
            [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN_3]
        )
        assert len(repo.list_all()) == 3

    def test_list_all_on_empty_data(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [])
        assert repo.list_all() == []

    def test_all_results_are_architecture_pattern_instances(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        for p in repo.list_all():
            assert isinstance(p, ArchitecturePattern)

    def test_repo_is_subclass_of_architecture_pattern_repository(self, tmp_path):
        path = make_arch_patterns_file(tmp_path, [VALID_ARCH_PATTERN])
        repo = JsonArchitecturePatternRepository(path)
        assert isinstance(repo, ArchitecturePatternRepository)

    def test_real_data_all_patterns_retrievable(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        for p in repo.list_all():
            retrieved = service.get_architecture_pattern(p.id)
            assert retrieved.id == p.id


# ===========================================================================
# 6. CATEGORY FILTERING
# ===========================================================================

class TestArchitecturePatternCategoryFiltering:

    def test_filter_by_category_returns_matching(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path,
            [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN_3]
        )
        results = repo.filter_by_category("structural")
        assert len(results) == 2
        ids = {p.id for p in results}
        assert "layered-architecture" in ids
        assert "clean-architecture" in ids

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        results = repo.filter_by_category("STRUCTURAL")
        assert len(results) == 1

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        assert repo.filter_by_category("unknown-category") == []

    def test_filter_by_category_data_flow(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_3]
        )
        results = repo.filter_by_category("data-flow")
        assert len(results) == 1
        assert results[0].id == "pipeline-architecture"

    def test_real_data_structural_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("structural")
        assert len(results) >= 3
        ids = {p.id for p in results}
        assert "layered-architecture" in ids
        assert "clean-architecture" in ids
        assert "modular-monolith" in ids

    def test_real_data_distributed_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("distributed")
        assert len(results) == 3
        ids = {p.id for p in results}
        assert "microservices" in ids
        assert "event-driven-architecture" in ids
        assert "client-server" in ids

    def test_real_data_presentation_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("presentation")
        assert len(results) == 2
        ids = {p.id for p in results}
        assert "mvc" in ids
        assert "mvvm" in ids

    def test_real_data_data_flow_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("data-flow")
        assert len(results) == 1
        assert results[0].id == "pipeline-architecture"

    def test_real_data_extensibility_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("extensibility")
        assert len(results) == 1
        assert results[0].id == "plugin-architecture"


# ===========================================================================
# 7. TAG FILTERING
# ===========================================================================

class TestArchitecturePatternTagFiltering:

    def test_filter_by_tag_returns_matching(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_3]
        )
        results = repo.filter_by_tag("data-flow")
        assert len(results) == 1
        assert results[0].id == "pipeline-architecture"

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        results = repo.filter_by_tag("STRUCTURAL")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        assert repo.filter_by_tag("nonexistent-tag") == []

    def test_real_data_testability_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("testability")
        assert len(results) > 0

    def test_real_data_decoupling_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("decoupling")
        assert len(results) > 0


# ===========================================================================
# 8. RELATIONSHIP VALIDATION
# ===========================================================================

class TestArchitecturePatternRelationshipValidation:

    def test_related_principles_is_a_list(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        p = repo.get_by_id("layered-architecture")
        assert isinstance(p.related_principles, list)

    def test_related_patterns_is_a_list(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        p = repo.get_by_id("layered-architecture")
        assert isinstance(p.related_patterns, list)

    def test_related_anti_patterns_is_a_list(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        p = repo.get_by_id("layered-architecture")
        assert isinstance(p.related_anti_patterns, list)

    def test_real_data_related_principles_are_strings(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        for p in repo.list_all():
            for rp in p.related_principles:
                assert isinstance(rp, str) and rp.strip(), \
                    f"ArchitecturePattern '{p.id}' has empty related_principle"

    def test_real_data_related_anti_patterns_are_strings(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        for p in repo.list_all():
            for rap in p.related_anti_patterns:
                assert isinstance(rap, str) and rap.strip(), \
                    f"ArchitecturePattern '{p.id}' has empty related_anti_pattern"

    def test_layered_architecture_references_god_object_anti_pattern(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        p = repo.get_by_id("layered-architecture")
        assert "god-object" in p.related_anti_patterns

    def test_plugin_architecture_references_solid_ocp(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        p = repo.get_by_id("plugin-architecture")
        assert "solid-ocp" in p.related_principles

    def test_pipeline_architecture_references_solid_srp(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        p = repo.get_by_id("pipeline-architecture")
        assert "solid-srp" in p.related_principles


# ===========================================================================
# 9. DETERMINISTIC SEARCH
# ===========================================================================

class TestArchitecturePatternDeterministicSearch:

    def test_search_finds_by_name_substring(self, tmp_path):
        service = make_arch_pattern_service(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        results = service.search("Layered")
        assert any(p.id == "layered-architecture" for p in results)

    def test_search_finds_by_description_substring(self, tmp_path):
        service = make_arch_pattern_service(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_3]
        )
        results = service.search("sequence of independent stages")
        assert any(p.id == "pipeline-architecture" for p in results)

    def test_search_finds_by_intent(self, tmp_path):
        service = make_arch_pattern_service(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        results = service.search("stable part")
        assert any(p.id == "clean-architecture" for p in results)

    def test_search_finds_by_tag(self, tmp_path):
        service = make_arch_pattern_service(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_3]
        )
        results = service.search("composable")
        assert len(results) == 1
        assert results[0].id == "pipeline-architecture"

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        results = service.search("LAYERED")
        assert len(results) == 1

    def test_search_returns_empty_for_no_match(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        assert service.search("zzznomatch") == []

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        assert service.search("") == []

    def test_search_whitespace_only_returns_empty(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        assert service.search("   ") == []

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_arch_pattern_service(
            tmp_path,
            [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN_3]
        )
        first = [p.id for p in service.search("a")]
        second = [p.id for p in service.search("a")]
        assert first == second

    def test_search_finds_in_components(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        results = service.search("Presentation Layer")
        assert len(results) == 1

    def test_search_finds_in_when_to_use(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        results = service.search("Enterprise applications")
        assert len(results) == 1

    def test_real_data_search_for_dependency(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        results = service.search("dependency")
        assert len(results) > 0

    def test_real_data_search_for_testing(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        results = service.search("testable")
        assert len(results) > 0


# ===========================================================================
# 10. READ-ONLY BEHAVIOUR
# ===========================================================================

class TestArchitecturePatternReadOnlyBehaviour:

    def test_architecture_pattern_is_frozen(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        p = repo.get_by_id("layered-architecture")
        assert p is not None
        with pytest.raises((AttributeError, TypeError)):
            p.name = "Modified"  # type: ignore

    def test_architecture_pattern_id_cannot_be_changed(self, tmp_path):
        repo = make_arch_pattern_repo(tmp_path, [VALID_ARCH_PATTERN])
        p = repo.get_by_id("layered-architecture")
        with pytest.raises((AttributeError, TypeError)):
            p.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        results = repo.list_all()
        results.clear()
        assert len(repo.list_all()) == 2

    def test_filter_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        results = repo.filter_by_category("structural")
        results.clear()
        assert len(repo.filter_by_category("structural")) == 2


# ===========================================================================
# 11. SERVICE EXCEPTION HANDLING
# ===========================================================================

class TestArchitecturePatternServiceExceptions:

    def test_get_raises_for_unknown_id(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_architecture_pattern("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_not_found_error_has_id(self, tmp_path):
        service = make_arch_pattern_service(tmp_path, [VALID_ARCH_PATTERN])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_architecture_pattern("missing-id")
        assert exc_info.value.principle_id == "missing-id"

    def test_not_found_is_subclass_of_academy_error(self):
        exc = PrincipleNotFoundError("test-id")
        assert isinstance(exc, AcademyError)


# ===========================================================================
# 12. STABLE ORDERING
# ===========================================================================

class TestArchitecturePatternStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path,
            [VALID_ARCH_PATTERN_3, VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2]
        )
        ids = [p.id for p in repo.list_all()]
        assert ids == sorted(ids)

    def test_filter_by_category_results_are_sorted(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path, [VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN]
        )
        results = repo.filter_by_category("structural")
        ids = [p.id for p in results]
        assert ids == sorted(ids)

    def test_list_all_order_stable_across_calls(self, tmp_path):
        repo = make_arch_pattern_repo(
            tmp_path,
            [VALID_ARCH_PATTERN, VALID_ARCH_PATTERN_2, VALID_ARCH_PATTERN_3]
        )
        first = [p.id for p in repo.list_all()]
        second = [p.id for p in repo.list_all()]
        assert first == second

    def test_real_data_list_all_is_sorted(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        ids = [p.id for p in repo.list_all()]
        assert ids == sorted(ids)


# ===========================================================================
# 13. REAL DATA END-TO-END
# ===========================================================================

class TestArchitecturePatternRealDataEndToEnd:

    def test_service_get_clean_architecture_by_id(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        p = service.get_architecture_pattern("clean-architecture")
        assert p.name == "Clean Architecture"

    def test_service_get_pipeline_architecture(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        p = service.get_architecture_pattern("pipeline-architecture")
        assert "Unix" in " ".join(p.examples)

    def test_service_list_returns_all_twelve(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        assert len(service.list_architecture_patterns()) == 12

    def test_find_by_category_structural_returns_expected(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        results = service.find_by_category("structural")
        ids = {p.id for p in results}
        assert "layered-architecture" in ids
        assert "clean-architecture" in ids
        assert "hexagonal-architecture" in ids
        assert "modular-monolith" in ids
        assert "repository-centric-architecture" in ids

    def test_find_by_tag_ui_returns_mvc_and_mvvm(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        results = service.find_by_tag("ui")
        ids = {p.id for p in results}
        assert "mvc" in ids
        assert "mvvm" in ids

    def test_search_for_jarvis_returns_multiple(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        results = service.search("Jarvis")
        assert len(results) >= 3

    def test_service_raises_for_nonexistent(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        service = ArchitecturePatternService(repo)
        with pytest.raises(PrincipleNotFoundError):
            service.get_architecture_pattern("nonexistent-xyz")

    def test_every_pattern_has_non_empty_components(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        for p in repo.list_all():
            assert len(p.components) > 0, \
                f"ArchitecturePattern '{p.id}' has no components"

    def test_every_pattern_has_non_empty_when_to_use(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        for p in repo.list_all():
            assert len(p.when_to_use) > 0, \
                f"ArchitecturePattern '{p.id}' has no when_to_use"

    def test_every_pattern_has_non_empty_when_not_to_use(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        for p in repo.list_all():
            assert len(p.when_not_to_use) > 0, \
                f"ArchitecturePattern '{p.id}' has no when_not_to_use"

    def test_plugin_architecture_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        p = repo.get_by_id("plugin-architecture")
        assert p is not None
        assert "VS Code" in " ".join(p.examples)

    def test_mvc_references_jarvis_desktop(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real architecture_patterns.json not present.")
        repo = JsonArchitecturePatternRepository(REAL_DATA_PATH)
        p = repo.get_by_id("mvc")
        assert any("Jarvis" in ex for ex in p.examples)