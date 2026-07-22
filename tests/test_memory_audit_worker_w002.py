"""
Genesis-W002 Sprint-001 — Memory Audit Worker Tests

Coverage:
  - MemoryAuditWorker: duplicate detection
  - MemoryAuditWorker: misclassified person records
  - MemoryAuditWorker: spelling variant conflicts
  - MemoryAuditWorker: bare/noise values
  - MemoryAuditWorker: conflicting facts
  - MemoryAuditWorker: journal accumulation
  - MemoryAuditWorker: health score
  - MemoryAuditWorker: successes
  - MemoryAuditWorker: empty store
  - EngineeringReport: formatted output
"""

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.workers.memory_audit_worker import MemoryAuditWorker
from core.workers.engineering_models import Category, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(
    subject: str,
    attribute: str,
    value: str,
    tags: list[str] | None = None,
    category: str = "general",
    source: str = "user",
    record_id: str | None = None,
):
    r = MagicMock()
    r.subject   = subject
    r.attribute = attribute
    r.value     = value
    r.tags      = tags or []
    r.category  = category
    r.source    = source
    r.id        = record_id or f"{subject}:{attribute}"
    r.updated_at = datetime.now(UTC)
    return r


def make_engine(records: list) -> MagicMock:
    engine = MagicMock()
    engine.list_memories.return_value = records
    return engine


def make_worker(records: list) -> MemoryAuditWorker:
    return MemoryAuditWorker(make_engine(records))


# ===========================================================================
# 1. Empty store
# ===========================================================================

class TestMemoryAuditWorkerEmpty:

    def test_empty_store_returns_report(self):
        worker = make_worker([])
        report = worker.analyse()
        assert report.health_score == 100
        assert report.session_turns == 0
        assert not report.has_issues()

    def test_empty_store_no_issues(self):
        worker = make_worker([])
        report = worker.analyse()
        assert report.issues == []


# ===========================================================================
# 2. Duplicate detection
# ===========================================================================

class TestDuplicateDetection:

    def test_detects_exact_duplicates(self):
        records = [
            make_record("user", "name", "Gianni"),
            make_record("user", "name", "Gianni"),
        ]
        report = make_worker(records).analyse()
        mem_issues = [i for i in report.issues if i.category == Category.MEMORY]
        assert any("duplicate" in i.title.lower() for i in mem_issues)

    def test_no_duplicate_when_different_values(self):
        records = [
            make_record("user", "name", "Gianni"),
            make_record("user", "name", "Ludovic"),
        ]
        report = make_worker(records).analyse()
        mem_issues = [i for i in report.issues if i.category == Category.MEMORY]
        assert not any("duplicate" in i.title.lower() for i in mem_issues)

    def test_no_duplicate_when_different_attributes(self):
        records = [
            make_record("user", "name", "Gianni"),
            make_record("user", "favourite colour", "blue"),
        ]
        report = make_worker(records).analyse()
        mem_issues = [i for i in report.issues if i.category == Category.MEMORY]
        assert not any("duplicate" in i.title.lower() for i in mem_issues)

    def test_duplicate_confidence_high(self):
        records = [
            make_record("user", "pets", "2 dogs"),
            make_record("user", "pets", "2 dogs"),
        ]
        report = make_worker(records).analyse()
        dup_issues = [i for i in report.issues if "duplicate" in i.title.lower()]
        assert dup_issues[0].confidence >= 0.90


# ===========================================================================
# 3. Misclassified person records
# ===========================================================================

class TestMisclassifiedPersonRecords:

    def test_detects_preference_tagged_as_person(self):
        records = [
            make_record(
                "favourite drink", "role", "coffee",
                tags=["person", "auto-extracted"]
            ),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "misclassified" in i.title.lower()]
        assert len(issues) == 1
        assert issues[0].severity == Severity.HIGH

    def test_no_flag_for_real_person(self):
        records = [
            make_record("manager", "role", "Sarah", tags=["person", "auto-extracted"]),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "misclassified" in i.title.lower()]
        assert len(issues) == 0

    def test_misclassified_includes_likely_files(self):
        records = [
            make_record("favourite colour", "role", "blue", tags=["person"]),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "misclassified" in i.title.lower()]
        assert any("fact_extractor" in f for f in issues[0].likely_files)


# ===========================================================================
# 4. Spelling variant conflicts
# ===========================================================================

