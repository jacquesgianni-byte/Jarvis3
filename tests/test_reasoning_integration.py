"""
Genesis-013 Task 002 — Reasoning integration battery.

End-to-end over the REAL MemorySkill, ReasoningSkill and IntentRouter,
with the Agent's exact escalation logic replicated, against a faithful
fake Knowledge Engine. Verifies the acceptance flow, the memory<->
reasoning priority order, "why?" explainability, and zero regressions.

Runs standalone: python tests/test_reasoning_integration.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.intents import Intent
from core.router import IntentRouter
from core.skills.memory import MemorySkill
from core.skills.reasoning import ReasoningSkill
from core.reasoning.engine import ReasoningEngine


# ---------------------------------------------------------------------------
# Fake Knowledge Engine (fixed G-012/MP-003 semantics) + AI spy
# ---------------------------------------------------------------------------

class Rec:
    def __init__(self, attribute, value, confidence=1.0, source="user"):
        self.attribute = attribute; self.value = value
        self.confidence = confidence; self.source = source
        self.expired = False


class FakeKnowledge:
    def __init__(self):
        self.store = {}

    def store_memory(self, subject, category, attribute, value, **kw):
        a = attribute.lower().strip(); key = (subject, a)
        if key in self.store:
            r = self.store[key]; r.value = value.strip(); r.expired = False
            return r
        self.store[key] = Rec(a, value.strip()); return self.store[key]

    def recall_memory(self, subject, attribute, category=None):
        r = self.store.get((subject, attribute.lower().strip()))
        return None if (r is None or r.expired) else r

    def search_memory(self, query, subject=None, **kw):
        q = query.lower()
        return [r for (s, a), r in self.store.items()
                if not r.expired and (q in a or a in q)]

    def forget_memory(self, subject, attribute, category=None, permanent=False):
        r = self.store.get((subject, attribute.lower().strip()))
        if r is None or r.expired: return False
        r.expired = True; return True


class AISpy:
    """Fails the run loudly if the AI is ever consulted."""
    def ask(self, request):
        raise AssertionError(f"AI WAS CALLED for: {request!r}")


class MiniAgent:
    """Replicates the Agent's _route dispatch + escalation exactly."""

    def __init__(self, rules_dir):
        self.knowledge = FakeKnowledge()
        self.reasoning = ReasoningEngine(self.knowledge, rules_dir=rules_dir)
        self.router = IntentRouter()
        self.memory = MemorySkill(self.knowledge)
        self.reasoning_skill = ReasoningSkill(self.reasoning)
        self.ai = AISpy()
        # ── DEBUG ──────────────────────────────────────────────────────
        from core.skills.reasoning import _DIRECT_PATTERNS
        print("  [DBG] _DIRECT_PATTERNS at runtime:")
        for pat, attr in _DIRECT_PATTERNS:
            print(f"    pattern={pat.pattern!r}  ->  attr={attr!r}")
        print(f"  [DBG] Rule conclusions known to engine: {list(self.reasoning._by_conclusion.keys())}")
        # ───────────────────────────────────────────────────────────────

    def process(self, request):
        intent = self.router.detect(request)
        # ── DEBUG ──────────────────────────────────────────────────────
        print(f"  [DBG] process({request!r})")
        print(f"  [DBG] intent = {intent}")
        # ───────────────────────────────────────────────────────────────

        if intent == Intent.MEMORY:
            response = self.memory.execute(request)
            if response.data and response.data.get("memory_miss"):
                reasoned = self.reasoning_skill.infer_attribute(
                    response.data.get("attribute", "")
                )
                if reasoned is not None:
                    return reasoned
            return response

        if intent == Intent.REASONING:
            # ── DEBUG ──────────────────────────────────────────────────
            print(f"  [DBG] -> REASONING branch entered")
            orig = self.reasoning_skill.infer_attribute
            def _traced(attribute):
                print(f"  [DBG]    infer_attribute({attribute!r})")
                result = orig(attribute)
                print(f"  [DBG]    infer_attribute returned: {result!r}")
                if result: print(f"  [DBG]    message: {result.message!r}")
                return result
            self.reasoning_skill.infer_attribute = _traced
            # ───────────────────────────────────────────────────────────
            return self.reasoning_skill.execute(request)

        if intent == Intent.UNKNOWN:
            # ── DEBUG ──────────────────────────────────────────────────
            print(f"  [DBG] -> UNKNOWN branch — AI SPY ABOUT TO FIRE")
            # ───────────────────────────────────────────────────────────
            return self.ai.ask(request)     # spy raises

        return None                          # other skills, out of scope here


RULES = {
    "sets": {
        "afl_clubs": ["Brisbane Lions", "Carlton", "Collingwood"],
        "australian_places": ["Melbourne", "Officer South", "Sydney"],
    },
    "rules": [
        {"id": "team_implies_sport",
         "if": [{"attribute": "favourite team", "in_set": "afl_clubs"}],
         "then": {"attribute": "favourite sport", "value": "AFL"},
         "confidence": 0.9},
        {"id": "location_implies_country",
         "if": [{"attribute": "location", "in_set": "australian_places"}],
         "then": {"attribute": "country", "value": "Australia"},
         "confidence": 0.85},
        {"id": "country_implies_hemisphere",
         "if": [{"attribute": "country", "equals": "Australia"}],
         "then": {"attribute": "hemisphere", "value": "southern"},
         "confidence": 0.9},
    ],
}

passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "core.json").write_text(json.dumps(RULES), encoding="utf-8")

    # =====================================================================
    print("\n[1] ACCEPTANCE FLOW — the Genesis-013 script")
    agent = MiniAgent(tmp)

    r = agent.memory.remember("favourite team", "Brisbane Lions")
    check("fact stored via Knowledge Engine",
          "Brisbane Lions" in r.message)

    r = agent.process("what sport do i follow?")
    check("routed to REASONING (not AI — spy silent)",
          r is not None and "AFL" in r.message)
    check("answer cites its premise",
          "favourite team" in r.message and "Brisbane Lions" in r.message)
    check("response flagged as reasoned with confidence",
          r.data.get("reasoned") is True
          and abs(r.data["confidence"] - 0.9) < 1e-9)

    r = agent.process("why?")
    check("'why?' explained from the engine's trace",
          "favourite sport" in r.message and "AFL" in r.message
          and "team_implies_sport" in r.message and "90%" in r.message)

    # =====================================================================
    print("\n[2] MEMORY <-> REASONING escalation priority")
    agent = MiniAgent(tmp)
    agent.memory.remember("location", "Officer South")

    r = agent.process("what is my country?")
    check("recall miss escalates to a reasoned conclusion (DERIVED)",
          "Australia" in r.message and r.data.get("reasoned") is True)

    r = agent.process("what is my hemisphere?")
    check("recall miss escalates through a 2-rule chain (CHAINED)",
          "southern" in r.message and r.data["reason_type"] == "chained")

    # Stored fact beats reasoning:
    agent.memory.remember("country", "New Zealand")
    r = agent.process("what is my country?")
    check("stored fact answers first — reasoning never overrides knowledge",
          "New Zealand" in r.message and not r.data.get("reasoned"))

    # Honest miss preserved when reasoning has no path:
    r = agent.process("what is my dog?")
    check("no rule path -> the original honest miss is spoken",
          "don't have your dog" in r.message)

    r = agent.process("why")
    check("'why' explains the most recent conclusion (hemisphere chain)",
          "hemisphere" in r.message and "which I inferred" in r.message)

    # =====================================================================
    print("\n[3] Bulk conclusions")
    agent = MiniAgent(tmp)
    agent.memory.remember("favourite team", "Collingwood")
    agent.memory.remember("location", "Melbourne")
    r = agent.process("what can you conclude about me?")
    check("lists multiple derivations",
          "favourite sport" in r.message and "country" in r.message
          and "hemisphere" in r.message)

    agent2 = MiniAgent(tmp)
    r = agent2.process("what can you infer?")
    check("no facts -> honest 'nothing to conclude yet'",
          "don't have enough" in r.message)

    r = agent2.process("how did you work that out?")
    check("'why' with no prior conclusion answers honestly",
          "haven't concluded" in r.message)

    # =====================================================================
    print("\n[4] Router — new cases + full regression battery")
    router = IntentRouter()
    cases = {
        # New REASONING routing:
        "what sport do i follow?": Intent.REASONING,
        "which sport do I watch?": Intent.REASONING,
        "what can you conclude about me?": Intent.REASONING,
        "what can you infer?": Intent.REASONING,
        "why?": Intent.REASONING,
        "why": Intent.REASONING,
        "how did you work that out?": Intent.REASONING,
        "how do you know that?": Intent.REASONING,
        "explain that": Intent.REASONING,
        "which hemisphere am i in?": Intent.REASONING,
        # Conservative: these must still reach the AI:
        "why is the sky blue?": Intent.UNKNOWN,
        "explain quantum physics": Intent.UNKNOWN,
        "how do you know if milk is off?": Intent.UNKNOWN,
        # G-012 regression battery, unchanged expectations:
        "which weighs more, one kilogram of steel or one kilogram of feathers?": Intent.UNKNOWN,
        "hello": Intent.GREETING,
        "hey jarvis": Intent.GREETING,
        "they said something": Intent.UNKNOWN,
        "what is my name?": Intent.MEMORY,
        "what is your name?": Intent.IDENTITY,
        "who are you": Intent.IDENTITY,
        "what is my colour?": Intent.MEMORY,
        "whats my favourite colour": Intent.MEMORY,
        "what's my favorite color?": Intent.MEMORY,
        "who is my wife?": Intent.MEMORY,
        "do you know my car?": Intent.MEMORY,
        "remember my colour is blue": Intent.MEMORY,
        "forget my colour": Intent.MEMORY,
        "what is my drink?": Intent.MEMORY,
        "what is the capital of france?": Intent.UNKNOWN,
        "what time is it?": Intent.UNKNOWN,
        "tell me a short story?": Intent.UNKNOWN,
        "tool": Intent.TOOL,
        "exit": Intent.EXIT,
        "goodbye": Intent.EXIT,
    }
    failures = [
        (req, router.detect(req), want)
        for req, want in cases.items()
        if router.detect(req) != want
    ]
    for req, got, want in failures:
        print(f"    ROUTER MISMATCH: {req!r} -> {got}, wanted {want}")
    check(f"router battery {len(cases)}/{len(cases)} (13 new + 21 regression)",
          not failures)

    # =====================================================================
    print("\n[5] Memory regression — G-012/MP-003 behaviour unchanged")
    agent = MiniAgent(tmp)
    agent.memory.remember("colour", "black")
    r = agent.process("what is my colour?")
    check("canonical store/recall unchanged",
          "favourite colour is black" in r.message)
    agent.process("forget my colour")
    r = agent.process("what is my colour?")
    check("forget + honest miss unchanged (colour has no rule path)",
          "don't have your favourite colour" in r.message)
    agent.memory.remember("colour", "green")
    r = agent.process("what is my colour?")
    check("re-store after forget unchanged", "green" in r.message)

print(f"\n{'='*60}\nGENESIS-013 TASK 002: ALL {passed} CHECKS PASS\n{'='*60}")