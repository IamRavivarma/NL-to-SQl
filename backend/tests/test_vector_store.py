from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_mongodb import MongoDBAtlasVectorSearch

from app.core.database import get_chunks_collection
from app.rag.vector_store import ChunkStore


async def test_delete_document_removes_only_that_documents_chunks(mongo):
    # Pins the contract delete_document relies on: LangChain stores chunk metadata as top-level fields.
    collection = get_chunks_collection()
    collection.delete_many({})
    store = ChunkStore(MongoDBAtlasVectorSearch(collection=collection, embedding=DeterministicFakeEmbedding(size=384)))

    meta = lambda doc_id, i: {"document_id": doc_id, "filename": f"{doc_id}.txt", "page": 1, "chunk_index": i}
    store.add_chunks(["a1", "a2", "a3", "b1"], [meta("A", 0), meta("A", 1), meta("A", 2), meta("B", 0)])

    assert store.delete_document("A") == 3
    remaining = list(collection.find({}, {"_id": 0, "text": 1, "document_id": 1}))
    assert remaining == [{"text": "b1", "document_id": "B"}]
    collection.delete_many({})


from app.rag.vector_store import VECTOR_INDEX_DEFINITION, VECTOR_INDEX_NAME, ensure_vector_index


class RecordingVectorStore:
    def __init__(self):
        self.calls = []

    def similarity_search_with_score(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return []


def test_search_can_be_limited_to_one_document():
    vector_store = RecordingVectorStore()
    store = ChunkStore(vector_store)
    store.search("leave days", 4, document_id="doc1")
    store.search("leave days", 4)
    (_, limited), (_, everything) = vector_store.calls
    assert limited["pre_filter"] == {"document_id": {"$eq": "doc1"}}
    assert "pre_filter" not in everything


def test_index_definition_allows_filtering_by_document():
    assert {"type": "filter", "path": "document_id"} in VECTOR_INDEX_DEFINITION["fields"]


class FakeCollection:
    name = "chunks"

    def __init__(self, indexes):
        self.indexes = indexes
        self.created, self.updated = [], []
        self.database = self

    def list_collection_names(self):
        return ["chunks"]

    def list_search_indexes(self):
        return self.indexes

    def create_search_index(self, model):
        self.created.append(model)

    def update_search_index(self, name, definition):
        self.updated.append((name, definition))


def test_existing_index_without_the_filter_is_updated():
    old = {"fields": [{"type": "vector", "path": "embedding", "numDimensions": 384, "similarity": "cosine"}]}
    collection = FakeCollection([{"name": VECTOR_INDEX_NAME, "latestDefinition": old}])
    ensure_vector_index(collection)
    assert collection.updated == [(VECTOR_INDEX_NAME, VECTOR_INDEX_DEFINITION)]
    assert collection.created == []


def test_up_to_date_index_is_left_alone():
    collection = FakeCollection([{"name": VECTOR_INDEX_NAME, "latestDefinition": VECTOR_INDEX_DEFINITION}])
    ensure_vector_index(collection)
    assert collection.updated == [] and collection.created == []
