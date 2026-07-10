# Genesis-013 — Task 002 Engineering Report
## Reasoning Integration

**Status:** COMPLETE — all 17 integration checks pass (incl. 34-case router battery)
**Full-suite regression run (pre-freeze verification):** 106/106 —
Interrupt Engine (G-011) 27/27 · Reasoning Engine core (G-013 T001)
37/37 · Reasoning integration (G-013 T002) 17/17 · G-012/MP-003 memory,
canonicalisation and defect-fix battery 25/25. Zero previously passing
tests modified; zero regressions.
**Date:** 2026-07-10
**Scope:** integration only. The Reasoning Engine (Task 001, FROZEN) is unmodified.

---

## Delivered files

| File | Change |
|---|---|
| `core/skills/reasoning.py` | **NEW** — ReasoningSkill gateway: parses reasoning questions, calls infer()/conclusions()/explain(), phrases conclusions by outcome band (asserted plain, hedged hedged), remembers the last conclusion for "why?" follow-ups, owns all reasoning telemetry |
| `core/intents.py` | `REASONING` member added (verified: only the six existing members are referenced anywhere in the codebase) |
| `core/router.py` | Conservative REASONING routing: exact-match follow-ups ("why", "how did you work that out", "explain that"...), "what can you conclude/infer", and three direct patterns (sport/country/hemisphere). Checked after MEMORY, before GREETING. "Why is the sky blue?" still reaches the AI — tested |
| `core/agent.py` | Constructs `ReasoningEngine(self.knowledge)` (read-only injection), registers ReasoningSkill, and implements the Memory ↔ Reasoning escalation in the MEMORY branch. Pipeline otherwise untouched |
| `core/skills/memory.py` | One additive change: the recall-miss Response now carries `data={"memory_miss": True, "attribute": ...}` so the Agent can escalate. **The spoken miss message is byte-identical** |
| `tests/test_reasoning_integration.py` | 17-check end-to-end battery |

Prerequisite from Task 001 (already delivered/installed): `core/reasoning/`
package and `data/rules/core.json`. If the rules folder is missing the
engine starts with 0 rules and logs a WARNING — graceful, but reasoning
answers nothing.

## The orchestration decision (spec §4), as implemented

Priority order lives in the Agent's MEMORY branch:

1. **Stored fact** — MemorySkill answers; escalation never runs.
2. **Reasoned conclusion** — on a flagged miss, the Agent calls
   `ReasoningSkill.infer_attribute(attribute)` (structured — the
   already-canonicalised attribute, no re-parsing).
3. **Honest local miss** — if reasoning returns None (no path or
   suppressed), the original MemorySkill miss Response is spoken.
4. **AI fallback** — unchanged for UNKNOWN intents; never invoked for
   personal facts (an AI cannot know them either).

Tested explicitly: storing `country = New Zealand` makes the stored fact
answer even though a rule could infer Australia — **reasoning never
overrides knowledge.**

## Explainability (spec §5)

"Why?" / "how did you work that out?" route to REASONING; the skill
calls the engine's `explain()` on the most recent conclusion and phrases
the trace: conclusion, confidence as a percentage, each premise (with
"(which I inferred)" marking chained premises), and the rule chain.
Nothing is regenerated manually. With no recent conclusion, the honest
answer is spoken.

## Telemetry (spec §6)

Per reasoning call: `TIMING | req=N | stage=reasoning_infer |
result=asserted|hedged|no_conclusion|conclusions=K | X ms`, plus the
summary line:

    REASONING | inferences | asserted | hedged | suppressed | no_path |
    derived | chained | multi_premise | avg_ms | rules_loaded | ai_consults

Counts come from the frozen engine's `stats()`; the clock is
gateway-side. `ai_consults` is structurally 0 in V1. Existing TIMING /
KNOWLEDGE / USAGE lines untouched.

## Tests performed (17 checks)

**Acceptance flow (spec §7):** store "favourite team = Brisbane Lions" →
"what sport do I follow?" → AFL with premise cited, `reasoned=True`,
confidence 0.9 — under an **AI spy that raises on any call** (zero
OpenAI, enforced not assumed) → "why?" → trace-based explanation naming
rule and confidence. **Escalation:** derived (country) and 2-rule
chained (hemisphere) answers from recall misses; stored fact wins over
inference; no-path preserves the honest miss verbatim. **Bulk:** "what
can you conclude about me?" lists derivations; empty knowledge answers
honestly. **Router:** 34/34 — 13 new reasoning cases (including three
must-still-reach-AI guards) + the full 21-case G-012 regression battery.
**Memory regression:** store / recall / forget / re-store cycle
unchanged.

## Known limitations

1. Direct-pattern vocabulary is three patterns; most single-attribute
   reasoning flows through the memory-miss escalation instead, which
   scales automatically with the rule packs.
2. "Why?" explains only the most recent conclusion (single-slot session
   memory in the skill).
3. Bulk conclusions speak at most 4 items.
4. `data/rules/core.json` ships 4 rules; growing the pack is data work.

## Recommendation for Task 003

Options, in my suggested order: **(a)** on-machine acceptance +
Genesis-013 freeze report; **(b)** rule-pack expansion pass after
reviewing `data/categories.json` vocabulary (pure data, no code);
**(c)** the deferred maintenance items (exit-punctuation fix, legacy
MemoryManager removal, root main.py); **(d)** the reasoning_effort /
model benchmark decision, which now has three USAGE-line data points.
Genesis-014 candidates beyond that: inference persistence
(`source=INFERRED` write-back under the existing conflict rule) or the
F12 Engineering Console, which now has four telemetry streams to display.