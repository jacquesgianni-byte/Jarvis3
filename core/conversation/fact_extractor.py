"""
Jarvis Conversation Memory â€” Fact Extractor (Genesis-020 Sprint-001)

Deterministic pattern-based extraction of facts from natural language.

Constitutional constraints:
    - No LLM calls. All extraction is deterministic regex.
    - No external services.
    - Returns structured ExtractedFact objects only.
    - Never modifies any storage directly.

Extraction targets:
    - Projects:      "I'm building Jarvis", "we're working on Genesis-020"
    - Milestones:    "we finished Engineering Academy", "Genesis-019 is frozen"
    - People:        "Claude is my senior engineer", "GPT handles specs"
    - Current tasks: "we're starting Genesis-020", "I'm starting sprint 001"
    - Decisions:     "we decided to use Flask", "I chose to use Tavily"
    - Achievements:  "we completed 529 tests", "Genesis-019 passed"
    - Possessions:   "I have 2 dogs", "Their names are Rex and Tom"
    - Workplace:     "I work at Academy of Healthcare"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum, auto
from typing import Optional


class FactType(Enum):
    PROJECT     = auto()   # ongoing project or work
    MILESTONE   = auto()   # completed or frozen milestone
    PERSON      = auto()   # named person and their role/relationship
    TASK        = auto()   # current or upcoming task
    DECISION    = auto()   # a decision made
    ACHIEVEMENT = auto()   # something completed or accomplished
    PREFERENCE  = auto()   # a stated preference or like/dislike
    PET         = auto()   # a pet or animal owned
    WORKPLACE   = auto()   # where the user works
    EVENT       = auto()   # user-world event: implicit, time-bounded
    UNKNOWN     = auto()   # could not be classified


@dataclass(frozen=True)
class ExtractedFact:
    """A single fact extracted from a user message."""
    fact_type:  FactType
    subject:    str          # who/what the fact is about ("user", "claude", "jarvis")
    attribute:  str          # the property ("current project", "role", "milestone")
    value:      str          # the value ("Jarvis OS", "senior engineer", "Genesis-019")
    confidence: float = 0.8  # extraction confidence (0.0â€“1.0)
    raw:        str = ""     # original text that triggered extraction
    extracted_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    metadata:   dict = field(default_factory=dict)  # supplementary data (e.g. temporal_ctx)


# ---------------------------------------------------------------------------
# Extraction patterns
# Each tuple: (regex, handler_name)
# Handlers return Optional[ExtractedFact]
# ---------------------------------------------------------------------------

_PROJECT_PATTERNS = [
    re.compile(r"\bi(?:'m| am) (?:building|working on|developing|creating|making)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'re| are) (?:building|working on|developing|creating|making)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bmy (?:project|app|system|platform|tool)\s+is\s+(.+)", re.IGNORECASE),
    re.compile(r"\bour (?:project|app|system|platform|tool)\s+is\s+(.+)", re.IGNORECASE),
]

_MILESTONE_PATTERNS = [
    re.compile(r"\bwe(?:'ve| have)?\s+(?:just\s+)?(?:finished|completed|frozen?|shipped|released)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'ve| have)\s+(?:just\s+)?(?:finished|completed|frozen?|shipped|released)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(.+?)\s+is\s+(?:done|complete|finished|frozen|locked)", re.IGNORECASE),
    re.compile(r"\b(genesis[- ]?[\d\.]+)\s+(?:is\s+)?(?:done|complete|finished|frozen|locked|passed)", re.IGNORECASE),
    re.compile(r"\btoday\s+we\s+(?:finished|completed|shipped)\s+(.+)", re.IGNORECASE),
]

_PERSON_PATTERNS = [
    # "Claude is my senior engineer" â†’ person=Claude, role=senior engineer
    re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+is\s+my\s+(.+)", re.IGNORECASE),
    # "my senior engineer is Claude" â€” value extracted separately for proper-noun guard
    re.compile(r"\bmy\s+(.+?)\s+is\s+(\S+(?:\s+\S+)?)", re.IGNORECASE),
    # "GPT handles specs" â†’ person=GPT, role=handles specs
    re.compile(r"\b(GPT|ChatGPT|Claude|Anthropic|OpenAI)\s+(?:handles|manages|does|owns)\s+(.+)", re.IGNORECASE),
]

# Words that look like proper nouns (Title Case) but are not person/place names.
_NON_NAME_WORDS: frozenset[str] = frozenset({
    # colours
    "blue", "red", "green", "yellow", "black", "white", "purple", "orange",
    "pink", "brown", "grey", "gray", "violet", "indigo",
    # foods / drinks
    "pizza", "pasta", "sushi", "coffee", "tea", "water", "beer", "wine",
    "cake", "bread", "rice", "fish", "meat", "soup",
    # sports
    "football", "tennis", "basketball", "cricket", "rugby", "golf",
    "swimming", "running", "cycling",
    # generic adjectives / values
    "small", "large", "medium", "good", "great", "fine", "okay", "ok",
    "true", "false", "yes", "no", "maybe",
})

_PROPER_NOUN_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$")


def _is_proper_noun(value: str) -> bool:
    """
    Return True if *value* looks like a person or place name.

    Requires Title Case AND exclusion from the known non-name vocabulary.
    """
    if not _PROPER_NOUN_RE.match(value.strip()):
        return False
    return value.strip().lower() not in _NON_NAME_WORDS

# Phrases that look like person names when extracted as subjects but are
# actually preference attributes. Guards _extract_people() subject slot.
# GC-003: prevents "My favourite drink is coffee" creating a person record
# with subject="favourite drink". Uses prefix match so both "favourite X"
# and "favorite X" spellings are covered without listing every variant.
_PREFERENCE_SUBJECT_PREFIXES: tuple[str, ...] = (
    "favourite ", "favorite ",
)


def _is_preference_subject(name: str) -> bool:
    """Return True if name looks like a preference attribute, not a person."""
    lower = name.lower().strip()
    return any(lower.startswith(prefix) for prefix in _PREFERENCE_SUBJECT_PREFIXES)


_TASK_PATTERNS = [
    re.compile(r"\bwe(?:'re| are) (?:starting|beginning|kicking off|about to start)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'m| am) (?:starting|beginning|kicking off|about to start)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bnext(?:\s+up)?\s+(?:is\s+)?(.+)", re.IGNORECASE),
    re.compile(r"\bstarting\s+(genesis[- ]?[\d\.]+)", re.IGNORECASE),
]

_DECISION_PATTERNS = [
    re.compile(r"\bwe\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'ve| have)\s+decided\s+to\s+(.+)", re.IGNORECASE),
    re.compile(r"\bthe\s+decision\s+is\s+(.+)", re.IGNORECASE),
    re.compile(r"\bwe(?:'re| are)\s+going\s+to\s+use\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi\s+chose\s+(?:to\s+use\s+)?(.+)", re.IGNORECASE),
]

_ACHIEVEMENT_PATTERNS = [
    re.compile(r"\bwe(?:'ve| have)\s+(?:built|implemented|created|added|written)\s+(.+)", re.IGNORECASE),
    re.compile(r"\bi(?:'ve| have)\s+(?:built|implemented|created|added|written)\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+tests?\s+(?:are\s+)?(?:passing|passed|green)", re.IGNORECASE),
]

_POSSESSION_PATTERNS = [
    # "I have 2 dogs" / "I have a cat" / "I've got three fish"
    re.compile(r"\bi(?:'ve| have| got|'ve got)\s+(\d+|a|an|some|two|three|four|five)\s+([a-z]+)", re.IGNORECASE),
    # "Their names are Rex and Tom" / "His name is Rex"
    re.compile(r"\b(?:their|his|her|its)\s+names?\s+are?\s+(.+)", re.IGNORECASE),
]

_WORKPLACE_PATTERNS = [
    # "I work at Academy of Healthcare"
    re.compile(r"\bi\s+work\s+at\s+(.+)", re.IGNORECASE),
    # "I work for Google"
    re.compile(r"\bi\s+work\s+for\s+(.+)", re.IGNORECASE),
    # "I am employed at / by X"
    re.compile(r"\bi(?:'m| am)\s+employed\s+(?:at|by)\s+(.+)", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# EVENT detection — structural patterns, no verb vocabulary
# TemporalParser is the single authority on temporal expressions.
# ---------------------------------------------------------------------------

_EVENT_FIRST_PERSON_RE = re.compile(r"\b(?:i|we)\b", re.IGNORECASE)

_EVENT_PAST_FORM_RE = re.compile(
    r"\b\w+ed\b"
    r"|"
    r"\b(?:was|were|had|got|felt|became|seemed)\b"
    r"|"
    r"\b(?:was|were|am|is|are|i'm)\s+\w+ing\b",
    re.IGNORECASE,
)

_EVENT_INTENT_MODAL_RE = re.compile(
    r"\b(?:need|want|have|plan|going|intend|hope|expect|"
    r"try|must|should|will|shall)\s+to\b",
    re.IGNORECASE,
)

# Explicit memory/command verbs at sentence start — handled by MemorySkill, not EVENT
_EVENT_COMMAND_RE = re.compile(
    r"^\s*(?:remember|note|save|store|forget|tell|show|find|get|set|remind)\b",
    re.IGNORECASE,
)

# Noise words that indicate an extraction isn't useful
_NOISE_VALUES = {
    "it", "that", "this", "them", "something", "anything",
    "everything", "nothing", "a lot", "more", "some", "the",
    "me", "you", "us", "we", "i", "my", "your",
}


def _clean_value(value: str) -> str:
    """Strip trailing punctuation and whitespace from an extracted value."""
    return value.strip().rstrip(".,;:!?").strip()


def _is_noise(value: str) -> bool:
    """Return True if the extracted value is too generic to be useful."""
    cleaned = value.lower().strip()
    return len(cleaned) < 2 or cleaned in _NOISE_VALUES


class FactExtractor:
    """
    Deterministic fact extractor for natural language conversation.

    Applies ordered regex patterns to extract structured facts.
    Returns a list of ExtractedFact objects â€” never modifies storage.

    Designed to be called on every user message in the conversation.
    Fast enough for synchronous use (no I/O, no LLM, pure regex).
    """

    def __init__(self, temporal_parser=None) -> None:
        """Optional TemporalParser injection for EVENT extraction.
        When None (default), EVENT extraction disabled.
        """
        self._temporal_parser = temporal_parser

    # Interrogative words that signal a question rather than a statement.
    _QUESTION_START = re.compile(
        r"^\s*(?:what|who|where|when|why|how|which|whose|whom|is|are|do|does|"
        r"did|can|could|would|should|shall|will|have|has|had)\b",
        re.IGNORECASE,
    )
    _QUESTION_END = re.compile(r"\?\s*$")

    def extract(self, text: str) -> list[ExtractedFact]:
        """
        Extract all facts from a single text message.

        Args:
            text: The user's message.

        Returns:
            A list of ExtractedFact objects. May be empty.
        """
        if not text or not text.strip():
            return []

        stripped = text.strip()
        if self._QUESTION_END.search(stripped):
            return []
        if self._QUESTION_START.match(stripped):
            return []

        facts: list[ExtractedFact] = []

        facts.extend(self._extract_projects(text))
        facts.extend(self._extract_milestones(text))
        facts.extend(self._extract_people(text))
        facts.extend(self._extract_tasks(text))
        facts.extend(self._extract_decisions(text))
        facts.extend(self._extract_achievements(text))
        facts.extend(self._extract_possessions(text))
        facts.extend(self._extract_workplace(text))
        facts.extend(self._extract_events(text))  # EVENT memory

        # Deduplicate by (attribute, value)
        seen: set[tuple[str, str]] = set()
        unique: list[ExtractedFact] = []
        for fact in facts:
            key = (fact.attribute.lower(), fact.value.lower())
            if key not in seen:
                seen.add(key)
                unique.append(fact)

        return unique

    # ------------------------------------------------------------------
    # Extraction methods
    # ------------------------------------------------------------------

    def _extract_projects(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _PROJECT_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.PROJECT,
                        subject="user",
                        attribute="current project",
                        value=value,
                        confidence=0.85,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_milestones(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _MILESTONE_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.MILESTONE,
                        subject="user",
                        attribute="last milestone",
                        value=value,
                        confidence=0.80,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_people(self, text: str) -> list[ExtractedFact]:
        facts = []
        seen_roles: set[tuple[str, str]] = set()
        for idx, pattern in enumerate(_PERSON_PATTERNS):
            m = pattern.search(text)
            if m:
                name = _clean_value(m.group(1))
                role = _clean_value(m.group(2))

                if idx == 1 and not _is_proper_noun(role):
                    continue

                if not _is_noise(name) and not _is_noise(role) and not _is_preference_subject(name):
                    key = (name.lower(), role.lower())
                    if key in seen_roles:
                        continue
                    seen_roles.add(key)
                    facts.append(ExtractedFact(
                        fact_type=FactType.PERSON,
                        subject=name.lower(),
                        attribute="role",
                        value=role,
                        confidence=0.85,
                        raw=text,
                    ))
                    facts.append(ExtractedFact(
                        fact_type=FactType.PERSON,
                        subject="user",
                        attribute=f"{name.lower()} role",
                        value=role,
                        confidence=0.85,
                        raw=text,
                    ))
        return facts

    def _extract_tasks(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _TASK_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.TASK,
                        subject="user",
                        attribute="current task",
                        value=value,
                        confidence=0.80,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_decisions(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _DECISION_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.DECISION,
                        subject="user",
                        attribute="recent decision",
                        value=value,
                        confidence=0.75,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_achievements(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _ACHIEVEMENT_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.ACHIEVEMENT,
                        subject="user",
                        attribute="recent achievement",
                        value=value,
                        confidence=0.75,
                        raw=text,
                    ))
                    break
        return facts

    def _extract_possessions(self, text: str) -> list[ExtractedFact]:
        """
        CV-001 Fix (Genesis-026): Possession extraction disabled.

        Previously extracted "I have 2 dogs" -> attribute="pets" and
        "Their names are..." -> attribute="pet names", but this caused
        ontology corruption for non-animal entities (servers, cars, children)
        because the patterns hardcoded "pets" regardless of noun.

        SlotCompletionEngine (Genesis-025) handles all group declaration and
        slot fill detection correctly at Step 4 before post-turn.
        FactExtractor must not duplicate that work with legacy hardcoded keys.

        Returning an empty list preserves the call site in extract() unchanged.
        _POSSESSION_PATTERNS are retained for reference but no longer used.
        """
        return []


    def _extract_events(self, text: str) -> list[ExtractedFact]:
        """Detect implicit user-world events using structural grammar signals.

        No verb vocabulary. TemporalParser is the single authority.

        Required:
            (a) First-person subject: I or we
            (b) Temporal expression detected by TemporalParser
        Excluded:
            Questions, commands, intent/modal (need to / want to / going to)
        Confidence:
            0.75 if past verb form also present (stronger signal)
            0.65 if temporal expression alone (e.g. irregular past: met, saw)

        Past verb form is a confidence booster, not a gate. TemporalParser
        finding an expression is the authoritative signal.
        Returns [] when temporal_parser is None (all existing callers).
        """
        if self._temporal_parser is None:
            return []
        if self._QUESTION_END.search(text):
            return []
        if self._QUESTION_START.match(text):
            return []
        if _EVENT_INTENT_MODAL_RE.search(text):
            return []
        if _EVENT_COMMAND_RE.match(text):
            return []  # Explicit command — handled by MemorySkill, not EVENT
        if not _EVENT_FIRST_PERSON_RE.search(text):
            return []
        # TemporalParser is the authority — call it before checking past form
        from datetime import date as _date
        ctx = self._temporal_parser.parse(text, _date.today())
        if ctx is None or not ctx.expression:
            return []  # No temporal signal — not an event worth storing
        # Past verb form boosts confidence but is not required
        # (covers irregular past: met, saw, had, went — not ending in -ed)
        has_past = bool(_EVENT_PAST_FORM_RE.search(text))
        confidence = 0.75 if has_past else 0.65
        _STOP = frozenset({
            "i", "we", "a", "an", "the", "my", "our", "and", "or", "to",
            "for", "of", "in", "on", "at", "with", "this", "that", "it",
            "was", "were", "am", "is", "are", "be", "been", "had", "have",
            "has", "did", "do", "just", "very", "really", "so", "then",
        })
        words = re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split()
        key_words = [w for w in words if w not in _STOP and len(w) >= 3]
        key = " ".join(key_words[:3]) or text.strip()[:30].lower()
        clause = text.strip().rstrip(".")
        return [ExtractedFact(
            fact_type=FactType.EVENT,
            subject="user",
            attribute=key,
            value=clause,
            confidence=confidence,
            raw=text,
            metadata={"temporal_ctx": ctx.to_metadata()},
        )]

    def _extract_workplace(self, text: str) -> list[ExtractedFact]:
        facts = []
        for pattern in _WORKPLACE_PATTERNS:
            m = pattern.search(text)
            if m:
                value = _clean_value(m.group(1))
                if not _is_noise(value):
                    facts.append(ExtractedFact(
                        fact_type=FactType.WORKPLACE,
                        subject="user",
                        attribute="workplace",
                        value=value,
                        confidence=0.85,
                        raw=text,
                    ))
                    break
        return facts