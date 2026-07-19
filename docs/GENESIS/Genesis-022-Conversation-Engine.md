# Genesis-022 — Conversation Engine
## Frozen Handover Document

**Status:** COMPLETE AND FROZEN  
**Final regression:** 2,239 passing · 33 skipped · 0 failed  
**Sprints:** 6  
**New tests:** 587  
**New files:** 10  

---

## 1. Executive Summary

Genesis-022 gives Jarvis the ability to understand conversation — not just classify intent.

Before Genesis-022, Jarvis was a command interpreter. Every user message was independently classified and routed. There was no awareness of what had just been said, no ability to resolve "it" or "him", no way to track a pending question, and no recovery from mid-conversation corrections.

After Genesis-022, Jarvis processes every message through a deterministic, staged pipeline that:

- Detects and handles conversational recovery ("never mind", "cancel", "go back") before anything else
- Resolves ambiguous references ("Close it" → "Close Visual Studio") using live conversation state
- Recognises when a user is answering a pending question or filling a slot
- Classifies the dialogue act (acknowledgement, topic change, continuation, new conversation)
- Produces a typed Decision for the Agent to dispatch

The Conversation Engine is deterministic, fully tested, and completely independent of AI. It makes Jarvis behave like a conversational assistant rather than a command interpreter.

---

## 2. Architecture Overview

```
core/conversation/          ← existing Genesis-020 package (untouched)
    conversation_exceptions.py    ← Sprint-001: error hierarchy
    conversation_models.py        ← Sprint-001: Decision, Slot, Topic, ConversationContext
    conversation_state.py         ← Sprint-002: live session state
    conversation_policy.py        ← Sprint-002: centralised thresholds
    conversation_resolver.py      ← Sprint-003: reference resolution
    conversation_dialogue.py      ← Sprint-004: dialogue classification
    conversation_recovery.py      ← Sprint-005: recovery handler
    conversation_pipeline.py      ← Sprint-005: stage orchestration
    conversation_router.py        ← Sprint-006: Decision production
    conversation_engine.py        ← Sprint-006: single entry point
```

### Layered architecture

```
┌─────────────────────────────────────────────────────────────┐
│                          Agent                              │
│  (dispatches Decision to Memory / Workers / AI / Tools)    │
└─────────────────────────┬───────────────────────────────────┘
                          │ process(request)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  ConversationEngine                         │
│  Owns: State, Policy, Pipeline, Router                     │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
┌──────────────────────┐    ┌─────────────────────────────────┐
│  ConversationPipeline│    │       ConversationRouter        │
│                      │    │                                 │
│  Stage 1: Recovery   │    │  Terminal recovery → RECOVERY   │
│  Stage 2: Resolution │───►│  Slot fill → SLOT_FILLED        │
│  Stage 3: Dialogue   │    │  Ack → ANSWER_DIRECTLY          │
│                      │    │  Intent → IntentRouter          │
└──────────────────────┘    └─────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────────────┐    ┌────────────────────┐
│   ConversationState     │    │      Decision       │
│   ConversationPolicy    │    │  (returned to Agent)│
└─────────────────────────┘    └────────────────────┘
```

---

## 3. Summary of All Six Sprints

### Sprint-001 — Models & Exceptions
**Files:** `conversation_exceptions.py`, `conversation_models.py`  
**Tests:** 90  

Established the data foundation for the entire engine. Defined:
- `DecisionType` enum (8 types: ANSWER_DIRECTLY, ASK_FOLLOW_UP, INVOKE_MEMORY, INVOKE_TOOL, INVOKE_WORKER, AI_FALLBACK, SLOT_FILLED, RECOVERY)
- `Decision` frozen dataclass — the single output of the pipeline
- `Slot` and `SlotStatus` — conversation slots with TTL and fill()
- `Topic` — conversation topic tracking
- `ConversationTurn` — one complete turn record
- `ConversationContext` — mutable pipeline processing bag
- `ConversationError` hierarchy — 9 exception types

**Architectural rule established:**  
> Pipeline stages enrich ConversationContext but must never dispatch work.
> Only ConversationRouter produces the final Decision.

---

### Sprint-002 — State & Policy
**Files:** `conversation_state.py`, `conversation_policy.py`  
**Tests:** 133  

