# RAG Data Assistant — Design

## Overview

A single-user web app where a user uploads unstructured documents (PDF, TXT, DOCX) and asks questions about them. The FastAPI backend splits each document into chunks, embeds them locally with HuggingFace `all-MiniLM-L6-v2`, and stores them in **MongoDB Atlas Vector Search**. A **LangGraph** retrieve → generate graph finds the most relevant chunks and **ChatGroq** writes a grounded answer that is **streamed** token by token to the React frontend, with source citations. A **Recharts** dashboard shows usage and speed metrics (Groq latency and tokens/second), demonstrating the "lightning-fast inference" goal.

This replaces an earlier NL-to-SQL prototype.

### In scope
- Upload, list, delete documents (PDF, TXT, DOCX; ≤ 20 MB each)
- Chunking, local embeddings, Atlas vector storage and search
- Streaming answers with citations (filename, page, snippet) and "not found" handling
- Multiple saved conversations with short-term context (last 6 messages)
- Per-answer speed metrics and a Recharts usage/speed dashboard

### Out of scope
- Scanned/image-only PDFs (OCR), other file types
- Authentication / multi-user
- Restricting a question to selected documents
- Query rewriting for follow-ups (retrieval uses the current question only)

## Tech Stack

| Concern | Choice |
|---|---|
| Frontend | React (Vite), Tailwind CSS, Recharts, `react-markdown` |
| Backend | FastAPI, Python 3.10+ (managed with `uv`) |
| Database | MongoDB Atlas, database `MONGODB_DB` (default `rag_assistant`) |
| ODM | Beanie (async) for app collections |
| Vector store | MongoDB Atlas Vector Search via `langchain-mongodb` (`MongoDBAtlasVectorSearch`) |
| Orchestration | LangChain + LangGraph |
| LLM | Groq API via `langchain-groq`; model from `GROQ_MODEL`, default `openai/gpt-oss-120b` |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` (384 dims) via `langchain-huggingface`, run locally |
| Loaders / splitting | `PyPDFLoader`, `TextLoader`, `Docx2txtLoader`; `RecursiveCharacterTextSplitter` (1000 chars, 150 overlap) |

**Model note (for the report):** the brief names `llama3-70b-8192` / `llama3-8b-8192`. Groq has retired all Llama chat models; the account's available models are `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, and non-chat models. `openai/gpt-oss-120b` is the closest equivalent (large, open-weight, served on Groq LPUs). The model is a setting, so it can be changed without code changes.

**Embedding fallback:** sentence-transformers requires PyTorch. Windows Smart App Control on the dev machine has blocked a native Python DLL before. The first implementation task verifies PyTorch loads; if it is persistently blocked, the same `all-MiniLM-L6-v2` model is run through `fastembed` (ONNX, `langchain-community` `FastEmbedEmbeddings`) behind the same `get_embeddings()` function. Nothing else changes.

## Configuration (`backend/.env`)

| Variable | Required | Default |
|---|---|---|
| `MONGODB_URI` | yes | — |
| `MONGODB_DB` | no | `rag_assistant` |
| `GROQ_API_KEY` | yes | — |
| `GROQ_MODEL` | no | `openai/gpt-oss-120b` |
| `EMBEDDING_MODEL` | no | `sentence-transformers/all-MiniLM-L6-v2` |

`.env.example` documents all of them. Frontend: `VITE_API_BASE_URL` (default `http://localhost:8000`).

## Data Model (MongoDB)

**`documents`** (Beanie `Document`)

| Field | Type | Notes |
|---|---|---|
| filename | str | original name |
| file_type | str | `pdf` / `txt` / `docx` |
| size_bytes | int | |
| page_count | int | 1 for TXT/DOCX |
| chunk_count | int | |
| uploaded_at | datetime (UTC) | |

**`chunks`** (managed by `MongoDBAtlasVectorSearch`)

```json
{ "text": "...", "embedding": [384 floats],
  "document_id": "<documents._id as string>", "filename": "report.pdf", "page": 3, "chunk_index": 17 }
```
`page` is 1-based (always 1 for TXT/DOCX).

**Atlas vector index** `vector_index` on `chunks`, created at startup if missing:
```json
{ "fields": [ { "type": "vector", "path": "embedding", "numDimensions": 384, "similarity": "cosine" } ] }
```
If creation fails, startup logs a warning including this JSON for manual creation in the Atlas UI.

**`conversations`** (Beanie)

