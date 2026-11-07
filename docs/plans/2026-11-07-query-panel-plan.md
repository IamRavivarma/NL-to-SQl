# Query Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the real query behind every answer: AI-written SQL over uploaded spreadsheets (executed read-only on SQLite), or the MongoDB `$vectorSearch` pipeline for documents, with a results table.

**Architecture:** Spreadsheet rows are parsed once and written both as text chunks (unchanged) and as SQLite tables with a catalog. The LangGraph graph becomes `plan_sql → (retrieve) → generate`; `stream_answer` emits `queries` in `meta`/`done`, persisted on `Message`. A `QueryPanel` React component renders them.

**Tech Stack:** FastAPI, sqlite3 (stdlib), LangGraph, ChatGroq, Beanie, React + Tailwind, Vitest, pytest.

**Spec:** `docs/specs/2026-11-07-query-panel-design.md`

## Global Constraints

- SQLite file from setting `SQLITE_PATH`, default `data/tables.db` (relative to `backend/`), gitignored.
- Only one statement starting with `SELECT` or `WITH`; read-only connection (`mode=ro` URI + `PRAGMA query_only = ON`); 5 s time limit; fetch at most 200 rows; show at most 50.
- One SQL retry with the error; then fallback to vector search with both panels shown.
- MongoDB panel: `$vectorSearch` {index `vector_index`, path `embedding`, numCandidates 100, limit 4, queryVector `"<384 numbers from your question>"`} + `$project`; columns `File, Page, Score, Excerpt`; excerpt ≤ 200 chars; score 3 decimals.
- No LLM call in `plan_sql` when the catalog is empty.
- SQL source chip snippet: `Rows returned by the SQL query`.

## Review Focus

1. Spreadsheet with duplicate/blank/non-ASCII headers (`Email Address` twice, `Revenue (₹)`) → unique valid column names; test in Task 2.
2. Model wraps SQL in ```sql fences or adds prose around JSON → still parsed; test in Task 4.
3. Model returns `DELETE`/`DROP`/two statements → rejected, never executed; test in Task 2.
4. Same file uploaded twice → second table gets `_2`, deleting one drops only its own tables; test in Task 2.
5. Mixed-type column (numbers and text) → `TEXT`, no crash on insert; test in Task 2.

---

### Task 1: Parsed tables from CSV/XLSX loaders

**Files:** Modify `backend/app/ingestion/loaders.py`; Test `backend/tests/test_loaders.py`

**Interfaces — Produces:**
- `@dataclass(frozen=True) class Table: sheet: str | None; page: int; header: list[str]; rows: list[list]` (rows hold raw typed values: `str` for CSV, openpyxl values for XLSX; `None` for empty).
- `load_tables(filename: str, content: bytes) -> list[Table]` — only non-empty tables (≥1 data row); `[]` for non-spreadsheet types. Raises `DocumentLoadError` like `load_pages`.
- Existing `load_pages` output unchanged (built from the same parse).

- [ ] Test `test_load_tables_csv`: `b"Name,Salary\nAlice,52000\n"` → `[Table(sheet=None, page=1, header=["Name","Salary"], rows=[["Alice","52000"]])]`.
- [ ] Test `test_load_tables_xlsx_skips_empty_sheets`: sheets Staff (header+1 row), Empty, Offices → pages `[1, 3]`, sheet names `["Staff","Offices"]`, header blank → `Column N`.
- [ ] Test `test_load_tables_pdf_is_empty`: `load_tables("a.pdf", make_pdf(["x"])) == []`.
- [ ] Run → fail; implement by splitting `_rows_to_lines` into `_parse_table(rows) -> (header, data_rows)` + line formatting; run all loader tests → pass; commit.

### Task 2: SQLite table store

**Files:** Create `backend/app/sql/__init__.py`, `backend/app/sql/table_store.py`; Test `backend/tests/test_table_store.py`

**Interfaces — Produces:**
- `sanitize_identifier(name: str, fallback: str) -> str` — lowercase, non `[a-z0-9]` runs → `_`, strip `_`, prefix `t_` if starts with digit, empty → `fallback`.
- `infer_type(values: list) -> str` — `"INTEGER" | "REAL" | "TEXT"` over non-empty values (bool → TEXT; `"52000"` → INTEGER; `"48000.5"` → REAL).
- `class SqlError(Exception)` (message shown to the user).
- `@dataclass TableInfo: table_name, document_id, filename, page, columns: list[dict{name, original, type}], row_count`.
- `class TableStore(path: str)`: `create_tables(document_id, filename, tables: list[Table]) -> list[str]`; `drop_document(document_id) -> int`; `catalog() -> list[TableInfo]`; `sample_rows(table_name, n=3) -> list[tuple]`; `run_select(sql) -> QueryResult`.
- `@dataclass QueryResult: columns: list[str]; rows: list[list]; truncated: bool` (≤200 rows).
- `validate_select(sql: str) -> str` — strips trailing `;`, raises `SqlError` unless one statement starting with SELECT/WITH.
- `get_table_store() -> TableStore` (lru_cache, `settings.sqlite_path`, creates parent dir). Add `sqlite_path: str = "data/tables.db"` to settings; add `backend/data/` to `.gitignore`.

- [ ] Tests (tmp_path DB): sanitize cases (`"Revenue (₹)"→"revenue"`, `"2024 Sales"→"t_2024_sales"`, `""→fallback`); duplicate headers → `email_address`, `email_address_2`; infer_type cases incl. mixed → TEXT; create → catalog row_count & types, values typed (`52000` int); same filename twice → `products`, `products_2`; xlsx table name `sales_q1`; drop_document drops only its tables and catalog rows; `run_select("SELECT ...")` works; `DELETE FROM x`, `DROP TABLE x`, `SELECT 1; SELECT 2` → `SqlError`; a write smuggled via `WITH` CTE fails (read-only); 250-row table → 200 rows, `truncated=True`; bad column → `SqlError` with sqlite message.
- [ ] Run → fail; implement (time limit via `set_progress_handler` deadline); run → pass; commit.

### Task 3: Ingestion and delete use the table store

**Files:** Modify `backend/app/ingestion/pipeline.py`, `backend/app/api/upload.py`, `backend/app/api/documents.py`, `backend/app/api/deps.py`; Tests `backend/tests/test_pipeline.py`, `backend/tests/test_documents_api.py`, `backend/tests/conftest.py` (override `get_table_store` with a tmp store).

**Interfaces:** `ingest_document(filename, content, store, table_store=None)`; `deps.get_tables() -> TableStore`.

- [ ] Tests: CSV ingest creates a table with the document id; table-store failure → chunks deleted, record removed, `IngestionError`; DELETE document drops its tables; TXT ingest creates none.
- [ ] Run → fail; implement (tables written after chunks, in threadpool; rollback deletes chunks + tables); run full backend suite → pass; commit.

### Task 4: SQL planner

**Files:** Create `backend/app/sql/planner.py`; Modify `backend/app/rag/prompts.py`; Test `backend/tests/test_planner.py`

**Interfaces — Produces:**
- `describe_schema(catalog: list[TableInfo], samples: dict[str, list[tuple]]) -> str`.
- `parse_sql_plan(text: str) -> str | None` — finds the first `{...}` JSON object (also inside ``` fences); returns `sql` if non-empty string else `None`; invalid JSON → `None`.
- `SQL_PLANNER_PROMPT`, `SQL_ANSWER_PROMPT` in prompts.py (answer only from the result rows; cite `[filename p.N]` from the table list; if rows are empty say no matching rows).

