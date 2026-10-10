# RAG Data Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-user web app where users upload PDF/TXT/DOCX documents and ask questions answered by a streamed, cited RAG pipeline (MongoDB Atlas Vector Search + LangGraph + ChatGroq), with a Recharts speed/usage dashboard.

**Architecture:** FastAPI backend: `ingestion/` turns uploads into chunks stored via LangChain's `MongoDBAtlasVectorSearch` (wrapped by our `ChunkStore`); `rag/graph.py` runs a LangGraph retrieve → generate graph and yields `meta` / `token` / `done` events; `api/query.py` persists conversations/messages with Beanie and streams the events as Server-Sent Events. React (Vite) frontend with Chat and Dashboard tabs consumes the stream with `fetch` + `ReadableStream`.

**Tech Stack:** Python 3.13 via `uv`, FastAPI, Beanie 2.x (on PyMongo async), pymongo, langchain-core, langchain-mongodb, langchain-groq, langchain-huggingface + sentence-transformers, langchain-text-splitters, LangGraph, pypdf, docx2txt; React 19, Vite, Tailwind CSS v4, Recharts, react-markdown, Vitest.

**Spec:** `docs/specs/2026-10-10-rag-assistant-design.md`

## Global Constraints

- Supported uploads: `pdf`, `txt`, `docx` only; max **20 MB** (20 * 1024 * 1024 bytes).
- Chunking: `RecursiveCharacterTextSplitter`, `chunk_size=1000`, `chunk_overlap=150`.
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`, **384** dimensions, cosine similarity.
- Atlas vector index name `vector_index` on collection `chunks`, path `embedding`.
- Retrieval: k = **4**, `numCandidates` **100** (`oversampling_factor=25`).
- Conversation context: last **6** messages.
- Question length: 1–**2000** characters.
- Snippets: ≤ **200** characters; conversation title: first question truncated to **60** characters.
- Exact user-facing strings: `"I couldn't find that in your documents."`, `"Upload a document first, then ask me about it."`, `"No readable text found — scanned PDFs aren't supported."`, `"Could not process the document."`, `"Sorry, something went wrong while answering."`.
- Config via `backend/.env`: `MONGODB_URI` (required), `MONGODB_DB` (default `rag_assistant`), `GROQ_API_KEY` (required), `GROQ_MODEL` (default `openai/gpt-oss-120b`), `EMBEDDING_MODEL` (default `sentence-transformers/all-MiniLM-L6-v2`).
- Frontend: `VITE_API_BASE_URL` (default `http://localhost:8000`); dev server on port 5173.
- `langchain-community` is being sunset (deprecation warning in current releases), so PDF/DOCX text is read with `pypdf` / `docx2txt` directly and wrapped in our own `Page` objects instead of `PyPDFLoader` / `Docx2txtLoader`.
- All backend commands run from `backend/`. Integration tests use database `<MONGODB_DB>_test` and are **skipped** when `MONGODB_URI` is not set; until the Atlas connection string is in `backend/.env`, "Expected: PASS" for integration tests reads "Expected: SKIPPED".
- On this Windows machine, start the backend with `.venv/Scripts/python.exe -m uvicorn ...` (the `uvicorn.exe` launcher has been blocked by Smart App Control before).

## Review Focus

1. A TXT file that is not UTF-8 (Windows-1252 / Latin-1) or has a UTF-8 BOM should load with readable text, not crash or show `\ufeff` — pinned in Task 3.
2. Upper-case or missing extensions (`REPORT.PDF`, `notes`) should be accepted / rejected with the clear "unsupported" message, not a 500 — pinned in Task 3.
3. An SSE event split across network reads (and `\r\n` line endings) must still parse into exactly one event — pinned in Task 9.
4. The LLM's "not found" reply with a typographic apostrophe (`couldn’t`) or without the trailing period must still clear the sources — pinned in Task 6.
5. If deleting a document's chunks fails, the document record must remain so the user can retry (no orphaned chunks) — pinned in Task 5.

---

## File Structure

```
.gitignore
README.md
backend/
├── pyproject.toml
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                  # app, lifespan, CORS, routers, /health
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Settings
│   │   └── database.py          # init_db/close_db (Beanie), sync client, chunks collection
│   ├── models/
│   │   ├── __init__.py          # exports StoredDocument, Conversation, Message, Source, Metrics
│   │   ├── document.py
│   │   ├── conversation.py
│   │   └── message.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── loaders.py           # load_pages(); DocumentLoadError; Page
│   │   └── pipeline.py          # split_pages(); ingest_document(); IngestionError
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── embeddings.py        # get_embeddings()
│   │   ├── vector_store.py      # ChunkStore, get_chunk_store(), ensure_vector_index()
│   │   ├── prompts.py           # RAG_SYSTEM_PROMPT and answer strings
│   │   └── graph.py             # build_graph(), stream_answer(), build_sources()
│   └── api/
│       ├── __init__.py
│       ├── deps.py              # get_store(), get_llm()
│       ├── sse.py               # format_sse()
│       ├── serializers.py       # document/message/conversation -> dict
│       ├── upload.py
│       ├── documents.py
│       ├── query.py
│       ├── conversations.py
│       └── stats.py
└── tests/
    ├── conftest.py              # env setup, mongo/client fixtures
    ├── fakes.py                 # FakeChunkStore, hit(), fake_llm(), FailingChatModel
    ├── files.py                 # make_pdf(), make_docx()
    ├── test_health.py
    ├── test_embeddings.py
    ├── test_models.py
    ├── test_loaders.py
    ├── test_pipeline.py
    ├── test_documents_api.py
    ├── test_graph.py
    ├── test_sse.py
    ├── test_query_api.py
    ├── test_conversations_api.py
    └── test_stats_api.py
frontend/
├── package.json
├── vite.config.js
├── index.html
├── .env.example
└── src/
    ├── main.jsx
    ├── index.css
    ├── App.jsx
    ├── services/
    │   ├── api.js
    │   └── api.test.js
    └── components/
        ├── Sidebar.jsx
        ├── FileUpload.jsx
        ├── DocumentList.jsx
        ├── ConversationList.jsx
        ├── ChatView.jsx
        ├── MessageBubble.jsx
        └── Dashboard.jsx
```

---

### Task 1: Backend scaffold, config, health endpoint, embeddings check

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/rag/__init__.py`, `backend/app/rag/embeddings.py`, `backend/tests/conftest.py`, `backend/tests/test_health.py`, `backend/tests/test_embeddings.py`

**Interfaces:**
- Produces: `app.core.config.settings` (fields `mongodb_uri`, `mongodb_db`, `groq_api_key`, `groq_model`, `embedding_model`, `cors_origins`); `app.rag.embeddings.get_embeddings() -> langchain_core.embeddings.Embeddings`; `app.rag.embeddings.EMBEDDING_DIMENSIONS = 384`; `app.main.app`; test fixtures module `tests/conftest.py` exposing `HAS_MONGO` and fixture `bare_client`.

- [ ] **Step 1: Create `.gitignore` (repo root)**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
.env
node_modules/
dist/
*.log
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "rag-assistant-backend"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "python-multipart>=0.0.9",
    "pydantic-settings>=2.5",
    "beanie>=2.0",
    "pymongo>=4.10",
    "langchain-core>=1.0",
    "langchain-mongodb>=0.12",
    "langchain-groq>=1.0",
    "langchain-huggingface>=1.0",
    "sentence-transformers>=3.0",
    "langchain-text-splitters>=1.0",
    "langgraph>=1.0",
    "pypdf>=5.0",
    "docx2txt>=0.8",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=1.0",
    "httpx>=0.27",
    "fpdf2>=2.8",
    "python-docx>=1.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
# Mongo clients are bound to one event loop, so all tests share a single loop.
asyncio_default_test_loop_scope = "session"
asyncio_default_fixture_loop_scope = "session"
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: Create `backend/.env.example`**

```dotenv
# MongoDB Atlas connection string (Atlas UI -> Connect -> Drivers)
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=rag_assistant
GROQ_API_KEY=your-groq-api-key
# Any chat model listed at https://console.groq.com/docs/models
GROQ_MODEL=openai/gpt-oss-120b
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Then create `backend/.env` by copying `.env.example` and filling `GROQ_API_KEY` (from the old worktree's `backend/.env`) and `MONGODB_URI` (from the user; leave the placeholder line out entirely if not yet available — see conftest below).

- [ ] **Step 4: Install dependencies**

Run: `cd backend && uv sync`
Expected: creates `backend/.venv`, installs all packages (PyTorch is a large download).

- [ ] **Step 5: Write `backend/app/core/config.py` and empty package files**

Create empty `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/rag/__init__.py`.

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str
    mongodb_db: str = "rag_assistant"
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
```

- [ ] **Step 6: Write `backend/tests/conftest.py`**

```python
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values
from httpx import ASGITransport, AsyncClient

# Configure the environment before any `app` import: settings are module-level.
_env = {**dotenv_values(Path(__file__).resolve().parent.parent / ".env"), **os.environ}
HAS_MONGO = bool(_env.get("MONGODB_URI"))
os.environ["MONGODB_URI"] = _env.get("MONGODB_URI") or "mongodb://localhost:1"
os.environ["GROQ_API_KEY"] = _env.get("GROQ_API_KEY") or "test-key"
_db = _env.get("MONGODB_DB") or "rag_assistant"
os.environ["MONGODB_DB"] = _db if _db.endswith("_test") else f"{_db}_test"


@pytest.fixture
async def bare_client():
    """HTTP client for endpoints that need no database."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

- [ ] **Step 7: Write the failing health test `backend/tests/test_health.py`**

```python
async def test_health_returns_ok(bare_client):
    response = await bare_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 8: Run it to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 9: Write `backend/app/main.py` (minimal; lifespan comes in Task 2)**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

app = FastAPI(title="RAG Data Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 10: Run the health test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 11: Write the failing embeddings test `backend/tests/test_embeddings.py`**

This is also the Smart App Control check for PyTorch.

```python
import math

from app.rag.embeddings import EMBEDDING_DIMENSIONS, get_embeddings


def test_embeddings_are_384_dim_and_normalized():
    vector = get_embeddings().embed_query("What is retrieval-augmented generation?")
    assert len(vector) == EMBEDDING_DIMENSIONS == 384
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-3)


def test_similar_texts_score_higher_than_unrelated():
    emb = get_embeddings()
    query, close, far = emb.embed_documents(
        ["How do I reset my password?", "Steps to change your account password", "The cat sat on the mat"]
    )
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert dot(query, close) > dot(query, far)
```

- [ ] **Step 12: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rag.embeddings'`

- [ ] **Step 13: Write `backend/app/rag/embeddings.py`**

```python
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.core.config import settings

EMBEDDING_DIMENSIONS = 384


@lru_cache
def get_embeddings() -> Embeddings:
    # Imported lazily: loading PyTorch takes seconds and is only needed once.
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )
```

- [ ] **Step 14: Run the embeddings test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_embeddings.py -v`
Expected: PASS (first run downloads ~90 MB model).

**If it fails with `DLL load failed ... An Application Control policy has blocked this file`** (PyTorch blocked by Smart App Control): retry once (first-sight blocks can clear). If still blocked, switch to the fastembed fallback — same model, ONNX, no PyTorch:
1. `uv remove langchain-huggingface sentence-transformers && uv add fastembed`
2. Replace `get_embeddings` body with:

```python
@lru_cache
def get_embeddings() -> Embeddings:
    return _FastEmbedMiniLM(settings.embedding_model)


class _FastEmbedMiniLM(Embeddings):
    """all-MiniLM-L6-v2 via ONNX (fastembed); used where PyTorch can't load."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
```
3. Re-run the test; expected PASS. Note the switch in the commit message.

- [ ] **Step 15: Commit**

```bash
git add .gitignore backend/pyproject.toml backend/uv.lock backend/.env.example backend/app backend/tests
git commit -m "feat: scaffold backend with config, health endpoint and local embeddings"
```

---

### Task 2: MongoDB connection and Beanie models

**Files:**
- Create: `backend/app/core/database.py`, `backend/app/models/__init__.py`, `backend/app/models/document.py`, `backend/app/models/conversation.py`, `backend/app/models/message.py`, `backend/tests/test_models.py`
- Modify: `backend/tests/conftest.py` (add `mongo` and `client` fixtures)

**Interfaces:**
- Consumes: `settings` (Task 1).
- Produces:
  - `app.core.database`: `async init_db() -> None`, `async close_db() -> None`, `get_sync_client() -> pymongo.MongoClient`, `get_chunks_collection() -> pymongo.collection.Collection`, `utcnow() -> datetime`.
  - `app.models.DOCUMENT_MODELS` (list of all Beanie document classes).
  - `app.models`: `StoredDocument(filename: str, file_type: str, size_bytes: int, page_count: int, chunk_count: int, uploaded_at: datetime)`; `Conversation(title: str, created_at, updated_at)`; `Source(filename: str, page: int, snippet: str)`; `Metrics(model: str, ttft_ms: int, total_ms: int, output_tokens: int, tokens_per_sec: float, chunks_retrieved: int)`; `Message(conversation_id: PydanticObjectId, role: Literal["user","assistant"], content: str, sources: list[Source], metrics: Metrics | None, status: Literal["complete","error"], created_at)`.
  - conftest fixtures `mongo` (inits Beanie on the test DB, clears collections, skips without Atlas) and `client` (HTTP client on a DB-backed app; clears `app.dependency_overrides` after).

- [ ] **Step 1: Write the failing test `backend/tests/test_models.py`**

```python
from app.models import Conversation, Message, Metrics, Source, StoredDocument


async def test_message_round_trip_with_sources_and_metrics(mongo):
    conversation = Conversation(title="What is in the handbook?")
    await conversation.insert()
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Vacation is 20 days [handbook.pdf p.3].",
        sources=[Source(filename="handbook.pdf", page=3, snippet="Employees get 20 days")],
        metrics=Metrics(
            model="openai/gpt-oss-120b", ttft_ms=300, total_ms=900,
            output_tokens=40, tokens_per_sec=66.7, chunks_retrieved=4,
        ),
    )
    await message.insert()

    fetched = await Message.find_one(Message.conversation_id == conversation.id)
    assert fetched.sources[0].page == 3
    assert fetched.metrics.tokens_per_sec == 66.7
    assert fetched.status == "complete"
    assert fetched.created_at.tzinfo is not None


