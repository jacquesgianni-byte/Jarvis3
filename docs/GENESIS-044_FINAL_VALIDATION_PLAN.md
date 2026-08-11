# GENESIS-044_FINAL_VALIDATION_PLAN.md
**Date:** 2026-08-11
**Status:** AWAITING GPT APPROVAL — no implementation
**Sprint:** Genesis-044 Sprint-004 (Final Validation)

---

## SECTION 1 — FINAL ARCHITECTURE STATE

### 1.1 State ownership after Sprint-003

| Component | What it is | Points to |
|-----------|-----------|-----------|
| `Agent.jarvis_state` | `ConversationState` instance | Canonical state — created once in `Agent.__init__()` |
| `Agent.session` | Direct reference | Same object as `jarvis_state` — NO adapter |
| `ConversationEngine._state` | Injected reference | Same object as `jarvis_state` — Sprint-001 DI |
| `ContextManager._session` | Reference to session | Same object as `jarvis_state` |
| `ContextResolver._session` | Reference to session | Same object as `jarvis_state` |
| `ConversationStateEngine` | Stateless resolver | Renamed to `Agent.dialogue_resolver` |
| `SessionContextAdapter` | Deprecated shim | ZERO runtime callers |
| `ConversationContext.last_jarvis_response` | Deprecated field | ZERO runtime consumers — field exists, nothing writes/reads it |

### 1.2 Response state ownership

| Field | Status | Consumer |
|-------|--------|---------|
| `ConversationState._last_response` | CANONICAL | `FollowUpResolver.resolve()` ("Say that again"), `_post_turn()` writes via `set_last_turn()` |
| `ConversationContext.last_jarvis_response` | DEPRECATED | Zero runtime consumers. Field retained for safe deletion in Genesis-045 |
| `_sessions["last_response"]` | REMOVED | Gone from routes.py save/restore |
| `_sessions["last_jarvis_response"]` | REMOVED | Gone from routes.py save/restore |

### 1.3 HTTP persistence path (authoritative)

```
Agent._post_turn()
  → session.set_last_turn(response=response_message)
  → ConversationState._last_response = response_message

routes.py._save_session()
  → _sessions[session_id]["jarvis_state"] = agent.jarvis_state
  (entire ConversationState object reference, including _last_response)

routes.py._restore_session()
  → agent.jarvis_state = saved_state
  → agent.session = saved_state
  (session and jarvis_state both point to restored ConversationState)
```

---

## SECTION 2 — REPOSITORY AUDIT

### 2.1 SessionContextAdapter references

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/conversation/session_context_adapter.py` | entire file | The adapter class itself | COMPATIBILITY — deprecated, retained for test imports |
| `core/conversation/session_context.py` | 31, 33 | Imports and uses adapter in compat stub | COMPATIBILITY — compat stub, not runtime |
| `core/agent.py` | import removed | Was imported, now gone | REMOVED |
| `tests/test_genesis043_sprint001.py` | multiple | Tests the adapter interface directly | TEST |
| `tests/test_genesis044_sprint001.py` | multiple | Tests adapter set_active_topic alias | TEST |

**Runtime callers: ZERO** ✅

### 2.2 SessionContext references

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/conversation/session_context.py` | entire file | Compat stub, delegates to adapter | COMPATIBILITY |
| `core/conversation/context_manager.py` | import | `ConversationState as SessionContext` alias | COMPATIBILITY — compat import alias, Genesis-045 cleanup |
| `core/conversation/context_resolver.py` | import | Same alias | COMPATIBILITY |
| `core/conversation/followup_resolver.py` | import | Same alias | COMPATIBILITY |
| `core/conversation/clarification_engine.py` | import | Same alias | COMPATIBILITY |
| `core/conversation/conversation_state_engine.py` | import | Same alias | COMPATIBILITY |
| Multiple test files | various | Type annotations in test setup | TEST |
| `core/conversation/projection.py` | docstring | Mentions SessionContext in comment | DOCUMENTATION |
| `core/workers/manager.py` | docstring | Mentions SessionContext in comment | DOCUMENTATION |

**Runtime callers: ZERO** — all are aliases pointing to `ConversationState` ✅