- [ ] Tests: schema text contains table name, column name + type + original name, sample values; parse plain JSON, fenced JSON, prose + JSON, `{"sql": null}`, garbage → None.
- [ ] Run → fail; implement; pass; commit.

### Task 5: Graph routing, queries in the stream, persistence

**Files:** Modify `backend/app/rag/graph.py`, `backend/app/api/query.py`, `backend/app/models/message.py`, `backend/app/models/__init__.py`, `backend/app/api/conversations.py`/serializers (include `queries`); Tests `backend/tests/test_graph.py`, `backend/tests/test_query_api.py`.

**Interfaces:**
- `stream_answer(question, history, *, store, llm, model_name, tables=None)`; `meta` event gets `queries: list[dict]`; `done` gets `queries`.
- `mongodb_query_run(hits) -> dict` and `sql_query_run(sql, result | None, error | None, tables) -> dict` (shapes from the spec).
- `Message.queries: list[dict] = []`.

- [ ] Tests (fake LLM with queued responses): no tables → exactly one LLM call, one mongodb query run with 4 rows; tables + valid SQL → sql run with rows, retrieve skipped, sources = table chips with snippet `Rows returned by the SQL query`, answer context contains result; `{"sql": null}` → mongodb run; bad SQL twice → two runs (sql with error, mongodb); bad then good → one sql run, 3 LLM calls total + answer; query API persists `queries` and returns them from `GET /api/conversations/{id}`.
- [ ] Run → fail; implement (planner LLM calls are not streamed as tokens: only `generate` node tokens are forwarded); full suite → pass; commit.

### Task 6: QueryPanel UI

**Files:** Create `frontend/src/components/QueryPanel.jsx`, `QueryPanel.test.jsx`; Modify `MessageBubble.jsx`, `ChatView.jsx` (store `queries` from meta/done).

- [ ] Tests (renderToStaticMarkup): SQL run shows "SQL query", the SQL text, column headers, cell values; mongodb run shows "MongoDB query" and `$vectorSearch`; truncated shows "Showing 50 of 200 rows"; error run shows the error text; empty list renders nothing.
- [ ] Run → fail; implement (open by default, toggle, Copy button, max-h scroll table, sticky header); `npm test` + `npm run build` pass; commit.

### Task 7: Docs and end-to-end check

- [ ] README: feature bullet, "How it works" lines, test counts, `SQLITE_PATH` config row.
- [ ] Restart backend; upload a sample XLSX + use handbook.pdf; ask an aggregate question (exact total), a PDF question (MongoDB panel), a follow-up; delete test data; commit.
