from starlette.datastructures import UploadFile

from app.api.deps import get_store
from app.ingestion.loaders import MAX_FILE_BYTES
from app.main import app
from app.models import StoredDocument
from tests.fakes import FakeChunkStore
from tests.files import make_pdf


def use_store(store):
    app.dependency_overrides[get_store] = lambda: store
    return store


async def test_upload_pdf_returns_201_and_lists_document(client):
    store = use_store(FakeChunkStore())
    response = await client.post(
        "/api/upload", files={"file": ("guide.pdf", make_pdf(["Refunds take ten days"]), "application/pdf")}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "guide.pdf" and body["file_type"] == "pdf"
    assert body["page_count"] == 1 and body["chunk_count"] == 1
    assert len(store.added) == 1

    listed = (await client.get("/api/documents")).json()
    assert [d["id"] for d in listed] == [body["id"]]


async def test_upload_unsupported_type_returns_400(client):
    use_store(FakeChunkStore())
    response = await client.post("/api/upload", files={"file": ("old.xls", b"a,b", "application/vnd.ms-excel")})
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


async def test_upload_reads_at_most_the_size_limit_plus_one_byte(client, monkeypatch):
    # An oversized upload must be rejected without reading the whole body into memory.
    sizes = []
    original_read = UploadFile.read

    async def spy_read(self, size=-1):
        sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", spy_read)
    use_store(FakeChunkStore())
    response = await client.post(
        "/api/upload", files={"file": ("big.txt", b"x" * (MAX_FILE_BYTES + 10), "text/plain")}
    )
    assert response.status_code == 400
    assert "20 MB" in response.json()["detail"]
    assert sizes == [MAX_FILE_BYTES + 1]


async def test_upload_store_failure_returns_500_and_saves_nothing(client):
    use_store(FakeChunkStore(fail_on_add=True))
    response = await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})
    assert response.status_code == 500
    assert response.json()["detail"] == "Could not process the document."
    assert await StoredDocument.count() == 0


async def test_delete_removes_chunks_and_record(client):
    store = use_store(FakeChunkStore())
    doc_id = (await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})).json()["id"]

    response = await client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 204
    assert store.deleted == [doc_id]
    assert await StoredDocument.count() == 0


async def test_delete_keeps_record_when_chunk_delete_fails(client):
    use_store(FakeChunkStore())
    doc_id = (await client.post("/api/upload", files={"file": ("a.txt", b"hello world", "text/plain")})).json()["id"]

    use_store(FakeChunkStore(fail_on_delete=True))
    response = await client.delete(f"/api/documents/{doc_id}")
    assert response.status_code == 500
    assert await StoredDocument.count() == 1  # user can retry the delete


async def test_delete_unknown_document_returns_404(client):
    use_store(FakeChunkStore())
    response = await client.delete("/api/documents/650000000000000000000000")
    assert response.status_code == 404
