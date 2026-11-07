# RAG Data Assistant

Upload PDF, TXT, DOCX, CSV or Excel (.xlsx) files and ask questions about them in plain English. Every answer is built only from your documents, cites the file and page it came from, and streams into the browser word by word from Groq's LPU inference. A dashboard measures how fast each answer arrives.

![Chat screen](docs/screenshots/chat.png)

![Dashboard](docs/screenshots/dashboard.png)

## Quick start

The project is already set up (dependencies installed, `backend/.env` filled in), so starting it only needs two terminals.

**Terminal 1: backend**
```powershell
cd "C:\Storage\PROJECTS\College\NL to SQL\backend"
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

**Terminal 2: frontend**
```powershell
cd "C:\Storage\PROJECTS\College\NL to SQL\frontend"
npm run dev
```

Open **http://localhost:5173**. Keep both terminals open while using the app; press `Ctrl+C` in each to stop it.

If port 8000 is already used by another app, run the backend with `--port 8001` and start the frontend with:
```powershell
$env:VITE_API_BASE_URL="http://localhost:8001"; npm run dev
```

On a new computer, follow [Setup](#setup) first.

## What was done in this project

In simple terms, this is a "chat with your documents" app: you upload files, ask questions, and the AI answers using only what is written in those files, showing the page it found the answer on.

1. **Reading documents.** The backend extracts text page by page from PDF, TXT and Word files, and row by row from CSV and Excel files (each row keeps its column names), then cuts it into small overlapping pieces (chunks).
2. **Making text searchable by meaning.** Each chunk is turned into a list of 384 numbers (an *embedding*) by a small AI model that runs on your own computer. Chunks with similar meaning get similar numbers, so "holidays" can match "annual leave".
3. **Storing it in the cloud.** Chunks, numbers, file names and page numbers are saved in MongoDB Atlas, which can find the closest chunks to a question (Vector Search).
4. **Answering questions.** A LangGraph workflow finds the 4 most relevant chunks, then sends them with the question to a fast AI model on Groq. The model is told to answer only from those chunks, cite them as `[file p.N]`, and say *"I couldn't find that in your documents."* when the answer isn't there.
5. **Natural language to SQL.** Spreadsheets (CSV/Excel) are also loaded into SQL tables. For a question about them ("total revenue in Q2?"), the AI writes a SQL query, the app runs it read-only, and the chat shows the **SQL query and its results table** above the answer, so totals, counts and "top 5" questions are exact. For PDF, Word and text questions the chat shows the real **MongoDB search query** and the passages it found.
6. **Live streaming.** The answer appears in the browser word by word as it is generated.
7. **Web interface.** A React page with drag-and-drop upload, a document list, saved conversations, clickable source chips that show the exact excerpt, and a dashboard with speed and usage charts.
8. **Testing.** 125 backend tests and 22 frontend tests, plus a full end-to-end check against the real Atlas database and Groq.

Problems solved along the way:
- Groq retired the Llama 3 model named in the brief, so the app uses `openai/gpt-oss-120b`, and the model is now a setting.
- The speed chart first showed impossible numbers because the model "thinks" before writing; speed is now measured from the start of generation.
- The network blocked Atlas's usual address lookup, so the app uses Atlas's direct server address.
- A failed upload could leave leftover pieces in the database; uploads are now all-or-nothing.

## Features

- **Document upload** — PDF, TXT (UTF-8, UTF-16, Windows-1252), DOCX, CSV and Excel `.xlsx` up to 20 MB, by drag-and-drop or file picker. Spreadsheet rows are stored as `Column: value | Column: value` lines so every chunk keeps its column names; each Excel sheet counts as a page, so citations point to the sheet number. Old `.xls` files must be saved as `.xlsx` first. Uploads are all-or-nothing: a failed upload never leaves half a document behind.
- **Query panel (NL-to-SQL)** — every answer shows the database query behind it with a results table: AI-written SQL for questions about uploaded spreadsheets (one read-only `SELECT`, 5-second limit, one automatic retry with the error), or the MongoDB `$vectorSearch` pipeline and retrieved passages for documents. Spreadsheets uploaded before this feature need to be uploaded again to get their SQL tables.
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
         CSV/XLSX rows also ──► SQLite tables (`backend/data/tables.db`)
Ask:     question ──► LangGraph: plan_sql (ChatGroq writes SQL if the question is about a spreadsheet; run read-only)
                       ├─ SQL worked ──────────────────────────────► generate from the result rows
                       └─ otherwise ──► retrieve (Atlas $vectorSearch, top 4) ──► generate from the excerpts
         ──► SSE: meta (queries + sources) → tokens → done ──► browser shows query panel + streamed answer
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
    sql/         SQLite table store and the SQL planner
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
| `SQLITE_PATH` | no | `data/tables.db` (spreadsheet rows as SQL tables) |

## Tests

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest   # 125 tests; integration tests use <MONGODB_DB>_test, skipped without MONGODB_URI
cd frontend; npm test                              # 22 tests
```

## Design documents

- [Design spec](docs/specs/2026-10-10-rag-assistant-design.md)
- [Implementation plan](docs/plans/2026-10-10-rag-assistant-plan.md)
- [Query panel (NL-to-SQL) design](docs/specs/2026-11-07-query-panel-design.md)
- [Query panel implementation plan](docs/plans/2026-11-07-query-panel-plan.md)
