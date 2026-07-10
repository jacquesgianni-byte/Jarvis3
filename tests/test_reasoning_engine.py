"""
Genesis-013 Task 001 — ReasoningEngine test battery.

Covers every area required by the task spec:
rule loading, invalid rule rejection, single-step inference, multi-step
inference, multi-premise inference, confidence propagation, cycle
detection, explanation generation, missing rule path, read-only
behaviour, deterministic repeatability — plus history bounding,
suppression, cap enforcement and the depth limit.

Runs standalone: python tests/test_reasoning_engine.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reasoning.engine import ReasoningEngine, MAX_CHAIN_DEPTH
from core.reasoning.history import InMemoryInferenceHistory
from core.reasoning.models import Outcome, ReasonType
from core.reasoning.rules import RuleLoader


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class Rec:
    def __init__(self, attribute, value, confidence=1.0, source="user"):
        self.attribute = attribute
        self.value = value
        self.confidence = confidence
        self.source = source


class FakeKnowledge:
    """Read-spy Knowledge Engine: raises on ANY write."""

    def __init__(self, facts=None):
        # facts: {attribute: (value, confidence)}
        self._facts = {}
        for attribute, spec in (facts or {}).items():
            value, confidence = spec if isinstance(spec, tuple) else (spec, 1.0)
            self._facts[attribute] = Rec(attribute, value, confidence)
        self.reads = 0

    def recall_memory(self, subject, attribute, category=None):
        self.reads += 1
        return self._facts.get(attribute)

    # -- write methods: forbidden ------------------------------------------
    def _forbidden(self, *a, **k):
        raise AssertionError("READ-ONLY VIOLATION: ReasoningEngine wrote to knowledge!")

    store_memory = _forbidden
    update_memory = _forbidden
    forget_memory = _forbidden


def write_pack(directory, name, payload):
    path = Path(directory) / name
    path.write_text(json.dumps(payload) if isinstance(payload, dict) else payload,
                    encoding="utf-8")
    return path


PACK = {
    "sets": {"afl_clubs": ["Brisbane Lions", "Carlton"]},
    "rules": [
        {"id": "team_implies_sport",
         "if": [{"attribute": "favourite team", "in_set": "afl_clubs"}],
         "then": {"attribute": "followed sport", "value": "AFL"},
         "confidence": 0.9},
        {"id": "location_implies_country",
         "if": [{"attribute": "location", "in_set": "australian_places"}],
         "then": {"attribute": "country", "value": "Australia"},
         "confidence": 0.85},
        {"id": "country_implies_hemisphere",
         "if": [{"attribute": "country", "equals": "Australia"}],
         "then": {"attribute": "hemisphere", "value": "southern"},
         "confidence": 0.9},
        {"id": "team_and_country_implies_local",
         "if": [{"attribute": "favourite team", "in_set": "afl_clubs"},
                {"attribute": "country", "equals": "Australia"}],
         "then": {"attribute": "supporter type", "value": "local AFL supporter"},
         "confidence": 0.8},
    ],
}
PACK2 = {
    "sets": {"australian_places": ["Melbourne", "Officer South"]},
    "rules": [
        {"id": "hemisphere_implies_christmas",
         "if": [{"attribute": "hemisphere", "equals": "southern"}],
         "then": {"attribute": "christmas season", "value": "summer"},
         "confidence": 0.9},
    ],
}

passed = 0


def check(name, condition):
    global passed
    assert condition, f"FAIL: {name}"
    passed += 1
    print(f"  PASS  {name}")


def make_engine(facts, tmp, extra_packs=True):
    write_pack(tmp, "core.json", PACK)
    if extra_packs:
        write_pack(tmp, "extra.json", PACK2)
    return ReasoningEngine(FakeKnowledge(facts), rules_dir=tmp)


# ---------------------------------------------------------------------------
print("\n[1] Rule loading — directory based, multiple packs, cross-file sets")
with tempfile.TemporaryDirectory() as tmp:
    write_pack(tmp, "core.json", PACK)
    write_pack(tmp, "extra.json", PACK2)
    loader = RuleLoader(tmp)
    rules = loader.load()
    check("all 5 rules load across 2 files", len(rules) == 5)
    check("sets merge across files", "australian_places" in loader.sets)
    check("rule in core.json can use set from extra.json",
          any(r.id == "location_implies_country" for r in rules))

print("\n[2] Invalid rule rejection — valid subset survives")
with tempfile.TemporaryDirectory() as tmp:
    bad = {
        "sets": {"ok_set": ["a"]},
        "rules": [
            {"id": "good", "if": [{"attribute": "x", "equals": "a"}],
             "then": {"attribute": "y", "value": "b"}, "confidence": 0.8},
            {"if": [{"attribute": "x", "equals": "a"}],
             "then": {"attribute": "y", "value": "b"}, "confidence": 0.8},          # no id
            {"id": "bad_conf", "if": [{"attribute": "x", "equals": "a"}],
             "then": {"attribute": "y", "value": "b"}, "confidence": 1.5},          # conf > 1
            {"id": "bad_set", "if": [{"attribute": "x", "in_set": "nope"}],
             "then": {"attribute": "y", "value": "b"}, "confidence": 0.8},          # unknown set
            {"id": "no_then", "if": [{"attribute": "x", "equals": "a"}],
             "confidence": 0.8},                                                     # missing then
            {"id": "empty_if", "if": [], "then": {"attribute": "y", "value": "b"},
             "confidence": 0.8},                                                     # empty if
            {"id": "good", "if": [{"attribute": "x", "equals": "a"}],
             "then": {"attribute": "z", "value": "c"}, "confidence": 0.8},          # duplicate id
            {"id": "two_kinds", "if": [{"attribute": "x", "equals": "a", "exists": True}],
             "then": {"attribute": "y", "value": "b"}, "confidence": 0.8},          # ambiguous premise
        ],
    }
    write_pack(tmp, "bad.json", bad)
    write_pack(tmp, "broken.json", "{ this is not json")
    rules = RuleLoader(tmp).load()
    check("exactly the 1 valid rule loads from 9 candidates + broken file",
          len(rules) == 1 and rules[0].id == "good")

print("\n[3] Single-step inference (DERIVED)")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 1.0)}, tmp)
    inf = engine.infer("user", "followed sport")
    check("concludes AFL", inf is not None and inf.value == "AFL")
    check("confidence 0.9 x 1.0 = 0.9", abs(inf.confidence - 0.9) < 1e-9)
    check("reason_type DERIVED", inf.reason_type is ReasonType.DERIVED)
    check("outcome ASSERTED", inf.outcome is Outcome.ASSERTED)
    check("premise snapshot captured",
          inf.premises[0].attribute == "favourite team"
          and inf.premises[0].value == "Brisbane Lions"
          and inf.premises[0].source == "user")

print("\n[4] Chained inference (CHAINED, depth 3) + confidence propagation")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"location": ("Officer South", 1.0)}, tmp)
    inf = engine.infer("user", "christmas season")
    # chain: christmas<-hemisphere<-country<-location = 3 rules
    check("3-rule chain concludes summer christmas",
          inf is not None and inf.value == "summer")
    check("reason_type CHAINED", inf.reason_type is ReasonType.CHAINED)
    check("rule chain recorded outermost-first",
          inf.rule_ids == ("hemisphere_implies_christmas",
                           "country_implies_hemisphere",
                           "location_implies_country"))
    expected = 0.9 * (0.9 * (0.85 * 1.0))    # compounding decay
    check(f"confidence compounds along chain ({expected:.4f})",
          abs(inf.confidence - expected) < 1e-9)
    check("chained premise marked source=inferred",
          inf.premises[0].source == "inferred")

print("\n[5] Depth limit — a 4-rule chain is refused")
with tempfile.TemporaryDirectory() as tmp:
    deep = {"sets": {}, "rules": [
        {"id": f"r{i}", "if": [{"attribute": f"a{i}", "exists": True}],
         "then": {"attribute": f"a{i+1}", "value": "v"}, "confidence": 0.9}
        for i in range(4)      # a0->a1->a2->a3->a4
    ]}
    write_pack(tmp, "deep.json", deep)
    check("sanity: MAX_CHAIN_DEPTH is 3", MAX_CHAIN_DEPTH == 3)
    e3 = ReasoningEngine(FakeKnowledge({"a1": ("v", 1.0)}), rules_dir=tmp)
    check("3-rule chain (a1 stored -> a4) succeeds",
          e3.infer("user", "a4") is not None)
    e4 = ReasoningEngine(FakeKnowledge({"a0": ("v", 1.0)}), rules_dir=tmp)
    check("4-rule chain (a0 stored -> a4) blocked",
          e4.infer("user", "a4") is None)

print("\n[6] Multi-premise (AND semantics)")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 1.0),
                          "country": ("Australia", 1.0)}, tmp)
    inf = engine.infer("user", "supporter type")
    check("both premises stored -> MULTI_PREMISE conclusion",
          inf is not None and inf.reason_type is ReasonType.MULTI_PREMISE
          and len(inf.premises) == 2)
    engine2 = make_engine({"favourite team": ("Brisbane Lions", 1.0),
                           "country": ("New Zealand", 1.0)}, tmp)
    check("contradicting stored fact fails the premise (no chaining past it)",
          engine2.infer("user", "supporter type") is None)

print("\n[7] Multi-premise + chaining, min() propagation")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 0.7),
                          "location": ("Melbourne", 1.0)}, tmp)
    inf = engine.infer("user", "supporter type")
    # country inferred at 0.85; premises min(0.7, 0.85) -> 0.8*0.7=0.56 hedged
    check("weakest premise governs (0.8 x 0.7 = 0.56)",
          inf is not None and abs(inf.confidence - 0.56) < 1e-9)
    check("outcome HEDGED in 0.50-0.74 band", inf.outcome is Outcome.HEDGED)
    check("reason_type CHAINED when any premise inferred",
          inf.reason_type is ReasonType.CHAINED)

print("\n[8] Suppression + confidence cap")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 0.5)}, tmp)
    inf = engine.infer("user", "followed sport")     # 0.9*0.5=0.45 < 0.5
    check("sub-threshold conclusion returns None", inf is None)
    entry = engine.history.recent(1)[0]
    check("suppressed attempt recorded in history",
          entry.outcome is Outcome.SUPPRESSED
          and entry.inference.value == "AFL")
with tempfile.TemporaryDirectory() as tmp:
    capped = {"sets": {}, "rules": [
        {"id": "max_conf", "if": [{"attribute": "x", "exists": True}],
         "then": {"attribute": "y", "value": "v"}, "confidence": 1.0}]}
    write_pack(tmp, "cap.json", capped)
    e = ReasoningEngine(FakeKnowledge({"x": ("v", 1.0)}), rules_dir=tmp)
    check("hard cap: 1.0 x 1.0 still capped at 0.9 — user facts prevail",
          abs(e.infer("user", "y").confidence - 0.9) < 1e-9)

print("\n[9] Cycle detection")
with tempfile.TemporaryDirectory() as tmp:
    cyclic = {"sets": {}, "rules": [
        {"id": "a_from_b", "if": [{"attribute": "b", "exists": True}],
         "then": {"attribute": "a", "value": "v"}, "confidence": 0.9},
        {"id": "b_from_a", "if": [{"attribute": "a", "exists": True}],
         "then": {"attribute": "b", "value": "v"}, "confidence": 0.9}]}
    write_pack(tmp, "cycle.json", cyclic)
    e = ReasoningEngine(FakeKnowledge({}), rules_dir=tmp)
    check("mutual a<->b rules terminate with None", e.infer("user", "a") is None)
    check("no-path recorded", e.history.recent(1)[0].outcome is Outcome.NO_PATH)

print("\n[10] Explanation generation")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"location": ("Officer South", 1.0)}, tmp)
    inf = engine.infer("user", "hemisphere")
    text = engine.explain(inf).summary()
    check("explanation names conclusion, confidence, rule chain and premises",
          "hemisphere = southern" in text
          and "country_implies_hemisphere" in text
          and "location_implies_country" in text
          and "country = Australia" in text
          and "inferred" in text)

print("\n[11] Missing rule path — honest no_path")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 1.0)}, tmp)
    check("unknown attribute returns None", engine.infer("user", "shoe size") is None)
    check("stats count no_path", engine.stats().no_path == 1)

print("\n[12] Read-only behaviour")
with tempfile.TemporaryDirectory() as tmp:
    fake = FakeKnowledge({"location": ("Melbourne", 1.0),
                          "favourite team": ("Brisbane Lions", 1.0)})
    write_pack(tmp, "core.json", PACK); write_pack(tmp, "extra.json", PACK2)
    engine = ReasoningEngine(fake, rules_dir=tmp)
    engine.infer("user", "christmas season")
    engine.infer("user", "supporter type")
    engine.conclusions("user")
    check(f"only reads issued to knowledge ({fake.reads} reads, 0 writes)",
          fake.reads > 0)   # any write would have raised AssertionError
    try:
        ReasoningEngine(fake, rules_dir=tmp, ai_assist=object())
        check("ai_assist rejected in V1", False)
    except ValueError:
        check("ai_assist rejected in V1 (AI advises, rules decide)", True)

print("\n[13] Deterministic repeatability")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"location": ("Officer South", 1.0)}, tmp)
    runs = [engine.infer("user", "christmas season") for _ in range(20)]
    check("20 runs: identical value, confidence and rule chain",
          len({(r.value, r.confidence, r.rule_ids) for r in runs}) == 1)

print("\n[14] conclusions() — derivable set, known facts excluded")
with tempfile.TemporaryDirectory() as tmp:
    engine = make_engine({"favourite team": ("Brisbane Lions", 1.0),
                          "country": ("Australia", 1.0)}, tmp)
    concluded = {i.attribute for i in engine.conclusions("user")}
    check("derives sport, hemisphere, supporter type, christmas season",
          concluded == {"followed sport", "hemisphere",
                        "supporter type", "christmas season"})
    check("stored fact (country) not re-concluded", "country" not in concluded)

print("\n[15] History bounding")
hist = InMemoryInferenceHistory(max_entries=5)
with tempfile.TemporaryDirectory() as tmp:
    write_pack(tmp, "core.json", PACK); write_pack(tmp, "extra.json", PACK2)
    engine = ReasoningEngine(FakeKnowledge({}), rules_dir=tmp, history=hist)
    for _ in range(12):
        engine.infer("user", "followed sport")
    check("bounded at 5 entries after 12 attempts", len(hist) == 5)
    check("recent() returns newest first, respecting limit",
          len(hist.recent(3)) == 3)

print(f"\n{'='*60}\nGENESIS-013 TASK 001: ALL {passed} CHECKS PASS\n{'='*60}")