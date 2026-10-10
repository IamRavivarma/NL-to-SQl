# RAG Data Assistant

Upload PDF, TXT or DOCX documents and ask questions about them. Answers are grounded in your documents, cite file and page, and stream in real time from Groq. A dashboard charts response speed and usage.

**Stack:** React (Vite) · Tailwind CSS · Recharts · FastAPI · MongoDB Atlas (Beanie) · Atlas Vector Search · LangChain + LangGraph · Groq · HuggingFace `all-MiniLM-L6-v2`

## How it works

1. **Upload** (`POST /api/upload`) — text is extracted, split into ~1000-character chunks, embedded locally with `all-MiniLM-L6-v2` (384 dims) and stored in the `chunks` collection with Atlas Vector Search.
2. **Ask** (`POST /api/query`) — a LangGraph graph runs **retrieve** (vector search, top 4 chunks) → **generate** (ChatGroq with the chunks as context). Tokens stream to the browser as Server-Sent Events.
3. **Measure** — time to first token and tokens/second are stored with every answer and shown on the dashboard.

**Model note:** the original brief named `llama3-70b-8192`. Groq has retired its Llama chat models, so the app uses `openai/gpt-oss-120b` (set by `GROQ_MODEL`).

## Setup

**Requirements:** Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node.js 20+, a free [MongoDB Atlas](https://www.mongodb.com/atlas) M0 cluster, a free [Groq API key](https://console.groq.com/keys).

1. Atlas: create an M0 cluster, a database user, and allow your IP (Network Access). Copy the connection string (Connect → Drivers).
2. Backend:
   ```bash
   cd backend
   cp .env.example .env      # fill MONGODB_URI and GROQ_API_KEY
   uv sync
   .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000   # macOS/Linux: .venv/bin/python
   ```
   On first start the backend creates the `vector_index` Atlas Vector Search index (takes up to a minute to become active). If that fails, the log prints the index JSON to create it manually in the Atlas UI (Atlas Search → Create Index → Vector Search, collection `chunks`).
3. Frontend:
   ```bash
   cd frontend
   cp .env.example .env
   npm install
   npm run dev
   ```
   Open http://localhost:5173.

## Tests

```bash
cd backend && .venv/Scripts/python.exe -m pytest   # integration tests use <MONGODB_DB>_test and are skipped without MONGODB_URI
cd frontend && npm test
```