### 2.3 last_jarvis_response references

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/conversation/context.py` | 32, 41, 78 | Field declaration and reset | DEAD/UNUSED — no runtime writers or readers remain |
| `tests/test_conversation_orchestration_sprint002.py` | 8 | Docstring comment only | DOCUMENTATION |
| `tests/test_gc004_conversation_context.py` | 72 | Comment: "# No last_jarvis_response set" | DOCUMENTATION |
| `tests/test_genesis043_final_fixes.py` | 48, 49, 75 | Test fixture simulating old session dict | TEST — Genesis-043 era test, pre-Sprint-003 |
| `tests/acceptance/test_genesis043_conversation_acceptance.py` | 57, 58, 69, 70, 88 | Test fixture simulating old session dict | TEST — Genesis-043 era test, pre-Sprint-003 |

**Runtime consumers: ZERO** ✅
**Flagged for Genesis-045 cleanup:** `test_genesis043_final_fixes.py` and `test_genesis043_conversation_acceptance.py` test fixtures

### 2.4 last_response references

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/conversation/conversation_state.py` | property | `_last_response` property declaration | RUNTIME — canonical field |
| `core/conversation/session_context_adapter.py` | property | Delegates to `_s.last_response` | COMPATIBILITY — adapter, zero callers |
| `core/agent.py` | `_post_turn()` | `session.set_last_turn(response=...)` | RUNTIME — canonical write |
| `core/conversation/followup_resolver.py` | resolve() | `session.last_response` — "Say that again" | RUNTIME — canonical read |
| `core/agent.py` | lines 1447, 1503 | `last_response = self.session.last_response` | RUNTIME — "why/how do you know" reads |
| `tests/test_genesis043_final_fixes.py` | session dict | `"last_response": ...` in old test fixture | TEST |
| `tests/acceptance/...` | session dict | `"last_response": ...` in old test fixture | TEST |

**Single runtime source of truth: `ConversationState._last_response`** ✅