Established the live session state and centralised policy.

**ConversationState** tracks:
- Topic stack (push/pop for conversation recovery)
- Mode (NORMAL / AWAITING_ANSWER / RECOVERING / CONFIRMING)
- Pending question with auto-expiry
- Slot registry (add, fill, query by status)
- Turn history capped at `max_turns` (default 20)
- Reference context (`current_it`, `current_person`, `current_project`)
- Session metadata
- Full reset with preserved `turn_count` and `created_at`

**ConversationPolicy** centralises all thresholds:
- `resolution_threshold = 0.75` — minimum confidence to resolve a reference
- `ambiguity_threshold = 0.60` — below this, decision is ambiguous
- `clarification_threshold = 0.50` — below this, must ask before acting
- `confirmation_threshold = 0.85` — above this for risky actions, confirm first
- Validation enforces: resolution ≥ ambiguity ≥ clarification
- No confidence value is hardcoded anywhere else in the codebase

---

### Sprint-003 — Reference Resolver
**File:** `conversation_resolver.py`  
**Tests:** 88  

Deterministic pronoun and reference resolution using `ConversationState`.

**ReferenceType categories** (for future extensibility):
```
OBJECT   → "it", "this", "that"
PERSON   → "him", "her", "he", "she", "they", "them"
FILE     → "the file", "this file", "the README"
PROJECT  → "the project", "this project"
WORKER   → "the worker", "that worker"
TOPIC    → reserved
UNKNOWN  → fallback
```

**Resolution priority (confidence):**
```
Person pronouns  (him/her/he/she)   → 0.95
Named references (the project/file) → 0.90
Neutral pronouns (it/this/that)     → 0.80
Plural refs      (them/those)       → 0.70
"the last one"                      → 0.65
```

**Examples:**
```
"Close it."          + context: it="Visual Studio"  → "Close Visual Studio."
"Ask him."           + context: person="Claude"     → "Ask Claude."
"Explain this file." + context: entity="README.md"  → "Explain README.md."
```

All confidence thresholds gate through `ConversationPolicy.should_resolve()`.
The resolver never modifies ConversationState — it only returns a ResolutionResult.

---

### Sprint-004 — Dialogue Manager
**File:** `conversation_dialogue.py`  
**Tests:** 100  

Classifies the dialogue act of each message using `DialogueType`.

**DialogueType enum:**
```
ANSWER_PENDING   → input answers a pending question  (slot_related, continuation)
FILL_SLOT        → input fills an open slot          (slot_related, continuation)
CONTINUE         → normal flow, no pending state     (continuation)
ACKNOWLEDGEMENT  → "ok", "sure", "got it"            (continuation)
TOPIC_CHANGE     → "actually", "never mind"          (not continuation)
NEW_CONVERSATION → no context at all                 (not continuation)
UNKNOWN          → empty input                       (not continuation)
```

**Priority order in `analyse()`:**
1. Empty input → UNKNOWN
2. Acknowledgement (anchored regex match)
3. Topic change markers
4. Pending question → ANSWER_PENDING
5. Open slot → FILL_SLOT
6. No context → NEW_CONVERSATION
7. Default → CONTINUE

**Key behaviours:**
- "ok" / "yes" / "got it" are ACKNOWLEDGEMENT — not new routing
- "never mind" / "actually" are TOPIC_CHANGE — not misclassified
- Short answers to pending questions recognised regardless of phrasing
- `_extract_slot_value()` strips "My name is" / "It's" / "I'm" prefixes

---

### Sprint-005 — Recovery Handler & Pipeline
**Files:** `conversation_recovery.py`, `conversation_pipeline.py`  
**Tests:** 111  

Wired all previous components into a deterministic staged pipeline.

**RecoveryAction enum:**
```
NONE              → not a recovery pattern
PENDING_CANCELLED → pending question cancelled
TOPIC_REVERTED    → topic rolled back to previous
STATE_RESET       → full dialogue state reset
ACKNOWLEDGED      → soft recovery, pipeline continues
```

**Recovery priority:**
```
"never mind" / "start over" / "forget it" → STATE_RESET, should_continue=False
"cancel" / "skip it" / "not now"          → PENDING_CANCELLED (or ACKNOWLEDGED)
"go back" / "return to"                   → TOPIC_REVERTED (or ACKNOWLEDGED)
"actually," / "wait,"                     → ACKNOWLEDGED, continues
```

