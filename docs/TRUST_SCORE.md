# Jarvis Trust Score
*Updated: Genesis-043 Validation Phase*
*Principle: Every Genesis must improve this dashboard.*

## Scoring Key
- ✅ PASS — Reliable in real-world testing
- ⚠️ PARTIAL — Works in some cases, fails in others
- ❌ FAIL — Known failure
- 🔲 UNTESTED — Not yet validated in real-world conditions

---

## Current Score: Genesis-043 Validation

| Metric | Status | Notes |
|--------|--------|-------|
| Memory accuracy | ⚠️ PARTIAL | "Leo is 8" recalled as "Leo is 9" — stale data wins |
| Pronoun resolution | ⚠️ PARTIAL | Works for fresh sessions; fails with stale entity registry |
| Entity resolution | ⚠️ PARTIAL | "Who is Chase?" returns colour property, not relationship |
| Location recall | ✅ PASS | "Where do I live?" → Melbourne consistently |
| Group recall | ✅ PASS | "Who are my dogs?" → Rex and Tom |
| Follow-up continuity (1st) | ✅ PASS | "Tell me another one" → correct joke |
| Follow-up continuity (2nd) | ❌ FAIL | "Tell me another one" again → followup_resolver leaked |
| Knowledge consistency | ❌ FAIL | Conflicting facts not resolved; oldest or random wins |
| Contradiction detection | ❌ FAIL | No contradiction detection exists |
| Hallucination rate | 🔲 UNTESTED | Not formally measured |
| Android real-world pass rate | ⚠️ PARTIAL | Memory/location pass; follow-up chain fails |
| Desktop real-world pass rate | ⚠️ PARTIAL | Same failures as Android |

**Score: 4/12 PASS · 4/12 PARTIAL · 3/12 FAIL · 1/12 UNTESTED**

---

## Definition of Done (per Genesis)

A Genesis is complete only when ALL FOUR pass:

- [ ] Automated tests: 0 failures
- [ ] Desktop conversation: all Golden Conversations pass
- [ ] Android conversation: all Golden Conversations pass
- [ ] Human judgement: Ludovic says "I would trust this for my family"

---

## Golden Conversations (Permanent Suite)

These must pass every time. The suite only grows. Never shrinks.

| # | Conversation | Expected |
|---|-------------|----------|
| G-01 | My son Lucas is 14. / How old is he? | Lucas is 14. |
| G-02 | My dogs are Rex and Tom. / Who are my dogs? | Rex and Tom are your dogs. |
| G-03 | My dogs are Rex and Tom. / Who is Rex? | Rex is one of your dogs. |
| G-04 | My dogs are Rex and Tom. / Who is Rex? / What about Tom? | Tom is one of your dogs. |
| G-05 | Tell me a joke. / Tell me another one. | A different joke. |
| G-06 | Tell me a joke. / Tell me another one. / Tell me another one. | Another joke (not system content). |
| G-07 | Tell me a joke. / Say that again. | The same joke repeated. |
| G-08 | I live in Melbourne. / Where do I live? | You live in Melbourne. |
| G-09 | My son Leo is 8. / How old is Leo? | Leo is 8. (not 9 from stale data) |
| G-10 | Who is Chase? | Relationship answer (not colour property). |
