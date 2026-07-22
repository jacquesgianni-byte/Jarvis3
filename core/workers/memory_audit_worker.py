"""
Jarvis Memory Audit Worker (Genesis-W002 Sprint-001)

Analyses Jarvis's KnowledgeEngine memory store and produces a structured
audit report. Diagnostic only — never modifies data or generates patches.

Responsibilities:
    - Detect duplicate facts
    - Detect zombie/orphaned records (misclassified, stale, or derived-only)
    - Detect inconsistent attribute names (colour vs color, etc.)
    - Detect bare-value records likely to produce poor recall
    - Detect conflicting facts about the same subject
    - Report memory statistics
    - Produce confidence scores for each finding

Design constraints:
    - No AI calls
    - No data modification
    - No code generation
    - Read-only KnowledgeEngine access via list_memories() only
    - Deterministic — same store → same report

Usage (library):
    from core.knowledge_engine.engine import KnowledgeEngine
    worker = MemoryAuditWorker(KnowledgeEngine())
    report = worker.analyse()
    print(report.formatted())

Usage (CLI):
    python -m core.workers.memory_audit_worker
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from core.workers.engineering_models import (
    Category, EngineeringIssue, EngineeringReport, Severity,
)

# ---------------------------------------------------------------------------
# Spelling variants that should resolve to the same canonical attribute
# ---------------------------------------------------------------------------
_SPELLING_VARIANTS: list[frozenset[str]] = [
    frozenset({"colour", "color"}),
    frozenset({"favourite colour", "favorite color", "favourite color", "favorite colour"}),
    frozenset({"favourite drink", "favorite drink"}),
    frozenset({"favourite food", "favorite food"}),
    frozenset({"favourite sport", "favorite sport"}),
    frozenset({"favourite team", "favorite team"}),
]

# Subjects that are clearly not person names but get tagged as persons
# due to over-broad person extraction patterns
_KNOWN_NON_PERSON_SUBJECTS: frozenset[str] = frozenset({
    "favourite drink", "favourite colour", "favourite food",
    "favorite drink", "favorite color", "favorite food",
    "favourite sport", "favorite sport",
    "favourite team", "favorite team",
    "what", "how", "why", "when", "where",
})

# Bare/noise values that indicate a record is not useful for recall
_BARE_VALUES: frozenset[str] = frozenset({
    "it", "that", "this", "them", "something", "anything",
    "everything", "nothing", "yes", "no", "ok", "okay",
    "true", "false", "me", "you", "we", "i", "my",
})

# Maximum age in days before a conversation journal record is considered stale
_JOURNAL_STALE_DAYS = 30


class MemoryAuditWorker:
    """
    Analyses the KnowledgeEngine memory store and returns an audit report.

    Accepts a KnowledgeEngine instance so it can be used both in tests
    (with a mock engine) and in production (with the real engine).

    Public API:
        analyse() -> EngineeringReport
    """

    def __init__(self, engine: Any) -> None:
        """
        Args:
            engine: A KnowledgeEngine instance (or compatible mock).
        """
        self._engine = engine

    def analyse(self) -> EngineeringReport:
        """
        Load all memory records and produce an audit report.

        Returns:
            EngineeringReport with health score, successes, and issues.
        """
        # Load all records — use a high limit to get everything
        records = self._engine.list_memories(limit=10000)

        issues: list[EngineeringIssue] = []
        issues.extend(self._check_duplicates(records))
        issues.extend(self._check_misclassified(records))
        issues.extend(self._check_spelling_variants(records))
        issues.extend(self._check_bare_values(records))
        issues.extend(self._check_conflicts(records))
        issues.extend(self._check_zombie_journals(records))

        successes = self._detect_successes(records)
        health_score = self._compute_health(records, issues)
        summary = self._build_summary(records, issues, health_score)

        return EngineeringReport(
            health_score=health_score,
            session_turns=len(records),  # repurposed as record count
            successes=successes,
            issues=sorted(issues, key=lambda i: (
                {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}[i.severity.value]
            )),
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_duplicates(self, records: list) -> list[EngineeringIssue]:
        """Detect records with identical (subject, attribute, value) tuples."""
        seen: dict[tuple, int] = defaultdict(int)
        for r in records:
            key = (r.subject.lower().strip(),
                   r.attribute.lower().strip(),
                   r.value.lower().strip())
            seen[key] += 1

        dupes = {k: v for k, v in seen.items() if v > 1}
        if not dupes:
            return []

        evidence = [
            f"subject={k[0]!r} attribute={k[1]!r} value={k[2]!r} × {v}"
            for k, v in list(dupes.items())[:3]
        ]
        return [EngineeringIssue(
            severity=Severity.MEDIUM,
            category=Category.MEMORY,
            title=f"Duplicate memory records detected ({len(dupes)} group(s))",
            description=(
                f"{len(dupes)} subject/attribute/value combination(s) appear more "
                "than once in the store. Duplicates waste space and can cause "
                "inconsistent recall."
            ),
            evidence=evidence,
            confidence=0.97,
            likely_files=[
                "core/conversation/conversation_observer.py",
                "core/skills/memory.py",
            ],
            recommendation=(
                "Add a deduplication check in ConversationObserver.observe() before "
                "calling store_memory(). Consider using update_memory() instead."
            ),
        )]

    def _check_misclassified(self, records: list) -> list[EngineeringIssue]:
        """
        Detect records where subject is a preference/attribute word but
        the record is tagged as a person — a known over-extraction bug.
        """
        misclassified = [
            r for r in records
            if r.subject.lower().strip() in _KNOWN_NON_PERSON_SUBJECTS
            and "person" in (r.tags or [])
        ]
        if not misclassified:
            return []

        evidence = [
            f"subject={r.subject!r} attribute={r.attribute!r} value={r.value!r}"
            for r in misclassified[:3]
        ]
        return [EngineeringIssue(
            severity=Severity.HIGH,
            category=Category.MEMORY,
            title=f"Misclassified person records ({len(misclassified)} record(s))",
            description=(
                f"{len(misclassified)} record(s) have non-person subjects "
                "(e.g. 'favourite drink') but are tagged as persons. "
                "These will produce wrong recall answers."
            ),
            evidence=evidence,
            confidence=0.93,
            likely_files=[
                "core/conversation/fact_extractor.py",
                "core/conversation/conversation_observer.py",
            ],
            recommendation=(
                "In FactExtractor._extract_people(), add a guard that skips "
                "subjects matching known preference/attribute words. "
                "Mirror the _NON_NAME_WORDS guard already used for values."
            ),
        )]

    def _check_spelling_variants(self, records: list) -> list[EngineeringIssue]:
        """
        Detect attributes stored under multiple spelling variants
        (e.g. 'colour' and 'color') for the same subject.
        """
        issues = []
        # Group attributes by subject
        by_subject: dict[str, set[str]] = defaultdict(set)
        for r in records:
            by_subject[r.subject.lower()].add(r.attribute.lower())

        for subject, attrs in by_subject.items():
            for variant_set in _SPELLING_VARIANTS:
                found = attrs & variant_set
                if len(found) > 1:
                    issues.append(EngineeringIssue(
                        severity=Severity.MEDIUM,
                        category=Category.MEMORY,
                        title=f"Spelling variant conflict for subject {subject!r}",
                        description=(
                            f"Subject {subject!r} has the same fact stored under "
                            f"multiple spelling variants: {sorted(found)}. "
                            "Recall may return different values depending on which "
                            "variant is queried."
                        ),
                        evidence=[f"subject={subject!r} attrs={sorted(found)}"],
                        confidence=0.91,
                        likely_files=["core/skills/memory.py"],
                        recommendation=(
                            "The _canonicalise() function in memory.py should "
                            "normalise all variants to a single canonical form "
                            "before storage."
                        ),
                    ))
        return issues

    def _check_bare_values(self, records: list) -> list[EngineeringIssue]:
        """
        Detect records whose value is a noise/bare word that won't
        produce a useful recall response.
        """
        bare = [
            r for r in records
            if r.value.lower().strip() in _BARE_VALUES
            and r.subject != "jarvis"
        ]
        if not bare:
            return []

        evidence = [
            f"subject={r.subject!r} attribute={r.attribute!r} value={r.value!r}"
            for r in bare[:3]
        ]
        return [EngineeringIssue(
            severity=Severity.LOW,
            category=Category.MEMORY,
            title=f"Bare/noise values in memory ({len(bare)} record(s))",
            description=(
                f"{len(bare)} record(s) store bare/noise values "
                "(e.g. 'it', 'that', 'yes') that won't produce useful recall. "
                "These typically come from over-broad extraction patterns."
            ),
            evidence=evidence,
            confidence=0.85,
            likely_files=["core/conversation/fact_extractor.py"],
            recommendation=(
                "The _is_noise() function in fact_extractor.py filters these "
                "during extraction. Check whether these records were created "
                "by an older version before the noise filter was added."
            ),
        )]

    def _check_conflicts(self, records: list) -> list[EngineeringIssue]:
        """
        Detect conflicting values for the same (subject, attribute) pair
        across records with different IDs (not just duplicates).
        """
        by_key: dict[tuple, list[str]] = defaultdict(list)
        for r in records:
            key = (r.subject.lower().strip(), r.attribute.lower().strip())
            by_key[key].append(r.value.strip())

        conflicts = {
            k: vals for k, vals in by_key.items()
            if len(set(v.lower() for v in vals)) > 1
            and k[0] != "jarvis"  # journal records legitimately differ
        }
        if not conflicts:
            return []

        evidence = [
            f"subject={k[0]!r} attribute={k[1]!r} values={list(set(v.lower() for v in vals))[:3]}"
            for k, vals in list(conflicts.items())[:3]
        ]
        return [EngineeringIssue(
            severity=Severity.MEDIUM,
            category=Category.MEMORY,
            title=f"Conflicting facts detected ({len(conflicts)} attribute(s))",
            description=(
                f"{len(conflicts)} subject/attribute pair(s) have multiple "
                "different stored values. The most recent value wins during "
                "recall, but older conflicting values may cause confusion."
            ),
            evidence=evidence,
            confidence=0.82,
            likely_files=[
                "core/knowledge_engine/engine.py",
                "core/skills/memory.py",
            ],
            recommendation=(
                "Use update_memory() instead of store_memory() for facts that "
                "can change over time (name, colour, etc.) to ensure only one "
                "value is kept per attribute."
            ),
        )]

    def _check_zombie_journals(self, records: list) -> list[EngineeringIssue]:
        """
        Detect conversation journal records (subject='jarvis',
        attribute starts with 'conversation_') that are accumulating
        without bound. These are not useful for recall and bloat the store.
        """
        journals = [
            r for r in records
            if r.subject == "jarvis"
            and r.attribute.startswith("conversation_")
        ]
        if len(journals) < 50:
            return []

        return [EngineeringIssue(
            severity=Severity.LOW,
            category=Category.MEMORY,
            title=f"Journal record accumulation ({len(journals)} records)",
            description=(
                f"{len(journals)} conversation journal records exist in the store. "
                "These grow without bound and are rarely used for recall. "
                "They may slow down search_memory() over time."
            ),
            evidence=[
                f"Oldest: {journals[-1].attribute if journals else 'n/a'}",
                f"Newest: {journals[0].attribute if journals else 'n/a'}",
            ],
            confidence=0.88,
            likely_files=["core/conversation/conversation_observer.py"],
            recommendation=(
                "Consider adding a TTL or max-count limit to journal records. "
                "Alternatively, store journals in a separate category so "
                "search_memory() can exclude them by default."
            ),
        )]

    # ------------------------------------------------------------------
    # Successes
    # ------------------------------------------------------------------

    def _detect_successes(self, records: list) -> list[str]:
        successes = []

        user_records = [r for r in records if r.subject == "user"]
        if user_records:
            successes.append(f"{len(user_records)} user fact(s) stored")

        subjects = {r.subject for r in records if r.subject != "jarvis"}
        if subjects:
            successes.append(f"{len(subjects)} unique subject(s) in store")

        hit_records = [r for r in records if "auto-extracted" not in (r.tags or [])]
        explicit = [r for r in records
                    if r.subject == "user" and "derived" not in (r.tags or [])
                    and "auto-extracted" not in (r.tags or [])]
        if explicit:
            successes.append(f"{len(explicit)} explicitly stored user fact(s)")

        pet_records = [r for r in records if "pet" in (r.tags or [])]
        if pet_records:
            successes.append(f"{len(pet_records)} pet fact(s) correctly tagged")

        workplace = [r for r in records
                     if r.subject == "user" and r.attribute == "workplace"]
        if workplace:
            successes.append(f"Workplace stored: {workplace[0].value!r}")

        return successes

    # ------------------------------------------------------------------
    # Health score
    # ------------------------------------------------------------------

    def _compute_health(self, records: list, issues: list[EngineeringIssue]) -> int:
        if not records:
            return 100

        score = 100
        high   = sum(1 for i in issues if i.severity == Severity.HIGH)
        medium = sum(1 for i in issues if i.severity == Severity.MEDIUM)
        low    = sum(1 for i in issues if i.severity == Severity.LOW)

        score -= high   * 20
        score -= medium * 8
        score -= low    * 3

        # Bonus for having user facts
        user_facts = sum(1 for r in records if r.subject == "user")
        if user_facts >= 5:
            score = min(100, score + 5)

        return max(0, min(100, score))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self, records: list, issues: list[EngineeringIssue], health_score: int
    ) -> str:
        user_facts  = sum(1 for r in records if r.subject == "user")
        high_count  = sum(1 for i in issues if i.severity == Severity.HIGH)
        total       = len(records)

        parts = [f"Memory store: {total} record(s), {user_facts} user fact(s)."]
        if high_count:
            parts.append(f"{high_count} HIGH severity issue(s) require attention.")
        if health_score >= 90:
            parts.append("Memory store is in excellent condition.")
        elif health_score >= 70:
            parts.append("Memory store is healthy with minor issues.")
        else:
            parts.append("Memory store has structural issues worth cleaning up.")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from core.knowledge_engine.engine import KnowledgeEngine

    print("Loading KnowledgeEngine...")
    try:
        engine = KnowledgeEngine()
    except Exception as e:
        print(f"Error: could not load KnowledgeEngine: {e}")
        sys.exit(1)

    worker = MemoryAuditWorker(engine)
    print("Analysing memory store...\n")
    report = worker.analyse()
    print(report.formatted())