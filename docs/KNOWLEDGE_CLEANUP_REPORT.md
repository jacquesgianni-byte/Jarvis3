# KNOWLEDGE_CLEANUP_REPORT.md
**Generated:** 2026-08-11 06:03 UTC
**Status:** DRY RUN — no data modified

---

## SUMMARY

| Metric | Count |
|--------|-------|
| Total records | 1498 |
| Valid structured knowledge | 51 |
| Conversation transcripts | 1422 |
| Corrupted / superseded | 1 |
| Ambiguous (requires review) | 24 |
| Expired records | 8 |
| Duplicate subject+attribute pairs | 0 |
| Duplicate entity properties | 0 |
| Invalid attribute names | 0 |

---

## CLASS 1 — VALID STRUCTURED KNOWLEDGE
**51 records** — KEEP, no action required

Sample records:
  - `user` → `favourite colour` → `blue`
  - `user` → `colour` → `black`
  - `user` → `favourite team` → `Liverpool`
  - `user` → `new favourite sport` → `football and i follow liverpool fc`
  - `user` → `favourite soccer team` → `liverpool fc`
  - `user` → `favourite drink` → `coffe`
  - `user` → `favourite drink role` → `coffee`
  - `user` → `what role` → `favourite drink`
  - `user` → `location` → `Melbourne`
  - `user` → `name` → `Gianni`
  - _(and 41 more)_

---

## CLASS 2 — CORRUPTED / SUPERSEDED RECORDS
**1 records** — PROPOSED ACTION: DELETE

| Subject | Attribute | Value | Reason |
|---------|-----------|-------|--------|
| `user` | `leo` | `8 not 9!` | misrouted_correction |

---

## CLASS 3 — CONVERSATION TRANSCRIPTS
**1422 records** — DEFERRED (see CONVERSATION_MEMORY_ARCHITECTURE_REVIEW.md)

Date range of transcripts:
  - Earliest: 2026-07-18
  - Latest:   2026-08-11

Sample transcript records:
  - `conversation_2026-07-18_04-12-58` → `hello`
  - `conversation_2026-07-18_04-13-49` → `What is your name?`
  - `conversation_2026-07-18_04-14-04` → `Remember my favourite drink is coffee.`
  - `conversation_2026-07-18_04-14-14` → `What is my favourite drink?`
  - `conversation_2026-07-18_04-14-27` → `Forget my favourite drink.`

---

## CLASS 4 — AMBIGUOUS (REQUIRES HUMAN REVIEW)
**24 records** — REVIEW BEFORE ACTION

### engineering_artefact (12 records)

| Subject | Attribute | Value |
|---------|-----------|-------|
| `genesis_evidence_034` | `test_results` | `{"passed": 3641, "skipped": 33, "failed": 0, "warn` |
| `genesis_evidence_034` | `tests_added` | `0` |
| `genesis_evidence_034` | `desktop_validation` | `{"status": "passed", "scenarios": ["Open sets acti` |
| `genesis_evidence_034` | `recommendation` | `BEGIN_NEXT_GENESIS` |
| `genesis_evidence_034` | `recommendation_reason` | `Lifecycle and Evidence Manager complete. 3641 test` |
| `genesis_evidence_034` | `sprint` | `002` |
| `genesis_evidence_034` | `results` | `All scenarios passed.` |
| `genesis_evidence_034` | `validation` | `3641 tests passing.` |
| `genesis_evidence_034` | `status` | `complete` |
| `genesis_evidence_034` | `commits` | `["ae7df07", "c5c2ca1"]` |
| _(+2 more)_ | | |

### jarvis_non_transcript (3 records)

| Subject | Attribute | Value |
|---------|-----------|-------|
| `jarvis` | `episode_genesis-027_9402` | `We built the Worker Operating System` |
| `jarvis` | `episode_genesis-027_e859` | `WorkerFactory was implemented` |
| `jarvis` | `episode_genesis-027_76ab` | `CodingWorker was registered` |

### suspicious_subject (8 records)

| Subject | Attribute | Value |
|---------|-----------|-------|
| `favourite drink` | `role` | `coffee` |
| `what` | `role` | `favourite drink` |
| `name` | `role` | `Gianni` |
| `favourite colour` | `role` | `blue` |
| `dog's name` | `role` | `Max` |
| `favourite movie` | `role` | `Interstellar` |
| `son` | `role` | `Alex` |
| `manager` | `role` | `Sarah` |

### unclassified (1 records)

| Subject | Attribute | Value |
|---------|-----------|-------|
| `worker_intelligence` | `profile_coordinator` | `{"worker_id": "coordinator", "worker_name": "coord` |


---

## EXPIRED RECORDS
**8 records** — PROPOSED ACTION: ARCHIVE

| Subject | Attribute | Value | Expired |
|---------|-----------|-------|---------|
| `user` | `colour` | `black` | 2026-07-22T10:41:13 |
| `favourite drink` | `role` | `coffee` | 2026-07-22T06:30:04 |
| `what` | `role` | `favourite drink` | 2026-07-22T06:31:57 |
| `favourite colour` | `role` | `blue` | 2026-07-22T06:30:04 |
| `user` | `favourite colour role` | `blue` | 2026-07-22T10:41:13 |
| `user` | `dog's name` | `Max` | 2026-07-20T06:33:23 |
| `favourite movie` | `role` | `Interstellar` | 2026-07-22T06:30:04 |
| `user` | `lucky number` | `7` | 2026-07-22T08:35:04 |

---

## DUPLICATE ENTITY PROPERTIES
**0 duplicate subject+attribute pairs**

_None found (expected — confirmed by data analysis)._

---

## PROPOSED ACTIONS SUMMARY

| Action | Count | Risk |
|--------|-------|------|
| DELETE corrupted records | 1 | LOW — superseded by JTI-001 fixes |
| ARCHIVE expired records | 8 | NONE — already invisible to recall |
| DEFER transcript records | 1422 | N/A — architecture decision pending |
| REVIEW ambiguous records | 24 | N/A — human review required |
| KEEP valid structured records | 51 | N/A |

**No action has been taken. This is a dry-run report only.**

---

## NEXT STEPS

1. Human reviews this report
2. Approve/modify proposed actions
3. Run cleanup script with `--confirm` flag
4. Full pytest after cleanup
5. Commit cleaned knowledge.json