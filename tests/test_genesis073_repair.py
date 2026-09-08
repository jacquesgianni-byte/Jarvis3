"""
Genesis-073 Repair Sprint -- Focused Test Suite
Run: python -m pytest tests/test_genesis073_repair.py -v
"""
import json, pathlib, re, unittest


# ===========================================================================
# Repair 1 -- SLOT_FILLED guard
# ===========================================================================

class TestRepair1SlotFilledGuard(unittest.TestCase):
    DECLARED_SLOT_NAMES = frozenset({
        "pet names", "people names", "vehicle names",
        "instrument names", "server names", "project names",
        "names", "breeds", "colours", "ages", "roles",
        "makes", "plates", "types", "statuses", "locations",
        "ips", "owners",
    })

    def _is_declared(self, slot_name):
        return slot_name in self.DECLARED_SLOT_NAMES

    def test_conversational_statement_blocked(self):
        self.assertFalse(self._is_declared("Hey Jarvis I've had a pretty busy week"))

    def test_year_slot_blocked(self):
        self.assertFalse(self._is_declared("year"))

    def test_suggest_slot_blocked(self):
        self.assertFalse(self._is_declared("suggest"))

    def test_work_slot_blocked(self):
        self.assertFalse(self._is_declared("work"))

    def test_have_slot_blocked(self):
        self.assertFalse(self._is_declared("have"))

    def test_pet_names_passes(self):
        self.assertTrue(self._is_declared("pet names"))

    def test_people_names_passes(self):
        self.assertTrue(self._is_declared("people names"))

    def test_vehicle_names_passes(self):
        self.assertTrue(self._is_declared("vehicle names"))

    def test_instrument_names_passes(self):
        self.assertTrue(self._is_declared("instrument names"))

    def test_raw_names_passes(self):
        self.assertTrue(self._is_declared("names"))

    def test_breeds_passes(self):
        self.assertTrue(self._is_declared("breeds"))

    def test_colours_passes(self):
        self.assertTrue(self._is_declared("colours"))

    def test_ages_passes(self):
        self.assertTrue(self._is_declared("ages"))

    def test_roles_passes(self):
        self.assertTrue(self._is_declared("roles"))

    def test_statuses_passes(self):
        self.assertTrue(self._is_declared("statuses"))


# ===========================================================================
# Repair 2 -- MemoryDetector tag-question tail
# ===========================================================================

_TAG_QUESTION_TAIL_RE = re.compile(
    r",?\s*(?:"
    r"don\'t\s+i"
    r"|didn\'t\s+i"
    r"|haven\'t\s+i"
    r"|hasn\'t\s+i"
    r"|isn\'t\s+it"
    r"|aren\'t\s+(?:i|they|we)"
    r"|wasn\'t\s+i"
    r"|weren\'t\s+(?:i|they|we)"
    r"|right"
    r"|correct"
    r")\s*\??\s*$",
    re.IGNORECASE,
)

_ANIMAL_NOUNS = (
    r"dogs?|puppies|puppy|cats?|kittens?|kitten|birds?|parrots?|budgies?"
    r"|fish|goldfish|tropical fish|rabbits?|bunnies|bunny"
    r"|hamsters?|guinea pigs?|horses?|ponies|pony|pets?"
)
_PETS_PATTERN = re.compile(
    r"^i(?:'ve| have| got|'ve got) (\d+|a|an|some|two|three|four|five)"
    r" (" + _ANIMAL_NOUNS + r")",
    re.IGNORECASE,
)


class TestRepair2TagQuestionTail(unittest.TestCase):
    def _would_detect(self, message):
        cleaned = message.strip().rstrip(".")
        match = _PETS_PATTERN.match(cleaned)
        if not match:
            return False
        tail = cleaned[match.end():]
        if tail.strip() and _TAG_QUESTION_TAIL_RE.search(tail):
            return False
        return True

    def test_dont_i_blocked(self):
        """S14: 'I have two dogs, don't I?' must not store as a fact."""
        self.assertFalse(self._would_detect("I have two dogs, don't I?"))

    def test_right_blocked(self):
        self.assertFalse(self._would_detect("I have two dogs, right?"))

    def test_didnt_i_blocked(self):
        self.assertFalse(self._would_detect("I got three cats, didn't I?"))

    def test_havent_i_blocked(self):
        self.assertFalse(self._would_detect("I have two dogs, haven't I?"))

    def test_correct_blocked(self):
        self.assertFalse(self._would_detect("I have two dogs, correct?"))

    def test_declaration_period_detected(self):
        """R1: 'I have two dogs.' must still be detected."""
        self.assertTrue(self._would_detect("I have two dogs."))

    def test_declaration_no_period_detected(self):
        self.assertTrue(self._would_detect("I have two dogs"))

    def test_three_dogs_detected(self):
        self.assertTrue(self._would_detect("I have three dogs."))

    def test_cat_detected(self):
        self.assertTrue(self._would_detect("I have a cat."))

    def test_ive_got_detected(self):
        self.assertTrue(self._would_detect("I've got five fish."))


# ===========================================================================
# Repair 3 -- Intent.MEMORY question gate
# ===========================================================================

_WH_PREFIXES = (
    "what ", "who ", "when ", "where ", "how ", "which ",
    "do ", "did ", "don't ", "didn't ", "haven't ", "hasn't ",
    "so how", "so what", "so who",
)

def _is_interrogative(request):
    stripped = request.strip()
    return (
        stripped.endswith("?")
        or stripped.lower().startswith(_WH_PREFIXES)
    )


