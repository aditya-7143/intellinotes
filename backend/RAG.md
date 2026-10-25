# Semantic retrieval in the organization workflow

LangGraph still runs `retrieve -> draft -> validate`. Creation and feedback both
use the same semantic retriever. Keyword ranking has been removed from this flow.
The Library's ordinary text-search endpoint reads current Markdown files.

## Libraries

- `httpx`: the OpenRouter adapter calls `/api/v1/embeddings` using the existing
  `OPENROUTER_API_KEY`. The default model is `nvidia/nemotron-3-embed-1b:free`.
  Requests omit `dimensions` and use its native 2,048-dimensional vectors.
  `input_type` is `passage` for note chunks and `query` for searches. Chunk text
  is sent to the hosted provider. The free NVIDIA endpoint is intended for
  non-confidential data; see its model page for data-use terms.
- Optional `langchain-ollama`: `OllamaEmbeddings` handles async embedding requests through
  the maintained Ollama SDK. The application adapter adds Nomic's task prefixes,
  validates vectors, and converts provider errors to the API's error format.
- `langchain-text-splitters`: `RecursiveCharacterTextSplitter` splits long sections
  at paragraph, line, and word boundaries. UTF-8 byte sizing, zero overlap, and
  whitespace preservation keep chunks bounded and exact edit anchors intact.
  A small heading parser preserves section labels and fenced code boundaries.
- `pgvector`: persisted vector columns and cosine-distance search in PostgreSQL.
  Queries use the existing application tables to retain ownership/version checks.
- `langgraph`: orchestrates retrieval, generation, and validation before review.

Both embedding adapters implement the same application port; retrieval, workers,
and index status select the configured adapter through a factory.
After upgrading from a previous index format, restart the backend and worker and run
`POST /api/v1/index/reindex` for your account (or the worker's `--backfill` command
for all notes). The new `sections-v3-file-references` index identity prevents mixing old
and new chunk boundaries. Organization waits until indexing completes.

## Local setup

Run commands from `backend` with its virtual environment activated.

1. Install the updated Python dependencies:

   ```bash
   uv sync --extra dev
   ```

2. Install the **pgvector server extension** for your running PostgreSQL version.
   Installing the Python `pgvector` package alone does not install the extension.
   Follow <https://github.com/pgvector/pgvector#installation> for native PostgreSQL.
   The Docker Compose database now uses `pgvector/pgvector:pg16`. Preserve your
   existing database volume; do not delete it to enable the extension.

   On this Mac, `pg_config` currently reports PostgreSQL 14. Homebrew's pgvector
   bottle installs extension files for PostgreSQL 17/18, so `brew install pgvector`
   alone does **not** enable it for PostgreSQL 14. Build the extension against the
   matching `pg_config` following the upstream instructions, or use the Compose
   database. A PostgreSQL upgrade requires its own data migration; do not point a
   newer server at an existing PostgreSQL 14 data directory.

3. Configure hosted embeddings in `backend/.env`:

   ```bash
   EMBEDDING_PROVIDER=openrouter
   EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b:free
   # Set a valid OPENROUTER_API_KEY (the same key used for the LLM).
   ```

   Verify using a few synthetic sentences (this makes two hosted API calls):

   ```bash
   python -m app.infrastructure.embeddings.check
   ```

   HTTP 401 means authentication failed; check the configured key. HTTP 402 can
   indicate insufficient credits. No real note files are read by this smoke test.
   `EMBEDDING_BASE_URL` is optional and defaults to `OPENROUTER_BASE_URL` for this
   adapter. Remove any old localhost override when switching from Ollama.

   For optional local embeddings, set `EMBEDDING_PROVIDER=ollama`, set
   `EMBEDDING_MODEL=nomic-embed-text`, run Ollama, and pull that model. Its endpoint
   defaults to `OLLAMA_BASE_URL`. Restart API/worker and reindex after switching.

