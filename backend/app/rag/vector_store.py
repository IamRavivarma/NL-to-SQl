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
        {"type": "vector", "path": "embedding", "numDimensions": EMBEDDING_DIMENSIONS, "similarity": "cosine"},
        # Lets a search be limited to one document (the file selected in the sidebar).
        {"type": "filter", "path": "document_id"},
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

    def search(self, query: str, k: int = TOP_K, document_id: str | None = None) -> list[tuple[Document, float]]:
        kwargs = {"pre_filter": document_filter(document_id)} if document_id else {}
        return self._vector_store.similarity_search_with_score(
            query, k=k, oversampling_factor=OVERSAMPLING_FACTOR, **kwargs
        )


def document_filter(document_id: str) -> dict:
    return {"document_id": {"$eq": document_id}}


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
    """Create the Atlas vector index, or update it to the current definition (search indexes need the collection)."""
    database = collection.database
    if collection.name not in database.list_collection_names():
        database.create_collection(collection.name)
    existing = next((index for index in collection.list_search_indexes() if index["name"] == VECTOR_INDEX_NAME), None)
    if existing is not None:
        if existing.get("latestDefinition") != VECTOR_INDEX_DEFINITION:
            collection.update_search_index(VECTOR_INDEX_NAME, VECTOR_INDEX_DEFINITION)
        return
    collection.create_search_index(
        SearchIndexModel(definition=VECTOR_INDEX_DEFINITION, name=VECTOR_INDEX_NAME, type="vectorSearch")
    )
