"""
Jarvis Memory Skill

Handles remembering and recalling information.
Single gateway between the Agent and the KnowledgeEngine.

No other module should call the KnowledgeEngine directly.

Genesis-012: this skill's backend moved from the in-memory
MemoryManager (which never persisted anything) to the KnowledgeEngine.
All facts are stored as structured subject/attribute/value records via
the engine's six public methods only — storage is never touched
directly.
"""

import re
import time

from core import telemetry
from core.logger import get_logger
from core.models.response import Response
from core.skills.base import Skill

# All personal facts belong to this subject until multi-user profiles.
_SUBJECT = "user"

# Category for facts stored via this skill.
_CATEGORY = "general"

# Spelling canonicalisation so "favorite color" and "favourite colour"
# resolve to the same stored attribute.
_CANONICAL = {
    "favorite": "favourite",
    "color": "colour",
    "colors": "colours",
}

# Attribute-level canonicalisation (Maintenance Patch 003).
_ATTRIBUTE_CANONICAL = {
    "colour": "favourite colour",
    "drink": "favourite drink",
    "food": "favourite food",
    "sport": "favourite sport",
    "team": "favourite team",
}


def _canonicalise(text: str) -> str:
    """Normalise spelling variants, then collapse bare concepts to
    their canonical attribute."""
    words = text.lower().strip().split()
    joined = " ".join(_CANONICAL.get(w, w) for w in words)
    return _ATTRIBUTE_CANONICAL.get(joined, joined)


# ---------------------------------------------------------------------------
# Acknowledgement templates for new memory types.
# Keys match the canonicalised attribute name stored by MemoryDetector.
# Values are format strings receiving `value` as the only argument.
# Only new types added in GC-001/GC-002 are listed here — existing types
# continue to use the default "I'll remember that your X is Y" phrasing.
# ---------------------------------------------------------------------------
_ACK_TEMPLATES: dict[str, str] = {
    "pets":      "Okay, I'll remember that you have {value}.",
    "pet names": "Okay, I'll remember that your dogs are named {value}.",
    "workplace": "Okay, I'll remember that you work at {value}.",
}

# Recall-question shapes
_RECALL_PATTERN = re.compile(r"\bmy\s+(.+?)\s*\??$", re.IGNORECASE)

# Explicit commands.
_REMEMBER_PATTERN = re.compile(
    r"\bremember\s+(?:that\s+)?(?:my\s+)?(.+?)\s+is\s+(.+?)\s*[.!]*$",
    re.IGNORECASE,
)
_FORGET_PATTERN = re.compile(
    r"\bforget\s+(?:about\s+)?my\s+(.+?)\s*[.!?]*$",
    re.IGNORECASE,
)


