# NL-to-SQL Data Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user web app where a user uploads CSV/Excel files into PostgreSQL tables, asks natural-language questions, gets answers via a LangChain SQL agent (Llama 3.3 70B on Groq), and sees results visualized with an LLM-picked chart.

**Architecture:** FastAPI backend with async SQLAlchemy/asyncpg talking to PostgreSQL; uploaded files become dynamically created tables. A LangChain SQL agent (restricted to a read-only Postgres role) turns questions into SQL, and a second LLM call picks a chart spec. React (Vite) + Tailwind + Recharts frontend renders a chat interface with inline charts.

**Tech Stack:** FastAPI, Python 3.10+, SQLAlchemy (async) + asyncpg, PostgreSQL, LangChain, langchain-groq (Llama 3.3 70B), pandas/openpyxl for file parsing, React (Vite), Tailwind CSS, Recharts, axios, pytest/pytest-asyncio, uv.

## Global Constraints

- Python 3.10+, dependency management via `uv` (spec: Tech Stack).
- No authentication/multi-user support in v1 (spec: Overview — out of scope).
- No PDF/text RAG or embeddings in v1 (spec: Overview — out of scope).
- The SQL agent must only ever query through the `readonly_agent` Postgres role, which has `SELECT`-only grants on uploaded-data tables (spec: Safety Guardrails).
- Generated SQL must be validated as a single `SELECT` statement before execution (spec: Safety Guardrails).
- Postgres `statement_timeout` of 10s applies to the readonly role (spec: Safety Guardrails).
- Chart picker failures must fall back to a plain table render, not fail the chat response (spec: Error Handling).
- Table creation on upload is all-or-nothing; failures roll back (spec: Error Handling).
- Charts render inline in chat messages; each stored chat message includes its chart spec (spec: Frontend Structure).

---

## Precondition: PostgreSQL instance

These tasks assume a running PostgreSQL instance reachable for both a normal app role (create/read/write) and a `readonly_agent` role. Task 2 creates the SQL script to set this up; you must run it manually once against your Postgres instance (documented in that task) before Task 6 onward will pass their integration tests.

---

### Task 1: Backend project scaffold, config, health check

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/core/__init__.py`
- Create: `backend/app/core/config.py`
- Create: `backend/.env.example`
- Test: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.core.config.Settings` (pydantic-settings `BaseSettings` subclass) with fields `database_url: str`, `readonly_database_url: str`, `groq_api_key: str`; module-level `settings = Settings()`.
- Produces: `app.main.app` — the FastAPI instance, with `GET /health` returning `{"status": "ok"}`.

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "nl-to-sql-backend"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "python-multipart>=0.0.9",
    "pandas>=2.2",
    "openpyxl>=3.1",
    "langchain>=0.3",
    "langchain-community>=0.3",
    "langchain-groq>=0.2",
    "pydantic-settings>=2.5",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `backend/app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    readonly_database_url: str
    groq_api_key: str


settings = Settings()
```

- [ ] **Step 3: Create `backend/.env.example`**

```
DATABASE_URL=postgresql+asyncpg://app_user:app_password@localhost:5432/nl_to_sql
READONLY_DATABASE_URL=postgresql+asyncpg://readonly_agent:readonly_password@localhost:5432/nl_to_sql
GROQ_API_KEY=your-groq-api-key
```

- [ ] **Step 4: Create `backend/app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="NL-to-SQL Data Assistant")


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Create `backend/app/__init__.py` and `backend/app/core/__init__.py`** (empty files)

- [ ] **Step 6: Write the failing test — `backend/tests/test_health.py`**

```python
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 7: Set up env and run test**

```bash
cd backend
cp .env.example .env
uv sync
uv run pytest tests/test_health.py -v
```

Expected: PASS (config loads from `.env`, health check returns ok).

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/app backend/.env.example backend/tests/test_health.py
git commit -m "feat: scaffold FastAPI backend with health check"
```

---

### Task 2: Database connections and readonly role setup script

**Files:**
- Create: `backend/app/core/database.py`
- Create: `backend/scripts/init_db.sql`
- Test: `backend/tests/test_database.py`

**Interfaces:**
- Consumes: `app.core.config.settings` (Task 1).
- Produces: `app.core.database.Base` (SQLAlchemy `DeclarativeBase`), `app.core.database.engine` (app-role async engine), `app.core.database.readonly_engine` (readonly-role async engine), `app.core.database.async_session_maker` (sessionmaker bound to `engine`), `app.core.database.get_db()` (async generator FastAPI dependency yielding an `AsyncSession`).

- [ ] **Step 1: Create `backend/scripts/init_db.sql`**

```sql
-- Run once, manually, as a Postgres superuser/owner, against the target database.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'readonly_agent') THEN
        CREATE ROLE readonly_agent LOGIN PASSWORD 'readonly_password';
    END IF;
END
$$;

ALTER ROLE readonly_agent SET statement_timeout = '10s';

GRANT CONNECT ON DATABASE nl_to_sql TO readonly_agent;
GRANT USAGE ON SCHEMA public TO readonly_agent;
-- No table grants here: table_builder.py grants SELECT per table at creation time.
```

- [ ] **Step 2: Create `backend/app/core/database.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url)
readonly_engine = create_async_engine(settings.readonly_database_url)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session_maker() as session:
        yield session
```

- [ ] **Step 3: Write the failing test — `backend/tests/test_database.py`**

```python
from sqlalchemy import text

from app.core.database import engine


async def test_app_engine_connects():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

- [ ] **Step 4: Run migration script and test**

Run `backend/scripts/init_db.sql` manually against your Postgres instance (e.g. `psql -U postgres -d nl_to_sql -f backend/scripts/init_db.sql`), with `nl_to_sql` database and `app_user` role already created matching `.env`.

```bash
cd backend
uv run pytest tests/test_database.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/database.py backend/scripts/init_db.sql backend/tests/test_database.py
git commit -m "feat: add async database engines and readonly role setup script"
```

---

