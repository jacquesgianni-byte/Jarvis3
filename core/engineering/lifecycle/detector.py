"""
Engineering Lifecycle Manager — Detector
Genesis-034 Sprint-001

Deterministic detection of Open/Close Genesis commands.
No AI. Pure pattern matching.
"""

from __future__ import annotations

import re
from typing import Optional

from core.engineering.lifecycle.models import LifecycleCommand, LifecycleCommandKind

# ── Open Genesis patterns ──────────────────────────────────────────────────────
_OPEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"^open\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^start\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^begin\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^genesis[-\s]?(\d+)\s+(?:is\s+)?open", re.IGNORECASE),
    re.compile(r"^(?:i'?m?\s+)?starting\s+genesis[-\s]?(\d+)", re.IGNORECASE),
]

# ── Close Genesis patterns ─────────────────────────────────────────────────────
_CLOSE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^close\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^complete\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^finish\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^end\s+genesis[-\s]?(\d+)", re.IGNORECASE),
    re.compile(r"^genesis[-\s]?(\d+)\s+(?:is\s+)?(?:complete|closed|done|finished)", re.IGNORECASE),
    re.compile(r"^wrap\s+up\s+genesis[-\s]?(\d+)", re.IGNORECASE),
]


class LifecycleDetector:
    """
    Detects Open Genesis / Close Genesis commands.
    Deterministic — no AI, no external calls.
    """

    def detect(self, utterance: str) -> Optional[LifecycleCommand]:
        """
        Parse a user utterance for lifecycle commands.

        Returns a LifecycleCommand if detected, else None.
        """
        text = utterance.strip()

        for pattern in _CLOSE_PATTERNS:
            m = pattern.match(text)
            if m:
                genesis = m.group(1).zfill(3)
                return LifecycleCommand(
                    kind=LifecycleCommandKind.CLOSE_GENESIS,
                    genesis=genesis,
                    raw=text,
                )

        for pattern in _OPEN_PATTERNS:
            m = pattern.match(text)
            if m:
                genesis = m.group(1).zfill(3)
                return LifecycleCommand(
                    kind=LifecycleCommandKind.OPEN_GENESIS,
                    genesis=genesis,
                    raw=text,
                )

        return None
