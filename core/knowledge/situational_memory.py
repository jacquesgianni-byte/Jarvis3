"""
Situational Memory Store -- Genesis-073 Sprint-001

Foundation A: Jarvis-owned persistent situational memory.

Provides:
    MemoryEntry               -- the unit of situational knowledge
    SituationalMemoryStore    -- append/overwrite store backed by entries.json
    MemoryExtractionPipeline  -- LLM-powered extraction of MemoryEntry records
                                 from conversation text

Five initial category hypotheses:
    decision    -- something Gianni has decided
    question    -- something raised but not yet resolved
    constraint  -- a limit or boundary that must be respected
    intention   -- something Gianni intends to do
    unresolved  -- something important that does not fit the above

Design rules:
    * entries.json is the single store -- one flat list of MemoryEntry dicts
    * Correction semantics: PATCH overwrites by id (active flag preserved)
    * Deactivation: set active=False, never delete
    * Extraction: AnthropicProvider.ask() via injected ai_client
    * No background threads, no scheduled triggers
    * requires_approval=True on all mutations (Chief governance)
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CATEGORIES = frozenset({"fact", "decision", "question", "constraint", "intention", "unresolved"})

_EXTRACTION_SYSTEM = (
    "You are a memory extraction pipeline for a personal AI operating system. "
    "Your only job is to identify durable situational facts from conversation text "
    "and return them as a JSON array. "
    "Extract only facts that are likely to matter in a future session. "
    "Do not extract small talk, greetings, transient details, or general knowledge. "
    "IMPORTANT — category definitions:\n"
    "  fact       = a stable truth about the person or their world that provides "
    "contextual grounding (name, family, relationships, preferences, location, "
    "background). NOT a rule — something true about the world.\n"
    "  decision   = something the person has decided or committed to.\n"
    "  constraint = a rule, limit, or boundary that must be respected. "
    "NOT a biographical fact — a constraint governs behaviour.\n"
    "  intention  = something the person intends or plans to do.\n"
    "  question   = something raised but not yet resolved.\n"
    "  unresolved = something important that does not fit the above categories.\n"
    "IMPORTANT — splitting: if a statement contains more than one distinct memory, "
    "return each as a separate JSON object. Do not merge two memories into one entry.\n"
    "IMPORTANT — privacy: do NOT extract sensitive health, medical, financial, or "
    "deeply personal information (e.g. diagnoses, mental health, income, trauma) "
    "unless the user has explicitly asked for it to be remembered.\n"
    "Reply with ONLY a JSON array -- no preamble, no explanation, no markdown fences."
)

_EXTRACTION_PROMPT_TEMPLATE = (
    "Extract durable situational memory entries from the following conversation text.\n\n"
    "For each entry produce a JSON object with these exact fields:\n"
    '  \"category\": one of [\"fact\", \"decision\", \"question\", \"constraint\", \"intention\", \"unresolved\"]\n'
    '  \"content\":  a concise, self-contained statement (one or two sentences max)\n\n"'
    "Return a JSON array. If nothing durable is found, return an empty array [].\n\n"
    "Conversation text:\n{text}"
)


# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------

@dataclass
class MemoryEntry:
    id: str
    category: str        # one of VALID_CATEGORIES
    content: str
    timestamp: str       # ISO-8601 UTC
    active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryEntry":
        return cls(
            id=d["id"],
            category=d["category"],
            content=d["content"],
            timestamp=d["timestamp"],
            active=d.get("active", True),
        )

    @classmethod
    def create(cls, category: str, content: str) -> "MemoryEntry":
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Unknown category {category!r}. Valid: {sorted(VALID_CATEGORIES)}"
            )
        return cls(
            id=str(uuid.uuid4()),
            category=category,
            content=content.strip(),
            timestamp=datetime.now(timezone.utc).isoformat(),
            active=True,
        )


# ---------------------------------------------------------------------------
# SituationalMemoryStore
# ---------------------------------------------------------------------------

class SituationalMemoryStore:
    """
    Append/overwrite store backed by data/situational_memory/entries.json.

    Thread safety: single-process Flask server; no locking required.
    """

    def __init__(self, data_root: Path) -> None:
        self._dir = data_root / "situational_memory"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "entries.json"
        logger.info("[MEMORY] SituationalMemoryStore at %s", self._path)

    # ------------------------------------------------------------------
    # Core read/write
    # ------------------------------------------------------------------

    def _load(self) -> List[MemoryEntry]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [MemoryEntry.from_dict(d) for d in raw]
        except Exception as e:
            logger.error("[MEMORY] Failed to load entries.json: %s", e)
            return []

    def _save(self, entries: List[MemoryEntry]) -> None:
        try:
            self._path.write_text(
                json.dumps([e.to_dict() for e in entries], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("[MEMORY] Failed to save entries.json: %s", e)
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, entry: MemoryEntry) -> MemoryEntry:
        """Append a new entry. Returns the stored entry."""
        entries = self._load()
        entries.append(entry)
        self._save(entries)
        logger.info("[MEMORY] Stored entry id=%s category=%s", entry.id[:8], entry.category)
        return entry

    def get_all(
        self, category: Optional[str] = None, active_only: bool = True
    ) -> List[MemoryEntry]:
        """Return entries, optionally filtered by category and/or active flag."""
        entries = self._load()
        if active_only:
            entries = [e for e in entries if e.active]
        if category:
            entries = [e for e in entries if e.category == category]
        return entries

    def get_by_id(self, entry_id: str) -> Optional[MemoryEntry]:
        """Return a single entry by id, or None."""
        for e in self._load():
            if e.id == entry_id:
                return e
        return None

    def correct(
        self,
        entry_id: str,
        category: Optional[str],
        content: Optional[str],
    ) -> Optional[MemoryEntry]:
        """
        Overwrite category and/or content for an existing entry.
        Returns the updated entry, or None if not found.
        Correction semantics: active flag is preserved.
        """
        entries = self._load()
        for i, e in enumerate(entries):
            if e.id == entry_id:
                if category is not None:
                    if category not in VALID_CATEGORIES:
                        raise ValueError(f"Unknown category {category!r}")
                    e.category = category
                if content is not None:
                    e.content = content.strip()
                entries[i] = e
                self._save(entries)
                logger.info("[MEMORY] Corrected entry id=%s", entry_id[:8])
                return e
        return None

    def deactivate(self, entry_id: str) -> bool:
        """Set active=False for an entry. Returns True if found."""
        entries = self._load()
        for i, e in enumerate(entries):
            if e.id == entry_id:
                e.active = False
                entries[i] = e
                self._save(entries)
                return True
        return False


# ---------------------------------------------------------------------------
# MemoryExtractionPipeline
# ---------------------------------------------------------------------------

class MemoryExtractionPipeline:
    """
    Extract MemoryEntry records from conversation text via AnthropicProvider.

    ai_client: anything with an ask(prompt: str) -> Response interface.
               Accepts None (returns empty list -- safe for tests without API key).
    """

    def __init__(self, ai_client=None) -> None:
        self._ai = ai_client

    def extract(self, text: str) -> List[MemoryEntry]:
        """
        Run extraction on text. Returns list of MemoryEntry (unsaved).
        Never raises -- returns [] on any failure.
        """
        if not text or not text.strip():
            return []
        if self._ai is None:
            logger.warning("[MEMORY] No AI client -- extraction skipped.")
            return []

        prompt = _EXTRACTION_PROMPT_TEMPLATE.format(text=text.strip())
        full_prompt = _EXTRACTION_SYSTEM + "\n\n" + prompt

        try:
            response = self._ai.ask(full_prompt)
        except Exception as e:
            logger.error("[MEMORY] AI call failed during extraction: %s", e)
            return []

        if not getattr(response, "success", False):
            logger.warning("[MEMORY] AI extraction returned failure response.")
            return []

        raw = getattr(response, "message", "") or ""
        return self._parse(raw)

    def _parse(self, raw: str) -> List[MemoryEntry]:
        """Parse JSON array from AI response. Silently drops malformed entries."""
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning("[MEMORY] Extraction parse failed: %s | raw=%r", e, raw[:200])
            return []

        if not isinstance(data, list):
            logger.warning("[MEMORY] Extraction response is not a list: %r", type(data))
            return []

        entries = []
        for item in data:
            try:
                category = item.get("category", "").strip()
                content  = item.get("content", "").strip()
                if not category or not content:
                    continue
                entry = MemoryEntry.create(category=category, content=content)
                entries.append(entry)
            except (ValueError, AttributeError) as e:
                logger.warning(
                    "[MEMORY] Skipping malformed extraction item: %s | item=%r", e, item
                )

        logger.info("[MEMORY] Extraction produced %d entries.", len(entries))
        return entries
