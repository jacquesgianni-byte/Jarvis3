# Jarvis Knowledge Engine

**Package:** `core.knowledge_engine`
**Sprint:** Genesis-011
**Status:** Production — Phase 1 (JSON storage)

---

## What is the Knowledge Engine?

The Knowledge Engine is the memory and knowledge layer for Jarvis OS.

It is not a simple key/value store. It is a structured, searchable, updatable knowledge layer that stores facts about the user and their world in a way that is organised, queryable, and meaningful.

> Memory is storage. Knowledge is memory that is organised, searchable, and usable.

The Knowledge Engine has no knowledge of the UI, voice pipeline, AI providers, or any other Jarvis subsystem. It only knows how to store, recall, search, update, and forget.

---

## The MemoryRecord

Every piece of knowledge is stored as a `MemoryRecord`. This is the fundamental unit of the Knowledge Engine.

```python
@dataclass
class MemoryRecord:
    id: str              # UUID — unique across all devices
    subject: str         # Who or what this fact is about
    category: str        # Organisational grouping
    attribute: str       # The property being described
    value: str           # The value of the attribute
    data_type: str       # Type hint for future typed memory support
    confidence: float    # 0.0 – 1.0. How certain Jarvis is.
    importance: float    # 0.0 – 1.0. How significant this memory is.
    visibility: Visibility   # private | shared | system
    source: MemorySource     # user | inferred | system
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    tags: list[str]
    notes: str | None
```

---

## The Subject / Attribute / Value Model

Memories are structured as facts about subjects, not abstract key/value pairs.

```
"Ludovic's favourite colour is blue."
 ────────   ────────────────   ────
 subject    attribute          value
```

This model allows Jarvis to answer natural questions:

| Question | Subject | Attribute |
|---|---|---|
| What is my wife's name? | `wife` | `name` |
| What printer do I have? | `printer` | `model` |
| What do I like to drink? | `user` | `favourite_drink` |
| Tell me about my son. | `son` | *(all attributes)* |

---

## Categories

Categories are the top-level organisational layer. Every memory belongs to exactly one category.

**Categories are not hardcoded in the engine.** They are defined in:

```
data/categories.json
```

To add a new category, edit that file. No code changes are required.

Default categories: `identity`, `preferences`, `relationships`, `occupation`, `devices`, `health`, `finance`, `projects`, `schedule`, `system`, `general`.

Each category defines default `importance` and `visibility` values that are inherited by memories when none are explicitly provided.

---

## The Storage Abstraction

The Knowledge Engine never touches the filesystem directly. All storage is handled through the `KnowledgeRepository` abstract interface:

```
KnowledgeEngine
      │
      ▼
KnowledgeRepository   ← abstract interface
      │
      ▼
JsonKnowledgeRepository   ← current implementation
```

This means the storage backend is completely swappable without changing the engine or any of its callers.

---

## Why JSON Today

Phase 1 uses a single JSON file at `data/knowledge.json`.

**Why JSON:**
- Zero dependencies — no database installation required
- Human-readable — easy to inspect and debug during development
- Sufficient for single-user, single-device use with hundreds of memories
- Loaded once into memory at startup, written on every mutation
- Atomic writes via `.tmp` file + `os.replace()` — no corruption on power loss

**Limitation:** JSON is not suitable beyond approximately 1,000–5,000 records. Full-table scans on every search become noticeably slow at that scale.

---

## When to Migrate to SQLite

Migrate when any of these conditions are met:

- Memory count exceeds ~1,000 records
- Search latency becomes noticeable (> 50ms)
- Multi-user profiles are introduced
- Cross-device sync requires a proper transaction layer

**Migration process:**
1. Implement `SQLiteKnowledgeRepository(KnowledgeRepository)`
2. Replace `JsonKnowledgeRepository` in the engine constructor
3. Write a one-time migration script to move `knowledge.json` → SQLite
4. No changes to `KnowledgeEngine`, `Agent`, or any other caller

The public API is identical regardless of backend.

---

## Public API

The Knowledge Engine exposes exactly six methods. No other module accesses storage directly.

