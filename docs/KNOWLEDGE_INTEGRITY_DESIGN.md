# Knowledge Integrity Design — JTI-001
*Status: PROPOSED — awaiting GPT review before implementation*
*Do not implement until this design is approved.*

---

## Problem Statement

KnowledgeEngine accumulates records across sessions with no conflict resolution.
When the same fact is stated twice with different values, retrieval is
unpredictable. The person's most recent statement must always win for facts
about themselves.

Example:
```
Session 1:  My son Leo is 9.     → stored: subject=user, attribute=son leo, value=9
Session 2:  My son Leo is 8.     → stored: subject=user, attribute=son leo, value=8
Query:      How old is Leo?      → returns: 9  (wrong — stale record wins)
```

---

## Proposed Design

### 1. Record Metadata

Add optional fields to every MemoryRecord:

| Field | Type | Description |
|-------|------|-------------|
| `stored_at` | ISO timestamp | When this record was created |
| `source` | enum | `user_statement` \| `derived` \| `inferred` \| `corrected` |
| `confidence` | float 0.0–1.0 | How confident we are in this fact |
| `superseded_by` | record_id \| None | Points to the record that replaced this one |

### 2. Conflict Detection on Write

When `store_memory()` is called:

1. Search for existing records with same `subject` + `attribute`
2. If found AND new source is `user_statement`:
   - Mark old record: `superseded_by = new_record_id`
   - Store new record with `confidence = 1.0`
3. If found AND old source is `derived` or `inferred`:
   - Replace silently (explicit user statement always wins)
4. If no conflict: store normally

### 3. Retrieval Ranking

When `recall_memory()` returns candidates, rank by:

1. `superseded_by IS None` — hard filter (never return superseded records)
2. `source == "user_statement"` — prefer explicit user statements
3. `stored_at` descending — prefer most recent
4. `confidence` descending — prefer higher confidence

### 4. Correction Detection

If user says "actually Leo is 8, not 9" or "I meant 8, not 9":

1. `ConversationStateEngine` detects correction pattern
2. Previous record marked `superseded_by = correction_record_id`
3. Correction stored with `source = "corrected"`, `confidence = 1.0`

### 5. What Does NOT Change

- KnowledgeEngine public API is unchanged
- No new storage backends
- Metadata fields are optional — existing records without them still work
- All existing tests continue to pass

---

## Questions for GPT

1. Should superseded records be **deleted** or **retained** for audit history?
2. Should confidence decay (PAPER-001 Principle 8) apply to `user_statement`
   records, or only to `derived` and `inferred` records?
3. Should correction detection live in `ConversationStateEngine` or in a
   dedicated `CorrectionEngine`?
4. Should this be a mini-sprint before Genesis-044, or part of Genesis-044?
5. Should stale records from test sessions be purged from `knowledge.json`,
   or handled purely through supersession?

---

## Impact Assessment

| Component | Change required | Risk |
|-----------|----------------|------|
| KnowledgeEngine.store_memory() | Add conflict detection | Medium |
| KnowledgeEngine.recall_memory() | Add ranking by recency/source | Low |
| MemoryRecord model | Add 4 optional fields | Low |
| ConversationStateEngine | Add correction pattern detection | Medium |
| Existing tests | No changes expected | Low |
| knowledge.json schema | Backward-compatible | Low |
