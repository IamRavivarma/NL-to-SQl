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
    # Imported here: the model modules import utcnow from this module.
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
