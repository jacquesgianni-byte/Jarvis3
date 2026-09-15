"""
Jarvis ShiftController — Evidence Models (Sprint A)

EvidenceStrength is DETERMINISTIC. No LLM involvement.
DiagnosisHypothesis is ADVISORY ONLY — it cannot influence
EvidenceStrength, risk classification, or any governance decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto


class EvidenceStrength(Enum):
    """
    Deterministic evidence classification.

    HIGH   = stack trace + failing assertion + affected file (all three)
    MEDIUM = failing assertion + affected file, no stack trace
    LOW    = failing test only — no assertion text, no identified file
    """
    HIGH   = auto()
    MEDIUM = auto()
    LOW    = auto()

    def label(self) -> str:
        return self.name

    @classmethod
    def classify(
        cls,
        has_stack_trace: bool,
        has_assertion: bool,
        has_affected_file: bool,
    ) -> "EvidenceStrength":
        """
        Deterministic classification from three boolean inputs.
        Order of evaluation matches the spec exactly.
        """
        if has_stack_trace and has_assertion and has_affected_file:
            return cls.HIGH
        if has_assertion and has_affected_file:
            return cls.MEDIUM
        return cls.LOW


@dataclass(frozen=True)
class EvidenceBundle:
    """
    Structured evidence carrier attached to every FindingRecord.

    All fields are populated from pytest output parsing only.
    No LLM involvement in populating this dataclass.
    """
    test_id:         str                    # pytest node id  e.g. tests/test_foo.py::TestBar::test_baz
    failure_message: str                    # assertion text or error message
    stack_trace:     str | None             # full traceback if present, else None
    affected_file:   str | None             # repo-relative file from stack/assertion, else None
    strength:        EvidenceStrength

    @classmethod
    def from_pytest_output(
        cls,
        test_id: str,
        failure_message: str,
        stack_trace: str | None,
        affected_file: str | None,
    ) -> "EvidenceBundle":
        """
        Build an EvidenceBundle from raw pytest output fields.
        Strength is derived deterministically.
        """
        strength = EvidenceStrength.classify(
            has_stack_trace=bool(stack_trace),
            has_assertion=bool(failure_message),
            has_affected_file=bool(affected_file),
        )
        return cls(
            test_id=test_id,
            failure_message=failure_message,
            stack_trace=stack_trace,
            affected_file=affected_file,
            strength=strength,
        )

    def to_dict(self) -> dict:
        return {
            "test_id": self.test_id,
            "failure_message": self.failure_message,
            "stack_trace": self.stack_trace,
            "affected_file": self.affected_file,
            "strength": self.strength.label(),
        }


@dataclass
class DiagnosisHypothesis:
    """
    Advisory LLM output attached to a FindingRecord.

    CRITICAL GOVERNANCE CONSTRAINT:
        DiagnosisHypothesis is human-readable context only.
        It CANNOT influence EvidenceStrength.
        It CANNOT influence risk classification.
        It CANNOT make or influence governance decisions.
        It is labelled 'HYPOTHESIS (ADVISORY ONLY)' in all output.

    It is generated after evidence classification, never before.
    Its content is never passed into RiskClassifier inputs.
    """
    text: str
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    ADVISORY_LABEL: str = "HYPOTHESIS (ADVISORY ONLY)"

    def to_dict(self) -> dict:
        return {
            "label": self.ADVISORY_LABEL,
            "text": self.text,
            "generated_at": self.generated_at.isoformat(),
        }