async def test_stored_document_defaults_uploaded_at(mongo):
    doc = StoredDocument(filename="a.txt", file_type="txt", size_bytes=10, page_count=1, chunk_count=1)
    await doc.insert()
    assert (await StoredDocument.get(doc.id)).uploaded_at is not None
```

- [ ] **Step 2: Add fixtures to `backend/tests/conftest.py`** (append)

```python
@pytest.fixture
async def mongo():
    """Beanie on the Atlas test database with empty collections."""
    if not HAS_MONGO:
        pytest.skip("MONGODB_URI not set; skipping integration test")
    from app.core.database import close_db, init_db
    from app.models import DOCUMENT_MODELS

    await init_db()
    for model in DOCUMENT_MODELS:
        await model.delete_all()
    yield
    await close_db()


@pytest.fixture
async def client(mongo):
    """HTTP client against the app, with Beanie initialised on the test DB."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models'` (collection error, even without Atlas).

- [ ] **Step 4: Write the models**

`backend/app/core/database.py`:

```python
from datetime import datetime, timezone
from functools import lru_cache

from beanie import init_beanie
from pymongo import AsyncMongoClient, MongoClient
from pymongo.collection import Collection

from app.core.config import settings

CHUNKS_COLLECTION = "chunks"

_async_client: AsyncMongoClient | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def init_db() -> None:
    from app.models import DOCUMENT_MODELS

    global _async_client
    _async_client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
    await init_beanie(database=_async_client[settings.mongodb_db], document_models=DOCUMENT_MODELS)


async def close_db() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.close()
        _async_client = None


@lru_cache
def get_sync_client() -> MongoClient:
    """Sync client for LangChain's MongoDBAtlasVectorSearch, which uses PyMongo's sync API."""
    return MongoClient(settings.mongodb_uri, tz_aware=True)


def get_chunks_collection() -> Collection:
    return get_sync_client()[settings.mongodb_db][CHUNKS_COLLECTION]
```

(`init_db` imports `app.models` inside the function because the model modules import `utcnow` from this module.)

`backend/app/models/document.py`:

```python
from datetime import datetime

from beanie import Document
from pydantic import Field

from app.core.database import utcnow


class StoredDocument(Document):
    filename: str
    file_type: str
    size_bytes: int
    page_count: int
    chunk_count: int
    uploaded_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "documents"
```

`backend/app/models/conversation.py`:

```python
from datetime import datetime

from beanie import Document
from pydantic import Field

from app.core.database import utcnow


class Conversation(Document):
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "conversations"
```

`backend/app/models/message.py`:

```python
from datetime import datetime
from typing import Annotated, Literal

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field

from app.core.database import utcnow


class Source(BaseModel):
    filename: str
    page: int
    snippet: str


class Metrics(BaseModel):
    model: str
    ttft_ms: int
    total_ms: int
    output_tokens: int
    tokens_per_sec: float
    chunks_retrieved: int


class Message(Document):
    conversation_id: Annotated[PydanticObjectId, Indexed()]
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = Field(default_factory=list)
    metrics: Metrics | None = None
    status: Literal["complete", "error"] = "complete"
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "messages"
```

`backend/app/models/__init__.py`:

```python
from app.models.conversation import Conversation
from app.models.document import StoredDocument
from app.models.message import Message, Metrics, Source

DOCUMENT_MODELS = [StoredDocument, Conversation, Message]

__all__ = ["Conversation", "DOCUMENT_MODELS", "Message", "Metrics", "Source", "StoredDocument"]
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: PASS (SKIPPED without `MONGODB_URI`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/database.py backend/app/models backend/tests
git commit -m "feat: add MongoDB connection and Beanie models"
```

---

### Task 3: Document loaders (PDF / TXT / DOCX)

**Files:**
- Create: `backend/app/ingestion/__init__.py` (empty), `backend/app/ingestion/loaders.py`, `backend/tests/files.py`, `backend/tests/test_loaders.py`

**Interfaces:**
- Produces: `Page(text: str, page_number: int)` (frozen dataclass); `DocumentLoadError(ValueError)` with a user-facing message; `MAX_FILE_BYTES = 20 * 1024 * 1024`; `detect_file_type(filename: str) -> str`; `load_pages(filename: str, content: bytes) -> tuple[str, list[Page]]` (returns file type and non-empty pages, 1-based page numbers). Test helpers `tests.files.make_pdf(pages: list[str]) -> bytes`, `tests.files.make_docx(paragraphs: list[str]) -> bytes`.

- [ ] **Step 1: Write test helpers `backend/tests/files.py`**

```python
from io import BytesIO

import docx
from fpdf import FPDF


def make_pdf(pages: list[str]) -> bytes:
    """One PDF page per string; an empty string makes a blank page."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        if text:
            pdf.multi_cell(0, 10, text)
    return bytes(pdf.output())


