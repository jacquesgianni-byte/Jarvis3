# KNOWLEDGE_CLEANUP_ANALYSIS.md
**Date:** 2026-08-10
**Author:** JTI-001 post-fix analysis
**Status:** AWAITING HUMAN REVIEW — no destructive action taken

## PURPOSE

JTI-001 introduced fixes that prevent future knowledge corruption. However,
the existing knowledge.json contains records produced by the bugs that
JTI-001 has now fixed. This document classifies those records and proposes
rules for cleanup — but does NOT perform any cleanup. No record will be
deleted or modified until this analysis has been reviewed and approved.

## DATASET OVERVIEW

Total records: 1,433 (as of 2026-08-10 analysis)
Date range: 2026-07-09 to 2026-08-09

## RECORD CLASSIFICATION

### Class 1 — Valid Structured Knowledge

Records that represent genuine, current, accurate knowledge about the user
or entities in their life. These must be preserved unconditionally.

Identification rule: category = "entity_property" OR (subject = "user"
AND attribute is a meaningful personal fact such as "name", "favourite colour",
"pet names", "people names", "workplace", "occupation" etc.)

Examples from current data:
  leo        -> prop:age       -> "9"         (stale but valid record type)
  leo        -> prop:property  -> "very smart"
  leo        -> prop:interest  -> "football"
  chase      -> prop:colour    -> "white"
  lucas      -> prop:age       -> "14"        (created by Fix 2)
  user       -> name           -> "Gianni"
  user       -> favourite colour -> "blue"
  user       -> pet names      -> "rex and tom"
  user       -> people names   -> "lucas and leo"

Count (approximate): ~72 records
Action: KEEP — no changes

### Class 2 — Superseded / Corrupted Knowledge

Records produced by bugs that JTI-001 has now fixed.

#### Subclass 2a — Misrouted correction records

Created when MemorySkill stored corrections under subject="user" instead of
updating the authoritative entity record.

Identification rule: subject = "user" AND attribute matches a known entity
name (a proper noun that also exists as a subject in an entity_property record).

Known examples:
  user -> leo -> "8 not 9!"   (failed correction attempt, 2026-08-09)

Proposed action: DELETE (permanent). The correct value now lives in
leo -> prop:age. The text "8 not 9!" has no recall value.

Information risk: None.

#### Subclass 2b — Garbled multi-entity property records

Created when PropertyAssigner captured conjunction statements as a single value.

Identification rule: category = "entity_property" AND attribute = "prop:property"
AND value contains a pattern matching digit + word + "is" + digit.

Known examples:
  lucas -> prop:property -> "14 leo is 8"   (garbled, 2026-07-30)

Proposed action: DELETE (permanent). Clean records now exist as prop:age entries.

Information risk: Low. Clean values now stored correctly.

### Class 3 — Conversation Transcript Records

Records stored under subject = "jarvis" with attribute = "conversation_YYYY-MM-DD_HH-MM-SS".
These are verbatim conversation transcripts stored in the knowledge base.

Identification rule: subject = "jarvis" AND attribute matches
^conversation_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$

Count: ~1,361 records (94.9% of total)
Action: See CONVERSATION_MEMORY_ARCHITECTURE_REVIEW.md. Do not delete until
architecture decision is made.

### Class 4 — Ambiguous Records Requiring Human Review

Records that require human judgement before any action.

4a — Expired records (9 total): ARCHIVE to data/knowledge_archive.json

4b — Records with subject = entity phrase (e.g. "favourite drink", "dog's name",
"what", "son"): HUMAN REVIEW before action. Likely parsing artefacts.

4c — Genesis evidence records (genesis_evidence_034, genesis_lifecycle,
work_goals): HUMAN REVIEW. Likely safe to delete but verify first.

## PROPOSED CLEANUP RULES (generic)

Rule 1 — Delete misrouted correction records:
  subject = "user" AND attribute is a single lowercase word AND
  a record exists with subject = attribute AND value contains correction language

Rule 2 — Delete garbled multi-entity property records:
  category = "entity_property" AND attribute = "prop:property" AND
  value matches r"\d+\s+\w+\s+is\s+\d+"

Rule 3 — Archive expired records:
  expires_at is in the past -> move to data/knowledge_archive.json

Rule 4 — Flag ambiguous subject records for human review:
  subject contains spaces, apostrophes, possessive forms, or question words

## WHAT THIS DOCUMENT DOES NOT AUTHORISE

- No records may be deleted or modified until this analysis is reviewed
- knowledge.json must not be cleared or reset
- Cleanup must be implemented as a reversible script with dry-run mode
- Archive must be created before any deletions
- Full pytest must pass after cleanup

## NEXT STEPS

1. Human reviews this document and approves/modifies the cleanup rules
2. A cleanup script is written with dry-run mode
3. Dry-run output is reviewed
4. Script is run with confirmation
5. Full pytest run after cleanup
6. knowledge.json committed
