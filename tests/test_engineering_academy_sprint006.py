"""
Genesis-019 Sprint 006 — Engineering Academy Decision Intelligence
Deterministic unit tests. Completely self-contained.

Coverage:
  - Engineering decision JSON loading
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
  - Regression safety

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
from core.engineering.academy.json_repository import JsonEngineeringDecisionRepository
from core.engineering.academy.loader import AcademyLoader
from core.engineering.academy.models import (
    EngineeringDecision,
    REQUIRED_ENGINEERING_DECISION_FIELDS,
)
from core.engineering.academy.repository import EngineeringDecisionRepository
from core.engineering.academy.service import EngineeringDecisionService

# ---------------------------------------------------------------------------
# Real data path
# ---------------------------------------------------------------------------

REAL_DATA_PATH = REPO_ROOT / "data" / "engineering" / "engineering_decisions.json"

# ---------------------------------------------------------------------------
# Test fixtures — minimal valid records
# ---------------------------------------------------------------------------

VALID_DECISION = {
    "id": "refactor-vs-rewrite",
    "name": "Refactor vs Rewrite",
    "category": "codebase",
    "situation": "An existing module is difficult to maintain.",
    "indicators": [
        "The existing code produces frequent bugs despite ongoing fixes",
        "Adding features requires touching many unrelated files",
    ],
    "recommended_action": "Default to refactoring. Rewrite only when architecture is fundamentally wrong.",
    "trade_offs": [
        "Refactor: slower but lower risk",
        "Rewrite: faster initially but high risk",
    ],
    "risks": ["Rewrites take three times longer than estimated"],
    "benefits": ["Refactoring provides continuous improvement"],
    "decision_questions": ["Can the existing code be made testable without a rewrite?"],
    "related_principles": ["jarvis-evidence-before-assumption"],
    "related_patterns": ["adapter", "facade"],
    "related_anti_patterns": ["dead-code", "spaghetti-code"],
    "related_architecture_patterns": ["modular-monolith"],
    "related_best_practices": ["refactoring-safely", "testing-first"],
    "jarvis_example": "Jarvis agent.py was restored from git rather than rewritten from memory.",
    "references": [],
    "tags": ["refactor", "rewrite", "codebase", "risk"],
}

VALID_DECISION_2 = {
    "id": "build-vs-buy",
    "name": "Build vs Buy",
    "category": "architecture",
    "situation": "A capability could be built in-house or purchased externally.",
    "indicators": ["The external library does exactly what is needed"],
    "recommended_action": "Buy for commodity capabilities. Build for core differentiators.",
    "trade_offs": [
        "Buy: faster delivery but dependency risk",
        "Build: full control but expensive",
    ],
    "risks": ["Bought solutions may not cover edge cases"],
    "benefits": ["Buying accelerates delivery of non-core capabilities"],
    "decision_questions": ["Is this capability part of our core domain?"],
    "jarvis_example": "Jarvis uses Whisper open source for voice transcription.",
    "tags": ["build-vs-buy", "architecture", "vendor", "control"],
}

VALID_DECISION_3 = {
    "id": "risk-vs-reward",
    "name": "Risk vs Reward",
    "category": "process",
    "situation": "An engineering decision involves risk in exchange for reward.",
    "indicators": ["The change touches a critical path"],
    "recommended_action": "Quantify both risk and reward before deciding.",
    "trade_offs": [
        "Accept risk: potential reward but exposure to failure",
        "Avoid risk: safe but forgoes improvements",
    ],
    "risks": ["Underestimating risk because reward is attractive"],
    "benefits": ["Accepting well-understood risks enables improvement"],
    "decision_questions": ["What is the rollback plan if this fails?"],
    "jarvis_example": "Jarvis Genesis milestone freeze discipline is the risk management gate.",
    "tags": ["risk", "reward", "process", "decision"],
}


def make_decisions_file(tmp_path: Path, decisions: list) -> Path:
    data = {"engineering_decisions": decisions}
    path = tmp_path / "engineering_decisions.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def make_decision_repo(tmp_path: Path, decisions: list) -> JsonEngineeringDecisionRepository:
    path = make_decisions_file(tmp_path, decisions)
    return JsonEngineeringDecisionRepository(path)


def make_decision_service(tmp_path: Path, decisions: list) -> EngineeringDecisionService:
    repo = make_decision_repo(tmp_path, decisions)
    return EngineeringDecisionService(repo)


# ===========================================================================
# 1. LOADING
# ===========================================================================

class TestEngineeringDecisionLoading:

    def test_loads_valid_file_successfully(self, tmp_path):
        path = make_decisions_file(tmp_path, [VALID_DECISION])
        decisions = AcademyLoader().load_engineering_decisions(path)
        assert len(decisions) == 1

    def test_loaded_decision_has_correct_id(self, tmp_path):
        path = make_decisions_file(tmp_path, [VALID_DECISION])
        decisions = AcademyLoader().load_engineering_decisions(path)
        assert decisions[0].id == "refactor-vs-rewrite"

    def test_loads_multiple_decisions(self, tmp_path):
        path = make_decisions_file(tmp_path, [VALID_DECISION, VALID_DECISION_2, VALID_DECISION_3])
        decisions = AcademyLoader().load_engineering_decisions(path)
        assert len(decisions) == 3

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_engineering_decisions(tmp_path / "nonexistent.json")
        assert "not found" in str(exc_info.value).lower()

    def test_raises_on_invalid_json(self, tmp_path):
        path = tmp_path / "engineering_decisions.json"
        path.write_text("{ invalid json !!!", encoding="utf-8")
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "invalid json" in str(exc_info.value).lower()

    def test_loads_optional_fields_with_defaults(self, tmp_path):
        decision = {
            "id": "yagni-decision",
            "name": "YAGNI Decision",
            "category": "design",
            "situation": "An engineer is about to add a feature not yet required.",
            "indicators": ["The feature is not in the current sprint"],
            "recommended_action": "Do not build it.",
            "trade_offs": ["Build now vs defer"],
            "risks": ["Speculative code becomes dead code"],
            "benefits": ["Keeps current design simple"],
            "decision_questions": ["Is this requirement confirmed?"],
            "jarvis_example": "Jarvis Genesis-016 deferred AST parsing.",
            "tags": ["yagni", "design"],
            # related_* and references omitted
        }
        path = make_decisions_file(tmp_path, [decision])
        result = AcademyLoader().load_engineering_decisions(path)
        assert result[0].related_principles == []
        assert result[0].related_patterns == []
        assert result[0].related_anti_patterns == []
        assert result[0].related_architecture_patterns == []
        assert result[0].related_best_practices == []
        assert result[0].references == []

    def test_loads_extra_unknown_fields_into_extra(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["future_field"] = "some value"
        path = make_decisions_file(tmp_path, [decision])
        result = AcademyLoader().load_engineering_decisions(path)
        assert result[0].extra.get("future_field") == "some value"

    def test_real_decisions_file_loads(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        decisions = AcademyLoader().load_engineering_decisions(REAL_DATA_PATH)
        assert len(decisions) > 0

    def test_real_decisions_file_has_expected_count(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        decisions = AcademyLoader().load_engineering_decisions(REAL_DATA_PATH)
        assert len(decisions) == 20


# ===========================================================================
# 2. SCHEMA VALIDATION
# ===========================================================================

class TestEngineeringDecisionSchemaValidation:

    def test_raises_when_top_level_key_missing(self, tmp_path):
        path = tmp_path / "engineering_decisions.json"
        path.write_text(json.dumps({"wrong_key": []}), encoding="utf-8")
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "engineering_decisions" in str(exc_info.value)

    def test_raises_when_decision_is_not_object(self, tmp_path):
        path = make_decisions_file(tmp_path, ["not a dict"])
        with pytest.raises(AcademySchemaError):
            AcademyLoader().load_engineering_decisions(path)

    def test_indicators_must_be_list(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["indicators"] = "not a list"
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "indicators" in str(exc_info.value)

    def test_trade_offs_must_be_list(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["trade_offs"] = "not a list"
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "trade_offs" in str(exc_info.value)

    def test_risks_must_be_list(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["risks"] = "not a list"
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "risks" in str(exc_info.value)

    def test_benefits_must_be_list(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["benefits"] = "not a list"
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "benefits" in str(exc_info.value)

    def test_tags_must_be_list(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["tags"] = "not a list"
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "tags" in str(exc_info.value)

    def test_empty_situation_raises(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["situation"] = "   "
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError):
            AcademyLoader().load_engineering_decisions(path)

    def test_empty_recommended_action_raises(self, tmp_path):
        decision = dict(VALID_DECISION)
        decision["recommended_action"] = ""
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError):
            AcademyLoader().load_engineering_decisions(path)

    def test_all_required_fields_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        decisions = AcademyLoader().load_engineering_decisions(REAL_DATA_PATH)
        for d in decisions:
            for f in REQUIRED_ENGINEERING_DECISION_FIELDS:
                assert hasattr(d, f), f"EngineeringDecision '{d.id}' missing '{f}'"


# ===========================================================================
# 3. MISSING REQUIRED FIELDS
# ===========================================================================

class TestEngineeringDecisionMissingRequiredFields:

    @pytest.mark.parametrize("missing_field", [
        "id", "name", "category", "situation", "indicators",
        "recommended_action", "trade_offs", "risks",
        "benefits", "decision_questions", "tags",
    ])
    def test_raises_on_missing_required_field(self, tmp_path, missing_field):
        decision = dict(VALID_DECISION)
        del decision[missing_field]
        path = make_decisions_file(tmp_path, [decision])
        with pytest.raises(InvalidPrincipleError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert missing_field in str(exc_info.value)


# ===========================================================================
# 4. DUPLICATE DETECTION
# ===========================================================================

class TestEngineeringDecisionDuplicateDetection:

    def test_raises_on_duplicate_ids(self, tmp_path):
        path = make_decisions_file(tmp_path, [VALID_DECISION, VALID_DECISION])
        with pytest.raises(AcademySchemaError) as exc_info:
            AcademyLoader().load_engineering_decisions(path)
        assert "duplicate" in str(exc_info.value).lower()

    def test_no_duplicate_ids_in_real_data(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        decisions = AcademyLoader().load_engineering_decisions(REAL_DATA_PATH)
        ids = [d.id for d in decisions]
        assert len(ids) == len(set(ids))


# ===========================================================================
# 5. REPOSITORY QUERIES
# ===========================================================================

class TestEngineeringDecisionRepositoryQueries:

    def test_get_by_id_returns_correct_decision(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        result = repo.get_by_id("refactor-vs-rewrite")
        assert result is not None
        assert result.id == "refactor-vs-rewrite"
        assert result.name == "Refactor vs Rewrite"

    def test_get_by_id_returns_none_for_unknown(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        assert repo.get_by_id("nonexistent") is None

    def test_list_all_returns_all_decisions(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_2, VALID_DECISION_3])
        assert len(repo.list_all()) == 3

    def test_list_all_on_empty_data(self, tmp_path):
        repo = make_decision_repo(tmp_path, [])
        assert repo.list_all() == []

    def test_all_results_are_engineering_decision_instances(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        for d in repo.list_all():
            assert isinstance(d, EngineeringDecision)

    def test_repo_is_subclass_of_engineering_decision_repository(self, tmp_path):
        path = make_decisions_file(tmp_path, [VALID_DECISION])
        repo = JsonEngineeringDecisionRepository(path)
        assert isinstance(repo, EngineeringDecisionRepository)

    def test_real_data_all_decisions_retrievable(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        for d in repo.list_all():
            retrieved = service.get_decision(d.id)
            assert retrieved.id == d.id


# ===========================================================================
# 6. CATEGORY FILTERING
# ===========================================================================

class TestEngineeringDecisionCategoryFiltering:

    def test_filter_by_category_returns_matching(self, tmp_path):
        repo = make_decision_repo(
            tmp_path, [VALID_DECISION, VALID_DECISION_2, VALID_DECISION_3]
        )
        results = repo.filter_by_category("codebase")
        assert len(results) == 1
        assert results[0].id == "refactor-vs-rewrite"

    def test_filter_by_category_is_case_insensitive(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        results = repo.filter_by_category("CODEBASE")
        assert len(results) == 1

    def test_filter_by_category_returns_empty_for_unknown(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        assert repo.filter_by_category("unknown-category") == []

    def test_real_data_design_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("design")
        assert len(results) >= 3
        ids = {d.id for d in results}
        assert "composition-vs-inheritance" in ids
        assert "pattern-vs-simplicity" in ids
        assert "yagni-decision" in ids

    def test_real_data_architecture_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("architecture")
        assert len(results) >= 3
        ids = {d.id for d in results}
        assert "build-vs-buy" in ids
        assert "synchronous-vs-asynchronous" in ids
        assert "monolith-vs-modularisation" in ids

    def test_real_data_quality_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("quality")
        assert len(results) >= 3
        ids = {d.id for d in results}
        assert "performance-vs-readability" in ids
        assert "test-coverage-decision" in ids
        assert "maintainability-decision" in ids

    def test_real_data_codebase_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("codebase")
        assert len(results) >= 2
        ids = {d.id for d in results}
        assert "refactor-vs-rewrite" in ids
        assert "technical-debt-assessment" in ids

    def test_real_data_process_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("process")
        assert len(results) >= 2
        ids = {d.id for d in results}
        assert "feature-flags" in ids
        assert "risk-vs-reward" in ids


# ===========================================================================
# 7. TAG FILTERING
# ===========================================================================

class TestEngineeringDecisionTagFiltering:

    def test_filter_by_tag_returns_matching(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        results = repo.filter_by_tag("codebase")
        assert len(results) == 1
        assert results[0].id == "refactor-vs-rewrite"

    def test_filter_by_tag_is_case_insensitive(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        results = repo.filter_by_tag("REFACTOR")
        assert len(results) == 1

    def test_filter_by_tag_returns_empty_for_unknown(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        assert repo.filter_by_tag("nonexistent-tag") == []

    def test_real_data_risk_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("risk")
        assert len(results) > 0

    def test_real_data_trade_off_tag(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_tag("trade-off")
        assert len(results) > 0


# ===========================================================================
# 8. RELATIONSHIP VALIDATION
# ===========================================================================

class TestEngineeringDecisionRelationshipValidation:

    def test_related_principles_is_a_list(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        assert isinstance(d.related_principles, list)

    def test_related_patterns_is_a_list(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        assert isinstance(d.related_patterns, list)

    def test_related_anti_patterns_is_a_list(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        assert isinstance(d.related_anti_patterns, list)

    def test_related_best_practices_is_a_list(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        assert isinstance(d.related_best_practices, list)

    def test_real_data_related_principles_are_strings(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            for rp in d.related_principles:
                assert isinstance(rp, str) and rp.strip(), \
                    f"Decision '{d.id}' has empty related_principle"

    def test_refactor_vs_rewrite_references_evidence_principle(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        d = repo.get_by_id("refactor-vs-rewrite")
        assert "jarvis-evidence-before-assumption" in d.related_principles

    def test_build_vs_buy_references_adapter_pattern(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        d = repo.get_by_id("build-vs-buy")
        assert "adapter" in d.related_patterns

    def test_every_decision_has_jarvis_example(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            assert d.jarvis_example.strip(), \
                f"Decision '{d.id}' has empty jarvis_example"


# ===========================================================================
# 9. DETERMINISTIC SEARCH
# ===========================================================================

class TestEngineeringDecisionDeterministicSearch:

    def test_search_finds_by_name(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        results = service.search("Refactor")
        assert any(d.id == "refactor-vs-rewrite" for d in results)

    def test_search_finds_by_situation(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        results = service.search("purchased externally")
        assert any(d.id == "build-vs-buy" for d in results)

    def test_search_finds_by_recommended_action(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        results = service.search("Default to refactoring")
        assert any(d.id == "refactor-vs-rewrite" for d in results)

    def test_search_finds_by_jarvis_example(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION_3])
        results = service.search("freeze discipline")
        assert any(d.id == "risk-vs-reward" for d in results)

    def test_search_finds_by_tag(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        results = service.search("vendor")
        assert any(d.id == "build-vs-buy" for d in results)

    def test_search_finds_by_decision_question(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        results = service.search("testable without a rewrite")
        assert any(d.id == "refactor-vs-rewrite" for d in results)

    def test_search_is_case_insensitive(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        results = service.search("REWRITE")
        assert len(results) >= 1

    def test_search_returns_empty_for_no_match(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        assert service.search("zzznomatch") == []

    def test_search_empty_query_returns_empty(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        assert service.search("") == []

    def test_search_whitespace_only_returns_empty(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        assert service.search("   ") == []

    def test_search_is_deterministic_on_repeated_calls(self, tmp_path):
        service = make_decision_service(
            tmp_path, [VALID_DECISION, VALID_DECISION_2, VALID_DECISION_3]
        )
        first = [d.id for d in service.search("a")]
        second = [d.id for d in service.search("a")]
        assert first == second

    def test_real_data_search_for_jarvis(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        results = service.search("Jarvis")
        assert len(results) == 20  # every record has a jarvis_example

    def test_real_data_search_for_risk(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        results = service.search("risk")
        assert len(results) >= 5


# ===========================================================================
# 10. READ-ONLY BEHAVIOUR
# ===========================================================================

class TestEngineeringDecisionReadOnlyBehaviour:

    def test_decision_is_frozen(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        assert d is not None
        with pytest.raises((AttributeError, TypeError)):
            d.name = "Modified"  # type: ignore

    def test_decision_id_cannot_be_changed(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION])
        d = repo.get_by_id("refactor-vs-rewrite")
        with pytest.raises((AttributeError, TypeError)):
            d.id = "modified-id"  # type: ignore

    def test_list_all_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_2])
        results = repo.list_all()
        results.clear()
        assert len(repo.list_all()) == 2

    def test_filter_mutation_does_not_affect_repo(self, tmp_path):
        repo = make_decision_repo(tmp_path, [VALID_DECISION, VALID_DECISION_3])
        results = repo.filter_by_category("codebase")
        results.clear()
        assert len(repo.filter_by_category("codebase")) == 1


# ===========================================================================
# 11. SERVICE EXCEPTION HANDLING
# ===========================================================================

class TestEngineeringDecisionServiceExceptions:

    def test_get_raises_for_unknown_id(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_decision("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_not_found_error_has_id(self, tmp_path):
        service = make_decision_service(tmp_path, [VALID_DECISION])
        with pytest.raises(PrincipleNotFoundError) as exc_info:
            service.get_decision("missing-id")
        assert exc_info.value.principle_id == "missing-id"

    def test_not_found_is_subclass_of_academy_error(self):
        exc = PrincipleNotFoundError("test-id")
        assert isinstance(exc, AcademyError)


# ===========================================================================
# 12. STABLE ORDERING
# ===========================================================================

class TestEngineeringDecisionStableOrdering:

    def test_list_all_is_sorted_by_id(self, tmp_path):
        repo = make_decision_repo(
            tmp_path, [VALID_DECISION_3, VALID_DECISION, VALID_DECISION_2]
        )
        ids = [d.id for d in repo.list_all()]
        assert ids == sorted(ids)

    def test_filter_by_category_results_are_sorted(self, tmp_path):
        d_extra = dict(VALID_DECISION)
        d_extra["id"] = "short-term-vs-long-term-solution"
        d_extra["name"] = "Short-Term vs Long-Term"
        repo = make_decision_repo(tmp_path, [VALID_DECISION, d_extra])
        results = repo.filter_by_category("codebase")
        ids = [d.id for d in results]
        assert ids == sorted(ids)

    def test_list_all_order_stable_across_calls(self, tmp_path):
        repo = make_decision_repo(
            tmp_path, [VALID_DECISION, VALID_DECISION_2, VALID_DECISION_3]
        )
        first = [d.id for d in repo.list_all()]
        second = [d.id for d in repo.list_all()]
        assert first == second

    def test_real_data_list_all_is_sorted(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        ids = [d.id for d in repo.list_all()]
        assert ids == sorted(ids)


# ===========================================================================
# 13. REAL DATA END-TO-END
# ===========================================================================

class TestEngineeringDecisionRealDataEndToEnd:

    def test_service_get_refactor_vs_rewrite(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        d = service.get_decision("refactor-vs-rewrite")
        assert d.name == "Refactor vs Rewrite"

    def test_service_get_risk_vs_reward(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        d = service.get_decision("risk-vs-reward")
        assert "freeze" in d.jarvis_example.lower()

    def test_service_list_returns_all_twenty(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        assert len(service.list_decisions()) == 20

    def test_every_decision_has_non_empty_decision_questions(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            assert len(d.decision_questions) > 0, \
                f"Decision '{d.id}' has no decision_questions"

    def test_every_decision_has_non_empty_indicators(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            assert len(d.indicators) > 0, \
                f"Decision '{d.id}' has no indicators"

    def test_every_decision_has_non_empty_trade_offs(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            assert len(d.trade_offs) > 0, \
                f"Decision '{d.id}' has no trade_offs"

    def test_every_decision_has_jarvis_example(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        for d in repo.list_all():
            assert "Jarvis" in d.jarvis_example, \
                f"Decision '{d.id}' jarvis_example does not mention Jarvis"

    def test_find_by_category_design_includes_expected(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        results = service.find_by_category("design")
        ids = {d.id for d in results}
        assert "composition-vs-inheritance" in ids
        assert "abstraction-level" in ids

    def test_service_raises_for_nonexistent(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        with pytest.raises(PrincipleNotFoundError):
            service.get_decision("nonexistent-xyz")

    def test_security_vs_convenience_in_reliability_category(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        results = repo.filter_by_category("reliability")
        ids = {d.id for d in results}
        assert "security-vs-convenience" in ids

    def test_synchronous_vs_asynchronous_references_event_driven(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        d = repo.get_by_id("synchronous-vs-asynchronous")
        assert "event-driven-architecture" in d.related_architecture_patterns

    def test_search_for_evidence_returns_multiple(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        results = service.search("evidence")
        assert len(results) >= 3

    def test_find_by_tag_incremental_returns_results(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("Real engineering_decisions.json not present.")
        repo = JsonEngineeringDecisionRepository(REAL_DATA_PATH)
        service = EngineeringDecisionService(repo)
        results = service.find_by_tag("incremental")
        assert len(results) >= 1


# ===========================================================================
# 14. REGRESSION SAFETY — confirms Sprint 001–005 still intact
# ===========================================================================

class TestRegressionSafety:

    def test_existing_principles_loader_still_works(self, tmp_path):
        """Sprint 001 regression: AcademyLoader.load() still works."""
        principles_path = REPO_ROOT / "data" / "engineering" / "principles.json"
        if not principles_path.exists():
            pytest.skip("principles.json not present.")
        from core.engineering.academy.json_repository import JsonAcademyRepository
        repo = JsonAcademyRepository(principles_path)
        assert len(repo.list_all()) == 21

    def test_existing_patterns_loader_still_works(self, tmp_path):
        """Sprint 002 regression: load_patterns() still works."""
        patterns_path = REPO_ROOT / "data" / "engineering" / "patterns.json"
        if not patterns_path.exists():
            pytest.skip("patterns.json not present.")
        from core.engineering.academy.json_repository import JsonPatternRepository
        repo = JsonPatternRepository(patterns_path)
        assert len(repo.list_all()) == 9

    def test_existing_anti_patterns_loader_still_works(self, tmp_path):
        """Sprint 003 regression: load_anti_patterns() still works."""
        ap_path = REPO_ROOT / "data" / "engineering" / "anti_patterns.json"
        if not ap_path.exists():
            pytest.skip("anti_patterns.json not present.")
        from core.engineering.academy.json_repository import JsonAntiPatternRepository
        repo = JsonAntiPatternRepository(ap_path)
        assert len(repo.list_all()) == 12

    def test_existing_architecture_patterns_loader_still_works(self, tmp_path):
        """Sprint 004 regression: load_architecture_patterns() still works."""
        arch_path = REPO_ROOT / "data" / "engineering" / "architecture_patterns.json"
        if not arch_path.exists():
            pytest.skip("architecture_patterns.json not present.")
        from core.engineering.academy.json_repository import JsonArchitecturePatternRepository
        repo = JsonArchitecturePatternRepository(arch_path)
        assert len(repo.list_all()) == 12

    def test_existing_best_practices_loader_still_works(self, tmp_path):
        """Sprint 005 regression: load_best_practices() still works."""
        bp_path = REPO_ROOT / "data" / "engineering" / "best_practices.json"
        if not bp_path.exists():
            pytest.skip("best_practices.json not present.")
        from core.engineering.academy.json_repository import JsonBestPracticeRepository
        repo = JsonBestPracticeRepository(bp_path)
        assert len(repo.list_all()) == 20