def make_docx(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
```

- [ ] **Step 2: Write the failing tests `backend/tests/test_loaders.py`**

```python
import pytest

from app.ingestion.loaders import MAX_FILE_BYTES, DocumentLoadError, Page, load_pages
from tests.files import make_docx, make_pdf


def test_pdf_pages_keep_page_numbers_and_skip_blank_pages():
    file_type, pages = load_pages("guide.pdf", make_pdf(["Intro to refunds", "", "Shipping takes 5 days"]))
    assert file_type == "pdf"
    assert [p.page_number for p in pages] == [1, 3]
    assert "refunds" in pages[0].text
    assert "Shipping" in pages[1].text


def test_uppercase_extension_is_accepted():
    file_type, _ = load_pages("REPORT.PDF", make_pdf(["Quarterly numbers"]))
    assert file_type == "pdf"


def test_docx_is_one_page():
    file_type, pages = load_pages("notes.docx", make_docx(["First paragraph.", "Second paragraph."]))
    assert file_type == "docx"
    assert len(pages) == 1 and pages[0].page_number == 1
    assert "Second paragraph." in pages[0].text


def test_txt_utf8_with_bom():
    _, pages = load_pages("a.txt", "\ufeffCafé menu".encode("utf-8"))
    assert pages == [Page(text="Café menu", page_number=1)]


def test_txt_windows_1252_falls_back_without_crashing():
    _, pages = load_pages("a.txt", "Café – menu".encode("cp1252"))
    assert "Caf" in pages[0].text and "menu" in pages[0].text


@pytest.mark.parametrize("filename", ["data.csv", "notes", "image.png"])
def test_unsupported_types_are_rejected(filename):
    with pytest.raises(DocumentLoadError, match="Unsupported file type"):
        load_pages(filename, b"hello")


def test_empty_file_is_rejected():
    with pytest.raises(DocumentLoadError, match="empty"):
        load_pages("a.txt", b"")


def test_too_large_file_is_rejected():
    with pytest.raises(DocumentLoadError, match="20 MB"):
        load_pages("a.txt", b"x" * (MAX_FILE_BYTES + 1))


def test_pdf_without_text_is_rejected():
    with pytest.raises(DocumentLoadError, match="No readable text found"):
        load_pages("scan.pdf", make_pdf(["", ""]))


def test_corrupt_pdf_is_rejected():
    with pytest.raises(DocumentLoadError, match="Could not read"):
        load_pages("broken.pdf", b"%PDF-1.4 not really a pdf")


def test_corrupt_docx_is_rejected():
    with pytest.raises(DocumentLoadError, match="Could not read"):
        load_pages("broken.docx", b"not a zip file")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loaders.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion'`

- [ ] **Step 4: Write `backend/app/ingestion/loaders.py`**

```python
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import docx2txt
from pypdf import PdfReader

MAX_FILE_BYTES = 20 * 1024 * 1024
SUPPORTED_TYPES = ("pdf", "txt", "docx")


class DocumentLoadError(ValueError):
    """Raised with a message that can be shown to the user as-is."""


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int  # 1-based


def detect_file_type(filename: str) -> str:
    file_type = PurePath(filename or "").suffix.lower().lstrip(".")
    if file_type not in SUPPORTED_TYPES:
        raise DocumentLoadError("Unsupported file type. Upload a PDF, TXT or DOCX file.")
    return file_type


def load_pages(filename: str, content: bytes) -> tuple[str, list[Page]]:
    file_type = detect_file_type(filename)
    if not content:
        raise DocumentLoadError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentLoadError("The file is larger than 20 MB.")

    if file_type == "pdf":
        pages = _load_pdf(content)
    elif file_type == "docx":
        pages = [Page(text=_load_docx(content), page_number=1)]
    else:
        pages = [Page(text=_decode_text(content), page_number=1)]

    pages = [page for page in pages if page.text.strip()]
    if not pages:
        raise DocumentLoadError("No readable text found — scanned PDFs aren't supported.")
    return file_type, pages


def _load_pdf(content: bytes) -> list[Page]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise DocumentLoadError("Password-protected PDFs aren't supported.")
        return [Page(text=page.extract_text() or "", page_number=i + 1) for i, page in enumerate(reader.pages)]
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError("Could not read this PDF file.") from exc


def _load_docx(content: bytes) -> str:
    try:
        return docx2txt.process(BytesIO(content)) or ""
    except Exception as exc:
        raise DocumentLoadError("Could not read this DOCX file.") from exc


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows-1252 is the usual non-UTF-8 encoding for text files saved on Windows.
        return content.decode("cp1252", errors="replace")
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_loaders.py -v`
Expected: PASS (all 13)

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion backend/tests/files.py backend/tests/test_loaders.py
git commit -m "feat: load text from PDF, TXT and DOCX uploads with validation"
```

---

### Task 4: Vector store wrapper and ingestion pipeline

**Files:**
- Create: `backend/app/rag/vector_store.py`, `backend/app/ingestion/pipeline.py`, `backend/tests/fakes.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `load_pages`, `Page`, `DocumentLoadError` (Task 3); `get_embeddings`, `EMBEDDING_DIMENSIONS` (Task 1); `get_chunks_collection` (Task 2); `StoredDocument` (Task 2).
- Produces:
  - `app.rag.vector_store`: `VECTOR_INDEX_NAME = "vector_index"`, `VECTOR_INDEX_DEFINITION: dict`, `TOP_K = 4`; class `ChunkStore` with sync methods `add_chunks(texts: list[str], metadatas: list[dict]) -> None`, `delete_document(document_id: str) -> int`, `search(query: str, k: int = TOP_K) -> list[tuple[langchain_core.documents.Document, float]]`; `get_chunk_store() -> ChunkStore` (cached); `ensure_vector_index(collection) -> None`.
  - `app.ingestion.pipeline`: `CHUNK_SIZE = 1000`, `CHUNK_OVERLAP = 150`; `Chunk(text: str, page: int, chunk_index: int)`; `split_pages(pages: list[Page]) -> list[Chunk]`; `IngestionError(Exception)`; `async ingest_document(filename: str, content: bytes, store) -> StoredDocument` (raises `DocumentLoadError` or `IngestionError`). Chunk metadata keys: `document_id` (str), `filename`, `page`, `chunk_index`.
  - `tests.fakes`: `FakeChunkStore(hits=None, fail_on_add=False, fail_on_delete=False)` with attributes `added: list[tuple[str, dict]]`, `deleted: list[str]`; `hit(text, filename="guide.pdf", page=1, score=0.9)`; `fake_llm(answer: str)`; `FailingChatModel`.

- [ ] **Step 1: Write `backend/tests/fakes.py`**

```python
from langchain_core.documents import Document
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeChunkStore:
    """In-memory stand-in for app.rag.vector_store.ChunkStore."""

    def __init__(self, hits=None, fail_on_add=False, fail_on_delete=False):
        self.hits = hits or []
        self.fail_on_add = fail_on_add
        self.fail_on_delete = fail_on_delete
        self.added: list[tuple[str, dict]] = []
        self.deleted: list[str] = []
        self.queries: list[str] = []

    def add_chunks(self, texts, metadatas):
        if self.fail_on_add:
            raise RuntimeError("vector store unavailable")
        self.added.extend(zip(texts, metadatas))

    def delete_document(self, document_id):
        if self.fail_on_delete:
            raise RuntimeError("vector store unavailable")
        self.deleted.append(document_id)
        return 1

    def search(self, query, k=4):
        self.queries.append(query)
        return self.hits[:k]


def hit(text, filename="guide.pdf", page=1, score=0.9):
    metadata = {"filename": filename, "page": page, "document_id": "doc1", "chunk_index": 0}
    return Document(page_content=text, metadata=metadata), score


def fake_llm(answer: str) -> GenericFakeChatModel:
    """Chat model that streams `answer` word by word (no usage metadata)."""
    return GenericFakeChatModel(messages=iter([AIMessage(content=answer)]))


class FailingChatModel(GenericFakeChatModel):
    """Chat model whose every call raises, to exercise error paths."""

    def _generate(self, *args, **kwargs):
        raise RuntimeError("groq unavailable")

    def _stream(self, *args, **kwargs):
        raise RuntimeError("groq unavailable")
```

- [ ] **Step 2: Write the failing tests `backend/tests/test_pipeline.py`**

```python
import pytest

from app.ingestion.loaders import DocumentLoadError, Page
from app.ingestion.pipeline import CHUNK_SIZE, IngestionError, ingest_document, split_pages
from app.models import StoredDocument
from tests.fakes import FakeChunkStore
from tests.files import make_pdf


def test_split_pages_numbers_chunks_across_pages():
    long_text = ("Refunds are processed within ten days. " * 60).strip()  # > CHUNK_SIZE
    chunks = split_pages([Page(text=long_text, page_number=1), Page(text="Short page.", page_number=2)])
    assert len(chunks) >= 3
    assert all(len(c.text) <= CHUNK_SIZE for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].page == 2 and chunks[-1].text == "Short page."


async def test_ingest_stores_record_and_chunks(mongo):
    store = FakeChunkStore()
    doc = await ingest_document("guide.pdf", make_pdf(["Refund policy text", "Shipping policy text"]), store)

    saved = await StoredDocument.get(doc.id)
    assert saved.filename == "guide.pdf"
    assert saved.file_type == "pdf"
    assert saved.page_count == 2
    assert saved.chunk_count == len(store.added) == 2
    text, metadata = store.added[1]
    assert "Shipping" in text
    assert metadata == {"document_id": str(doc.id), "filename": "guide.pdf", "page": 2, "chunk_index": 1}


async def test_ingest_rolls_back_when_vector_store_fails(mongo):
    store = FakeChunkStore(fail_on_add=True)
    with pytest.raises(IngestionError, match="Could not process the document."):
        await ingest_document("guide.pdf", make_pdf(["Some text"]), store)
    assert await StoredDocument.count() == 0
    assert len(store.deleted) == 1  # partial chunks cleaned up


async def test_ingest_rejects_invalid_file_before_touching_db(mongo):
    store = FakeChunkStore()
    with pytest.raises(DocumentLoadError):
        await ingest_document("data.csv", b"a,b", store)
    assert await StoredDocument.count() == 0
    assert store.added == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ingestion.pipeline'`

- [ ] **Step 4: Write `backend/app/rag/vector_store.py`**

```python
from functools import lru_cache

from langchain_core.documents import Document
from langchain_mongodb import MongoDBAtlasVectorSearch
from pymongo.collection import Collection
from pymongo.operations import SearchIndexModel

from app.core.database import get_chunks_collection
from app.rag.embeddings import EMBEDDING_DIMENSIONS, get_embeddings

VECTOR_INDEX_NAME = "vector_index"
VECTOR_INDEX_DEFINITION = {
    "fields": [
        {"type": "vector", "path": "embedding", "numDimensions": EMBEDDING_DIMENSIONS, "similarity": "cosine"}
    ]
}
TOP_K = 4
# numCandidates = k * oversampling_factor = 100
OVERSAMPLING_FACTOR = 25


class ChunkStore:
    """The only code that reads or writes the `chunks` collection. All methods are sync."""

    def __init__(self, vector_store: MongoDBAtlasVectorSearch):
        self._vector_store = vector_store

    def add_chunks(self, texts: list[str], metadatas: list[dict]) -> None:
        self._vector_store.add_texts(texts, metadatas=metadatas)

    def delete_document(self, document_id: str) -> int:
        return self._vector_store.collection.delete_many({"document_id": document_id}).deleted_count

    def search(self, query: str, k: int = TOP_K) -> list[tuple[Document, float]]:
        return self._vector_store.similarity_search_with_score(
            query, k=k, oversampling_factor=OVERSAMPLING_FACTOR
        )


@lru_cache
def get_chunk_store() -> ChunkStore:
    vector_store = MongoDBAtlasVectorSearch(
        collection=get_chunks_collection(),
        embedding=get_embeddings(),
        index_name=VECTOR_INDEX_NAME,
        text_key="text",
        embedding_key="embedding",
        relevance_score_fn="cosine",
    )
    return ChunkStore(vector_store)


def ensure_vector_index(collection: Collection) -> None:
    """Create the Atlas vector index if it doesn't exist (search indexes need the collection to exist)."""
    database = collection.database
    if collection.name not in database.list_collection_names():
        database.create_collection(collection.name)
    if any(index["name"] == VECTOR_INDEX_NAME for index in collection.list_search_indexes()):
        return
    collection.create_search_index(
        SearchIndexModel(definition=VECTOR_INDEX_DEFINITION, name=VECTOR_INDEX_NAME, type="vectorSearch")
    )
```

- [ ] **Step 5: Write `backend/app/ingestion/pipeline.py`**

```python
import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from starlette.concurrency import run_in_threadpool

from app.ingestion.loaders import Page, load_pages
from app.models import StoredDocument

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


class IngestionError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int
    chunk_index: int


def split_pages(pages: list[Page]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for piece in _splitter.split_text(page.text):
            chunks.append(Chunk(text=piece, page=page.page_number, chunk_index=len(chunks)))
    return chunks


async def ingest_document(filename: str, content: bytes, store) -> StoredDocument:
    """Validate, split, embed and store a document. All-or-nothing: on failure nothing is left behind."""
    file_type, pages = load_pages(filename, content)
    chunks = split_pages(pages)

    document = StoredDocument(
        filename=filename,
        file_type=file_type,
        size_bytes=len(content),
        page_count=max(page.page_number for page in pages),
        chunk_count=len(chunks),
    )
    await document.insert()
    document_id = str(document.id)

    try:
        # Embedding is CPU-bound and the vector store client is sync: keep both off the event loop.
        await run_in_threadpool(
            store.add_chunks,
            [chunk.text for chunk in chunks],
            [
                {"document_id": document_id, "filename": filename, "page": chunk.page, "chunk_index": chunk.chunk_index}
                for chunk in chunks
            ],
        )
    except Exception as exc:
        logger.exception("Storing chunks failed for %s", filename)
        try:
            await run_in_threadpool(store.delete_document, document_id)
        except Exception:
            logger.exception("Cleanup of partial chunks failed for document %s", document_id)
        await document.delete()
        raise IngestionError("Could not process the document.") from exc

    return document
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -v`
Expected: `test_split_pages_numbers_chunks_across_pages` PASS; the three `mongo` tests PASS (SKIPPED without Atlas).

- [ ] **Step 7: Commit**

```bash
git add backend/app/rag/vector_store.py backend/app/ingestion/pipeline.py backend/tests/fakes.py backend/tests/test_pipeline.py
git commit -m "feat: add Atlas chunk store and all-or-nothing ingestion pipeline"
```

---

### Task 5: Upload and documents API, app lifespan

**Files:**
- Create: `backend/app/api/__init__.py` (empty), `backend/app/api/deps.py`, `backend/app/api/serializers.py`, `backend/app/api/upload.py`, `backend/app/api/documents.py`, `backend/tests/test_documents_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `ingest_document`, `IngestionError` (Task 4); `DocumentLoadError` (Task 3); `get_chunk_store`, `ensure_vector_index`, `VECTOR_INDEX_NAME`, `VECTOR_INDEX_DEFINITION` (Task 4); `init_db`, `close_db`, `get_chunks_collection` (Task 2).
- Produces: `app.api.deps.get_store()` and `app.api.deps.get_llm()` (FastAPI dependencies; tests override them via `app.dependency_overrides`); `app.api.serializers.serialize_document(doc) -> dict` (keys `id, filename, file_type, size_bytes, page_count, chunk_count, uploaded_at`); routes `POST /api/upload`, `GET /api/documents`, `DELETE /api/documents/{document_id}`.

- [ ] **Step 1: Write the failing tests `backend/tests/test_documents_api.py`**

```python
from app.api.deps import get_store
from app.main import app
from app.models import StoredDocument
from tests.fakes import FakeChunkStore
from tests.files import make_pdf


def use_store(store):
    app.dependency_overrides[get_store] = lambda: store
    return store


async def test_upload_pdf_returns_201_and_lists_document(client):
    store = use_store(FakeChunkStore())
    response = await client.post(
        "/api/upload", files={"file": ("guide.pdf", make_pdf(["Refunds take ten days"]), "application/pdf")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "guide.pdf" and body["file_type"] == "pdf"
    assert body["page_count"] == 1 and body["chunk_count"] == 1
    assert len(store.added) == 1

    listed = (await client.get("/api/documents")).json()
    assert [d["id"] for d in listed] == [body["id"]]


async def test_upload_unsupported_type_returns_400(client):
    use_store(FakeChunkStore())
    response = await client.post("/api/upload", files={"file": ("data.csv", b"a,b", "text/csv")})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


async def test_upload_store_failure_returns_500_and_saves_nothing(client):
    use_store(FakeChunkStore(fail_on_add=True))
    response = await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"] == "Could not process the document."
    assert await StoredDocument.count() == 0


async def test_delete_removes_chunks_and_record(client):
    store = use_store(FakeChunkStore())
    doc_id = (await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})).json()["id"]

    response = await client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 204
    assert store.deleted == [doc_id]
    assert await StoredDocument.count() == 0


async def test_delete_keeps_record_when_chunk_delete_fails(client):
    use_store(FakeChunkStore())
    doc_id = (await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})).json()["id"]

    use_store(FakeChunkStore(fail_on_delete=True))
    response = await client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 500
    assert await StoredDocument.count() == 1  # user can retry the delete


