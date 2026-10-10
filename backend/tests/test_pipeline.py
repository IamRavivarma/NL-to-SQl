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


async def test_ingest_keeps_record_when_cleanup_also_fails(mongo):
    # If partial chunks can't be removed, the record must stay so the user can see and delete the document.
    store = FakeChunkStore(fail_on_add=True, fail_on_delete=True)
    with pytest.raises(IngestionError, match="Could not process the document."):
        await ingest_document("guide.pdf", make_pdf(["Some text"]), store)
    assert await StoredDocument.count() == 1


async def test_ingest_rejects_invalid_file_before_touching_db(mongo):
    store = FakeChunkStore()
    with pytest.raises(DocumentLoadError):
        await ingest_document("data.csv", b"a,b", store)
    assert await StoredDocument.count() == 0
    assert store.added == []
