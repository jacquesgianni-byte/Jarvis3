"""
Engineering Academy Loader.

Single responsibility: read JSON, validate schema, construct models.
No business logic. No caching. No querying.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .exceptions import AcademySchemaError, InvalidPrincipleError
from .models import REQUIRED_FIELDS, EngineeringPrinciple


class AcademyLoader:
    """
    Loads and validates the principles JSON file.

    Responsibilities
    ----------------
    * Read raw JSON from disk.
    * Validate top-level structure.
    * Validate each principle record.
    * Detect duplicate IDs.
    * Construct and return immutable ``EngineeringPrinciple`` objects.

    This class does NOT cache, query, or filter results.
    """

    def load(self, path: Path) -> List[EngineeringPrinciple]:
        """
        Load principles from *path* and return a validated list.

        Parameters
        ----------
        path:
            Absolute or relative path to ``principles.json``.

        Raises
        ------
        AcademySchemaError
            If the file is missing, unreadable, malformed JSON, or fails
            top-level structure validation.
        InvalidPrincipleError
            If any individual principle record is missing required fields
            or has invalid field types.
        """
        raw = self._read_file(path)
        records = self._validate_top_level(raw)
        principles = [self._validate_record(r) for r in records]
        self._detect_duplicates(principles)
        return principles

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _read_file(self, path: Path) -> object:
        """Read and parse the JSON file."""
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

    def _validate_top_level(self, raw: object) -> list:
        """Confirm the top-level structure is a dict with a 'principles' list."""
        if not isinstance(raw, dict):
            raise AcademySchemaError(
                "Principles file must be a JSON object at the top level."
            )
        if "principles" not in raw:
            raise AcademySchemaError(
                "Principles file is missing required top-level key 'principles'."
            )
        principles = raw["principles"]
        if not isinstance(principles, list):
            raise AcademySchemaError(
                "'principles' must be a JSON array."
            )
        return principles

    def _validate_record(self, record: object) -> EngineeringPrinciple:
        """Validate a single principle record and construct the model."""
        if not isinstance(record, dict):
            raise AcademySchemaError(
                f"Each principle must be a JSON object; got {type(record).__name__}."
            )

        # Determine an identifier for error messages even before full validation.
        principle_id = record.get("id", "<unknown>")

        for field in REQUIRED_FIELDS:
            if field not in record:
                raise InvalidPrincipleError(
                    principle_id, f"missing required field '{field}'"
                )

        # Field-type checks.
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

    def _detect_duplicates(self, principles: List[EngineeringPrinciple]) -> None:
        """Raise AcademySchemaError if any two principles share an ID."""
        seen: set[str] = set()
        for p in principles:
            if p.id in seen:
                raise AcademySchemaError(
                    f"Duplicate principle ID detected: '{p.id}'"
                )
            seen.add(p.id)
