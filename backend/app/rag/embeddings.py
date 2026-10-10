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
