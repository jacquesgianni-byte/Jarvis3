"""
Reverse Entity Parser (Genesis-026 Sprint-003)

Parses natural language queries into structured ReverseLookupRequest objects.

Responsibilities:
    - Detect queries that ask about a specific entity member by name/identifier
    - Extract the queried member tokens from the raw text
    - Return a ReverseLookupRequest for ContextualRecallEngine to act on

Design constraints:
    - No reasoning. No KnowledgeEngine access. No SessionContext.
    - Stateless — same input → same output.
    - Token-based extraction only — does NOT classify whether tokens are
      "proper names". Members can be Rex, staging, db01, GPU-7, printer3.
    - Parser evolves independently of the reasoning engine.

Architecture position:
    Agent._route()
        └── ReverseEntityParser.parse()   ← this module
                └── ReverseLookupRequest  (passed to ContextualRecallEngine)

Genesis-026 Sprint-003.
"""

from __future__ import annotations

import re
from typing import Optional

from core.conversation.contextual_recall_engine import ReverseLookupRequest


# ---------------------------------------------------------------------------
# Trigger patterns
#
# Each pattern captures the member token(s) after the trigger word.
# Group 1 is always the raw member string (may contain commas / "and").
#
# Design: patterns are intentionally broad — they capture any non-trivial
# token, not just human-style names. "Who is staging?" and "Who is Rex?"
# are treated identically.
# ---------------------------------------------------------------------------

_REVERSE_PATTERNS: list[re.Pattern] = [
    # "Who is Rex?" / "Who is staging?" / "Who is VM-03?"
    re.compile(
        r"\bwho\s+is\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "Who are Rex and Tom?" / "Who are prod and staging?"
    re.compile(
        r"\bwho\s+are\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "What is staging?" / "What is GPU-7?"
    re.compile(
        r"\bwhat\s+is\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "Tell me about Rex." / "Tell me about staging."
    re.compile(
        r"\btell\s+me\s+about\s+(.+?)(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Do you know Rex?" / "Do you remember staging?"
    re.compile(
        r"\bdo\s+you\s+(?:know|remember)\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
    # "Remind me who Rex is." / "Remind me what staging is."
    re.compile(
        r"\bremind\s+me\s+(?:who|what)\s+(.+?)\s+is(?:\.|$)",
        re.IGNORECASE,
    ),
    # "Which one is Rex?" / "Which one is db01?"
    re.compile(
        r"\bwhich\s+one\s+is\s+(.+?)(?:\?|$)",
        re.IGNORECASE,
    ),
]

# Tokens that should never be treated as member identifiers.
# These are common function words that appear after trigger verbs.
# Kept minimal — we want to accept identifiers like "staging", "prod", "db01".
_STOP_TOKENS: frozenset[str] = frozenset({
    "they", "them", "those", "it", "that", "this",
    "he", "she", "we", "you", "i",
    "my", "your", "their", "our",
    "a", "an", "the",
})

# Separator pattern for splitting "Rex and Tom" or "Rex, Tom and Max"
_MEMBER_SEPARATOR = re.compile(
    r"\s*,\s*(?:and\s+)?|\s+and\s+",
    re.IGNORECASE,
)


class ReverseEntityParser:
    """
    Parses "Who is X?" style queries into ReverseLookupRequest objects.

    Stateless. No dependencies. Called by the Agent before delegating
    to ContextualRecallEngine.reverse_lookup().

    Public API:
        parse(query) -> Optional[ReverseLookupRequest]
    """

    def parse(self, query: str) -> Optional[ReverseLookupRequest]:
        """
        Parse a raw query into a ReverseLookupRequest.

        Returns None if the query does not match any reverse lookup pattern,
        or if no valid member tokens can be extracted.

        Args:
            query: The user's raw message.

        Returns:
            ReverseLookupRequest with extracted member list, or None.
        """
        if not query or not query.strip():
            return None

        for pattern in _REVERSE_PATTERNS:
            m = pattern.search(query.strip())
            if not m:
                continue

            raw_capture = m.group(1).strip().rstrip(".?!")
            members = self._extract_members(raw_capture)

            if not members:
                continue

            return ReverseLookupRequest(members=members)

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_members(self, raw: str) -> list[str]:
        """
        Split a raw capture string into individual member tokens.

        Filters out stop tokens and empty strings.
        Preserves identifiers like "staging", "VM-03", "GPU-7", "printer3".

        Args:
            raw: The raw captured string, e.g. "Rex and Tom" or "staging".

        Returns:
            List of member token strings (lowercased for lookup consistency).
        """
        tokens = _MEMBER_SEPARATOR.split(raw)
        members = []
        for token in tokens:
            token = token.strip().rstrip(".?!")
            if not token:
                continue
            if token.lower() in _STOP_TOKENS:
                continue
            if len(token) < 1:
                continue
            members.append(token)
        return members