### Task 3: ORM models for datasets and chat messages

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/dataset.py`
- Create: `backend/app/models/chat.py`
- Modify: `backend/app/main.py` (create tables on startup)
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Consumes: `app.core.database.Base`, `app.core.database.engine`, `app.core.database.async_session_maker` (Task 2).
- Produces: `app.models.dataset.UploadedDataset` (fields: `id: int`, `table_name: str`, `original_filename: str`, `columns: dict` (JSON: `{name: type}`), `row_count: int`, `uploaded_at: datetime`).
- Produces: `app.models.chat.ChatMessage` (fields: `id: int`, `question: str`, `sql_query: str | None`, `result_summary: str | None`, `chart_spec: dict | None` (JSON), `created_at: datetime`).

- [ ] **Step 1: Create `backend/app/models/dataset.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadedDataset(Base):
    __tablename__ = "uploaded_datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    columns: Mapped[dict] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 2: Create `backend/app/models/chat.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

- [ ] **Step 3: Create `backend/app/models/__init__.py`**

```python
from app.models.chat import ChatMessage
from app.models.dataset import UploadedDataset

__all__ = ["ChatMessage", "UploadedDataset"]
```

- [ ] **Step 4: Modify `backend/app/main.py` to create tables on startup**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import Base, engine
from app.models import ChatMessage, UploadedDataset  # noqa: F401  (ensures models are registered)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="NL-to-SQL Data Assistant", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Write the failing test — `backend/tests/test_models.py`**

```python
from sqlalchemy import select

from app.core.database import Base, async_session_maker, engine
from app.models import UploadedDataset


async def test_insert_and_query_uploaded_dataset():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        dataset = UploadedDataset(
            table_name="sales_q1",
            original_filename="sales_q1.csv",
            columns={"date": "DATE", "region": "TEXT", "revenue": "NUMERIC"},
            row_count=10,
        )
        session.add(dataset)
        await session.commit()

        result = await session.execute(
            select(UploadedDataset).where(UploadedDataset.table_name == "sales_q1")
        )
        fetched = result.scalar_one()
        assert fetched.original_filename == "sales_q1.csv"
        assert fetched.row_count == 10
```

- [ ] **Step 6: Run test**

```bash
cd backend
uv run pytest tests/test_models.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models backend/app/main.py backend/tests/test_models.py
git commit -m "feat: add UploadedDataset and ChatMessage ORM models"
```

---

### Task 4: File parser — infer schema and rows from CSV/Excel

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/file_parser.py`
- Test: `backend/tests/test_file_parser.py`

**Interfaces:**
- Produces: `app.services.file_parser.ParsedFile` (dataclass: `columns: list[tuple[str, str]]` — `(name, sql_type)` pairs where `sql_type` is one of `"INTEGER"`, `"FLOAT"`, `"DATE"`, `"TEXT"`; `rows: list[dict]`).
- Produces: `app.services.file_parser.parse_file(filename: str, content: bytes) -> ParsedFile`. Raises `app.services.file_parser.FileParseError` on empty/unparseable input. Dispatches on file extension (`.csv` vs `.xlsx`/`.xls`).

- [ ] **Step 1: Write the failing tests — `backend/tests/test_file_parser.py`**

```python
import pytest

from app.services.file_parser import FileParseError, parse_file


def test_parses_csv_with_mixed_types():
    content = b"date,region,revenue\n2024-01-01,East,100.5\n2024-01-02,West,200\n"
    result = parse_file("sales.csv", content)
    assert ("date", "DATE") in result.columns
    assert ("region", "TEXT") in result.columns
    assert ("revenue", "FLOAT") in result.columns
    assert len(result.rows) == 2
    assert result.rows[0]["region"] == "East"


def test_column_with_mixed_types_falls_back_to_text():
    content = b"col\n1\nabc\n"
    result = parse_file("mixed.csv", content)
    assert ("col", "TEXT") in result.columns


def test_column_with_nulls_infers_from_non_null_values():
    content = b"col\n1\n\n3\n"
    result = parse_file("nulls.csv", content)
    assert ("col", "INTEGER") in result.columns
    assert result.rows[1]["col"] is None


def test_empty_file_raises():
    with pytest.raises(FileParseError):
        parse_file("empty.csv", b"")


def test_unsupported_extension_raises():
    with pytest.raises(FileParseError):
        parse_file("data.txt", b"col\n1\n")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_file_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError` (module doesn't exist yet).

- [ ] **Step 3: Create `backend/app/services/file_parser.py`**

```python
import io
from dataclasses import dataclass

import pandas as pd


class FileParseError(Exception):
    pass


@dataclass
class ParsedFile:
    columns: list[tuple[str, str]]
    rows: list[dict]


def _infer_sql_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "TEXT"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATE"
    parsed = pd.to_numeric(non_null, errors="coerce")
    if parsed.notna().all():
        if (parsed % 1 == 0).all():
            return "INTEGER"
        return "FLOAT"
    parsed_dates = pd.to_datetime(non_null, errors="coerce", format="%Y-%m-%d")
    if parsed_dates.notna().all():
        return "DATE"
    return "TEXT"


def _dataframe_to_parsed_file(df: pd.DataFrame) -> ParsedFile:
    if df.empty:
        raise FileParseError("File contains no rows")

    columns: list[tuple[str, str]] = []
    for col in df.columns:
        sql_type = _infer_sql_type(df[col])
        columns.append((str(col), sql_type))
        if sql_type == "DATE":
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d")

    df = df.where(pd.notnull(df), None)
    rows = df.to_dict(orient="records")
    return ParsedFile(columns=columns, rows=rows)


def parse_file(filename: str, content: bytes) -> ParsedFile:
    if not content:
        raise FileParseError("File is empty")

    lower = filename.lower()
    try:
        if lower.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(content))
        elif lower.endswith(".xlsx") or lower.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise FileParseError(f"Unsupported file type: {filename}")
    except FileParseError:
        raise
    except Exception as exc:
        raise FileParseError(f"Could not parse file: {exc}") from exc

    return _dataframe_to_parsed_file(df)
```

- [ ] **Step 4: Create `backend/app/services/__init__.py`** (empty file)

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_file_parser.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/file_parser.py backend/app/services/__init__.py backend/tests/test_file_parser.py
git commit -m "feat: add CSV/Excel file parser with type inference"
```

---

### Task 5: Table builder — dynamic table creation, insert, readonly grant

**Files:**
- Create: `backend/app/services/table_builder.py`
- Test: `backend/tests/test_table_builder.py`