**Recovery is the ONLY stage that may modify ConversationState.**

**ConversationPipeline — three stages:**
```
Stage 1: RecoveryStage    → sets recovery_result, may mark terminal
Stage 2: ResolutionStage  → sets resolution_result, updates current_input
Stage 3: DialogueStage    → sets dialogue_result
```

Terminal after recovery → ResolutionStage and DialogueStage record as **skipped**.

**ProcessingStep telemetry trace (per stage):**
```python
ProcessingStep(
    stage="ResolutionStage",
    executed=True,
    duration_ms=1.2,
    outcome="resolved 'it' → 'Visual Studio'",
    metadata={"resolved": True}
)
```

---

### Sprint-006 — Router & Engine Integration
**Files:** `conversation_router.py`, `conversation_engine.py`  
**Updated:** `core/agent.py`, `conversation_models.py`  
**Tests:** 65  

Wired the complete pipeline to the Agent.

**ConversationRouter** routing priority:
1. Terminal recovery → `RECOVERY`
2. Slot filled / pending answered → `SLOT_FILLED`
3. Acknowledgement → `ANSWER_DIRECTLY`
4. Intent via existing IntentRouter → mapped to DecisionType
5. Unknown → `AI_FALLBACK`

**Intent → DecisionType mapping:**
```
GREETING    → ANSWER_DIRECTLY
IDENTITY    → ANSWER_DIRECTLY
MEMORY      → INVOKE_MEMORY
REASONING   → INVOKE_MEMORY
TOOL        → INVOKE_TOOL
ENGINEERING → INVOKE_MEMORY
EXIT        → ANSWER_DIRECTLY
UNKNOWN     → AI_FALLBACK
```

**ConversationEngine** — single entry point:
```python
engine = ConversationEngine()
decision = engine.process(user_input)
```

Owns State, Policy, Pipeline, Router. Records every turn.

**Agent integration** — minimal surgical addition:
- `RECOVERY` → returns `"Understood, sir. I've cleared that."`
- `SLOT_FILLED` → stores via MemorySkill, returns acknowledgement
- All 7 existing intent paths remain **completely unchanged**

---

## 4. New Modules Created

| File | Sprint | Purpose |
|---|---|---|
| `conversation_exceptions.py` | 001 | ConversationError hierarchy (9 types) |
| `conversation_models.py` | 001 | Decision, Slot, Topic, ConversationContext |
| `conversation_state.py` | 002 | Live mutable session state |
| `conversation_policy.py` | 002 | Centralised confidence thresholds |
| `conversation_resolver.py` | 003 | Reference resolution with ReferenceType |
| `conversation_dialogue.py` | 004 | DialogueType classification |
| `conversation_recovery.py` | 005 | Recovery detection and state modification |
| `conversation_pipeline.py` | 005 | Stage orchestration with telemetry trace |
| `conversation_router.py` | 006 | Decision production from PipelineContext |
| `conversation_engine.py` | 006 | Single entry point — wires everything |

**Modified:**
| File | Change |
|---|---|
| `core/agent.py` | Added ConversationEngine; handles RECOVERY and SLOT_FILLED |
| `conversation_models.py` | Added `reason` field to `Decision` |

---

## 5. Final Conversation Flow Diagram

```
User Input: "Close it."
    │
    ▼
ConversationEngine.process("Close it.")
    │
    ▼
ConversationPipeline.run()
    │
    ├─► Stage 1: RecoveryStage
    │       check: "close it" not a recovery pattern
    │       result: RecoveryResult(NONE, recovered=False)
    │       trace:  ✓ RecoveryStage (0.3ms): no recovery
    │
    ├─► Stage 2: ResolutionStage
    │       check: "it" detected in input
    │       state: references.current_it = "Visual Studio"
    │       policy: confidence 0.80 ≥ threshold 0.75 → resolve
    │       result: ResolutionResult(resolved=True, "Close Visual Studio.")
    │       trace:  ✓ ResolutionStage (0.8ms): resolved 'it' → 'Visual Studio'
    │
    └─► Stage 3: DialogueStage
            check: no pending question, no active slots
            classify: CONTINUE (context exists, no special dialogue act)
            trace:  ✓ DialogueStage (0.2ms): Continue
    │
    ▼
ConversationRouter.decide(ctx)
    │   effective_input = "Close Visual Studio."
    │   no terminal recovery, no slot fill, no ack
    │   IntentRouter.detect("Close Visual Studio.") → UNKNOWN
    │
    ▼
Decision(
    decision_type=AI_FALLBACK,
    resolved_input="Close Visual Studio.",
    raw_input="Close it.",
    confidence=0.50,
    payload={"intent": "UNKNOWN", "resolved": True}
)
    │
    ▼
Agent dispatches → AI provider → Response
```