async def test_delete_unknown_document_returns_404(client):
    use_store(FakeChunkStore())
    response = await client.delete("/api/documents/650000000000000000000000")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_documents_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'` (collection error).

- [ ] **Step 3: Write `backend/app/api/deps.py`**

```python
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

from app.core.config import settings
from app.rag.vector_store import ChunkStore, get_chunk_store


def get_store() -> ChunkStore:
    return get_chunk_store()


def get_llm() -> BaseChatModel:
    return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)
```

- [ ] **Step 4: Write `backend/app/api/serializers.py`**

```python
from app.models import Conversation, Message, StoredDocument


def serialize_document(doc: StoredDocument) -> dict:
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "sources": [source.model_dump() for source in message.sources],
        "metrics": message.metrics.model_dump() if message.metrics else None,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
    }


def serialize_conversation(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "updated_at": conversation.updated_at.isoformat(),
    }
```

- [ ] **Step 5: Write `backend/app/api/upload.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.api.deps import get_store
from app.ingestion.loaders import DocumentLoadError
from app.ingestion.pipeline import IngestionError, ingest_document

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", status_code=201)
async def upload(file: UploadFile, store=Depends(get_store)):
    content = await file.read()
    try:
        document = await ingest_document(file.filename or "", content, store)
    except DocumentLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IngestionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "id": str(document.id),
        "filename": document.filename,
        "file_type": document.file_type,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
    }
```

- [ ] **Step 6: Write `backend/app/api/documents.py`**

```python
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_store
from app.api.serializers import serialize_document
from app.models import StoredDocument

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
async def list_documents():
    documents = await StoredDocument.find_all().sort(-StoredDocument.uploaded_at).to_list()
    return [serialize_document(doc) for doc in documents]


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: PydanticObjectId, store=Depends(get_store)):
    document = await StoredDocument.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        await run_in_threadpool(store.delete_document, str(document_id))
    except Exception as exc:
        # Keep the record so the delete can be retried; never leave orphaned chunks without a record.
        logger.exception("Deleting chunks failed for document %s", document_id)
        raise HTTPException(status_code=500, detail="Could not delete the document. Please try again.") from exc
    await document.delete()
    return Response(status_code=204)
```

- [ ] **Step 7: Replace `backend/app/main.py`**

```python
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.documents import router as documents_router
from app.api.upload import router as upload_router
from app.core.config import settings
from app.core.database import close_db, get_chunks_collection, init_db
from app.rag.vector_store import VECTOR_INDEX_DEFINITION, VECTOR_INDEX_NAME, ensure_vector_index

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        await run_in_threadpool(ensure_vector_index, get_chunks_collection())
    except Exception:
        logger.warning(
            "Could not create the Atlas vector index automatically. Create a Vector Search index named %r "
            "on the 'chunks' collection in the Atlas UI with this definition: %s",
            VECTOR_INDEX_NAME,
            json.dumps(VECTOR_INDEX_DEFINITION),
            exc_info=True,
        )
    yield
    await close_db()


app = FastAPI(title="RAG Data Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(upload_router)
app.include_router(documents_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

(`ASGITransport` does not run the lifespan, so tests initialise Beanie through the `mongo` fixture.)

- [ ] **Step 8: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all PASS (DB tests SKIPPED without Atlas).

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/test_documents_api.py
git commit -m "feat: add upload and documents endpoints with vector index setup on startup"
```

---

### Task 6: LangGraph retrieve → generate with streamed events

**Files:**
- Create: `backend/app/rag/prompts.py`, `backend/app/rag/graph.py`, `backend/tests/test_graph.py`

**Interfaces:**
- Consumes: `ChunkStore`-like `store.search(query, k)` and `TOP_K` (Task 4); fakes (Task 4).
- Produces:
  - `app.rag.prompts`: `RAG_SYSTEM_PROMPT: str`, `NOT_FOUND_ANSWER = "I couldn't find that in your documents."`, `NO_DOCUMENTS_ANSWER = "Upload a document first, then ask me about it."`, `HISTORY_LIMIT = 6`.
  - `app.rag.graph`: `build_sources(hits) -> list[dict]` (`{filename, page, snippet}`), `is_not_found(answer: str) -> bool`, `build_graph(store, llm)`, `async stream_answer(question: str, history: list[tuple[str, str]], *, store, llm, model_name: str) -> AsyncIterator[dict]` yielding, in order: `{"type": "meta", "sources": [...]}`, zero or more `{"type": "token", "text": str}`, then `{"type": "done", "answer": str, "sources": [...], "metrics": {model, ttft_ms, total_ms, output_tokens, tokens_per_sec, chunks_retrieved}}`. Exceptions propagate to the caller. `history` items are `("human" | "ai", content)`.

- [ ] **Step 1: Write the failing tests `backend/tests/test_graph.py`**

```python
import pytest

from app.rag.graph import build_sources, is_not_found, stream_answer
from app.rag.prompts import NOT_FOUND_ANSWER
from tests.fakes import FailingChatModel, FakeChunkStore, fake_llm, hit


async def collect(**kwargs):
    return [event async for event in stream_answer(model_name="test-model", **kwargs)]


def test_build_sources_dedupes_by_file_and_page_and_truncates_snippets():
    hits = [hit("A" * 500, "a.pdf", 1), hit("other chunk", "a.pdf", 1), hit("B", "b.pdf", 2)]
    sources = build_sources(hits)
    assert sources == [
        {"filename": "a.pdf", "page": 1, "snippet": "A" * 200},
        {"filename": "b.pdf", "page": 2, "snippet": "B"},
    ]


@pytest.mark.parametrize(
    "answer",
    ["I couldn't find that in your documents.", "I couldn’t find that in your documents", "  i couldn't find that in your documents.  "],
)
def test_is_not_found_tolerates_apostrophes_case_and_period(answer):
    assert is_not_found(answer)


def test_is_not_found_false_for_real_answers():
    assert not is_not_found("Refunds take ten days [guide.pdf p.1].")


async def test_stream_emits_meta_tokens_done_in_order():
    store = FakeChunkStore(hits=[hit("Refunds take ten days.", "guide.pdf", 1)])
    events = await collect(
        question="How long do refunds take?", history=[], store=store, llm=fake_llm("Ten days [guide.pdf p.1].")
    )

    assert events[0] == {"type": "meta", "sources": [{"filename": "guide.pdf", "page": 1, "snippet": "Refunds take ten days."}]}
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Ten days [guide.pdf p.1]."
    done = events[-1]
    assert done["type"] == "done"
    assert done["answer"] == "Ten days [guide.pdf p.1]."
    assert done["sources"] == events[0]["sources"]
    metrics = done["metrics"]
    assert metrics["model"] == "test-model"
    assert metrics["chunks_retrieved"] == 1
    assert metrics["output_tokens"] == 4  # whitespace estimate: no usage metadata from the fake model
    assert metrics["ttft_ms"] >= 0 and metrics["total_ms"] >= metrics["ttft_ms"]
    assert metrics["tokens_per_sec"] > 0
    assert store.queries == ["How long do refunds take?"]


async def test_not_found_answer_clears_sources():
    store = FakeChunkStore(hits=[hit("Unrelated text")])
    events = await collect(question="Who won the 1998 World Cup?", history=[], store=store, llm=fake_llm(NOT_FOUND_ANSWER))
    assert events[-1]["answer"] == NOT_FOUND_ANSWER
    assert events[-1]["sources"] == []


async def test_no_hits_still_answers():
    events = await collect(question="Anything?", history=[], store=FakeChunkStore(hits=[]), llm=fake_llm(NOT_FOUND_ANSWER))
    assert events[0] == {"type": "meta", "sources": []}
    assert events[-1]["type"] == "done"


async def test_llm_failure_propagates_after_meta():
    store = FakeChunkStore(hits=[hit("text")])
    stream = stream_answer("Q?", [], store=store, llm=FailingChatModel(messages=iter([])), model_name="m")
    first = await anext(stream)
    assert first["type"] == "meta"
    with pytest.raises(RuntimeError, match="groq unavailable"):
        async for _ in stream:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.rag.graph'`

- [ ] **Step 3: Write `backend/app/rag/prompts.py`**

