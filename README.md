# IntelliNotes

An agentic note-taking application with human-in-the-loop structuring. Paste code snippets or unstructured text, and AI will organize them into a proper folder structure with notes. You review, accept, reject, or provide feedback for revisions.

Snippet processing now runs through a LangGraph workflow: retrieve relevant library
sections → draft a refined create/update proposal → validate → human review. The AI
can propose inserting content into an existing Markdown section, explain placement,
or create a new note. The review screen shows complete new notes and a diff plus
before/after content for updates. Nothing is saved to the library until acceptance.

Retrieval uses semantic embeddings through LangChain's `OllamaEmbeddings`,
LangChain's `RecursiveCharacterTextSplitter`, and persisted pgvector search.
Relevant chunks from the current user's notes supply context to the configured LLM;
note changes queue reindexing. PostgreSQL needs the vector extension, Ollama needs
the `nomic-embed-text` model, and an indexing worker must process existing and changed
notes. See [semantic retrieval setup](backend/RAG.md), including reindexing after
the chunker upgrade. The earlier BM25 keyword ranker has been replaced.

Feedback reruns retrieval and validation with the original snippet and instructions.
The original snippet is retained. Refinement prompts preserve meaning and code
behavior; review remains necessary to assess AI output. Updates must reference a
retrieved note, its exact version, and unique edit anchors. Acceptance rechecks the
version and stored file before applying changes.

## Features

- **Authentication**: JWT-based auth with access/refresh tokens
- **Agentic Note Structuring**: Paste snippets → AI proposes folder/note structure → Human reviews → Accept/Reject/Feedback
- **Multi-LLM Support**: Ollama (local), OpenAI, Anthropic, OpenRouter
- **Flexible Storage**: Local filesystem or S3-compatible (MinIO, AWS S3, GCS)
- **Folder Management**: Hierarchical folders with path-based organization
- **Note Management**: Markdown notes with tags, search, and folder organization
- **Modern Stack**: FastAPI + Next.js 14 + TypeScript + Tailwind CSS

## Architecture

```
intellinotes/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/v1/         # API routes (auth, notes, folders, structuring)
│   │   ├── core/           # Config, security, exceptions
│   │   ├── domain/         # SQLAlchemy models
│   │   ├── application/    # Use cases, DTOs, ports (interfaces)
│   │   └── infrastructure/ # Adapters (DB, LLM, Storage, Repositories)
│   └── tests/
├── frontend/               # Next.js frontend
│   ├── src/
│   │   ├── app/            # App Router pages
│   │   ├── components/     # Reusable UI components
│   │   ├── features/       # Feature-specific logic
│   │   ├── lib/            # API client, utilities
│   │   └── types/          # TypeScript types
│   └── public/
└── docker-compose.yml
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) Ollama for local LLM: `curl -fsSL https://ollama.com/install.sh | sh`

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# Pull Ollama model (in another terminal)
docker-compose exec ollama ollama pull llama3.1

# View logs
docker-compose logs -f backend
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Ollama: http://localhost:11434

### Local Development

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Copy env and configure
cp .env.example .env
# Edit .env with your settings

# Run migrations (when alembic is set up)
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Configuration

### Backend Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `JWT_SECRET` | Secret for JWT signing | Required |
| `LLM_PROVIDER` | `ollama`, `openai`, or `anthropic` | `ollama` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `llama3.1` |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `STORAGE_TYPE` | `local` or `s3` | `local` |
| `LOCAL_STORAGE_PATH` | Path for local storage | `./data/notes` |
| `S3_BUCKET` | S3 bucket name | - |
| `S3_ENDPOINT_URL` | S3 endpoint (for MinIO) | - |

### Frontend Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_URL` | Backend API URL | `http://localhost:8000` |

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user
- `PATCH /api/v1/auth/me` - Update profile

### Folders
- `GET /api/v1/folders` - List folders (tree)
- `POST /api/v1/folders` - Create folder
- `GET /api/v1/folders/{id}` - Get folder
- `PATCH /api/v1/folders/{id}` - Update folder
- `DELETE /api/v1/folders/{id}` - Delete folder

### Notes
- `GET /api/v1/notes` - List notes (optional `folder_id`)
- `GET /api/v1/notes/search?q=` - Search notes
- `POST /api/v1/notes` - Create note
- `GET /api/v1/notes/{id}` - Get note
- `PATCH /api/v1/notes/{id}` - Update note
- `DELETE /api/v1/notes/{id}` - Delete note

### Structuring (Agentic)
- `POST /api/v1/structuring` - Create structuring proposal
- `GET /api/v1/structuring` - List proposals
- `GET /api/v1/structuring/{id}` - Get proposal
- `POST /api/v1/structuring/{id}/accept` - Accept proposal
- `POST /api/v1/structuring/{id}/reject` - Reject proposal
- `POST /api/v1/structuring/{id}/feedback` - Provide feedback for revision

## Agentic Workflow

1. **Input**: User pastes a code snippet or unstructured text
2. **AI Analysis**: LLM analyzes content and proposes:
   - Folder hierarchy
   - Note titles, content (markdown), folder placement, tags
3. **Review**: User sees visual tree of proposed structure
4. **Actions**:
   - **Accept**: Creates folders and notes in storage
   - **Reject**: Discards proposal
   - **Feedback**: Sends feedback to LLM for revision
   - **Regenerate**: Creates new proposal from same input

## Design Principles

- **Clean Architecture**: Domain → Application → Infrastructure → Interface
- **Dependency Inversion**: Ports (interfaces) in `application`, adapters in `infrastructure`
- **Strategy Pattern**: `LLMProvider` protocol for multiple LLM backends
- **Repository Pattern**: Abstract data access for testability
- **Single Responsibility**: Each use case = one class

## Development

### Running Tests

```bash
# Backend
cd backend
pytest

# The tests also run with Python's unittest runner:
DEBUG=false python -m unittest discover -s tests -v

# Frontend
cd frontend
npm run typecheck
npm run lint
```

### Code Style

- Backend: Ruff for linting/formatting, MyPy for type checking
- Frontend: ESLint + Prettier (via Next.js defaults)

## License

MIT

## Semantic RAG retrieval

The organization graph now retrieves indexed note chunks using local Ollama
embeddings and PostgreSQL pgvector instead of request-time keyword ranking.
Feedback reruns semantic retrieval before proposing new edits. See
[backend/RAG.md](backend/RAG.md) for pgvector setup, model download, the indexing
worker, existing-note backfill, status/reindex endpoints, and consistency limits.
The frontend and API run as before; the indexing worker runs separately.
