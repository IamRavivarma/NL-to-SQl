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