**Interfaces:**
- Consumes: `app.services.file_parser.ParsedFile` (Task 4), `app.core.database.async_session_maker` (Task 2).
- Produces: `app.services.table_builder.sanitize_table_name(filename: str, existing_names: set[str]) -> str`.
- Produces: `async def create_table_and_insert(session: AsyncSession, table_name: str, parsed: ParsedFile) -> None` — creates the table, inserts rows, grants `SELECT` to `readonly_agent`. Raises on failure; caller is responsible for the transaction (session commit/rollback).

- [ ] **Step 1: Write the failing tests — `backend/tests/test_table_builder.py`**

```python
import pytest
from sqlalchemy import text

from app.core.database import async_session_maker
from app.services.file_parser import ParsedFile
from app.services.table_builder import create_table_and_insert, sanitize_table_name


def test_sanitize_table_name_basic():
    assert sanitize_table_name("Sales Q1.csv", set()) == "sales_q1"


def test_sanitize_table_name_strips_invalid_chars():
    assert sanitize_table_name("2024-report!.csv", set()) == "t_2024_report"


def test_sanitize_table_name_handles_collision():
    existing = {"sales_q1", "sales_q1_1"}
    assert sanitize_table_name("Sales Q1.csv", existing) == "sales_q1_2"


async def test_create_table_and_insert_creates_queryable_table():
    parsed = ParsedFile(
        columns=[("region", "TEXT"), ("revenue", "FLOAT")],
        rows=[{"region": "East", "revenue": 100.5}, {"region": "West", "revenue": 200.0}],
    )
    async with async_session_maker() as session:
        await create_table_and_insert(session, "test_sales", parsed)
        await session.commit()

        result = await session.execute(text("SELECT region, revenue FROM test_sales ORDER BY region"))
        rows = result.mappings().all()
        assert len(rows) == 2
        assert rows[0]["region"] == "East"

        await session.execute(text("DROP TABLE test_sales"))
        await session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_table_builder.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `backend/app/services/table_builder.py`**

```python
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.file_parser import ParsedFile

_INVALID_CHARS = re.compile(r"[^a-z0-9_]")


def sanitize_table_name(filename: str, existing_names: set[str]) -> str:
    base = filename.rsplit(".", 1)[0].lower()
    base = base.replace(" ", "_").replace("-", "_")
    base = _INVALID_CHARS.sub("", base)
    if not base or not base[0].isalpha():
        base = f"t_{base}".strip("_")
        base = _INVALID_CHARS.sub("", base) or "t_upload"

    if base not in existing_names:
        return base

    suffix = 1
    while f"{base}_{suffix}" in existing_names:
        suffix += 1
    return f"{base}_{suffix}"


async def create_table_and_insert(
    session: AsyncSession, table_name: str, parsed: ParsedFile
) -> None:
    column_defs = ", ".join(f'"{name}" {sql_type}' for name, sql_type in parsed.columns)
    await session.execute(text(f'CREATE TABLE "{table_name}" ({column_defs})'))

    if parsed.rows:
        col_names = [name for name, _ in parsed.columns]
        col_list = ", ".join(f'"{c}"' for c in col_names)
        placeholders = ", ".join(f":{c}" for c in col_names)
        insert_stmt = text(f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})')
        await session.execute(insert_stmt, parsed.rows)

    await session.execute(text(f'GRANT SELECT ON "{table_name}" TO readonly_agent'))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_table_builder.py -v
```

Expected: PASS. (The collision test's expected `sales_q1_2` requires `sanitize_table_name` to check the base name too — verify `sales_q1` counts as taken since it's in `existing_names`.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/table_builder.py backend/tests/test_table_builder.py
git commit -m "feat: add dynamic table creation with readonly grant"
```

---

### Task 6: POST /api/upload endpoint

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/upload.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_upload_api.py`

**Interfaces:**
- Consumes: `parse_file` (Task 4), `sanitize_table_name` + `create_table_and_insert` (Task 5), `UploadedDataset` (Task 3), `get_db` (Task 2).
- Produces: `POST /api/upload` — multipart file upload. Response `201`: `{"table_name": str, "row_count": int, "columns": [{"name": str, "type": str}]}`. Response `400` on parse/duplicate errors: `{"detail": str}`.

- [ ] **Step 1: Write the failing test — `backend/tests/test_upload_api.py`**

```python
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import engine
from app.main import app


async def test_upload_csv_creates_table_and_metadata():
    csv_content = b"region,revenue\nEast,100\nWest,200\n"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/upload",
            files={"file": ("test_upload_sales.csv", csv_content, "text/csv")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["table_name"] == "test_upload_sales"
    assert body["row_count"] == 2

    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT COUNT(*) FROM "test_upload_sales"'))
        assert result.scalar() == 2
        await conn.execute(text('DROP TABLE "test_upload_sales"'))
        await conn.execute(text("DELETE FROM uploaded_datasets WHERE table_name = 'test_upload_sales'"))
        await conn.commit()


async def test_upload_empty_file_returns_400():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/upload", files={"file": ("empty.csv", b"", "text/csv")}
        )
    assert response.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_upload_api.py -v
```

Expected: FAIL (404, route doesn't exist).

- [ ] **Step 3: Create `backend/app/api/upload.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import UploadedDataset
from app.services.file_parser import FileParseError, parse_file
from app.services.table_builder import create_table_and_insert, sanitize_table_name

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", status_code=201)
async def upload_file(file: UploadFile, db: AsyncSession = Depends(get_db)):
    content = await file.read()
    try:
        parsed = parse_file(file.filename, content)
    except FileParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = await db.execute(select(UploadedDataset.table_name))
    existing_names = {row[0] for row in existing.all()}
    table_name = sanitize_table_name(file.filename, existing_names)

    try:
        await create_table_and_insert(db, table_name, parsed)
        dataset = UploadedDataset(
            table_name=table_name,
            original_filename=file.filename,
            columns={name: sql_type for name, sql_type in parsed.columns},
            row_count=len(parsed.rows),
        )
        db.add(dataset)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not import file: {exc}") from exc

    return {
        "table_name": table_name,
        "row_count": len(parsed.rows),
        "columns": [{"name": name, "type": sql_type} for name, sql_type in parsed.columns],
    }