```python
NOT_FOUND_ANSWER = "I couldn't find that in your documents."
NO_DOCUMENTS_ANSWER = "Upload a document first, then ask me about it."
HISTORY_LIMIT = 6

RAG_SYSTEM_PROMPT = f"""You are a helpful assistant that answers questions about the user's uploaded documents.

Rules:
- Answer ONLY using the numbered context excerpts provided with the question.
- Cite the excerpts you used inline as [filename p.N], using the filename and page shown on each excerpt.
- If the excerpts do not contain the answer, reply with exactly: {NOT_FOUND_ANSWER}
- Be concise. Use Markdown (lists, bold, tables) when it makes the answer clearer.
- Earlier conversation turns are only for understanding follow-up questions; facts must come from the excerpts."""
```

- [ ] **Step 4: Write `backend/app/rag/graph.py`**

```python
import time
from collections.abc import AsyncIterator
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from starlette.concurrency import run_in_threadpool

from app.rag.prompts import HISTORY_LIMIT, NOT_FOUND_ANSWER, RAG_SYSTEM_PROMPT
from app.rag.vector_store import TOP_K

SNIPPET_CHARS = 200

Hit = tuple[Document, float]


class RagState(TypedDict, total=False):
    question: str
    history: list[tuple[str, str]]
    hits: list[Hit]
    answer: AIMessage


def build_sources(hits: list[Hit]) -> list[dict]:
    sources, seen = [], set()
    for doc, _score in hits:
        key = (doc.metadata["filename"], doc.metadata["page"])
        if key in seen:
            continue
        seen.add(key)
        snippet = " ".join(doc.page_content.split())[:SNIPPET_CHARS]
        sources.append({"filename": key[0], "page": key[1], "snippet": snippet})
    return sources


def _normalize(text: str) -> str:
    return text.strip().replace("\u2019", "'").rstrip(".").lower()


def is_not_found(answer: str) -> bool:
    return _normalize(answer) == _normalize(NOT_FOUND_ANSWER)


def _format_context(hits: list[Hit]) -> str:
    if not hits:
        return "(no excerpts found)"
    return "\n\n".join(
        f"[{i}] ({doc.metadata['filename']} p.{doc.metadata['page']})\n{doc.page_content}"
        for i, (doc, _score) in enumerate(hits, start=1)
    )


def build_graph(store, llm: BaseChatModel):
    async def retrieve(state: RagState) -> dict:
        hits = await run_in_threadpool(store.search, state["question"], TOP_K)
        return {"hits": hits}

    async def generate(state: RagState) -> dict:
        messages = [
            ("system", RAG_SYSTEM_PROMPT),
            *state["history"][-HISTORY_LIMIT:],
            ("human", f"Context excerpts:\n{_format_context(state['hits'])}\n\nQuestion: {state['question']}"),
        ]
        return {"answer": await llm.ainvoke(messages)}

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def stream_answer(
    question: str, history: list[tuple[str, str]], *, store, llm: BaseChatModel, model_name: str
) -> AsyncIterator[dict]:
    started = time.perf_counter()
    first_token_at: float | None = None
    sources: list[dict] = []
    chunks_retrieved = 0
    parts: list[str] = []
    final: AIMessage | None = None

    graph = build_graph(store, llm)
    async for mode, payload in graph.astream(
        {"question": question, "history": history}, stream_mode=["updates", "messages"]
    ):
        if mode == "updates":
            if "retrieve" in payload:
                hits = payload["retrieve"]["hits"]
                chunks_retrieved = len(hits)
                sources = build_sources(hits)
                yield {"type": "meta", "sources": sources}
            elif "generate" in payload:
                final = payload["generate"]["answer"]
        else:
            chunk, metadata = payload
            text = chunk.content if isinstance(chunk.content, str) else ""
            if metadata.get("langgraph_node") == "generate" and text:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                parts.append(text)
                yield {"type": "token", "text": text}

    finished = time.perf_counter()
    answer = "".join(parts) or (final.content if final is not None else "")
    if is_not_found(answer):
        sources = []

    usage = (final.usage_metadata if final is not None else None) or {}
    output_tokens = usage.get("output_tokens") or len(answer.split())
    generation_seconds = max(finished - (first_token_at or started), 1e-3)
    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "metrics": {
            "model": model_name,
            "ttft_ms": int(((first_token_at or finished) - started) * 1000),
            "total_ms": int((finished - started) * 1000),
            "output_tokens": output_tokens,
            "tokens_per_sec": round(output_tokens / generation_seconds, 1),
            "chunks_retrieved": chunks_retrieved,
        },
    }
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_graph.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/prompts.py backend/app/rag/graph.py backend/tests/test_graph.py
git commit -m "feat: add LangGraph retrieve-generate pipeline with streamed events and metrics"
```

---

### Task 7: Streaming query endpoint and conversations API

**Files:**
- Create: `backend/app/api/sse.py`, `backend/app/api/query.py`, `backend/app/api/conversations.py`, `backend/tests/test_sse.py`, `backend/tests/test_query_api.py`, `backend/tests/test_conversations_api.py`
- Modify: `backend/app/main.py` (include routers)

**Interfaces:**
- Consumes: `stream_answer`, `NO_DOCUMENTS_ANSWER`, `HISTORY_LIMIT` (Task 6); `get_store`, `get_llm`, `serialize_message`, `serialize_conversation` (Task 5); models (Task 2).
- Produces: `app.api.sse.format_sse(event: str, data: dict) -> str`; `POST /api/query` streaming `meta {conversation_id, sources}` → `token {text}`* → `done {message_id, metrics, sources}` or `error {message, conversation_id}`; `GET /api/conversations`, `GET /api/conversations/{id}` → `{id, title, updated_at, messages: [serialize_message...]}`, `DELETE /api/conversations/{id}`. Test helper `parse_sse(text) -> list[tuple[str, dict]]` lives in `tests/test_query_api.py`.

- [ ] **Step 1: Write the failing SSE test `backend/tests/test_sse.py`**

```python
from app.api.sse import format_sse


def test_format_sse_writes_event_and_json_data():
    assert format_sse("token", {"text": "Hi \"there\"\nnext"}) == 'event: token\ndata: {"text": "Hi \\"there\\"\\nnext"}\n\n'
```

- [ ] **Step 2: Write the failing query tests `backend/tests/test_query_api.py`**

```python
import json

from app.api.deps import get_llm, get_store
from app.main import app
from app.models import Conversation, Message, StoredDocument
from app.rag.prompts import NO_DOCUMENTS_ANSWER
from tests.fakes import FailingChatModel, FakeChunkStore, fake_llm, hit


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def add_document():
    await StoredDocument(filename="guide.pdf", file_type="pdf", size_bytes=1, page_count=1, chunk_count=1).insert()


def override(store, llm):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: llm


async def test_query_streams_answer_and_persists_conversation(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("Refunds take ten days.")]), fake_llm("Ten days [guide.pdf p.1]."))

    response = await client.post("/api/query", json={"question": "How long do refunds take?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done" and set(names[1:-1]) == {"token"}
    conversation_id = events[0][1]["conversation_id"]
    assert "".join(data["text"] for name, data in events if name == "token") == "Ten days [guide.pdf p.1]."

    conversation = await Conversation.get(conversation_id)
    assert conversation.title == "How long do refunds take?"
    messages = await Message.find(Message.conversation_id == conversation.id).sort(+Message.created_at).to_list()
    assert [(m.role, m.content) for m in messages] == [
        ("user", "How long do refunds take?"),
        ("assistant", "Ten days [guide.pdf p.1]."),
    ]
    assert messages[1].sources[0].filename == "guide.pdf"
    assert messages[1].metrics.chunks_retrieved == 1
    assert events[-1][1]["message_id"] == str(messages[1].id)


async def test_follow_up_reuses_conversation_and_sends_history(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("x")]), fake_llm("First answer."))
    first = parse_sse((await client.post("/api/query", json={"question": "First?"})).text)
    conversation_id = first[0][1]["conversation_id"]

    llm = fake_llm("Second answer.")
    override(FakeChunkStore(hits=[hit("x")]), llm)
    second = parse_sse((await client.post("/api/query", json={"question": "Second?", "conversation_id": conversation_id})).text)
    assert second[0][1]["conversation_id"] == conversation_id
    assert await Message.find(Message.conversation_id == first[0][1]["conversation_id"]).count() == 4


async def test_no_documents_short_circuits_without_llm(client):
    override(FakeChunkStore(), FailingChatModel(messages=iter([])))
    events = parse_sse((await client.post("/api/query", json={"question": "Hello?"})).text)
    assert [name for name, _ in events] == ["meta", "token", "done"]
    assert events[1][1]["text"] == NO_DOCUMENTS_ANSWER
    assert events[2][1]["metrics"] is None


async def test_llm_failure_emits_error_and_saves_error_message(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("x")]), FailingChatModel(messages=iter([])))
    events = parse_sse((await client.post("/api/query", json={"question": "Q?"})).text)
    name, data = events[-1]
    assert name == "error"
    assert data["message"] == "Sorry, something went wrong while answering."
    assistant = await Message.find_one(Message.role == "assistant")
    assert assistant.status == "error"
    assert data["conversation_id"] == str(assistant.conversation_id)


async def test_unknown_conversation_returns_404(client):
    override(FakeChunkStore(), fake_llm("x"))
    response = await client.post("/api/query", json={"question": "Q?", "conversation_id": "650000000000000000000000"})
    assert response.status_code == 404


async def test_blank_or_too_long_question_returns_422(client):
    override(FakeChunkStore(), fake_llm("x"))
    assert (await client.post("/api/query", json={"question": "   "})).status_code == 422
    assert (await client.post("/api/query", json={"question": "x" * 2001})).status_code == 422
```

- [ ] **Step 3: Write the failing conversations tests `backend/tests/test_conversations_api.py`**

```python
from app.models import Conversation, Message


async def make_conversation(title):
    conversation = Conversation(title=title)
    await conversation.insert()
    await Message(conversation_id=conversation.id, role="user", content=title).insert()
    await Message(conversation_id=conversation.id, role="assistant", content="answer").insert()
    return conversation


async def test_list_conversations_newest_first(client):
    older = await make_conversation("older")
    newer = await make_conversation("newer")
    body = (await client.get("/api/conversations")).json()
    assert [c["id"] for c in body] == [str(newer.id), str(older.id)]
    assert body[0]["title"] == "newer"


async def test_get_conversation_returns_messages_in_order(client):
    conversation = await make_conversation("hello")
    body = (await client.get(f"/api/conversations/{conversation.id}")).json()
    assert body["title"] == "hello"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]


async def test_delete_conversation_removes_messages(client):
    conversation = await make_conversation("bye")
    assert (await client.delete(f"/api/conversations/{conversation.id}")).status_code == 204
    assert await Conversation.count() == 0
    assert await Message.count() == 0


async def test_unknown_conversation_404(client):
    assert (await client.get("/api/conversations/650000000000000000000000")).status_code == 404
    assert (await client.delete("/api/conversations/650000000000000000000000")).status_code == 404
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_sse.py tests/test_query_api.py tests/test_conversations_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api.sse'`

- [ ] **Step 5: Write `backend/app/api/sse.py`**

```python
import json


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
```

