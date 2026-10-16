# RAG Data Assistant

Upload PDF, TXT or DOCX documents and ask questions about them in plain English. Every answer is built only from your documents, cites the file and page it came from, and streams into the browser word by word from Groq's LPU inference. A dashboard measures how fast each answer arrives.

![Chat screen](docs/screenshots/chat.png)

![Dashboard](docs/screenshots/dashboard.png)

## Features

- **Document upload** — PDF, TXT (UTF-8, UTF-16, Windows-1252) and DOCX up to 20 MB, by drag-and-drop or file picker. Uploads are all-or-nothing: a failed upload never leaves half a document behind.
- **Grounded answers with citations** — answers quote `[file p.N]`, list their sources as chips that expand to the exact excerpt, and say *"I couldn't find that in your documents."* instead of guessing.
- **Streaming** — tokens arrive over Server-Sent Events as Groq generates them.
- **Conversations** — saved in MongoDB; follow-up questions understand the earlier turns.
- **Speed dashboard** — time to first word, total time and tokens/second for every answer, plus usage charts (Recharts).

## How it maps to the brief

| Brief | Implementation |
|---|---|
| React (Vite), Tailwind CSS, Recharts | `frontend/` — React 19, Vite, Tailwind CSS v4, Recharts dashboard |
| FastAPI (Python 3.10+) | `backend/app/` — FastAPI on Python 3.11+ (required by `langchain-mongodb`) |
| MongoDB with Beanie or Motor | Beanie models for documents, conversations and messages (`backend/app/models/`) |
| MongoDB Atlas Vector Search | `chunks` collection + `vector_index` (384-dim, cosine), created automatically on startup |
| LangChain / LangGraph agent with ChatGroq | LangGraph graph **retrieve → generate** (`backend/app/rag/graph.py`) using `langchain-groq` |
| HuggingFace `all-MiniLM-L6-v2` via sentence-transformers | Local embeddings (`backend/app/rag/embeddings.py`) |
| Groq Llama 3 (`llama3-70b-8192`) | **`openai/gpt-oss-120b`** — see the model note below |
| Responses streamed to the frontend | `POST /api/query` streams `meta → token… → done` events |

**Model note:** Groq has retired its Llama 3 chat models (`llama3-70b-8192`, `llama3-8b-8192`, `llama-3.3-70b-versatile`), so the app uses `openai/gpt-oss-120b`, a large open-weight model also served on Groq LPUs. The model is a setting (`GROQ_MODEL`), so it can be changed without code changes.

## How it works

```
Upload:  file ──► extract text per page ──► split (1000 chars, 150 overlap) ──► embed (MiniLM, 384-d) ──► Atlas `chunks`
Ask:     question ──► LangGraph: retrieve (Atlas $vectorSearch, top 4) ──► generate (ChatGroq) ──► SSE tokens ──► browser
Measure: each answer stores time-to-first-word, total time and tokens/sec ──► GET /api/stats ──► dashboard
```

| Endpoint | Purpose |
|---|---|
| `POST /api/upload` | Upload and index a document |
| `GET /api/documents`, `DELETE /api/documents/{id}` | List / delete documents (and their chunks) |
| `POST /api/query` | Ask a question; streams Server-Sent Events |
| `GET /api/conversations`, `GET`/`DELETE /api/conversations/{id}` | Conversation history |
| `GET /api/stats` | Dashboard data |
| `GET /health` | Health check |

## Project structure

```
backend/
  app/
    api/         HTTP endpoints (upload, documents, query/SSE, conversations, stats)
    ingestion/   file loaders and the upload pipeline
    rag/         embeddings, Atlas vector store, prompts, LangGraph graph
    models/      Beanie documents
    core/        settings and database connections
  tests/         pytest suite (unit + MongoDB integration tests)
frontend/
  src/components/  Sidebar, chat, message cards, dashboard
  src/services/    API client and SSE stream parser
docs/            design spec, implementation plan, screenshots
```

## Setup

**Requirements:** Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 20+, a free [MongoDB Atlas](https://www.mongodb.com/atlas) M0 cluster, and a free [Groq API key](https://console.groq.com/keys).

1. **Atlas:** create an M0 cluster and a database user, allow your IP under *Network Access*, and copy the connection string (*Connect → Drivers*).
2. **Backend** (first terminal):
   ```powershell
   cd backend
   copy .env.example .env      # then fill in MONGODB_URI and GROQ_API_KEY
   uv sync
   .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
   ```
   Wait for `Application startup complete`. On first start the backend creates the Atlas vector index; it takes about a minute to become active.
3. **Frontend** (second terminal):
   ```powershell
   cd frontend
   copy .env.example .env
   npm install
   npm run dev
   ```
4. Open **http://localhost:5173**, upload a document, and ask a question. The first question after starting takes 10–15 seconds while the embedding model loads.

**If the backend can't reach Atlas** with a `mongodb+srv://` address (DNS errors such as *"The DNS query name does not exist"* or *"resolution lifetime expired"*), your network is blocking DNS SRV lookups. Use Atlas's standard address instead — *Connect → Drivers*, choose an older driver version — which lists the three servers directly (`mongodb://user:pass@host-00:27017,host-01:27017,host-02:27017/?tls=true&replicaSet=…&authSource=admin`).

## Configuration (`backend/.env`)

| Variable | Required | Default |
|---|---|---|
| `MONGODB_URI` | yes | — |
| `MONGODB_DB` | no | `rag_assistant` |
| `GROQ_API_KEY` | yes | — |
| `GROQ_MODEL` | no | `openai/gpt-oss-120b` |
| `EMBEDDING_MODEL` | no | `sentence-transformers/all-MiniLM-L6-v2` |

## Tests

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest   # 61 tests; integration tests use <MONGODB_DB>_test, skipped without MONGODB_URI
cd frontend; npm test                              # 17 tests
```

## Design documents

- [Design spec](docs/specs/2026-10-10-rag-assistant-design.md)
- [Implementation plan](docs/plans/2026-10-10-rag-assistant-plan.md)

The repository history also contains an earlier natural-language-to-SQL prototype (branch `worktree-nl-to-sql-implementation`, spec in `docs/specs/2026-08-09-nl-to-sql-dashboard-design.md`), which this RAG assistant replaced to match the project brief.
