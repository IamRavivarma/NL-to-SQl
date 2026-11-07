# Query Panel (NL-to-SQL + visible MongoDB query) — Design

## Intent

Keep the RAG document assistant exactly as it is, and add one thing the user asked for: when someone asks a question, the chat shows **the database query generated from their natural-language question and its results**, then the answer streams in below as today.

- Questions about **spreadsheet data (CSV / XLSX)** are answered by a **real SQL query** that the AI writes and the app runs against a SQL copy of the spreadsheet rows. This also makes totals, counts, averages and "top N" questions exact, which plain RAG can't do (it only reads 4 chunks).
- Questions about **PDF / DOCX / TXT** (or anything SQL can't answer) show the **MongoDB Atlas `$vectorSearch` query that actually ran** and the passages it returned. (User decision: "for pdf show mongodb".)

Why: this is a college project and the user wants the NL-to-SQL idea visible in the app, without rebuilding it.

### Goals
- A query panel in each assistant message: query text (SQL or MongoDB pipeline) + results table.
- Real, executed queries only. Never show a query that didn't run.
- Exact answers for aggregate questions over uploaded spreadsheets.
- Saved with the conversation, so reopening a chat shows the panels again.

### Non-goals
- Connecting to an external/user-supplied database (PostgreSQL etc.).
- Charts of query results (table only for now).
- Joins across different uploaded files are allowed if the model writes them, but not designed for.
- Schema retrieval via vector search (all table schemas fit in the prompt for this project's scale).

### Anti-goals (failure even if it "works")
- Fake or decorative SQL for PDFs.
- Any SQL that can modify data.
- Breaking or slowing the existing document Q&A when no spreadsheets are uploaded.

## How it works

### Upload (CSV / XLSX only)
1. Existing flow unchanged: rows become `Column: value | ...` text chunks in Atlas.
2. New: the same parsed rows are written into **SQLite** (`backend/data/tables.db`, setting `SQLITE_PATH`, gitignored). One table per CSV, one per non-empty Excel sheet.
   - Table name: sanitized file stem (`products`), plus `_<sheet>` for Excel (`sales_q1`); lowercase, `[a-z0-9_]`, deduplicated with `_2`, `_3`.
   - Column names: sanitized the same way (`Revenue (₹)` → `revenue`); blank → `column_N`; duplicates suffixed.
   - Column types inferred: all non-empty values integers → `INTEGER`; numbers → `REAL`; else `TEXT`. Empty cells → `NULL`. Dates stored as ISO text.
   - A `table_catalog` table records `table_name, document_id, filename, page (sheet number, 1 for CSV), columns (JSON list of {name, original, type}), row_count`.
3. All-or-nothing: if writing tables fails, the chunks and document record are rolled back, as today. Deleting a document also drops its tables.
4. Spreadsheets uploaded before this feature have no tables until re-uploaded.

### Asking (LangGraph, now three steps)
`plan_sql → retrieve → generate`

1. **plan_sql** (skipped, no LLM call, when there are no tables): one non-streaming ChatGroq call with the schema of every table (columns, types, 3 sample rows) + last conversation turns + the question. The model returns JSON `{"sql": "<one SELECT>"}` or `{"sql": null}` when the question isn't about the tables.
   - Validation: exactly one statement starting with `SELECT` or `WITH`. Executed on a **read-only** SQLite connection (`mode=ro` URI + `PRAGMA query_only = ON`), with a 5-second time limit. At most 200 rows are fetched.
   - **Error correction:** if the SQL fails, the error is sent back to the model once for a corrected query. If it fails again, the SQL panel shows the error and the app falls back to document search.
2. **retrieve:** runs only when there's no successful SQL result: the existing Atlas vector search (k=4, numCandidates 100), unchanged.
3. **generate:** streams the answer as today.
   - With SQL: context = the SQL + result rows (as a Markdown table, up to 50 rows). The prompt says to answer from the result and cite `[filename p.N]` of the table's source (sheet number).
   - Without SQL: existing excerpt prompt, unchanged.

### What the panel shows (`queries`, a list, usually one item)
- **SQL:** `{kind: "sql", query, columns, rows (≤50), row_count, truncated, error?, tables: [{filename, page}]}`
- **MongoDB:** `{kind: "mongodb", query, columns: ["File", "Page", "Score", "Excerpt"], rows, row_count}`, where `query` is the real aggregation pipeline that ran: `$vectorSearch` (index `vector_index`, path `embedding`, `numCandidates` 100, `limit` 4, `queryVector` shown as `"<384 numbers from your question>"`) and `$project`. Rows are the retrieved chunks (excerpt ≤ 200 chars, score to 3 decimals).
- Failed SQL followed by fallback shows both panels: the SQL with its error, then the MongoDB one.

### API / storage changes
- SSE `meta` gains `queries` (sent before the first token, so the panel appears before the answer streams); `done` repeats `queries`.
- `Message.queries: list[QueryRun]` (default `[]`) persisted; returned by `GET /api/conversations/{id}`.
- Sources for SQL answers: one chip per source table (`filename`, sheet page, snippet = "Rows returned by the SQL query").
- Metrics unchanged; `ttft_ms` naturally includes the SQL planning call.

### Frontend
- New `QueryPanel` component, rendered in `MessageBubble` above the answer text:
  - header: database icon + "SQL query" or "MongoDB query" + the file name(s) + row count, with a show/hide toggle (open by default);
  - query in a monospace code block with a Copy button;
  - results in a scrollable table (max height, sticky header); "Showing 50 of N rows" when truncated;
  - SQL error in red when present.
- The waiting text changes to "Writing the query…" when there are tables.

## Testing
- Unit: name/type sanitizing and inference; SQLite table write/drop/catalog; read-only enforcement (`DELETE`/`DROP`/multiple statements rejected); SQL plan JSON parsing (including fenced/invalid JSON → no SQL); graph routes (SQL success, SQL null → vector, SQL error → retry → fallback) with fake LLMs.
- Integration: upload CSV creates a table; delete drops it; query endpoint persists `queries`.
- Frontend: `QueryPanel` renders SQL, MongoDB, truncated and error cases.
- Manual end-to-end on Atlas + Groq: an aggregate question on an Excel file (exact total), a PDF question (MongoDB panel), and a follow-up.

## Builder's calls (not discussed with the user)
SQLite as the SQL engine; all schemas in the prompt (no schema RAG); one retry for SQL errors; 200-row fetch / 50-row display; table-only results (no chart); panel open by default.