```python
from core.knowledge_engine import KnowledgeEngine

engine = KnowledgeEngine()

# Store a new memory
record = engine.store_memory(
    subject="user",
    category="preferences",
    attribute="favourite_colour",
    value="blue",
    tags=["colour", "preference"]
)

# Recall a specific memory
record = engine.recall_memory(subject="user", attribute="favourite_colour")

# Search across memories
results = engine.search_memory(query="colour", subject="user")

# Update an existing memory
record = engine.update_memory(subject="user", attribute="favourite_colour", value="green")

# Forget a memory (soft delete by default)
engine.forget_memory(subject="user", attribute="favourite_colour")

# Forget permanently
engine.forget_memory(subject="user", attribute="favourite_colour", permanent=True)

# List all memories for a subject
memories = engine.list_memories(subject="user")
```

---

## Conflict Resolution Rules

| Scenario | Behaviour |
|---|---|
| Same fact stored twice | Second store triggers update automatically |
| User provides new value | Existing record updated, previous value preserved in `notes` |
| Inferred value conflicts with user value | User value always wins |
| Lower confidence conflicts with higher | Higher confidence value is preserved |

---

## Importance and Visibility

**Importance** (0.0 – 1.0) controls whether a memory is injected into AI prompts:

| Range | Behaviour |
|---|---|
| 0.9 – 1.0 | Always injected when relevant |
| 0.5 – 0.9 | Injected when topic matches |
| 0.0 – 0.5 | Stored but rarely auto-injected |

**Visibility** controls access:

| Value | Meaning |
|---|---|
| `private` | User's own session only (default) |
| `shared` | May be shared across profiles/devices |
| `system` | Jarvis configuration — never injected into prompts |

---

## Enums

Use enums rather than raw strings to avoid typos and casing bugs:

```python
from core.knowledge_engine import MemorySource, Visibility

engine.store_memory(
    subject="user",
    category="preferences",
    attribute="drink",
    value="coffee",
    source=MemorySource.USER,
    visibility=Visibility.PRIVATE
)
```

---

## Exceptions

All engine-specific exceptions inherit from `KnowledgeEngineError`:

```python
from core.knowledge_engine import (
    KnowledgeEngineError,    # base
    CategoryNotFoundError,   # unknown category id
    MemoryNotFoundError,     # required record not found
    StorageError,            # IO failure
    InvalidMemoryError,      # validation failure
    DuplicateMemoryError,    # attempted duplicate creation
)
```

---

## File Layout

```
core/
└── knowledge_engine/
    ├── __init__.py        Public exports
    ├── README.md          This file
    ├── models.py          MemoryRecord, MemorySource, Visibility
    ├── categories.py      CategoryLoader — reads data/categories.json
    ├── exceptions.py      All engine-specific exceptions
    ├── repository.py      KnowledgeRepository abstract interface
    ├── json_storage.py    JsonKnowledgeRepository — Phase 1 implementation
    └── engine.py          KnowledgeEngine — all business logic

data/
    knowledge.json         Live knowledge store
    categories.json        Category configuration

tests/
    test_knowledge_engine.py    Core API tests
    test_edge_cases.py          Boundary and failure tests
```

---

## Design Decisions Worth Preserving

**Why subject/attribute/value instead of key/value?**
Key/value is a dictionary. Subject/attribute/value is a fact. Facts can be queried by subject ("tell me about my printer"), by attribute ("what colour do I like?"), or by value. A dictionary cannot.

**Why UUIDs?**
When multi-device sync is introduced, every device needs to generate unique IDs without coordination. UUIDs make that trivial.

**Why store `notes` on update?**
Memories change over time. Without provenance, there is no way to know that a user's favourite colour was blue before it was green. Notes make the history auditable and potentially useful for future features.

**Why `importance` on every record?**
Prompt context windows are limited. When Jarvis answers a question, it cannot inject all 500 memories. Importance is what allows the engine to select the most relevant subset automatically, without hard rules.

---

*Jarvis Knowledge Engine — Genesis-011*
*"One Brain. Multiple Interfaces."*