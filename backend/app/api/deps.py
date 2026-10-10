from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

from app.core.config import settings
from app.rag.vector_store import ChunkStore, get_chunk_store


def get_store() -> ChunkStore:
    return get_chunk_store()


def get_llm() -> BaseChatModel:
    return ChatGroq(model=settings.groq_model, api_key=settings.groq_api_key, temperature=0)