```

- [ ] **Step 4: Create `backend/app/api/__init__.py`** (empty file)

- [ ] **Step 5: Modify `backend/app/main.py` to register the router**

```python
from app.api.upload import router as upload_router

app.include_router(upload_router)
```

(Add this import and `include_router` call alongside the existing `app = FastAPI(...)` setup from Task 3.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_upload_api.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_upload_api.py
git commit -m "feat: add POST /api/upload endpoint"
```

---

### Task 7: GET/DELETE /api/datasets endpoints

**Files:**
- Create: `backend/app/api/datasets.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_datasets_api.py`

**Interfaces:**
- Consumes: `UploadedDataset` (Task 3), `get_db` (Task 2).
- Produces: `GET /api/datasets` → `200`: `[{"id": int, "table_name": str, "original_filename": str, "row_count": int, "columns": [{"name": str, "type": str}], "uploaded_at": str}]`.
- Produces: `DELETE /api/datasets/{id}` → `204` on success (drops the table and metadata row); `404` if not found.

- [ ] **Step 1: Write the failing tests — `backend/tests/test_datasets_api.py`**

```python
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.database import engine
from app.main import app


async def _upload(client, table_hint):
    csv_content = b"region,revenue\nEast,100\n"
    return await client.post(
        "/api/upload", files={"file": (f"{table_hint}.csv", csv_content, "text/csv")}
    )


async def test_list_datasets_returns_uploaded_table():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _upload(client, "test_list_datasets")
        response = await client.get("/api/datasets")

    assert response.status_code == 200
    names = [d["table_name"] for d in response.json()]
    assert "test_list_datasets" in names

    async with engine.connect() as conn:
        await conn.execute(text('DROP TABLE "test_list_datasets"'))
        await conn.execute(text("DELETE FROM uploaded_datasets WHERE table_name = 'test_list_datasets'"))
        await conn.commit()


async def test_delete_dataset_drops_table_and_metadata():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        upload_response = await _upload(client, "test_delete_dataset")
        list_response = await client.get("/api/datasets")
        dataset_id = next(
            d["id"] for d in list_response.json() if d["table_name"] == "test_delete_dataset"
        )

        delete_response = await client.delete(f"/api/datasets/{dataset_id}")
        assert delete_response.status_code == 204

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT to_regclass('public.test_delete_dataset')")
        )
        assert result.scalar() is None


async def test_delete_missing_dataset_returns_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/datasets/999999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_datasets_api.py -v
```

Expected: FAIL (404 routes don't exist).

- [ ] **Step 3: Create `backend/app/api/datasets.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import UploadedDataset

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
async def list_datasets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UploadedDataset).order_by(UploadedDataset.uploaded_at.desc()))
    datasets = result.scalars().all()
    return [
        {
            "id": d.id,
            "table_name": d.table_name,
            "original_filename": d.original_filename,
            "row_count": d.row_count,
            "columns": [{"name": name, "type": sql_type} for name, sql_type in d.columns.items()],
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in datasets
    ]


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: int, db: AsyncSession = Depends(get_db)):
    dataset = await db.get(UploadedDataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    await db.execute(text(f'DROP TABLE IF EXISTS "{dataset.table_name}"'))
    await db.delete(dataset)
    await db.commit()
```

- [ ] **Step 4: Modify `backend/app/main.py` to register the router**

```python
from app.api.datasets import router as datasets_router

app.include_router(datasets_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_datasets_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/datasets.py backend/app/main.py backend/tests/test_datasets_api.py
git commit -m "feat: add GET/DELETE /api/datasets endpoints"
```

---

### Task 8: SQL validation + LangChain SQL agent (Groq/Llama 3.3 70B)

**Files:**
- Create: `backend/app/ai/__init__.py`
- Create: `backend/app/ai/prompts.py`
- Create: `backend/app/ai/sql_agent.py`
- Test: `backend/tests/test_sql_agent.py`

**Interfaces:**
- Produces: `app.ai.sql_agent.validate_single_select(sql: str) -> bool` — pure function, no I/O.
- Produces: `app.ai.sql_agent.SqlAgentResult` (dataclass: `sql: str`, `columns: list[str]`, `rows: list[dict]`).
- Produces: `app.ai.sql_agent.SqlAgentError(Exception)`.
- Produces: `async def run_sql_query(question: str) -> SqlAgentResult` — builds a `SQLDatabase` scoped to `uploaded_datasets` table names (queried from the app DB) over the `readonly_engine` (Task 2), runs a LangChain SQL agent using `ChatGroq(model="llama-3.3-70b-versatile", api_key=settings.groq_api_key)`, validates the generated SQL with `validate_single_select`, retries once on invalid SQL by feeding the error back to the agent, and raises `SqlAgentError` on a second failure.

- [ ] **Step 1: Write the failing tests — `backend/tests/test_sql_agent.py`**

```python
import pytest

from app.ai.sql_agent import SqlAgentError, validate_single_select


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("SELECT * FROM sales_q1", True),
        ("select region, sum(revenue) from sales_q1 group by region", True),
        ("SELECT * FROM sales_q1;", True),
        ("DROP TABLE sales_q1", False),
        ("SELECT * FROM sales_q1; DROP TABLE sales_q1;", False),
        ("UPDATE sales_q1 SET revenue = 0", False),
        ("", False),
    ],
)
def test_validate_single_select(sql, expected):
    assert validate_single_select(sql) is expected
```

Note: this task only unit-tests the pure validation function. `run_sql_query` makes a real LLM call via Groq and is exercised manually in Task 10's end-to-end check (an automated test would either require a live `GROQ_API_KEY` and a live DB, or a mocked LangChain agent chain — out of scope for this bite-sized task per the spec's testing section, which calls for question→query-shape checks rather than exact behavioral mocking).

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/test_sql_agent.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `backend/app/ai/prompts.py`**

```python
SQL_AGENT_SYSTEM_PROMPT = """You are a data analyst assistant. Given a question and a database \
schema, write a single PostgreSQL SELECT statement that answers the question. \
Only use tables and columns that exist in the provided schema. Never write \
INSERT, UPDATE, DELETE, DROP, ALTER, or any statement other than a single SELECT. \
Return only the SQL query, with no explanation and no markdown formatting."""
```

- [ ] **Step 4: Create `backend/app/ai/sql_agent.py`**