### 2.5 ConversationState( instantiations

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/agent.py` | `__init__` | `self.jarvis_state = ConversationState()` | RUNTIME — ONE creation, canonical |
| `core/conversation/conversation_engine.py` | `__init__` | `self._state = state if state is not None else ConversationState()` | RUNTIME — uses injected state, fallback only |
| `core/conversation/session_context.py` | compat stub | Creates ConversationState for compat stub | COMPATIBILITY — not used at runtime |
| Test files | various | Create ConversationState for test isolation | TEST |

**Runtime: ONE creation per Agent instance** ✅

### 2.6 conversation_state vs dialogue_resolver

| File | Line | Content | Classification |
|------|------|---------|---------------|
| `core/agent.py` | `__init__` | `self.dialogue_resolver = ConversationStateEngine()` | RUNTIME — renamed Sprint-001 |
| `core/agent.py` | `_route()` etc | `self.dialogue_resolver.detect_focus_change(...)` | RUNTIME — correct |
| `core/conversation/conversation_state_engine.py` | docstring | References `ConversationStateEngine` by class name | DOCUMENTATION |
| Test files | various | Reference `ConversationStateEngine` by class name | TEST |
| `core/conversation/conversation_state.py` | class name | `class ConversationState` | RUNTIME — the state class itself |

**`self.conversation_state` attribute: ZERO occurrences on Agent** ✅

---

## SECTION 3 — ARCHITECTURE VERIFICATION CHECKLIST

| # | Requirement | Evidence | Status |
|---|-------------|---------|--------|
| 1 | ConversationState is canonical conversation state | `Agent.jarvis_state = ConversationState()` — one instance per agent | ✅ |
| 2 | Agent.session points to same ConversationState | `Agent.session = Agent.jarvis_state` (Sprint-002) | ✅ |
| 3 | ConversationEngine receives same ConversationState | `ConversationEngine(state=self.jarvis_state)` (Sprint-001) | ✅ |
| 4 | SessionContextAdapter ZERO runtime callers | Audit confirms — only test files import it | ✅ |
| 5 | context.last_jarvis_response ZERO runtime consumers | Audit confirms — field exists, nothing reads/writes at runtime | ✅ |
| 6 | HTTP persistence uses canonical jarvis_state | `_sessions["jarvis_state"] = agent.jarvis_state` — Sprint-003 | ✅ |
| 7 | last_response has one runtime source of truth | `ConversationState._last_response` — Sprint-003 | ✅ |
| 8 | EntityRegistry/TopicTracker/Summariser in canonical state | Created in `ConversationState.__init__()` — unchanged | ✅ |
| 9 | No second ConversationState in conversation pipeline | `ConversationEngine` uses injected `jarvis_state` — Sprint-001 | ✅ |
| 10 | Genesis-043 behaviour not regressed | 4,406 passed, 33 skipped, 0 failed post Sprint-003 | ✅ |

---

## SECTION 4 — FINAL VALIDATION EXECUTION PLAN

### 4.1 Automated tests

```
python -m pytest tests/ -x -q
```
Required: 4,406+ passed, 0 failed, 33 skipped

### 4.2 Golden Conversations (all 10)

| GC | Conversation | Component tested |
|----|-------------|-----------------|
| GC-001 | My name is Gianni / What is my name? | MemoryDetector, MemorySkill |
| GC-002 | Remember my favourite colour is blue / What is my favourite colour? | MemorySkill, canonicalise |
| GC-003 | Chase is white / Who is Chase? | PropertyAssigner, SemanticRecallEngine |
| GC-004 | My name is Gianni / What is my name? / Why? | context explanation path |
| GC-005 | My dogs are Rex and Tom / Who is Rex? / What about Tom? | SlotCompletionEngine, ContextualRecallEngine |
| GC-006 | My son Leo is 9 / Actually Leo is 8 / How old is Leo? | PropertyAssigner qualifier strip, entity correction |
| GC-007 | Lucas is 14 and Leo is 8 / How old is Lucas? / How old is Leo? | detect_assignments, conjunction split |
| GC-008 | Tell me a joke / Tell me another one x2 / Say that again | FollowUpResolver, last_response canonical path |
| GC-009 | My name is Gianni / Remember favourite colour is blue / What is colour? | entity-aware memory guard |
| GC-010 | Tell me a joke / Tell me about history / Tell me another one | topic switch correctness |

### 4.3 Additional Sprint-004 acceptance conversations

**A — Memory:**
```
My son Lucas is 14.
How old is he?
```
Expected: pronoun "he" resolves to Lucas → "Lucas is 14."

**B — Correction:**
```
My son Leo is 9.
Actually, Leo is 8.
How old is Leo?
```
Expected: "Leo is 8."

**C — Group relationship:**
```
My dogs are Rex and Tom.
Who is Rex?
What about Tom?
```
Expected: "Rex is one of your dogs." / "Tom is one of your dogs."

**D — Location:**
```
I live in Melbourne.
Where do I live?
```
Expected: "You live in Melbourne." (or similar recall)

**E — Follow-up:**
```
Tell me a joke.
Tell me another one.
Tell me another one.
Say that again.
```
Expected: Three different jokes, exact repeat of third.

**F — Topic continuity:**
```
Tell me about computers.
Make it shorter.
Tell me another thing about them.
```
Expected: All three turns coherent about computers.

**G — HTTP continuity:**
Request 1: `Tell me a joke.`
Request 2 (new HTTP request): `Say that again.`
Expected: Second request returns exact first joke from persisted `jarvis_state._last_response`.

### 4.4 Platforms

Both Desktop and Android must pass conversations A–G.

### 4.5 Behaviour anomalies to watch for

- AI fallback when local answer should exist
- Internal routing terms in responses ("followup_resolver", "ai_fallback")
- Stale memory overriding corrected facts
- Broken pronoun resolution after topic switch
- Unexpected state reset mid-conversation
- "Say that again" returning wrong response

**If any anomaly is found:** document it. Fix ONLY if directly caused by Genesis-044 state unification. Otherwise record for future Genesis.

---

## SECTION 5 — GENESIS-044 COMPLETION CRITERIA

Genesis-044 is complete ONLY when ALL of the following are confirmed:

1. ✅ Architecture correct (this document + audit)
2. ☐ Full pytest: 4,406+ passed, 0 failed
3. ☐ All 10 Golden Conversations pass on Android
4. ☐ All 10 Golden Conversations pass on Desktop
5. ☐ Additional acceptance conversations A–G pass on both platforms
6. ☐ HTTP continuity test passes
7. ☐ No critical regression from Genesis-043 baseline
8. ☐ GPT final architecture review and approval
9. ☐ Human real-world validation sign-off

---

## SECTION 6 — WHAT GENESIS-044 DID NOT CHANGE

The following are explicitly out of scope and must be verified as unchanged:

- KnowledgeEngine API — unchanged
- MemorySkill behaviour — unchanged
- PropertyAssigner behaviour — unchanged
- SemanticRecallEngine behaviour — unchanged
- FollowUpResolver logic — unchanged
- All 10 Golden Conversations — must behave identically to Genesis-043

---

## SECTION 7 — POST-GENESIS-044 CLEANUP (Genesis-045 candidates)

These items were identified during Genesis-044 but intentionally deferred:

| Item | Why deferred | Priority |
|------|-------------|---------|
| Delete `SessionContextAdapter` file | Tests still import it | LOW |
| Delete `ConversationContext.last_jarvis_response` field | Retained for safe transition | LOW |
| Update `test_genesis043_final_fixes.py` test fixtures | Old session dict format | LOW |
| Update `test_genesis043_conversation_acceptance.py` fixtures | Old session dict format | LOW |
| Remove compat import aliases (SessionContext = ConversationState) | Still in 5 component files | LOW |
| Remove compat stub `session_context.py` | Still imported by some tests | LOW |
