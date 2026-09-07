# Genesis-080 Evidence Register

> **Governing rule (GPT, confirmed by Chief):**
> We may clarify how an existing criterion is measured.
> We may not make the criterion easier because Jarvis is struggling.

---

## 1. Frozen Acceptance Criteria

These criteria cannot be changed during the observation or acceptance period.
They may only be clarified in how they are *measured* — never weakened.

### The Chain-Event (required)
Jarvis, without being asked, uses information from separate sessions,
understands the current situation, derives a useful synthesis, surfaces it
at the appropriate moment, explains why it matters, and is correct.

The answer must materially depend on Jarvis's persistent knowledge.
**Counterfactual dependence is mandatory** — if Jarvis would have produced
the same answer without the stored memory, the chain-event is not credited.

### Six Capabilities (all required)
1. **Remember** — not merely storing/retrieving, but surfacing the relevant
   thing at the right moment without being asked.
2. **Understand** — correctly tracking natural, undesigned conversations.
3. **Reason** — demonstrating that the answer genuinely depends on stored
   history rather than merely sounding contextual.
4. **Act** — judging whether/when/what to do, including declining to act.
5. **Initiative** — novel, synthesised, reasoning-driven intervention,
   measured over time.
6. **Calibrated uncertainty** — knowing when not to claim knowledge and
   flagging potential error.

### Structural Requirements
- Minimum **4 weeks** real longitudinal use
- Genuine **7+ day cold gap** with unassisted recovery
- Written interaction log maintained throughout
- Plant/correct/probe recovery test across sessions
- Chain-event must occur at least once during the acceptance period

### Automatic FAIL Conditions (any single instance = FAIL)
1. Confident false assertion about own project history
2. Corrected error repeats in a later session
3. Any initiative event traceable to a scheduled trigger or keyword match
4. Jarvis repeatedly requires Gianni to re-provide demonstrably stored information
5. Chain-event never occurs across the full acceptance period

### The Gianni Test
- Did Gianni choose Jarvis over an alternative?
- What alternative would he have used?
- Did it save meaningful effort?
- Did he return voluntarily?
- Did he stop using another tool?
- Would he genuinely miss Jarvis if it disappeared?

Pass requires questions 5/6/7 answered yes by observed behaviour.

---

## 2. Approved Measurement Refinements

These refine *how* existing criteria are measured. They do not change what
the criteria require.

### Precision and Recall (Remember criterion)
Precision and recall are observed **separately** — not collapsed into a
single percentage.

- **Precision** = True positives / (True positives + False positives)
  *Of what was captured, how much was worth keeping?*
- **Recall** = True positives / (True positives + False negatives)
  *Of what should have been captured, how much was?*

Minimum targets for the observation period:
- Precision ≥ 70%
- Recall ≥ 60%
- Zero sensitive information violations

A system with high precision but low recall may still fail the Remember
criterion if it misses the one critical fact that the chain-event requires.

### Counterfactual Dependence Protocol (Reason criterion)
For any candidate chain-event, run three conditions:

| Condition | Setup | Expected |
|---|---|---|
| A — Memory present | Jarvis has the relevant stored memory | Correct, memory-dependent answer |
| B — Memory removed | Same interaction, memory unavailable | Different or incomplete answer |
| C — Irrelevant substitution | Memory replaced with plausible but irrelevant content | Answer changes or degrades |

If Jarvis produces essentially the same reasoning in all three conditions,
the chain-event is **not credited** as evidence of persistent memory-driven
reasoning.

---

## 3. Current Baseline (Genesis-073 completion)

**Commit:** `912a872`
**Suite:** 5967 passed / 33 skipped / 0 failed
**Date:** 2026-09-05

### What is implemented (Foundation A)
- `SituationalMemoryStore` — `data/situational_memory/entries.json`
- Six categories: `fact`, `decision`, `question`, `constraint`, `intention`, `unresolved`
- `MemoryExtractionPipeline` — LLM-powered, prompt-level privacy guardrail
- Three governed endpoints: `POST/GET/PATCH /memory/situational`
- `threading.Lock` on all store write operations
- `_spawn_situational_extraction()` wired into Agent — daemon thread, post-response
- Direct propagation of `detection.key`+`detection.value` from explicit memory turns