- [ ] **Step 6: Write `backend/app/api/query.py`**

```python
import logging

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_llm, get_store
from app.api.sse import format_sse
from app.core.config import settings
from app.core.database import utcnow
from app.models import Conversation, Message, Metrics, Source, StoredDocument
from app.rag.graph import stream_answer
from app.rag.prompts import HISTORY_LIMIT, NO_DOCUMENTS_ANSWER

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["query"])

ERROR_MESSAGE = "Sorry, something went wrong while answering."
TITLE_CHARS = 60


class QueryRequest(BaseModel):
    question: str = Field(max_length=2000)
    conversation_id: PydanticObjectId | None = None

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be empty")
        return value


async def _load_history(conversation_id: PydanticObjectId) -> list[tuple[str, str]]:
    recent = (
        await Message.find(Message.conversation_id == conversation_id, Message.status == "complete")
        .sort(-Message.created_at)
        .limit(HISTORY_LIMIT)
        .to_list()
    )
    return [("human" if m.role == "user" else "ai", m.content) for m in reversed(recent)]


async def _save_assistant(conversation: Conversation, content: str, sources, metrics, status: str) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        sources=[Source(**s) for s in sources],
        metrics=Metrics(**metrics) if metrics else None,
        status=status,
    )
    await message.insert()
    conversation.updated_at = utcnow()
    await conversation.save()
    return message


@router.post("/query")
async def query(request: QueryRequest, store=Depends(get_store), llm=Depends(get_llm)):
    if request.conversation_id is not None:
        conversation = await Conversation.get(request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(title=request.question[:TITLE_CHARS])
        await conversation.insert()

    history = await _load_history(conversation.id)
    await Message(conversation_id=conversation.id, role="user", content=request.question).insert()

    return StreamingResponse(
        _events(conversation, request.question, history, store, llm),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(conversation: Conversation, question: str, history, store, llm):
    conversation_id = str(conversation.id)
    partial: list[str] = []
    try:
        if await StoredDocument.count() == 0:
            yield format_sse("meta", {"conversation_id": conversation_id, "sources": []})
            yield format_sse("token", {"text": NO_DOCUMENTS_ANSWER})
            message = await _save_assistant(conversation, NO_DOCUMENTS_ANSWER, [], None, "complete")
            yield format_sse("done", {"message_id": str(message.id), "metrics": None, "sources": []})
            return

        async for event in stream_answer(question, history, store=store, llm=llm, model_name=settings.groq_model):
            if event["type"] == "meta":
                yield format_sse("meta", {"conversation_id": conversation_id, "sources": event["sources"]})
            elif event["type"] == "token":
                partial.append(event["text"])
                yield format_sse("token", {"text": event["text"]})
            else:
                message = await _save_assistant(
                    conversation, event["answer"], event["sources"], event["metrics"], "complete"
                )
                yield format_sse(
                    "done", {"message_id": str(message.id), "metrics": event["metrics"], "sources": event["sources"]}
                )
    except Exception:
        logger.exception("Answering failed for conversation %s", conversation_id)
        try:
            await _save_assistant(conversation, "".join(partial), [], None, "error")
        except Exception:
            logger.exception("Could not save the failed answer for conversation %s", conversation_id)
        yield format_sse("error", {"message": ERROR_MESSAGE, "conversation_id": conversation_id})
```

- [ ] **Step 7: Write `backend/app/api/conversations.py`**

```python
from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, Response

from app.api.serializers import serialize_conversation, serialize_message
from app.models import Conversation, Message

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


async def _get_or_404(conversation_id: PydanticObjectId) -> Conversation:
    conversation = await Conversation.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("")
async def list_conversations():
    conversations = await Conversation.find_all().sort(-Conversation.updated_at).to_list()
    return [serialize_conversation(c) for c in conversations]


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: PydanticObjectId):
    conversation = await _get_or_404(conversation_id)
    messages = await Message.find(Message.conversation_id == conversation.id).sort(+Message.created_at).to_list()
    return {**serialize_conversation(conversation), "messages": [serialize_message(m) for m in messages]}


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: PydanticObjectId):
    conversation = await _get_or_404(conversation_id)
    await Message.find(Message.conversation_id == conversation.id).delete()
    await conversation.delete()
    return Response(status_code=204)
```

- [ ] **Step 8: Register routers in `backend/app/main.py`**

Add imports next to the existing router imports:

```python
from app.api.conversations import router as conversations_router
from app.api.query import router as query_router
```

and after `app.include_router(documents_router)`:

```python
app.include_router(query_router)
app.include_router(conversations_router)
```

- [ ] **Step 9: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all PASS (DB tests SKIPPED without Atlas). `test_sse.py` passes without Atlas.

- [ ] **Step 10: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat: stream answers over SSE and persist conversations"
```

---

### Task 8: Stats endpoint for the dashboard

**Files:**
- Create: `backend/app/api/stats.py`, `backend/tests/test_stats_api.py`
- Modify: `backend/app/main.py` (include router)

**Interfaces:**
- Consumes: models (Task 2).
- Produces: `GET /api/stats` → `{totals: {documents, chunks, questions, avg_tokens_per_sec, avg_ttft_ms}, per_question: [{created_at, ttft_ms, total_ms, tokens_per_sec}], questions_per_day: [{date, count}], chunks_per_document: [{filename, chunks}]}`. Averages are `null` when there are no completed answers; `per_question` is the latest 50 completed answers with metrics, oldest first.

- [ ] **Step 1: Write the failing test `backend/tests/test_stats_api.py`**

```python
from datetime import datetime, timezone

from app.models import Conversation, Message, Metrics, StoredDocument


def metrics(ttft, tps):
    return Metrics(model="m", ttft_ms=ttft, total_ms=ttft + 500, output_tokens=100, tokens_per_sec=tps, chunks_retrieved=4)


async def test_stats_empty(client):
    body = (await client.get("/api/stats")).json()
    assert body["totals"] == {"documents": 0, "chunks": 0, "questions": 0, "avg_tokens_per_sec": None, "avg_ttft_ms": None}
    assert body["per_question"] == [] and body["questions_per_day"] == [] and body["chunks_per_document"] == []


async def test_stats_aggregates_documents_questions_and_metrics(client):
    await StoredDocument(filename="a.pdf", file_type="pdf", size_bytes=1, page_count=1, chunk_count=10).insert()
    await StoredDocument(filename="b.txt", file_type="txt", size_bytes=1, page_count=1, chunk_count=5).insert()
    conversation = Conversation(title="t")
    await conversation.insert()
    day1 = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    cid = conversation.id
    await Message(conversation_id=cid, role="user", content="q1", created_at=day1).insert()
    await Message(conversation_id=cid, role="assistant", content="a1", metrics=metrics(200, 400.0), created_at=day1).insert()
    await Message(conversation_id=cid, role="user", content="q2", created_at=day2).insert()
    await Message(conversation_id=cid, role="assistant", content="a2", metrics=metrics(400, 600.0), created_at=day2).insert()
    await Message(conversation_id=cid, role="user", content="q3", created_at=day2).insert()
    await Message(conversation_id=cid, role="assistant", content="", status="error", created_at=day2).insert()

    body = (await client.get("/api/stats")).json()
    assert body["totals"] == {"documents": 2, "chunks": 15, "questions": 3, "avg_tokens_per_sec": 500.0, "avg_ttft_ms": 300}
    assert [p["ttft_ms"] for p in body["per_question"]] == [200, 400]
    assert body["questions_per_day"] == [{"date": "2026-10-09", "count": 1}, {"date": "2026-10-10", "count": 2}]
    assert sorted(body["chunks_per_document"], key=lambda d: d["filename"]) == [
        {"filename": "a.pdf", "chunks": 10},
        {"filename": "b.txt", "chunks": 5},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_stats_api.py -v`
Expected: FAIL — `404 Not Found` from `/api/stats` (assertion error on JSON keys), or SKIPPED without Atlas.

- [ ] **Step 3: Write `backend/app/api/stats.py`**

```python
from collections import Counter

from fastapi import APIRouter

from app.models import Message, StoredDocument

router = APIRouter(prefix="/api", tags=["stats"])

PER_QUESTION_LIMIT = 50


@router.get("/stats")
async def stats():
    documents = await StoredDocument.find_all().to_list()
    questions = await Message.find(Message.role == "user").to_list()
    answered = (
        await Message.find(Message.role == "assistant", Message.status == "complete", Message.metrics != None)  # noqa: E711
        .sort(+Message.created_at)
        .to_list()
    )

    per_day = Counter(m.created_at.date().isoformat() for m in questions)
    return {
        "totals": {
            "documents": len(documents),
            "chunks": sum(d.chunk_count for d in documents),
            "questions": len(questions),
            "avg_tokens_per_sec": round(sum(m.metrics.tokens_per_sec for m in answered) / len(answered), 1)
            if answered
            else None,
            "avg_ttft_ms": round(sum(m.metrics.ttft_ms for m in answered) / len(answered)) if answered else None,
        },
        "per_question": [
            {
                "created_at": m.created_at.isoformat(),
                "ttft_ms": m.metrics.ttft_ms,
                "total_ms": m.metrics.total_ms,
                "tokens_per_sec": m.metrics.tokens_per_sec,
            }
            for m in answered[-PER_QUESTION_LIMIT:]
        ],
        "questions_per_day": [{"date": day, "count": per_day[day]} for day in sorted(per_day)],
        "chunks_per_document": [{"filename": d.filename, "chunks": d.chunk_count} for d in documents],
    }
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Add `from app.api.stats import router as stats_router` with the other router imports and `app.include_router(stats_router)` after the conversations router.

- [ ] **Step 5: Run the full backend suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all PASS (DB tests SKIPPED without Atlas).

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/tests/test_stats_api.py
git commit -m "feat: add stats endpoint for the usage and speed dashboard"
```

---

### Task 9: Frontend scaffold and API client with SSE parser

**Files:**
- Create: `frontend/package.json` (via npm), `frontend/vite.config.js`, `frontend/index.html`, `frontend/.env.example`, `frontend/src/main.jsx`, `frontend/src/index.css`, `frontend/src/App.jsx` (placeholder replaced in Task 10), `frontend/src/services/api.js`, `frontend/src/services/api.test.js`

**Interfaces:**
- Produces (`src/services/api.js`): `createSseParser(onEvent: (event: string, data: object) => void) => (text: string) => void`; `streamQuery({question, conversationId, onEvent, signal}) => Promise<void>`; `uploadDocument(file) => Promise<object>`; `listDocuments()`; `deleteDocument(id)`; `listConversations()`; `getConversation(id)`; `deleteConversation(id)`; `getStats()`. Errors are thrown as `Error` with a user-readable `message` (the backend `detail` when present).

- [ ] **Step 1: Create the package and install dependencies**

```bash
mkdir frontend && cd frontend
npm init -y
npm pkg set name=rag-assistant-frontend private=true type=module
npm pkg set scripts.dev="vite" scripts.build="vite build" scripts.preview="vite preview" scripts.test="vitest run"
npm install react react-dom recharts react-markdown
npm install -D vite @vitejs/plugin-react tailwindcss @tailwindcss/vite vitest
npm pkg delete main
```

- [ ] **Step 2: Create config and entry files**

`frontend/vite.config.js`:

```js
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173 },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>RAG Data Assistant</title>
  </head>
  <body class="bg-slate-50 text-slate-900">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

