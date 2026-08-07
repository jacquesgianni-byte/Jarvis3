# Genesis-042 — Refactoring Intelligence

## Sprint-001 Findings

### Dead Code Removed
- `core/core/core/core/memory_manager.py` — 8-line stub, never imported. DELETED.

### Naming Confusion (NOT duplicates — different purposes)
| File | Class | Purpose |
|------|-------|---------|
| `core/conversation/decision_engine.py` | `DecisionEngine` | Tracks architectural decisions from conversation timeline (Genesis-020) |
| `core/decision/engine.py` | `DecisionEngine` | Evaluates engineering state / can we close this Genesis? (Genesis-036) |

**Action needed:** Rename to make distinction clear.
- `core/conversation/decision_engine.py` → rename class to `ConversationDecisionEngine`
- `core/decision/engine.py` → rename class to `EngineeringDecisionEngine`

### Technical Debt Found in agent.py
- 800+ lines, does routing + session + memory + engineering
- Imports 60+ modules at top
- 7 different approval trigger frozensets scattered through the file
- Engineering routing logic duplicated in 3 places (Section 7.0, 7.5, 7.6, 7.46)
- 4 separate "collaboration runner" fast-paths

### Conversation Module (40+ files)
Files that appear unused or redundant:
- `conversation_dialogue.py` — dialogue management, unclear if called
- `conversation_pipeline.py` — pipeline abstraction, unclear if called  
- `conversation_policy.py` — policy engine, unclear if called
- `conversation_recovery.py` — recovery logic, unclear if called
- `conversation_router.py` — routing, but agent.py does its own routing

### Next Sprints
- Sprint-002: Audit conversation module — identify dead files
- Sprint-003: Flatten agent.py routing into clean pipeline
- Sprint-004: Rename duplicate class names
- Sprint-005: Consolidate engineering routing (3 fast-paths → 1)

## Goal
When Genesis-042 is complete:
- agent.py is under 400 lines
- No duplicate class names
- No dead code
- Every file in conversation/ is actively used
- Engineering routing is one clear path
