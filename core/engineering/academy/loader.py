"""
Engineering Academy Loader.

Single responsibility: read JSON, validate schema, construct models.
No business logic. No caching. No querying.

Supports both principles.json and patterns.json via dedicated load methods.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .exceptions import AcademySchemaError, InvalidPrincipleError
from .models import (
    REQUIRED_FIELDS,
    REQUIRED_PATTERN_FIELDS,
    DesignPattern,
    EngineeringPrinciple,
)


class AcademyLoader:
    """
    Loads and validates Academy JSON data files.

    Responsibilities
    ----------------
    * Read raw JSON from disk.
    * Validate top-level structure.
    * Validate each record against its required fields.
    * Detect duplicate IDs within a file.
    * Construct and return immutable model objects.

    This class does NOT cache, query, or filter results.
    """

    # ------------------------------------------------------------------
    # Principles
    # ------------------------------------------------------------------

    def load(self, path: Path) -> List[EngineeringPrinciple]:
        """
        Load principles from *path* and return a validated list.

        Raises
        ------
        AcademySchemaError
            If the file is missing, unreadable, malformed JSON, or fails
            top-level structure validation.
        InvalidPrincipleError
            If any individual principle record fails validation.
        """
        raw = self._read_file(path)
        records = self._validate_top_level(raw, key="principles")
        principles = [self._validate_principle(r) for r in records]
        self._detect_duplicates(
            [p.id for p in principles], label="principle"
        )
        return principles

    # ------------------------------------------------------------------
    # Patterns
    # ------------------------------------------------------------------

    def load_patterns(self, path: Path) -> List[DesignPattern]:
        """
        Load design patterns from *path* and return a validated list.

        Raises
        ------
        AcademySchemaError
            If the file is missing, unreadable, malformed JSON, or fails
            top-level structure validation.
        InvalidPrincipleError
            If any individual pattern record fails validation.
        """
        raw = self._read_file(path)
        records = self._validate_top_level(raw, key="patterns")
        patterns = [self._validate_pattern(r) for r in records]
        self._detect_duplicates(
            [p.id for p in patterns], label="pattern"
        )
        return patterns

    # ------------------------------------------------------------------
    # Private — shared I/O
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> object:
        """Read and parse a JSON file from disk."""
        try:
            text = Path(path).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise AcademySchemaError(f"Principles file not found: {path}")
        except OSError as exc:
            raise AcademySchemaError(f"Cannot read principles file: {exc}")

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AcademySchemaError(f"Invalid JSON in principles file: {exc}")

    def _validate_top_level(self, raw: object, key: str) -> list:
        """Confirm the top-level structure is a dict containing *key* as a list."""
        if not isinstance(raw, dict):
            raise AcademySchemaError(
                "Principles file must be a JSON object at the top level."
            )
        if key not in raw:
            raise AcademySchemaError(
                f"Principles file is missing required top-level key '{key}'."
            )
        records = raw[key]
        if not isinstance(records, list):
            raise AcademySchemaError(f"'{key}' must be a JSON array.")
        return records

    def _detect_duplicates(self, ids: List[str], label: str) -> None:
        """Raise AcademySchemaError if any two records share an ID."""
        seen: set[str] = set()
        for record_id in ids:
            if record_id in seen:
                raise AcademySchemaError(
                    f"Duplicate {label} ID detected: '{record_id}'"
                )
            seen.add(record_id)

    # ------------------------------------------------------------------
    # Private — principle validation
    # ------------------------------------------------------------------

    def _validate_principle(self, record: object) -> EngineeringPrinciple:
        """Validate a single principle record and construct the model."""
        if not isinstance(record, dict):
            raise AcademySchemaError(
                f"Each principle must be a JSON object; got {type(record).__name__}."
            )

        principle_id = record.get("id", "<unknown>")

        for field in REQUIRED_FIELDS:
            if field not in record:
                raise InvalidPrincipleError(
                    principle_id, f"missing required field '{field}'"
                )

        str_fields = ("id", "name", "category", "summary", "rationale", "guidance")
        for f in str_fields:
            if not isinstance(record[f], str) or not record[f].strip():
                raise InvalidPrincipleError(
                    principle_id, f"field '{f}' must be a non-empty string"
                )

        list_fields = ("violations", "tags")
        for f in list_fields:
            if not isinstance(record[f], list):
                raise InvalidPrincipleError(
                    principle_id, f"field '{f}' must be a list"
                )

        return EngineeringPrinciple.from_dict(record)

    # ------------------------------------------------------------------
    # Private — pattern validation
    # ------------------------------------------------------------------

    def _validate_pattern(self, record: object) -> DesignPattern:
        """Validate a single pattern record and construct the model."""
        if not isinstance(record, dict):
            raise AcademySchemaError(
                f"Each pattern must be a JSON object; got {type(record).__name__}."
            )

        pattern_id = record.get("id", "<unknown>")

        for field in REQUIRED_PATTERN_FIELDS:
            if field not in record:
                raise InvalidPrincipleError(
                    pattern_id, f"missing required field '{field}'"
                )

        str_fields = ("id", "name", "category", "intent", "problem", "solution")
        for f in str_fields:
            if not isinstance(record[f], str) or not record[f].strip():
                raise InvalidPrincipleError(
                    pattern_id, f"field '{f}' must be a non-empty string"
                )

        list_fields = (
            "when_to_use", "when_not_to_use", "advantages", "disadvantages", "tags"
        )
        for f in list_fields:
            if not isinstance(record[f], list):
                raise InvalidPrincipleError(
                    pattern_id, f"field '{f}' must be a list"
                )

        return DesignPattern.from_dict(record)
