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
