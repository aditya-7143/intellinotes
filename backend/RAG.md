# Semantic retrieval in the organization workflow

LangGraph still runs `retrieve -> draft -> validate`. Creation and feedback both
use the same semantic retriever. Keyword ranking has been removed from this flow.
The Library's ordinary text-search endpoint is unchanged.

## Libraries

- `langchain-ollama`: `OllamaEmbeddings` handles async embedding requests through
  the maintained Ollama SDK. The application adapter adds Nomic's task prefixes,
  validates vectors, and converts provider errors to the API's error format.
- `langchain-text-splitters`: `RecursiveCharacterTextSplitter` splits long sections
  at paragraph, line, and word boundaries. UTF-8 byte sizing, zero overlap, and
  whitespace preservation keep chunks bounded and exact edit anchors intact.
  A small heading parser preserves section labels and fenced code boundaries.
- `pgvector`: persisted vector columns and cosine-distance search in PostgreSQL.
  Queries use the existing application tables to retain ownership/version checks.
- `langgraph`: orchestrates retrieval, generation, and validation before review.

There is no custom keyword relevance algorithm or embedding HTTP client in this flow.
After upgrading from the previous chunker, restart the backend and worker and run
`POST /api/v1/index/reindex` for your account (or the worker's `--backfill` command
for all notes). The new `sections-v2-langchain` index identity prevents mixing old
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

3. Run Ollama and download the embedding model:

   ```bash
   ollama serve
   ```

   In another terminal:

   ```bash
   ollama pull nomic-embed-text
   ```

4. Start the backend normally:

   ```bash
   uvicorn app.main:app --reload --log-level debug
   ```

   Startup enables `vector` and creates the two new tables. The database role
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

For Compose, run `docker compose exec ollama ollama pull nomic-embed-text`.
The `index-worker` service processes new jobs. To index existing notes once,
run `docker compose exec index-worker python -m app.infrastructure.rag.worker --backfill --once`;
the regular worker then drains the remaining jobs.

Your chat model remains independently configured through `LLM_PROVIDER`.
No embedding API key or paid embedding service is required with local Ollama.
Your actual `.env` is not edited by this change. New configuration defaults are
listed in `.env.example`.

## What is stored

- PostgreSQL `notes` remains the source used to plan edits; Markdown storage is unchanged.
- `note_sections` stores user/note IDs, heading, exact chunk text, note version,
  embedding model identity, and a 768-dimensional vector.
- `note_index_jobs` stores durable indexing work, attempts, retry time, and leases.
  Errors store exception type only, not note contents or provider response bodies.

A note create/update invalidates its previous chunks and queues work in the same
database transaction. Deletion removes chunks and jobs. An indexing worker splits
changed notes at Markdown headings, using LangChain to subdivide long sections into
UTF-8-safe chunks of up to 1,200 bytes. Each embedding includes bounded title/path/heading/tag
metadata and uses Nomic's `search_document:` prefix. Queries use `search_query:`.

Long queries are embedded in bounded pieces and mean-pooled, so inputs are not
discarded before embedding. This can dilute relevance when a dump mixes many topics;
query decomposition is a future improvement. Inputs are bounded conservatively for
the configured Nomic model. LangChain's Ollama integration uses the SDK's default
server truncation behavior; models with smaller context limits require adjusting
the chunk budget.

## Retrieval and consistency

The retriever uses pgvector cosine distance with user and embedding-model filters.
It fetches only matching note records, not every note in the library. Results are
checked against current note versions before entering the LLM context. Feedback
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
full reindex. Use a Nomic-compatible 768-dimensional model; other dimensions are
rejected. Existing vectors are not mixed with a different model identity. If a
model tag is updated in place, force a full reindex before further retrieval.

## Checks

```bash
python -m pytest tests -q
```

Tests mock embedding generation and database operations. They verify routing,
prefixes, the real LangChain adapter via a mock HTTP transport, exact chunk text,
vector validation, queue semantics, stale versions, and tenant filters.
They do not measure retrieval quality or replace a live PostgreSQL/Ollama check.
