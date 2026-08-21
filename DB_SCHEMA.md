# PostgreSQL Schema — Data Model Redesign

Working reference doc for the new Postgres data model. Details are being defined table-by-table; this file is the shared source of truth during the redesign.

- **Status**: complete (9 tables defined) — see Relationships summary + Migration notes below
- **Scope**: 9 required Postgres tables in `backend/models.py`
- **Related**: `backend/models.py`, `backend/state.py`, `backend/database.py`, `.env.example`

---

## Decisions (confirmed)

1. **Repo identity = normalized `repo_url` + per-commit `repo_hash`**; `repo_name` is display-only (derived from the URL), never used for lookups/scoping. Qdrant chunks carry `repo_url` (display) and `repo_hash` in their payload. **Qdrant scoping is hash-only**: every read (retrieval, BM25, symbol graph) filters by `repo_hash` alone — it is globally unique, so retained old-commit chunks never leak into a newer commit's results and no repo dimension is needed. No table changes result from this (9 tables stay).
2. **User ↔ repo linkage**: no join table. A user's repos are derived from their `conversations.repo_hash`.
3. **Ingestion progress**: the frontend poll is being replaced (streaming/SSE), so `pipeline_state` is not re-created. `indexed_repo.status` holds coarse state.
4. **Old-commit cleanup**: after a successful sync, old commits are soft-deleted via `indexed_repo.status = 'deleted'`. Only the commit's **cited chunks** (those referenced by a `citation` row) are retained in Qdrant; all other chunks are deleted via `VectorIndexer.delete_by_repo_hash`. `file_summary` + `repo_graph` for the tombstoned commit are deleted. `latest_indexed_repo_by_name` and `list_user_repos` skip `status='deleted'`.
5. **Citations are durable rows + message JSON.** The `citation` table (7th table) stores `(message_id, repo_hash, chunk_id, file/lines/symbol/language)`. A cited chunk is retained during cleanup precisely because its `chunk_id` appears in this table. The assistant `Message.citation` JSON stays as the UI-facing snapshot (no snippet stored). Deleting a message cascades its citations, making retained chunks eligible for later cleanup.
6. **`indexed_repo.status` allowed values**: `pending` | `indexing` | `indexed` | `syncing` | `failed` | `deleted`.

---

## Table 1 — `indexed_repo`

**Purpose**: Source of truth for all indexed repos **and their commits**. The same repo can exist multiple times (once per commit hash), so syncing a changed repo = inserting a new row with the new commit hash rather than overwriting.

**Design notes**:
- `id` is the surrogate primary key (every table has one).
- `repo_hash` is a **unique key** — identity = a specific commit of a repo. `repo_name` alone is **not** unique — uniqueness is on `repo_hash`.
- This is the enabler for the sync/diff feature: "same repo, different hashes" each become their own `indexed_repo` row.

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key (surrogate) |
| `repo_hash` | varchar(64) | no | — | **Unique key** — hash of this repo commit (e.g. git HEAD SHA) |
| `repo_url` | varchar(2048) | no | — | GitHub / repository URL |
| `repo_name` | varchar(255) | no | — | Repository name (not unique) |
| `file_count` | integer | no | 0 | Number of indexed files |
| `chunks_count` | integer | no | 0 | Number of generated chunks |
| `status` | varchar(50) | no | `indexed` | Indexing status |
| `created_at` | timestamptz | no | now() | When repo was added |
| `updated_at` | timestamptz | no | now() | Last update |

---

## Table 2 — `users`

**Purpose**: Application users.

**Design notes**:
- `id` is the surrogate primary key (every table has one).
- `clerk_id` is a **unique key** — the app-level user identity (referenced by `conversations.clerk_id`).
- Simplifies the current `users` table (which had `first_name`/`last_name`/`avatar_url`) down to a single `name`.
- "Nothing special here."

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key (surrogate) |
| `clerk_id` | varchar(255) | no | — | **Unique key** — Clerk user ID |
| `email` | varchar(255) | yes | — | User email |
| `name` | varchar(255) | yes | — | User's name |
| `created_at` | timestamptz | no | now() | Account creation time |
| `updated_at` | timestamptz | no | now() | Last update |

---

## Table 3 — `file_summary`

**Purpose**: Stores metadata/summary for individual files inside an indexed repository (per commit).