---

## 6. Integration Points

### Agent
- `Agent.__init__`: instantiates `ConversationEngine()`
- `Agent._route()`: calls `engine.process(request)` before intent routing
- `RECOVERY` decision → returns clean acknowledgement, no further routing
- `SLOT_FILLED` decision → stores via `MemorySkill.remember()`, returns ack
- All other decisions → fall through to existing intent routing (unchanged)

### KnowledgeEngine (Memory)
- `SLOT_FILLED` causes Agent to call `MemorySkill.remember(slot_name, slot_value)`
- ConversationEngine itself never writes to KnowledgeEngine
- ConversationState is separate from KnowledgeEngine — ephemeral only

### Worker Coordinator
- `INVOKE_WORKER` DecisionType is reserved and routed correctly
- ConversationEngine never calls WorkerCoordinator directly
- Agent dispatches to workers based on Decision — clean separation

### AI Provider
- `AI_FALLBACK` DecisionType routes to AI provider as before
- ConversationEngine is AI-free — zero AI calls at any stage
- Resolution result is passed in Decision.resolved_input for AI context

### Existing IntentRouter
- ConversationRouter wraps IntentRouter — does not replace it
- All pre-Genesis-022 routing behaviour preserved unchanged
- IntentRouter consulted for all non-recovery, non-slot decisions

---

## 7. Design Principles and Architectural Decisions

### 1. Deterministic pipeline — no AI in the engine
Every stage is deterministic regex + state lookup. The engine is fully predictable, instantly testable, and never incurs AI latency for conversational housekeeping.

### 2. Single Decision output
Only `ConversationRouter` produces a `Decision`. Pipeline stages enrich `PipelineContext` but are architecturally prohibited from dispatching work. This is enforced by convention and documented in every stage.

### 3. Recovery runs first
`RecoveryStage` is Stage 1. "Never mind" clears state before resolution or dialogue even runs. Terminal recovery sets `is_terminal=True` and downstream stages skip cleanly.

### 4. Reference resolution before dialogue
Resolution (Stage 2) runs before dialogue (Stage 3). This ensures "it should be blue" resolves "it" before the dialogue manager tries to match it against an open slot.

### 5. ConversationPolicy centralises all thresholds
No confidence value is hardcoded outside `ConversationPolicy`. Tuning conversation sensitivity requires changes in exactly one place. Validated at construction — logical ordering enforced.

### 6. State ownership is explicit
`RecoveryHandler` is the ONLY component permitted to modify `ConversationState`. All other components are read-only. This prevents subtle state corruption bugs as the system grows.

### 7. Processing telemetry from day one
Each pipeline stage appends a `ProcessingStep` to `PipelineContext.history`. The Engineering Console (future sprint) has complete visibility into how every message was processed without changing business logic.

### 8. No collision with Genesis-020
New files use descriptive names (`conversation_state.py`, not `state.py`) in the existing `core/conversation/` package. Zero naming collisions with Genesis-020 files. Both coexist cleanly.

### 9. Minimal Agent changes
The Agent received the smallest possible change: two new cases in `_route()` for `RECOVERY` and `SLOT_FILLED`. All 7 existing intent paths are byte-for-byte unchanged.

---

## 8. Test Statistics and Regression Summary

### Genesis-022 test breakdown

