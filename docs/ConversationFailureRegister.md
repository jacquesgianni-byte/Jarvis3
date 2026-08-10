# Jarvis Conversation Failure Register
*Principle: Every failure is recorded. Patterns are found. Root causes are fixed.*
*The register only grows. Never shrinks.*

---

## Classification Codes

| Code | Meaning |
|------|---------|
| MEM | Memory / knowledge retrieval failure |
| ENT | Entity resolution failure |
| PRN | Pronoun resolution failure |
| FUP | Follow-up continuity failure |
| KIC | Knowledge integrity / conflict failure |
| SES | Session persistence failure |
| HAL | Hallucination / fabrication |
| CTX | Conversational context failure |

---

## Register

### CFR-001
**Date:** Genesis-043 Validation
**Conversation:**
```
My son Leo is 8.
How old is Leo?
```
**Expected:** Leo is 8.
**Actual:** Leo is 9.
**Classification:** KIC
**Root cause:** KnowledgeEngine contains a prior record `leo → age → 9` from a
previous session. New fact is stored but retrieval returns the stale record.
No conflict resolution or recency ranking exists.
**Component:** KnowledgeEngine / memory retrieval
**Status:** OPEN — design required before fix

---

### CFR-002
**Date:** Genesis-043 Validation
**Conversation:**
```
Who is Chase?
```
**Expected:** Chase is one of your [relationship/group].
**Actual:** Chase -- white
**Classification:** ENT + KIC
**Root cause:** `retrieve_all_properties("chase")` finds a stale `colour: white`
record from a previous session. No mechanism exists to prefer conversationally
relevant facts over stale properties.
**Component:** Agent._route() focus change handler / KnowledgeEngine
**Status:** OPEN — linked to CFR-001 (stale data problem)

---

### CFR-003
**Date:** Genesis-043 Validation
**Conversation:**
```
Tell me a joke.
Tell me another one.
Tell me another one.   ← second time
```
**Expected:** Another joke.
**Actual:** `followup_resolver:` followed by AI system prompt content.
**Classification:** FUP
**Root cause:** After the first follow-up is handled, `_post_turn()` sets
`last_topic = "followup_resolver"` (the skill name). The second follow-up
builds `suggested_prompt = "Tell me another followup_resolver"`. The AI
returns its own system instructions in response to this nonsensical prompt.
**Component:** Agent._post_turn() / FollowUpResolver
**Status:** OPEN — fix designed, not yet implemented

---

### CFR-004
**Date:** Genesis-043 Validation
**Conversation:**
```
My son Lucas is 14.
how old is he?   ← lowercase from Android
```
**Expected:** Lucas is 14.
**Actual:** I'm not sure what you'd like me to remember. / Son is 14.
**Classification:** PRN
**Root cause:** Entity registration regex only matched capitalised names.
After title-case fix, "Son" was registered before "Lucas" because
`_SENTENCE_STARTERS` did not include relationship nouns.
**Component:** Agent._handle_memory_detection() G043-Fix1
**Status:** RESOLVED — `_SENTENCE_STARTERS` extended with relationship nouns

---

### CFR-005
**Date:** Genesis-043 Validation
**Conversation:**
```
My dogs are Rex and Tom.
Who is Rex?
What about Tom?
```
**Expected:** Tom is one of your dogs.
**Actual:** Tom -- colour: black
**Classification:** ENT + KIC
**Root cause:** Focus change handler called `retrieve_all_properties("tom")`
which found a stale `colour: black` record. No reverse lookup was attempted
before returning the property dump.
**Component:** Agent._route() focus change handler
**Status:** RESOLVED — FIX-F2 adds reverse lookup before property dump

---

## Pattern Analysis

| Pattern | Failures | Conclusion |
|---------|----------|------------|
| Stale KnowledgeEngine data overrides fresh input | CFR-001, CFR-002, CFR-005 | Knowledge integrity is the highest-priority architectural problem |
| Internal skill names leaking into conversational state | CFR-003 | `last_topic` must never be set to a component name |
| Capitalisation-dependent logic breaking on lowercase input | CFR-004 | All entity/name detection must be case-insensitive |

---

## Open Issues Requiring Design Review

1. **Knowledge conflict resolution** — when two records contradict, which wins?
2. **last_topic pollution** — internal skill names must never become conversational topics
3. **Stale property contamination** — old entity properties must not outrank relationship context