`frontend/.env.example`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

Copy it to `frontend/.env`.

`frontend/src/index.css`:

```css
@import "tailwindcss";
```

`frontend/src/main.jsx`:

```jsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.jsx` (placeholder, replaced in Task 10):

```jsx
export default function App() {
  return <p className="p-4">RAG Data Assistant</p>;
}
```

- [ ] **Step 3: Write the failing parser tests `frontend/src/services/api.test.js`**

```js
import { describe, expect, it } from "vitest";
import { createSseParser } from "./api";

function collect() {
  const events = [];
  const feed = createSseParser((event, data) => events.push([event, data]));
  return { events, feed };
}

describe("createSseParser", () => {
  it("parses complete events", () => {
    const { events, feed } = collect();
    feed('event: meta\ndata: {"sources":[]}\n\nevent: token\ndata: {"text":"Hi"}\n\n');
    expect(events).toEqual([
      ["meta", { sources: [] }],
      ["token", { text: "Hi" }],
    ]);
  });

  it("joins an event split across reads", () => {
    const { events, feed } = collect();
    feed("event: tok");
    feed('en\ndata: {"text":" wor');
    expect(events).toEqual([]);
    feed('ld"}\n\n');
    expect(events).toEqual([["token", { text: " world" }]]);
  });

  it("handles CRLF line endings", () => {
    const { events, feed } = collect();
    feed('event: done\r\ndata: {"metrics":null}\r\n\r\n');
    expect(events).toEqual([["done", { metrics: null }]]);
  });

  it("ignores a trailing incomplete event", () => {
    const { events, feed } = collect();
    feed('event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"te');
    expect(events).toEqual([["token", { text: "a" }]]);
  });
});
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd frontend && npm test`
Expected: FAIL — `Failed to resolve import "./api"`

- [ ] **Step 5: Write `frontend/src/services/api.js`**

```js
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
  } catch {
    // Non-JSON error body; fall through to the generic message.
  }
  return `Request failed (${response.status})`;
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, options);
  } catch {
    throw new Error("Could not reach the server. Is the backend running?");
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.status === 204 ? null : response.json();
}

export const listDocuments = () => request("/api/documents");
export const deleteDocument = (id) => request(`/api/documents/${id}`, { method: "DELETE" });
export const listConversations = () => request("/api/conversations");
export const getConversation = (id) => request(`/api/conversations/${id}`);
export const deleteConversation = (id) => request(`/api/conversations/${id}`, { method: "DELETE" });
export const getStats = () => request("/api/stats");

export function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/api/upload", { method: "POST", body: form });
}

export function createSseParser(onEvent) {
  let buffer = "";
  return (text) => {
    buffer += text.replace(/\r\n/g, "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const data = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) onEvent(event, JSON.parse(data.join("\n")));
    }
  };
}

export async function streamQuery({ question, conversationId, onEvent, signal }) {
  let response;
  try {
    response = await fetch(`${BASE_URL}/api/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, conversation_id: conversationId ?? null }),
      signal,
    });
  } catch {
    throw new Error("Could not reach the server. Is the backend running?");
  }
  if (!response.ok) throw new Error(await errorMessage(response));

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const feed = createSseParser(onEvent);
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    feed(value);
  }
}
```

- [ ] **Step 6: Run the tests and the build**

Run: `npm test && npm run build`
Expected: 4 tests PASS; build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/index.html frontend/.env.example frontend/src
git commit -m "feat: scaffold React frontend with API client and SSE parser"
```

---

### Task 10: App shell, sidebar, uploads, documents and conversations lists

**Files:**
- Create: `frontend/src/components/Sidebar.jsx`, `frontend/src/components/FileUpload.jsx`, `frontend/src/components/DocumentList.jsx`, `frontend/src/components/ConversationList.jsx`, `frontend/src/components/ChatView.jsx` (stub, completed in Task 11), `frontend/src/components/Dashboard.jsx` (stub, completed in Task 12)
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: `api.js` functions (Task 9).
- Produces: `App` state passed down — `ChatView` props `{conversationId: string|null, onConversationStarted(id), onAnswerFinished(), onBusyChange(bool)}`; `Dashboard` takes no props. `Sidebar` props `{documents, conversations, activeConversationId, busy, onUploaded(), onDeleteDocument(id), onSelectConversation(id), onDeleteConversation(id), onNewChat()}`.

- [ ] **Step 1: Write `frontend/src/components/FileUpload.jsx`**

```jsx
import { useState } from "react";
import { uploadDocument } from "../services/api";

export default function FileUpload({ onUploaded }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  async function handleChange(event) {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    setStatus(`Processing ${file.name}…`);
    try {
      await uploadDocument(file);
      onUploaded();
    } catch (err) {
      setError(err.message);
    } finally {
      setStatus(null);
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-3">
      <label className="block cursor-pointer text-sm font-medium text-indigo-600 hover:text-indigo-700">
        + Upload PDF, TXT or DOCX
        <input type="file" accept=".pdf,.txt,.docx" className="hidden" onChange={handleChange} disabled={!!status} />
      </label>
      <p className="mt-1 text-xs text-slate-500">Max 20 MB</p>
      {status && <p className="mt-2 text-xs text-slate-600">{status}</p>}
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/DocumentList.jsx`**

```jsx
export default function DocumentList({ documents, onDelete }) {
  if (documents.length === 0) {
    return <p className="text-xs text-slate-500">No documents yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {documents.map((doc) => (
        <li key={doc.id} className="group flex items-center justify-between rounded px-2 py-1 text-sm hover:bg-slate-100">
          <span className="truncate" title={doc.filename}>
            {doc.filename}
            <span className="ml-1 text-xs text-slate-400">{doc.chunk_count} chunks</span>
          </span>
          <button
            type="button"
            onClick={() => onDelete(doc.id)}
            className="ml-2 text-xs text-slate-400 opacity-0 hover:text-red-600 group-hover:opacity-100"
            aria-label={`Delete ${doc.filename}`}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/ConversationList.jsx`**

```jsx
export default function ConversationList({ conversations, activeId, disabled, onSelect, onDelete }) {
  if (conversations.length === 0) {
    return <p className="text-xs text-slate-500">No conversations yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {conversations.map((c) => (
        <li
          key={c.id}
          className={`group flex items-center justify-between rounded px-2 py-1 text-sm ${
            c.id === activeId ? "bg-indigo-50 text-indigo-700" : "hover:bg-slate-100"
          }`}
        >
          <button
            type="button"
            disabled={disabled}
            onClick={() => onSelect(c.id)}
            className="flex-1 truncate text-left disabled:cursor-not-allowed"
            title={c.title}
          >
            {c.title}
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onDelete(c.id)}
            className="ml-2 text-xs text-slate-400 opacity-0 hover:text-red-600 group-hover:opacity-100"
            aria-label={`Delete conversation ${c.title}`}
          >
            Delete
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/Sidebar.jsx`**

```jsx
import ConversationList from "./ConversationList";
import DocumentList from "./DocumentList";
import FileUpload from "./FileUpload";

export default function Sidebar({
  documents,
  conversations,
  activeConversationId,
  busy,
  onUploaded,
  onDeleteDocument,
  onSelectConversation,
  onDeleteConversation,
  onNewChat,
}) {
  return (
    <aside className="flex w-72 shrink-0 flex-col gap-5 overflow-y-auto border-r border-slate-200 bg-slate-50 p-4">
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Documents</h2>
        <FileUpload onUploaded={onUploaded} />
        <DocumentList documents={documents} onDelete={onDeleteDocument} />
      </section>
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Conversations</h2>
          <button
            type="button"
            onClick={onNewChat}
            disabled={busy}
            className="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            New chat
          </button>
        </div>
        <ConversationList
          conversations={conversations}
          activeId={activeConversationId}
          disabled={busy}
          onSelect={onSelectConversation}
          onDelete={onDeleteConversation}
        />
      </section>
    </aside>
  );
}
```

- [ ] **Step 5: Write stubs `frontend/src/components/ChatView.jsx` and `frontend/src/components/Dashboard.jsx`**

```jsx
// ChatView.jsx — completed in Task 11
export default function ChatView() {
  return <div className="p-6 text-slate-500">Chat coming soon.</div>;
}
```

```jsx
// Dashboard.jsx — completed in Task 12
export default function Dashboard() {
  return <div className="p-6 text-slate-500">Dashboard coming soon.</div>;
}
```

- [ ] **Step 6: Replace `frontend/src/App.jsx`**

