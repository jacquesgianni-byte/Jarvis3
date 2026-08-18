# ADR-001 — KnowledgeEngine Subject Namespace

**Status:** Accepted  
**Genesis:** 050  
**Date:** 2026-08-18

---

## Context

Jarvis has one persistent structured-assertion layer: the KnowledgeEngine.
Every fact stored in Jarvis is a `MemoryRecord` with the shape
`(subject, category, attribute, value)`.

The `subject` field is the primary identity and lookup dimension.
Every recall engine uses `subject` as the first filter when retrieving facts.

Because `subject` is load-bearing, its values must be stable and intentional.
Accidental subject pollution (typos, inconsistent casing, partial phrases)
causes silent retrieval failures that are difficult to diagnose.

---

## Decision

The following subject values are established and must be used consistently:

### `"user"`
Facts about the primary user of this Jarvis instance.

Examples:
- `subject="user", attribute="name", value="Gianni"`
- `subject="user", attribute="favourite colour", value="blue"`
- `subject="user", attribute="occupation", value="developer"`
- `subject="user", attribute="people names", value="Lucas and Leo"`

All personal facts, preferences, relationships, events, and occupational
information about the user are stored under `subject="user"`.

### `"jarvis"`
Facts that Jarvis has observed or recorded about its own operation.

Examples:
- `subject="jarvis", attribute="conversation_2026-08-18_07-01-25", value="What is my name?"`
- `subject="jarvis", attribute="episode_genesis-027_...", value="..."`

Journal entries, conversation records, and tag-seeded episode records
are stored under `subject="jarvis"`.

### Entity names (lowercase)
Facts about named entities that the user has introduced.

Examples:
- `subject="leo", attribute="prop:age", value="8 years old"`
- `subject="rex", attribute="prop:colour", value="golden"`

Entity names are always stored in lowercase. The entity name is the
subject — not a relationship label, not a sentence fragment.

---

## Rules

1. **Subject values are lowercase.** The KnowledgeEngine normalises on write,
   but callers must not rely on this — pass lowercase explicitly.

2. **Subject values are stable identifiers, not sentences.**
   `subject="leo"` is correct. `subject="remember that leo"` is a bug.

3. **`"user"` is singular.** There is one primary user per Jarvis instance.
   Multi-user support is not in scope; do not introduce `subject="user_2"` etc.

4. **`"jarvis"` is for system observations only.** Do not store user facts
   under `subject="jarvis"`.

5. **Entity names must be real names, not relationship labels.**
   `subject="leo"` is correct. `subject="son"` is not — relationship
   context belongs in the `category` and `attribute` fields.

---

## What this ADR does not cover

Subjects for external documents, web sources, or device state have not been
implemented and will be designed when a concrete use case exists.
Do not extrapolate from this ADR to invent new subject values.

---

## Consequences

- All new `store_memory()` calls must use one of the three established
  subject patterns above.
- The `PropertyAssigner` bug (storing `subject="remember that leo"`) is a
  known pre-existing issue logged for a future CFR. It is a bug to be fixed,
  not a pattern to be followed.
- Any future subject value outside these three patterns requires a new ADR.