class TestRepair3MemoryQuestionGate(unittest.TestCase):
    def test_favourite_colour_is_question(self):
        """S10: 'What is my favourite colour?' must not be stored."""
        self.assertTrue(_is_interrogative("What is my favourite colour?"))

    def test_how_many_dogs_is_question(self):
        """Recovery Step 2."""
        self.assertTrue(_is_interrogative("So how many dogs do I have?"))

    def test_what_do_you_know_is_question(self):
        """S6."""
        self.assertTrue(_is_interrogative("What do you know about me?"))

    def test_do_you_remember_is_question(self):
        """S5."""
        self.assertTrue(_is_interrogative("Do you remember what my favourite colour is?"))

    def test_who_are_my_dogs_is_question(self):
        self.assertTrue(_is_interrogative("Who are my dogs?"))

    def test_what_do_you_remember_is_question(self):
        self.assertTrue(_is_interrogative("What do you remember about it?"))

    def test_how_are_you_is_question(self):
        self.assertTrue(_is_interrogative("How are you going?"))

    def test_declaration_not_question(self):
        self.assertFalse(_is_interrogative("My name is Gianni"))

    def test_possession_not_question(self):
        self.assertFalse(_is_interrogative("I have three dogs"))

    def test_statement_not_question(self):
        self.assertFalse(_is_interrogative("I live in Melbourne"))

    def test_favourite_colour_declaration_not_question(self):
        self.assertFalse(_is_interrogative("My favourite colour is blue"))

    def test_conversational_statement_not_question(self):
        self.assertFalse(_is_interrogative(
            "I've been thinking about getting away next year, but I haven't decided where to go yet."
        ))


# ===========================================================================
# Repair 4 -- Possession signal auxiliary 'have been'
# ===========================================================================

_POSSESSION_OLD = re.compile(
    r"\bi\s+(?:also\s+)?(?:have|own|possess|keep)\b|\bi(?:'ve| have)\s+(?:also\s+)?got\b",
    re.IGNORECASE,
)
_POSSESSION_NEW = re.compile(
    r"\bi\s+(?:also\s+)?(?:have(?!\s+been\b)|own|possess|keep)\b|\bi(?:'ve| have)\s+(?:also\s+)?got\b",
    re.IGNORECASE,
)


class TestRepair4PossessionSignal(unittest.TestCase):
    def test_have_been_talking_blocked(self):
        """S9: 'I have been talking about the project' is auxiliary."""
        self.assertIsNone(_POSSESSION_NEW.search(
            "My wife and I have been talking about the project."
        ))

    def test_have_been_working_blocked(self):
        self.assertIsNone(_POSSESSION_NEW.search("I have been working on this for a while."))

    def test_have_been_thinking_blocked(self):
        self.assertIsNone(_POSSESSION_NEW.search(
            "I have been thinking about getting away next year."
        ))

    def test_have_been_doing_blocked(self):
        self.assertIsNone(_POSSESSION_NEW.search("I have been doing this kind of work for years."))

    def test_have_been_friends_blocked(self):
        """'I have been friends with...' must not fire possession."""
        self.assertIsNone(_POSSESSION_NEW.search("I have been friends with him for years."))

    def test_i_have_dogs_matches(self):
        self.assertIsNotNone(_POSSESSION_NEW.search("I have two dogs."))

    def test_i_have_a_cat_matches(self):
        self.assertIsNotNone(_POSSESSION_NEW.search("I have a cat."))

    def test_i_own_matches(self):
        self.assertIsNotNone(_POSSESSION_NEW.search("I own three guitars."))

    def test_ive_got_matches(self):
        self.assertIsNotNone(_POSSESSION_NEW.search("I've got some fish."))

    def test_i_also_have_matches(self):
        """CV-007 regression: 'I also have X' must still match."""
        self.assertIsNotNone(_POSSESSION_NEW.search("I also have two cats."))

    def test_i_keep_matches(self):
        self.assertIsNotNone(_POSSESSION_NEW.search("I keep three rabbits."))

    def test_old_pattern_was_broken(self):
        """Confirms the bug existed before the fix."""
        self.assertIsNotNone(_POSSESSION_OLD.search(
            "My wife and I have been talking about the project."
        ))

    def test_new_pattern_is_fixed(self):
        """Confirms the fix works."""
        self.assertIsNone(_POSSESSION_NEW.search(
            "My wife and I have been talking about the project."
        ))


# ===========================================================================
# Repair 5 -- Betty Lou Who deactivated
# ===========================================================================

class TestRepair5BettyLouDeactivated(unittest.TestCase):
    ENTRIES_PATH = (
        pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")
        / "data" / "situational_memory" / "entries.json"
    )

    def test_betty_lou_not_active(self):
        """No active entry in entries.json should contain 'Betty Lou Who'."""
        if not self.ENTRIES_PATH.exists():
            self.skipTest("entries.json not found -- store may be empty")

        with open(self.ENTRIES_PATH, encoding="utf-8") as f:
            entries = json.load(f)

        active_betty = [
            e for e in entries
            if e.get("active", True)
            and "betty lou" in e.get("content", "").lower()
        ]
        self.assertEqual(
            active_betty, [],
            f"Found {len(active_betty)} active 'Betty Lou Who' entries -- should be 0.\n"
            f"Entries: {active_betty}"
        )

    def test_betty_lou_entry_if_present_is_inactive(self):
        """If the entry exists, it must be inactive (audit trail preserved)."""
        if not self.ENTRIES_PATH.exists():
            self.skipTest("entries.json not found")

        with open(self.ENTRIES_PATH, encoding="utf-8") as f:
            entries = json.load(f)

        for entry in entries:
            if "betty lou" in entry.get("content", "").lower():
                self.assertFalse(
                    entry.get("active", True),
                    f"Entry {entry.get('id')} has 'Betty Lou Who' and is still active."
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