```python
import re
from dataclasses import dataclass

import sqlparse
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from sqlalchemy import select
from sqlalchemy import text as sa_text

from app.ai.prompts import SQL_AGENT_SYSTEM_PROMPT
from app.core.config import settings
from app.core.database import async_session_maker, readonly_engine
from app.models import UploadedDataset

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


class SqlAgentError(Exception):
    pass


@dataclass
class SqlAgentResult:
    sql: str
    columns: list[str]
    rows: list[dict]


def validate_single_select(sql: str) -> bool:
    if not sql or not sql.strip():
        return False
    statements = [s for s in sqlparse.parse(sql) if s.token_first(skip_cm=True) is not None]
    if len(statements) != 1:
        return False
    return bool(_SELECT_ONLY.match(str(statements[0])))


async def _allowed_table_names() -> list[str]:
    async with async_session_maker() as session:
        result = await session.execute(select(UploadedDataset.table_name))
        return [row[0] for row in result.all()]


def _extract_sql(llm_output: str) -> str:
    cleaned = llm_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("sql").strip()
    return cleaned.rstrip(";").strip()


async def run_sql_query(question: str) -> SqlAgentResult:
    table_names = await _allowed_table_names()
    if not table_names:
        raise SqlAgentError("No datasets have been uploaded yet")

    db = SQLDatabase(engine=readonly_engine, include_tables=table_names)
    llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=settings.groq_api_key, temperature=0)

    schema = db.get_table_info()
    messages = [
        ("system", SQL_AGENT_SYSTEM_PROMPT),
        ("human", f"Schema:\n{schema}\n\nQuestion: {question}"),
    ]

    sql = ""
    for attempt in range(2):
        response = await llm.ainvoke(messages)
        sql = _extract_sql(response.content)
        if validate_single_select(sql):
            break
        messages.append(("ai", response.content))
        messages.append(
            (
                "human",
                f"That query was invalid or not a single SELECT statement: {sql!r}. "
                "Write a corrected single SELECT statement only.",
            )
        )

    if not validate_single_select(sql):
        raise SqlAgentError("Could not generate a valid SQL query for this question")

    async with readonly_engine.connect() as conn:
        result = await conn.execute(sa_text(sql))
        columns = list(result.keys())
        rows = [dict(row) for row in result.mappings().all()]

    return SqlAgentResult(sql=sql, columns=columns, rows=rows)
```

- [ ] **Step 5: Add `sqlparse` to `backend/pyproject.toml` dependencies**

Add `"sqlparse>=0.5"` to the `dependencies` list from Task 1, then run:

```bash
cd backend
uv sync
```

- [ ] **Step 6: Create `backend/app/ai/__init__.py`** (empty file)

- [ ] **Step 7: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/test_sql_agent.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/ai backend/pyproject.toml backend/tests/test_sql_agent.py
git commit -m "feat: add LangChain SQL agent with single-SELECT validation"
```

---

### Task 9: Chart picker

**Files:**
- Create: `backend/app/ai/chart_picker.py`
- Test: `backend/tests/test_chart_picker.py`

**Interfaces:**
- Consumes: `SqlAgentResult` (Task 8), `settings` (Task 1).
- Produces: `app.ai.chart_picker.ChartSpec` (dataclass: `chart_type: str` — one of `"bar"`, `"line"`, `"pie"`, `"table"`, `"stat_card"`; `x_field: str | None`, `y_field: str | None`, `title: str`).
- Produces: `app.ai.chart_picker.fallback_table_spec(question: str) -> ChartSpec` — pure function, no I/O.
- Produces: `async def pick_chart(question: str, result: SqlAgentResult) -> ChartSpec` — calls the LLM to choose a chart spec; on any exception or malformed response, returns `fallback_table_spec(question)` instead of raising.

- [ ] **Step 1: Write the failing tests — `backend/tests/test_chart_picker.py`**

```python
from unittest.mock import AsyncMock, patch

from app.ai.chart_picker import ChartSpec, fallback_table_spec, pick_chart
from app.ai.sql_agent import SqlAgentResult


def test_fallback_table_spec():
    spec = fallback_table_spec("revenue by region")
    assert spec.chart_type == "table"
    assert spec.title == "revenue by region"


async def test_pick_chart_parses_valid_llm_response():
    result = SqlAgentResult(
        sql="SELECT region, SUM(revenue) FROM sales_q1 GROUP BY region",
        columns=["region", "sum"],
        rows=[{"region": "East", "sum": 100}],
    )
    fake_response = AsyncMock()
    fake_response.content = (
        '{"chart_type": "bar", "x_field": "region", "y_field": "sum", '
        '"title": "Revenue by region"}'
    )
    with patch("app.ai.chart_picker.ChatGroq") as mock_llm_cls:
        mock_llm_cls.return_value.ainvoke = AsyncMock(return_value=fake_response)
        spec = await pick_chart("revenue by region", result)

    assert spec == ChartSpec(chart_type="bar", x_field="region", y_field="sum", title="Revenue by region")


async def test_pick_chart_falls_back_on_malformed_response():
    result = SqlAgentResult(sql="SELECT 1", columns=["1"], rows=[{"1": 1}])
    fake_response = AsyncMock()
    fake_response.content = "not valid json"
    with patch("app.ai.chart_picker.ChatGroq") as mock_llm_cls:
        mock_llm_cls.return_value.ainvoke = AsyncMock(return_value=fake_response)
        spec = await pick_chart("some question", result)

    assert spec == fallback_table_spec("some question")


async def test_pick_chart_falls_back_on_llm_exception():
    result = SqlAgentResult(sql="SELECT 1", columns=["1"], rows=[{"1": 1}])
    with patch("app.ai.chart_picker.ChatGroq") as mock_llm_cls:
        mock_llm_cls.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        spec = await pick_chart("some question", result)

    assert spec == fallback_table_spec("some question")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_chart_picker.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create `backend/app/ai/chart_picker.py`**