| Sprint | Classes | Tests | Focus |
|---|---|---|---|
| 001 | 10 | 90 | Models, exceptions, ConversationContext |
| 002 | 22 | 133 | ConversationState, ConversationPolicy |
| 003 | 12 | 88 | ReferenceResolver, ReferenceType, ResolutionResult |
| 004 | 13 | 100 | DialogueManager, DialogueType, slot extraction |
| 005 | 15 | 111 | RecoveryHandler, pipeline, ProcessingStep |
| 006 | 12 | 65 | Router, Engine, Agent integration, full flow |
| **Total** | **84** | **587** | |

### Full regression suite (all Genesis milestones)

```
Genesis-019  (Engineering Academy)    ~400 tests  ✅
Genesis-020  (Brain / Projections)    ~500 tests  ✅
Genesis-021  (Worker OS)              ~390 tests  ✅
Genesis-022  (Conversation Engine)    ~587 tests  ✅
─────────────────────────────────────────────────
Total:  2,239 passing · 33 skipped · 0 failed
```

The 33 permanent skips are `best_practices.json` location tests (known debt, `data/` vs `data/engineering/`). Not regressions.

---

## 9. Files Added / Replaced

### NEW (drop into `core/conversation/`)
```
core/conversation/conversation_exceptions.py
core/conversation/conversation_models.py
core/conversation/conversation_state.py
core/conversation/conversation_policy.py
core/conversation/conversation_resolver.py
core/conversation/conversation_dialogue.py
core/conversation/conversation_recovery.py
core/conversation/conversation_pipeline.py
core/conversation/conversation_router.py
core/conversation/conversation_engine.py
```

### REPLACE
```
core/agent.py           ← ConversationEngine wired in
```

### NEW (tests)
```
tests/test_conversation_engine_sprint001.py
tests/test_conversation_engine_sprint002.py
tests/test_conversation_engine_sprint003.py
tests/test_conversation_engine_sprint004.py
tests/test_conversation_engine_sprint005.py
tests/test_conversation_engine_sprint006.py
```

---

## 10. Known Limitations (Intentionally Deferred)

### Multi-slot resolution
When multiple slots are active simultaneously, the Dialogue Manager only fills by exact slot name match. Full multi-slot inference (determining which slot a free-form answer belongs to) requires intent context not available in Sprint-004.

### Conversation persistence
`ConversationState` is in-memory only. Restarting Jarvis loses pending questions, reference context, and topic history. Persistent session recovery was explicitly deferred (Sprint-005 spec).

### AI-powered resolution
`ReferenceResolver` is deterministic only. If `current_it` is None and the user says "close it", no resolution occurs. An AI-powered resolver could infer context from the AI's knowledge of the conversation. Deferred to a future Genesis.

### `INVOKE_WORKER` not yet dispatched
`DecisionType.INVOKE_WORKER` is defined and routed correctly by the Router, but the Agent does not yet dispatch it to the `WorkerCoordinator`. The routing path exists; the dispatch call needs a future sprint to complete the loop.

### `ASK_FOLLOW_UP` not yet produced
`DecisionType.ASK_FOLLOW_UP` is defined in the model but the Router never produces it. A future sprint can add a follow-up question generator that uses this type to register pending questions via `DialogueManager`.

### Conversation branching / history replay
`ConversationState` stores turn history but there is no mechanism to replay or branch from a past point in the conversation. The infrastructure exists; the feature is deferred.

### ReferenceType.TOPIC not yet used
`ReferenceType.TOPIC` is reserved in the enum for "the previous topic" / "that subject" resolution. Not yet implemented in `ReferenceResolver` pattern matching.

---

## 11. Git Commit Message

```
Genesis-022: Conversation Engine v1.0 — FROZEN

Implements the complete Conversation Engine across 6 sprints.

Sprints:
  001 — Models & Exceptions: Decision, Slot, Topic, ConversationContext
  002 — State & Policy: ConversationState, ConversationPolicy
  003 — Reference Resolver: ReferenceType, policy-gated confidence
  004 — Dialogue Manager: DialogueType, slot filling, acknowledgement
  005 — Recovery + Pipeline: RecoveryHandler, staged processing, telemetry
  006 — Router + Engine: ConversationRouter, ConversationEngine, Agent integration

Final regression: 2,239 passing · 33 skipped · 0 failed
New tests: 587 across 84 test classes
New files: 10 (core/conversation/) + agent.py update

Architecture:
  User Input → RecoveryStage → ResolutionStage → DialogueStage
             → ConversationRouter → Decision → Agent → dispatch

All Genesis-020 and Genesis-021 behaviour preserved unchanged.
```