4. For an existing database with `notes.content`, stop the API and workers, back
   up the database and Markdown directory, then run:

   ```bash
   python -m app.infrastructure.database.migrate_file_storage
   ```

   This explicit migration verifies every Markdown file matches the legacy DB
   content before dropping the duplicate note/chunk text columns. Missing files
   or differences abort the transaction; reconcile them first. It clears derived
   vectors and queues every note for rebuilding. It never overwrites Markdown.
   Fresh databases do not need this step. Startup refuses the legacy schema with
   an actionable message instead of silently discarding data.

   If the database still has a `folders` table, run the folder migration next:

   ```bash
   python -m app.infrastructure.database.migrate_storage_folders
   ```

   It checks registered note files, materializes legacy directories (including
   empty ones), removes `notes.folder_id` and the `folders` table, and queues notes
   for reindexing because their version fingerprints changed. It refuses missing
   files or inconsistent file references. Directory creation is additive and
   idempotent; a failed migration may leave empty directories but does not delete
   note files. Database changes roll back on failure. Existing pending update
   proposals should be regenerated after migration because their versions changed.

   If the existing index uses 768 dimensions, run this next with API/workers stopped:

   ```bash
   python -m app.infrastructure.database.migrate_embedding_dimensions
   ```

   It clears only derived vector entries, changes the column to `vector(2048)`,
   and queues every registered note for rebuilding, all in one DB transaction.
   It does not modify Markdown, note metadata, or proposals. Rerunning against
   the current dimension is a no-op. Startup detects an incompatible column and
   asks for this migration instead of failing later during indexing.

   Start the backend:

   ```bash
   uvicorn app.main:app --reload --log-level debug
   ```

   Startup enables `vector` and creates missing tables. The database role
   needs permission to create the extension, or an administrator must run
   `CREATE EXTENSION IF NOT EXISTS vector;` once beforehand. Existing note tables
   and files are not dropped or rewritten.

5. In a separate terminal, index existing notes and keep processing changes:

   ```bash
   cd "/Users/adityawairkar/Desktop/Aditya Wairkar/projects/intellinotes/backend"
   source .venv/bin/activate
   python -m app.infrastructure.rag.worker --backfill
   ```

   Use `python -m app.infrastructure.rag.worker` on subsequent starts.
   `--once` processes a single available job and exits; `--backfill --once` queues
   all notes but only processes one, so it is not a complete backfill.

Compose loads credentials from `backend/.env` and uses OpenRouter by default.
The `index-worker` service processes new jobs. To index existing notes once,
run `docker compose exec index-worker python -m app.infrastructure.rag.worker --backfill --once`;
the regular worker then drains the remaining jobs.

Your chat model remains independently configured through `LLM_PROVIDER`.
OpenRouter embeddings reuse the chat API key. The default Nemotron `:free` route
is free; selecting another model may incur charges. There is no paid fallback.
Your actual `.env` is not edited by this change. New configuration defaults are
listed in `.env.example`.

## What is stored

- Markdown files are the source of truth. PostgreSQL `notes` stores metadata and
  storage keys, with no content column. Repository reads hydrate content from the
  storage port; ordinary text search scans those files (linear in library size).
- Folders are read from storage, not a database table. Local storage scans actual
  directories, including empty ones; S3 derives prefixes and uses trailing-slash
  markers for empty folders. Folder APIs use paths rather than UUIDs, and note
  create/update/filter requests use `folder_path`. Renames/moves update descendant
  note paths and storage keys and queue reindexing. Only empty folders may be
  deleted. Failed rename commits attempt to move the directory back; a process
  crash during a folder move still needs reconciliation. Perform renames through
  the app; external renames are not automatically mapped to existing note IDs.
- `note_sections` stores user/note IDs, heading, character start/end offsets,
  source version, embedding model identity, and a 2,048-dimensional vector by default. It
  contains no chunk body. Offsets refer to decoded UTF-8 text, not byte positions.
- Proposal drafts, review previews and acceptance receipts still contain text in
  `structuring_proposals` for the existing review/history workflow. These are
  snapshots, not the source used to read or index library notes.
