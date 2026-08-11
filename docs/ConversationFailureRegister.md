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

---

## CFR-006 — Informational Request Misrouted as Focus Change

**Status:** OPEN
**Discovered:** Genesis-044 Sprint-004 final validation (2026-08-11)
**Classification:** Pre-existing issue (predates Genesis-044)
**Priority:** Medium

### Failure chain

```
User: Tell me about computers.
Jarvis: Focusing on Computers.        ← WRONG: should be AI explanation

User: Make it shorter.
Jarvis: Computers.                    ← WRONG: no content to shorten

User: Tell me another thing about them.
Jarvis: [list of computer models]     ← PARTIAL: related but not educational
```

### Root cause

`_FOCUS_ENTITY_PATTERNS` in `conversation_state_engine.py` contains:

```python
re.compile(r"\btell\s+me\s+about\s+([A-Za-z][\w\-]*)\b", re.IGNORECASE),
```

This pattern was designed to detect genuine entity-focus changes
("Tell me about Lucas.", "Tell me about Rex.") but it also matches
generic informational requests ("Tell me about computers.", "Tell me
about history.", "Tell me about black holes.").

When matched, `detect_focus_change()` returns `detected=True` with
`entity="computers"`, causing the agent to set "Computers" as the
active focus entity and return "Focusing on Computers." instead of
routing the request to AI for an explanation.

### What must NOT happen in the fix

The fix must NOT:
- Add a hardcoded list of common nouns to exclude
- Add a hardcoded list of topic words
- Modify `_STOP_SUBJECTS` with topic words
- Create a new exclusion pattern list
- Rely on capitalisation or casing as a semantic signal
  (users may not capitalise names; speech-to-text may produce
  inconsistent casing; children and non-technical users should
  not need correct punctuation; some genuine entities are lowercase;
  some proper nouns are also topics or products)

### Architectural direction for future fix

The fix must distinguish informational requests from genuine
entity-focus changes using the existing routing/intent architecture.
Potential approaches:

1. Check `EntityRegistry` — if the captured entity has no existing
   records in `jarvis_state.entity_registry`, it is likely a topic,
   not a known entity. Route to AI instead of setting focus.

2. Check `KnowledgeEngine` — if the captured entity has no
   `entity_property` records, it is an unknown entity and should
   not trigger focus change. Note: this would require a
   KnowledgeEngine read inside `ConversationStateEngine`, which
   currently violates its design constraint ("No KnowledgeEngine
   reads or writes"). The constraint or the boundary would need
   to be reviewed.

3. Use the existing routing/intent evidence to distinguish an
   informational request from an entity-focus request. The
   distinction must be semantic rather than based on capitalisation
   or a hardcoded vocabulary. "Tell me about computers" should be
   treated as an informational request. "Tell me about Lucas" may
   be treated as an entity-focus request when the conversation
   state provides evidence that Lucas is an entity relevant to
   the user. The future architecture review should determine the
   exact mechanism.

The correct approach is to be determined by the architecture review
that precedes the implementing Genesis sprint. Do not prescribe the
implementation here.

### Files involved

- `core/conversation/conversation_state_engine.py` — `_FOCUS_ENTITY_PATTERNS`
- `core/agent.py` — focus-entity block (~line 1080)

### Acceptance criteria for future fix

```
Tell me about computers.  → AI explanation, not "Focusing on Computers."
Tell me about Lucas.      → still sets Lucas as active focus entity
                            (when Lucas is a known entity in state)
Tell me about Rex.        → still sets Rex as active focus entity
                            (when Rex is a known entity in state)
Who is Chase?             → still sets Chase as active focus entity
Tell me about history.    → AI explanation
Tell me about music.      → AI explanation
```

### Do not fix in

- Genesis-044 (frozen)
- Any sprint without explicit GPT architectural approval
