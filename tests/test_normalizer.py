"""
Normalizer regression suite (added after the 2026-07-10 word-corruption
defect). Guards two properties:

  1. Valid English words are NEVER corrupted from the inside.
  2. The intended corrections (typos, spacing, slang) still work.

Runs standalone: python tests/test_normalizer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.understanding.normalizer import Normalizer

n = Normalizer()
passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


print("\n[1] Valid words survive intact (the 2026-07-10 defect)")
check("'your' not corrupted",
      n.normalize("what is your name?") == "what is your name?")
check("'colour' not corrupted",
      n.normalize("what is my colour?") == "what is my colour?")
check("'favourite colour' normalises spelling only, no corruption",
      n.normalize("my favourite colour is blue") == "my favorite colour is blue")
check("'purpose' not corrupted",
      n.normalize("what is your purpose?") == "what is your purpose?")
check("'saturday' / 'turn' / 'burger' not corrupted",
      n.normalize("Turn on the burger timer Saturday")
      == "turn on the burger timer saturday")

print("\n[2] Intended corrections still work")
check("slang: 'ur' -> 'your'",
      n.normalize("whats ur name") == "whats your name")
check("typo: 'rember'/'remeber' -> 'remember'",
      n.normalize("rember my colour is blue") == "remember my colour is blue"
      and n.normalize("remeber this") == "remember this")
check("spacing: 'goodmorning' -> 'good morning'",
      n.normalize("goodmorning jarvis") == "good morning jarvis")
check("'fav' -> 'favorite' as a whole word only",
      n.normalize("my fav team is Carlton") == "my favorite team is carlton")
check("lowercase + strip preserved",
      n.normalize("  HELLO  ") == "hello")

print(f"\nNORMALIZER SUITE: ALL {passed} CHECKS PASS")