**Design notes**:
- `repo_hash` is a **foreign key** → `indexed_repo.repo_hash`. Summaries are scoped to a specific commit of a repo.
- Uniqueness per `(repo_hash, file_path)` (implied by "a file inside a repo").

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `repo_hash` | varchar(64) | no | — | **FK → `indexed_repo.repo_hash`** — identifier/hash of repository |
| `file_path` | varchar(1024) | no | — | Path of file (relative, within the repo) |
| `summary_text` | text | yes | — | Summary of the file |
| `created_at` | timestamptz | no | now() | Creation time |
| `updated_at` | timestamptz | no | now() | Last update |

---

## Table 4 — `repo_graph`

**Purpose**: Stores the repository dependency/code graph (symbol graph) for an indexed repo (per commit).

**Design notes**:
- `repo_hash` is a **foreign key** → `indexed_repo.repo_hash` and **UNIQUE** (`uq_repo_graph_repo_hash`) — one graph per commit. Graph is scoped to a specific commit of a repo.
- Replaces the current `repo_graphs` table (which was keyed by `repo_name` only, no commit).

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `repo_hash` | varchar(64) | no | — | **FK → `indexed_repo.repo_hash`** — repository identifier |
| `build_at` | timestamptz | no | now() | When the graph was built |
| `graph_json` | json | no | — | Repository dependency/code graph |

---

## Table 5 — `conversations`

**Purpose**: Chat-memory / conversation table.

**Design notes**:
- `clerk_id` is a **foreign key** → `users.clerk_id` (user owning the conversation).
- `repo_hash` is a **foreign key** → `indexed_repo.repo_hash` (repository/commit associated with the conversation).
- **Sync behavior**: when a repo is synced, simply **update `repo_hash` to point to the new hash** — the conversation keeps its chat history but now references the newly indexed commit.

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `clerk_id` | varchar(255) | no | — | **FK → `users.clerk_id`** — user owning the conversation |
| `repo_hash` | varchar(64) | no | — | **FK → `indexed_repo.repo_hash`** — repository associated with the conversation (points to the latest commit after sync) |
| `title` | varchar(500) | yes | `New chat` | Conversation title |
| `created_at` | timestamptz | no | now() | Conversation creation |
| `updated_at` | timestamptz | no | now() | Last activity |

---

## Table 6 — `messages`

**Purpose**: Stores individual messages inside a conversation.

**Design notes**:
- `conversation_id` is a **foreign key** → `conversations.id`.
- `role` is `user` or `assistant`.
- Replaces the current `messages` table (`citations` JSON → renamed `citation`).

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `conversation_id` | uuid | no | — | **FK → `conversations.id`** — conversation this message belongs to |
| `role` | varchar(20) | no | — | `user` / `assistant` |
| `content` | text | no | — | Actual message |
| `citation` | json | yes | — | Citation data |
| `repo_hash` | varchar(64) | yes | — | Commit the message was sent/answered against (the sync-boundary divider reads this) |
| `created_at` | timestamptz | no | now() | Message timestamp |

---

## Table 7 — `citation`

**Purpose**: Durable record of every `[C1]`-style citation in a message. Primary driver of the "retain cited chunks" cleanup rule — a chunk stays alive while a `citation` row references its `chunk_id`.

**Design notes**:
- `message_id` is a **foreign key** → `messages.id` ON DELETE CASCADE (citation dies with its message).
- `repo_hash` is a **foreign key** → `indexed_repo.repo_hash` ON DELETE **RESTRICT** (blocks deleting a commit that still has citations — safety net for cleanup).
- No snippet / no repo_name / no conversation_id (kept minimal by design).
- The UI-facing citation snapshot remains on `Message.citation` (JSON) — this table is for durability + cleanup.
- Unique per `(message_id, citation_id)`.

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `message_id` | uuid | no | — | **FK → `messages.id`**, ON DELETE CASCADE |
| `citation_id` | varchar(16) | no | — | the `[C1]` label; unique with `message_id` |
| `repo_hash` | varchar(64) | yes | — | **FK → `indexed_repo.repo_hash`**, ON DELETE RESTRICT |
| `chunk_id` | varchar(64) | no | — | Qdrant point id of the cited chunk (indexed) |
| `file_path` | varchar(1024) | no | — | relative path |
| `start_line` / `end_line` | int | no | — | as cited at the time |
| `symbol` | varchar(255) | yes | — | function/class name when present |
| `language` | varchar(50) | yes | — | |
| `created_at` | timestamptz | no | now() | |