- `note_index_jobs` stores durable indexing work, attempts, retry time, and leases.
  Errors store exception type only, not note contents or provider response bodies.

A note create/update invalidates its previous chunks and queues work in the same
database transaction. Deletion removes chunks and jobs. An indexing worker reads
Markdown through the storage port and splits it at headings, using LangChain to subdivide long sections into
UTF-8-safe chunks of up to 1,200 bytes. Each embedding includes bounded title/path/heading/tag
metadata. Only the optional Nomic/Ollama adapter uses `search_document:` and
`search_query:` prefixes; Nemotron receives plain text plus the explicit task type.

Long queries are embedded in bounded pieces and mean-pooled, so inputs are not
discarded before embedding. This can dilute relevance when a dump mixes many topics;
query decomposition is a future improvement. Inputs are bounded conservatively for
the embedding model. The optional LangChain Ollama integration uses the SDK's default
server truncation behavior; models with smaller context limits require adjusting
the chunk budget.

## Retrieval and consistency

The retriever uses pgvector cosine distance with user and embedding-model filters.
It fetches only matching note records, not every note in the library. Results are
loaded from their files and checked against current note versions before slices
are read using the stored offsets and passed into the LLM context. Feedback
includes the original input, original instructions, and current feedback in its
new semantic query. Approval still verifies versions again before applying edits.

Exact vector search is used initially. PostgreSQL user/note indexes support
filtering; an approximate HNSW index can be added after measuring library size
and recall. `RAG_MIN_SIMILARITY=0.3` is a starting threshold, not an evaluated
quality guarantee. `RAG_TOP_K=5` limits retrieved chunks.

If any note has a pending/failed job or lacks vectors for the selected model,
organization returns HTTP 409. It does not silently create duplicates from an
incomplete index or fall back to keyword search. A stale candidate also returns
409 and requires reindexing. Empty libraries can create their first proposal
without calling the embedding provider.

The worker scans registered note files every 30 seconds and queues changed files.
Between scans, stale retrieved candidates are rejected by the file-derived version
check; an externally changed file that did not match the old vectors may be missed
until the next scan. Missing files invalidate the index and eventually produce a
failed indexing job; restore the file or reconcile its metadata before reindexing.
The scanner does not discover unregistered Markdown or infer external renames.
Use app operations for creation/moves/deletion. Both API and worker must use the
same storage path/bucket; Compose mounts the same notes volume in both services.

Local saves use atomic replacement so readers never see partially written files.
Approval writes files, then commits metadata and indexing jobs; failures attempt
to restore files using the existing compensating transaction. A process crash
between file writes and DB commit still requires reconciliation. Database and
filesystem writes are not a single atomic transaction.

Authenticated maintenance endpoints (available at `/docs`):

- `GET /api/v1/index/status`: current user's note/index counts and pending/failed jobs.
- `POST /api/v1/index/reindex`: queue only the current user's notes and reset failures.

Jobs retry with exponential backoff, capped at 15 minutes. After eight attempts
by default they remain failed until requeued. A five-minute lease permits another
worker to recover a crashed claim. Claim tokens and note-version checks prevent
outdated workers from publishing over a newer generation. Index publication and
job completion happen atomically. These are indexing guarantees; the existing
Markdown/database acceptance crash-recovery limitation is unchanged.

Changing the embedding model requires restarting backend/worker processes and a
full reindex. The default OpenRouter/Nemotron size is 2,048; optional local
Ollama defaults to 768. `EMBEDDING_DIMENSIONS` can explicitly override validation
and schema size for another compatible configuration. This never truncates or
pads returned vectors. Run the dimension migration when changing sizes. Existing
vectors are not mixed with a different model/task identity. If a
model tag is updated in place, force a full reindex before further retrieval.

## Checks

```bash
python -m pytest tests -q
```

Tests mock embedding generation and database operations. They verify routing,
prefixes, the real LangChain adapter via a mock HTTP transport, exact chunk text,
vector validation, queue semantics, stale versions, and tenant filters.
They do not measure retrieval quality or replace a live PostgreSQL/Ollama check.