---

## 12. Genesis-023 Readiness Assessment

### What Genesis-023 should build on

The Conversation Engine v1.0 is production-ready as a foundation. The clean interfaces mean Genesis-023 can extend without redesigning.

**Highest-value next steps:**

**Option A — Worker Dispatch Completion**  
Wire `DecisionType.INVOKE_WORKER` in the Agent so the full loop  
`Conversation → Decision → WorkerCoordinator → WorkerResult` is closed.  
Estimated: 1 sprint, low risk.

**Option B — Proactive Follow-up Questions**  
Implement `ASK_FOLLOW_UP` routing so Jarvis can ask clarifying questions  
before routing to a Worker. Uses existing `DialogueManager` pending question  
infrastructure. Estimated: 1–2 sprints.

**Option C — Conversation Persistence**  
Persist `ConversationState` across sessions so pending questions and  
reference context survive restarts. Uses existing serialisable models.  
Estimated: 1 sprint.

**Option D — Engineering Console (F12)**  
Surface `PipelineContext.history` (the `ProcessingStep` trace) in the  
desktop as a developer panel. Infrastructure is already built — it just  
needs a UI. Estimated: 1 sprint.

### What Genesis-023 should NOT do

- Do not add AI to the Conversation Engine without first running the deterministic version in production
- Do not add parallelism to pipeline stages without a concrete bottleneck to solve
- Do not redesign `ConversationState` — it is stable and well-tested
- Do not touch Genesis-020 projections (Timeline, Goals, Decisions, Summary) — they are frozen and working

---
## 12.5 Architect's Assessment

Genesis-022 represents the completion of Jarvis's deterministic Conversation Engine.

The architecture intentionally separates understanding from execution. The Conversation Engine is responsible for interpreting conversational context, while the Agent remains responsible for dispatching work. This preserves clear separation of concerns, keeps the engine fully deterministic, and allows conversation behaviour to evolve independently of Workers, Memory, AI providers, or tools.

Future Genesis should extend Jarvis through the ConversationRouter and Decision model rather than bypassing the Conversation Engine. All user input should continue to flow through the Conversation Engine before reaching the Agent.

Genesis-022 establishes the Conversation Engine as the canonical gateway between user interaction and system execution, providing a stable foundation for future capabilities while preserving testability, maintainability, and predictable behaviour.

## 13. Final Genesis-022 Complete Milestone Summary

```
╔══════════════════════════════════════════════════════════════╗
║          Genesis-022 — Conversation Engine v1.0             ║
║                   COMPLETE AND FROZEN                        ║
╠══════════════════════════════════════════════════════════════╣
║  Sprints completed:    6 / 6                                 ║
║  New files:            10 core + 6 test files                ║
║  New tests:            587                                   ║
║  Total passing:        2,239                                 ║
║  Regressions:          0                                     ║
╠══════════════════════════════════════════════════════════════╣
║  What Jarvis can now do:                                     ║
║                                                              ║
║  ✅ Resolve "Close it." → "Close Visual Studio."             ║
║  ✅ Recognise "ok" as acknowledgement, not a new command     ║
║  ✅ Answer a pending question ("Blue" fills colour slot)     ║
║  ✅ Recover from "never mind" cleanly                        ║
║  ✅ Track topic history and revert with "go back"            ║
║  ✅ Detect topic changes ("actually, different question")    ║
║  ✅ Classify every message with a typed DialogueType         ║
║  ✅ Gate all decisions through ConversationPolicy            ║
║  ✅ Trace every message through ProcessingStep telemetry     ║
╠══════════════════════════════════════════════════════════════╣
║  Architecture:                                               ║
║                                                              ║
║  Genesis-020  → Brain (memory, timeline, goals)             ║
║  Genesis-021  → Hands (workers, planning, coordination)     ║
║  Genesis-022  → Understanding (conversation engine)         ║
║                                                              ║
║  Next: Genesis-023                                           ║
╚══════════════════════════════════════════════════════════════╝
```

---

*Genesis-022 frozen. Conversation Engine v1.0 complete.*  
*Jarvis now understands conversation, not just commands.*