Indexes: `chunk_id`, `repo_hash`, `message_id`.

---

## Table 8 — `conversation_summaries`

**Purpose**: Rolling per-conversation summary for **short-term memory** (chat memory feature). Maintained by the background ARQ summarizer (`memory/worker.py`); `last_message_id` is the watermark — the summarizer merges messages created after it into `summary_content`.

**Design notes**:
- `conversation_id` is a **foreign key** → `conversations.id` ON DELETE CASCADE, **unique** (one summary per conversation).
- `last_message_id` is a plain UUID watermark (no FK) — the summarizer resumes from it.
- Read path: when a conversation's raw history exceeds the token budget, the stored summary replaces the older turns (see `memory/short_term.py`).

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `conversation_id` | uuid | no | — | **FK → `conversations.id`** ON DELETE CASCADE, **unique** |
| `summary_content` | text | no | — | Rolling recap of the conversation so far |
| `total_tokens_covered` | int | no | 0 | Tokens summarized so far |
| `last_message_id` | uuid | yes | — | Watermark — resume point for the summarizer |
| `updated_at` | timestamptz | no | now() | Last summary update |

## Table 9 — `usage_events`

**Purpose**: One row per cost-bearing action a user performs, backing the 24h per-user usage caps (`backend/usage.py`). Append-only; expired rows are purged opportunistically on each `record_usage`.

**Design notes**:
- `clerk_id` + `action` + `created_at` — no FK (users are also keyed by `clerk_id` in `users`, but usage is a fire-and-forget ledger; a missing user row must not block recording).
- The composite index `ix_usage_events_clerk_action_time` serves the exact cap query: `WHERE clerk_id = ? AND action IN (...) AND created_at >= now() - window`.
- Counting is Postgres-side, so caps are correct across uvicorn workers and need no Redis (per `SCALE.md`).

| Column | Type (proposed) | Null | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | no | uuid4 | Primary key |
| `clerk_id` | varchar(255) | no | — | User (Clerk id) the action is attributed to |
| `action` | varchar(50) | no | — | Cost-bearing action (`repo_ingest` / `repo_sync` / `chat_message` / `explain`) |
| `created_at` | timestamptz | no | now() | When the action spent budget |

Indexes: composite `(clerk_id, action, created_at)`.

## Relationships summary

```
users (id PK; clerk_id UNIQUE)
  ├── conversations.clerk_id  → users.clerk_id
  │     ├── messages.conversation_id → conversations.id
  │     │     └── citation.message_id → messages.id        (durable citations; drives retention)
  │     └── conversation_summaries.conversation_id → conversations.id   (rolling short-term memory)
  │
indexed_repo (id PK; repo_hash UNIQUE)   ← "same repo, different hashes"
  ├── file_summary.repo_hash  → indexed_repo.repo_hash   (per-commit file summaries)
  ├── repo_graph.repo_hash    → indexed_repo.repo_hash   (per-commit graph)
  ├── conversations.repo_hash → indexed_repo.repo_hash   (updated on sync → new hash)
  └── citation.repo_hash      → indexed_repo.repo_hash   (RESTRICT; retains cited chunks)

usage_events (id PK; clerk_id + action + created_at)   ← standalone ledger, no FK
```

## Migration notes (current → new)

| Current table | New table | Change |
|---|---|---|
| `user_repos` | `indexed_repo` | `id` surrogate PK + `repo_hash` UNIQUE; one row per commit; `user_id` linkage moves to conversations via `clerk_id` |
| `users` | `users` | `id` surrogate PK; `clerk_id` becomes UNIQUE; `first_name`/`last_name`/`avatar_url` → single `name` |
| `file_summaries` | `file_summary` | keyed by `repo_hash` (was `repo_name`) |
| `repo_graphs` | `repo_graph` | keyed by `repo_hash` (was `repo_name`) |
| `conversations` | `conversations` | `user_id` → `clerk_id`; `repo_name`/`repo_url` → `repo_hash` |
| `messages` | `messages` | `citations` → `citation` |
| `pipeline_state` | dropped | — |
| `qa_records` | dropped | — |
| — | `citation` | new — durable per-message citations for retention/cleanup |
| — | `conversation_summaries` | new — rolling short-term memory summary (chat-memory feature) |
| — | `usage_events` | new — per-user cost-bearing action ledger for the 24h usage caps |