### What is NOT yet demonstrated
- Chain-event: **never occurred**
- Cross-session recall improvement: **unproven**
- Unprompted memory surfacing: **unproven**
- Longitudinal conversation understanding: **unproven**
- Counterfactual dependence: **unproven**
- Any initiative: **zero instances**

---

## 4. Observation Log

Format: one entry per session where situational memory activity is notable.
Chief maintains this log. Do not pad with invented evidence.

```
| Date | Turns | Extracted | True+ | False+ | False- | Category accurate | Notes |
|------|-------|-----------|-------|--------|--------|-------------------|-------|
```

*(Log begins when real observation sessions start.)*

---

## 5. Chain-Event Candidates

Any candidate chain-event must be recorded here with full evidence before
being credited. The counterfactual protocol (Section 2) must be run.

*(None recorded yet.)*

---

## 6. Foundation B Gate

Foundation B (Relevance Detection) does not start because we think we are
ready. It starts because the evidence in Section 4 says we are ready.

**Gate criteria (all required before Foundation B begins):**
- Minimum 3 real use sessions logged in Section 4
- Precision ≥ 70% across logged sessions
- Recall ≥ 60% across logged sessions
- Zero sensitive information violations
- No extraction latency impact observed
- At least one session where a stored memory demonstrably improved a response

**Current status: BLOCKED**

---

## 7. Genesis-080 Acceptance Period Gate

The acceptance period (4-week clock) does not start until:
- Foundation B is complete and validated
- Foundation C (Judgment Layer) is complete
- The chain-event has occurred at least once in pre-acceptance testing
- This register has been reviewed and countersigned by Chief

**Current status: NOT STARTED**

---

*This register is the authority. Not chat history. Not memory files. The repo.*

---

## Session 2 Observation Log -- 2026-09-07

**Commit at session start:** `cf80df5`
**Session duration:** ~8 minutes, 34 turns
**Extraction status:** FIRING -- `[MEMORY] Situational extraction` confirmed in log

### Quantitative results

| Metric | Value |
|---|---|
| Turns in session | ~34 |
| New entries stored | 14 (active) |
| True positives | 5 |
| False positives | 9 |
| False negatives | occupation (partial miss -- captured late) |
| **Precision** | **36%** (target: >=70%) |
| Recall | Not yet formally measurable |
| Sensitive info violations | 0 |
| Latency impact | None observed -- background extraction transparent |

### True positives
- The user has two children named Lucas and Leo. [OK]
- The user's name is Gianni. [OK]
- The user has two dogs named Rex and Tom. [OK]
- The user is a painter who paints houses. [OK]
- The user is a painter by trade. [OK -- slight duplicate of above]

### False positives -- two distinct failure modes

**A. Hallucination (most serious):**
- The user's lucky number is 7. -- never stated. Appeared twice.
- The user's workplace is Academy of Healthcare. -- never stated.
- Sarah is the user's manager. -- never stated.
- The user's name is Ludovic. -- wrong name; Gianni was stated, not Ludovic.

**B. Duplication:**
- The user's favourite colour is blue. -- stored three times.
- The user has two children named Lucas and Leo. -- stored twice.

### Failure mode classification

**Extraction integrity failures (Foundation A concern):**
- Hallucination: extraction pipeline generating plausible but unsupported facts
- Wrong attribution: name extracted incorrectly from earlier session context
- Duplicate accumulation: no contradiction or deduplication mechanism

**Memory utilisation failures (Foundation B concern -- separate):**
- Jarvis could not recall occupation from situational store mid-session
- Colour preference confused across corrections

### Evidence standard established

> A situational memory entry must be traceable to something actually expressed
> by the user or explicitly authorised for memory.
> **Plausibility is not evidence.**

### Foundation B gate -- current status

| Criterion | Status |
|---|---|
| Precision >=70% | FAIL -- 36% observed |
| Zero hallucinated entries | FAIL -- 4 hallucinated entries confirmed |
| Zero sensitive info violations | PASS |
| At least one cross-session recall improvement | NOT YET |

**Foundation B: BLOCKED**

Hallucination is a disqualifying failure mode independent of the precision
percentage. A memory system that invents facts is unsafe for downstream
reliance regardless of how many correct facts it also captures.

### What this session proved

The extraction pipeline fires correctly and captures some genuine facts.
The trust problem is not mechanical -- it is semantic. The pipeline cannot
yet distinguish between facts the user stated and facts the LLM considers
plausible. That distinction is the prerequisite for Foundation A being
declared trustworthy.