```jsx
import { useCallback, useEffect, useState } from "react";
import ChatView from "./components/ChatView";
import Dashboard from "./components/Dashboard";
import Sidebar from "./components/Sidebar";
import { deleteConversation, deleteDocument, listConversations, listDocuments } from "./services/api";

const TABS = [
  { id: "chat", label: "Chat" },
  { id: "dashboard", label: "Dashboard" },
];

export default function App() {
  const [tab, setTab] = useState("chat");
  const [documents, setDocuments] = useState([]);
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (action) => {
    try {
      setError(null);
      await action();
    } catch (err) {
      setError(err.message);
    }
  }, []);

  const refreshDocuments = useCallback(() => run(async () => setDocuments(await listDocuments())), [run]);
  const refreshConversations = useCallback(
    () => run(async () => setConversations(await listConversations())),
    [run],
  );

  useEffect(() => {
    refreshDocuments();
    refreshConversations();
  }, [refreshDocuments, refreshConversations]);

  function handleDeleteDocument(id) {
    run(async () => {
      await deleteDocument(id);
      setDocuments(await listDocuments());
    });
  }

  function handleDeleteConversation(id) {
    run(async () => {
      await deleteConversation(id);
      if (id === activeConversationId) setActiveConversationId(null);
      setConversations(await listConversations());
    });
  }

  return (
    <div className="flex h-screen">
      <Sidebar
        documents={documents}
        conversations={conversations}
        activeConversationId={activeConversationId}
        busy={busy}
        onUploaded={refreshDocuments}
        onDeleteDocument={handleDeleteDocument}
        onSelectConversation={(id) => {
          setActiveConversationId(id);
          setTab("chat");
        }}
        onDeleteConversation={handleDeleteConversation}
        onNewChat={() => {
          setActiveConversationId(null);
          setTab("chat");
        }}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-1 border-b border-slate-200 bg-white px-4">
          <h1 className="mr-6 py-3 font-semibold">⚡ RAG Data Assistant</h1>
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`border-b-2 px-3 py-3 text-sm font-medium ${
                tab === t.id ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </header>
        {error && <p className="bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>}
        <div className="min-h-0 flex-1">
          {tab === "chat" ? (
            <ChatView
              conversationId={activeConversationId}
              onConversationStarted={setActiveConversationId}
              onAnswerFinished={refreshConversations}
              onBusyChange={setBusy}
            />
          ) : (
            <Dashboard />
          )}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 7: Verify build and manual smoke**

Run: `npm run build`
Expected: build succeeds.

Manual: with the backend running (`cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000`) and `npm run dev`, open http://localhost:5173 — upload a small TXT file; it appears under Documents with its chunk count; Delete removes it; an unsupported file (e.g. `.csv`) shows "Unsupported file type…" under the upload box. Tabs switch between the two stubs.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: add app shell with sidebar, uploads, documents and conversations"
```

---

### Task 11: Streaming chat view

**Files:**
- Modify: `frontend/src/components/ChatView.jsx`
- Create: `frontend/src/components/MessageBubble.jsx`

**Interfaces:**
- Consumes: `streamQuery`, `getConversation` (Task 9); App props (Task 10). Message shape (from server and local): `{id, role, content, sources: [{filename, page, snippet}], metrics: {ttft_ms, tokens_per_sec, ...} | null, status: "streaming" | "complete" | "error", error?: string}`.

- [ ] **Step 1: Write `frontend/src/components/MessageBubble.jsx`**

```jsx
import Markdown from "react-markdown";

function SpeedBadge({ metrics }) {
  if (!metrics) return null;
  return (
    <span
      className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700"
      title={`Time to first token · output speed (${metrics.model})`}
    >
      ⚡ {(metrics.ttft_ms / 1000).toFixed(2)}s · {Math.round(metrics.tokens_per_sec)} tok/s
    </span>
  );
}

function Sources({ sources }) {
  if (!sources?.length) return null;
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-xs font-medium text-slate-500">Sources ({sources.length})</summary>
      <ul className="mt-2 space-y-2">
        {sources.map((s) => (
          <li key={`${s.filename}-${s.page}`} className="rounded border border-slate-200 bg-slate-50 p-2">
            <p className="text-xs font-semibold text-slate-700">
              {s.filename} · p. {s.page}
            </p>
            <p className="mt-1 text-xs text-slate-600">{s.snippet}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-white">{message.content}</div>
      </div>
    );
  }

  const waiting = message.status === "streaming" && !message.content;
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-3 shadow-sm">
        {waiting ? (
          <p className="animate-pulse text-slate-400">Searching your documents…</p>
        ) : (
          <div className="prose prose-sm max-w-none [&_li]:ml-4 [&_ol]:list-decimal [&_p]:my-1 [&_ul]:list-disc">
            <Markdown>{message.content}</Markdown>
          </div>
        )}
        {message.status === "error" && (
          <p className="mt-2 text-sm text-red-600">{message.error ?? "Sorry, something went wrong while answering."}</p>
        )}
        <Sources sources={message.sources} />
        {message.metrics && (
          <div className="mt-2">
            <SpeedBadge metrics={message.metrics} />
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/components/ChatView.jsx`**

```jsx
import { useEffect, useRef, useState } from "react";
import { getConversation, streamQuery } from "../services/api";
import MessageBubble from "./MessageBubble";

const STREAMING_ID = "streaming";

export default function ChatView({ conversationId, onConversationStarted, onAnswerFinished, onBusyChange }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState(null);
  // Id of the conversation whose messages are already on screen (e.g. one we just started by streaming).
  const shownIdRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (conversationId === shownIdRef.current) return;
    shownIdRef.current = conversationId;
    setLoadError(null);
    if (conversationId === null) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    getConversation(conversationId)
      .then((conversation) => !cancelled && setMessages(conversation.messages))
      .catch((err) => !cancelled && setLoadError(err.message));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function setBusyState(value) {
    setBusy(value);
    onBusyChange(value);
  }

  function updateStreaming(patch) {
    setMessages((prev) =>
      prev.map((m) => (m.id === STREAMING_ID ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)),
    );
  }

  function adoptConversation(id) {
    if (id && id !== shownIdRef.current) {
      shownIdRef.current = id;
      onConversationStarted(id);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const question = input.trim();
    if (!question || busy) return;

    setInput("");
    setBusyState(true);
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: question },
      { id: STREAMING_ID, role: "assistant", content: "", sources: [], metrics: null, status: "streaming" },
    ]);

    try {
      await streamQuery({
        question,
        conversationId,
        onEvent: (name, data) => {
          if (name === "meta") {
            adoptConversation(data.conversation_id);
            updateStreaming({ sources: data.sources });
          } else if (name === "token") {
            updateStreaming((m) => ({ content: m.content + data.text }));
          } else if (name === "done") {
            updateStreaming({ id: data.message_id, status: "complete", metrics: data.metrics, sources: data.sources });
          } else if (name === "error") {
            adoptConversation(data.conversation_id);
            updateStreaming({ id: `error-${Date.now()}`, status: "error", error: data.message });
          }
        },
      });
      // Stream ended without done/error (connection dropped).
      updateStreaming({ id: `error-${Date.now()}`, status: "error", error: "The answer was interrupted." });
    } catch (err) {
      updateStreaming({ id: `error-${Date.now()}`, status: "error", error: err.message });
    } finally {
      setBusyState(false);
      onAnswerFinished();
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {loadError && <p className="text-sm text-red-600">{loadError}</p>}
        {messages.length === 0 && !loadError && (
          <div className="mt-20 text-center text-slate-500">
            <p className="text-lg font-medium text-slate-700">Ask anything about your documents</p>
            <p className="mt-1 text-sm">Upload a PDF, TXT or DOCX on the left, then ask a question.</p>
          </div>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-slate-200 bg-white p-4">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
          placeholder="Ask a question about your documents…"
          value={input}
          maxLength={2000}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Answering…" : "Send"}
        </button>
      </form>
    </div>
  );
}
```

Note: the "interrupted" update after `streamQuery` only affects a message still having id `"streaming"`; after `done`/`error` the id has changed, so it is a no-op.

- [ ] **Step 3: Verify build and manual streaming check**

Run: `npm run build && npm test`
Expected: build succeeds, 4 tests PASS.

Manual (backend + Atlas + Groq configured): upload a PDF, ask a question it answers — the reply appears word by word, then Sources and the ⚡ badge appear; the conversation shows in the sidebar; ask a follow-up in the same conversation; ask something unrelated — reply is "I couldn't find that in your documents." with no Sources; click another conversation and back — messages reload with badges.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components
git commit -m "feat: stream answers in the chat view with sources and speed badge"
```

---

### Task 12: Recharts dashboard

**Files:**
- Modify: `frontend/src/components/Dashboard.jsx`

**Interfaces:**
- Consumes: `getStats()` (Task 9) returning the `/api/stats` shape (Task 8).

- [ ] **Step 1: Replace `frontend/src/components/Dashboard.jsx`**

```jsx
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getStats } from "../services/api";

function StatCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

function ChartCard({ title, children, empty }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title}</h3>
      {empty ? (
        <p className="flex h-56 items-center justify-center text-sm text-slate-400">No data yet</p>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getStats().then(setStats).catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="p-6 text-sm text-red-600">{error}</p>;
  if (!stats) return <p className="p-6 text-sm text-slate-500">Loading dashboard…</p>;

  const { totals } = stats;
  const perQuestion = stats.per_question.map((q, i) => ({ ...q, label: `Q${i + 1}` }));

  return (
    <div className="h-full space-y-4 overflow-y-auto p-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Documents" value={totals.documents} />
        <StatCard label="Chunks" value={totals.chunks} />
        <StatCard label="Questions" value={totals.questions} />
        <StatCard
          label="Avg speed"
          value={totals.avg_tokens_per_sec == null ? "—" : `${Math.round(totals.avg_tokens_per_sec)} tok/s`}
        />
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="Response time per question (ms)" empty={perQuestion.length === 0}>
          <LineChart data={perQuestion}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="ttft_ms" name="First token" stroke="#f59e0b" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="total_ms" name="Total" stroke="#4f46e5" strokeWidth={2} dot={false} />
          </LineChart>
        </ChartCard>
        <ChartCard title="Output speed per question (tokens/sec)" empty={perQuestion.length === 0}>
          <BarChart data={perQuestion}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="label" fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip />
            <Bar dataKey="tokens_per_sec" name="tokens/sec" fill="#f59e0b" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Questions per day" empty={stats.questions_per_day.length === 0}>
          <BarChart data={stats.questions_per_day}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" fontSize={12} />
            <YAxis allowDecimals={false} fontSize={12} />
            <Tooltip />
            <Bar dataKey="count" name="Questions" fill="#4f46e5" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Chunks per document" empty={stats.chunks_per_document.length === 0}>
          <BarChart data={stats.chunks_per_document} layout="vertical" margin={{ left: 24 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis type="number" allowDecimals={false} fontSize={12} />
            <YAxis type="category" dataKey="filename" width={120} fontSize={12} />
            <Tooltip />
            <Bar dataKey="chunks" name="Chunks" fill="#10b981" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ChartCard>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build and manual check**

Run: `npm run build`
Expected: build succeeds.

Manual: open the Dashboard tab with no data — four "No data yet" cards and "—" average. After uploading documents and asking a few questions, reopen it — stat cards and all four charts show values matching the chat badges.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Dashboard.jsx
git commit -m "feat: add Recharts usage and speed dashboard"
```

---

### Task 13: README and end-to-end verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

````markdown
# RAG Data Assistant

Upload PDF, TXT or DOCX documents and ask questions about them. Answers are grounded in your documents, cite file and page, and stream in real time from Groq. A dashboard charts response speed and usage.

**Stack:** React (Vite) · Tailwind CSS · Recharts · FastAPI · MongoDB Atlas (Beanie) · Atlas Vector Search · LangChain + LangGraph · Groq · HuggingFace `all-MiniLM-L6-v2`

## How it works

1. **Upload** (`POST /api/upload`) — text is extracted, split into ~1000-character chunks, embedded locally with `all-MiniLM-L6-v2` (384 dims) and stored in the `chunks` collection with Atlas Vector Search.
2. **Ask** (`POST /api/query`) — a LangGraph graph runs **retrieve** (vector search, top 4 chunks) → **generate** (ChatGroq with the chunks as context). Tokens stream to the browser as Server-Sent Events.
3. **Measure** — time to first token and tokens/second are stored with every answer and shown on the dashboard.

**Model note:** the original brief named `llama3-70b-8192`. Groq has retired its Llama chat models, so the app uses `openai/gpt-oss-120b` (set by `GROQ_MODEL`).

## Setup

**Requirements:** Python 3.10+ with [uv](https://docs.astral.sh/uv/), Node.js 20+, a free [MongoDB Atlas](https://www.mongodb.com/atlas) M0 cluster, a free [Groq API key](https://console.groq.com/keys).

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
````

- [ ] **Step 2: Run all automated checks**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -v` then `cd ../frontend && npm test && npm run build`
Expected: everything PASS (integration tests run, not skipped, once `MONGODB_URI` is set).

- [ ] **Step 3: Manual end-to-end against real Atlas + Groq**

1. Start the backend; confirm the log shows no vector-index warning (or create the index manually) and wait ~1 minute.
2. Start the frontend; upload a multi-page PDF, a TXT and a DOCX.
3. Ask a question answered on a specific PDF page → streamed answer cites `[file p.N]`; Sources list that page; ⚡ badge shows.
4. Ask an unrelated question → "I couldn't find that in your documents." with no Sources.
5. Ask a follow-up ("tell me more about that") in the same conversation → coherent answer.
6. Dashboard tab → totals and four charts populated.
7. Delete a document → it disappears; in Atlas, its chunks are gone. Delete a conversation → gone after refresh.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, architecture and model note"
```