```python
import json
from dataclasses import dataclass

from langchain_groq import ChatGroq

from app.ai.sql_agent import SqlAgentResult
from app.core.config import settings

_CHART_PICKER_PROMPT = """Given a question and a sample of SQL query results, choose the best \
chart type to visualize the answer. Respond with ONLY a JSON object of the form:
{{"chart_type": "bar"|"line"|"pie"|"table"|"stat_card", "x_field": "<column name or null>", \
"y_field": "<column name or null>", "title": "<short chart title>"}}

Use "stat_card" for a single-value result, "table" when no clear chart applies.

Question: {question}
Columns: {columns}
Sample rows: {sample_rows}"""


@dataclass
class ChartSpec:
    chart_type: str
    x_field: str | None
    y_field: str | None
    title: str


def fallback_table_spec(question: str) -> ChartSpec:
    return ChartSpec(chart_type="table", x_field=None, y_field=None, title=question)


async def pick_chart(question: str, result: SqlAgentResult) -> ChartSpec:
    try:
        llm = ChatGroq(model="llama-3.3-70b-versatile", api_key=settings.groq_api_key, temperature=0)
        prompt = _CHART_PICKER_PROMPT.format(
            question=question,
            columns=result.columns,
            sample_rows=result.rows[:5],
        )
        response = await llm.ainvoke(prompt)
        data = json.loads(response.content)
        return ChartSpec(
            chart_type=data["chart_type"],
            x_field=data.get("x_field"),
            y_field=data.get("y_field"),
            title=data.get("title", question),
        )
    except Exception:
        return fallback_table_spec(question)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_chart_picker.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ai/chart_picker.py backend/tests/test_chart_picker.py
git commit -m "feat: add LLM chart picker with table fallback"
```

---

### Task 10: POST /api/chat endpoint

**Files:**
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_chat_api.py`

**Interfaces:**
- Consumes: `run_sql_query` + `SqlAgentError` (Task 8), `pick_chart` (Task 9), `ChatMessage` (Task 3), `get_db` (Task 2).
- Produces: `POST /api/chat` with body `{"question": str}` → `200`: `{"question": str, "sql": str | None, "columns": list[str], "rows": list[dict], "chart": {"chart_type": str, "x_field": str | None, "y_field": str | None, "title": str}}`. On `SqlAgentError`, returns `200` with `{"question": str, "sql": None, "columns": [], "rows": [], "chart": null, "error": "Sorry, I couldn't answer that question."}`.

- [ ] **Step 1: Write the failing tests — `backend/tests/test_chat_api.py`**

```python
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient

from app.ai.chart_picker import ChartSpec
from app.ai.sql_agent import SqlAgentError, SqlAgentResult
from app.core.database import async_session_maker
from app.main import app
from app.models import ChatMessage


async def test_chat_success_persists_message_and_returns_chart():
    fake_result = SqlAgentResult(
        sql="SELECT region, SUM(revenue) AS total FROM sales_q1 GROUP BY region",
        columns=["region", "total"],
        rows=[{"region": "East", "total": 100}],
    )
    fake_spec = ChartSpec(chart_type="bar", x_field="region", y_field="total", title="Revenue by region")

    with patch("app.api.chat.run_sql_query", new=AsyncMock(return_value=fake_result)), patch(
        "app.api.chat.pick_chart", new=AsyncMock(return_value=fake_spec)
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"question": "revenue by region"})

    assert response.status_code == 200
    body = response.json()
    assert body["chart"]["chart_type"] == "bar"
    assert body["rows"] == [{"region": "East", "total": 100}]

    async with async_session_maker() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(ChatMessage).where(ChatMessage.question == "revenue by region")
        )
        saved = result.scalars().first()
        assert saved is not None
        assert saved.sql_query == fake_result.sql


async def test_chat_agent_failure_returns_friendly_error():
    with patch(
        "app.api.chat.run_sql_query", new=AsyncMock(side_effect=SqlAgentError("no good query"))
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/chat", json={"question": "gibberish question"})

    assert response.status_code == 200
    body = response.json()
    assert body["sql"] is None
    assert "error" in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
uv run pytest tests/test_chat_api.py -v
```

Expected: FAIL (404, route doesn't exist).

- [ ] **Step 3: Create `backend/app/api/chat.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chart_picker import pick_chart
from app.ai.sql_agent import SqlAgentError, run_sql_query
from app.core.database import get_db
from app.models import ChatMessage

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await run_sql_query(request.question)
    except SqlAgentError:
        message = ChatMessage(question=request.question, sql_query=None, result_summary=None, chart_spec=None)
        db.add(message)
        await db.commit()
        return {
            "question": request.question,
            "sql": None,
            "columns": [],
            "rows": [],
            "chart": None,
            "error": "Sorry, I couldn't answer that question.",
        }

    chart_spec = await pick_chart(request.question, result)

    message = ChatMessage(
        question=request.question,
        sql_query=result.sql,
        result_summary=f"{len(result.rows)} row(s) returned",
        chart_spec={
            "chart_type": chart_spec.chart_type,
            "x_field": chart_spec.x_field,
            "y_field": chart_spec.y_field,
            "title": chart_spec.title,
        },
    )
    db.add(message)
    await db.commit()

    return {
        "question": request.question,
        "sql": result.sql,
        "columns": result.columns,
        "rows": result.rows,
        "chart": {
            "chart_type": chart_spec.chart_type,
            "x_field": chart_spec.x_field,
            "y_field": chart_spec.y_field,
            "title": chart_spec.title,
        },
    }
```

- [ ] **Step 4: Modify `backend/app/main.py` to register the router**

```python
from app.api.chat import router as chat_router

app.include_router(chat_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend
uv run pytest tests/test_chat_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/app/main.py backend/tests/test_chat_api.py
git commit -m "feat: add POST /api/chat endpoint tying together SQL agent and chart picker"
```

---

### Task 11: GET /api/chat/history endpoint

**Files:**
- Create: `backend/app/api/history.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_history_api.py`

**Interfaces:**
- Consumes: `ChatMessage` (Task 3), `get_db` (Task 2).
- Produces: `GET /api/chat/history` → `200`: `[{"id": int, "question": str, "sql_query": str | None, "result_summary": str | None, "chart_spec": dict | None, "created_at": str}]`, ordered oldest first.

- [ ] **Step 1: Write the failing test — `backend/tests/test_history_api.py`**

```python
from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_history_returns_messages_in_order():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/chat", json={"question": "first question, unmatched to any table"})
        response = await client.get("/api/chat/history")

    assert response.status_code == 200
    body = response.json()
    assert any(m["question"] == "first question, unmatched to any table" for m in body)
    timestamps = [m["created_at"] for m in body]
    assert timestamps == sorted(timestamps)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend
uv run pytest tests/test_history_api.py -v
```

Expected: FAIL (404, route doesn't exist).

- [ ] **Step 3: Create `backend/app/api/history.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ChatMessage

router = APIRouter(prefix="/api/chat", tags=["history"])


@router.get("/history")
async def get_history(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatMessage).order_by(ChatMessage.created_at.asc()))
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "question": m.question,
            "sql_query": m.sql_query,
            "result_summary": m.result_summary,
            "chart_spec": m.chart_spec,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]