| Field | Type | Notes |
|---|---|---|
| title | str | first question, truncated to 60 chars |
| created_at, updated_at | datetime | |

**`messages`** (Beanie)

| Field | Type | Notes |
|---|---|---|
| conversation_id | PydanticObjectId | indexed |
| role | `"user"` / `"assistant"` | |
| content | str | |
| sources | list[{filename, page, snippet}] | assistant only |
| metrics | {model, ttft_ms, total_ms, output_tokens, tokens_per_sec, chunks_retrieved} \| null | assistant only |
| status | `"complete"` / `"error"` | assistant only |
| created_at | datetime | |

## Backend Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, lifespan (Beanie init, vector index), CORS, routers
│   ├── core/
│   │   ├── config.py        # pydantic-settings
│   │   └── database.py      # Mongo client, init_beanie, chunks collection handle
│   ├── models/              # Beanie documents: document.py, conversation.py, message.py
│   ├── ingestion/
│   │   ├── loaders.py       # bytes + filename -> list[Page(text, page_number)]; validation
│   │   └── pipeline.py      # split, embed+store chunks, create document record; rollback on failure
│   ├── rag/
│   │   ├── embeddings.py    # get_embeddings(): cached
│   │   ├── vector_store.py  # get_vector_store(), ensure_vector_index(), delete_chunks(document_id)
│   │   ├── prompts.py       # system prompt
│   │   └── graph.py         # LangGraph: retrieve -> generate; stream_answer() async generator
│   └── api/
│       ├── upload.py        # POST /api/upload
│       ├── documents.py     # GET /api/documents, DELETE /api/documents/{id}
│       ├── query.py         # POST /api/query (SSE)
│       ├── conversations.py # GET list / GET one / DELETE
│       └── stats.py         # GET /api/stats
├── tests/
├── pyproject.toml
└── .env.example
```

Each unit has one job: `loaders` knows file formats, `pipeline` owns ingestion consistency, `vector_store` is the only module touching the `chunks` collection, `graph` owns retrieval + generation, and API modules only translate HTTP.

## API

| Method & path | Request | Response |
|---|---|---|
| `POST /api/upload` | multipart `file` | `201 {id, filename, file_type, page_count, chunk_count}`; `400` invalid file |
| `GET /api/documents` | — | list of documents, newest first |
| `DELETE /api/documents/{id}` | — | `204`; `404` if missing |
| `POST /api/query` | `{question, conversation_id?}` | `text/event-stream` (below) |
| `GET /api/conversations` | — | `[{id, title, updated_at}]`, newest first |
| `GET /api/conversations/{id}` | — | `{id, title, messages: [...]}`; `404` |
| `DELETE /api/conversations/{id}` | — | `204` (deletes its messages too); `404` |
| `GET /api/stats` | — | see Dashboard |
| `GET /health` | — | `{status: "ok"}` |

### Query stream (Server-Sent Events)

Each event is `event: <name>\ndata: <json>\n\n`:

1. `meta` — `{conversation_id, sources: [{filename, page, snippet}]}` (sent after retrieval, before generation)
2. `token` — `{text}` — repeated
3. `done` — `{message_id, metrics}`; or `error` — `{message}` (terminal)

The frontend reads it with `fetch` + `ReadableStream` (EventSource cannot POST).

## Query Flow

1. Validate the question (non-empty, ≤ 2000 chars). Load or create the conversation (`404` for unknown id). Save the user message.
2. If no documents exist → stream `meta` (no sources), a single `token` "Upload a document first, then ask me about it.", and `done`; no LLM call.
3. **retrieve node:** similarity search, k = 4, `numCandidates` 100. Sources = retrieved chunks deduplicated by (filename, page), snippet ≤ 200 chars. Emit `meta`.
4. **generate node:** system prompt + last 6 conversation messages + numbered context excerpts + question → ChatGroq, streamed. Each chunk of text is emitted as a `token` event.
5. The system prompt instructs: answer only from the excerpts; cite as [filename p.N]; if the excerpts don't contain the answer, reply exactly "I couldn't find that in your documents." In that case the stored sources are cleared.
6. Measure `ttft_ms` (request start → first token), `total_ms`, `output_tokens` (from Groq usage metadata; fallback: whitespace token estimate), `tokens_per_sec = output_tokens / generation seconds`. Save the assistant message (status `complete`) and emit `done`.
7. On exception after streaming has started: save the assistant message with partial content and status `error`, emit `error` with "Sorry, something went wrong while answering." The stream always ends with `done` or `error`.

## Upload Flow

1. Validate: extension in {pdf, txt, docx}, size ≤ 20 MB, non-empty.
2. Load pages (`loaders`); reject if total extracted text is empty ("No readable text found — scanned PDFs aren't supported").
3. Split into chunks; create the `documents` record (with `chunk_count`).
4. Embed and insert chunks with `document_id` metadata.
5. If step 4 fails: delete chunks with that `document_id`, delete the `documents` record, return `500` "Could not process the document". No half-uploaded documents.

Embedding runs in a thread pool (CPU-bound) so the event loop stays responsive.

Delete: remove chunks by `document_id`, then the `documents` record.

## Dashboard (`GET /api/stats`)

```json
{
  "totals": {"documents": 4, "chunks": 312, "questions": 27, "avg_tokens_per_sec": 512.4, "avg_ttft_ms": 380},
  "per_question": [{"created_at": "...", "ttft_ms": 350, "total_ms": 1200, "tokens_per_sec": 498.1}],
  "questions_per_day": [{"date": "2026-10-10", "count": 12}],
  "chunks_per_document": [{"filename": "report.pdf", "chunks": 120}]
}
```
`per_question` covers the latest 50 completed answers, oldest first. Averages use completed answers only.

## Frontend

```
frontend/src/
├── App.jsx                   # tab switch: Chat | Dashboard
├── services/api.js           # REST calls + streamQuery(question, conversationId, handlers)
├── components/
│   ├── Sidebar.jsx           # FileUpload + DocumentList + ConversationList + "New chat"
│   ├── FileUpload.jsx        # accepts .pdf,.txt,.docx; shows "Processing…"
│   ├── DocumentList.jsx      # filename, chunks, delete
│   ├── ConversationList.jsx  # select / delete conversations
│   ├── ChatView.jsx          # message list + input; consumes the stream
│   ├── MessageBubble.jsx     # markdown answer, Sources <details>, speed badge "⚡ 0.4s · 480 tok/s"
│   └── Dashboard.jsx         # stat cards + 4 Recharts charts
```

- While streaming, the assistant bubble updates on every `token`; the input is disabled until `done`/`error`.
- Selecting a conversation loads its messages; "New chat" clears the view and the next question creates a conversation; the conversation list refreshes after each answer.
- Dashboard charts: response time per question (LineChart: ttft + total), tokens/sec per question (BarChart), questions per day (BarChart), chunks per document (BarChart), plus stat cards. Shows an empty state when there's no data. Fetched when the tab opens.

## Error Handling Summary

| Situation | Behaviour |
|---|---|
| Bad file type / too large / empty / no text | `400` with a specific message, shown under the upload box |
| Failure while storing chunks | rollback (chunks + record removed), `500` with message |
| No documents uploaded | friendly instruction, no LLM call |
| Answer not in documents | "I couldn't find that in your documents.", no sources |
| Groq / Mongo error during query | `error` event; partial message saved with status `error`; UI shows the message |
| Unknown conversation / document id | `404` |
| Backend unreachable (frontend) | inline error in chat / upload / dashboard |

## Testing

- **Unit (no network):** `loaders` with generated PDF (`fpdf2`), DOCX (`python-docx`) and TXT files, including empty/no-text and bad-extension cases; `graph` with fake retriever and a fake streaming chat model (LangChain `GenericFakeChatModel`) — sources dedup, not-found clears sources, metrics computed, error path; SSE formatting.
- **Integration (Atlas test DB `<MONGODB_DB>_test`, skipped when `MONGODB_URI` is unset):** Beanie models; upload pipeline with fake embeddings incl. rollback on failure; documents/conversations/stats endpoints; query endpoint with a fake LLM and fake vector store producing the full event sequence and persisted messages.
- **Manual end-to-end:** real Atlas + Groq: upload a PDF, ask an answerable and an unanswerable question, watch streaming, confirm citations and speed badge, check dashboard, delete document and conversation.

## Risks

- **PyTorch blocked by Smart App Control** → `fastembed` fallback (same model), verified in the first task.
- **Atlas M0 limits** (512 MB, limited search indexes) — ample for this project.
- **Vector index build delay:** a new Atlas vector index takes up to ~1 minute to become queryable; the first query right after first startup may return no results. Documented in the README.
- **Groq model retirement** — mitigated by `GROQ_MODEL` setting.
