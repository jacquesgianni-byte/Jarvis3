# Genesis-013 — Task 001 Engineering Report
## Thought & Reasoning Engine Core

**Status:** COMPLETE — all 37 checks pass
**Date:** 2026-07-10
**Scope:** deterministic reasoning core only, exactly per approved design v1.1.

---

## Delivered files

| File | Purpose |
|---|---|
| `core/reasoning/__init__.py` | Package exports |
| `core/reasoning/models.py` | ReasonType [R3], Outcome, Rule, Premise, Inference, PremiseSnapshot, Explanation, ReasoningStats; confidence constants (cap 0.9, assert 0.75, suppress 0.5) |
| `core/reasoning/rules.py` | Directory-based RuleLoader [R2] — loads every valid *.json in `data/rules/`, merges sets across packs, validates rules, skips invalid ones with WARNINGs (CategoryLoader precedent) |
| `core/reasoning/history.py` | InferenceHistoryRepository ABC + bounded InMemoryInferenceHistory [R4] — no persistence in V1 |
| `core/reasoning/engine.py` | ReasoningEngine — infer / conclusions / explain / stats |
| `data/rules/core.json` | Starter rule pack (4 rules, 2 sets) speaking the vocabulary of real stored facts: favourite team → followed sport; location → country → hemisphere (chaining demo); team+country → supporter type (multi-premise demo) |
| `tests/test_reasoning_engine.py` | 37-check battery, standalone runnable |

## Contract compliance

* **[R1] Read-only** — enforced and *tested*: the fake Knowledge Engine
  raises on any write method; the battery drives inference, chaining and
  bulk conclusions through it (21 reads, 0 writes). The engine calls
  `recall_memory()` only, holds no facts, caches nothing.
* **[R3] reason_type** — DERIVED / CHAINED / MULTI_PREMISE produced;
  AI_ASSISTED / OBSERVED reserved, never emitted.
* **[R4] No persistence** — history is in-memory, bounded (default 200),
  behind the repository ABC for a later swap.
* **[R5] AI advises, rules decide** — the `ai_assist` constructor seam
  exists and V1 *rejects* any non-None value with a ValueError quoting
  the rule. Nothing to disable; it cannot be turned on by accident.
* **User facts prevail** — three ways: confidence hard cap 0.9 < 1.0;
  a stored fact that contradicts a premise fails the rule (the engine
  never "chains around" the user's own statement — tested); and
  `conclusions()` refuses to conclude attributes already stored.

## Behaviour summary

Single-step, chained (≤3 rules, cycle-protected via per-chain visited
set), and multi-premise (AND) inference. Confidence = rule × min(premises),
compounding along chains (verified numerically: 0.9 × 0.9 × 0.85 = 0.6885),
capped at 0.9. Below 0.5 the conclusion is suppressed — recorded in
history, never returned. No rule path → honest None + NO_PATH history
entry. Deterministic: rules tried in load order, ties keep the earlier
rule; 20 repeated runs produce byte-identical conclusions. Explanations
are built during inference from premise snapshots, so they stay honest
even if facts later change.

## Tests performed (37 checks, 15 areas)

Rule loading across multiple packs with cross-file set references ·
invalid-rule rejection (8 invalid shapes + 1 broken JSON file; exactly
the valid rule survives) · single-step · 3-rule chain with
outermost-first rule trace · depth limit (3 passes, 4 blocked) ·
multi-premise AND + contradicting-fact rejection · min() propagation
with hedged outcome · suppression + history record · confidence cap ·
cycle termination · explanation content · missing path · read-only +
ai_assist rejection · 20-run determinism · conclusions() derivable set ·
history bounding and ordering.

## Defect found and fixed during development

Injected-history truthiness bug: `history or Default()` silently
replaced an injected *empty* history (empty ⇒ `__len__`==0 ⇒ falsy).
Caught by test [15], fixed with an explicit `is not None` check,
documented in code. A small vindication of the test-battery standard.

## Known limitations (documented, per spec — not implemented)

1. Rule conclusions are fixed values; value-mapping rules ("timezone
   *of* the stored city") need one rule per mapping in V1.
2. Premise matching is exact/set membership on canonicalised strings —
   no numeric comparison, negation, or OR (OR = write two rules).
3. `conclusions()` recomputes from scratch per call — fine at V1 scale;
   telemetry will watch it.
4. Engine reads facts for the given subject only ("user") — multi-
   subject reasoning is deferred per spec.
5. Shipped rule pack is intentionally small (4 rules); growing it is a
   data exercise, ideally after reviewing `data/categories.json`
   vocabulary.

## Ideas that arose (documented, NOT implemented, per instruction)

* A `not_equals` premise kind fell out naturally during matching design —
  deferred; belongs with contradiction work.
* `conclusions()` output is the obvious seed for future proactive
  reasoning ("Chief, did you know I can work out…") — deferred.

## Recommendation for Task 002

Wire the gateway, exactly per design §3: **ReasoningSkill** (translates
language ↔ structured infer/explain calls, owns telemetry: TIMING
`stage=reasoning_infer` + the REASONING summary line with reason_type
breakdown), `Intent.REASONING` router patterns, Agent construction
(`ReasoningEngine(self.knowledge)` + skill registration), the
recall-miss escalation decision (recommend: Agent consults TRE on
MemorySkill miss before the honest "not stored" reply), and an
on-machine acceptance script — store "my favourite team is Brisbane
Lions", ask **"what sport do I follow?"**, expect an asserted local
conclusion with a spoken explanation available on "why?", zero OpenAI.