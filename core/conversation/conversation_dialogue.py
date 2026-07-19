"""
Jarvis Dialogue Manager (Genesis-022 Sprint-004)

Manages pending questions and slot filling for multi-turn conversations.

The DialogueManager receives:
    - raw user input
    - ConversationState  (what the conversation knows right now)
    - ConversationPolicy (confidence thresholds)

and produces a DialogueResult — never modifying state directly.
The pipeline stage that calls the DialogueManager decides what to do
with the result and updates state accordingly.

Design constraints:
    - Completely deterministic. No AI, no fuzzy matching.
    - Never modifies ConversationState directly.
    - Always preserves original input.
    - All thresholds from ConversationPolicy.
    - DialogueType gives downstream components a clean typed signal.

DialogueType signal:
    ANSWER_PENDING   — this input answers a pending question
    FILL_SLOT        — this input fills a named slot
    CONTINUE         — conversation continues normally (no pending)
    TOPIC_CHANGE     — detected topic change mid-conversation
    NEW_CONVERSATION — no context, fresh start
    ACKNOWLEDGEMENT  — short acknowledgement ("ok", "sure", "yes", "no")
    UNKNOWN          — dialogue type cannot be determined

Slot filling:
    The manager tracks which slots are pending and matches user input
    to the most appropriate open slot. It never fills slots itself —
    it returns a DialogueResult indicating what should be filled,
    and the pipeline stage applies the fill to ConversationState.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.conversation.conversation_state import ConversationState
    from core.conversation.conversation_policy import ConversationPolicy

from core.conversation.conversation_models import Slot, SlotStatus


# ---------------------------------------------------------------------------
# DialogueType
# ---------------------------------------------------------------------------

class DialogueType(Enum):
    """
    The type of dialogue act the current input represents.

    Used by Recovery, Pipeline, and Router stages to understand
    what the Dialogue Manager concluded without relying on booleans
    or string comparisons.
    """
    ANSWER_PENDING   = auto()  # input answers a pending question
    FILL_SLOT        = auto()  # input fills a named open slot
    CONTINUE         = auto()  # normal continuation, no pending state
    TOPIC_CHANGE     = auto()  # user changed topic mid-conversation
    NEW_CONVERSATION = auto()  # no context, fresh start detected
    ACKNOWLEDGEMENT  = auto()  # short ack: "ok", "sure", "yes", "no", "got it"
    UNKNOWN          = auto()  # cannot determine dialogue type

    def label(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def is_slot_related(self) -> bool:
        """True if this type involves slot filling."""
        return self in (DialogueType.ANSWER_PENDING, DialogueType.FILL_SLOT)

    @property
    def is_continuation(self) -> bool:
        """True if the conversation continues in its current thread."""
        return self in (
            DialogueType.CONTINUE,
            DialogueType.ACKNOWLEDGEMENT,
            DialogueType.ANSWER_PENDING,
            DialogueType.FILL_SLOT,
        )


# ---------------------------------------------------------------------------
# DialogueResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DialogueResult:
    """
    The result of a single dialogue analysis.

    Immutable. Produced by DialogueManager.analyse().
    Pipeline stages read this and decide how to update ConversationState.

    Attributes:
        dialogue_type:    What kind of dialogue act this input represents.
        original_input:   The user's exact input — never modified.
        slot_name:        Name of the slot being filled (if any).
        slot_value:       Value to fill into the slot (if any).
        pending_question: The pending question this answers (if any).
        confidence:       Manager confidence in this classification.
        reason:           Human-readable explanation.
        is_acknowledgement: True if input is a short ack with no content.
    """
    dialogue_type:    DialogueType
    original_input:   str
    slot_name:        Optional[str]  = None
    slot_value:       Optional[str]  = None
    pending_question: Optional[str]  = None
    confidence:       float          = 1.0
    reason:           str            = ""
    is_acknowledgement: bool         = False

    @classmethod
    def continue_normally(cls, original: str, reason: str = "") -> "DialogueResult":
        """Convenience: normal continuation, nothing special."""
        return cls(
            dialogue_type=DialogueType.CONTINUE,
            original_input=original,
            confidence=1.0,
            reason=reason or "No pending state. Continuing normally.",
        )

    @classmethod
    def unknown(cls, original: str, reason: str = "") -> "DialogueResult":
        """Convenience: cannot determine dialogue type."""
        return cls(
            dialogue_type=DialogueType.UNKNOWN,
            original_input=original,
            confidence=0.0,
            reason=reason or "Dialogue type could not be determined.",
        )

    def __str__(self) -> str:
        if self.slot_name:
            return (
                f"DialogueResult({self.dialogue_type.label()}, "
                f"slot={self.slot_name!r}={self.slot_value!r})"
            )
        return f"DialogueResult({self.dialogue_type.label()}, conf={self.confidence:.2f})"


# ---------------------------------------------------------------------------
# Acknowledgement patterns
# ---------------------------------------------------------------------------

_ACK_PATTERNS = re.compile(
    r"^(ok|okay|sure|yes|yeah|yep|no|nope|nah|got it|understood|"
    r"alright|all right|fine|noted|roger|copy that|correct|right|"
    r"absolutely|definitely|of course|certainly|agreed|thanks|"
    r"thank you|cheers|good|great|perfect|excellent|sounds good|"
    r"makes sense|i see|i understand|i get it)[\s\.\!\?]*$",
    re.IGNORECASE,
)

# Topic change markers
_TOPIC_CHANGE_PATTERNS = re.compile(
    r"\b(actually|wait|never mind|forget that|forget it|let'?s change|"
    r"different question|another question|switch to|let'?s talk about|"
    r"moving on|one more thing|quick question|by the way|btw)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# DialogueManager
# ---------------------------------------------------------------------------

class DialogueManager:
    """
    Analyses user input in the context of pending questions and slots.

    Never modifies ConversationState. Always returns a DialogueResult.
    All threshold decisions are delegated to ConversationPolicy.

    Public API:
        analyse(raw_input, state, policy) → DialogueResult
        is_acknowledgement(raw_input)     → bool
        has_topic_change(raw_input)       → bool
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        raw_input: str,
        state: "ConversationState",
        policy: "ConversationPolicy",
    ) -> DialogueResult:
        """
        Analyse the user's input in dialogue context.

        Priority order:
            1. Empty / whitespace → UNKNOWN
            2. Acknowledgement detection
            3. Topic change detection
            4. Pending question answer
            5. Open slot fill
            6. Fresh start detection
            7. Normal continuation

        Args:
            raw_input: The user's message (after reference resolution).
            state:     Current conversation state (read-only).
            policy:    Conversation policy for threshold decisions.

        Returns:
            DialogueResult describing the dialogue act.
        """
        # 1. Empty input
        if not raw_input or not raw_input.strip():
            return DialogueResult.unknown(
                raw_input or "",
                "Empty input — dialogue type cannot be determined.",
            )

        stripped = raw_input.strip()

        # 2. Acknowledgement — short confirmations with no content
        if self.is_acknowledgement(stripped):
            return DialogueResult(
                dialogue_type=DialogueType.ACKNOWLEDGEMENT,
                original_input=raw_input,
                confidence=0.95,
                reason=f"Input {stripped!r} is a conversational acknowledgement.",
                is_acknowledgement=True,
            )

        # 3. Topic change
        if self.has_topic_change(stripped):
            return DialogueResult(
                dialogue_type=DialogueType.TOPIC_CHANGE,
                original_input=raw_input,
                confidence=0.85,
                reason="Topic change marker detected in input.",
            )

        # 4. Pending question — this input is the answer
        if state.has_pending():
            pending = state.pending_slot
            if pending is not None:
                value = self._extract_slot_value(stripped)
                return DialogueResult(
                    dialogue_type=DialogueType.ANSWER_PENDING,
                    original_input=raw_input,
                    slot_name=pending.name,
                    slot_value=value,
                    pending_question=pending.question,
                    confidence=0.90,
                    reason=(
                        f"Input answers pending question for slot "
                        f"{pending.name!r}: {pending.question!r}"
                    ),
                )

        # 5. Open slot fill — check if any active slot can be filled
        active = state.active_slots()
        if active:
            matched = self._match_slot(stripped, active)
            if matched is not None:
                slot, value = matched
                return DialogueResult(
                    dialogue_type=DialogueType.FILL_SLOT,
                    original_input=raw_input,
                    slot_name=slot.name,
                    slot_value=value,
                    confidence=0.80,
                    reason=f"Input fills open slot {slot.name!r}.",
                )

        # 6. Fresh start — no context at all
        if self._is_fresh_start(state):
            return DialogueResult(
                dialogue_type=DialogueType.NEW_CONVERSATION,
                original_input=raw_input,
                confidence=0.70,
                reason="No conversation context found. Treating as new conversation.",
            )

        # 7. Normal continuation
        return DialogueResult.continue_normally(raw_input)

    def is_acknowledgement(self, raw_input: str) -> bool:
        """
        Return True if the input is a short acknowledgement with no content.

        Used to distinguish "ok" / "yes" / "got it" from actual answers
        that happen to start with those words.
        """
        if not raw_input or not raw_input.strip():
            return False
        return bool(_ACK_PATTERNS.match(raw_input.strip()))

    def has_topic_change(self, raw_input: str) -> bool:
        """
        Return True if the input contains a topic-change marker.

        Examples: "actually", "never mind", "different question",
        "let's talk about something else".
        """
        if not raw_input or not raw_input.strip():
            return False
        return bool(_TOPIC_CHANGE_PATTERNS.search(raw_input.strip()))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_slot_value(self, text: str) -> str:
        """
        Extract the meaningful value from a slot answer.

        Strips common filler phrases and returns the core content.
        e.g. "My name is Claude" → "Claude"
             "It's blue" → "blue"
             "Blue" → "Blue"
        """
        # Strip common prefixes
        patterns = [
            re.compile(r"^(?:my (?:name|answer|response) is|it'?s|it is|"
                       r"i'?m|i am|the answer is|yes it'?s|that'?s)\s+",
                       re.IGNORECASE),
        ]
        result = text.strip()
        for pattern in patterns:
            result = pattern.sub("", result).strip()
        return result.rstrip(".,!?").strip() or text.strip()

    def _match_slot(
        self, text: str, active_slots: list[Slot]
    ) -> Optional[tuple[Slot, str]]:
        """
        Try to match input text to one of the active slots.

        Returns (slot, value) if a match is found, None otherwise.
        Currently uses a simple heuristic: if there is exactly one
        active slot, the entire input is the value for that slot.
        Multiple active slots require explicit slot name matching
        (future sprint).
        """
        if len(active_slots) == 1:
            return (active_slots[0], self._extract_slot_value(text))

        # Multiple slots: try to find one whose name appears in the text
        text_lower = text.lower()
        for slot in active_slots:
            if slot.name.lower().replace("_", " ") in text_lower:
                return (slot, self._extract_slot_value(text))

        return None

    def _is_fresh_start(self, state: "ConversationState") -> bool:
        """
        Return True if there is no conversation context at all.

        A fresh start has: no topic, no turns, no references, no slots.
        """
        return (
            state.current_topic is None
            and state.turn_count == 0
            and state.references.current_it is None
            and state.references.current_person is None
            and state.references.current_project is None
            and not state.active_slots()
        )