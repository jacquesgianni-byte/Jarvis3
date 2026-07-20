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

# Category for facts stored via this skill. CategoryLoader falls back
# to "general" for unknown ids, so this is always safe. Refining
# per-key category mapping is future work (needs data/categories.json).
_CATEGORY = "general"

# Spelling canonicalisation so "favorite color" and "favourite colour"
# resolve to the same stored attribute.
_CANONICAL = {
    "favorite": "favourite",
    "color": "colour",
    "colors": "colours",
}

# Attribute-level canonicalisation (Maintenance Patch 003).
# Bare concepts that the MemoryDetector also stores in "favourite X"
# form collapse to ONE canonical attribute, so "my colour is blue" and
# "my favourite colour is blue" reference the same knowledge record.
# The canonical set mirrors the detector's fixed favourite-X patterns.
_ATTRIBUTE_CANONICAL = {
    "colour": "favourite colour",
    "drink": "favourite drink",
    "food": "favourite food",
    "sport": "favourite sport",
    "team": "favourite team",
}


def _canonicalise(text: str) -> str:
    """Normalise spelling variants, then collapse bare concepts to
    their canonical attribute — store, recall and forget all agree."""
    words = text.lower().strip().split()
    joined = " ".join(_CANONICAL.get(w, w) for w in words)
    return _ATTRIBUTE_CANONICAL.get(joined, joined)

# Recall-question shapes: "what is my X", "who is my X", "do you know
# my X", "tell me my X" — the attribute is whatever follows "my".
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
        """
        Args:
            engine: The KnowledgeEngine instance (owned by the Agent).
        """
        self.engine = engine
        self.logger = get_logger()

        # Session lookup statistics (Genesis-012 telemetry).
        # Every recall lookup is a question that previously went to
        # OpenAI, so total lookups == GPT calls avoided.
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

        The single gateway for all memory writes — used both by the
        Agent (natural memory statements) and by explicit remember
        commands. The detector's key becomes the engine attribute; the
        subject is always the user.
        """

        attribute = _canonicalise(key)
        value = value.strip().rstrip(".!")

        self.engine.store_memory(
            subject=_SUBJECT,
            category=_CATEGORY,
            attribute=attribute,
            value=value,
        )

        return Response(
            success=True,
            message=f"Okay sir, I'll remember that your {attribute} is {value}."
        )

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

        A miss answers honestly and locally — no AI call. A wrong or
        invented answer would be worse than an honest "not stored yet".
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
        # Observer-derived records (tagged "derived") are excluded so
        # that a forgotten canonical memory cannot be resurrected by
        # a fuzzy match against an observer artefact (zombie recall).
        # Genesis-024 Sprint-001 fix.
        if record is None:
            results = self.engine.search_memory(attribute, subject=_SUBJECT)
            canonical = [r for r in results if "derived" not in r.tags]
            if canonical:
                record = canonical[0]
            elif results:
                # All matches are derived — treat as a miss to avoid
                # returning stale observer artefacts.
                record = None

        self._record_lookup(lookup_started, hit=record is not None)

        if record is None:
            # The miss carries structured metadata (what missed, and the
            # canonical attribute) so the ORCHESTRATOR can decide whether
            # any other subsystem may fill the gap before this honest
            # answer is spoken. This skill neither knows nor cares who
            # that consumer is. The spoken message itself is unchanged.
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
        """
        Record one Knowledge Engine lookup and emit telemetry.

        Two lines per lookup:
          * A TIMING line (carries req=N via the RequestToken binding):
              TIMING | req=7 | stage=knowledge_lookup | result=hit | 1.2 ms
          * A running KNOWLEDGE summary for the Engineering Console:
              KNOWLEDGE | lookups=5 | hits=4 | misses=1 | hit_rate=80.0% |
              avg_ms=1.3 | gpt_calls_avoided=5

        Every lookup — hit or miss — is a question that previously went
        to OpenAI (see 2026-07-08 logs: "what is my colour?" cost 9s of
        GPT-5), so lookups == GPT calls avoided.
        """

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
        """Forget a fact (soft delete via the engine).

        Forgets the canonical attribute AND its variant form (with and
        without the "favourite " prefix), so legacy pre-canonicalisation
        duplicates die too. DEFECT FIX (MP-003 validation): a zombie
        legacy 'colour' record survived every "forget my colour" because
        forget only ever targeted the canonical record, while the recall
        ladder could still find the zombie.
        """

        attribute = _canonicalise(raw_attribute)

        candidates = {attribute}
        if attribute.startswith("favourite "):
            candidates.add(attribute.removeprefix("favourite "))
        else:
            candidates.add(f"favourite {attribute}")

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