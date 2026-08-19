"""
Temporal Recall Engine (Genesis-031 Sprint-002)

Answers temporal queries ("When did I start my job?") by looking up
temporal metadata stored in KnowledgeEngine memory records.

Responsibilities:
    - Detect "when did I X?" query patterns
    - Search KnowledgeEngine for matching memories
    - Extract resolved_date from record metadata
    - Return a natural language answer

Design constraints:
    - No AI calls
    - No new storage -- reads from KnowledgeEngine only
    - KnowledgeEngine remains single source of truth
    - TemporalParser never called here -- metadata was set at store time

Architecture position:
    Agent._route()
        -> TemporalRecallEngine.detect_query(text)
        -> TemporalRecallEngine.answer(query, knowledge)
        -> KnowledgeEngine.search_memory()
        -> Response

Genesis-031 Sprint-002.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.knowledge_engine.engine import KnowledgeEngine
    from core.conversation.temporal_parser import TemporalParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query patterns
# ---------------------------------------------------------------------------

_WHEN_PATTERNS: list[re.Pattern] = [
    # "When did I move?" / "When did I start?" -- single verb
    re.compile(r"\bwhen\s+did\s+i\s+\w+\??$", re.IGNORECASE),
    # "When did I start my job?" / "When did I buy my car?"
    re.compile(r"\bwhen\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "When was I ..."
    re.compile(r"\bwhen\s+was\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "What day did I ..."
    re.compile(r"\bwhat\s+day\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "What date did I ..."
    re.compile(r"\bwhat\s+date\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),
    # "What did I do last Saturday?" / "What did I finish last night?"
    re.compile(r"\bwhat\s+did\s+i\s+(.+?)\??$", re.IGNORECASE),  # EVENT recall
]

# Keywords to extract from the query for memory search
_KEYWORD_STRIP = re.compile(
    r"\b(?:when|did|i|my|a|an|the|was|what|day|date)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TemporalQuery:
    """A detected temporal query."""
    raw_text:    str
    search_hint: str   # Keywords to search memory for


@dataclass(frozen=True)
class TemporalAnswer:
    """Result of answering a temporal query."""
    found:       bool
    answer:      str
    memory_value: Optional[str] = None
    resolved_date: Optional[str] = None


class TemporalRecallEngine:
    """
    Answers when-did-I and what-did-I queries from temporal metadata in KnowledgeEngine.

    KnowledgeEngine injected at call time.
    TemporalParser optionally injected for date-tag fallback retrieval.

    Public API:
        detect_query(text) -> Optional[TemporalQuery]
        answer(query, knowledge) -> TemporalAnswer
    """

    def __init__(self, temporal_parser=None) -> None:
        """Optional TemporalParser for date-tag fallback in answer().
        When None: date-tag fallback disabled (backward compatible).
        Single TemporalParser authority Ã¢â‚¬â€ never construct a parser internally.
        """
        self._temporal_parser = temporal_parser

    def detect_query(self, text: str) -> Optional[TemporalQuery]:
        """
        Detect a temporal query in the user's message.

        Args:
            text: The user's raw message.

        Returns:
            TemporalQuery if a when-query is detected, else None.
        """
        if not text or not text.strip():
            return None

        for pattern in _WHEN_PATTERNS:
            if pattern.search(text):
                hint = self._extract_search_hint(text)
                if hint:
                    logger.debug("[TEMPORAL_RECALL] Query detected: %r hint=%r", text[:40], hint)
                    return TemporalQuery(raw_text=text, search_hint=hint)

        return None

    def answer(
        self,
        query: TemporalQuery,
        knowledge: "KnowledgeEngine",
    ) -> TemporalAnswer:
        """
        Answer a temporal query from KnowledgeEngine records.

        Searches for memories matching the query hint, then looks for
        temporal metadata (resolved_date) in the record's metadata field.

        Args:
            query:     A TemporalQuery from detect_query().
            knowledge: The KnowledgeEngine instance to search.

        Returns:
            TemporalAnswer with a natural language response.
        """
        # PRIMARY PATH: Genesis-052 Sprint-002 — exact tag search via list_by_tag().
        # resolved_date is a hard constraint, not a relevance hint.
        # list_by_tag() delegates to the repository's exact tag filter — deterministic.
        # subject='user' filter excludes journal records.
        results = []
        _query_date_tag: str | None = None  # carried into fallback guard below
        if self._temporal_parser is not None:
            from datetime import date as _date
            _ctx = self._temporal_parser.parse(query.raw_text, _date.today())
            if _ctx is not None and _ctx.resolved_date is not None:
                _query_date_tag = f"resolved:{_ctx.resolved_date.isoformat()}"
                if hasattr(knowledge, "list_by_tag"):
                    results = knowledge.list_by_tag(_query_date_tag, subject="user")
                else:
                    # Graceful fallback for test doubles that lack list_by_tag
                    _candidates = knowledge.search_memory(query=_query_date_tag, subject="user", limit=20)
                    results = [r for r in _candidates if _query_date_tag in getattr(r, "tags", [])]
                if results:
                    logger.info("[TEMPORAL_RECALL] Date-tag exact: %s -> %d results", _query_date_tag, len(results))

        # SECONDARY PATH: keyword search — only when no resolved date was found
        # OR exact search returned nothing (event not yet stored for that date).
        # Genesis-052 Sprint-002: if a resolved date was established, every
        # fallback result is filtered to that date — Saturday cannot leak into
        # a Sunday answer.
        def _matches_query_date(record) -> bool:
            """Return True if record carries _query_date_tag (or no date constraint exists)."""
            if _query_date_tag is None:
                return True  # no date constraint — all records are eligible
            return _query_date_tag in getattr(record, "tags", [])

        if not results:
            _candidates = knowledge.search_memory(query=query.search_hint, subject="user", limit=10)
            results = [r for r in _candidates if _matches_query_date(r)]
        if not results:
            _candidates = knowledge.search_memory(query=query.search_hint, limit=10)
            results = [r for r in _candidates if _matches_query_date(r)]
        if not results:
            _seen_ids = set(); _accumulated = []
            for keyword in query.search_hint.split():
                if len(keyword) >= 3:
                    for _r in knowledge.search_memory(query=keyword, limit=10):
                        if not _matches_query_date(_r):
                            continue
                        _rid = getattr(_r, "event_id", id(_r))
                        if _rid not in _seen_ids:
                            _seen_ids.add(_rid); _accumulated.append(_r)
            results = _accumulated

        # Genesis-049: Collect ALL user records matching the resolved date.
        # Do not return on first match — a day may have multiple activities.
        # Order by time-of-day slot (chronological), then importance.
        _TOD_ORDER = {"morning": 0, "afternoon": 1, "evening": 2, "night": 3, "unspecified": 4}

        _matched = []  # list of (record, resolved_date, temporal_expr, tod_slot)
        for record in results:
            if getattr(record, "subject", None) != "user":
                continue  # only user memories qualify as temporal answers
            metadata = getattr(record, "metadata", None) or {}
            resolved_date    = metadata.get("resolved_date")
            temporal_expr    = metadata.get("temporal_expression")
            time_of_day_slot = metadata.get("time_of_day_slot", "unspecified")
            if not resolved_date:
                for tag in getattr(record, "tags", []):
                    if tag.startswith("resolved:"):
                        resolved_date = tag[len("resolved:"):]
                    elif tag.startswith("expr:"):
                        temporal_expr = tag[len("expr:"):]
                    elif tag.startswith("tod:"):
                        time_of_day_slot = tag[len("tod:"):]
            if resolved_date:
                _matched.append((record, resolved_date, temporal_expr, time_of_day_slot))

        if not _matched:
            return TemporalAnswer(
                found=False,
                answer="I don't have a specific date recorded for that.",
            )

        # Sort: tod slot order first, then importance descending
        _matched.sort(key=lambda x: (
            _TOD_ORDER.get(x[3], 4),
            -(getattr(x[0], "importance", 0.5) or 0.5),
        ))

        if len(_matched) == 1:
            # Single record — use existing _format_answer path
            r, rd, te, tod = _matched[0]
            logger.info("[TEMPORAL_RECALL] Found: value=%r date=%r", r.value, rd)
            return TemporalAnswer(
                found=True,
                answer=self._format_answer(r.value, rd, te, tod),
                memory_value=r.value,
                resolved_date=rd,
            )

        # Multiple records — compose a natural multi-event answer
        logger.info("[TEMPORAL_RECALL] Multi-event: %d records for %s", len(_matched), _matched[0][1])
        answer_text = self._compose_multi_answer(_matched)
        return TemporalAnswer(
            found=True,
            answer=answer_text,
            memory_value="; ".join(r.value for r, *_ in _matched[:3]),
            resolved_date=_matched[0][1],
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compose_multi_answer(self, matched: list) -> str:
        """
        Genesis-051 Sprint-001: Compose a historical answer from multiple memory records.

        Path B fix: never replay stale relative temporal expressions.
        Reconstructs temporal context from resolved: and tod: metadata.

        Rules:
        - Prefer record.value as natural-language body, stripping:
            (a) first-person prefix ("I ", "we ")
            (b) the resolved temporal expression (expr: tag) from the tail
        - Fall back to record.attribute only when safe stripping fails.
        - Never output "this morning", "yesterday", etc. in a historical answer.
        - Handle mixed tod: slots correctly — no shared header when slots differ.
        - Cap at 3 records; overflow note for 4+.

        matched: sorted list of (record, resolved_date, temporal_expr, tod_slot).
        """
        import re as _re

        _SLOT_LABELS = {
            "morning": "morning",
            "afternoon": "afternoon",
            "evening": "evening",
            "night": "night",
        }

        _cap = 3
        _overflow = max(0, len(matched) - _cap)
        _display = matched[:_cap]

        # Collect unique resolved dates and tod slots across display records.
        _dates = [rd for _, rd, _, _ in _display]
        _slots = [tod for _, _, _, tod in _display]
        _unique_dates = list(dict.fromkeys(_dates))   # order-preserving dedupe
        _unique_slots = list(dict.fromkeys(_slots))

        _same_date = len(_unique_dates) == 1
        _same_slot = len(_unique_slots) == 1 and _unique_slots[0] != "unspecified"

        # ------------------------------------------------------------------
        # Build per-record phrase: value with first-person prefix + temporal
        # tail removed.  Falls back to record.attribute on failure.
        # ------------------------------------------------------------------
        def _clean_phrase(record, temporal_expr: str) -> str:
            value = record.value.strip().rstrip(".")
            # Strip leading first-person subject.
            value = _re.sub(r"^(?:i|we)\s+", "", value, flags=_re.IGNORECASE)
            # Strip resolved temporal expression from the tail (case-insensitive,
            # ignore punctuation boundaries).
            if temporal_expr:
                escaped = _re.escape(temporal_expr.strip())
                # Match expression optionally preceded by a preposition/space
                # at or near the end of the value.
                tail_pattern = _re.compile(
                    r"\s+(?:this|last|that\s+)?" + escaped + r"\s*$",
                    _re.IGNORECASE,
                )
                stripped = tail_pattern.sub("", value).strip()
                if stripped and stripped.lower() != value.lower():
                    value = stripped
                else:
                    # Expression not found as a simple tail — try anywhere in value.
                    anywhere = _re.compile(
                        r"\s*" + escaped + r"\s*",
                        _re.IGNORECASE,
                    )
                    candidate = anywhere.sub(" ", value).strip().rstrip(",;")
                    if candidate and len(candidate) >= 3:
                        value = candidate
                    else:
                        # Safe strip failed — use attribute as degraded fallback.
                        attr = getattr(record, "attribute", "")
                        if attr and attr.strip():
                            return attr.strip()
            return value.strip().rstrip(".,;") if value.strip() else getattr(record, "attribute", "event")

        phrases = [_clean_phrase(r, te) for r, _, te, _ in _display]

        # ------------------------------------------------------------------
        # Build temporal header.
        # Same date + same slot  → one shared header ("On Saturday morning, …")
        # Same date + mixed slot → per-record headers inline
        # Mixed dates            → per-record headers inline
        # ------------------------------------------------------------------
        if _same_date and _same_slot:
            # Shared header path: single date + single tod slot.
            try:
                from datetime import date as _date
                d = _date.fromisoformat(_unique_dates[0])
                day_name = d.strftime("%A")            # e.g. "Saturday"
            except (ValueError, TypeError):
                day_name = _unique_dates[0]

            slot_label = _SLOT_LABELS.get(_unique_slots[0], "")
            header = f"On {day_name} {slot_label}".strip() if slot_label else f"On {day_name}"

            # Compose body list.
            if len(phrases) == 1:
                body = phrases[0]
            elif len(phrases) == 2:
                body = f"{phrases[0]} and {phrases[1]}"
            else:
                body = f"{phrases[0]}, {phrases[1]}, and {phrases[2]}"
            body = body[0].lower() + body[1:] if body else body
            result = f"{header}, you {body}."

        elif _same_date:
            # Same date but mixed/absent tod slots.
            try:
                from datetime import date as _date
                d = _date.fromisoformat(_unique_dates[0])
                day_name = d.strftime("%A, %d %B %Y")
            except (ValueError, TypeError):
                day_name = _unique_dates[0]

            # Attach per-record slot label where available.
            labelled = []
            for phrase, (_, _, _, tod) in zip(phrases, _display):
                slot = _SLOT_LABELS.get(tod, "")
                labelled.append(f"{phrase} ({slot})" if slot else phrase)

            if len(labelled) == 1:
                body = labelled[0]
            elif len(labelled) == 2:
                body = f"{labelled[0]} and {labelled[1]}"
            else:
                body = f"{labelled[0]}, {labelled[1]}, and {labelled[2]}"
            body = body[0].upper() + body[1:] if body else body
            result = f"On {day_name}, you {body[0].lower() + body[1:]}."

        else:
            # Mixed dates — each event gets its own inline date context.
            parts = []
            for phrase, (_, rd, _, tod) in zip(phrases, _display):
                try:
                    from datetime import date as _date
                    d = _date.fromisoformat(rd)
                    day_str = d.strftime("%A, %d %B %Y")
                except (ValueError, TypeError):
                    day_str = rd
                slot = _SLOT_LABELS.get(tod, "")
                when = f"{day_str} {slot}".strip() if slot else day_str
                parts.append(f"{phrase} (on {when})")

            if len(parts) == 1:
                body = parts[0]
            elif len(parts) == 2:
                body = f"{parts[0]} and {parts[1]}"
            else:
                body = f"{parts[0]}, {parts[1]}, and {parts[2]}"
            body = body[0].upper() + body[1:] if body else body
            result = f"You {body}."

        if _overflow > 0:
            more = "thing" if _overflow == 1 else "things"
            result += f" I have {_overflow} more {more} from that time if you'd like the full list."

        return result

    def _extract_search_hint(self, text: str) -> str:
        """
        Extract meaningful keywords from a temporal query for memory search.

        "When did I start my new job?" -> "start new job"
        "When did I buy my car?" -> "buy car"
        "When did I move?" -> "move"
        """
        stripped = _KEYWORD_STRIP.sub(" ", text)
        stripped = re.sub(r"[?!.,]", " ", stripped)
        words = [w for w in stripped.split() if len(w) >= 2]
        return " ".join(words[:5])

    def _format_answer(
        self,
        memory_value: str,
        resolved_date: str,
        original_expression: Optional[str],
        time_of_day_slot: str = "unspecified",  # Genesis-047 Sprint-003
    ) -> str:
        """
        Format a natural language answer from a memory record.

        Genesis-052 Sprint-003: memory_value is now included in the answer.
        Previously the method accepted memory_value but discarded it, producing
        date-only responses such as "That was on Sunday, 16 August 2026 (last sunday)."

        The fix applies the same light cleaning used by _compose_multi_answer:
          - strip leading first-person prefix ("I " / "we ")
          - strip the resolved temporal expression from the tail
          - compose naturally: "On {date}, you {event}."

        Falls back to date-only when memory_value is empty or cleaning fails.

        Args:
            memory_value:        The stored fact ("I finished the shed last Sunday")
            resolved_date:       ISO date string ("2026-08-16")
            original_expression: The original temporal phrase ("last sunday")
            time_of_day_slot:    Structured sub-day slot from metadata.
                                 Genesis-047 Sprint-003.

        Returns:
            A natural language answer string.
        """
        import re as _re

        try:
            d = date.fromisoformat(resolved_date)
            date_str = d.strftime("%A, %d %B %Y")  # e.g. "Sunday, 16 August 2026"
        except (ValueError, TypeError):
            date_str = resolved_date

        _SLOT_LABELS = {
            "morning":   "morning",
            "afternoon": "afternoon",
            "evening":   "evening",
            "night":     "night",
        }
        slot_label = _SLOT_LABELS.get(time_of_day_slot)

        # ------------------------------------------------------------------
        # Clean memory_value: strip first-person prefix + temporal tail.
        # Mirrors _clean_phrase() logic from _compose_multi_answer().
        # ------------------------------------------------------------------
        def _clean(value: str, expr: Optional[str]) -> str:
            value = value.strip().rstrip(".")
            # Strip leading first-person subject ("I " / "we ")
            value = _re.sub(r"^(?:i|we)\s+", "", value, flags=_re.IGNORECASE)
            # Strip resolved temporal expression from the tail
            if expr:
                escaped = _re.escape(expr.strip())
                tail_re = _re.compile(
                    r"\s+(?:this|last|that\s+)?" + escaped + r"\s*$",
                    _re.IGNORECASE,
                )
                stripped = tail_re.sub("", value).strip()
                if stripped and stripped.lower() != value.lower():
                    value = stripped
            return value.strip() if value.strip() else ""

        cleaned = _clean(memory_value, original_expression) if memory_value else ""

        # ------------------------------------------------------------------
        # Compose answer — include event content when available.
        # ------------------------------------------------------------------
        if cleaned:
            if slot_label:
                return f"On {date_str} {slot_label}, you {cleaned}."
            return f"On {date_str}, you {cleaned}."

        # Fallback: no usable event content — date only (preserves prior behaviour)
        if slot_label:
            return f"That was on {date_str} {slot_label}."
        if original_expression:
            return f"That was on {date_str} ({original_expression})."
        return f"That was on {date_str}."