class TestSpellingVariants:

    def test_detects_colour_color_conflict(self):
        records = [
            make_record("user", "favourite colour", "blue"),
            make_record("user", "favorite color", "blue"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "spelling" in i.title.lower() or "variant" in i.title.lower()]
        assert len(issues) >= 1

    def test_no_flag_when_single_spelling(self):
        records = [
            make_record("user", "favourite colour", "blue"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "spelling" in i.title.lower() or "variant" in i.title.lower()]
        assert len(issues) == 0

    def test_detects_drink_variant(self):
        records = [
            make_record("user", "favourite drink", "coffee"),
            make_record("user", "favorite drink", "coffee"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "spelling" in i.title.lower() or "variant" in i.title.lower()]
        assert len(issues) >= 1


# ===========================================================================
# 5. Bare value detection
# ===========================================================================

class TestBareValueDetection:

    def test_detects_bare_value_it(self):
        records = [
            make_record("user", "current project", "it"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "bare" in i.title.lower() or "noise" in i.title.lower()]
        assert len(issues) >= 1

    def test_no_flag_for_meaningful_value(self):
        records = [
            make_record("user", "current project", "Jarvis OS"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "bare" in i.title.lower() or "noise" in i.title.lower()]
        assert len(issues) == 0

    def test_jarvis_journal_bare_values_not_flagged(self):
        records = [
            make_record("jarvis", "conversation_2026-07-21", "yes"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "bare" in i.title.lower()]
        assert len(issues) == 0


# ===========================================================================
# 6. Conflicting facts
# ===========================================================================

class TestConflictingFacts:

    def test_detects_conflicting_name(self):
        records = [
            make_record("user", "name", "Gianni", record_id="r1"),
            make_record("user", "name", "Ludovic", record_id="r2"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "conflict" in i.title.lower()]
        assert len(issues) >= 1

    def test_no_conflict_when_same_value(self):
        records = [
            make_record("user", "name", "Gianni", record_id="r1"),
            make_record("user", "name", "Gianni", record_id="r2"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "conflict" in i.title.lower()]
        assert len(issues) == 0

    def test_jarvis_journals_not_flagged_as_conflicts(self):
        records = [
            make_record("jarvis", "conversation_2026-07-21_10-00", "hello", record_id="r1"),
            make_record("jarvis", "conversation_2026-07-21_11-00", "goodbye", record_id="r2"),
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "conflict" in i.title.lower()]
        assert len(issues) == 0


# ===========================================================================
# 7. Journal accumulation
# ===========================================================================

class TestJournalAccumulation:

    def test_detects_journal_accumulation(self):
        records = [
            make_record("jarvis", f"conversation_2026-07-21_10-{i:02d}-00", f"turn {i}")
            for i in range(60)
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "journal" in i.title.lower() or "accumulation" in i.title.lower()]
        assert len(issues) >= 1

    def test_no_flag_when_few_journals(self):
        records = [
            make_record("jarvis", f"conversation_2026-07-21_10-{i:02d}-00", f"turn {i}")
            for i in range(10)
        ]
        report = make_worker(records).analyse()
        issues = [i for i in report.issues if "journal" in i.title.lower() or "accumulation" in i.title.lower()]
        assert len(issues) == 0


# ===========================================================================
# 8. Health score
# ===========================================================================

class TestHealthScore:

    def test_clean_store_high_health(self):
        records = [
            make_record("user", "name", "Gianni"),
            make_record("user", "favourite colour", "blue"),
            make_record("user", "pets", "2 dogs", tags=["pet"]),
            make_record("user", "pet names", "Rex and Tom", tags=["pet"]),
            make_record("user", "workplace", "Academy of Healthcare"),
        ]
        report = make_worker(records).analyse()
        assert report.health_score >= 80

    def test_misclassified_lowers_health(self):
        records = [
            make_record("favourite drink", "role", "coffee", tags=["person"]),
            make_record("favourite colour", "role", "blue", tags=["person"]),
        ]
        report = make_worker(records).analyse()
        assert report.health_score <= 80

    def test_health_score_bounded(self):
        report = make_worker([]).analyse()
        assert 0 <= report.health_score <= 100


# ===========================================================================
# 9. Successes
# ===========================================================================

class TestSuccesses:

    def test_user_facts_reported(self):
        records = [
            make_record("user", "name", "Gianni"),
            make_record("user", "favourite colour", "blue"),
        ]
        report = make_worker(records).analyse()
        assert any("user fact" in s.lower() for s in report.successes)

    def test_pet_facts_reported(self):
        records = [
            make_record("user", "pets", "2 dogs", tags=["pet"]),
        ]
        report = make_worker(records).analyse()
        assert any("pet" in s.lower() for s in report.successes)

    def test_workplace_reported(self):
        records = [
            make_record("user", "workplace", "Academy of Healthcare"),
        ]
        report = make_worker(records).analyse()
        assert any("workplace" in s.lower() or "Academy" in s for s in report.successes)


# ===========================================================================
# 10. Formatted output
# ===========================================================================

class TestFormattedOutput:

    def test_formatted_contains_health_score(self):
        report = make_worker([]).analyse()
        output = report.formatted()
        assert "Health Score" in output
        assert "100" in output

    def test_formatted_contains_summary(self):
        records = [make_record("user", "name", "Gianni")]
        report = make_worker(records).analyse()
        output = report.formatted()
        assert "Memory store" in output or "Summary" in output