```

- [ ] **Step 4: Modify `backend/app/main.py` to register the router**

```python
from app.api.history import router as history_router

app.include_router(history_router)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend
uv run pytest tests/test_history_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/history.py backend/app/main.py backend/tests/test_history_api.py
git commit -m "feat: add GET /api/chat/history endpoint"
```

---

### Task 12: Frontend scaffold — Vite, Tailwind, API service

**Files:**
- Create: `frontend/` (via Vite scaffold)
- Create: `frontend/src/services/api.js`
- Create: `frontend/.env.example`
- Modify: `frontend/tailwind.config.js`, `frontend/src/index.css` (Tailwind setup)

**Interfaces:**
- Produces: `frontend/src/services/api.js` exporting `uploadFile(file)`, `sendMessage(question)`, `getDatasets()`, `deleteDataset(id)`, `getHistory()` — all async functions using axios against `import.meta.env.VITE_API_BASE_URL`.

- [ ] **Step 1: Scaffold the Vite React app**

```bash
cd "C:\Storage\PROJECTS\NL to SQL"
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install axios recharts
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Configure `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 3: Replace `frontend/src/index.css` contents**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Create `frontend/.env.example`**

```
VITE_API_BASE_URL=http://localhost:8000
```

Then copy it: `cp .env.example .env` (from inside `frontend/`).

- [ ] **Step 5: Create `frontend/src/services/api.js`**

```javascript
import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

export async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await client.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function sendMessage(question) {
  const response = await client.post("/api/chat", { question });
  return response.data;
}

export async function getDatasets() {
  const response = await client.get("/api/datasets");
  return response.data;
}

export async function deleteDataset(id) {
  await client.delete(`/api/datasets/${id}`);
}

export async function getHistory() {
  const response = await client.get("/api/chat/history");
  return response.data;
}
```

- [ ] **Step 6: Verify the build succeeds**

```bash
cd frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 7: Commit**

```bash
cd "C:\Storage\PROJECTS\NL to SQL"
git add frontend
git commit -m "feat: scaffold Vite/React/Tailwind frontend with API service"
```

---

### Task 13: FileUpload and DatasetList components

**Files:**
- Create: `frontend/src/components/FileUpload.jsx`
- Create: `frontend/src/components/DatasetList.jsx`

**Interfaces:**
- Consumes: `uploadFile`, `getDatasets`, `deleteDataset` (Task 12).
- Produces: `FileUpload({ onUploaded })` — renders a file input, calls `uploadFile`, invokes `onUploaded(datasetSummary)` on success, shows the returned columns/row count, shows an error message on failure.
- Produces: `DatasetList({ datasets, onDelete })` — renders each dataset's `table_name`, `row_count`, and a delete button that calls `onDelete(id)`.

- [ ] **Step 1: Create `frontend/src/components/FileUpload.jsx`**

```jsx
import { useState } from "react";
import { uploadFile } from "../services/api";

export default function FileUpload({ onUploaded }) {
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(event) {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    setError(null);
    try {
      const result = await uploadFile(file);
      onUploaded(result);
    } catch (err) {
      setError(err.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  return (
    <div className="p-4 border border-dashed border-gray-400 rounded-lg">
      <input type="file" accept=".csv,.xlsx,.xls" onChange={handleChange} disabled={uploading} />
      {uploading && <p className="text-sm text-gray-500 mt-2">Uploading...</p>}
      {error && <p className="text-sm text-red-600 mt-2">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/DatasetList.jsx`**

```jsx
export default function DatasetList({ datasets, onDelete }) {
  if (datasets.length === 0) {
    return <p className="text-sm text-gray-500">No datasets uploaded yet.</p>;
  }

  return (
    <ul className="space-y-2">
      {datasets.map((dataset) => (
        <li key={dataset.id} className="flex justify-between items-center p-2 bg-gray-100 rounded">
          <div>
            <p className="font-medium">{dataset.table_name}</p>
            <p className="text-xs text-gray-500">{dataset.row_count} rows</p>
          </div>
          <button
            className="text-sm text-red-600 hover:underline"
            onClick={() => onDelete(dataset.id)}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Verify the build succeeds**

```bash
cd frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 4: Commit**

```bash
cd "C:\Storage\PROJECTS\NL to SQL"
git add frontend/src/components/FileUpload.jsx frontend/src/components/DatasetList.jsx
git commit -m "feat: add FileUpload and DatasetList components"
```

---

### Task 14: ChatInterface and ChartRenderer components

**Files:**
- Create: `frontend/src/components/ChartRenderer.jsx`
- Create: `frontend/src/components/ChatInterface.jsx`

**Interfaces:**
- Consumes: `sendMessage` (Task 12).
- Produces: `ChartRenderer({ chart, rows })` — renders a Recharts `BarChart`/`LineChart`/`PieChart` for `chart.chart_type` in `{"bar","line","pie"}` using `chart.x_field`/`chart.y_field`; a plain HTML table for `"table"`; a single large number for `"stat_card"`.
- Produces: `ChatInterface({ initialHistory })` — question input, sends via `sendMessage`, appends each exchange (question, SQL, `ChartRenderer`) to a scrollable message list, seeded from `initialHistory`.

- [ ] **Step 1: Create `frontend/src/components/ChartRenderer.jsx`**

