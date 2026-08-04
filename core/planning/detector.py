"""
Planning Intelligence — Detector
Genesis-037 Sprint-001

Detects planning request commands. No AI. Pure pattern matching.
"""

from __future__ import annotations

from typing import Optional


_PLAN_TRIGGERS: frozenset[str] = frozenset({
    "what needs to happen next",
    "what needs to happen",
    "what should happen next",
    "what should happen",
    "create a work plan",
    "create a plan",
    "create work plan",
    "generate a plan",
    "generate a work plan",
    "plan the next sprint",
    "plan next sprint",
    "plan the sprint",
    "give me a plan",
    "show me a plan",
    "show me the plan",
    "work plan",
    "sprint plan",
    "engineering plan",
    "make a plan",
    "plan",
})


class PlanningDetector:
    """Detects planning request commands. Deterministic — no AI."""

    def can_handle(self, utterance: str) -> bool:
        return utterance.strip().lower().rstrip("?!.") in _PLAN_TRIGGERS or \
               utterance.strip().lower() in _PLAN_TRIGGERS
