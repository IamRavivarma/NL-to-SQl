import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.query import router as query_router
from app.api.stats import router as stats_router
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
app.include_router(query_router)
app.include_router(conversations_router)
app.include_router(stats_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