```jsx
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const COLORS = ["#2563eb", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#0891b2"];

export default function ChartRenderer({ chart, rows }) {
  if (!chart || rows.length === 0) {
    return <p className="text-sm text-gray-500">No data to display.</p>;
  }

  if (chart.chart_type === "stat_card") {
    const value = Object.values(rows[0])[0];
    return (
      <div className="p-4 bg-gray-100 rounded-lg text-center">
        <p className="text-3xl font-semibold">{value}</p>
        <p className="text-sm text-gray-500">{chart.title}</p>
      </div>
    );
  }

  if (chart.chart_type === "bar") {
    return (
      <BarChart width={400} height={250} data={rows}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={chart.x_field} />
        <YAxis />
        <Tooltip />
        <Bar dataKey={chart.y_field} fill={COLORS[0]} />
      </BarChart>
    );
  }

  if (chart.chart_type === "line") {
    return (
      <LineChart width={400} height={250} data={rows}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={chart.x_field} />
        <YAxis />
        <Tooltip />
        <Line type="monotone" dataKey={chart.y_field} stroke={COLORS[0]} />
      </LineChart>
    );
  }

  if (chart.chart_type === "pie") {
    return (
      <PieChart width={400} height={250}>
        <Pie data={rows} dataKey={chart.y_field} nameKey={chart.x_field} label>
          {rows.map((_, index) => (
            <Cell key={index} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    );
  }

  const columns = Object.keys(rows[0]);
  return (
    <table className="text-sm border-collapse">
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col} className="border px-2 py-1 bg-gray-100 text-left">
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {columns.map((col) => (
              <td key={col} className="border px-2 py-1">
                {String(row[col])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/ChatInterface.jsx`**

```jsx
import { useState } from "react";
import { sendMessage } from "../services/api";
import ChartRenderer from "./ChartRenderer";

function historyToMessages(history) {
  return history.map((m) => ({
    question: m.question,
    sql: m.sql_query,
    chart: m.chart_spec,
    rows: [],
    error: m.sql_query ? null : "No answer was generated for this question.",
  }));
}

export default function ChatInterface({ initialHistory }) {
  const [messages, setMessages] = useState(historyToMessages(initialHistory));
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!question.trim()) return;

    setSending(true);
    try {
      const result = await sendMessage(question);
      setMessages((prev) => [
        ...prev,
        {
          question: result.question,
          sql: result.sql,
          chart: result.chart,
          rows: result.rows,
          error: result.error ?? null,
        },
      ]);
      setQuestion("");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        {messages.map((message, i) => (
          <div key={i} className="border-b pb-4">
            <p className="font-medium">{message.question}</p>
            {message.sql && (
              <details className="text-xs text-gray-500 mt-1">
                <summary>SQL</summary>
                <pre className="whitespace-pre-wrap">{message.sql}</pre>
              </details>
            )}
            {message.error ? (
              <p className="text-sm text-red-600 mt-2">{message.error}</p>
            ) : (
              <div className="mt-2">
                <ChartRenderer chart={message.chart} rows={message.rows} />
              </div>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 p-4 border-t">
        <input
          className="flex-1 border rounded px-3 py-2"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about your data..."
          disabled={sending}
        />
        <button
          type="submit"
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
          disabled={sending}
        >
          Ask
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Verify the build succeeds**

```bash
cd frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 4: Commit**

```bash
cd "C:\Storage\PROJECTS\NL to SQL"
git add frontend/src/components/ChartRenderer.jsx frontend/src/components/ChatInterface.jsx
git commit -m "feat: add ChatInterface and ChartRenderer components"
```

---

### Task 15: Dashboard integration and App wiring

**Files:**
- Create: `frontend/src/components/Dashboard.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `FileUpload`, `DatasetList` (Task 13), `ChatInterface` (Task 14), `getDatasets`, `deleteDataset`, `getHistory` (Task 12).
- Produces: `Dashboard()` — on mount, loads datasets and chat history; lays out `DatasetList`/`FileUpload` in a sidebar and `ChatInterface` in the main panel; passes a live `onUploaded` handler that refreshes the dataset list.

- [ ] **Step 1: Create `frontend/src/components/Dashboard.jsx`**

```jsx
import { useEffect, useState } from "react";
import ChatInterface from "./ChatInterface";
import DatasetList from "./DatasetList";
import FileUpload from "./FileUpload";
import { deleteDataset, getDatasets, getHistory } from "../services/api";

export default function Dashboard() {
  const [datasets, setDatasets] = useState([]);
  const [history, setHistory] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    async function load() {
      const [datasetsResult, historyResult] = await Promise.all([getDatasets(), getHistory()]);
      setDatasets(datasetsResult);
      setHistory(historyResult);
      setLoaded(true);
    }
    load();
  }, []);

  async function refreshDatasets() {
    setDatasets(await getDatasets());
  }

  async function handleDelete(id) {
    await deleteDataset(id);
    await refreshDatasets();
  }

  if (!loaded) {
    return <p className="p-4 text-gray-500">Loading...</p>;
  }

  return (
    <div className="flex h-screen">
      <aside className="w-72 border-r p-4 space-y-4 overflow-y-auto">
        <h2 className="font-semibold text-lg">Datasets</h2>
        <FileUpload onUploaded={refreshDatasets} />
        <DatasetList datasets={datasets} onDelete={handleDelete} />
      </aside>
      <main className="flex-1">
        <ChatInterface initialHistory={history} />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Modify `frontend/src/App.jsx`**

```jsx
import Dashboard from "./components/Dashboard";

function App() {
  return <Dashboard />;
}

export default App;
```

- [ ] **Step 3: Verify the build succeeds**

```bash
cd frontend
npm run build
```

Expected: build completes with no errors.

- [ ] **Step 4: Manual end-to-end check**

With the Postgres instance set up (Task 2's `init_db.sql` run), backend running (`cd backend && uv run uvicorn app.main:app --reload`) and frontend running (`cd frontend && npm run dev`):

1. Upload a small CSV via the sidebar — confirm it appears in the dataset list.
2. Ask a question referencing that data — confirm a chart or table renders and the SQL is visible under "SQL".
3. Refresh the page — confirm the prior exchange still appears (loaded from `/api/chat/history`).
4. Delete the dataset — confirm it disappears from the list and its Postgres table is dropped.

- [ ] **Step 5: Commit**

```bash
cd "C:\Storage\PROJECTS\NL to SQL"
git add frontend/src/components/Dashboard.jsx frontend/src/App.jsx
git commit -m "feat: wire up Dashboard integrating datasets, upload, and chat"
```
