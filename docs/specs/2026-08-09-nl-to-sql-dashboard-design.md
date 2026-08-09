# NL-to-SQL Data Assistant — Design

## Overview

A single-user web app that lets a user upload CSV/Excel files, which are loaded into PostgreSQL as tables, then ask natural-language questions about the data. A LangChain SQL agent (backed by Llama 3.3 70B via Groq's free API) converts the question into a read-only SQL query, runs it against Postgres, and an LLM call picks an appropriate chart type to visualize the result. The frontend renders the answer and chart inline in a chat interface.

Out of scope for v1: PDF/text document RAG, embeddings/vector search, authentication/multi-user support.

## Tech Stack

- **Frontend**: React (Vite), Tailwind CSS, Recharts
- **Backend**: FastAPI, Python 3.10+
- **Database**: PostgreSQL (single instance; app metadata tables + dynamically created tables from uploads)
- **ORM**: SQLAlchemy (async) + asyncpg
- **AI Orchestration**: LangChain SQL Agent
- **LLM**: Llama 3.3 70B via Groq API (free tier)

## Architecture / Data Flow

1. **Upload** (`POST /api/upload`): user uploads a CSV/Excel file → backend infers column names/types from the file → creates a new Postgres table with a sanitized name derived from the filename (collisions get a numeric suffix) → bulk-inserts rows → records metadata (table name, original filename, columns, row count, upload timestamp) in an `uploaded_datasets` table. Failures roll back the entire table creation (all-or-nothing).

2. **Chat** (`POST /api/chat`): user submits a question → LangChain SQL agent is given the schema of tables listed in `uploaded_datasets` (app metadata tables like `chat_messages` are excluded from its visible schema) → LLM generates a SQL query → query is validated (must be a single `SELECT` statement, no DDL/DML) → executed against Postgres through a dedicated `readonly_agent` role that only has `SELECT` grants on uploaded-data tables, with a statement timeout (10s) → result rows returned.

3. **Chart selection**: the question, generated SQL, and result rows (or their shape/sample) are passed to a second LLM call that returns a chart spec JSON: chart type (bar/line/pie/table/stat-card) and field-to-axis mapping. If this call fails or returns a malformed spec, the backend falls back to rendering the raw result as a table — the chat response still succeeds.

4. **History**: each exchange (question, generated SQL, result summary, chart spec) is persisted to a `chat_messages` table and returned to the frontend so past charts re-render correctly when scrolling back through the conversation.

## Safety Guardrails

- The SQL agent exclusively uses the `readonly_agent` Postgres role (`SELECT`-only grants on uploaded-data tables) — this is a DB-level boundary, not just application logic, so a prompt-injected or malformed query cannot mutate data.
- Generated SQL is validated (single `SELECT` statement only) before execution.
- If the agent produces invalid/non-SELECT SQL, it gets one retry with the error fed back; on a second failure the user sees a friendly "couldn't answer that" message instead of a raw error.
- Postgres `statement_timeout` on the readonly role prevents runaway queries.

## Backend Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── upload.py        # POST /api/upload
│   │   ├── chat.py          # POST /api/chat
│   │   └── datasets.py      # GET /api/datasets, DELETE /api/datasets/{id}
│   ├── core/
│   │   ├── config.py        # env config (DB URL, GROQ_API_KEY)
│   │   └── database.py      # async SQLAlchemy engine/session (app role + readonly_agent role)
│   ├── models/
│   │   ├── dataset.py       # uploaded_datasets ORM model
│   │   └── chat.py          # chat_messages ORM model
│   ├── services/
│   │   ├── file_parser.py   # CSV/Excel -> inferred schema + rows
│   │   └── table_builder.py # dynamic CREATE TABLE + bulk insert, name sanitization
│   ├── ai/
│   │   ├── sql_agent.py     # LangChain SQL agent (Groq/Llama 3.3 70B)
│   │   ├── chart_picker.py  # LLM call: result + question -> chart spec JSON
│   │   └── prompts.py
│   └── main.py
├── pyproject.toml
└── uv.lock
```

## Frontend Structure

```
frontend/src/
├── components/
│   ├── FileUpload.jsx    # drag-drop CSV/Excel, upload progress, shows inferred schema after upload
│   ├── DatasetList.jsx   # sidebar: uploaded tables with row/column counts
│   ├── ChatInterface.jsx # question input + message history (question, collapsed SQL, answer)
│   ├── ChartRenderer.jsx # chart spec JSON -> Recharts (bar/line/pie/table/stat-card)
│   └── Dashboard.jsx     # layout: dataset list + chat + chart area
├── services/
│   └── api.js             # axios wrapper: uploadFile(), sendMessage(), getDatasets()
└── App.jsx
```

Charts render inline within chat messages (not a separate persistent dashboard grid) — keeps v1 simple. Each stored chat message includes its chart spec so history re-renders correctly.

## Error Handling

- **Upload**: unparseable/empty file, or duplicate table name → 400 with a clear message; table creation is all-or-nothing.
- **Chat/SQL agent**: invalid or non-SELECT SQL is caught before execution; one retry with the error fed back to the LLM; second failure returns a friendly error message.
- **Query timeout**: enforced via Postgres `statement_timeout` on the readonly role.
- **Chart picker failure**: falls back to a plain table render; chat response still succeeds.

## Testing

- **Backend (pytest)**: unit tests for `file_parser.py` (mixed types, dates, nulls) and `table_builder.py` (name sanitization, collisions); integration tests for `/api/upload` and `/api/chat` against a test Postgres database.
- **SQL agent**: a fixed set of question → expected-query-shape checks (verifying the right table/columns are targeted, not exact string match) to catch prompt regressions.
- **Frontend**: no exhaustive automated suite for v1; manual verification of the upload → chat → chart flow is the acceptance bar.
