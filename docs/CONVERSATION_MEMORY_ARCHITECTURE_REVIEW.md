# CONVERSATION_MEMORY_ARCHITECTURE_REVIEW.md
**Date:** 2026-08-10
**Author:** JTI-001 architecture analysis
**Status:** RECOMMENDATION ONLY — no implementation

## PURPOSE

knowledge.json currently contains approximately 1,361 conversation transcript
records alongside approximately 72 structured knowledge records. This review
investigates whether these should continue to live in the same store.

## WHAT ARE THE TRANSCRIPT RECORDS?

Every record with subject = "jarvis" and attribute matching
conversation_YYYY-MM-DD_HH-MM-SS is a verbatim message transcript.
These capture both user messages and Jarvis responses in a flat key-value
format with a timestamp-based attribute name.

## WHICH COMPONENT WRITES THEM?

apps/server/routes.py writes a transcript record after every chat response,
regardless of what happened in the agent pipeline. Every HTTP request to
/chat generates one record.

## ARE THEY USED BY RECALL?

Direct recall: No. No component calls recall_memory() for a specific
conversation timestamp.

Search recall: Yes, indirectly. ConversationProvider in SemanticRecallEngine
calls search_memory(query=entity_name, subject="jarvis"). This finds transcript
records where the entity name appears in the value. The only fact contributed
is SemanticFact(label="Discussed recently") — the lowest-value signal.

Structured recall: No. PropertyProvider and GroupProvider do not use transcripts.

## DO THEY DUPLICATE OTHER STORAGE?

ConversationTimeline: Partially. Timeline records structured events, not raw text.
Session history: In-memory only, does not persist across restarts.
EpisodicMemoryEngine: May use search_memory() with episode labels. Transcripts
could contribute incidentally. This dependency needs mapping before deletion.

## DO THEY AFFECT RETRIEVAL QUALITY?

Positively: Marginally — "Discussed recently" fallback signal only.

Negatively:
1. Inflate search_memory() result sets (70+ transcript hits per entity search)
2. Caused CFR-001/CFR-002 class bugs: contradictions accumulated with no resolution
3. Make knowledge.json 95% noise
4. Contribute to notes bloat via repeated store_memory() calls

## RECOMMENDATION

Option C: Keep both but clearly distinguish storage and retrieval semantics.

Rationale: Deleting or separating transcripts immediately risks breaking
EpisodicMemoryEngine and creating regression. The correct architecture
separates concerns, but that is Genesis-044+ work. The smallest correct
change for Genesis-043 is to document the intended separation.

Recommended immediate actions (Genesis-043):
  - Commit this document to docs/. No code changes.

Recommended future actions (Genesis-044+):

Phase 1 — Tag transcripts clearly:
  Add a "transcript" tag to all records written by routes.py so they can
  be filtered out of structured recall without deletion.

Phase 2 — Separate retrieval paths:
  ConversationProvider searches only tagged transcript records.
  PropertyProvider and GroupProvider explicitly exclude them.

Phase 3 — Separate storage (optional):
  Move transcripts to data/conversation_history.json with its own retention
  policy. Structured knowledge stays in data/knowledge.json.

## WHY NOT OTHER OPTIONS?

Option A (Keep as-is): Already causing known bugs. Not acceptable.
Option B (Separate immediately): Refactoring surface too large for Validation sprint.
Option D (Delete transcripts): EpisodicMemoryEngine dependencies not fully mapped.

## SUMMARY

| Option | Risk | Effort | Recommended |
|--------|------|--------|-------------|
| A: Keep as-is | HIGH | None | No |
| B: Separate now | HIGH | HIGH | No |
| C: Distinguish semantics, separate later | LOW | LOW now | YES |
| D: Delete transcripts | MEDIUM | LOW | No |

## FILES REFERENCED

  data/knowledge.json                        — unified store (1,433 records)
  apps/server/routes.py                      — writes transcript records
  core/conversation/semantic_recall_engine.py — ConversationProvider reads transcripts
  core/episodic_memory_engine.py             — may depend on transcript content
  core/knowledge_engine/engine.py            — central storage API
