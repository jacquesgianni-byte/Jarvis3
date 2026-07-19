"""
Jarvis Conversation Recovery Handler (Genesis-022 Sprint-005)

Recognises conversational corrections before any other processing occurs.

The RecoveryHandler receives:
    - raw user input
    - ConversationState (read-write — recovery IS allowed to modify state)

and produces a RecoveryResult indicating what happened.

Recovery is the ONLY pipeline stage that may modify ConversationState.
All other stages are read-only with respect to state.

Design constraints:
    - Completely deterministic. No AI.
    - Modifies ConversationState only for confirmed recovery patterns.
    - Always produces a RecoveryResult.
    - Never invokes routing, Workers, or Tools.

Recovery actions:
    NONE         — not a recovery pattern, continue normally
    PENDING_CANCELLED — pending question was cancelled
    TOPIC_REVERTED    — topic was rolled back to previous
    STATE_RESET       — full dialogue state reset
    ACKNOWLEDGED      — recovery acknowledged, no state change needed
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState


# ---------------------------------------------------------------------------
# RecoveryAction
# ---------------------------------------------------------------------------

class RecoveryAction(Enum):
    """What the recovery handler did in response to the input."""
    NONE               = auto()  # not a recovery pattern
    PENDING_CANCELLED  = auto()  # pending question cancelled
    TOPIC_REVERTED     = auto()  # topic rolled back
    STATE_RESET        = auto()  # full dialogue state reset
    ACKNOWLEDGED       = auto()  # recovery noted, no state change

    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def is_recovery(self) -> bool:
        """True if any recovery action was taken (not NONE)."""
        return self != RecoveryAction.NONE


# ---------------------------------------------------------------------------
# RecoveryResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RecoveryResult:
    """
    The result of a single recovery check.

    Immutable. Produced by RecoveryHandler.check().
    Stored in ConversationContext for downstream stages to read.

    Attributes:
        action:           What recovery action was taken.
        original_input:   The user's exact input.
        recovered:        True if any recovery action was applied.
        reason:           Human-readable explanation.
        should_continue:  True if pipeline should continue after recovery.
                          False if the pipeline should stop (e.g. full reset).
        pattern_matched:  The specific pattern that triggered recovery.
    """
    action:          RecoveryAction
    original_input:  str
    recovered:       bool           = False
    reason:          str            = ""
    should_continue: bool           = True
    pattern_matched: str            = ""

    @classmethod
    def no_recovery(cls, original: str) -> "RecoveryResult":
        """Convenience: no recovery pattern matched."""
        return cls(
            action=RecoveryAction.NONE,
            original_input=original,
            recovered=False,
            reason="No recovery pattern detected.",
            should_continue=True,
        )

    def __str__(self) -> str:
        if self.recovered:
            return f"RecoveryResult({self.action.label()}, pattern={self.pattern_matched!r})"
        return "RecoveryResult(no recovery)"


# ---------------------------------------------------------------------------
# Recovery patterns
# ---------------------------------------------------------------------------

# Full reset — wipes pending question AND topic
_FULL_RESET_PATTERNS = re.compile(
    r"^(never mind|nevermind|forget (?:it|that|everything)|"
    r"start over|let'?s start over|reset|scratch that|"
    r"ignore (?:it|that|everything)|"
    r"let'?s begin again|begin again|"
    r"cancel (?:that|it|everything)|cancel all)[\s\.\!\?]*$",
    re.IGNORECASE,
)

# Pending cancel — cancels pending question but keeps topic
_PENDING_CANCEL_PATTERNS = re.compile(
    r"^(cancel|stop|abort|skip (?:it|that)|"
    r"don'?t (?:ask|bother)|never mind about that|"
    r"no thanks|not now|maybe later)[\s\.\!\?]*$",
    re.IGNORECASE,
)

# Topic revert — go back to previous topic
_TOPIC_REVERT_PATTERNS = re.compile(
    r"\b(go back|let'?s go back|back to|return to|"
    r"revert|previous topic|earlier topic|"
    r"what (?:we|i) (?:was|were) (?:saying|talking about|discussing))\b",
    re.IGNORECASE,
)

# Soft recovery — "actually" etc. — acknowledged but pipeline continues
_SOFT_RECOVERY_PATTERNS = re.compile(
    r"^(actually[,\s]|wait[,\s]|hold on[,\s]|one moment[,\s])",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# RecoveryHandler
# ---------------------------------------------------------------------------

class RecoveryHandler:
    """
    Checks user input for conversational recovery patterns before
    any other pipeline stage runs.

    This is the ONLY component in the pipeline that may modify
    ConversationState. All other stages are read-only.

    Public API:
        check(raw_input, state) → RecoveryResult
        is_recovery(raw_input)  → bool  (fast pre-check)
    """

    def check(
        self,
        raw_input: str,
        state: "ConversationState",
    ) -> RecoveryResult:
        """
        Check input for recovery patterns and apply state changes if needed.

        Priority order:
            1. Empty input → no recovery
            2. Full reset patterns ("never mind", "start over")
            3. Pending cancel patterns ("cancel", "skip it")
            4. Topic revert patterns ("go back", "return to")
            5. Soft recovery patterns ("actually", "wait")
            6. No recovery

        Args:
            raw_input: The user's raw message.
            state:     ConversationState — may be modified by this method.

        Returns:
            RecoveryResult describing what (if anything) was done.
        """
        if not raw_input or not raw_input.strip():
            return RecoveryResult.no_recovery(raw_input or "")

        stripped = raw_input.strip()

        # 1. Full reset
        m = _FULL_RESET_PATTERNS.match(stripped)
        if m:
            return self._handle_full_reset(raw_input, stripped, m.group(0), state)

        # 2. Pending cancel
        m = _PENDING_CANCEL_PATTERNS.match(stripped)
        if m:
            return self._handle_pending_cancel(raw_input, stripped, m.group(0), state)

        # 3. Topic revert
        m = _TOPIC_REVERT_PATTERNS.search(stripped)
        if m:
            return self._handle_topic_revert(raw_input, stripped, m.group(0), state)

        # 4. Soft recovery
        m = _SOFT_RECOVERY_PATTERNS.match(stripped)
        if m:
            return RecoveryResult(
                action=RecoveryAction.ACKNOWLEDGED,
                original_input=raw_input,
                recovered=True,
                reason=f"Soft recovery marker {m.group(0)!r} detected. Pipeline continues.",
                should_continue=True,
                pattern_matched=m.group(0),
            )

        return RecoveryResult.no_recovery(raw_input)

    def is_recovery(self, raw_input: str) -> bool:
        """Fast pre-check: does this input contain any recovery pattern?"""
        if not raw_input or not raw_input.strip():
            return False
        s = raw_input.strip()
        return any(p.search(s) for p in [
            _FULL_RESET_PATTERNS, _PENDING_CANCEL_PATTERNS,
            _TOPIC_REVERT_PATTERNS, _SOFT_RECOVERY_PATTERNS,
        ])

    # ------------------------------------------------------------------
    # State modification helpers — only called from check()
    # ------------------------------------------------------------------

    def _handle_full_reset(
        self, raw: str, stripped: str, pattern: str,
        state: "ConversationState"
    ) -> RecoveryResult:
        """Full reset: clear pending, clear topic."""
        had_pending = state.has_pending()
        had_topic   = state.current_topic is not None

        state.clear_pending()
        state.clear_topic()
        state.clear_references()

        parts = []
        if had_pending: parts.append("pending question cancelled")
        if had_topic:   parts.append("topic cleared")
        if not parts:   parts.append("state already clear")

        return RecoveryResult(
            action=RecoveryAction.STATE_RESET,
            original_input=raw,
            recovered=True,
            reason=f"Full reset: {', '.join(parts)}.",
            should_continue=False,  # pipeline stops after reset
            pattern_matched=pattern,
        )

    def _handle_pending_cancel(
        self, raw: str, stripped: str, pattern: str,
        state: "ConversationState"
    ) -> RecoveryResult:
        """Cancel pending question only — keep topic and references."""
        if state.has_pending():
            state.clear_pending()
            return RecoveryResult(
                action=RecoveryAction.PENDING_CANCELLED,
                original_input=raw,
                recovered=True,
                reason="Pending question cancelled.",
                should_continue=False,
                pattern_matched=pattern,
            )
        # No pending to cancel — acknowledge and continue
        return RecoveryResult(
            action=RecoveryAction.ACKNOWLEDGED,
            original_input=raw,
            recovered=True,
            reason="Cancel detected but no pending question to cancel.",
            should_continue=True,
            pattern_matched=pattern,
        )

    def _handle_topic_revert(
        self, raw: str, stripped: str, pattern: str,
        state: "ConversationState"
    ) -> RecoveryResult:
        """Revert to previous topic if history exists."""
        previous = state.pop_topic()
        if previous is not None:
            return RecoveryResult(
                action=RecoveryAction.TOPIC_REVERTED,
                original_input=raw,
                recovered=True,
                reason=f"Topic reverted to {previous.name!r}.",
                should_continue=True,  # continue with reverted topic
                pattern_matched=pattern,
            )
        return RecoveryResult(
            action=RecoveryAction.ACKNOWLEDGED,
            original_input=raw,
            recovered=True,
            reason="Topic revert requested but no previous topic in history.",
            should_continue=True,
            pattern_matched=pattern,
        )