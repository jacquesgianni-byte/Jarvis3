"""
Engineering Evidence Manager — Store
Genesis-034 Sprint-002

Accumulates and persists Genesis engineering evidence via KnowledgeEngine.
No new storage layer. Uses 'projects' category.

Storage convention:
  subject:   "genesis_evidence_{number}"
  category:  "projects"
  attribute: field name (e.g. "commits", "test_results", "files_added")
  value:     JSON-serialised field value
  tags:      ["genesis_evidence", "genesis_{number}", "{attribute}"]

Each field is stored as a separate memory record so individual
fields can be updated without replacing the entire evidence block.
On snapshot(), all fields are assembled back into EvidenceSnapshot.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from core.engineering.evidence.models import EvidenceSnapshot

logger = logging.getLogger(__name__)

_CATEGORY = "projects"
_TAG_TYPE = "genesis_evidence"


def _subject(genesis: str) -> str:
    return f"genesis_evidence_{genesis}"


def _attr_to_tag(attribute: str) -> str:
    return f"field_{attribute}"


class EvidenceStore:
    """
    Accumulates Genesis evidence records via KnowledgeEngine.

    Each evidence field is stored/updated independently.
    snapshot() assembles all fields into an EvidenceSnapshot.
    """

    def __init__(self, knowledge_engine) -> None:
        self._ke = knowledge_engine

    # ── Write ──────────────────────────────────────────────────────────────────

    def initialise(self, genesis: str, sprint: str = "") -> None:
        """Initialise evidence storage for a new Genesis."""
        self._set(genesis, "genesis", genesis)
        self._set(genesis, "sprint", sprint)
        self._set(genesis, "status", "in_progress")
        logger.info("[EVIDENCE] Initialised evidence for Genesis-%s", genesis)

    def append_commit(self, genesis: str, commit_hash: str) -> None:
        """Append a commit hash to the commits list."""
        commits = self._get_list(genesis, "commits")
        if commit_hash not in commits:
            commits.append(commit_hash)
            self._set(genesis, "commits", json.dumps(commits))
            logger.info("[EVIDENCE] Commit appended: %s", commit_hash)

    def set_files(
        self,
        genesis: str,
        files_added: list[str],
        files_modified: list[str],
    ) -> None:
        """Record files added and modified."""
        self._set(genesis, "files_added",    json.dumps(files_added))
        self._set(genesis, "files_modified", json.dumps(files_modified))

    def set_test_results(
        self,
        genesis: str,
        passed: int,
        skipped: int,
        failed: int,
        warnings: int = 0,
        tests_added: int = 0,
    ) -> None:
        """Record test suite results."""
        results = {
            "passed":   passed,
            "skipped":  skipped,
            "failed":   failed,
            "warnings": warnings,
        }
        self._set(genesis, "test_results", json.dumps(results))
        self._set(genesis, "tests_added",  str(tests_added))
        logger.info(
            "[EVIDENCE] Test results: passed=%d failed=%d skipped=%d",
            passed, failed, skipped,
        )

    def set_desktop_validation(
        self,
        genesis: str,
        status: str,
        scenarios: list[str],
        notes: Optional[str] = None,
    ) -> None:
        """Record desktop validation results."""
        dv = {"status": status, "scenarios": scenarios, "notes": notes}
        self._set(genesis, "desktop_validation", json.dumps(dv))

    def set_recommendation(
        self,
        genesis: str,
        recommendation: str,
        reason: str,
    ) -> None:
        """Set the final recommendation and reason."""
        self._set(genesis, "recommendation",        recommendation)
        self._set(genesis, "recommendation_reason", reason)

    def set_status(self, genesis: str, status: str) -> None:
        """Update genesis status (e.g. 'complete', 'in_progress')."""
        self._set(genesis, "status", status)

    def set_field(self, genesis: str, field_name: str, value: Any) -> None:
        """
        Set any arbitrary evidence field by name.
        Value is JSON-serialised if it's a list or dict.
        """
        if isinstance(value, (list, dict)):
            self._set(genesis, field_name, json.dumps(value))
        else:
            self._set(genesis, field_name, str(value))

    def append_to_list_field(
        self, genesis: str, field_name: str, item: Any
    ) -> None:
        """Append an item to a list-typed evidence field."""
        current = self._get_list(genesis, field_name)
        current.append(item)
        self._set(genesis, field_name, json.dumps(current))

    # ── Read ───────────────────────────────────────────────────────────────────

    def snapshot(self, genesis: str) -> EvidenceSnapshot:
        """
        Assemble all stored evidence fields into an EvidenceSnapshot.
        Missing fields use EvidenceSnapshot defaults.
        """
        def _str(attr: str, default: str = "") -> str:
            r = self._ke.recall_memory(_subject(genesis), attr)
            return r.value if r else default

        def _list(attr: str) -> list:
            r = self._ke.recall_memory(_subject(genesis), attr)
            if r is None:
                return []
            try:
                val = json.loads(r.value)
                return val if isinstance(val, list) else []
            except (json.JSONDecodeError, TypeError):
                return []

        def _dict(attr: str, default: dict) -> dict:
            r = self._ke.recall_memory(_subject(genesis), attr)
            if r is None:
                return default
            try:
                val = json.loads(r.value)
                return val if isinstance(val, dict) else default
            except (json.JSONDecodeError, TypeError):
                return default

        def _int(attr: str, default: int = 0) -> int:
            r = self._ke.recall_memory(_subject(genesis), attr)
            if r is None:
                return default
            try:
                return int(r.value)
            except (ValueError, TypeError):
                return default

        return EvidenceSnapshot(
            genesis=genesis,
            sprint=_str("sprint"),
            status=_str("status", "in_progress"),
            commits=_list("commits"),
            files_added=_list("files_added"),
            files_modified=_list("files_modified"),
            architecture_decisions=_list("architecture_decisions"),
            tests_added=_int("tests_added"),
            test_results=_dict("test_results", {
                "passed": 0, "skipped": 0, "failed": 0, "warnings": 0
            }),
            desktop_validation=_dict("desktop_validation", {
                "status": "pending", "scenarios": [], "notes": None
            }),
            technical_debt=_list("technical_debt"),
            risks=_list("risks"),
            future_improvements=_list("future_improvements"),
            technical_problem=_str("technical_problem"),
            technical_uncertainty=_str("technical_uncertainty"),
            hypothesis=_str("hypothesis"),
            approach=_str("approach"),
            experiments=_list("experiments"),
            results=_str("results"),
            validation=_str("validation"),
            remaining_unknowns=_list("remaining_unknowns"),
            recommendation=_str("recommendation", "CONTINUE_GENESIS"),
            recommendation_reason=_str("recommendation_reason"),
        )

    def has_evidence(self, genesis: str) -> bool:
        """Return True if any evidence has been stored for this genesis."""
        r = self._ke.recall_memory(_subject(genesis), "genesis")
        return r is not None

    # ── Internal ───────────────────────────────────────────────────────────────

    def _set(self, genesis: str, attribute: str, value: str) -> None:
        """Store or update a single evidence field."""
        subj = _subject(genesis)
        tags = [_TAG_TYPE, f"genesis_{genesis}", _attr_to_tag(attribute)]

        existing = self._ke.recall_memory(subj, attribute)
        if existing is not None:
            # Hard-delete then re-store to correctly update tags+value
            self._ke.forget_memory(subj, attribute, permanent=True)

        self._ke.store_memory(
            subject=subj,
            category=_CATEGORY,
            attribute=attribute,
            value=value,
            tags=tags,
        )

    def _get_list(self, genesis: str, attribute: str) -> list:
        r = self._ke.recall_memory(_subject(genesis), attribute)
        if r is None:
            return []
        try:
            val = json.loads(r.value)
            return val if isinstance(val, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
