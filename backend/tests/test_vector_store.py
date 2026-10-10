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
