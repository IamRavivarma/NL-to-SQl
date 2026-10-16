import logging
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter
from starlette.concurrency import run_in_threadpool

from app.ingestion.loaders import Page, load_pages
from app.models import StoredDocument

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


class IngestionError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int
    chunk_index: int


def split_pages(pages: list[Page]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for piece in _splitter.split_text(page.text):
            chunks.append(Chunk(text=piece, page=page.page_number, chunk_index=len(chunks)))
    return chunks


async def ingest_document(filename: str, content: bytes, store) -> StoredDocument:
    """Validate, split, embed and store a document. All-or-nothing: on failure nothing is left behind."""
    file_type, pages, page_count = load_pages(filename, content)
    chunks = split_pages(pages)

    document = StoredDocument(
        filename=filename,
        file_type=file_type,
        size_bytes=len(content),
        page_count=page_count,
        chunk_count=len(chunks),
    )
    await document.insert()
    document_id = str(document.id)

    try:
        # Embedding is CPU-bound and the vector store client is sync: keep both off the event loop.
        await run_in_threadpool(
            store.add_chunks,
            [chunk.text for chunk in chunks],
            [
                {"document_id": document_id, "filename": filename, "page": chunk.page, "chunk_index": chunk.chunk_index}
                for chunk in chunks
            ],
        )
    except Exception as exc:
        logger.exception("Storing chunks failed for %s", filename)
        try:
            await run_in_threadpool(store.delete_document, document_id)
        except Exception:
            # Keep the record: without it, any partial chunks would be orphaned and undeletable from the UI.
            logger.exception("Cleanup of partial chunks failed for document %s; keeping its record", document_id)
        else:
            await document.delete()
        raise IngestionError("Could not process the document.") from exc

    return document