class MemorySkill(Skill):
    """
    Handles remembering and recalling information.

    Acts as the single gateway into the KnowledgeEngine. Accepts both
    raw request strings (intent routing) and pre-parsed key/value pairs
    (natural memory detection via MemoryDetector).
    """

    def __init__(self, engine):
        self.engine = engine
        self.logger = get_logger()

        self._lookups = 0
        self._hits = 0
        self._lookup_ms_total = 0.0

    @property
    def name(self) -> str:
        return "memory"

    # ------------------------------------------------------------------
    # Raw request entry point (intent routing)
    # ------------------------------------------------------------------

    def execute(self, request: str) -> Response:
        """
        Execute the memory skill from a raw request string.

        Handles, in order:
            "forget my X"                     -> forget_memory
            "remember (that) my X is Y"       -> store_memory
            "... my X?"  (recall questions)   -> recall ladder
        """
        request = request.strip()

        forget = _FORGET_PATTERN.search(request)
        if forget:
            return self._forget(forget.group(1))

        remember = _REMEMBER_PATTERN.search(request)
        if remember:
            return self.remember(remember.group(1), remember.group(2))

        recall = _RECALL_PATTERN.search(request)
        if recall:
            return self._recall(recall.group(1))

        return Response(
            success=True,
            message="I'm not sure what you want me to remember, sir. "
                    "Try: remember my favourite colour is blue."
        )

    # ------------------------------------------------------------------
    # Pre-parsed entry point (MemoryDetector via the Agent)
    # ------------------------------------------------------------------

    def remember(self, key: str, value: str) -> Response:
        """
        Store a key/value fact via the KnowledgeEngine.

        Produces a natural acknowledgement based on the attribute type.
        New memory types (pets, pet names, workplace) use specific
        templates; all others use the default phrasing.
        """
        attribute = _canonicalise(key)
        value = value.strip().rstrip(".!")

        self.engine.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=attribute,
            value=value,
        )

        # Use a specific acknowledgement template if one exists,
        # otherwise fall back to the default phrasing.
        template = _ACK_TEMPLATES.get(attribute)
        if template:
            message = template.format(value=value)
        else:
            message = f"Okay sir, I'll remember that your {attribute} is {value}."

        return Response(success=True, message=message)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _recall(self, raw_attribute: str) -> Response:
        """
        Answer "what is my X" from the KnowledgeEngine.

        Resolution ladder:
            1. Exact attribute match.
            2. "favourite X" if the user said just "X" (and vice versa).
            3. Ranked search_memory() as the fuzzy fallback.
        """
        attribute = _canonicalise(raw_attribute)
        lookup_started = time.perf_counter()

        # 1. Exact.
        record = self.engine.recall_memory(_SUBJECT, attribute)

        # 2. Favourite-prefix variants.
        if record is None and not attribute.startswith("favourite "):
            record = self.engine.recall_memory(
                _SUBJECT, f"favourite {attribute}"
            )
        if record is None and attribute.startswith("favourite "):
            record = self.engine.recall_memory(
                _SUBJECT, attribute.removeprefix("favourite ")
            )

        # 3. Fuzzy search fallback — canonical records only.
        if record is None:
            results = self.engine.search_memory(attribute, subject=_SUBJECT)
            canonical = [r for r in results if "derived" not in r.tags]
            if canonical:
                record = canonical[0]
            elif results:
                record = None

        self._record_lookup(lookup_started, hit=record is not None)

        if record is None:
            return Response(
                success=True,
                message=f"I don't have your {attribute} stored yet, sir.",
                data={"memory_miss": True, "attribute": attribute},
            )

        return Response(
            success=True,
            message=f"Your {record.attribute} is {record.value}, sir."
        )

    def _record_lookup(self, started: float, hit: bool) -> None:
        """Record one Knowledge Engine lookup and emit telemetry."""
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        self._lookups += 1
        if hit:
            self._hits += 1
        self._lookup_ms_total += elapsed_ms

        telemetry.log_since(
            "knowledge_lookup",
            started,
            result="hit" if hit else "miss",
        )

        misses = self._lookups - self._hits
        hit_rate = 100.0 * self._hits / self._lookups
        avg_ms = self._lookup_ms_total / self._lookups

        self.logger.info(
            "KNOWLEDGE | lookups=%d | hits=%d | misses=%d | "
            "hit_rate=%.1f%% | avg_ms=%.1f | gpt_calls_avoided=%d",
            self._lookups, self._hits, misses, hit_rate, avg_ms,
            self._lookups,
        )

    def _forget(self, raw_attribute: str) -> Response:
        """Forget a fact (soft delete via the engine)."""
        attribute = _canonicalise(raw_attribute)

        candidates = {attribute}
        if attribute.startswith("favourite "):
            candidates.add(attribute.removeprefix("favourite "))
        else:
            candidates.add(f"favourite {attribute}")
        # Remove any legacy derived "<attribute> role" records created by
        # earlier person extraction logic (GC-005 compatibility cleanup).
        candidates.add(f"{attribute} role")

        forgotten = False
        for candidate in candidates:
            if self.engine.forget_memory(_SUBJECT, candidate):
                forgotten = True

        if forgotten:
            return Response(
                success=True,
                message=f"Understood, sir. I've forgotten your {attribute}."
            )

        return Response(
            success=True,
            message=f"I don't have your {attribute} stored, sir."
        )